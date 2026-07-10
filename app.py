import streamlit as st
import pandas as pd
import numpy as np
import re
from io import BytesIO
from pathlib import Path

st.set_page_config(page_title="Lead/Company File Consolidator", layout="wide")

# =========================
# Config
# =========================
MASTER_CORE_HEADERS = [
    "Decision Maker",
    "Job Title",
    "Organisation",
    "Country",
    "Segment",
    "Email",
    "Website",
    "Location",
    "LinkedIn URL",
    "Source File",
]

FREE_EMAIL_DOMAINS = {
    "gmail.com", "yahoo.com", "hotmail.com", "outlook.com", "aol.com",
    "icloud.com", "live.com", "msn.com", "me.com", "protonmail.com"
}

EUROPEAN_COUNTRIES = {
    "uk", "united kingdom", "great britain", "britain", "england", "scotland", "wales", "northern ireland", "gb", "gbr",
    "ireland", "republic of ireland", "ie",
    "austria", "belgium", "bulgaria", "croatia", "cyprus", "czech republic", "czechia",
    "denmark", "estonia", "finland", "france", "germany", "greece", "hungary",
    "iceland", "italy", "latvia", "liechtenstein", "lithuania", "luxembourg",
    "malta", "netherlands", "norway", "poland", "portugal", "romania", "slovakia",
    "slovenia", "spain", "sweden", "switzerland",
    "belarus", "bosnia and herzegovina", "serbia", "montenegro", "north macedonia",
    "albania", "andorra", "armenia", "azerbaijan", "georgia", "kosovo", "moldova",
    "monaco", "san marino", "vatican city", "eu", "europe", "european union"
}

TLD_TO_COUNTRY = {
    ".uk": "united kingdom",
    ".ie": "ireland",
    ".de": "germany",
    ".fr": "france",
    ".nl": "netherlands",
    ".it": "italy",
    ".es": "spain",
    ".se": "sweden",
    ".no": "norway",
    ".ch": "switzerland",
    ".be": "belgium",
    ".dk": "denmark",
    ".fi": "finland",
    ".at": "austria",
    ".pt": "portugal",
    ".pl": "poland",
    ".ro": "romania",
    ".cz": "czech republic",
    ".hu": "hungary",
    ".gr": "greece",
    ".bg": "bulgaria",
    ".sk": "slovakia",
    ".si": "slovenia",
    ".lv": "latvia",
    ".lt": "lithuania",
    ".lu": "luxembourg",
    ".mt": "malta",
    ".is": "iceland",
    ".rs": "serbia",
    ".me": "montenegro",
    ".al": "albania",
    ".ba": "bosnia and herzegovina",
    ".hr": "croatia",
    ".ee": "estonia",
    ".cy": "cyprus",
    ".eu": "eu",
    ".ac.uk": "united kingdom",
    ".gov.uk": "united kingdom",
    ".org.uk": "united kingdom",
    ".co.uk": "united kingdom"
}

# =========================
# Helpers
# =========================
def normalize_text(val):
    if pd.isna(val):
        return ""
    return str(val).replace("\n", " ").replace("\r", " ").strip()

def clean_col_name(col):
    c = normalize_text(col).lower()
    c = re.sub(r"[^a-z0-9]+", " ", c).strip()
    return c

def is_blank(val):
    s = normalize_text(val).lower()
    return s in {"", "nan", "none", "null"}

def safe_read_file(uploaded_file):
    suffix = Path(uploaded_file.name).suffix.lower()
    if suffix == ".csv":
        for enc in ["utf-8-sig", "utf-8", "latin-1", "cp1252"]:
            try:
                uploaded_file.seek(0)
                return pd.read_csv(uploaded_file, dtype=str)
            except Exception:
                continue
        uploaded_file.seek(0)
        return pd.read_csv(uploaded_file, dtype=str, encoding_errors="ignore")
    elif suffix in [".xlsx", ".xls"]:
        uploaded_file.seek(0)
        return pd.read_excel(uploaded_file, dtype=str)
    else:
        raise ValueError(f"Unsupported file format: {suffix}")

def infer_website_from_email(email):
    email = normalize_text(email).lower()
    if "@" not in email:
        return ""
    domain = email.split("@")[-1].strip()
    if domain in FREE_EMAIL_DOMAINS or "." not in domain:
        return ""
    return f"www.{domain}"

def normalize_website(val):
    s = normalize_text(val).lower().strip()
    if not s:
        return ""
    s = s.replace("http://", "").replace("https://", "")
    s = s.strip("/")
    return s

def extract_linkedin_url(row):
    for col in row.index:
        val = normalize_text(row[col])
        if "linkedin.com/" in val.lower():
            return val
    return ""

