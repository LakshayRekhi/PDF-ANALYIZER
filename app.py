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

from financial_ocr import FinancialPDFExtractor, ChartReadyNormalizer

# ─────────────────────────────────────────────
# BOOTSTRAP
# ─────────────────────────────────────────────
GROQ_API_KEY="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"
load_dotenv()
st.set_page_config(page_title="Financial Analyst", layout="wide", page_icon="📊")

st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Syne:wght@400;600;700;800&family=DM+Mono:wght@400;500&display=swap');

    html, body, [class*="css"] {
        font-family: 'Syne', sans-serif;
    }
    code, pre, .stCode {
        font-family: 'DM Mono', monospace !important;
    }

    /* Page background */
    .stApp {
        background: #0d0f14;
        color: #e8e8e8;
    }

    /* Sidebar */
    [data-testid="stSidebar"] {
        background: #13161e !important;
        border-right: 1px solid #1f2430;
    }

    /* Main container */
    .block-container {
        padding: 2rem 2.5rem 3rem;
        max-width: 1200px;
    }

    /* Title */
    h1 {
        font-size: 2.2rem;
        font-weight: 800;
        letter-spacing: -0.03em;
        color: #f5f5f5;
        margin-bottom: 0.2rem;
    }

    h2, h3 {
        font-weight: 700;
        color: #e0e0e0;
        letter-spacing: -0.02em;
    }

    /* Mode selector buttons */
    .stRadio > label {
        color: #888 !important;
        font-size: 0.75rem;
        letter-spacing: 0.1em;
        text-transform: uppercase;
    }
    .stRadio [data-testid="stMarkdownContainer"] p {
        font-size: 0.95rem;
        font-weight: 600;
        color: #e0e0e0;
    }
    div[role="radiogroup"] label {
        padding: 0.6rem 1.2rem;
        border: 1px solid #2a2e3d;
        border-radius: 8px;
        margin-right: 0.5rem;
        cursor: pointer;
        transition: all 0.2s;
        background: #1a1d27;
        color: #aaa;
    }
    div[role="radiogroup"] label:has(input:checked) {
        border-color: #6366f1;
        background: #1e1f35;
        color: #a5b4fc;
    }

    /* Chat input */
    .stChatInput textarea {
        background: #1a1d27 !important;
        border: 1px solid #2a2e3d !important;
        border-radius: 10px !important;
        color: #e8e8e8 !important;
        font-family: 'Syne', sans-serif !important;
        font-size: 0.95rem !important;
    }
    .stChatInput textarea:focus {
        border-color: #6366f1 !important;
        box-shadow: 0 0 0 2px rgba(99,102,241,0.15) !important;
    }

    /* Chat messages */
    [data-testid="stChatMessage"] {
        background: #13161e !important;
        border: 1px solid #1f2430;
        border-radius: 12px;
        padding: 1rem;
        margin-bottom: 0.75rem;
    }

    /* Metric cards */
    [data-testid="metric-container"] {
        background: #13161e;
        border: 1px solid #1f2430;
        border-radius: 12px;
        padding: 1.2rem 1.5rem;
    }
    [data-testid="stMetricValue"] {
        font-size: 1.8rem !important;
        font-weight: 800 !important;
        color: #a5b4fc !important;
    }
    [data-testid="stMetricLabel"] {
        font-size: 0.75rem !important;
        color: #666 !important;
        text-transform: uppercase;
        letter-spacing: 0.08em;
    }

    /* Expander */
    details {
        background: #13161e;
        border: 1px solid #1f2430 !important;
        border-radius: 10px;
    }
    summary {
        font-weight: 600;
        color: #bbb;
        font-size: 0.88rem;
        letter-spacing: 0.03em;
    }

    /* Info / success banners */
    .stInfo, .stSuccess {
        background: #1a1d27;
        border-radius: 10px;
    }

    /* Divider */
    hr {
        border-color: #1f2430 !important;
    }

    /* Dataframe */
    .stDataFrame {
        border: 1px solid #1f2430;
        border-radius: 10px;
        overflow: hidden;
    }
