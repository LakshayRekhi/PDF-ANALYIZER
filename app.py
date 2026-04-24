import json
import os
import re
from typing import Dict, Optional, Tuple

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from dotenv import load_dotenv
from groq import Groq

from financial_ocr import FinancialPDFExtractor
from insights import generate_insight
from visualization import render_visualization


# --- 1. CONFIGURATION ---
load_dotenv()
st.set_page_config(page_title="PDF Financial Analyst", layout="wide", page_icon="📊")

CHART_MODEL = "qwen/qwen3-32b"
TEXT_MODEL = "llama-3.3-70b-versatile"
CHART_TEMPERATURE = 0.0
TEXT_TEMPERATURE = 0.2

api_key = os.getenv("GROQ_API_KEY")
if not api_key:
    st.error("🚨 Groq API Key is missing.")
    st.stop()

client = Groq(api_key=api_key)


CATEGORY_MAP = {
    "revenue": "Revenue",
    "income": "Revenue",
    "sales": "Revenue",
    "expense": "Expenses",
    "expenses": "Expenses",
    "expenditure": "Expenses",
    "cost": "Expenses",
    "asset": "Assets",
    "assets": "Assets",
    "liability": "Liabilities",
    "liabilities": "Liabilities",
    "equity": "Equity",
    "capital": "Equity",
    "net assets": "Equity",
}


def _norm_category(category: str = "", item: str = "") -> str:
    raw = str(category or "").strip().lower()
    for key, value in CATEGORY_MAP.items():
        if key in raw:
            return value

    item_l = str(item or "").strip().lower()
    for key, value in CATEGORY_MAP.items():
        if key in item_l:
            return value

    return ""


def _norm_year(year_value) -> str:
    y = str(year_value or "").strip()
    if y.lower() in {"none", "null", "nan", "unknown", "n/a", "na", "-", ""}:
        return "Unknown"
    if y.lower() == "current":
        return "Current"
    match = re.search(r"(19|20)\d{2}", y)
    return match.group(0) if match else "Unknown"


def parse_financial_json(json_data: Dict) -> pd.DataFrame:
    records = []

    def to_number(value) -> float:
        if isinstance(value, (int, float)):
            return float(value)
        s = str(value or "").strip()
        if s in {"", "-", "None", "null", "NaN"}:
            return 0.0
        is_neg = ("(" in s and ")" in s) or s.startswith("-")
        cleaned = re.sub(r"[^\d.]", "", s)
        if cleaned == "":
            return 0.0
        num = float(cleaned)
        return -abs(num) if is_neg else num

    def add_row(company: str, item: str, year, amount, category: str = ""):
        records.append(
            {
                "Company": str(company or "Unknown").strip(),
                "Item": str(item or "Unknown").strip().title(),
                "Year": _norm_year(year),
                "Amount": float(to_number(amount)),
                "Category": _norm_category(category, item),
            }
        )

    if isinstance(json_data, dict) and "financials" in json_data:
        for entry in json_data.get("financials", []):
            content = entry.get("content", {})
            metadata = content.get("metadata", {})
            company = metadata.get("company_name", "Unknown")
            for item in content.get("line_items", []):
                amount = item.get("normalized_value")
                if amount is None:
                    amount = item.get("raw_value", 0)
                add_row(
                    company=company,
                    item=item.get("item", "Unknown"),
                    year=item.get("year", "Unknown"),
                    amount=amount,
                    category=item.get("category", ""),
                )

    elif isinstance(json_data, list) and json_data and "content" in json_data[0]:
        for entry in json_data:
            content = entry.get("content", {})
            metadata = content.get("metadata", {})
            company = metadata.get("company_name", "Unknown")
            for item in content.get("line_items", []):
                amount = item.get("normalized_value")
                if amount is None:
                    amount = item.get("raw_value", 0)
                add_row(
                    company=company,
                    item=item.get("item", "Unknown"),
                    year=item.get("year", "Unknown"),
                    amount=amount,
                    category=item.get("category", ""),
                )

    elif isinstance(json_data, dict) and "pages" in json_data:
        fallback_company = (
            json_data.get("metadata", {})
            .get("financial_metadata", {})
            .get("company_name", "Unknown")
        )

        for page in json_data.get("pages", []):
            company = page.get("metadata", {}).get("company_name", fallback_company)
            extracted = page.get("financial_data", {}).get("extracted_data", {})

            def traverse(node, section: str = ""):
                for key, value in node.items():
                    if isinstance(value, dict):
                        if any(str(k).isdigit() or str(k).lower() == "current" for k in value.keys()):
                            cat = _norm_category(section, key)
                            for year_key, amount_val in value.items():
                                add_row(company, key, year_key, amount_val, cat)
                        else:
                            next_section = key if _norm_category(key) else section
                            traverse(value, next_section)

            traverse(extracted)

    df = pd.DataFrame(records)
    if df.empty:
        return df

    df["Year"] = df["Year"].apply(_norm_year)
    df["Item"] = df["Item"].astype(str).str.strip()
    df["Category"] = df.apply(
        lambda row: _norm_category(row.get("Category", ""), row.get("Item", "")),
        axis=1,
    )
    df["Amount"] = pd.to_numeric(df["Amount"], errors="coerce").fillna(0.0)
    df = df[df["Item"] != ""]

    df["_abs"] = df["Amount"].abs()
    df = (
        df.sort_values("_abs", ascending=False)
        .drop_duplicates(subset=["Company", "Item", "Year", "Category"])
        .drop(columns=["_abs"])
        .reset_index(drop=True)
    )
    return df


