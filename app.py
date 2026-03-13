# import streamlit as st
# import pandas as pd
# import json
# import matplotlib.pyplot as plt
# import seaborn as sns
# from groq import Groq
# from dotenv import load_dotenv
# import os
# import re

# # --- 1. CONFIGURATION ---
# load_dotenv()
# st.set_page_config(page_title="PDF Financial Analyst", layout="wide", page_icon="📊")

# api_key = os.getenv("GROQ_API_KEY")
# if not api_key:
#     st.error("🚨 Groq API Key is missing.")
#     st.stop()

# client = Groq(api_key=api_key)

# # --- 2. UNIVERSAL DATA PARSING ---
# def parse_financial_json(json_data):
#     records = []
    
#     # CASE A: New Format (list with 'financials' key)
#     if 'financials' in json_data or (isinstance(json_data, list) and len(json_data) > 0 and 'content' in json_data[0]):
#         financials = json_data.get('financials', []) if isinstance(json_data, dict) else json_data
        
#         for entry in financials:
#             content = entry.get('content', {})
#             metadata = content.get('metadata', {})
#             company = metadata.get('company_name', 'Unknown')
            
#             for item in content.get('line_items', []):
#                 raw_item = item.get('item', 'Unknown')
#                 # Keep original item name for better matching
#                 norm_item = raw_item.strip()
#                 year_val = str(item.get('year', 'Unknown'))
                
#                 amount = item.get('normalized_value')
#                 if amount is None:
#                     try:
#                         raw_str = str(item.get('raw_value', '0'))
#                         clean_str = re.sub(r'[^\d.-]', '', raw_str)
#                         amount = float(clean_str)
#                     except:
#                         amount = 0.0

#                 records.append({
#                     "Company": company,
#                     "Item": norm_item,
#                     "Year": year_val,
#                     "Amount": float(amount)
#                 })

#     # CASE B: Old Format (Nested 'extracted_data')
#     elif 'pages' in json_data:
#         for page in json_data['pages']:
#             # Attempt to find company name
#             content_text = page.get('content', '')
#             company = "ABC Company" # Default
#             if "XYZ" in content_text or "XYZ" in page.get('metadata', {}).get('company_name', ''):
#                 company = "XYZ Organization"
            
#             extracted = page.get('financial_data', {}).get('extracted_data', {})
            
#             def traverse(current_node):
#                 for key, value in current_node.items():
#                     if isinstance(value, dict):
#                         # If keys are years (digits), we found data
#                         if any(k.isdigit() or k == 'current' for k in value.keys()):
#                             for year_key, amount_str in value.items():
#                                 year = "2020" if year_key == 'current' else year_key
#                                 norm_item = key.strip()
                                
#                                 try:
#                                     clean_str = re.sub(r'[^\d.-]', '', str(amount_str))
#                                     # Handle accounting negatives (100)
#                                     if "(" in str(amount_str): 
#                                         amt = -abs(float(clean_str))
#                                     else:
#                                         amt = float(clean_str)
#                                 except:
#                                     amt = 0.0
                                
#                                 records.append({
#                                     "Company": company,
#                                     "Item": norm_item,
#                                     "Year": year,
#                                     "Amount": amt
#                                 })
#                         else:
#                             traverse(value)
#             traverse(extracted)

#     return pd.DataFrame(records)

# # --- 3. EXTRACT CODE FROM LLM RESPONSE ---
# def extract_python_code(response_text):
#     """Extract only Python code from LLM response, removing explanations."""
#     # Method 1: Look for code between triple backticks
#     code_blocks = re.findall(r'```python\s*(.*?)```', response_text, re.DOTALL)
#     if code_blocks:
#         return code_blocks[0].strip()
    
#     # Method 2: Look for code without language specifier
#     code_blocks = re.findall(r'```\s*(.*?)```', response_text, re.DOTALL)
#     if code_blocks:
#         return code_blocks[0].strip()
    
#     # Method 3: If no code blocks, try to extract lines starting with common Python patterns
#     lines = response_text.split('\n')
#     code_lines = []
#     in_code = False
    
#     for line in lines:
#         # Start collecting when we see import, fig, ax, filtered, sns, plt
#         if any(line.strip().startswith(keyword) for keyword in ['import', 'fig', 'ax', 'filtered', 'sns', 'plt', 'for ', 'df']):
#             in_code = True
        
#         # Stop when we see explanation text
#         if in_code and line.strip() and not line.strip().startswith('#') and any(word in line.lower() for word in ['this code', 'the code', 'will create', 'function is']):
#             break
            
#         if in_code:
#             code_lines.append(line)
    
#     if code_lines:
#         return '\n'.join(code_lines).strip()
    
#     # Method 4: Return as-is if nothing found (will likely error)
#     return response_text.strip()

# # --- 4. CHART AGENT (IMPROVED WITH FUZZY MATCHING) ---
# def generate_chart_code(df, user_query):
#     companies = df['Company'].unique().tolist()
#     items = df['Item'].unique().tolist()
#     years = df['Year'].unique().tolist()
    
#     # Show user what's available
#     items_preview = items[:10] if len(items) > 10 else items
    
#     system_prompt = f"""You are a Python code generator. Output ONLY executable Python code with NO explanations.

# DATA CONTEXT:
# - DataFrame `df` exists with columns: ['Company', 'Item', 'Year', 'Amount']
# - Companies: {companies}
# - Available Items (sample): {items_preview}
# - Available Years: {years}

