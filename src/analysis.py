"""
Shared modelling code for 04a, 04b, 04c and 05.

Every notebook that fits the HC normative model or rebuilds an analytic sample
imports it from here, so the four notebooks cannot drift apart. This module has
no workspace side effects (it does not import src.utils), so it can be imported
and tested without BigQuery or GCS access.

Analytic samples, per task k:

* HC normative sample: HC, QC-passing, covs_eligible_normative_k.
* Normative sample (MDD or BD): mdd_eligible_k / bd_eligible_k, QC-passing,
  etm_washout_pass_k, covs_eligible_normative_k.
* Fitbit sample: the Normative sample plus fitbit_sufficient_k,
  wearable_washout_pass_k, covs_eligible_fitbit_k and wearable_eligible.
* HC Fitbit sample: the HC normative sample plus fitbit_sufficient_k,
  covs_eligible_fitbit_k and wearable_eligible (no episode washout applies).

Deviation score: D = (Y - Y_hat_HC) / sigma_HC, where Y_hat_HC and sigma_HC come
from the HC normative model
    Y ~ cr(age_k, df=4) + C(sex) + education_ordinal + C(touch_k).
For HC participants D is the in-sample standardised residual.
"""

from types import SimpleNamespace

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf
from patsy import cr  # noqa: F401  (used inside model formulas)

# ── Configuration ──────────────────────────────────────────────────────────────

ETM_TASKS = ['gradcpt', 'flanker', 'delaydiscounting', 'emorecog']

# Degrees of freedom of the natural cubic spline for age in the HC normative model.
NORM_AGE_SPLINE_DF = 4

# Minimum cell size: no estimate or count is reported for fewer participants.
MIN_CELL = 20

TASK_CONFIG = {
    'gradcpt': {
        'outcome':          'gradcpt_dprime',
        'qc_flags':         ['gradcpt_flag_non_response',
                             'gradcpt_flag_omission_error_rate',
                             'gradcpt_flag_trial_flags'],
        'higher_is_better': True,
        'label':            "GradCPT d'",
        'label_short':      'GradCPT',
        'direction':        'higher = better',
    },
    'flanker': {
        'outcome':          'flanker_rcs_interference',
        'qc_flags':         ['flanker_flag_accuracy',
                             'flanker_flag_trial_flags'],
        'higher_is_better': False,
        'label':            'Flanker RCS_int',
        'label_short':      'Flanker',
        'direction':        'higher = worse',
    },
    'delaydiscounting': {
        'outcome':          'delaydiscounting_lnk',
        'qc_flags':         ['delaydiscounting_flag_catch_trials',
                             'delaydiscounting_flag_median_rt'],
        'higher_is_better': False,
        'label':            'DD ln(k)',
        'label_short':      'DD',
        'direction':        'higher = worse',
    },
    'emorecog': {
        'outcome':          'emorecog_avg_accuracy',
        'qc_flags':         ['emorecog_flag_median_rtc',
                             'emorecog_flag_same_response',
                             'emorecog_flag_trial_flags'],
        'higher_is_better': True,
        'label':            'EmoRecog Avg Accuracy',
        'label_short':      'EmoRecog',
        'direction':        'higher = better',
    },
}

PHENOTYPES = ['mean_steps', 'mean_waso', 'STV', 'mean_sleep_duration']

# Columns taken from wearable_features when building a Fitbit sample.
WF_COLS = ['person_id', 'wearable_eligible'] + PHENOTYPES + ['photoperiod_hours']

# Main confirmatory pool: 3 Normative estimands (MDD, BD, BD - MDD contrast) and one
# Fitbit estimand per phenotype (MDD only), for each task.
N_NORMATIVE_PER_TASK = 3
N_FITBIT_PER_TASK    = len(PHENOTYPES)
MAIN_POOL_SIZE       = len(ETM_TASKS) * (N_NORMATIVE_PER_TASK + N_FITBIT_PER_TASK)

ELIGIBLE_COL = {'MDD': 'mdd_eligible_{task}', 'BD': 'bd_eligible_{task}'}