def looks_like_linkedin_url(val):
    s = normalize_text(val).lower()
    return "linkedin.com/" in s

def looks_like_url(val):
    s = normalize_text(val).lower()
    return s.startswith(("http://", "https://", "www.")) or bool(re.search(r"\b[a-z0-9.-]+\.[a-z]{2,}\b", s))

def looks_like_email(val):
    s = normalize_text(val).lower()
    return bool(re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", s))

def looks_like_address(val):
    s = normalize_text(val)
    s_lower = s.lower()
    if not s:
        return False

    comma_count = s.count(",")
    digit_count = sum(ch.isdigit() for ch in s)

    address_keywords = [
        "street", "st ", " st,", "road", "rd ", " avenue", "ave ", "lane", "drive",
        "park", "square", "building", "floor", "suite", "postcode", "zip",
        "house", "campus", "business park", "industrial estate"
    ]

    location_keywords = [
        "london", "manchester", "birmingham", "leeds", "oxford", "cambridge",
        "dublin", "paris", "berlin", "madrid", "amsterdam", "brussels",
        "england", "scotland", "wales", "united kingdom", "ireland", "france",
        "germany", "spain", "netherlands", "belgium", "italy", "norway",
        "sweden", "finland", "switzerland", "denmark"
    ]

    if comma_count >= 3 and digit_count >= 1:
        return True
    if any(k in s_lower for k in address_keywords) and digit_count >= 1:
        return True
    if any(k in s_lower for k in location_keywords) and comma_count >= 2 and digit_count >= 1:
        return True

    return False

def normalize_country_text(val):
    s = normalize_text(val).lower()
    s = re.sub(r"[^\w\s/,&\-]", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s

def infer_country_from_website(website):
    site = normalize_website(website)
    if not site:
        return ""
    for tld, country in sorted(TLD_TO_COUNTRY.items(), key=lambda x: len(x[0]), reverse=True):
        if site.endswith(tld.replace(".", "")) or tld in site:
            return country
    return ""

def country_is_uk_europe(country_cell, website_cell=""):
    s = normalize_country_text(country_cell)

    if not s:
        inferred = infer_country_from_website(website_cell)
        return inferred in EUROPEAN_COUNTRIES

    tokens = re.split(r"[/,;&|]+", s)
    tokens = [t.strip() for t in tokens if t.strip()]

    for t in tokens:
        if t in EUROPEAN_COUNTRIES:
            return True
        if "united kingdom" in t or t == "uk" or t == "gb":
            return True
        if "europe" in t or t == "eu":
            return True

    inferred = infer_country_from_website(website_cell)
    return inferred in EUROPEAN_COUNTRIES

def is_valid_person_name(val):
    s = normalize_text(val)
    s_lower = s.lower()

    if not s or len(s) < 2:
        return False
    if looks_like_linkedin_url(s) or looks_like_url(s) or looks_like_email(s):
        return False
    if looks_like_address(s):
        return False
    if s_lower in {"name", "contact", "decision maker", "unknown"}:
        return False
    if sum(ch.isdigit() for ch in s) > 3:
        return False

    return True

def is_valid_company_name(val):
    s = normalize_text(val)
    s_lower = s.lower()

    if not s or s_lower in {"nan", "none", "null", "organisation", "organization", "company name", "account"}:
        return False
    if looks_like_linkedin_url(s):
        return False
    if s_lower.startswith(("http://", "https://", "www.")):
        return False
    if looks_like_email(s):
        return False
    if looks_like_address(s):
        return False
    if sum(ch.isdigit() for ch in s) > 8:
        return False

    # Reject obvious search strings / prompts / junk
    junk_patterns = [
        r"site:linkedin\.com",
        r"\bnot job\b",
        r"\bor careers\b",
        r"\brecruiter\b",
        r"\bhead of\b",
        r"\bdirector of\b",
        r"\bchief\b",
        r"\bmanager\b",
        r"\bconsultant\b",
        r"\bspeaker\b",
        r"\binternship\b",
        r"\bopen for\b"
    ]
    for pat in junk_patterns:
        if re.search(pat, s_lower):
            return False

    return True

def dedupe_key_company(name, website):
    return f"{normalize_text(name).lower()}||{normalize_website(website)}"

def map_columns(df):
    file_mapping = {}
    master_headers = MASTER_CORE_HEADERS.copy()

    for col in df.columns:
        norm_col = clean_col_name(col)

        # PERSON / CONTACT
        if any(k in norm_col for k in ["decision maker", "contact person", "contact name", "full name"]):
            file_mapping[col] = "Decision Maker"

        elif norm_col == "name":
            file_mapping[col] = col  # leave plain "Name" untouched to avoid wrong forced mapping

        elif any(k in norm_col for k in ["job title", "title", "designation", "role", "position"]):
            file_mapping[col] = "Job Title"

        # ORGANISATION
        elif any(k in norm_col for k in [
            "organisation", "organization", "company", "company name",
            "account", "institution", "school", "university", "employer"
        ]):
            file_mapping[col] = "Organisation"

        elif "country" in norm_col or "region" == norm_col:
            file_mapping[col] = "Country"

        elif any(k in norm_col for k in ["segment", "industry", "vertical", "category", "type"]):
            file_mapping[col] = "Segment"

        elif "email" in norm_col:
            file_mapping[col] = "Email"

        elif any(k in norm_col for k in ["website", "web site", "domain", "company url", "organisation url", "organization url"]):
            file_mapping[col] = "Website"

        elif any(k in norm_col for k in ["location", "city", "address", "hq", "head office", "office"]):
            file_mapping[col] = "Location"

        elif "linkedin" in norm_col:
            file_mapping[col] = "LinkedIn URL"

        else:
            file_mapping[col] = col
            if col not in master_headers:
                master_headers.append(col)

    return file_mapping, master_headers

def standardize_df(df, source_name):
    df = df.copy()
    df.columns = [normalize_text(c) for c in df.columns]
    file_mapping, master_headers = map_columns(df)

    std = pd.DataFrame(columns=master_headers)

    for old_col, new_col in file_mapping.items():
        std[new_col] = df[old_col].astype(str)

    for col in master_headers:
        if col not in std.columns:
            std[col] = ""

    std["Source File"] = source_name

    # derive LinkedIn URL if hidden inside any field
    if "LinkedIn URL" not in std.columns:
        std["LinkedIn URL"] = ""
    std["LinkedIn URL"] = std["LinkedIn URL"].replace("nan", "").fillna("")
    derived_li = df.apply(extract_linkedin_url, axis=1)
    std["LinkedIn URL"] = np.where(std["LinkedIn URL"].astype(str).str.strip() == "", derived_li, std["LinkedIn URL"])

    # derive Website from email if blank
    std["Website"] = std["Website"].replace("nan", "").fillna("")
    std["Email"] = std["Email"].replace("nan", "").fillna("")
    std["Website"] = np.where(
        std["Website"].astype(str).str.strip() == "",
        std["Email"].apply(infer_website_from_email),
        std["Website"]
    )

    return std

def build_master_df(files):
    all_dfs = []
    errors = []

    for f in files:
        try:
            raw = safe_read_file(f)
            raw = raw.fillna("")
            std = standardize_df(raw, f.name)
            all_dfs.append(std)
        except Exception as e:
            errors.append(f"{f.name}: {e}")

    if all_dfs:
        master_df = pd.concat(all_dfs, ignore_index=True)
    else:
        master_df = pd.DataFrame(columns=MASTER_CORE_HEADERS)

    # clean whitespace
    for col in master_df.columns:
        master_df[col] = master_df[col].astype(str).apply(normalize_text)

    return master_df, errors

def build_contact_master(master_df):
    df = master_df.copy()

    # Keep broad contact output but clean obvious junk
    if "Decision Maker" in df.columns:
        df = df[
            (df["Decision Maker"].apply(lambda x: is_blank(x) or is_valid_person_name(x)))
        ].copy()

    # clean website
    df["Website"] = df["Website"].apply(normalize_website)

    return df.reset_index(drop=True)

def build_company_master(master_df):
    df = master_df.copy()

    for c in ["Organisation", "Country", "Segment", "Website", "Location", "Decision Maker", "LinkedIn URL"]:
        if c not in df.columns:
            df[c] = ""

    # Prefer Organisation only for company master
    df["Company Name"] = df["Organisation"].astype(str).apply(normalize_text)

    # Backup logic only if Organisation blank:
    # Use a few safe institution-like headers if present, but never generic person/name/linkedin/address/url values
    if "Company Name" not in df.columns:
        df["Company Name"] = ""

    # Clean Website
    df["Website"] = df["Website"].apply(normalize_website)

    # Validate company name
    df["company_valid"] = df["Company Name"].apply(is_valid_company_name)

    # Filter UK + Europe only
    df["country_ok"] = df.apply(lambda r: country_is_uk_europe(r.get("Country", ""), r.get("Website", "")), axis=1)

    # Remove rows where company name looks like LinkedIn or URL, visible in your file output
    df = df[df["company_valid"] & df["country_ok"]].copy()

    # If country blank, infer from website
    df["Country"] = np.where(
        df["Country"].astype(str).str.strip() == "",
        df["Website"].apply(infer_country_from_website).str.title(),
        df["Country"]
    )

    # Final shape
    company_df = df[["Company Name", "Country", "Segment", "Website", "Location"]].copy()

    # Additional cleanup
    company_df["Company Name"] = company_df["Company Name"].apply(normalize_text)
    company_df["Country"] = company_df["Country"].apply(normalize_text)
    company_df["Segment"] = company_df["Segment"].apply(normalize_text)
    company_df["Website"] = company_df["Website"].apply(normalize_text)
    company_df["Location"] = company_df["Location"].apply(normalize_text)

    # Drop junk placeholders
    company_df = company_df[
        company_df["Company Name"].apply(is_valid_company_name)
    ].copy()

    # Dedupe
    company_df["dedupe_key"] = company_df.apply(lambda r: dedupe_key_company(r["Company Name"], r["Website"]), axis=1)
    company_df = company_df.drop_duplicates(subset=["dedupe_key"], keep="first").drop(columns=["dedupe_key"])

    # Sort
    company_df = company_df.sort_values(by=["Country", "Company Name"], na_position="last").reset_index(drop=True)

    return company_df

def to_excel_bytes(sheets_dict):
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        for sheet_name, df in sheets_dict.items():
            safe_name = sheet_name[:31]
            df.to_excel(writer, sheet_name=safe_name, index=False)
    output.seek(0)
    return output

def to_csv_bytes(df):
    return df.to_csv(index=False).encode("utf-8-sig")

# =========================
# UI
# =========================
st.title("Lead & Company Consolidator")
st.caption("Upload CSV/XLSX files, standardize fields, clean bad rows, and extract a UK + Europe company master.")

uploaded_files = st.file_uploader(
    "Upload one or more CSV/XLSX files",
    type=["csv", "xlsx", "xls"],
    accept_multiple_files=True
)

if uploaded_files:
    master_df, errors = build_master_df(uploaded_files)

    if errors:
        st.warning("Some files could not be processed:")
        for e in errors:
            st.write(f"- {e}")

    contact_df = build_contact_master(master_df)
    company_df = build_company_master(master_df)

    # Metrics
    c1, c2, c3 = st.columns(3)
    c1.metric("Total consolidated rows", len(master_df))
    c2.metric("Clean contact rows", len(contact_df))
    c3.metric("Clean UK + Europe companies", len(company_df))

    # Tabs
    tab1, tab2, tab3, tab4 = st.tabs([
        "Master Contact Data",
        "Company Master (UK + Europe)",
        "Quality Checks",
        "Downloads"
    ])

    with tab1:
        st.subheader("Master Contact Data")
        st.write("Standardized full dataset across uploaded files.")
        st.dataframe(contact_df, use_container_width=True, height=550)

    with tab2:
        st.subheader("Company Master (UK + Europe only)")
        st.write("Clean companies only. LinkedIn URLs, website strings, addresses, and non-UK/Europe rows are excluded.")
        st.dataframe(company_df, use_container_width=True, height=550)

    with tab3:
        st.subheader("Quality Checks")

        qc1 = master_df[master_df["Organisation"].apply(looks_like_linkedin_url)][["Organisation", "Country", "Website", "Source File"]].copy()
        qc2 = master_df[master_df["Organisation"].apply(looks_like_address)][["Organisation", "Country", "Website", "Source File"]].copy()
        qc3 = master_df[~master_df.apply(lambda r: country_is_uk_europe(r.get("Country", ""), r.get("Website", "")), axis=1)][["Organisation", "Country", "Website", "Source File"]].copy()

        st.markdown("**Organisation values that look like LinkedIn URLs**")
        st.dataframe(qc1, use_container_width=True, height=220)

        st.markdown("**Organisation values that look like addresses**")
        st.dataframe(qc2, use_container_width=True, height=220)

        st.markdown("**Rows excluded from company master because country is outside UK/Europe**")
        st.dataframe(qc3, use_container_width=True, height=220)

    with tab4:
        st.subheader("Downloads")

        excel_bytes = to_excel_bytes({
            "Master Contact Data": contact_df,
            "Company Master UK Europe": company_df,
            "Raw Consolidated": master_df
        })

        st.download_button(
            label="Download Excel workbook",
            data=excel_bytes,
            file_name="consolidated_output_uk_europe_clean.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

        st.download_button(
            label="Download Company Master CSV",
            data=to_csv_bytes(company_df),
            file_name="company_master_uk_europe_clean.csv",
            mime="text/csv"
        )

        st.download_button(
            label="Download Master Contact CSV",
            data=to_csv_bytes(contact_df),
            file_name="master_contact_data_clean.csv",
            mime="text/csv"
        )

else:
    st.info("Upload one or more files to begin.")

st.markdown("---")
st.caption("Rules applied: UK + Europe only for company extraction; LinkedIn URLs removed from company names; website/address-like rows rejected; website can be inferred from business email.")
