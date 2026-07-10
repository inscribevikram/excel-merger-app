# app.py
import streamlit as st
import pandas as pd
import re
from io import BytesIO
from difflib import get_close_matches

st.set_page_config(page_title="Excel Master File Merger", layout="wide")
st.title("📊 Smart Excel File Merger")
st.write("Upload your execution sheets. This app automatically scans all sheets, finds "
         "the actual data table (ignoring title/junk rows), maps the headers, and merges them.")

uploaded_files = st.file_uploader(
    "Upload Excel files", type=["xlsx", "xls"], accept_multiple_files=True
)

similarity_threshold = st.slider(
    "Header matching sensitivity (Lower = more aggressive matching)", 0.5, 1.0, 0.7, 0.05
)

# Standardize column strings for matching
def normalize(col):
    return str(col).strip().lower().replace("_", " ")

# Core logic: Find the best sheet and the starting row of the actual data
def extract_clean_table(file):
    excel = pd.ExcelFile(file)
    best_df = None
    best_score = -1
    
    # Keywords that usually indicate a "target" table in your SDR workflow
    target_keywords = ["organisation", "company", "country", "segment", "role", "email", "linkedin", "decision maker", "contact"]
    
    for sheet_name in excel.sheet_names:
        # Read the first 50 rows of the sheet with no header assumption
        df_raw = excel.parse(sheet_name, header=None, nrows=50)
        
        if df_raw.empty:
            continue
            
        # Scan each row to see if it looks like a header row
        for idx, row in df_raw.iterrows():
            row_str = " ".join([str(val).lower() for val in row.dropna() if isinstance(val, str)])
            score = sum(1 for kw in target_keywords if kw in row_str)
            
            if score > best_score:
                best_score = score
                # If we found a row with good headers, read the whole sheet starting from this row
                best_df = excel.parse(sheet_name, header=idx)
                
    if best_df is not None and best_score > 0:
        # Drop columns that are completely unnamed or empty
        best_df = best_df.dropna(axis=1, how='all')
        best_df = best_df.loc[:, ~best_df.columns.astype(str).str.contains('^Unnamed')]
        return best_df
    else:
        # Fallback if no obvious header row was found
        return pd.read_excel(file)

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
    dataframes = []
    all_columns_list = []
    file_names = []

    with st.spinner('Scanning files and extracting tables...'):
        for f in uploaded_files:
            df = extract_clean_table(f)
            # Drop empty rows that might have been picked up at the bottom
            df = df.dropna(how='all')
            dataframes.append(df)
            all_columns_list.append(list(df.columns))
            file_names.append(f.name)

    master_headers, mapping_per_file = map_headers(all_columns_list, similarity_threshold)

    st.subheader("🔍 Auto-Detected Header Mapping Preview")
    for name, mapping in zip(file_names, mapping_per_file):
        with st.expander(f"Mapping for: {name}"):
            st.json(mapping)

    aligned_dfs = []
    for df, mapping, name in zip(dataframes, mapping_per_file, file_names):
        renamed_df = df.rename(columns=mapping)
        renamed_df = renamed_df.loc[:, ~renamed_df.columns.duplicated()]
        renamed_df = renamed_df.reindex(columns=master_headers)
        renamed_df["__source_file"] = name
        aligned_dfs.append(renamed_df)

    master_df = pd.concat(aligned_dfs, ignore_index=True)

    st.subheader("✅ Combined Master File")
    st.dataframe(master_df, use_container_width=True)
    st.write(f"**Total rows:** {len(master_df)} | **Total columns:** {len(master_df.columns)}")

    # Deduplication
    st.subheader("🧹 Deduplication Settings")
    dedup_enabled = st.checkbox("Remove duplicate rows", value=True)
    dedup_df = master_df.copy()

    if dedup_enabled:
        # Tries to find email or linkedin as the default duplicate checker
        default_dedup_col = find_col(master_headers, "email") or find_col(master_headers, "linkedin") or master_headers[0]
        dedup_column = st.selectbox(
            "Select column to check duplicates on (e.g. Email or LinkedIn)",
            options=master_headers,
            index=master_headers.index(default_dedup_col)
        )
        keep_option = st.radio(
            "Keep:",
            options=["First occurrence", "Last occurrence"], index=0, horizontal=True
        )
        keep_value = "first" if keep_option == "First occurrence" else "last"
        
        # Deduplicate ignoring case
        temp_key = dedup_df[dedup_column].astype(str).str.strip().str.lower()
        dedup_df = dedup_df[~temp_key.duplicated(keep=keep_value)]
        st.write(f"Removed **{len(master_df) - len(dedup_df)}** duplicates.")

    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        dedup_df.to_excel(writer, index=False, sheet_name="Master")
    output.seek(0)

    st.download_button(
        label="📥 Download Smart Master File",
        data=output,
        file_name="smart_master_file.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
else:
    st.info("Please upload your execution files.")