# CRITICAL RULES:
# 1. Use existing `df` variable - DO NOT create new data
# 2. Filter Year as STRING: df['Year'] == '2020'
# 3. **CASE-INSENSITIVE ITEM MATCHING**: Use df['Item'].str.contains('revenue', case=False) for partial matches
# 4. For TOTAL/SUMMARY items, look for uppercase keywords like "TOTAL", "NET", "GROSS"
# 5. Use sns.barplot() with hue='Company' for grouping
# 6. NO plt.show()
# 7. NO explanatory text - ONLY CODE
# 8. Add .fillna(0) after filtering to handle missing data
# 9. Use fig, ax = plt.subplots(figsize=(10, 6)) for better sizing

# USER REQUEST: {user_query}

# EXAMPLE OUTPUT FORMAT:
# # Case-insensitive filtering
# filtered_df = df[
#     (df['Company'].str.contains('ABC', case=False)) & 
#     (df['Item'].str.contains('TOTAL REVENUE', case=False)) & 
#     (df['Year'] == '2020')
# ]

# fig, ax = plt.subplots(figsize=(10, 6))
# sns.barplot(data=filtered_df, x='Year', y='Amount', hue='Company', ax=ax)
# for container in ax.containers:
#     ax.bar_label(container, fmt='$%.0f')
# ax.set_title('ABC Revenue 2020')
# ax.set_ylabel('Amount ($)')
# """
    
#     try:
#         response = client.chat.completions.create(
#             model="llama-3.3-70b-versatile",
#             messages=[
#                 {"role": "system", "content": system_prompt},
#                 {"role": "user", "content": f"Generate code for: {user_query}"}
#             ],
#             temperature=0
#         )
#         raw_response = response.choices[0].message.content.strip()
#         return extract_python_code(raw_response)
#     except Exception as e:
#         return f"raise ValueError('LLM Error: {e}')"

# # --- 5. TEXT AGENT ---
# def generate_text_answer(df, user_query):
#     data_context = df.to_csv(index=False)
#     system_prompt = f"Answer based strictly on:\n{data_context}\nUser Question: {user_query}"
    
#     try:
#         response = client.chat.completions.create(
#             model="llama-3.3-70b-versatile",
#             messages=[{"role": "system", "content": system_prompt}],
#             temperature=0.3
#         )
#         return response.choices[0].message.content
#     except Exception as e:
#         return f"Error: {e}"

# # --- 6. MAIN APP ---
# def main():
#     st.title("🤖 PDF Financial Analyst")
    
#     mode = st.radio("Mode:", ["📊 Generate Charts", "💬 FAQ / Text Chat"], horizontal=True)
#     st.divider()

#     with st.sidebar:
#         st.header("Upload Data")
#         uploaded_file = st.file_uploader("Upload JSON", type=["json"])
#         if uploaded_file:
#             raw_json = json.load(uploaded_file)
#         else:
#             raw_json = None

#     if raw_json:
#         # 1. Parse
#         df = parse_financial_json(raw_json)
        
#         if df.empty:
#             st.error("⚠️ Parsed data is empty. Check your JSON format.")
#         else:
#             # Show data summary
#             with st.expander(f"🔎 Verify Data ({len(df)} rows found)"):
#                 st.dataframe(df)
                
#                 # Show unique items for user reference
#                 st.subheader("Available Items in Dataset:")
#                 unique_items = df['Item'].unique()
#                 st.write(f"**{len(unique_items)} unique items found:**")
                
#                 # Group by company
#                 for company in df['Company'].unique():
#                     with st.expander(f"📊 {company}"):
#                         company_items = df[df['Company'] == company]['Item'].unique()
#                         st.write(", ".join(sorted(company_items)))

#             # 2. Input
#             if mode == "📊 Generate Charts":
#                 user_query = st.chat_input("Ex: 'Show ABC total revenue for 2020'")
#             else:
#                 user_query = st.chat_input("Ex: 'What is the net income?'")

#             if user_query:
#                 with st.chat_message("user"):
#                     st.write(user_query)

#                 with st.chat_message("assistant"):
#                     if mode == "📊 Generate Charts":
#                         st.write("📊 *Generating visualization...*")
#                         code = generate_chart_code(df, user_query)
                        
#                         # Show extracted code for debugging
#                         with st.expander("🔍 View Generated Code"):
#                             st.code(code, language='python')
                        
#                         try:
#                             exec(code, globals(), {"df": df})
                            
#                             fig = plt.gcf()
#                             if fig.get_axes():
#                                 st.pyplot(fig)
#                             else:
#                                 st.warning("⚠️ Empty Chart. The AI filters matched 0 rows.")
#                                 st.info("💡 Try searching with keywords from the 'Available Items' list above")
#                             plt.clf()
#                         except ValueError as ve:
#                             st.error(f"⚠️ {ve}")
#                         except Exception as e:
#                             st.error(f"❌ Execution Error: {e}")
#                             st.code(code, language='python')
#                     else:
#                         st.write("💬 *Thinking...*")
#                         answer = generate_text_answer(df, user_query)
#                         st.write(answer.replace("$", "\\$"))

# if __name__ == "__main__":
#     main()



# import streamlit as st
# import pandas as pd
# import json
# import matplotlib.pyplot as plt
# import seaborn as sns
# from dotenv import load_dotenv
# from groq import Groq
# import os
# import re
# from typing import Dict, Optional
# from pathlib import Path

# # ── Import OCR module ─────────────────────────────────────────────────────────
# from financial_ocr import FinancialPDFExtractor, ChartReadyNormalizer

