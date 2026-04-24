import json
import re
from typing import Any, Dict, List, Optional

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go


SOURCE_ALIASES = {
    "memberships": [r"membership", r"registration"],
    "sales": [r"sales", r"equipment", r"service"],
    "fundraising": [r"fundraising", r"donation", r"sponsorship", r"grant"],
    "interest": [r"interest", r"investment income", r"finance income"],
}


METRIC_ALIASES = {
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
    return "all"


def _year_sort_key(y: str):
    y = str(y)
    if re.fullmatch(r"(19|20)\d{2}", y):
        return (0, int(y))
    return (1, y)


def _resolve_year(df: pd.DataFrame, year: str) -> str:
    if str(year).lower() == "all":
        return "all"
    years = set(df["Year"].dropna().astype(str).tolist())
    return year if year in years else _latest_year(df)


def _extract_year_from_query(df: pd.DataFrame, user_query: str) -> str:
    match = re.search(r"(19|20)\d{2}", user_query)
    if match:
        return _resolve_year(df, match.group(0))
    return _latest_year(df)


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
    matches = _extract_companies_from_query(df, query)
    return matches[0] if matches else None


def _extract_requested_sources(user_query: str) -> List[str]:
    match = re.search(r"\(([^\)]+)\)", user_query)
    if not match:
        return list(SOURCE_ALIASES.keys())

    requested = [s.strip().lower() for s in match.group(1).split(",") if s.strip()]
    cleaned = [src for src in requested if src in SOURCE_ALIASES]
    return cleaned if cleaned else list(SOURCE_ALIASES.keys())


def _metric_from_query(user_query: str) -> str:
    q = user_query.lower()
    for metric, aliases in METRIC_ALIASES.items():
        if any(alias in q for alias in aliases):
            return metric
    return ""


def _is_compare_query(user_query: str) -> bool:
    q = user_query.lower()
    return any(token in q for token in ["compare", "comparison", "vs", "versus", "between"])


def _is_chart_request(user_query: str) -> bool:
    q = user_query.lower()
    return any(token in q for token in ["chart", "graph", "plot", "visual", "bar", "line", "pie"])


def _requested_chart_type(user_query: str) -> Optional[str]:
    q = user_query.lower()
    if "pie" in q or "donut" in q:
        return "pie"
    if "line" in q or "trend" in q:
        return "line"
    if any(token in q for token in ["bar", "column", "histogram"]):
        return "bar"
    return None


def _fmt_metric_label(metric: str) -> str:
    return "Net Surplus/Deficit" if metric == "Net Income" else metric


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
        return _category_total(frame, "Revenue") - abs(_category_total(frame, "Expenses"))
    return _category_total(frame, metric)


def _build_metric_company_bar(
    df: pd.DataFrame,
    metric: str,
    year: str,
    companies: Optional[List[str]] = None,
    title: Optional[str] = None,
) -> Optional[go.Figure]:
    year = _resolve_year(df, year)
    work = df.copy() if year == "all" else df[df["Year"].astype(str) == str(year)].copy()
    if work.empty:
        return None

    if companies:
        work = work[work["Company"].isin(companies)].copy()

    labels = sorted(work["Company"].dropna().astype(str).unique().tolist())
    if not labels:
        return None

    rows = []
    for company in labels:
        company_frame = work[work["Company"] == company]
        rows.append({"Company": company, "Amount": _metric_value(company_frame, metric)})

    chart_df = pd.DataFrame(rows)
    if chart_df.empty:
        return None

    if metric != "Net Income":
        chart_df["Amount"] = chart_df["Amount"].abs()

    chart_df = chart_df.sort_values("Amount", ascending=False)
    fig = px.bar(
        chart_df,
        x="Company",
        y="Amount",
        title=title or f"{_fmt_metric_label(metric)} Comparison ({year})",
    )
    fig.update_layout(xaxis_title="Company", yaxis_title=_fmt_metric_label(metric))
    if metric == "Net Income":
        fig.add_hline(y=0, line_dash="dash", line_color="gray")
    return fig


def _build_metric_item_breakdown_bar(
    df: pd.DataFrame,
    metric: str,
    year: str,
    company: str,
    title: Optional[str] = None,
) -> Optional[go.Figure]:
    year = _resolve_year(df, year)
    if year == "all":
        year = _latest_year(df)
        if year == "all":
            return None
    work = df[(df["Year"].astype(str) == str(year)) & (df["Company"] == company)].copy()
    if work.empty:
        return None

    if metric in {"Revenue", "Expenses", "Assets", "Liabilities", "Equity"}:
        metric_rows = work[work["Category"].astype(str).str.lower() == metric.lower()].copy()
    else:
        metric_rows = work.copy()

    metric_rows = metric_rows[
        ~metric_rows["Item"].astype(str).str.contains(r"\btotal\b|\bsubtotal\b", case=False, na=False)
    ]
    if metric_rows.empty:
        return None

    chart_df = (
        metric_rows.groupby("Item", as_index=False)["Amount"]
        .sum()
        .sort_values("Amount", ascending=False)
        .head(12)
    )
    if chart_df.empty:
        return None

    if metric != "Net Income":
        chart_df["Amount"] = chart_df["Amount"].abs()

    fig = px.bar(
        chart_df,
        x="Item",
        y="Amount",
        title=title or f"{_fmt_metric_label(metric)} Breakdown for {company} ({year})",
    )
    fig.update_layout(xaxis_title="Item", yaxis_title=_fmt_metric_label(metric), xaxis_tickangle=-30)
    return fig


def _build_source_distribution_pie(df: pd.DataFrame, user_query: str) -> Optional[go.Figure]:
    q = user_query.lower()
    if "pie" not in q:
        return None
    if not any(token in q for token in ["distribution", "breakdown", "composition", "share", "split"]):
        return None
    if not any(token in q for token in ["revenue", "income", "sales", "source", "stream"]):
        return None

    company = _match_company_from_query(df, user_query)
    if not company:
        return None

    year = _extract_year_from_query(df, user_query)
    sub = df[(df["Company"] == company) & (df["Year"].astype(str) == str(year))].copy()
    if sub.empty:
        return None

    revenue_sub = sub[sub["Category"].astype(str).str.lower() == "revenue"].copy()
    if revenue_sub.empty:
        revenue_sub = sub[
            ~sub["Item"].astype(str).str.contains(
                r"expense|cost|liabil|asset|equity|deficit|loss|total expenses",
                case=False,
                na=False,
                regex=True,
            )
        ].copy()

    revenue_sub = revenue_sub[
        ~revenue_sub["Item"].astype(str).str.contains(r"\btotal\b|\bsubtotal\b", case=False, na=False)
    ]
    if revenue_sub.empty:
        return None

    rows = []
    for source in _extract_requested_sources(user_query):
        patterns = SOURCE_ALIASES[source]
        mask = revenue_sub["Item"].astype(str).str.contains("|".join(patterns), case=False, regex=True, na=False)
        vals = revenue_sub.loc[mask, "Amount"]
        amount = float(vals[vals > 0].sum())
        if amount > 0:
            rows.append({"Source": source.title(), "Amount": amount})

    dist = pd.DataFrame(rows)
    if dist.empty:
        return None

    return px.pie(dist, names="Source", values="Amount", title=f"Revenue Distribution for {company} ({year})")


def _bar_to_pie(base_fig: Optional[go.Figure], title: Optional[str] = None) -> Optional[go.Figure]:
    if base_fig is None or not getattr(base_fig, "data", None):
        return None

    series = base_fig.data[0]
    labels = list(series.x) if hasattr(series, "x") and series.x is not None else []
    values = list(series.y) if hasattr(series, "y") and series.y is not None else []
    if not labels or not values:
        return None

    pie_df = pd.DataFrame({"Label": labels, "Amount": values})
    if pie_df.empty:
        return None

    return px.pie(
        pie_df,
        names="Label",
        values="Amount",
        title=title or (base_fig.layout.title.text if base_fig.layout and base_fig.layout.title else "Metric Share"),
    )


def _build_deterministic_chart(df: pd.DataFrame, user_query: str) -> Optional[go.Figure]:
    metric = _metric_from_query(user_query)
    year = _extract_year_from_query(df, user_query)
    companies = _extract_companies_from_query(df, user_query)
    q = user_query.lower()
    requested_chart_type = _requested_chart_type(user_query)

    # Respect explicit pie intent first.
    if requested_chart_type == "pie":
        source_pie = _build_source_distribution_pie(df, user_query)
        if source_pie is not None:
            return source_pie

        if metric:
            if len(companies) == 1 and metric != "Net Income":
                item_bar = _build_metric_item_breakdown_bar(df, metric=metric, year=year, company=companies[0])
                pie_from_items = _bar_to_pie(item_bar)
                if pie_from_items is not None:
                    return pie_from_items

            company_bar = _build_metric_company_bar(df, metric=metric, year=year, companies=companies or None)
            pie_from_companies = _bar_to_pie(company_bar)
            if pie_from_companies is not None:
                return pie_from_companies

    if metric and _is_compare_query(user_query):
        fig = _build_metric_company_bar(df, metric=metric, year=year, companies=companies or None)
        if fig is not None:
            return fig

    if metric and requested_chart_type in {None, "bar"} and any(token in q for token in ["bar", "column", "histogram", "chart", "graph", "plot"]):
        if len(companies) >= 2:
            fig = _build_metric_company_bar(df, metric=metric, year=year, companies=companies)
            if fig is not None:
                return fig

        if len(companies) == 1 and metric != "Net Income":
            fig = _build_metric_item_breakdown_bar(df, metric=metric, year=year, company=companies[0])
            if fig is not None:
                return fig

        fig = _build_metric_company_bar(df, metric=metric, year=year, companies=None)
        if fig is not None:
            return fig

    return _build_source_distribution_pie(df, user_query)


def _parse_json_object(text: str) -> Dict[str, Any]:
    raw = (text or "").strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    return json.loads(raw)


def _llm_chart_spec(
    df: pd.DataFrame,
    user_query: str,
    client: Any,
    model: str,
    temperature: float,
) -> Dict[str, Any]:
    if client is None:
        raise ValueError("LLM client is unavailable.")

    companies = sorted(df["Company"].dropna().astype(str).unique().tolist())
    years = sorted(df["Year"].dropna().astype(str).unique().tolist(), key=_year_sort_key)

    system_prompt = (
        "Return only a valid JSON object for financial chart intent parsing. "
        "Never return Python code. "
        "Allowed metric: Net Income, Revenue, Expenses, Assets, Liabilities, Equity. "
        "Allowed chart_type: bar, line, pie. "
        "Allowed group_by: company, item, year. "
        "Allowed year: specific year string from data, latest, or all."
    )
    user_payload = {
        "query": user_query,
        "available_companies": companies,
        "available_years": years,
        "required_schema": {
            "chart_type": "bar",
            "metric": "Net Income",
            "year": "latest",
            "companies": [],
            "group_by": "company",
            "top_n": 12,
            "title": "string",
        },
    }

    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(user_payload)},
        ],
        temperature=temperature,
        response_format={"type": "json_object"},
    )
    return _parse_json_object(response.choices[0].message.content)