# ── Data preparation ───────────────────────────────────────────────────────────

def prepare_cohort(cohort):
    """Cast cohort_master columns to the dtypes the model formulas need (in place)."""
    cohort['cci']               = cohort['cci'].astype(float)
    cohort['education_ordinal'] = cohort['education_ordinal'].astype(float)
    cohort['age_at_etm']        = cohort['age_at_etm'].astype(float)
    for task in ETM_TASKS:
        cohort[f'age_at_etm_{task}'] = cohort[f'age_at_etm_{task}'].astype(float)
        cohort[f'bmi_{task}']        = cohort[f'bmi_{task}'].astype(float)
        cohort[f'cci_{task}']        = cohort[f'cci_{task}'].astype(float)
        # patsy cannot use pandas' nullable BooleanDtype inside C(touch_{task})
        cohort[f'touch_{task}']      = cohort[f'touch_{task}'].astype(object)
    return cohort


def qc_pass_mask(cohort, task):
    """Non-missing outcome and no QC flag set on the first administration."""
    cfg = TASK_CONFIG[task]
    return (
        cohort[cfg['outcome']].notna()
        & cohort[cfg['qc_flags']].fillna(0).eq(0).all(axis=1)
    )


# ── HC normative model and deviation scores ───────────────────────────────────

def normative_formula(task):
    out_col = TASK_CONFIG[task]['outcome']
    return (f'{out_col} ~ cr(age_at_etm_{task}, df={NORM_AGE_SPLINE_DF}) '
            f'+ C(sex) + education_ordinal + C(touch_{task})')


def fit_normative_model(cohort, task):
    """Fit the HC normative model for one task.

    Returns (m_norm, sigma_hc, hc): the fitted OLS model, the residual SD and the HC
    normative sample, which carries D (the in-sample standardised residual).
    """
    hc = cohort[
        qc_pass_mask(cohort, task)
        & (cohort['group'] == 'HC')
        & cohort[f'covs_eligible_normative_{task}']
    ].copy()
    m_norm   = smf.ols(normative_formula(task), data=hc).fit()
    sigma_hc = np.sqrt(m_norm.mse_resid)
    hc['D']  = m_norm.resid / sigma_hc
    return m_norm, sigma_hc, hc


def normative_sample(cohort, task, group, m_norm=None, sigma_hc=None):
    """MDD or BD Normative sample for one task, with D when a normative model is given."""
    sub = cohort[
        qc_pass_mask(cohort, task)
        & (cohort[ELIGIBLE_COL[group].format(task=task)].fillna(0) == 1)
        & cohort[f'etm_washout_pass_{task}'].fillna(False)
        & cohort[f'covs_eligible_normative_{task}']
    ].assign(group=group).copy()
    if m_norm is not None:
        out_col  = TASK_CONFIG[task]['outcome']
        sub['D'] = (sub[out_col] - m_norm.predict(sub)) / sigma_hc
    return sub


def fitbit_sample(norm_df, task, wf, group):
    """Fitbit sample: a Normative sample restricted by the wearable gates and merged
    with that task's wearable features."""
    wf_sub = wf[(wf['task'] == task) & (wf['group'] == group)][WF_COLS]
    sub = norm_df[
        norm_df[f'fitbit_sufficient_{task}'].fillna(False).astype(bool)
        & norm_df[f'wearable_washout_pass_{task}'].fillna(False).astype(bool)
        & (norm_df[f'covs_eligible_fitbit_{task}'] == 1)
    ].merge(wf_sub, on='person_id', how='left')
    return sub[sub['wearable_eligible'] == True].copy()  # noqa: E712 (NaN -> excluded)


def hc_fitbit_sample(hc, task, wf):
    """HC Fitbit sample: the HC normative sample restricted by the wearable gates."""
    wf_sub = wf[(wf['task'] == task) & (wf['group'] == 'HC')][WF_COLS]
    sub = hc[
        hc[f'fitbit_sufficient_{task}'].fillna(0).astype(bool)
        & (hc[f'covs_eligible_fitbit_{task}'].fillna(0) == 1)
    ].merge(wf_sub, on='person_id', how='left')
    return sub[sub['wearable_eligible'] == True].copy()  # noqa: E712