# # ─────────────────────────────────────────────
# # 1. BOOTSTRAP
# # ─────────────────────────────────────────────
# load_dotenv()
# st.set_page_config(page_title="PDF Financial Analyst", layout="wide", page_icon="📊")

# api_key = os.getenv("GROQ_API_KEY")
# if not api_key:
#     st.error("🚨 GROQ_API_KEY is missing from your .env file.")
#     st.stop()

# client = Groq(api_key=api_key)
# normalizer = ChartReadyNormalizer()


# # ─────────────────────────────────────────────
# # 2. JSON  →  DATAFRAME
# # ─────────────────────────────────────────────
# def json_to_dataframe(json_data: Dict) -> pd.DataFrame:
#     records = []

#     # Format A: output from FinancialPDFExtractor
#     if "financials" in json_data:
#         for entry in json_data["financials"]:
#             content = entry.get("content", {})
#             meta = content.get("metadata", {})
#             company = meta.get("company_name", "Unknown")
#             for item in content.get("line_items", []):
#                 amount = item.get("normalized_value")
#                 if amount is None:
#                     amount = normalizer.to_numeric(item.get("raw_value", "0"))
#                 records.append({
#                     "Company": company,
#                     "Item": str(item.get("item", "Unknown")).strip(),
#                     "Year": str(item.get("year", "Unknown")),
#                     "Amount": float(amount),
#                     "Category": item.get("category", ""),
#                 })

#     # Format B: legacy nested format
#     elif "pages" in json_data:
#         for page in json_data["pages"]:
#             company = page.get("metadata", {}).get("company_name", "Unknown")

#             def traverse(node):
#                 for key, value in node.items():
#                     if isinstance(value, dict):
#                         if any(k.isdigit() or k == "current" for k in value.keys()):
#                             for year_key, raw_val in value.items():
#                                 year = "2020" if year_key == "current" else year_key
#                                 records.append({
#                                     "Company": company,
#                                     "Item": str(key).strip(),
#                                     "Year": year,
#                                     "Amount": normalizer.to_numeric(raw_val),
#                                     "Category": "",
#                                 })
#                         else:
#                             traverse(value)

#             traverse(page.get("financial_data", {}).get("extracted_data", {}))

#     return pd.DataFrame(records)


# # ─────────────────────────────────────────────
# # 3. CHART AGENT
# # ─────────────────────────────────────────────
# def _extract_code(text: str) -> str:
#     for pattern in [r"```python\s*(.*?)```", r"```\s*(.*?)```"]:
#         blocks = re.findall(pattern, text, re.DOTALL)
#         if blocks:
#             return blocks[0].strip()
#     return text.strip()


# def generate_chart_code(df: pd.DataFrame, user_query: str) -> str:
#     companies = df["Company"].unique().tolist()
#     items_sample = df["Item"].unique().tolist()[:15]
#     years = sorted(df["Year"].unique().tolist())
#     categories = df["Category"].unique().tolist() if "Category" in df.columns else []

#     system_prompt = f"""You are a Python code generator for financial charts. Output ONLY executable Python code — no explanations, no markdown.

# DATA CONTEXT:
# - DataFrame `df` with columns: Company, Item, Year, Amount, Category
# - Companies: {companies}
# - Sample Items: {items_sample}
# - Years: {years}
# - Categories: {categories}

# STRICT RULES:
# 1. Use existing `df` — never create new data.
# 2. Filter Year as STRING: df['Year'] == '2020'
# 3. Use case-insensitive partial matching: df['Item'].str.contains('revenue', case=False, na=False)
# 4. Use fig, ax = plt.subplots(figsize=(10, 6))
# 5. Use sns.barplot() with hue='Company' when comparing companies.
# 6. Add value labels: for c in ax.containers: ax.bar_label(c, fmt='%.0f', padding=3)
# 7. Set ax.set_ylabel('Amount') and a descriptive ax.set_title(...)
# 8. NO plt.show() — the caller renders the figure.
# 9. Add .copy() after filtering to avoid SettingWithCopyWarning.
# 10. If filtered data is empty, raise ValueError('No data matched the filters.')

# USER REQUEST: {user_query}
# """
#     try:
#         resp = client.chat.completions.create(
#             model="llama-3.3-70b-versatile",
#             messages=[
#                 {"role": "system", "content": system_prompt},
#                 {"role": "user", "content": user_query},
#             ],
#             temperature=0,
#         )
#         return _extract_code(resp.choices[0].message.content)
#     except Exception as exc:
#         return f"raise ValueError('LLM error: {exc}')"


# # ─────────────────────────────────────────────
# # 4. TEXT / FAQ AGENT
# # ─────────────────────────────────────────────
# def generate_text_answer(df: pd.DataFrame, user_query: str) -> str:
#     summary = df.groupby(["Company", "Item", "Year"])["Amount"].sum().reset_index()
#     context_csv = summary.to_csv(index=False)

#     system_prompt = (
#         "You are a financial analyst. Answer the user's question strictly based on the data below.\n\n"
#         f"DATA (CSV):\n{context_csv}\n\n"
#         "Be concise. Use bullet points where helpful. Do not make up numbers."
#     )
#     try:
#         resp = client.chat.completions.create(
#             model="llama-3.3-70b-versatile",
#             messages=[
#                 {"role": "system", "content": system_prompt},
#                 {"role": "user", "content": user_query},
#             ],
#             temperature=0.2,
#         )
#         return resp.choices[0].message.content
#     except Exception as exc:
#         return f"Error: {exc}"


