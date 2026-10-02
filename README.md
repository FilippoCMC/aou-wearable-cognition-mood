# aou-wearable-cognition-mood

Analysis code for:

> Filippo Corponi, Matteo Reami, Michail Kalfas, Giuseppe Fanelli, Paolo Ossola, Sameer Jauhar, Allan H Young. **Domain-Specific
> Cognitive Impairment and Rest-Activity Phenotypes in Interepisode Mood Disorders.**
> *Manuscript under review.*

The study uses the *All of Us* Research Program (Curated Data Repository v9, Controlled Tier,
dataset `C2025Q4R6`). It asks two questions:

1. **Normative deviation.** Do participants with major depressive disorder (MDD) or bipolar
   disorder (BD), tested outside a mood episode, perform differently from non-clinical controls
   (NCC) on four remote cognitive tasks from the *Exploring the Mind* (EtM) battery: GradCPT,
   Flanker, Delay Discounting and Emotion Recognition? Each clinical participant's score is
   expressed as a deviation `D` from a normative model fitted on NCC.
2. **Rest-activity phenotypes.** In MDD, do Fitbit-derived mean daily steps, wake after sleep
   onset (WASO), total sleep time (TST) and sleep timing variability (STV), measured over the 90
   days before testing, predict `D`?

## Data access

