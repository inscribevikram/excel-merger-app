# app.py
import streamlit as st
import pandas as pd
from io import BytesIO
import zipfile
from difflib import get_close_matches

st.set_page_config(page_title="Excel Master File Merger", layout="wide")
st.title("📊 Smart Excel File Merger")

# Added "zip" to accepted file types
uploaded_files = st.file_uploader(
    "Upload Excel files or a ZIP folder", type=["xlsx", "xls", "zip"], accept_multiple_files=True
)

similarity_threshold = st.slider(
    "Header matching sensitivity", 0.5, 1.0, 0.7, 0.05
)

TARGET_KEYWORDS = [
    "organisation", "company", "account", "country", "segment", 
    "role", "title", "email", "linkedin", "decision maker", 
    "contact", "pain point", "signal", "tier", "website", "domain", "location", "address"
]

def normalize(col):
    return str(col).replace('\n', ' ').strip().lower().replace("_", " ")

# Updated to read bytes directly (needed for zip extraction)
def extract_clean_table(file_bytes):
    excel = pd.ExcelFile(file_bytes)
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
    
    return pd.read_excel(file_bytes)

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
            elif "tier" in norm_col:
                if "Tier" not in master_headers:
                    master_headers.append("Tier")
                file_mapping[col] = "Tier"
            elif "website" in norm_col or "domain" in norm_col:
                if "Website" not in master_headers:
                    master_headers.append("Website")
                file_mapping[col] = "Website"
            elif "location" in norm_col or "address" in norm_col:
                if "Location" not in master_headers:
                    master_headers.append("Location")
                file_mapping[col] = "Location"
            elif match:
                idx = [normalize(m) for m in master_headers].index(match[0])
                file_mapping[col] = master_headers[idx]
            else:
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
            # --- ZIP FILE HANDLING LOGIC ---
            if f.name.endswith('.zip'):
                with zipfile.ZipFile(f, 'r') as z:
                    for file_info in z.infolist():
                        # Only process excel files, ignore mac __MACOSX system files
                        if (file_info.filename.endswith('.xlsx') or file_info.filename.endswith('.xls')) and not file_info.filename.startswith('__MACOSX/'):
                            with z.open(file_info) as excel_file:
                                file_bytes = BytesIO(excel_file.read())
                                df = extract_clean_table(file_bytes)
                                df = df.dropna(how='all')
                                dataframes.append(df)
                                all_columns_list.append(list(df.columns))
            # --- NORMAL EXCEL HANDLING LOGIC ---
            else:
                df = extract_clean_table(f)
                df = df.dropna(how='all')
                dataframes.append(df)
                all_columns_list.append(list(df.columns))

    # If no valid data was found (e.g., zip was empty or had no excel files)
    if not dataframes:
        st.error("No valid Excel data found in the uploaded files/zip.")
    else:
        master_headers, mapping_per_file = map_headers(all_columns_list, similarity_threshold)

        aligned_dfs = []
        for df, mapping in zip(dataframes, mapping_per_file):
            renamed_df = df.rename(columns=mapping)
            renamed_df = renamed_df.loc[:, ~renamed_df.columns.duplicated()]
            renamed_df = renamed_df.reindex(columns=master_headers)
            aligned_dfs.append(renamed_df)

        master_df = pd.concat(aligned_dfs, ignore_index=True)
        
        tab1, tab2 = st.tabs(["📊 Full Execution Merge", "🏢 Company Master List"])

        with tab1:
            st.subheader("🧹 Deduplication Settings (Execution Sheet)")
            dedup_enabled = st.checkbox("Remove duplicate leads", value=True, key="dedup_full")
            
            tab1_df = master_df.copy()
            
            if dedup_enabled:
                if "Organisation" in tab1_df.columns:
                    dedup_col = "Organisation"
                else:
                    dedup_col = master_headers[0]
                    
                st.write(f"Removing duplicate leads based on **{dedup_col}**.")
                temp_key = tab1_df[dedup_col].astype(str).str.strip().str.lower()
                
                before_count = len(tab1_df)
                tab1_df = tab1_df[~temp_key.duplicated(keep="first")]
                after_count = len(tab1_df)
                st.write(f"Removed **{before_count - after_count}** duplicates.")
            
            priority_cols = ["Tier", "Organisation", "Country", "Segment", "Decision Maker", "Role", "Linkedin", "Email"]
            final_cols = []
            
            for p_col in priority_cols:
                for actual_col in tab1_df.columns:
                    if normalize(p_col) == normalize(actual_col) and actual_col not in final_cols:
                        final_cols.append(actual_col)
                        
            for col in tab1_df.columns:
                if col not in final_cols:
                    final_cols.append(col)
                    
            tab1_df = tab1_df[final_cols]

            st.dataframe(tab1_df, use_container_width=True)

            output_tab1 = BytesIO()
            with pd.ExcelWriter(output_tab1, engine="openpyxl") as writer:
                tab1_df.to_excel(writer, index=False, sheet_name="Master Execution")
            output_tab1.seek(0)

            st.download_button(
                label="📥 Download Full Execution Master",
                data=output_tab1,
                file_name="execution_master_file.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

        with tab2:
            st.subheader("🏢 Extracted Company List")
            st.write("This view extracts core company details, derives missing websites from email addresses, drops blank companies, and removes duplicates.")
            
            tab2_df = master_df.copy()
            
            if "Email" not in tab2_df.columns:
                tab2_df["Email"] = ""
                
            required_company_cols = ["Organisation", "Country", "Segment", "Website", "Location"]
            for c in required_company_cols:
                if c not in tab2_df.columns:
                    tab2_df[c] = ""
                    
            free_emails = ["gmail.com", "yahoo.com", "hotmail.com", "outlook.com", "aol.com", "icloud.com", "live.com"]
            
            def derive_website(row):
                website = str(row.get("Website", "")).strip()
                if website and website.lower() != "nan":
                    return website
                
                email = str(row.get("Email", "")).strip()
                if "@" in email:
                    domain = email.split("@")[-1].lower()
                    if domain not in free_emails:
                        return "www." + domain
                return ""
                
            tab2_df["Website"] = tab2_df.apply(derive_website, axis=1)
            
            company_df = tab2_df[required_company_cols].copy()
            company_df.rename(columns={"Organisation": "Company Name"}, inplace=True)
            
            company_df["temp_key"] = company_df["Company Name"].astype(str).str.strip().str.lower()
            company_df = company_df[~company_df["temp_key"].isin(["nan", ""])]
            
            before_company_count = len(company_df)
            company_df = company_df.drop_duplicates(subset=["temp_key"], keep="first")
            after_company_count = len(company_df)
            
            company_df.drop(columns=["temp_key"], inplace=True)
            
            st.write(f"Found **{after_company_count}** unique companies.")
            
            st.dataframe(company_df, use_container_width=True)
            
            output_tab2 = BytesIO()
            with pd.ExcelWriter(output_tab2, engine="openpyxl") as writer:
                company_df.to_excel(writer, index=False, sheet_name="Company Master")
            output_tab2.seek(0)

            st.download_button(
                label="📥 Download Clean Company Master",
                data=output_tab2,
                file_name="company_master_list.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

else:
    st.info("Please upload your execution files.")