# # ─────────────────────────────────────────────
# # 5. STREAMLIT UI
# # ─────────────────────────────────────────────
# def sidebar_uploader() -> Optional[pd.DataFrame]:
#     with st.sidebar:
#         st.header("📂 Upload Financial Data")
#         source = st.radio("Source type", ["PDF (auto-extract)", "JSON (pre-extracted)"], index=0)

#         if source == "PDF (auto-extract)":
#             uploaded = st.file_uploader("Upload a financial PDF", type=["pdf"])
#             if uploaded:
#                 cache_key = f"df_{uploaded.name}_{uploaded.size}"
#                 if cache_key not in st.session_state:
#                     progress_bar = st.progress(0, text="Starting extraction…")

#                     def on_progress(current, total, message):
#                         progress_bar.progress(current / total, text=message)

#                     extractor = FinancialPDFExtractor()
#                     raw_json = extractor.extract_from_bytes(
#                         uploaded.read(), filename=uploaded.name, progress_callback=on_progress
#                     )
#                     progress_bar.empty()
#                     st.session_state[cache_key] = raw_json

#                     st.sidebar.download_button(
#                         "⬇️ Download extracted JSON",
#                         data=json.dumps(raw_json, indent=2),
#                         file_name=f"{Path(uploaded.name).stem}_extracted.json",
#                         mime="application/json",
#                     )

#                 return json_to_dataframe(st.session_state[cache_key])

#         else:
#             uploaded = st.file_uploader("Upload extracted JSON", type=["json"])
#             if uploaded:
#                 return json_to_dataframe(json.load(uploaded))

#     return None


# def show_data_explorer(df: pd.DataFrame):
#     with st.expander(f"🔎 Data Explorer — {len(df):,} rows", expanded=False):
#         col1, col2, col3 = st.columns(3)
#         col1.metric("Companies", df["Company"].nunique())
#         col2.metric("Line Items", df["Item"].nunique())
#         col3.metric("Years", df["Year"].nunique())

#         st.dataframe(df, use_container_width=True)

#         st.subheader("Available Items by Company")
#         for company in df["Company"].unique():
#             items = sorted(df[df["Company"] == company]["Item"].unique())
#             with st.expander(f"📊 {company} ({len(items)} items)"):
#                 st.write(", ".join(items))


# def chart_tab(df: pd.DataFrame):
#     st.subheader("📊 Chart Generator")
#     st.caption("Describe what you want to visualise — the AI will write and run the chart code.")

#     user_query = st.chat_input("e.g. 'Compare total revenue across all companies for 2022'", key="chart_input")
#     if not user_query:
#         return

#     with st.chat_message("user"):
#         st.write(user_query)

#     with st.chat_message("assistant"):
#         with st.spinner("Generating chart…"):
#             code = generate_chart_code(df, user_query)

#         with st.expander("🔍 Generated code"):
#             st.code(code, language="python")

#         try:
#             exec(code, {**globals(), "sns": sns, "plt": plt, "pd": pd}, {"df": df})  # noqa: S102
#             fig = plt.gcf()
#             if fig.get_axes():
#                 st.pyplot(fig)
#             else:
#                 st.warning("⚠️ Chart is empty — the filters matched 0 rows. Try different keywords.")
#             plt.clf()
#         except ValueError as ve:
#             st.warning(f"⚠️ {ve}")
#         except Exception as exc:
#             st.error(f"❌ Execution error: {exc}")
#             st.code(code, language="python")


# def faq_tab(df: pd.DataFrame):
#     st.subheader("💬 Financial Q&A")
#     st.caption("Ask any question about the financial data.")

#     user_query = st.chat_input("e.g. 'What is the net income trend for ABC Corp?'", key="faq_input")
#     if not user_query:
#         return

#     with st.chat_message("user"):
#         st.write(user_query)

#     with st.chat_message("assistant"):
#         with st.spinner("Analysing…"):
#             answer = generate_text_answer(df, user_query)
#         st.markdown(answer)


# def main():
#     st.title("🤖 PDF Financial Analyst")
#     st.caption("Upload a PDF or JSON → explore the data → generate charts or ask questions.")

#     df = sidebar_uploader()

#     if df is None:
#         st.info("👈 Upload a PDF or JSON file in the sidebar to get started.")
#         return

#     if df.empty:
#         st.error("⚠️ No financial data could be parsed. Check that the PDF contains financial statements.")
#         return

#     show_data_explorer(df)
#     st.divider()

#     tab_chart, tab_faq = st.tabs(["📊 Generate Charts", "💬 Q&A / FAQ"])
#     with tab_chart:
#         chart_tab(df)
#     with tab_faq:
#         faq_tab(df)


# if __name__ == "__main__":
#     main()



import streamlit as st
import pandas as pd
import json
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from dotenv import load_dotenv
from groq import Groq
import os
import re
from typing import Dict, Optional
from pathlib import Path

# ── Import OCR module ─────────────────────────────────────────────────────────
from financial_ocr import FinancialPDFExtractor, ChartReadyNormalizer

# ─────────────────────────────────────────────
# 1. BOOTSTRAP
# ─────────────────────────────────────────────
load_dotenv()
st.set_page_config(page_title="Financial Analyst", layout="wide", page_icon="📊")