def _apply_chart_spec(df: pd.DataFrame, spec: Dict[str, Any], user_query: str) -> Optional[go.Figure]:
    metric = str(spec.get("metric") or "")
    if metric not in METRIC_ALIASES:
        metric = _metric_from_query(user_query) or "Revenue"

    requested_year = str(spec.get("year") or "latest").strip().lower()
    if requested_year in {"", "latest", "current"}:
        year = _extract_year_from_query(df, user_query)
    elif requested_year == "all":
        year = "all"
    else:
        year = _resolve_year(df, requested_year)

    requested_companies = spec.get("companies") if isinstance(spec.get("companies"), list) else []
    valid_companies = set(df["Company"].dropna().astype(str).unique().tolist())
    companies = [c for c in requested_companies if c in valid_companies]
    if not companies:
        companies = _extract_companies_from_query(df, user_query)

    group_by = str(spec.get("group_by") or "company").lower()
    chart_type = str(spec.get("chart_type") or "bar").lower()
    title = spec.get("title")
    if not isinstance(title, str) or not title.strip():
        title = None

    if year == "all" and group_by == "year":
        work = df.copy()
        if companies:
            work = work[work["Company"].isin(companies)]
        if work.empty:
            return None

        rows = []
        for yr in sorted(work["Year"].astype(str).unique().tolist(), key=_year_sort_key):
            yr_frame = work[work["Year"].astype(str) == yr]
            rows.append({"Year": yr, "Amount": _metric_value(yr_frame, metric)})
        chart_df = pd.DataFrame(rows)
        if chart_df.empty:
            return None

        if metric != "Net Income":
            chart_df["Amount"] = chart_df["Amount"].abs()

        if chart_type == "line":
            fig = px.line(chart_df, x="Year", y="Amount", markers=True, title=title or f"{_fmt_metric_label(metric)} Trend")
        else:
            fig = px.bar(chart_df, x="Year", y="Amount", title=title or f"{_fmt_metric_label(metric)} by Year")

        fig.update_layout(yaxis_title=_fmt_metric_label(metric))
        if metric == "Net Income":
            fig.add_hline(y=0, line_dash="dash", line_color="gray")
        return fig

    selected_year = _extract_year_from_query(df, user_query) if year == "all" else year

    if group_by == "item" and companies and metric != "Net Income":
        return _build_metric_item_breakdown_bar(
            df,
            metric=metric,
            year=selected_year,
            company=companies[0],
            title=title,
        )

    base_fig = _build_metric_company_bar(
        df,
        metric=metric,
        year=selected_year,
        companies=companies if companies else None,
        title=title,
    )
    if base_fig is None:
        return None

    if chart_type == "pie":
        return _bar_to_pie(base_fig, title=title)

    return base_fig