</style>
""", unsafe_allow_html=True)

api_key = GROQ_API_KEY
if not api_key:
    st.error("🚨 GROQ_API_KEY is missing from your .env file.")
    st.stop()

client = Groq(api_key=api_key)
normalizer = ChartReadyNormalizer()

PLOTLY_TEMPLATE = "plotly_dark"
COLOR_SEQ = ["#6366f1", "#22d3ee", "#f59e0b", "#10b981", "#f43f5e", "#a78bfa", "#34d399"]


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────
def fmt_amount(value: float) -> str:
    abs_val = abs(value)
    sign = "-" if value < 0 else ""
    if abs_val >= 1_000_000:
        return f"{sign}${abs_val / 1_000_000:.2f}M"
    if abs_val >= 1_000:
        return f"{sign}${abs_val / 1_000:.1f}K"
    return f"{sign}${abs_val:,.0f}"


CATEGORY_MAP = {
    "revenue": "Revenue", "income": "Revenue", "sales": "Revenue",
    "expense": "Expenses", "expenses": "Expenses", "expenditure": "Expenses", "cost": "Expenses",
    "asset": "Assets", "assets": "Assets",
    "liability": "Liabilities", "liabilities": "Liabilities",
    "equity": "Equity", "capital": "Equity", "net assets": "Equity",
}


def _norm_category(cat: str, item: str = "") -> str:
    raw = str(cat or "").strip().lower()
    for k, v in CATEGORY_MAP.items():
        if k in raw:
            return v
    item_l = item.lower()
    for k, v in CATEGORY_MAP.items():
        if k in item_l:
            return v
    return ""


def _norm_year(y) -> str:
    y = str(y or "").strip()
    if y.lower() in {"none", "null", "nan", "unknown", "n/a", "na", "-", ""}:
        return "Unknown"
    if y.lower() == "current":
        return "Current"
    m = re.search(r"(19|20)\d{2}", y)
    return m.group(0) if m else y


def _year_key(y):
    y = str(y)
    if re.fullmatch(r"(19|20)\d{2}", y):
        return (0, int(y))
    return (1, y)


def _latest_year(df: pd.DataFrame) -> str:
    ys = sorted(df["Year"].unique(), key=_year_key)
    for y in reversed(ys):
        if y.lower() != "unknown":
            return y
    return ys[-1] if ys else "Unknown"


# ─────────────────────────────────────────────
# JSON → DATAFRAME
# ─────────────────────────────────────────────
def json_to_dataframe(json_data: Dict) -> pd.DataFrame:
    records = []

    # Format A: {"financials": [...]}
    if "financials" in json_data:
        for entry in json_data["financials"]:
            content = entry.get("content", {})
            meta = content.get("metadata", {})
            company = meta.get("company_name", "Unknown")
            for item in content.get("line_items", []):
                amount = item.get("normalized_value")
                if amount is None:
                    amount = normalizer.to_numeric(item.get("raw_value", "0"))
                item_name = str(item.get("item", "Unknown")).strip()
                records.append({
                    "Company": company,
                    "Item": item_name,
                    "Year": _norm_year(item.get("year")),
                    "Amount": float(amount),
                    "Category": _norm_category(item.get("category", ""), item_name),
                })

    # Format B: {"pages": [...]}
    elif "pages" in json_data:
        for page in json_data["pages"]:
            company = (
                page.get("metadata", {}).get("company_name") or
                json_data.get("metadata", {}).get("financial_metadata", {}).get("company_name", "Unknown")
            )

            def traverse(node, section=""):
                for key, value in node.items():
                    if isinstance(value, dict):
                        if any(k.isdigit() or k == "current" for k in value.keys()):
                            cat = _norm_category(section, key)
                            for year_key, raw_val in value.items():
                                records.append({
                                    "Company": company,
                                    "Item": str(key).strip(),
                                    "Year": _norm_year(year_key),
                                    "Amount": normalizer.to_numeric(raw_val),
                                    "Category": cat,
                                })
                        else:
                            next_sec = key if _norm_category(key) else section
                            traverse(value, next_sec)

            traverse(page.get("financial_data", {}).get("extracted_data", {}))

    df = pd.DataFrame(records)
    if df.empty:
        return df

    df["Amount"] = pd.to_numeric(df["Amount"], errors="coerce").fillna(0.0)
    df = df[df["Item"].str.strip() != ""].copy()

    # Deduplicate: keep the highest-abs value per Company+Item+Year+Category
    df["_abs"] = df["Amount"].abs()
    df = (df.sort_values("_abs", ascending=False)
            .drop_duplicates(subset=["Company", "Item", "Year", "Category"])
            .drop(columns="_abs")
            .reset_index(drop=True))
    return df


# ─────────────────────────────────────────────
# SIDEBAR
# ─────────────────────────────────────────────
def sidebar_uploader() -> Optional[pd.DataFrame]:
    with st.sidebar:
        st.markdown("### 📂 Upload Data")
        source = st.radio("Input type", ["PDF (auto-extract)", "JSON (pre-extracted)"], label_visibility="collapsed")

        if source == "PDF (auto-extract)":
            uploaded = st.file_uploader("Upload PDF", type=["pdf"], label_visibility="collapsed")
            if uploaded:
                cache_key = f"df_{uploaded.name}_{uploaded.size}"
                if cache_key not in st.session_state:
                    prog = st.progress(0, text="Extracting…")

                    def on_progress(cur, tot, msg):
                        prog.progress(cur / tot, text=msg)

                    extractor = FinancialPDFExtractor()
                    raw_json = extractor.extract_from_bytes(
                        uploaded.read(), filename=uploaded.name, progress_callback=on_progress
                    )
                    prog.empty()
                    st.session_state[cache_key] = raw_json
                    st.session_state[f"raw_{cache_key}"] = raw_json
                    st.success("✅ Done!")

                raw_json = st.session_state[cache_key]
                st.download_button(
                    "⬇️ Download extracted JSON",
                    data=json.dumps(raw_json, indent=2),
                    file_name=f"{uploaded.name.replace('.pdf','')}_extracted.json",
                    mime="application/json",
                )
                return json_to_dataframe(raw_json)

        else:
            uploaded = st.file_uploader("Upload JSON", type=["json"], label_visibility="collapsed")
            if uploaded:
                raw_json = json.load(uploaded)
                return json_to_dataframe(raw_json)

    return None


# ─────────────────────────────────────────────
# SUMMARY METRICS
# ─────────────────────────────────────────────
def show_summary(df: pd.DataFrame):
    latest = _latest_year(df)
    yr_df = df[df["Year"] == latest]

    def get_total(cat, hint):
        sub = yr_df[yr_df["Category"] == cat]
        if sub.empty:
            return 0.0
        tot = sub[sub["Item"].str.contains(hint, case=False, na=False)]
        if not tot.empty:
            return float(tot["Amount"].abs().max())
        detail = sub[~sub["Item"].str.contains(r"\btotal\b|\bsubtotal\b", case=False, na=False)]
        return float(detail["Amount"].sum()) if not detail.empty else float(sub["Amount"].sum())

    has_income = {"Revenue", "Expenses"}.intersection(set(df["Category"].unique()))
    if has_income:
        rev = get_total("Revenue", r"total\s*(revenue|income)")
        exp = get_total("Expenses", r"total\s*(expense|expenditure)")
        net = rev - abs(exp)
        labels = ("Revenue / Income", "Expenses / Outflows", "Net Position")
        vals = (rev, exp, net)
    else:
        assets = get_total("Assets", r"total\s*assets")
        liab = get_total("Liabilities", r"total\s*liabilities")
        equity = get_total("Equity", r"total\s*(equity|net\s*assets)")
        labels = ("Total Assets", "Total Liabilities", "Equity / Net Assets")
        vals = (assets, liab, equity)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric(labels[0], fmt_amount(vals[0]))
    c2.metric(labels[1], fmt_amount(abs(vals[1])))
    c3.metric(labels[2], fmt_amount(vals[2]))
    c4.metric(f"Line Items · {df['Year'].nunique()} yr(s)", str(df["Item"].nunique()))


# ─────────────────────────────────────────────
# CHART AGENT
# ─────────────────────────────────────────────
def _extract_code(text: str) -> str:
    for pat in [r"```python\s*(.*?)```", r"```\s*(.*?)```"]:
        blocks = re.findall(pat, text, re.DOTALL)
        if blocks:
            return blocks[0].strip()
    return text.strip()


def _sanitize_generated_code(code: str) -> str:
    """Patch common LLM Plotly mistakes before exec."""
    lines = code.splitlines()
    out = []

    for line in lines:
        if "fig.update_layout(" in line and "hole=" in line:
            indent = re.match(r"^\s*", line).group(0)
            hole_match = re.search(r"hole\s*=\s*([^,\)]+)", line)

            # Remove only the hole kwarg from update_layout call.
            cleaned = re.sub(r",\s*hole\s*=\s*[^,\)]+", "", line)
            cleaned = re.sub(r"hole\s*=\s*[^,\)]+\s*,\s*", "", cleaned)
            cleaned = re.sub(r"\(\s*\)", "()", cleaned)

            if cleaned.strip() != "fig.update_layout()":
                out.append(cleaned)

            if hole_match:
                out.append(f"{indent}fig.update_traces(hole={hole_match.group(1).strip()})")
            continue

        out.append(line)

    return "\n".join(out)


def generate_chart_code(df: pd.DataFrame, query: str) -> str:
    years = sorted(df["Year"].unique().tolist(), key=_year_key)
    companies = df["Company"].unique().tolist()
    items_sample = df["Item"].unique().tolist()[:20]
    categories = [c for c in df["Category"].unique().tolist() if c]
    sample = (
        df.groupby(["Company", "Item", "Year", "Category"])["Amount"]
        .sum().reset_index().head(30).to_string(index=False)
    )

    prompt = f"""You are a Python + Plotly code generator for financial data visualisation.