# ── Minimal custom CSS ────────────────────────
st.markdown("""
<style>
    [data-testid="stMetricValue"] { font-size: 2rem; font-weight: 700; }
    [data-testid="stMetricLabel"] { font-size: 0.8rem; color: #888; text-transform: uppercase; letter-spacing: .05em; }
    .block-container { padding-top: 1.5rem; }
    .stTabs [data-baseweb="tab"] { font-size: 0.95rem; font-weight: 600; }
    div[data-testid="stExpander"] summary { font-weight: 600; }
</style>
""", unsafe_allow_html=True)

api_key = os.getenv("GROQ_API_KEY")
if not api_key:
    st.error("🚨 GROQ_API_KEY is missing from your .env file.")
    st.stop()

client = Groq(api_key=api_key)
normalizer = ChartReadyNormalizer()

# ── Plotly theme ──────────────────────────────
PLOTLY_TEMPLATE = "plotly_white"
COLOR_SEQ = px.colors.qualitative.Bold


# ─────────────────────────────────────────────
# 2. HELPERS
# ─────────────────────────────────────────────
def fmt_amount(value: float) -> str:
    """Format large numbers: 1_200_000 → $1.2M"""
    abs_val = abs(value)
    if abs_val >= 1_000_000:
        return f"${value / 1_000_000:.1f}M"
    if abs_val >= 1_000:
        return f"${value / 1_000:.1f}K"
    return f"${value:,.0f}"


def deduplicate_df(df: pd.DataFrame) -> pd.DataFrame:
    """
    Same Company+Item+Year can appear on multiple pages only when it's a
    genuine repeat (e.g. a summary page re-listing the same figure).
    Deduplicate ONLY within the same Company+Item+Year+Category group,
    keeping the first occurrence so we don't lose cross-company same-named items.
    """
    if df.empty:
        return df
    df = df.copy()
    df["_abs"] = df["Amount"].abs()
    df = (
        df.sort_values("_abs", ascending=False)
          .drop_duplicates(subset=["Company", "Item", "Year", "Category"])
          .drop(columns="_abs")
          .reset_index(drop=True)
    )
    return df


# ─────────────────────────────────────────────
# 3. JSON → DATAFRAME
# ─────────────────────────────────────────────
def json_to_dataframe(json_data: Dict) -> pd.DataFrame:
    records = []

    if "financials" in json_data:
        for entry in json_data["financials"]:
            content = entry.get("content", {})
            meta = content.get("metadata", {})
            company = meta.get("company_name", "Unknown")
            for item in content.get("line_items", []):
                amount = item.get("normalized_value")
                if amount is None:
                    amount = normalizer.to_numeric(item.get("raw_value", "0"))
                records.append({
                    "Company": company,
                    "Item": str(item.get("item", "Unknown")).strip(),
                    "Year": str(item.get("year", "Unknown")),
                    "Amount": float(amount),
                    "Category": item.get("category", ""),
                })

    elif "pages" in json_data:
        for page in json_data["pages"]:
            company = page.get("metadata", {}).get("company_name", "Unknown")

            def traverse(node):
                for key, value in node.items():
                    if isinstance(value, dict):
                        if any(k.isdigit() or k == "current" for k in value.keys()):
                            for year_key, raw_val in value.items():
                                year = "2020" if year_key == "current" else year_key
                                records.append({
                                    "Company": company,
                                    "Item": str(key).strip(),
                                    "Year": year,
                                    "Amount": normalizer.to_numeric(raw_val),
                                    "Category": "",
                                })
                        else:
                            traverse(value)

            traverse(page.get("financial_data", {}).get("extracted_data", {}))

    df = pd.DataFrame(records)
    return deduplicate_df(df)


# ─────────────────────────────────────────────
# 4. AUTO OVERVIEW CHARTS (shown on load)
# ─────────────────────────────────────────────
def _top_items_bar(df: pd.DataFrame) -> go.Figure:
    """Horizontal bar: top 12 line items by absolute amount (latest year)."""
    latest_year = sorted(df["Year"].unique())[-1]
    sub = df[df["Year"] == latest_year].copy()
    sub = sub.groupby("Item", as_index=False)["Amount"].sum()
    sub["abs"] = sub["Amount"].abs()
    sub = sub.nlargest(12, "abs").sort_values("Amount")
    sub["label"] = sub["Amount"].apply(fmt_amount)
    sub["color"] = sub["Amount"].apply(lambda x: "#ef4444" if x < 0 else "#3b82f6")

    fig = go.Figure(go.Bar(
        x=sub["Amount"],
        y=sub["Item"],
        orientation="h",
        text=sub["label"],
        textposition="inside",   # inside = never clipped by margin
        textfont=dict(color="white", size=11),
        marker_color=sub["color"],
        hovertemplate="%{y}<br>%{text}<extra></extra>",
    ))

    # Pad x-axis so bars don't touch the edges
    max_abs = sub["abs"].max() if not sub.empty else 1
    fig.update_layout(
        title=f"Top Line Items — {latest_year}",
        template=PLOTLY_TEMPLATE,
        height=max(380, 32 * len(sub) + 80),   # dynamic height
        xaxis=dict(
            title="Amount",
            tickformat="$,.0f",
            range=[-max_abs * 1.05, max_abs * 1.25],  # room for positive labels
        ),
        yaxis_title="",
        margin=dict(l=20, r=20, t=50, b=40),
        showlegend=False,
    )
    return fig


