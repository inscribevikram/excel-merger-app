# app.py
import streamlit as st
import pandas as pd
from io import BytesIO
from difflib import get_close_matches

st.set_page_config(page_title="Excel Master File Merger", layout="wide")
st.title("📊 Smart Excel File Merger")

uploaded_files = st.file_uploader(
    "Upload Excel files", type=["xlsx", "xls"], accept_multiple_files=True
)

similarity_threshold = st.slider(
    "Header matching sensitivity", 0.5, 1.0, 0.7, 0.05
)

# Target keywords that indicate we found the right table
TARGET_KEYWORDS = [
    "organisation", "company", "account", "country", "segment", 
    "role", "title", "email", "linkedin", "decision maker", 
    "contact", "pain point", "signal", "tier"
]

def normalize(col):
    # Removes newlines, extra spaces, and common invisible characters
    return str(col).replace('\n', ' ').strip().lower().replace("_", " ")

def extract_clean_table(file):
    excel = pd.ExcelFile(file)
    best_df = None
    best_score = -1
    
    target_sheet_names = ["Priority Prospects", "Execution", "Sheet1"]
    sheets_to_check = []
    
    for s_name in excel.sheet_names:
        if any(target.lower() in s_name.lower() for target in target_sheet_names):
            sheets_to_check.insert(0, s_name)
        else:
            sheets_to_check.append(s_name)

    for sheet_name in sheets_to_check:
        df_raw = excel.parse(sheet_name, header=None, nrows=50)
        if df_raw.empty:
            continue
            
        for idx, row in df_raw.iterrows():
            row_str = " ".join([str(val).lower() for val in row.dropna() if isinstance(val, str)])
            score = sum(1 for kw in TARGET_KEYWORDS if kw in row_str)
            
            if score > best_score:
                best_score = score
                best_df = excel.parse(sheet_name, header=idx)
    
    if best_df is not None and best_score >= 3:
        best_df = best_df.dropna(axis=1, how='all')
        best_df = best_df.loc[:, ~best_df.columns.astype(str).str.contains('^Unnamed')]
        return best_df
    
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
            
            # --- HARDCODED SDR ALIASES ---
            if "decision maker" in norm_col or "contact" in norm_col or "name" in norm_col:
                if "Decision Maker" not in master_headers:
                    master_headers.append("Decision Maker")
                file_mapping[col] = "Decision Maker"
            elif "organisation" in norm_col or "company" in norm_col or "account" in norm_col:
                if "Organisation" not in master_headers:
                    master_headers.append("Organisation")
                file_mapping[col] = "Organisation"
            elif "role" in norm_col or "title" in norm_col:
                if "Role" not in master_headers:
                    master_headers.append("Role")
                file_mapping[col] = "Role"
            elif "linkedin" in norm_col:
                if "Linkedin" not in master_headers:
                    master_headers.append("Linkedin")
                file_mapping[col] = "Linkedin"
            elif "email" in norm_col:
                if "Email" not in master_headers:
                    master_headers.append("Email")
                file_mapping[col] = "Email"
            # Hardcode catch for "Tier" and "Priority Tier" (including those with \n)
            elif "tier" in norm_col:
                if "Tier" not in master_headers:
                    master_headers.append("Tier")
                file_mapping[col] = "Tier"
            elif match:
                idx = [normalize(m) for m in master_headers].index(match[0])
                file_mapping[col] = master_headers[idx]
            else:
                # Add the raw original header to the master list
                # But strip out ugly formatting like newline characters
                clean_header = str(col).replace('\n', ' ').strip()
                if clean_header not in master_headers:
                    master_headers.append(clean_header)
                file_mapping[col] = clean_header
                
        mapping_per_file.append(file_mapping)
        
    return master_headers, mapping_per_file

if uploaded_files:
    dataframes = []
    all_columns_list = []
    
    with st.spinner('Scanning files and extracting tables...'):
        for f in uploaded_files:
            df = extract_clean_table(f)
            df = df.dropna(how='all')
            dataframes.append(df)
            all_columns_list.append(list(df.columns))

    master_headers, mapping_per_file = map_headers(all_columns_list, similarity_threshold)

    aligned_dfs = []
    for df, mapping in zip(dataframes, mapping_per_file):
        renamed_df = df.rename(columns=mapping)
        renamed_df = renamed_df.loc[:, ~renamed_df.columns.duplicated()]
        renamed_df = renamed_df.reindex(columns=master_headers)
        aligned_dfs.append(renamed_df)

    master_df = pd.concat(aligned_dfs, ignore_index=True)
    
    # --- DEDUPLICATION LOGIC (Before sorting) ---
    st.subheader("🧹 Deduplication Settings")
    dedup_enabled = st.checkbox("Remove duplicate leads", value=True)
    
    if dedup_enabled:
        # Defaults to Organisation for deduping
        if "Organisation" in master_df.columns:
            dedup_col = "Organisation"
        else:
            dedup_col = master_headers[0]
            
        st.write(f"Removing duplicate leads based on **{dedup_col}**.")
        
        # Clean the key to ignore upper/lower case and spaces
        temp_key = master_df[dedup_col].astype(str).str.strip().str.lower()
        
        # Store count before drop
        before_count = len(master_df)
        master_df = master_df[~temp_key.duplicated(keep="first")]
        after_count = len(master_df)
        
        st.write(f"Removed **{before_count - after_count}** duplicates.")
    
    # --- REORDER COLUMNS TO MATCH YOUR PREFERRED LAYOUT ---
    priority_cols = ["Tier", "Organisation", "Country", "Segment", "Decision Maker", "Role", "Linkedin", "Email"]
    final_cols = []
    
    for p_col in priority_cols:
        for actual_col in master_df.columns:
            if normalize(p_col) == normalize(actual_col) and actual_col not in final_cols:
                final_cols.append(actual_col)
                
    for col in master_df.columns:
        if col not in final_cols:
            final_cols.append(col)
            
    master_df = master_df[final_cols]

    st.subheader("✅ Combined Master File")
    st.dataframe(master_df, use_container_width=True)

    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        master_df.to_excel(writer, index=False, sheet_name="Master")
    output.seek(0)

    st.download_button(
        label="📥 Download Smart Master File",
        data=output,
        file_name="smart_master_file_final.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
else:
    st.info("Please upload your execution files.")