def _load_data_from_sidebar() -> Tuple[Optional[pd.DataFrame], Optional[Dict]]:
    with st.sidebar:
        st.header("Upload Data")
        source = st.radio("Source", ["PDF (auto-extract)", "JSON (pre-extracted)"], index=0)

        if source == "PDF (auto-extract)":
            uploaded_pdf = st.file_uploader("Upload PDF", type=["pdf"])
            if not uploaded_pdf:
                return None, None

            cache_key = f"pdf_{uploaded_pdf.name}_{uploaded_pdf.size}"
            if cache_key not in st.session_state:
                with st.spinner("Extracting financial data from PDF..."):
                    extractor = FinancialPDFExtractor()
                    raw_json = extractor.extract_from_bytes(
                        uploaded_pdf.read(),
                        filename=uploaded_pdf.name,
                    )
                st.session_state[f"raw_{cache_key}"] = raw_json
                st.session_state[cache_key] = parse_financial_json(raw_json)

            raw_json = st.session_state[f"raw_{cache_key}"]
            df = st.session_state[cache_key]

            st.download_button(
                "⬇️ Download extracted JSON",
                data=json.dumps(raw_json, indent=2),
                file_name=f"{uploaded_pdf.name.rsplit('.', 1)[0]}_extracted.json",
                mime="application/json",
            )
            return df, raw_json

        uploaded_json = st.file_uploader("Upload JSON", type=["json"])
        if not uploaded_json:
            return None, None

        raw_json = json.load(uploaded_json)
        return parse_financial_json(raw_json), raw_json


def main():
    st.title("🤖 PDF Financial Analyst")
    st.caption("Upload PDF or JSON, then use Visualization or Insights.")

    df, raw_json = _load_data_from_sidebar()
    if raw_json is None:
        st.info("👈 Upload a PDF or JSON file in the sidebar to get started.")
        return

    if df is None or df.empty:
        st.error("⚠️ Parsed data is empty. Check the file content or extraction output.")
        return

    mode = st.radio("Mode:", ["📊 Generate Charts", "💬 FAQ / Text Chat"], horizontal=True)
    st.divider()

    with st.expander(f"🔎 Verify Data ({len(df)} rows found)"):
        st.dataframe(df)

    if mode == "📊 Generate Charts":
        user_query = st.chat_input("Ex: Compare total revenue for ABC and XYZ in 2020")
    else:
        user_query = st.chat_input("Ex: What is the net income?")

    if not user_query:
        return

    with st.chat_message("user"):
        st.write(user_query)

    with st.chat_message("assistant"):
        if mode == "📊 Generate Charts":
            st.write("📊 Generating visualization...")

            result = render_visualization(
                df=df,
                user_query=user_query,
                client=client,
                model=CHART_MODEL,
                temperature=CHART_TEMPERATURE,
            )

            mode_used = result.get("mode")
            details = result.get("details")
            if mode_used == "llm-spec" and details:
                with st.expander("🔍 Parsed chart intent", expanded=False):
                    st.json(details)

            if result.get("error"):
                st.error(result["error"])
                return

            figure = result.get("figure")
            if isinstance(figure, go.Figure):
                st.plotly_chart(figure, use_container_width=True)
            elif figure is not None:
                st.pyplot(figure)
            else:
                st.warning("No chart was produced. Try a more specific request.")
        else:
            st.write("💬 Thinking...")
            answer = generate_insight(
                df=df,
                user_query=user_query,
                client=client,
                model=TEXT_MODEL,
                temperature=TEXT_TEMPERATURE,
            )
            st.write(answer)


if __name__ == "__main__":
    main()