def _category_donut(df: pd.DataFrame) -> Optional[go.Figure]:
    """Donut: category composition (latest year, positive amounts, no TOTAL rows)."""
    if "Category" not in df.columns or df["Category"].str.strip().eq("").all():
        return None
    latest_year = sorted(df["Year"].unique())[-1]

    # Exclude TOTAL/SUBTOTAL rows and zero-amount rows to avoid double-counting
    sub = df[
        (df["Year"] == latest_year) &
        (df["Amount"] > 0) &
        (df["Category"].str.strip() != "") &
        (~df["Item"].str.contains(r"^TOTAL|^Total|subtotal", case=False, na=False, regex=True))
    ].copy()

    if sub.empty:
        return None

    grp = sub.groupby("Category", as_index=False)["Amount"].sum()
    # Drop categories that are trivially small (< 0.5% of total) — noise
    total = grp["Amount"].sum()
    grp = grp[grp["Amount"] / total >= 0.005]

    if grp.empty or len(grp) < 2:
        return None

    fig = go.Figure(go.Pie(
        labels=grp["Category"],
        values=grp["Amount"],
        hole=0.55,
        textinfo="label+percent",
        textposition="inside",
        marker_colors=COLOR_SEQ,
        hovertemplate="%{label}<br>%{customdata}<br>%{percent}<extra></extra>",
        customdata=[fmt_amount(v) for v in grp["Amount"]],
    ))
    fig.update_layout(
        title=f"Category Breakdown — {latest_year}",
        template=PLOTLY_TEMPLATE,
        height=400,
        margin=dict(l=10, r=10, t=50, b=20),
        showlegend=True,
        legend=dict(orientation="v", x=1.02, y=0.5),
    )
    return fig


def _trend_lines(df: pd.DataFrame) -> Optional[go.Figure]:
    """Line chart: top-5 non-total items across all years, sorted chronologically."""
    years = sorted(df["Year"].unique())   # chronological sort
    if len(years) < 2:
        return None

    # Exclude TOTAL/SUBTOTAL rows — use detail lines only
    detail = df[~df["Item"].str.contains(r"^TOTAL|^Total|subtotal", case=False, na=False, regex=True)]

    top_items = (
        detail.groupby("Item")["Amount"]
              .apply(lambda x: x.abs().sum())
              .nlargest(5).index.tolist()
    )
    sub = detail[detail["Item"].isin(top_items)].copy()
    # Ensure year order is chronological on x-axis
    sub["Year"] = pd.Categorical(sub["Year"], categories=years, ordered=True)
    sub = sub.sort_values("Year")

    fig = px.line(
        sub, x="Year", y="Amount", color="Item",
        markers=True,
        color_discrete_sequence=COLOR_SEQ,
        template=PLOTLY_TEMPLATE,
        title="Trend — Top 5 Line Items",
        labels={"Amount": "Amount ($)", "Year": "Year"},
    )
    fig.update_traces(line_width=2.5, marker_size=8)
    fig.update_layout(
        height=400,
        legend_title="",
        margin=dict(l=10, r=10, t=50, b=40),
    )
    fig.update_yaxes(tickformat="$,.0f")
    return fig


def show_overview(df: pd.DataFrame):
    """Auto-generated overview shown immediately after PDF loads."""
    st.subheader("📈 Overview")

    latest_year = sorted(df["Year"].unique())[-1]
    year_df = df[df["Year"] == latest_year]

    # KPI: use Category-aware logic where available, fall back to sign-based
    has_categories = "Category" in df.columns and not df["Category"].str.strip().eq("").all()

    if has_categories:
        rev_cats = ["Revenue", "Income"]
        exp_cats = ["Expenses", "Expense", "Expenditure"]
        total_revenue = year_df[year_df["Category"].isin(rev_cats)]["Amount"].sum()
        total_expenses = year_df[year_df["Category"].isin(exp_cats)]["Amount"].sum()
    else:
        total_revenue = year_df[year_df["Amount"] > 0]["Amount"].sum()
        total_expenses = year_df[year_df["Amount"] < 0]["Amount"].sum()

    net = total_revenue - abs(total_expenses)
    n_items = df["Item"].nunique()
    n_years = df["Year"].nunique()

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Total Revenue / Income", fmt_amount(total_revenue))
    k2.metric(
        "Total Expenses / Outflows",
        fmt_amount(abs(total_expenses)),
        delta=fmt_amount(-abs(total_expenses)) if total_expenses != 0 else None,
        delta_color="inverse",
    )
    k3.metric("Net Position", fmt_amount(net), delta_color="normal")
    k4.metric(f"Line Items · {n_years} year(s)", str(n_items))

    st.divider()

    # ── Charts row 1 ─────────────────────────────
    col_a, col_b = st.columns([3, 2])
    with col_a:
        st.plotly_chart(_top_items_bar(df), use_container_width=True)
    with col_b:
        donut = _category_donut(df)
        if donut:
            st.plotly_chart(donut, use_container_width=True)
        else:
            st.info("No category data available for donut chart.")

    # ── Charts row 2 (trend, only if multi-year) ─
    trend = _trend_lines(df)
    if trend:
        st.plotly_chart(trend, use_container_width=True)


# ─────────────────────────────────────────────
# 5. CHART AGENT  (Plotly-first, smart type)
# ─────────────────────────────────────────────
def _extract_code(text: str) -> str:
    for pattern in [r"```python\s*(.*?)```", r"```\s*(.*?)```"]:
        blocks = re.findall(pattern, text, re.DOTALL)
        if blocks:
            return blocks[0].strip()
    return text.strip()


