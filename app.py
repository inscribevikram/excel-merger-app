# app.py
import streamlit as st
import pandas as pd
import re
from io import BytesIO
from difflib import get_close_matches

st.set_page_config(page_title="Excel Master File Merger", layout="wide")
st.title("📊 Excel Master File Merger")
st.write("Upload multiple Excel files. The app maps similar headers, adds missing "
         "columns, combines them, removes duplicates, and validates data quality.")

uploaded_files = st.file_uploader(
    "Upload Excel files", type=["xlsx", "xls"], accept_multiple_files=True
)

similarity_threshold = st.slider(
    "Header matching sensitivity (higher = stricter match)", 0.5, 1.0, 0.8, 0.05
)

EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")
PHONE_REGEX = re.compile(r"^\+?[0-9\s\-()]{7,15}$")

def normalize(col):
    return str(col).strip().lower().replace("_", " ")

def map_headers(all_columns_list, threshold):
    master_headers = []
    mapping_per_file = []
    for cols in all_columns_list:
        file_mapping = {}
        for col in cols:
            norm_col = normalize(col)
            match = get_close_matches(
                norm_col, [normalize(m) for m in master_headers],
                n=1, cutoff=threshold
            )
            if match:
                idx = [normalize(m) for m in master_headers].index(match[0])
                file_mapping[col] = master_headers[idx]
            else:
                master_headers.append(col)
                file_mapping[col] = col
        mapping_per_file.append(file_mapping)
    return master_headers, mapping_per_file

def find_col(headers, keyword):
    matches = [h for h in headers if keyword in normalize(h)]
    return matches[0] if matches else None

if uploaded_files:
    dataframes, all_columns_list, file_names = [], [], []

    for f in uploaded_files:
        df = pd.read_excel(f)
        dataframes.append(df)
        all_columns_list.append(list(df.columns))
        file_names.append(f.name)

    master_headers, mapping_per_file = map_headers(all_columns_list, similarity_threshold)

    st.subheader("🔍 Header Mapping Preview")
    for name, mapping in zip(file_names, mapping_per_file):
        with st.expander(f"Mapping for: {name}"):
            st.json(mapping)

    aligned_dfs = []
    for df, mapping, name in zip(dataframes, mapping_per_file, file_names):
        renamed_df = df.rename(columns=mapping)
        renamed_df = renamed_df.reindex(columns=master_headers)
        renamed_df["__source_file"] = name
        aligned_dfs.append(renamed_df)

    master_df = pd.concat(aligned_dfs, ignore_index=True)

    st.subheader("✅ Combined Master File (Before Dedup)")
    st.dataframe(master_df, use_container_width=True)
    st.write(f"**Total rows:** {len(master_df)} | **Total columns:** {len(master_df.columns)}")

    st.subheader("🧹 Deduplication Settings")
    dedup_enabled = st.checkbox("Remove duplicate rows", value=True)
    dedup_df = master_df.copy()

    if dedup_enabled:
        default_email_col = find_col(master_headers, "email") or master_headers[0]
        dedup_column = st.selectbox(
            "Select column to check duplicates on (e.g. Email)",
            options=master_headers,
            index=master_headers.index(default_email_col)
        )
        keep_option = st.radio(
            "When duplicates are found, keep:",
            options=["First occurrence", "Last occurrence"], index=0, horizontal=True
        )
        keep_value = "first" if keep_option == "First occurrence" else "last"
        case_insensitive = st.checkbox("Ignore case & extra spaces (recommended for emails)", value=True)

        temp_key = dedup_df[dedup_column].astype(str).str.strip().str.lower() if case_insensitive else dedup_df[dedup_column]

        before_count = len(dedup_df)
        duplicate_mask = temp_key.duplicated(keep=False)
        duplicates_preview = dedup_df[duplicate_mask]

        st.write("**Duplicates found per source file:**")
        if duplicate_mask.sum() > 0:
            dup_summary = duplicates_preview.groupby("__source_file").size().reset_index(name="duplicate_rows")
            st.dataframe(dup_summary, use_container_width=True)
        else:
            st.write("No duplicates found.")

        dedup_df = dedup_df[~temp_key.duplicated(keep=keep_value)]
        after_count = len(dedup_df)
        removed_count = before_count - after_count
        st.write(f"**Total duplicates:** {duplicate_mask.sum()} rows | "
                 f"**Removed:** {removed_count} | **Remaining:** {after_count}")

        if duplicate_mask.sum() > 0:
            with st.expander("👀 Preview duplicate rows (before removal)"):
                st.dataframe(duplicates_preview, use_container_width=True)

    st.subheader("🛡️ Data Validation Checks")
    run_validation = st.checkbox("Run validation checks", value=True)

    if run_validation:
        email_col = find_col(master_headers, "email")
        phone_col = find_col(master_headers, "phone")

        required_cols = st.multiselect(
            "Select required columns (flag rows with blanks in these)",
            options=master_headers,
            default=[c for c in [email_col] if c]
        )

        issues = pd.DataFrame(index=dedup_df.index)
        issues["__source_file"] = dedup_df["__source_file"]

        if email_col:
            issues["invalid_email"] = ~dedup_df[email_col].astype(str).apply(
                lambda x: bool(EMAIL_REGEX.match(x.strip())) if x.strip().lower() != "nan" else False
            )
            issues["invalid_email"] = issues["invalid_email"] & dedup_df[email_col].notna()

        if phone_col:
            issues["invalid_phone"] = ~dedup_df[phone_col].astype(str).apply(
                lambda x: bool(PHONE_REGEX.match(x.strip())) if x.strip().lower() != "nan" else False
            )
            issues["invalid_phone"] = issues["invalid_phone"] & dedup_df[phone_col].notna()

        for col in required_cols:
            issues[f"missing_{col}"] = dedup_df[col].isna() | (dedup_df[col].astype(str).str.strip() == "")

        flag_cols = [c for c in issues.columns if c != "__source_file"]
        issues["has_issue"] = issues[flag_cols].any(axis=1) if flag_cols else False

        total_flagged = issues["has_issue"].sum()
        st.write(f"**Rows with validation issues:** {total_flagged} out of {len(dedup_df)}")

        if flag_cols:
            summary_rows = []
            for col in flag_cols:
                summary_rows.append({"Check": col, "Rows flagged": int(issues[col].sum())})
            st.dataframe(pd.DataFrame(summary_rows), use_container_width=True)

        if total_flagged > 0:
            with st.expander("👀 Preview rows with validation issues"):
                flagged_view = dedup_df[issues["has_issue"]].copy()
                for col in flag_cols:
                    flagged_view[col] = issues.loc[issues["has_issue"], col]
                st.dataframe(flagged_view, use_container_width=True)

        dedup_df["__validation_flag"] = issues["has_issue"].map({True: "ISSUE", False: "OK"})

    st.subheader("✅ Final Master File Preview")
    st.dataframe(dedup_df, use_container_width=True)
    st.write(f"**Final rows:** {len(dedup_df)} | **Final columns:** {len(dedup_df.columns)}")

    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        dedup_df.to_excel(writer, index=False, sheet_name="Master")
    output.seek(0)

    st.download_button(
        label="📥 Download Master Excel File (Validated & Deduplicated)",
        data=output,
        file_name="master_file_final.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
else:
    st.info("Please upload at least two Excel files to begin.")