def phenotype_complete(df, pheno):
    """Rows with the phenotype and photoperiod both observed."""
    return df[df[pheno].notna() & df['photoperiod_hours'].notna()].copy()


# ── Models ─────────────────────────────────────────────────────────────────────

def fit_group_model(df_mdd, df_bd):
    """D ~ 0 + C(group) with HC3 SEs, and the BD - MDD Wald contrast (effect, sd, tvalue,
    pvalue as floats).

    The coefficients are the group mean deviations (Glass's delta: D is already in
    sigma_HC units, so no further standardisation is applied)."""
    comb = pd.concat([df_mdd, df_bd], ignore_index=True)
    m    = smf.ols('D ~ 0 + C(group)', data=comb).fit(cov_type='HC3')
    ct   = m.t_test('C(group)[BD] - C(group)[MDD]')
    # t_test returns 1-element arrays, which NumPy >= 2 will not convert with float();
    # expose the contrast as plain floats instead.
    contrast = SimpleNamespace(**{k: np.asarray(getattr(ct, k)).item()
                                  for k in ('effect', 'sd', 'tvalue', 'pvalue')})
    return m, contrast


def residualise_phenotype(df, task, pheno):
    """P_z: residual of pheno ~ age + sex + BMI + CCI + photoperiod, scaled to SD 1."""
    m_w = smf.ols(
        f'{pheno} ~ age_at_etm_{task} + C(sex) + bmi_{task} + cci_{task} + photoperiod_hours',
        data=df,
    ).fit()
    resid = df[pheno] - m_w.predict(df)
    return resid / resid.std()


def fit_phenotype_association(df, task, pheno):
    """D ~ P_z with HC3 SEs. Returns (model, Pearson r between D and P_z, df with P_z)."""
    df = df.copy()
    df['P_z'] = residualise_phenotype(df, task, pheno)
    m = smf.ols('D ~ P_z', data=df).fit(cov_type='HC3')
    r = float(np.corrcoef(df['D'], df['P_z'])[0, 1])
    return m, r, df


# ── Result rows ────────────────────────────────────────────────────────────────

def result_row(*, task, analysis, phenotype, group, n_hc, n_mdd, n_bd,
               beta, se, t, p, effect_size, r2):
    """One estimate in the shared results schema (95% CI = beta +/- 1.96 SE)."""
    return dict(
        task=task, analysis=analysis, phenotype=phenotype, group=group,
        n_hc=int(n_hc),
        n_mdd=int(n_mdd) if n_mdd is not None else None,
        n_bd=int(n_bd)   if n_bd  is not None else None,
        beta=float(beta), se_hc3=float(se),
        ci_lo=float(beta - 1.96 * se),
        ci_hi=float(beta + 1.96 * se),
        t_stat=float(t), p_value=float(p),
        p_bh=None, significant=None,
        effect_size=float(effect_size) if effect_size is not None else None,
        r2=float(r2) if r2 is not None else None,
        suppressed=False,
    )


def suppressed_row(*, task, analysis, phenotype, group, n_hc, n_mdd, n_bd):
    """Placeholder for a cell below MIN_CELL: kept in the table, never estimated."""
    return dict(
        task=task, analysis=analysis, phenotype=phenotype, group=group,
        n_hc=int(n_hc),
        n_mdd=int(n_mdd) if n_mdd is not None else None,
        n_bd=int(n_bd)   if n_bd  is not None else None,
        beta=None, se_hc3=None, ci_lo=None, ci_hi=None,
        t_stat=None, p_value=None, p_bh=None, significant=None,
        effect_size=None, r2=None, suppressed=True,
    )


RESULT_COLUMNS = [
    'task', 'analysis', 'phenotype', 'group',
    'n_hc', 'n_mdd', 'n_bd',
    'beta', 'se_hc3', 'ci_lo', 'ci_hi',
    't_stat', 'p_value', 'p_bh', 'significant',
    'effect_size', 'r2', 'suppressed',
]