def generate_chart_code(df: pd.DataFrame, user_query: str) -> str:
    all_items = df["Item"].unique().tolist()
    companies = df["Company"].unique().tolist()
    years = sorted(df["Year"].unique().tolist())
    categories = [c for c in df["Category"].unique().tolist() if c]

    detail_items = [i for i in all_items if not re.match(r"^TOTAL|^Total|subtotal", i, re.I)]
    total_items  = [i for i in all_items if re.match(r"^TOTAL|^Total|subtotal", i, re.I)]

    sample_rows = (
        df.groupby(["Company", "Item", "Year", "Category"])["Amount"]
          .sum().reset_index()
          .head(40)
          .to_string(index=False)
    )

    system_prompt = f"""You are a Python + Plotly financial chart code generator.
Output ONLY raw executable Python code — zero explanations, zero markdown, zero comments outside code.

════════════════════════════════════════
DATAFRAME  `df`  — already loaded, do NOT recreate it
════════════════════════════════════════
Columns  : Company (str), Item (str), Year (str), Amount (float), Category (str)
Companies: {companies}
Years    : {years}   ← ALL ARE STRINGS — NEVER use integer year
Categories: {categories}
Detail Items (prefer these for breakdowns): {detail_items}
Total/Summary Items (use for high-level comparisons only): {total_items}

SAMPLE ROWS (use these exact spellings when filtering):
{sample_rows}

════════════════════════════════════════
FILTERING  RULES  — read carefully
════════════════════════════════════════
1. Year MUST be a string:  df['Year'] == '2020'   NOT df['Year'] == 2020
2. Company: exact df['Company'] == 'ABC Company' OR partial str.contains
3. Item: always use str.contains, case=False, na=False
4. Chain all filters with & wrapped in ():
   filtered = df[(df['Company'] == 'X') & (df['Year'] == '2020') & (df['Item'].str.contains('revenue', case=False, na=False))].copy()
5. After filtering: if filtered.empty: raise ValueError('No data matched.')
6. NEVER aggregate all rows into one bar. ALWAYS set x='Item' or color='Item'/'Category' to show a breakdown.

════════════════════════════════════════
CHART TYPE SELECTION
════════════════════════════════════════
- Item breakdown for one year → px.bar, orientation='h', x='Amount', y='Item', sorted by Amount
- Trend across years → px.line, x='Year', y='Amount', color='Item', markers=True
- Category composition → go.Pie hole=0.5, exclude TOTAL rows
- Revenue vs Expenses → px.bar barmode='group', color='Category' or color='Item'
- Waterfall → go.Waterfall

════════════════════════════════════════
REQUIRED OUTPUT RULES
════════════════════════════════════════
- Final figure must be assigned to variable `fig`
- template="plotly_white" on every chart
- fig.update_yaxes(tickformat="$,.0f") for bar/line
- fig.update_layout(height=480, margin=dict(l=10, r=80, t=50, b=40), title='...')
- DO NOT call fig.show()
- DO NOT import — px, go, pd, fmt_amount already available

USER REQUEST: {user_query}
"""
    try:
        resp = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_query},
            ],
            temperature=0,
        )
        return _extract_code(resp.choices[0].message.content)
    except Exception as exc:
        return f"raise ValueError('LLM error: {exc}')"


# ─────────────────────────────────────────────
# 6. FAQ AGENT
# ─────────────────────────────────────────────
def generate_text_answer(df: pd.DataFrame, user_query: str) -> str:
    summary = df.groupby(["Item", "Year"])["Amount"].sum().reset_index()
    summary["Amount_fmt"] = summary["Amount"].apply(fmt_amount)
    context_csv = summary.to_csv(index=False)

    system_prompt = (
        "You are a financial analyst. Answer strictly from the data below.\n\n"
        f"DATA:\n{context_csv}\n\n"
        "Rules: be concise, use bullet points, quote exact formatted figures, never invent numbers."
    )
    try:
        resp = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_query},
            ],
            temperature=0.1,
        )
        return resp.choices[0].message.content
    except Exception as exc:
        return f"Error: {exc}"


# ─────────────────────────────────────────────
# 7. SIDEBAR — PDF only
# ─────────────────────────────────────────────
def sidebar_uploader() -> Optional[pd.DataFrame]:
    with st.sidebar:
        st.markdown("## 📂 Upload PDF")
        uploaded = st.file_uploader("Financial statement PDF", type=["pdf"], label_visibility="collapsed")

        if uploaded:
            cache_key = f"df_{uploaded.name}_{uploaded.size}"
            if cache_key not in st.session_state:
                progress_bar = st.progress(0, text="Starting extraction…")

                def on_progress(current, total, message):
                    progress_bar.progress(current / total, text=message)

                with st.spinner("Extracting financial data…"):
                    extractor = FinancialPDFExtractor()
                    raw_json = extractor.extract_from_bytes(
                        uploaded.read(), filename=uploaded.name, progress_callback=on_progress
                    )
                progress_bar.empty()
                st.session_state[cache_key] = raw_json
                st.success("✅ Extraction complete")

            raw_json = st.session_state[cache_key]

            # Download extracted JSON
            st.download_button(
                "⬇️ Download JSON",
                data=json.dumps(raw_json, indent=2),
                file_name=f"{Path(uploaded.name).stem}_extracted.json",
                mime="application/json",
            )

            df = json_to_dataframe(raw_json)

            # Sidebar mini-stats
            if not df.empty:
                st.divider()
                st.caption(f"**{df['Item'].nunique()}** line items · **{df['Year'].nunique()}** year(s)")
                st.caption(f"Years: {', '.join(sorted(df['Year'].unique()))}")

                # Searchable item list
                with st.expander("🔍 Browse line items"):
                    search = st.text_input("Search items", placeholder="e.g. revenue", label_visibility="collapsed")
                    items = sorted(df["Item"].unique())
                    if search:
                        items = [i for i in items if search.lower() in i.lower()]
                    st.write("\n".join(f"- {i}" for i in items[:50]))
                    if len(items) > 50:
                        st.caption(f"…and {len(items) - 50} more")

            return df

    return None