Output ONLY raw executable Python code. No markdown. No explanations. No comments.

DATAFRAME `df` — already exists, never recreate it.
Columns: Company (str), Item (str), Year (str), Amount (float), Category (str)

Companies : {companies}
Years     : {years}  ← ALL STRINGS — never use integer
Categories: {categories}
Sample Items (use exact spellings): {items_sample}

SAMPLE DATA:
{sample}

RULES:
1. Year filter must be string:  df['Year'] == '2020'
2. Item filter: str.contains('revenue', case=False, na=False)
3. Chain filters with & in parens.
4. If filtered data is empty: raise ValueError('No data matched.')
5. Assign final figure to variable `fig`.
6. template="plotly_dark" on every chart.
7. fig.update_layout(height=500, title='...')
8. fig.update_yaxes(tickformat="$,.0f") for bar/line.
9. NEVER call fig.show().
10. px, go, pd, make_subplots, fmt_amount already imported — do NOT re-import.
11. For pie/donut charts: set hole in go.Pie(..., hole=0.5) or fig.update_traces(hole=0.5).
12. NEVER use fig.update_layout(hole=...).

CHART TYPE HINTS:
- Item breakdown for a year → px.bar, orientation='h', x='Amount', y='Item'
- Trend over years → px.line, x='Year', y='Amount', color='Item', markers=True
- Category breakdown → go.Pie, hole=0.5
- Company comparison → px.bar, barmode='group', color='Company'

