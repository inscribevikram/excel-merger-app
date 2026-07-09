# 📊 Excel Master File Merger & Validator

A simple, browser-based Python application built with Streamlit designed specifically for Sales Operations and Lead Generation workflows. It allows you to upload multiple Excel exports (e.g., from Apollo, LinkedIn Sales Navigator, or manual research), map differing column headers, and combine them into a single master file.

## 🚀 Live App
[Click here to use the live application](https://your-app-name.streamlit.app) *(Replace this link with your actual Streamlit Cloud URL)*

## ⚙️ Key Features
- **Fuzzy Header Mapping:** Automatically aligns slightly different column names (e.g., "Email" vs "Email Address") using adjustable sensitivity.
- **Missing Data Handling:** If a new file has columns the others don't, they are automatically added to the master file.
- **Smart Deduplication:** Identifies and removes duplicate leads based on any column (defaults to Email) with options for case-insensitivity. Tracks duplicate count per source file.
- **Data Validation:** Flags rows with malformed emails, invalid phone number formats, or missing required fields.
- **Source Tracking:** Automatically adds a `__source_file` column to track exactly which export each lead came from.

## 🛠️ Built With
- **Python**
- **Streamlit** (Web UI)
- **Pandas** (Data Manipulation)
- **Openpyxl** (Excel Read/Write)

## 💻 Local Setup (Optional)
If you want to run this application locally instead of using the cloud version:
1. Clone the repository.
2. Install the required dependencies: `pip install -r requirements.txt`
3. Run the application: `streamlit run app.py`