The notebooks do not include any data, and the data cannot be shared. *All of Us* Controlled
Tier data are available to registered researchers through the
[*All of Us* Researcher Workbench](https://www.researchallofus.org/). To reproduce the analysis,
you need Controlled Tier access, a Verily Workbench workspace on CDR v9, and the
workspace resources listed below.

## Repository layout

| Path | Contents |
|---|---|
| `00_build_cache.ipynb` | One-time build of a per-participant Fitbit cache from the CDR wearable tables |
| `01_cohort.ipynb` | EtM scores and quality control, MDD / BD / NCC assignment, washout and Fitbit-coverage flags, attrition |
| `02_covariates.ipynb` | Age, sex, education, BMI, Charlson comorbidity index, latitude, race and ethnicity, psychiatric medication classes |
| `03a_wearable_pulls.ipynb` | Valid days (steps, heart-rate wear time) and valid nights (sleep) from the cache |
| `03b_feature_extraction.ipynb` | Per-task wearable features over the 90-day window before each test, photoperiod |
| `04a_modelling_main.ipynb` | NCC normative model, `D` scores, the 28 primary tests, Benjamini-Hochberg correction |
| `04b_modelling_sensitivity.ipynb` | Sensitivity analyses (NCC wearable arm, U-shaped TST, sample balance, antipsychotic exclusion) |
| `04c_modelling_power.ipynb` | Minimum detectable effect sizes |
| `05_summary.ipynb` | Tables and figures |
| `src/` | Shared helpers: workspace resources and I/O (`utils.py`), model and sample definitions (`analysis.py`), Charlson index (`cci.py`), wearable cache (`wearables_cache/`) |
| `scripts/` | Headless runner for notebooks 01–05 |

## Workspace resources

`src/utils.py` resolves resources by their Workbench resource id at import time
(`wb resource list`), so bucket names never appear in the code. Create these in the workspace:

| Resource id | Type | Use |
|---|---|---|
| `aou-wearable-cognition-mood` | GCS bucket | all outputs (override with the `AOU_MAIN_BUCKET_ID` environment variable) |
| `aou-fitbit-cache` | GCS bucket | wearable cache written by `00_build_cache`, read-only afterwards |
| `C2025Q4R6` | BigQuery dataset | CDR v9 Controlled Tier |

## Environment

The notebooks run on a Verily Workbench JupyterLab app (`n1-standard-4` is enough) in a
[uv](https://docs.astral.sh/uv/) environment registered as a Jupyter kernel. Package versions
are pinned in `pyproject.toml` and locked in `uv.lock` (Python 3.12). The `wb` and `gsutil`
command-line tools, and uv itself, come with the Workbench image, so nothing needs installing.

From a terminal at the repository root:

```bash
uv sync --locked
uv run python -m ipykernel install --user \
    --name aou-wearable-cognition-mood \
    --display-name "Python 3.12 (aou-wearable-cognition-mood)"
```

Reload the JupyterLab tab and select the kernel **Python 3.12 (aou-wearable-cognition-mood)**.
If `shutil.which('wb')` returns `None` inside the kernel, add the directories that `which wb
gsutil` reports in a terminal to the `env` block of the kernel spec (`jupyter kernelspec list`).

## Running the analysis

Run the notebooks from the repository root, in order:

1. `00_build_cache`: once, interactively, one modality at a time
   (sleep → steps → heart rate).
2. `01_cohort` → `02_covariates` → `03a_wearable_pulls` → `03b_feature_extraction`
3. `04a_modelling_main` → `04b_modelling_sensitivity` → `04c_modelling_power` → `05_summary`

`04c` appends minimum-detectable-effect columns to the result files written by `04a` and `04b`,
so it must run after both.

> **Cost.** `00_build_cache`, `01_cohort` and `02_covariates` run billable BigQuery queries.
> The heart-rate step of `00_build_cache` alone takes several hours. Notebooks 01–03b cache
> every pull in the output bucket and reuse it on later runs; set `OVERWRITE = True` at the top
> of a notebook to pull again. Notebooks 04a–05 read only from the bucket.

Notebooks 01–05 can also be run headlessly with [papermill](https://papermill.readthedocs.io/).
The job runs detached, so it survives a closed browser tab:

```bash
bash scripts/run_notebooks.sh                          # 01_cohort → 05_summary
bash scripts/run_notebooks.sh 04a_modelling_main.ipynb 04b_modelling_sensitivity.ipynb \
    04c_modelling_power.ipynb 05_summary.ipynb         # a subset, in order
tail -f logs/notebook_runs/driver_<timestamp>.log
```

The run stops at the first failing notebook. See `uv run python scripts/run_notebooks.py --help`
for options. For a long run, raise the app's "Stop after an idle time of" setting.

## Where the manuscript results come from

Aggregate outputs are written to `results/` in the output bucket and to `res/` on the workbench.

| Manuscript | Produced by | Output |
|---|---|---|
| Table 1, Table 3 | `05_summary` | `res/nb05/demo_mdd_ab.csv`, `demo_bd_ab.csv`, `demo_mdd_c.csv` |
| Table 2, Table 4 | `04a_modelling_main` | `res/nb04a/main_results.csv` |
| Figure 1 | `05_summary` | `res/nb05/forest_plot_normative.png` |
| eTable 2 | `01_cohort` | OMOP concept ids defined at the top of the notebook |
| eTable 3 | `05_summary` | `res/nb05/attrition_{mdd,bd,hc}.csv` |
| eTable 4 | `04c_modelling_power` | `res/nb04c/main_res_mdes.csv` |
| eTable 5 | `05_summary` | `res/nb05/demo_hc.csv`, `demo_hc_c.csv` |
| eTable 6 | `04b_modelling_sensitivity`, `04c_modelling_power` | `res/nb04b/sensitivity_hc_cognition-wearable.csv`, `res/nb04c/sensitivity_hc_mdes.csv` |
| eTable 7 | `04b_modelling_sensitivity` | `res/nb04b/mdd_normative_vs_fitbit_balance.csv` |
| eTable 8 | `04b_modelling_sensitivity` | `res/nb04b/sleep_duration_ushape_sensitivity.csv` |
| eTable 9 | `04b_modelling_sensitivity`, `05_summary` | `res/nb04b/antipsychotic_sensitivity.csv`, `res/nb05/table_a_antipsychotic_sensitivity.csv` |
| eFigure 1 | `05_summary` | `res/nb05/wearable_feature_distributions.png` |
| eFigure 2 | `05_summary` | `res/nb05/hc_residuals.png` |

In the code, the non-clinical control group is labelled `HC`.

## Data governance

The code follows the *All of Us* Data and Statistics Dissemination Policy. No participant-level
data leave the workbench, and any count, percentage or statistic describing fewer than 20
participants is suppressed. Consider clearing notebook outputs before committing
(`jupyter nbconvert --clear-output --inplace *.ipynb`).

## Use of generative AI

The authors used Claude Code (Anthropic) with Claude Opus models (versions 4.6 to 5.5) to help write, debug, review and 
document the code and documentation in this repository, for analyses specified by the authors. Claude had no access to 
the *All of Us* Researcher Workbench or to participant-level data, and did not generate or modify any data. 
The authors decided the study design, analytical methods and interpretation of results. All
AI-assisted code and text were reviewed, tested and validated by the authors, who take full
responsibility for the accuracy and integrity of this repository.

## Citation

If you use this code, please cite the article above. Citation details will be added on
publication.

## Licence

MIT, see [LICENSE](LICENSE).

## Acknowledgements

We gratefully acknowledge *All of Us* participants for their contributions, without whom this
research would not have been possible. We also thank the National Institutes of Health's
*All of Us* Research Program for making available the participant data examined in this study.
