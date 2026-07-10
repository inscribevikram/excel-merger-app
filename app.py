import streamlit as st
import pandas as pd
import re
from io import BytesIO
from pathlib import Path

st.set_page_config(page_title="Company & Lead Cleaner", layout="wide")

# -----------------------------
# Constants
# -----------------------------
BASE_COLUMNS = [
    "Decision Maker",
    "Job Title",
    "Organisation",
    "Country",
    "Segment",
    "Email",
    "Website",
    "Location",
    "LinkedIn URL",
    "Source File"
]

FREE_EMAIL_DOMAINS = {
    "gmail.com", "yahoo.com", "hotmail.com", "outlook.com", "aol.com",
    "icloud.com", "live.com", "msn.com", "me.com", "protonmail.com"
}

EUROPEAN_COUNTRIES = {
    "uk", "united kingdom", "great britain", "britain", "england", "scotland", "wales", "northern ireland", "gb",
    "ireland", "republic of ireland",
    "austria", "belgium", "bulgaria", "croatia", "cyprus", "czech republic", "czechia", "denmark",
    "estonia", "finland", "france", "germany", "greece", "hungary", "iceland", "italy", "latvia",
    "liechtenstein", "lithuania", "luxembourg", "malta", "netherlands", "norway", "poland", "portugal",
    "romania", "slovakia", "slovenia", "spain", "sweden", "switzerland", "europe", "eu"
}

TLD_TO_COUNTRY = {
    ".co.uk": "united kingdom",
    ".org.uk": "united kingdom",
    ".gov.uk": "united kingdom",
    ".ac.uk": "united kingdom",
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
    ".gr": "greece",
    ".eu": "eu"
}

# -----------------------------
# Utility helpers
# -----------------------------
def clean_text(x):
    if pd.isna(x):
        return ""
    return str(x).replace("\n", " ").replace("\r", " ").strip()

def clean_col_name(col):
    col = clean_text(col).lower()
    col = re.sub(r"[^a-z0-9]+", " ", col).strip()
    return col

def is_blank(x):
    return clean_text(x).lower() in {"", "nan", "none", "null"}