USER REQUEST: {query}"""

    try:
        resp = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": query},
            ],
            temperature=0,
        )
        return _extract_code(resp.choices[0].message.content)
    except Exception as e:
        return f"raise ValueError('LLM error: {e}')"


# ─────────────────────────────────────────────
# INSIGHTS AGENT
# ─────────────────────────────────────────────
def generate_insight(df: pd.DataFrame, query: str) -> str:
    summary = df.groupby(["Company", "Category", "Item", "Year"])["Amount"].sum().reset_index()
    summary["Formatted"] = summary["Amount"].apply(fmt_amount)
    context = summary.to_csv(index=False)

    prompt = (
        "You are a concise financial analyst. Answer strictly from the data below.\n\n"
        f"DATA (CSV):\n{context}\n\n"
        "Rules:\n"
        "- Be direct and concise.\n"
        "- Use bullet points for lists.\n"
        "- Quote exact formatted figures from the Formatted column.\n"
        "- Never invent or estimate numbers.\n"
        "- If data is unavailable, say so clearly."
    )
    try:
        resp = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": query},
            ],
            temperature=0.1,
        )
        return resp.choices[0].message.content
    except Exception as e:
        return f"Error: {e}"


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────
def main():
    st.title("📊 Financial Analyst")
    st.caption("Upload a financial PDF or JSON — then visualise or ask questions about the data.")

    df = sidebar_uploader()

    if df is None:
        st.info("👈 Upload a PDF or JSON file in the sidebar to get started.")
        return

    if df.empty:
        st.error("⚠️ No financial data could be parsed from the uploaded file.")
        return

    # Summary bar
    show_summary(df)
    st.divider()

    # ── Mode selector ─────────────────────────
    mode = st.radio(
        "What do you want to do?",
        ["📊 Visualize Data", "💡 Get Insights"],
        horizontal=True,
        label_visibility="collapsed",
    )

    st.write("")

    # ── VISUALIZE MODE ────────────────────────
    if mode == "📊 Visualize Data":
        st.markdown("#### 📊 Visualize Data")
        st.caption("Describe what you want to see — the AI will generate an interactive chart.")

        if "chart_history" not in st.session_state:
            st.session_state.chart_history = []

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
                    if msg.get("hint"):
                        st.info(msg["hint"])

        query = st.chat_input(
            "e.g. 'Show top 10 expenses as a bar chart' or 'Revenue trend over all years'",
            key="viz_input",
        )

        if query:
            st.session_state.chart_history.append({"role": "user", "content": query})
            with st.chat_message("user"):
                st.write(query)

            with st.chat_message("assistant"):
                with st.spinner("Generating chart…"):
                    code = generate_chart_code(df, query)
                    safe_code = _sanitize_generated_code(code)

                if safe_code != code:
                    st.caption("Applied automatic Plotly compatibility fix to generated code.")

                with st.expander("🔍 Generated code", expanded=False):
                    st.code(safe_code, language="python")

                exec_globals = {
                    "df": df, "px": px, "go": go,
                    "pd": pd, "fmt_amount": fmt_amount,
                    "make_subplots": make_subplots,
                }
                exec_locals: Dict = {}

                try:
                    exec(safe_code, exec_globals, exec_locals)  # noqa: S102
                    fig = exec_locals.get("fig")

                    if fig is None:
                        msg = "⚠️ No figure was produced. Try rephrasing your request."
                        st.warning(msg)
                        st.session_state.chart_history.append({"role": "assistant", "warning": msg})
                    else:
                        fig.update_layout(
                            template="plotly_dark",
                            paper_bgcolor="rgba(0,0,0,0)",
                            plot_bgcolor="rgba(0,0,0,0)",
                            font=dict(family="Syne, sans-serif"),
                        )
                        st.plotly_chart(fig, use_container_width=True)
                        st.session_state.chart_history.append({"role": "assistant", "fig": fig})

                except ValueError as ve:
                    warning_msg = f"⚠️ {ve}"
                    st.warning(warning_msg)
                    # Give helpful hints
                    kws = [w for w in re.sub(r"[^\w\s]", "", query).lower().split() if len(w) > 2]
                    item_hits = [i for i in df["Item"].unique() if any(k in i.lower() for k in kws)]
                    hint = ""
                    if item_hits:
                        hint = f"💡 Matching items found: `{'`, `'.join(item_hits[:8])}`"
                        st.info(hint)
                    st.session_state.chart_history.append({
                        "role": "assistant", "warning": warning_msg, "hint": hint
                    })

                except Exception as exc:
                    err = f"❌ Execution error: {exc}"
                    st.error(err)
                    st.code(safe_code, language="python")
                    st.session_state.chart_history.append({"role": "assistant", "error": err})

    # ── INSIGHTS MODE ─────────────────────────
    else:
        st.markdown("#### 💡 Get Insights")
        st.caption("Ask any question about the data — get a direct, analyst-style answer.")

        if "insight_history" not in st.session_state:
            st.session_state.insight_history = []

        # Replay history
        for msg in st.session_state.insight_history:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])

        query = st.chat_input(
            "e.g. 'What are the top 3 expense items?' or 'How did revenue change year over year?'",
            key="insight_input",
        )

        if query:
            st.session_state.insight_history.append({"role": "user", "content": query})
            with st.chat_message("user"):
                st.markdown(query)

            with st.chat_message("assistant"):
                with st.spinner("Analysing…"):
                    answer = generate_insight(df, query)
                st.markdown(answer)
                st.session_state.insight_history.append({"role": "assistant", "content": answer})

    # ── Raw data toggle ───────────────────────
    with st.expander("🗂 Raw extracted data", expanded=False):
        st.caption(f"{len(df):,} rows · {df['Item'].nunique()} unique items · {df['Year'].nunique()} year(s)")
        st.dataframe(df.style.format({"Amount": fmt_amount}), use_container_width=True, height=400)


if __name__ == "__main__":
    main()