def render_visualization(
    df: pd.DataFrame,
    user_query: str,
    client: Any,
    model: str = "llama-3.3-70b-versatile",
    temperature: float = 0.0,
) -> Dict[str, Any]:
    """Return dict with keys: figure, error, mode, details."""
    if df is None or df.empty:
        return {
            "figure": None,
            "error": "No data available for visualization.",
            "mode": "none",
            "details": None,
        }

    deterministic_fig = _build_deterministic_chart(df, user_query)
    if deterministic_fig is not None:
        return {
            "figure": deterministic_fig,
            "error": None,
            "mode": "deterministic",
            "details": "Matched deterministic chart template.",
        }

    if not _is_chart_request(user_query):
        return {
            "figure": None,
            "error": "Could not infer a chart type. Try adding words like bar, line, or pie.",
            "mode": "none",
            "details": None,
        }

    try:
        spec = _llm_chart_spec(df, user_query, client=client, model=model, temperature=temperature)
        fig = _apply_chart_spec(df, spec, user_query)
        if fig is None:
            return {
                "figure": None,
                "error": "Could not map the request to available financial data.",
                "mode": "llm-spec",
                "details": spec,
            }
        return {
            "figure": fig,
            "error": None,
            "mode": "llm-spec",
            "details": spec,
        }
    except Exception as exc:
        return {
            "figure": None,
            "error": f"Visualization error: {exc}",
            "mode": "llm-spec",
            "details": None,
        }
