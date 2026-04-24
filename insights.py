import hashlib
import re
from typing import Any, Dict, List, Optional

import pandas as pd

try:
    import chromadb
    from chroma_config import get_chroma_settings
    CHROMA_AVAILABLE = True
except Exception:
    chromadb = None
    CHROMA_AVAILABLE = False


_METRIC_ALIASES = {
    "Net Income": ["net income", "net surplus", "surplus", "deficit", "profit", "loss"],
    "Revenue": ["revenue", "income", "sales"],
    "Expenses": ["expense", "expenses", "expenditure", "cost"],
    "Assets": ["asset", "assets", "assest", "assests"],
    "Liabilities": ["liability", "liabilities"],
    "Equity": ["equity", "net assets", "capital"],
}


def _latest_year(df: pd.DataFrame) -> str:
    years = df["Year"].dropna().astype(str).unique().tolist()
    numeric_years = sorted([y for y in years if re.fullmatch(r"(19|20)\d{2}", y)])
    if numeric_years:
        return numeric_years[-1]
    if "Current" in years:
        return "Current"
    return "Unknown"


def _year_sort_key(y: str):
    y = str(y)
    if re.fullmatch(r"(19|20)\d{2}", y):
        return (0, int(y))
    return (1, y)


def _resolve_year(df: pd.DataFrame, year: str) -> str:
    years = set(df["Year"].dropna().astype(str).tolist())
    return year if year in years else _latest_year(df)


def _fmt_money(value: float) -> str:
    return f"${value:,.0f}"


def _extract_companies_from_query(df: pd.DataFrame, query: str) -> List[str]:
    q = query.lower()
    companies = df["Company"].dropna().astype(str).unique().tolist()
    found: List[str] = []

    for company in companies:
        if company.lower() in q and company not in found:
            found.append(company)

    for company in companies:
        tokens = [t for t in re.findall(r"[a-z0-9]+", company.lower()) if len(t) > 2]
        strong = [t for t in tokens if t not in {"company", "organization", "organisation"}]
        if strong and all(t in q for t in strong[:2]) and company not in found:
            found.append(company)

    for alias in ["abc", "xyz"]:
        if alias in q:
            for company in companies:
                if alias in company.lower() and company not in found:
                    found.append(company)
                    break

    return found


def _match_company_from_query(df: pd.DataFrame, query: str) -> Optional[str]:
    companies = _extract_companies_from_query(df, query)
    return companies[0] if companies else None


def _metric_from_query(user_query: str) -> str:
    q = user_query.lower()
    for metric, aliases in _METRIC_ALIASES.items():
        if any(alias in q for alias in aliases):
            return metric
    return ""


def _extract_explicit_year(user_query: str) -> Optional[str]:
    match = re.search(r"(19|20)\d{2}", user_query)
    return match.group(0) if match else None


def _is_compare_query(user_query: str) -> bool:
    q = user_query.lower()
    return any(token in q for token in ["compare", "comparison", "vs", "versus", "between"])


def _category_total(frame: pd.DataFrame, category: str) -> float:
    sub = frame[frame["Category"].astype(str).str.lower() == category.lower()]
    if sub.empty:
        return 0.0

    if category == "Revenue":
        pattern = r"total\s*(?:revenue|income)"
    elif category == "Expenses":
        pattern = r"total\s*(?:expense|expenses|expenditure|cost)"
    elif category == "Assets":
        pattern = r"total\s*assets"
    elif category == "Liabilities":
        pattern = r"total\s*liabilities"
    elif category == "Equity":
        pattern = r"total\s*(?:equity|net\s*assets)|net\s*assets"
    else:
        pattern = r"\btotal\b"

    totals = sub[sub["Item"].astype(str).str.contains(pattern, case=False, na=False, regex=True)]
    if not totals.empty:
        val = float(totals["Amount"].abs().max())
    else:
        detail = sub[~sub["Item"].astype(str).str.contains(r"\btotal\b|\bsubtotal\b", case=False, na=False)]
        val = float(detail["Amount"].sum()) if not detail.empty else float(sub["Amount"].sum())

    if category in {"Expenses", "Liabilities"}:
        return abs(val)
    return val


def _metric_value(frame: pd.DataFrame, metric: str) -> float:
    if metric == "Net Income":
        rev = _category_total(frame, "Revenue")
        exp = _category_total(frame, "Expenses")
        return rev - abs(exp)
    return _category_total(frame, metric)


