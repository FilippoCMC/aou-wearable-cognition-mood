# Quan (2005) ICD-9 and Quan (2011) ICD-10 code lists for the Charlson Comorbidity Index,
# scored with the original Charlson (1987) weights (CCI_WEIGHTS).
# Psychiatric codes (F-prefix and ICD-9 29x/30x/31x) are excluded at query time in
# 02_covariates; this also removes the F00-F03/F051 and 290/2941 dementia codes, leaving
# G30/G311/3312 in that domain.
# Source: comorbidipy (https://github.com/vvcb/comorbidipy), TraCS/UNC mapping.
#
# Only ICD-9-CM and ICD-10-CM source codes are scored, each against its own list
# (CCI_LISTS). Other source vocabularies (SNOMED, ICD-10-PCS, ...) are numeric or
# alphanumeric strings that can prefix-match these lists by accident, and ICD-9-CM
# V-codes start with a letter, so the vocabulary cannot be inferred from the code.

CCI_ICD9 = {
    "mi": ("410", "412"),
    "chf": (
        "39891", "40201", "40211", "40291", "40401", "40403", "40411", "40413",
        "40491", "40493", "4254", "4255", "4256", "4257", "4258", "4259", "428",
    ),
    "pvd": (
        "0930", "4373", "440", "441", "4431", "4432", "4433", "4434", "4435",
        "4436", "4437", "4438", "4439", "4471", "5571", "5579", "V434",
    ),
    "cvd": ("36234", "430", "431", "432", "433", "434", "435", "436", "437", "438"),
    "dementia": ("290", "2941", "3312"),
    "copd": (
        "4168", "4169", "490", "491", "492", "493", "494", "495", "496", "497",
        "498", "499", "500", "501", "502", "503", "504", "505", "5064", "5081", "5088",
    ),
    "rheumd": (
        "4465", "7100", "7101", "7102", "7103", "7104", "7140", "7141", "7142",
        "7148", "725",
    ),
    "pud": ("531", "532", "533", "534"),
    "mild_liver": (
        "07022", "07023", "07032", "07033", "07044", "07054", "0706", "0709",
        "570", "571", "5733", "5734", "5738", "5739", "V427",
    ),
    "dm_no_cc": ("2500", "2501", "2502", "2503", "2508", "2509"),
    "dm_cc": ("2504", "2505", "2506", "2507"),
    "hemiplegia": (
        "3341", "342", "343", "3440", "3441", "3442", "3443", "3444", "3445",
        "3446", "3449",
    ),
    "renal": (
        "40301", "40311", "40391", "40402", "40403", "40412", "40413", "40492",
        "40493", "582", "5830", "5831", "5832", "5833", "5834", "5835", "5836",
        "5837", "585", "586", "5880", "V420", "V451", "V56",
    ),
    "malignancy": (
        "140", "141", "142", "143", "144", "145", "146", "147", "148", "149",
        "150", "151", "152", "153", "154", "155", "156", "157", "158", "159",
        "160", "161", "162", "163", "164", "165", "166", "167", "168", "169",
        "170", "171", "172", "174", "175", "176", "177", "178", "179", "180",
        "181", "182", "183", "184", "185", "186", "187", "188", "189", "190",
        "191", "192", "193", "194", "195", "200", "201", "202", "203", "204",
        "205", "206", "207", "208", "2386",
    ),
    "sev_liver": (
        "4560", "4561", "4562", "5722", "5723", "5724", "5725", "5726", "5727", "5728",
    ),
    "metastatic": ("196", "197", "198", "199"),
    "aids": ("042", "043", "044"),
}