# ─────────────────────────────────────────────
# 8. CHART TAB
# ─────────────────────────────────────────────
def chart_tab(df: pd.DataFrame):
    st.subheader("📊 Custom Chart")
    st.caption("Ask for any chart — the AI picks the right chart type and renders it interactively.")

    if "chart_history" not in st.session_state:
        st.session_state.chart_history = []

    user_query = st.chat_input("e.g. 'Show revenue trend over all years as a line chart'", key="chart_input")

    # Replay history
    for msg in st.session_state.chart_history:
        with st.chat_message(msg["role"]):
            if msg["role"] == "user":
                st.write(msg["content"])
            else:
                if msg.get("fig"):
                    st.plotly_chart(msg["fig"], use_container_width=True)
                if msg.get("warning"):
                    st.warning(msg["warning"])
                if msg.get("error"):
                    st.error(msg["error"])

    if not user_query:
        return

    st.session_state.chart_history.append({"role": "user", "content": user_query})
    with st.chat_message("user"):
        st.write(user_query)

    with st.chat_message("assistant"):
        with st.spinner("Generating chart…"):
            code = generate_chart_code(df, user_query)

        with st.expander("🔍 Generated code", expanded=False):
            st.code(code, language="python")

        exec_globals = {
            "df": df, "px": px, "go": go,
            "pd": pd, "fmt_amount": fmt_amount,
            "make_subplots": make_subplots,
        }
        exec_locals: Dict = {}

        try:
            exec(code, exec_globals, exec_locals)  # noqa: S102
            fig = exec_locals.get("fig")

            if fig is None:
                warning_msg = "⚠️ No figure produced. Try rephrasing your request."
                st.warning(warning_msg)
                st.session_state.chart_history.append({"role": "assistant", "warning": warning_msg})
            else:
                # Apply consistent styling
                fig.update_layout(template=PLOTLY_TEMPLATE, height=480)
                st.plotly_chart(fig, use_container_width=True)
                st.session_state.chart_history.append({"role": "assistant", "fig": fig})

        except ValueError as ve:
            warning_msg = f"⚠️ {ve}"
            st.warning(warning_msg)
            # Show what IS available for the keywords used
            keywords = [w for w in re.sub(r"[^\w\s]", "", user_query).lower().split() if len(w) > 2]
            item_matches = [i for i in df["Item"].unique() if any(k in i.lower() for k in keywords)]
            year_matches = [y for y in df["Year"].unique() if any(k in y for k in keywords)]
            company_matches = [c for c in df["Company"].unique() if any(k in c.lower() for k in keywords)]
            hints = []
            if item_matches:
                hints.append(f"**Items found:** {', '.join(item_matches[:8])}")
            if year_matches:
                hints.append(f"**Years found:** {', '.join(year_matches)}")
            if company_matches:
                hints.append(f"**Companies found:** {', '.join(company_matches)}")
            if hints:
                st.info("💡 Try using these exact names:\n\n" + "\n\n".join(hints))
            st.session_state.chart_history.append({"role": "assistant", "warning": warning_msg})

        except Exception as exc:
            error_msg = f"❌ Execution error: {exc}"
            st.error(error_msg)
            st.code(code, language="python")
            st.session_state.chart_history.append({"role": "assistant", "error": error_msg})


# ─────────────────────────────────────────────
# 9. FAQ TAB
# ─────────────────────────────────────────────
def faq_tab(df: pd.DataFrame):
    st.subheader("💬 Financial Q&A")
    st.caption("Ask any question about the numbers — get a concise analyst-style answer.")

    if "faq_history" not in st.session_state:
        st.session_state.faq_history = []

    user_query = st.chat_input("e.g. 'What are the top 3 expense items in 2022?'", key="faq_input")

    for msg in st.session_state.faq_history:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    if not user_query:
        return

    st.session_state.faq_history.append({"role": "user", "content": user_query})
    with st.chat_message("user"):
        st.markdown(user_query)

    with st.chat_message("assistant"):
        with st.spinner("Analysing…"):
            answer = generate_text_answer(df, user_query)
        st.markdown(answer)
        st.session_state.faq_history.append({"role": "assistant", "content": answer})


# ─────────────────────────────────────────────
# 10. MAIN
# ─────────────────────────────────────────────
def main():
    st.title("📊 Financial Analyst")

    df = sidebar_uploader()

    if df is None:
        st.info("👈 Upload a financial statement PDF in the sidebar to get started.")
        return

    if df.empty:
        st.error("⚠️ No financial data could be extracted. Ensure the PDF contains financial statements.")
        return

    show_overview(df)
    st.divider()

    tab_chart, tab_faq, tab_data = st.tabs(["📊 Custom Charts", "💬 Q&A", "🗂 Raw Data"])

    with tab_chart:
        chart_tab(df)

    with tab_faq:
        faq_tab(df)

    with tab_data:
        st.dataframe(
            df.style.format({"Amount": lambda x: fmt_amount(x)}),
            use_container_width=True,
            height=500,
        )


if __name__ == "__main__":
    main()