def deterministic_insight(df: pd.DataFrame, user_query: str) -> Optional[str]:
    metric = _metric_from_query(user_query)
    if not metric:
        return None

    explicit_year = _extract_explicit_year(user_query)
    year = _resolve_year(df, explicit_year) if explicit_year else _latest_year(df)

    if _is_compare_query(user_query):
        companies = _extract_companies_from_query(df, user_query)
        work = df[df["Year"].astype(str) == str(year)].copy()
        if companies:
            work = work[work["Company"].isin(companies)]

        labels = sorted(work["Company"].dropna().astype(str).unique().tolist())
        if not labels:
            return "Not available in provided data."

        rows = []
        for company in labels:
            val = _metric_value(work[work["Company"] == company], metric)
            rows.append((company, val))

        if metric != "Net Income":
            rows = [(name, abs(value)) for name, value in rows]

        label_name = "Net Surplus/Deficit" if metric == "Net Income" else metric
        lines = [f"- {name}: {_fmt_money(value)}" for name, value in rows]
        return f"{label_name} comparison in {year}:\n" + "\n".join(lines)

    company = _match_company_from_query(df, user_query)
    work = df.copy()
    subject = "All companies"
    if company:
        work = work[work["Company"] == company]
        subject = company
    if work.empty:
        return "Not available in provided data."

    if explicit_year:
        work = work[work["Year"].astype(str) == str(year)]
        if work.empty:
            return "Not available in provided data."

    years = sorted(work["Year"].astype(str).unique().tolist(), key=_year_sort_key)
    years = [y for y in years if y.lower() != "unknown"] or years

    label_name = "Net Surplus/Deficit" if metric == "Net Income" else metric

    if explicit_year:
        val = _metric_value(work, metric)
        if metric != "Net Income":
            val = abs(val)
        return f"{label_name} for {subject} in {year}: {_fmt_money(val)}"

    lines = []
    for yr in years:
        yf = work[work["Year"].astype(str) == yr]
        if yf.empty:
            continue
        val = _metric_value(yf, metric)
        if metric != "Net Income":
            val = abs(val)
        lines.append(f"- {yr}: {_fmt_money(val)}")

    if not lines:
        return "Not available in provided data."

    return f"{label_name} for {subject}:\n" + "\n".join(lines)


def _dataset_key(df: pd.DataFrame) -> str:
    companies = "|".join(sorted(df["Company"].dropna().astype(str).unique().tolist())[:30])
    years = "|".join(sorted(df["Year"].dropna().astype(str).unique().tolist())[:30])
    total = float(pd.to_numeric(df.get("Amount", pd.Series(dtype=float)), errors="coerce").fillna(0.0).sum())
    payload = f"rows={len(df)};companies={companies};years={years};total={total:.2f}"
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()


def _row_to_text(row: pd.Series) -> str:
    return (
        f"Company: {row.get('Company', '')} | "
        f"Year: {row.get('Year', '')} | "
        f"Category: {row.get('Category', '')} | "
        f"Item: {row.get('Item', '')} | "
        f"Amount: {row.get('Amount', '')}"
    )


def _retrieve_with_chroma(df: pd.DataFrame, user_query: str, top_k: int = 30) -> Optional[pd.DataFrame]:
    if not CHROMA_AVAILABLE or df.empty:
        return None

    try:
        key = _dataset_key(df)
        collection_name = f"financial_rows_{key[:24]}"
        client = chromadb.PersistentClient(path="financial_chroma_db", settings=get_chroma_settings())
        collection = client.get_or_create_collection(name=collection_name)

        if collection.count() == 0:
            docs = []
            ids = []
            metas = []
            for idx, row in df.reset_index(drop=True).iterrows():
                docs.append(_row_to_text(row))
                ids.append(f"row_{idx}")
                metas.append({"row_index": int(idx)})
            if docs:
                collection.add(documents=docs, ids=ids, metadatas=metas)

        count = collection.count()
        if count == 0:
            return None

        results = collection.query(query_texts=[user_query], n_results=min(top_k, count))
        metas = results.get("metadatas", [[]])[0]
        row_indexes = []
        for meta in metas:
            row_index = meta.get("row_index") if isinstance(meta, dict) else None
            if isinstance(row_index, int):
                row_indexes.append(row_index)

        if not row_indexes:
            return None

        unique_indexes = list(dict.fromkeys(row_indexes))
        return df.reset_index(drop=True).iloc[unique_indexes].copy()
    except Exception:
        return None