CCI_ICD10 = {
    "mi": ("I21", "I22", "I252"),
    "chf": (
        "I099", "I110", "I130", "I132", "I255", "I420", "I425", "I426", "I427",
        "I428", "I429", "I43", "I50", "P290",
    ),
    "pvd": (
        "I70", "I71", "I731", "I738", "I739", "I771", "I790", "I792",
        "K551", "K558", "K559", "Z958", "Z959",
    ),
    "cvd": (
        "G45", "G46", "H340", "I60", "I61", "I62", "I63", "I64", "I65",
        "I66", "I67", "I68", "I69",
    ),
    "dementia": ("F00", "F01", "F02", "F03", "F051", "G30", "G311"),
    "copd": (
        "I278", "I279", "J40", "J41", "J42", "J43", "J44", "J45", "J46", "J47",
        "J60", "J61", "J62", "J63", "J64", "J65", "J66", "J67", "J684", "J701", "J703",
    ),
    "rheumd": ("M05", "M06", "M315", "M32", "M33", "M34", "M351", "M353", "M360"),
    "pud": ("K25", "K26", "K27", "K28"),
    "mild_liver": (
        "B18", "K700", "K701", "K702", "K703", "K709", "K713", "K714", "K715",
        "K717", "K73", "K74", "K760", "K762", "K763", "K764", "K768", "K769", "Z944",
    ),
    "dm_no_cc": (
        "E100", "E101", "E106", "E108", "E109", "E110", "E111", "E116", "E118",
        "E119", "E120", "E121", "E126", "E128", "E129", "E130", "E131", "E136",
        "E138", "E139", "E140", "E141", "E146", "E148", "E149",
    ),
    "dm_cc": (
        "E102", "E103", "E104", "E105", "E107", "E112", "E113", "E114", "E115",
        "E117", "E122", "E123", "E124", "E125", "E127", "E132", "E133", "E134",
        "E135", "E137", "E142", "E143", "E144", "E145", "E147",
    ),
    "hemiplegia": (
        "G041", "G114", "G801", "G802", "G81", "G82", "G830", "G831", "G832",
        "G833", "G834", "G839",
    ),
    "renal": (
        "I120", "I131", "N032", "N033", "N034", "N035", "N036", "N037", "N052",
        "N053", "N054", "N055", "N056", "N057", "N18", "N19", "N250", "Z490",
        "Z491", "Z492", "Z940", "Z992",
    ),
    "malignancy": (
        "C00", "C01", "C02", "C03", "C04", "C05", "C06", "C07", "C08", "C09",
        "C10", "C11", "C12", "C13", "C14", "C15", "C16", "C17", "C18", "C19",
        "C20", "C21", "C22", "C23", "C24", "C25", "C26", "C30", "C31", "C32",
        "C33", "C34", "C37", "C38", "C39", "C40", "C41", "C43", "C45", "C46",
        "C47", "C48", "C49", "C50", "C51", "C52", "C53", "C54", "C55", "C56",
        "C57", "C58", "C60", "C61", "C62", "C63", "C64", "C65", "C66", "C67",
        "C68", "C69", "C70", "C71", "C72", "C73", "C74", "C75", "C76", "C81",
        "C82", "C83", "C84", "C85", "C88", "C90", "C91", "C92", "C93", "C94",
        "C95", "C96", "C97",
    ),
    "sev_liver": (
        "I850", "I859", "I864", "I982", "K704", "K711", "K721", "K729",
        "K765", "K766", "K767",
    ),
    "metastatic": ("C77", "C78", "C79", "C80"),
    "aids": ("B20", "B21", "B22", "B24"),
}

CCI_WEIGHTS = {
    "mi": 1, "chf": 1, "pvd": 1, "cvd": 1, "dementia": 1, "copd": 1,
    "rheumd": 1, "pud": 1, "mild_liver": 1, "dm_no_cc": 1,
    "hemiplegia": 2, "renal": 2, "dm_cc": 2, "malignancy": 2,
    "sev_liver": 3, "metastatic": 6, "aids": 6,
}

# Severity hierarchy: if the more-severe variant is present, zero out the less-severe.
ASSIGN0_PAIRS = [
    ("mild_liver", "sev_liver"),
    ("dm_no_cc",   "dm_cc"),
    ("malignancy", "metastatic"),
]


CCI_LISTS = {"ICD9CM": CCI_ICD9, "ICD10CM": CCI_ICD10}


def match_cci(code: str, mapping: dict) -> list:
    """Return all CCI category keys whose prefix tuple matches `code`."""
    return [cat for cat, prefixes in mapping.items() if code.startswith(prefixes)]


def compute_cci(cci_raw_df, cohort_pids):
    """
    Score each person in `cohort_pids` from a date-filtered (person_id, vocabulary_id, code)
    frame: prefix-match each code against its own vocabulary's list, apply the severity
    hierarchy, and return (person_id, cci). People with no matching codes get cci = 0.
    Raises unless every row is ICD9CM or ICD10CM.
    """
    import pandas as pd
    from tqdm.auto import tqdm

    other = set(cci_raw_df["vocabulary_id"].dropna().unique()) - set(CCI_LISTS)
    if other or cci_raw_df["vocabulary_id"].isna().any():
        raise ValueError(
            f"compute_cci expects ICD9CM/ICD10CM rows only; found {sorted(other)}"
            + (" and missing vocabulary_id" if cci_raw_df["vocabulary_id"].isna().any() else "")
        )

    codes = cci_raw_df["code"].values
    vocabs = cci_raw_df["vocabulary_id"].values
    pids  = cci_raw_df["person_id"].values

    records = []
    for pid, vocab, code in tqdm(zip(pids, vocabs, codes), total=len(cci_raw_df),
                                 desc="CCI matching"):
        if not code:
            continue
        cats = match_cci(code, CCI_LISTS[vocab])
        for cat in cats:
            records.append((pid, cat))

    matched = pd.DataFrame(records, columns=["person_id", "category"])

    if matched.empty:
        return pd.DataFrame({"person_id": list(cohort_pids), "cci": 0})

    flags = (
        matched.drop_duplicates()
        .assign(val=1)
        .pivot_table(
            index="person_id", columns="category",
            values="val", aggfunc="max", fill_value=0,
        )
        .reset_index()
    )
    for cat in CCI_WEIGHTS:
        if cat not in flags.columns:
            flags[cat] = 0
    for less_severe, more_severe in ASSIGN0_PAIRS:
        flags[less_severe] = flags[less_severe].where(flags[more_severe] == 0, other=0)
    flags["cci"] = sum(
        flags[cat] * w for cat, w in CCI_WEIGHTS.items() if cat in flags.columns
    )
    result = (
        pd.DataFrame({"person_id": list(cohort_pids)})
        .merge(flags[["person_id", "cci"]], on="person_id", how="left")
    )
    result["cci"] = result["cci"].fillna(0).astype(int)
    return result