def looks_like_email(x):
    s = clean_text(x).lower()
    return bool(re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", s))

def looks_like_linkedin(x):
    s = clean_text(x).lower()
    return "linkedin.com/" in s

def looks_like_url(x):
    s = clean_text(x).lower()
    if not s:
        return False
    return (
        s.startswith("http://")
        or s.startswith("https://")
        or s.startswith("www.")
        or bool(re.search(r"\b[a-z0-9.-]+\.[a-z]{2,}\b", s))
    )

def normalize_website(x):
    s = clean_text(x).lower()
    s = s.replace("http://", "").replace("https://", "").strip("/")
    return s

def infer_website_from_email(email):
    email = clean_text(email).lower()
    if "@" not in email:
        return ""
    domain = email.split("@")[-1].strip()
    if domain in FREE_EMAIL_DOMAINS or "." not in domain:
        return ""
    return f"www.{domain}"

def looks_like_address(x):
    s = clean_text(x)
    low = s.lower()

    if not s:
        return False

    comma_count = s.count(",")
    digit_count = sum(ch.isdigit() for ch in s)

    address_words = [
        "street", "road", "avenue", "lane", "park", "square", "building",
        "floor", "suite", "postcode", "zip", "campus", "house"
    ]

    if comma_count >= 3 and digit_count >= 1:
        return True

    if any(word in low for word in address_words) and digit_count >= 1:
        return True

    return False

def normalize_country(country):
    s = clean_text(country).lower()
    s = re.sub(r"[^\w\s/,&-]", "", s)
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

def country_is_uk_or_europe(country, website=""):
    c = normalize_country(country)

    if not c:
        inferred = infer_country_from_website(website)
        return inferred in EUROPEAN_COUNTRIES

    parts = re.split(r"[/,;&|]+", c)
    parts = [p.strip() for p in parts if p.strip()]

    for p in parts:
        if p in EUROPEAN_COUNTRIES:
            return True
        if "united kingdom" in p or p == "uk" or p == "gb":
            return True
        if "europe" in p or p == "eu":
            return True

    inferred = infer_country_from_website(website)
    return inferred in EUROPEAN_COUNTRIES

def valid_company_name(x):
    s = clean_text(x)
    low = s.lower()

    if not s:
        return False
    if low in {"organisation", "organization", "company name", "name", "unknown", "nan", "none", "null"}:
        return False
    if looks_like_linkedin(s):
        return False
    if low.startswith(("http://", "https://", "www.")):
        return False
    if looks_like_email(s):
        return False
    if looks_like_address(s):
        return False

    junk_patterns = [
        r"^site:linkedin",
        r"^sitelinkedin",
        r"\bnot job\b",
        r"\bjobs\b",
        r"\bhiring\b",
        r"\brecruiter\b",
        r"\bcareers\b",
        r"\bcareer\b",
        r"\bopen for internship\b",
    ]
    for pat in junk_patterns:
        if re.search(pat, low):
            return False

    return True

def valid_person_name(x):
    s = clean_text(x)
    low = s.lower()

    if not s:
        return False
    if looks_like_linkedin(s) or looks_like_email(s) or looks_like_address(s):
        return False
    if low in {"name", "contact", "decision maker", "unknown"}:
        return False

    return True

def extract_linkedin_from_row(row):
    for val in row:
        text = clean_text(val)
        if "linkedin.com/" in text.lower():
            return text
    return ""

# -----------------------------
# File loading
# -----------------------------
def read_uploaded_file(uploaded_file):
    ext = Path(uploaded_file.name).suffix.lower()

    if ext == ".csv":
        for enc in ["utf-8-sig", "utf-8", "latin-1", "cp1252"]:
            try:
                uploaded_file.seek(0)
                return pd.read_csv(uploaded_file, dtype=str, encoding=enc)
            except Exception:
                pass
        uploaded_file.seek(0)
        return pd.read_csv(uploaded_file, dtype=str, encoding_errors="ignore")

    if ext in [".xlsx", ".xls"]:
        uploaded_file.seek(0)
        return pd.read_excel(uploaded_file, dtype=str)

    raise ValueError(f"Unsupported file format: {ext}")

# -----------------------------
# Mapping logic
# -----------------------------
def map_columns(df):
    mapping = {}

    for col in df.columns:
        n = clean_col_name(col)

        if any(k in n for k in ["decision maker", "contact person", "contact name", "full name"]):
            mapping[col] = "Decision Maker"
        elif any(k in n for k in ["job title", "designation", "role", "position"]):
            mapping[col] = "Job Title"
        elif any(k in n for k in ["organisation", "organization", "company name", "company", "account", "institution", "employer"]):
            mapping[col] = "Organisation"
        elif "country" in n:
            mapping[col] = "Country"
        elif any(k in n for k in ["segment", "industry", "vertical", "category", "type"]):
            mapping[col] = "Segment"
        elif "email" in n:
            mapping[col] = "Email"
        elif any(k in n for k in ["website", "domain", "company url", "organisation url", "organization url"]):
            mapping[col] = "Website"
        elif any(k in n for k in ["location", "city", "address", "hq", "head office", "office"]):
            mapping[col] = "Location"
        elif "linkedin" in n:
            mapping[col] = "LinkedIn URL"
        else:
            mapping[col] = col

    return mapping

def standardize_df(df, source_name):
    df = df.copy()
    df.columns = [clean_text(c) for c in df.columns]
    mapping = map_columns(df)

    out = pd.DataFrame()

    for old_col, new_col in mapping.items():
        out[new_col] = df[old_col].astype(str)

    for col in BASE_COLUMNS:
        if col not in out.columns:
            out[col] = ""

    out["Source File"] = source_name

    if "LinkedIn URL" not in out.columns:
        out["LinkedIn URL"] = ""

    derived_li = df.astype(str).apply(lambda row: extract_linkedin_from_row(row.values), axis=1)
    out["LinkedIn URL"] = out["LinkedIn URL"].replace("nan", "").fillna("")
    out["LinkedIn URL"] = out["LinkedIn URL"].mask(out["LinkedIn URL"].astype(str).str.strip() == "", derived_li)

    out["Website"] = out["Website"].replace("nan", "").fillna("")
    out["Email"] = out["Email"].replace("nan", "").fillna("")
    out["Website"] = out.apply(
        lambda r: infer_website_from_email(r["Email"]) if is_blank(r["Website"]) else r["Website"],
        axis=1
    )

    for col in out.columns:
        out[col] = out[col].astype(str).apply(clean_text)

    return out

def build_master(uploaded_files):
    frames = []
    errors = []

    for f in uploaded_files:
        try:
            raw = read_uploaded_file(f)
            raw = raw.fillna("")
            std = standardize_df(raw, f.name)
            frames.append(std)
        except Exception as e:
            errors.append(f"{f.name}: {str(e)}")

    if frames:
        master = pd.concat(frames, ignore_index=True)
    else:
        master = pd.DataFrame(columns=BASE_COLUMNS)

    for col in BASE_COLUMNS:
        if col not in master.columns:
            master[col] = ""

    return master, errors

# -----------------------------
# Derived outputs
# -----------------------------
def build_contact_master(master_df):
    df = master_df.copy()

    if "Decision Maker" in df.columns:
        df = df[df["Decision Maker"].apply(lambda x: is_blank(x) or valid_person_name(x))].copy()

    df["Website"] = df["Website"].apply(normalize_website)
    return df.reset_index(drop=True)

def build_company_master(master_df):
    df = master_df.copy()

    for col in ["Organisation", "Country", "Segment", "Website", "Location"]:
        if col not in df.columns:
            df[col] = ""

    df["Company Name"] = df["Organisation"].apply(clean_text)
    df["Website"] = df["Website"].apply(normalize_website)

    df = df[df["Company Name"].apply(valid_company_name)].copy()
    df = df[df.apply(lambda r: country_is_uk_or_europe(r.get("Country", ""), r.get("Website", "")), axis=1)].copy()

    df["Country"] = df.apply(
        lambda r: infer_country_from_website(r["Website"]).title() if is_blank(r["Country"]) else r["Country"],
        axis=1
    )

    company_df = df[["Company Name", "Country", "Segment", "Website", "Location"]].copy()

    company_df["dedupe_key"] = (
        company_df["Company Name"].str.lower().str.strip() + "||" +
        company_df["Website"].fillna("").str.lower().str.strip()
    )
    company_df = company_df.drop_duplicates(subset=["dedupe_key"], keep="first").drop(columns=["dedupe_key"])

    company_df = company_df.sort_values(by=["Country", "Company Name"], na_position="last").reset_index(drop=True)
    return company_df

def quality_checks(master_df):
    qc_linkedin = master_df[master_df["Organisation"].apply(looks_like_linkedin)][["Organisation", "Country", "Website", "Source File"]].copy()
    qc_address = master_df[master_df["Organisation"].apply(looks_like_address)][["Organisation", "Country", "Website", "Source File"]].copy()
    qc_non_europe = master_df[
        ~master_df.apply(lambda r: country_is_uk_or_europe(r.get("Country", ""), r.get("Website", "")), axis=1)
    ][["Organisation", "Country", "Website", "Source File"]].copy()

    return qc_linkedin, qc_address, qc_non_europe

def to_excel(sheets_dict):
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        for name, df in sheets_dict.items():
            df.to_excel(writer, sheet_name=name[:31], index=False)
    output.seek(0)
    return output.getvalue()

# -----------------------------
# App UI
# -----------------------------
st.title("Lead & Company Cleaner")
st.write("Upload CSV/XLSX files to consolidate contacts and extract a clean UK + Europe company master.")

uploaded_files = st.file_uploader(
    "Upload files",
    type=["csv", "xlsx", "xls"],
    accept_multiple_files=True
)

if uploaded_files:
    try:
        master_df, errors = build_master(uploaded_files)
        contact_df = build_contact_master(master_df)
        company_df = build_company_master(master_df)
        qc_linkedin, qc_address, qc_non_europe = quality_checks(master_df)

        if errors:
            st.warning("Some files could not be processed:")
            for err in errors:
                st.write(f"- {err}")

        col1, col2, col3 = st.columns(3)
        col1.metric("Raw consolidated rows", len(master_df))
        col2.metric("Clean contact rows", len(contact_df))
        col3.metric("UK + Europe companies", len(company_df))

        tab1, tab2, tab3, tab4 = st.tabs([
            "Master Data",
            "Company Master",
            "Quality Checks",
            "Download"
        ])

        with tab1:
            st.subheader("Standardized Master Data")
            st.dataframe(contact_df, use_container_width=True, height=550)

        with tab2:
            st.subheader("Company Master - UK & Europe only")
            st.write("This excludes LinkedIn URLs, addresses, websites in the company name field, and non-UK/Europe rows.")
            st.dataframe(company_df, use_container_width=True, height=550)

        with tab3:
            st.subheader("Rows flagged for review")

            st.markdown("**Organisation values that look like LinkedIn URLs**")
            st.dataframe(qc_linkedin, use_container_width=True, height=180)

            st.markdown("**Organisation values that look like addresses**")
            st.dataframe(qc_address, use_container_width=True, height=180)

            st.markdown("**Rows excluded from company master because they are outside UK/Europe**")
            st.dataframe(qc_non_europe, use_container_width=True, height=180)

        with tab4:
            excel_data = to_excel({
                "Master Contact Data": contact_df,
                "Company Master UK Europe": company_df,
                "LinkedIn-like Organisation": qc_linkedin,
                "Address-like Organisation": qc_address,
                "Non Europe Excluded": qc_non_europe
            })

            st.download_button(
                "Download Excel workbook",
                data=excel_data,
                file_name="cleaned_company_lead_output.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

            st.download_button(
                "Download Company Master CSV",
                data=company_df.to_csv(index=False).encode("utf-8-sig"),
                file_name="company_master_uk_europe.csv",
                mime="text/csv"
            )

            st.download_button(
                "Download Master Contact CSV",
                data=contact_df.to_csv(index=False).encode("utf-8-sig"),
                file_name="master_contact_data.csv",
                mime="text/csv"
            )

    except Exception as e:
        st.error(f"App failed while processing the files: {e}")
        st.stop()
else:
    st.info("Upload one or more CSV or Excel files to begin.")