def _retrieve_with_lexical(df: pd.DataFrame, user_query: str, top_k: int = 30) -> pd.DataFrame:
    if df.empty:
        return df

    q = user_query.lower()
    tokens = [tok for tok in re.findall(r"[a-zA-Z0-9]+", q) if len(tok) > 2]
    metric = _metric_from_query(user_query)
    if metric:
        tokens.extend([tok for tok in re.findall(r"[a-zA-Z]+", metric.lower()) if len(tok) > 2])

    work = df.copy()

    def score_row(row: pd.Series) -> int:
        text = (
            f"{row.get('Company', '')} {row.get('Category', '')} "
            f"{row.get('Item', '')} {row.get('Year', '')}"
        ).lower()
        return sum(1 for tok in tokens if tok in text)

    if tokens:
        work["_score"] = work.apply(score_row, axis=1)
        work = work[work["_score"] > 0]

    if work.empty:
        year = _latest_year(df)
        work = df[df["Year"].astype(str) == year].copy()

    work["_abs"] = pd.to_numeric(work["Amount"], errors="coerce").fillna(0.0).abs()
    work = work.sort_values(["_score", "_abs"], ascending=[False, False]) if "_score" in work.columns else work.sort_values("_abs", ascending=False)
    return work.head(top_k).drop(columns=[c for c in ["_score", "_abs"] if c in work.columns])


def _retrieve_context_rows(df: pd.DataFrame, user_query: str, top_k: int = 30) -> pd.DataFrame:
    chroma_rows = _retrieve_with_chroma(df, user_query, top_k=top_k)
    if chroma_rows is not None and not chroma_rows.empty:
        return chroma_rows
    return _retrieve_with_lexical(df, user_query, top_k=top_k)


def _build_rag_context(df: pd.DataFrame, user_query: str, max_rows: int = 120) -> str:
    rows = _retrieve_context_rows(df, user_query, top_k=max_rows)
    if rows.empty:
        return ""

    cols = ["Company", "Item", "Year", "Amount"]
    if "Category" in rows.columns:
        cols.insert(1, "Category")

    summary = (
        rows.groupby(cols[:-1], as_index=False)["Amount"]
        .sum()
        .sort_values("Amount", key=lambda s: s.abs(), ascending=False)
        .head(max_rows)
    )
    summary["Formatted"] = summary["Amount"].map(_fmt_money)
    return summary.to_csv(index=False)


def _fallback_answer_from_rows(df: pd.DataFrame, user_query: str) -> str:
    rows = _retrieve_context_rows(df, user_query, top_k=8)
    if rows.empty:
        return "Not available in provided data."

    lines = []
    for _, row in rows.head(5).iterrows():
        lines.append(
            f"- {row.get('Company', 'Unknown')} | {row.get('Year', 'Unknown')} | "
            f"{row.get('Item', 'Unknown')}: {_fmt_money(float(row.get('Amount', 0.0)))}"
        )

    return "Top relevant records from your data:\n" + "\n".join(lines)


def generate_insight(
    df: pd.DataFrame,
    user_query: str,
    client: Any,
    model: str = "llama-3.3-70b-versatile",
    temperature: float = 0.2,
) -> str:
    deterministic = deterministic_insight(df, user_query)
    if deterministic:
        return deterministic

    context = _build_rag_context(df, user_query)
    if not context.strip():
        return "Not available in provided data."

    system_prompt = (
        "You are a financial QA assistant. Use only the provided context rows.\n"
        "If exact data is not present, reply: Not available in provided data.\n"
        "Do not invent numbers. Keep the answer concise and factual.\n"
        "When comparing entities, show each value explicitly.\n\n"
        f"CONTEXT CSV:\n{context}"
    )

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_query},
            ],
            temperature=temperature,
        )
        answer = (response.choices[0].message.content or "").strip()
        answer = re.sub(r"\b(?:[A-Za-z]\s+){2,}[A-Za-z]\b", lambda m: m.group(0).replace(" ", ""), answer)
        return answer if answer else "Not available in provided data."
    except Exception as exc:
        msg = str(exc)
        if "rate_limit" in msg.lower() or "429" in msg:
            return "Rate limit reached for text generation. Showing retrieved records instead.\n\n" + _fallback_answer_from_rows(df, user_query)
        return _fallback_answer_from_rows(df, user_query)
