International Cost of Capital App (Streamlit).

Compares a project's cost of equity, cost of debt and WACC in USD and in the
currency of a selected country.

Data sources (fetched live, cached, with a refresh button):
  * Damodaran (NYU Stern): industry unlevered betas and the Baa2/BBB default spread
  * OECD Corporate Tax Statistics: statutory corporate income tax rates
  * Trading Economics: 10-year government bond yields

Run locally:  streamlit run app.py
"""
from __future__ import annotations

import io
import re
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import requests
import streamlit as st

st.set_page_config(
    page_title="International Cost of Capital",
    page_icon="🌍",
    layout="wide",
)

# ----------------------------------------------------------------------------
# Constants
# ----------------------------------------------------------------------------
BETA_URL = "https://pages.stern.nyu.edu/~adamodar/pc/datasets/betas.xls"
BBB_URL = "https://pages.stern.nyu.edu/adamodar/New_Home_Page/datafile/ratings.html"
OECD_URL = (
    "https://www.oecd.org/en/publications/corporate-tax-statistics-2024_9c27d6e8-en/"
    "full-report/statutory-corporate-income-tax-rates_440f9286.html"
    "#chapter-d1e2342-08e74a33fb"
)
TE_URL = "https://tradingeconomics.com/bonds"

DEFAULT_INDUSTRY = "Software (System & Application)"
DEFAULT_COUNTRY = "United States"
DEFAULT_ERP = 6.5  # percent
DEFAULT_DEBT = 30  # percent
CACHE_TTL = 6 * 60 * 60  # seconds

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

MONTHS = (
    "January|February|March|April|May|June|July|August|September|October|"
    "November|December"
)

EUR_COUNTRIES = [
    "Germany", "France", "Italy", "Spain", "Netherlands", "Belgium", "Austria",
    "Finland", "Ireland", "Portugal", "Greece", "Slovakia", "Slovenia",
    "Lithuania", "Latvia", "Estonia", "Luxembourg", "Croatia", "Cyprus", "Malta",
    "Bulgaria",
]
CURRENCY: dict[str, str] = {
    "United States": "USD", "Canada": "CAD", "Mexico": "MXN", "Brazil": "BRL",
    "Argentina": "ARS", "Chile": "CLP", "Colombia": "COP", "Peru": "PEN",
    "Costa Rica": "CRC", "United Kingdom": "GBP", "Switzerland": "CHF",
    "Sweden": "SEK", "Norway": "NOK", "Denmark": "DKK", "Poland": "PLN",
    "Czech Republic": "CZK", "Hungary": "HUF", "Romania": "RON",
    "Iceland": "ISK", "Turkey": "TRY", "Israel": "ILS", "Saudi Arabia": "SAR",
    "Japan": "JPY", "China": "CNY", "Hong Kong": "HKD", "South Korea": "KRW",
    "Taiwan": "TWD", "India": "INR", "Indonesia": "IDR", "Malaysia": "MYR",
    "Thailand": "THB", "Philippines": "PHP", "Vietnam": "VND",
    "Singapore": "SGD", "Pakistan": "PKR", "Australia": "AUD",
    "New Zealand": "NZD", "South Africa": "ZAR", "Egypt": "EGP",
    "Nigeria": "NGN", "Kenya": "KES", "Morocco": "MAD",
}
CURRENCY.update({c: "EUR" for c in EUR_COUNTRIES})

ALIASES = {
    "türkiye": "Turkey", "turkiye": "Turkey",
    "korea": "South Korea", "republic of korea": "South Korea",
    "korea, republic of": "South Korea",
    "slovak republic": "Slovakia", "czechia": "Czech Republic",
    "united states of america": "United States", "usa": "United States",
    "us": "United States", "u.s.": "United States",
    "uk": "United Kingdom", "great britain": "United Kingdom",
    "china (people's republic of)": "China", "people's republic of china": "China",
    "hong kong, china": "Hong Kong", "hong kong (china)": "Hong Kong",
    "viet nam": "Vietnam", "chinese taipei": "Taiwan",
    "russian federation": "Russia",
}


# ----------------------------------------------------------------------------
# Styling (purple background)
# ----------------------------------------------------------------------------
st.markdown(
    """
    <style>
    .stApp {
        background: linear-gradient(160deg, #2b0a57 0%, #4a1a8c 55%, #6b2fb3 100%);
        background-attachment: fixed;
    }
    [data-testid="stHeader"] { background: transparent; }
    [data-testid="stSidebar"] { background: rgba(28, 6, 60, 0.92); }
    .stApp, .stApp p, .stApp li, .stApp label, .stApp h1, .stApp h2, .stApp h3,
    .stApp h4, .stApp h5, .stApp h6, .stApp .stMarkdown, .stApp caption,
    [data-testid="stCaptionContainer"], [data-testid="stWidgetLabel"] p,
    [data-testid="stMetricLabel"], [data-testid="stMetricDelta"] {
        color: #f5f0ff !important;
    }
    [data-testid="stMetricValue"] { color: #ffffff !important; }
    [data-testid="stMetric"] {
        background: rgba(255, 255, 255, 0.09);
        border: 1px solid rgba(255, 255, 255, 0.22);
        border-radius: 14px;
        padding: 14px 16px;
    }
    /* inputs: light fields with dark text so they stay readable */
    [data-baseweb="input"], [data-baseweb="base-input"] {
        background-color: #f5f0ff !important;
    }
    [data-baseweb="input"] input, [data-baseweb="base-input"] input {
        color: #1e0b3a !important;
        -webkit-text-fill-color: #1e0b3a !important;
    }
    [data-baseweb="select"] > div {
        background-color: #f5f0ff !important;
        color: #1e0b3a !important;
    }
    [data-baseweb="select"] * { color: #1e0b3a !important; }
    .stButton > button, [data-testid="stDownloadButton"] > button {
        background: #a855f7; color: #ffffff !important; border: 0;
        border-radius: 10px; font-weight: 600;
    }
    .stButton > button:hover, [data-testid="stDownloadButton"] > button:hover {
        background: #c084fc; color: #ffffff !important;
    }
    [data-testid="stExpander"] {
        background: rgba(255, 255, 255, 0.06);
        border-radius: 12px;
    }
    button[data-baseweb="tab"] p { color: #f5f0ff !important; }
    </style>
    """,
    unsafe_allow_html=True,
)


# ----------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------
def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def _get(url: str) -> requests.Response:
    resp = requests.get(url, headers=HEADERS, timeout=40)
    resp.raise_for_status()
    return resp


def _num(x) -> float:
    """Parse a number out of a messy table cell (handles %, footnotes, minus)."""
    if x is None:
        return np.nan
    if isinstance(x, (int, float, np.number)):
        return float(x)
    s = str(x).replace("\u2212", "-").replace(",", ".")
    m = re.search(r"-?\d+(?:\.\d+)?", s)
    return float(m.group()) if m else np.nan


def _flatten(cols) -> list[str]:
    out = []
    for c in cols:
        if isinstance(c, tuple):
            c = " ".join(str(x) for x in c if "Unnamed" not in str(x))
        out.append(str(c).strip())
    return out


def canon(name) -> str:
    """Normalise country names across OECD / Trading Economics / our currency map."""
    s = str(name).strip()
    s = re.sub(r"\s*[\*\u2020\u2021]+$", "", s)
    s = re.sub(r"\s*\(\d+\)$", "", s)
    s = re.sub(r"\s+\d+\s*Y(?:ears?)?$", "", s, flags=re.I)
    low = s.lower()
    if low in ALIASES:
        return ALIASES[low]
    for k in CURRENCY:
        if k.lower() == low:
            return k
    return s


def _result(url: str, source: str) -> dict:
    return {
        "ok": False, "data": None, "as_of": "n/a", "source": source,
        "url": url, "retrieved": _now(), "error": None,
    }


# ----------------------------------------------------------------------------
# Data fetchers (cached; the refresh button clears the cache)
# ----------------------------------------------------------------------------
@st.cache_data(ttl=CACHE_TTL, show_spinner=False)
def fetch_damodaran_betas() -> dict:
    out = _result(BETA_URL, "Damodaran (NYU Stern) - industry betas, 'Unlevered beta'")
    try:
        r = _get(BETA_URL)
        last_mod = r.headers.get("Last-Modified")
        xls = pd.ExcelFile(io.BytesIO(r.content), engine="xlrd")
        names = xls.sheet_names
        sheet = "Industry Averages" if "Industry Averages" in names else (
            names[1] if len(names) > 1 else names[0]
        )
        raw = xls.parse(sheet, header=None)

        hdr = None
        for i in range(min(40, len(raw))):
            if any(str(v).strip().lower() == "industry name" for v in raw.iloc[i].values):
                hdr = i
                break
        if hdr is None:
            raise ValueError("Could not locate the 'Industry Name' header row.")

        cols = [str(c).strip() for c in raw.iloc[hdr].values]
        df = raw.iloc[hdr + 1:].copy()
        df.columns = cols
        name_col = next(c for c in cols if c.lower() == "industry name")
        beta_col = next(c for c in cols if c.lower() == "unlevered beta")
        df = df[[name_col, beta_col]].copy()
        df.columns = ["Industry", "Unlevered beta"]
        df["Industry"] = df["Industry"].astype(str).str.strip()
        df["Unlevered beta"] = pd.to_numeric(df["Unlevered beta"], errors="coerce")
        df = df.dropna(subset=["Unlevered beta"])
        df = df[(df["Industry"] != "") & (~df["Industry"].str.lower().str.startswith("total market"))]
        df = df.drop_duplicates("Industry").sort_values("Industry").reset_index(drop=True)
        if df.empty:
            raise ValueError("Beta table is empty after parsing.")

        # Data date: look for "... as of January 2026" style text above the table.
        as_of = None
        for i in range(hdr):
            for v in raw.iloc[i].values:
                m = re.search(rf"({MONTHS})\s+\d{{4}}", str(v))
                if m:
                    as_of = m.group()
                    break
            if as_of:
                break
        if not as_of:
            as_of = f"file last modified {last_mod}" if last_mod else "not stated in file"
        out.update(ok=True, data=df, as_of=as_of)
    except Exception as exc:  # noqa: BLE001
        out["error"] = f"{type(exc).__name__}: {exc}"
    return out


@st.cache_data(ttl=CACHE_TTL, show_spinner=False)
def fetch_damodaran_bbb() -> dict:
    out = _result(BBB_URL, "Damodaran (NYU Stern) - Baa2/BBB spread, large non-financial service firms")
    try:
        r = _get(BBB_URL)
        tables = pd.read_html(io.StringIO(r.text))
        spread = None
        for t in tables:
            t = t.copy()
            t.columns = _flatten(t.columns)
            mask = t.apply(lambda col: col.astype(str).str.contains("Baa2/BBB", regex=False))
            if not mask.any().any():
                continue
            row = t[mask.any(axis=1)].iloc[0]
            spread_col = next((c for c in t.columns if "spread" in c.lower()), t.columns[-1])
            val = _num(row[spread_col])
            if np.isnan(val):
                continue
            spread = val / 100 if (val >= 0.5 or "%" in str(row[spread_col])) else val
            break  # the first matching table is the large-firm table
        if spread is None:
            raise ValueError("Baa2/BBB row not found on the page.")

        m = re.search(
            rf"(?:last\s+updated|updated|date\s+of\s+analysis|as\s+of)[^A-Za-z0-9]{{0,12}}"
            rf"((?:{MONTHS})\s+(?:\d{{1,2}},\s+)?\d{{4}})",
            r.text, flags=re.I,
        )
        last_mod = r.headers.get("Last-Modified")
        as_of = m.group(1) if m else (f"page last modified {last_mod}" if last_mod else "not stated on page")
        out.update(ok=True, data=float(spread), as_of=as_of)
    except Exception as exc:  # noqa: BLE001
        out["error"] = f"{type(exc).__name__}: {exc}"
    return out


@st.cache_data(ttl=CACHE_TTL, show_spinner=False)
def fetch_oecd_tax() -> dict:
    out = _result(OECD_URL, "OECD Corporate Tax Statistics 2024 - statutory corporate income tax rates")
    try:
        r = _get(OECD_URL)
        tables = pd.read_html(io.StringIO(r.text))
        rates: dict[str, float] = {}
        years_used: list[int] = []
        for t in tables:
            t = t.copy()
            t.columns = _flatten(t.columns)
            cols = list(t.columns)
            year_cols = {}
            for c in cols:
                m = re.fullmatch(r"\s*(20\d{2})(?:\.0)?\s*", c)
                if m:
                    year_cols[int(m.group(1))] = c
            if len(year_cols) < 3 or len(t) < 5:
                continue
            ccol = cols[0]
            chosen = None
            for yr in sorted(year_cols, reverse=True):
                vals = t[year_cols[yr]].map(_num)
                if vals.notna().sum() >= 10:
                    chosen = (yr, vals)
                    break
            if chosen is None:
                continue
            yr, vals = chosen
            scale = 1.0 if np.nanmax(vals.values) <= 1.0 else 100.0
            for name, v in zip(t[ccol], vals):
                if pd.isna(v) or pd.isna(name):
                    continue
                rates.setdefault(canon(name), float(v) / scale)
            years_used.append(yr)
        if "United States" not in rates:
            raise ValueError("Could not find a statutory-rate table containing the United States.")
        out.update(
            ok=True, data=rates,
            as_of=f"Corporate Tax Statistics 2024 - rates for {max(years_used)}",
        )
    except Exception as exc:  # noqa: BLE001
        out["error"] = f"{type(exc).__name__}: {exc}"
    return out


@st.cache_data(ttl=CACHE_TTL, show_spinner=False)
def fetch_te_yields() -> dict:
    out = _result(TE_URL, "Trading Economics - government bond yields (10-year)")
    try:
        r = _get(TE_URL)
        tables = pd.read_html(io.StringIO(r.text))
        yields: dict[str, tuple[float, str]] = {}
        for t in tables:
            t = t.copy()
            t.columns = _flatten(t.columns)
            cols = list(t.columns)
            ycol = next((c for c in cols if c.lower().startswith("yield")), None)
            if ycol is None:
                continue
            dcol = next((c for c in cols if c.lower() == "date"), None)
            ccol = None
            for c in cols:
                if c == ycol or c.lower() == "date":
                    continue
                s = t[c].dropna().astype(str)
                if len(s) and s.str.contains(r"[A-Za-z]{3,}").mean() > 0.8:
                    ccol = c
                    break
            if ccol is None:
                continue
            for _, row in t.iterrows():
                v = _num(row[ycol])
                if pd.isna(v) or pd.isna(row[ccol]) or not (-5 <= v <= 100):
                    continue
                yields.setdefault(
                    canon(row[ccol]),
                    (v / 100, str(row[dcol]).strip() if dcol else "n/a"),
                )
        if "United States" not in yields:
            raise ValueError("Could not find the United States yield on the page.")
        out.update(ok=True, data=yields, as_of=f"quote date: {yields['United States'][1]}")
    except Exception as exc:  # noqa: BLE001
        out["error"] = f"{type(exc).__name__}: {exc}"
    return out


# ----------------------------------------------------------------------------
# Finance calculations
# ----------------------------------------------------------------------------
def compute_capital(
    beta_u: float, tax: float, d_share: float, erp: float,
    rf_us: float, spread_usd: float, rf_fc: float,
    spread_fc_manual: float | None = None,
) -> dict:
    """Cost of equity, cost of debt and WACC in USD and the foreign currency."""
    e_share = 1.0 - d_share
    de = d_share / e_share
    beta_l = beta_u * (1.0 + (1.0 - tax) * de)  # Hamada re-levering

    # USD
    ke_usd = rf_us + beta_l * erp
    kd_usd = rf_us + spread_usd
    kd_usd_at = kd_usd * (1.0 - tax)
    wacc_usd = e_share * ke_usd + d_share * kd_usd_at

    # Foreign currency: Fisher / interest-rate-parity style conversion using the
    # government-yield differential as the expected inflation (depreciation) gap.
    factor = (1.0 + rf_fc) / (1.0 + rf_us)
    ke_fc = (1.0 + ke_usd) * factor - 1.0
    kd_fc_auto = (1.0 + kd_usd) * factor - 1.0
    spread_fc_auto = kd_fc_auto - rf_fc
    if spread_fc_manual is None:
        spread_fc, kd_fc = spread_fc_auto, kd_fc_auto
    else:
        spread_fc, kd_fc = spread_fc_manual, rf_fc + spread_fc_manual
    kd_fc_at = kd_fc * (1.0 - tax)
    wacc_fc = e_share * ke_fc + d_share * kd_fc_at

    return {
        "e_share": e_share, "d_share": d_share, "de": de, "beta_u": beta_u,
        "beta_l": beta_l, "tax": tax, "erp": erp,
        "rf_us": rf_us, "rf_fc": rf_fc, "factor": factor, "diff": factor - 1.0,
        "spread_usd": spread_usd, "spread_fc": spread_fc, "spread_fc_auto": spread_fc_auto,
        "ke_usd": ke_usd, "kd_usd": kd_usd, "kd_usd_at": kd_usd_at, "wacc_usd": wacc_usd,
        "ke_fc": ke_fc, "kd_fc": kd_fc, "kd_fc_at": kd_fc_at, "wacc_fc": wacc_fc,
    }


def pct(x: float) -> str:
    return f"{x * 100:.2f}%"


def to_excel_bytes(sheets: dict[str, pd.DataFrame]) -> bytes:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        for name, df in sheets.items():
            df.to_excel(writer, sheet_name=name[:31], index=False)
    return buf.getvalue()


def override_input(
    label: str, fetched: float | None, key: str, *, min_value: float,
    max_value: float, step: float, fallback_default: float, unit: str = "%",
) -> tuple[float, str]:
    """Show a fetched value, or a manual box when overridden / data is missing.

    Values are in display units (percent for rates, plain number for beta).
    """
    missing = fetched is None or (isinstance(fetched, float) and np.isnan(fetched))
    if missing:
        st.warning(f"{label}: fetched value unavailable - please enter it manually.", icon="⚠️")
        use_manual, default = True, fallback_default
    else:
        use_manual = st.toggle(f"Override {label}", key=f"tg_{key}")
        default = float(fetched)
    if use_manual:
        val = st.number_input(
            f"{label} ({unit})" if unit else label,
            min_value=float(min_value), max_value=float(max_value),
            value=float(np.clip(default, min_value, max_value)),
            step=float(step), format="%.2f", key=f"num_{key}",
        )
        return float(val), "Manual"
    st.caption(f"Using fetched: {fetched:.2f}{unit if unit else ''}")
    return float(fetched), "Fetched"


# ----------------------------------------------------------------------------
# Fetch data
# ----------------------------------------------------------------------------
with st.spinner("Fetching the latest data..."):
    beta_res = fetch_damodaran_betas()
    bbb_res = fetch_damodaran_bbb()
    tax_res = fetch_oecd_tax()
    yld_res = fetch_te_yields()

beta_df: pd.DataFrame | None = beta_res["data"]
tax_map: dict[str, float] = tax_res["data"] or {}
yield_map: dict[str, tuple[float, str]] = yld_res["data"] or {}

industries = list(beta_df["Industry"]) if beta_df is not None else [DEFAULT_INDUSTRY]

# Countries: those we can map to a currency and that have any fetched data
available = set(tax_map) | set(yield_map)
countries = sorted(c for c in CURRENCY if (c in available or not available))
if DEFAULT_COUNTRY not in countries:
    countries.insert(0, DEFAULT_COUNTRY)

# ----------------------------------------------------------------------------
# Sidebar
# ----------------------------------------------------------------------------
st.sidebar.title("⚙️ Inputs")
if st.sidebar.button("🔄 Refresh data", use_container_width=True):
    st.cache_data.clear()
    st.rerun()
latest = max([r["retrieved"] for r in (beta_res, bbb_res, tax_res, yld_res)])
st.sidebar.caption(f"Last data fetch: {latest}")

st.sidebar.subheader("Project")
industry = st.sidebar.selectbox(
    "Industry (Damodaran)", industries,
    index=industries.index(DEFAULT_INDUSTRY) if DEFAULT_INDUSTRY in industries else 0,
)
country = st.sidebar.selectbox(
    "Target country", countries,
    index=countries.index(DEFAULT_COUNTRY),
)
erp_pct = st.sidebar.number_input(
    "Equity risk premium (%)", min_value=0.0, max_value=20.0,
    value=DEFAULT_ERP, step=0.05, format="%.2f",
)
debt_pct = st.sidebar.slider("Target debt share of financing (%)", 0, 90, DEFAULT_DEBT, 1)

tax_choice = st.sidebar.radio(
    "Project tax rate to use",
    ["U.S. tax rate", "Selected-country tax rate"],
    horizontal=True,
    help="Switch which corporate tax rate is applied to BOTH the USD and foreign-currency calculations.",
)

is_us = country == "United States"
currency = CURRENCY.get(country, "FCY")

st.sidebar.subheader("Manual overrides")
st.sidebar.caption("Switch a toggle on to overwrite the fetched value.")

beta_fetched = None
if beta_df is not None:
    sel = beta_df.loc[beta_df["Industry"] == industry, "Unlevered beta"]
    beta_fetched = float(sel.iloc[0]) if len(sel) else None

with st.sidebar:
    beta_u, beta_origin = override_input(
        "Unlevered beta", beta_fetched, f"beta_{industry}",
        min_value=0.0, max_value=5.0, step=0.01, fallback_default=1.0, unit="",
    )
    st.divider()
    us_tax_fetched = tax_map.get("United States")
    us_tax_pct, us_tax_origin = override_input(
        "U.S. corporate tax rate",
        us_tax_fetched * 100 if us_tax_fetched is not None else None,
        "tax_us", min_value=0.0, max_value=60.0, step=0.1, fallback_default=25.0,
    )
    st.divider()
    if is_us:
        fc_tax_pct, fc_tax_origin = us_tax_pct, "Same as U.S."
        st.caption("Selected country is the U.S.: country tax rate = U.S. tax rate.")
    else:
        fc_tax_fetched = tax_map.get(country)
        fc_tax_pct, fc_tax_origin = override_input(
            f"{country} corporate tax rate",
            fc_tax_fetched * 100 if fc_tax_fetched is not None else None,
            f"tax_{country}", min_value=0.0, max_value=60.0, step=0.1, fallback_default=25.0,
        )
    st.divider()
    bbb_fetched = bbb_res["data"]
    spread_usd_pct, spread_usd_origin = override_input(
        "USD BBB spread",
        bbb_fetched * 100 if bbb_fetched is not None else None,
        "bbb_usd", min_value=0.0, max_value=20.0, step=0.01, fallback_default=1.0,
    )
    st.divider()
    us_y = yield_map.get("United States")
    rf_us_pct, rf_us_origin = override_input(
        "U.S. 10-year government yield",
        us_y[0] * 100 if us_y else None,
        "y_us", min_value=-2.0, max_value=50.0, step=0.01, fallback_default=4.0,
    )
    st.divider()
    if is_us:
        rf_fc_pct, rf_fc_origin = rf_us_pct, "Same as U.S."
        st.caption("Selected country is the U.S.: foreign yield = U.S. yield.")
    else:
        fc_y = yield_map.get(country)
        rf_fc_pct, rf_fc_origin = override_input(
            f"{country} 10-year government yield",
            fc_y[0] * 100 if fc_y else None,
            f"y_{country}", min_value=-2.0, max_value=100.0, step=0.01,
            fallback_default=rf_us_pct,
        )

    # Auto foreign BBB spread (depends on the inputs resolved above)
    st.divider()
    _auto = compute_capital(
        beta_u, 0.25, debt_pct / 100, erp_pct / 100, rf_us_pct / 100,
        spread_usd_pct / 100, rf_fc_pct / 100,
    )["spread_fc_auto"]
    spread_fc_manual: float | None = None
    spread_fc_origin = "Auto-calculated"
    if is_us:
        st.caption("Foreign BBB spread = USD BBB spread (selected country is the U.S.).")
    else:
        use_fc_spread = st.toggle(f"Override {currency} BBB spread", key=f"tg_bbb_fc_{country}")
        if use_fc_spread:
            spread_fc_manual = st.number_input(
                f"{currency} BBB spread (%)", min_value=0.0, max_value=50.0,
                value=float(np.clip(_auto * 100, 0.0, 50.0)), step=0.01,
                format="%.2f", key=f"num_bbb_fc_{country}",
            ) / 100
            spread_fc_origin = "Manual"
        else:
            st.caption(f"Auto-calculated {currency} BBB spread: {_auto * 100:.2f}%")

# ----------------------------------------------------------------------------
# Calculations
# ----------------------------------------------------------------------------
tax_used_pct = us_tax_pct if tax_choice.startswith("U.S.") else fc_tax_pct
tax_label = "U.S." if tax_choice.startswith("U.S.") else country
tax = tax_used_pct / 100
d_share = debt_pct / 100
erp = erp_pct / 100
rf_us, rf_fc, spread_usd = rf_us_pct / 100, rf_fc_pct / 100, spread_usd_pct / 100

if is_us:
    spread_fc_manual = None

res = compute_capital(beta_u, tax, d_share, erp, rf_us, spread_usd, rf_fc, spread_fc_manual)

# All-industry comparison
rows = []
base = beta_df if beta_df is not None else pd.DataFrame({"Industry": [industry], "Unlevered beta": [beta_u]})
for _, rw in base.iterrows():
    b = beta_u if rw["Industry"] == industry else float(rw["Unlevered beta"])
    r_ = compute_capital(b, tax, d_share, erp, rf_us, spread_usd, rf_fc, spread_fc_manual)
    rows.append({
        "Industry": rw["Industry"],
        "Selected": "✓" if rw["Industry"] == industry else "",
        "Unlevered beta": b,
        "Levered beta": r_["beta_l"],
        "Cost of equity (USD)": r_["ke_usd"] * 100,
        f"Cost of equity ({currency})": r_["ke_fc"] * 100,
        "WACC (USD)": r_["wacc_usd"] * 100,
        f"WACC ({currency})": r_["wacc_fc"] * 100,
    })
all_df = pd.DataFrame(rows)

# Side-by-side table
spec = [
    ("Risk-free rate (10-year government yield)", res["rf_us"], res["rf_fc"], "pct"),
    ("Unlevered beta", res["beta_u"], res["beta_u"], "num"),
    ("Levered beta", res["beta_l"], res["beta_l"], "num"),
    ("Equity risk premium", res["erp"], res["erp"], "pct"),
    ("Cost of equity", res["ke_usd"], res["ke_fc"], "pct"),
    ("BBB credit spread", res["spread_usd"], res["spread_fc"], "pct"),
    ("Pre-tax cost of debt", res["kd_usd"], res["kd_fc"], "pct"),
    ("Project tax rate", res["tax"], res["tax"], "pct"),
    ("After-tax cost of debt", res["kd_usd_at"], res["kd_fc_at"], "pct"),
    ("Equity weight E/V", res["e_share"], res["e_share"], "pct"),
    ("Debt weight D/V", res["d_share"], res["d_share"], "pct"),
    ("WACC", res["wacc_usd"], res["wacc_fc"], "pct"),
]
display_rows, numeric_rows = [], []
for label, u, f, kind in spec:
    if kind == "pct":
        display_rows.append({
            "Item": label, "USD": pct(u), currency: pct(f),
            f"Difference ({currency} - USD)": f"{(f - u) * 100:+.2f} pp",
        })
        numeric_rows.append({"Item": label, "USD": u * 100, currency: f * 100, "Unit": "%"})
    else:
        display_rows.append({
            "Item": label, "USD": f"{u:.3f}", currency: f"{f:.3f}",
            f"Difference ({currency} - USD)": "-",
        })
        numeric_rows.append({"Item": label, "USD": u, currency: f, "Unit": "x"})
disp_df = pd.DataFrame(display_rows)
num_df = pd.DataFrame(numeric_rows)

# Inputs & sources table
def _yield_date(c: str) -> str:
    return yield_map[c][1] if c in yield_map else "n/a"

src_rows = [
    ("Unlevered beta - " + industry, f"{beta_u:.3f}", beta_origin, beta_res["source"], beta_res["as_of"], beta_res["retrieved"], BETA_URL),
    ("U.S. corporate tax rate", f"{us_tax_pct:.2f}%", us_tax_origin, tax_res["source"], tax_res["as_of"], tax_res["retrieved"], OECD_URL),
    (f"{country} corporate tax rate", f"{fc_tax_pct:.2f}%", fc_tax_origin, tax_res["source"], tax_res["as_of"], tax_res["retrieved"], OECD_URL),
    ("USD BBB (Baa2) spread", f"{spread_usd_pct:.2f}%", spread_usd_origin, bbb_res["source"], bbb_res["as_of"], bbb_res["retrieved"], BBB_URL),
    ("U.S. 10-year yield", f"{rf_us_pct:.2f}%", rf_us_origin, yld_res["source"], f"quote date: {_yield_date('United States')}", yld_res["retrieved"], TE_URL),
    (f"{country} 10-year yield", f"{rf_fc_pct:.2f}%", rf_fc_origin, yld_res["source"], f"quote date: {_yield_date(country)}", yld_res["retrieved"], TE_URL),
    (f"{currency} BBB spread", f"{res['spread_fc'] * 100:.2f}%", spread_fc_origin, "Derived from USD BBB spread and yield differential (or manual)", "n/a", "n/a", "-"),
]
src_df = pd.DataFrame(
    src_rows,
    columns=["Input", "Value used", "Origin", "Source", "Data date", "Retrieved", "URL"],
)

# ----------------------------------------------------------------------------
# Main page
# ----------------------------------------------------------------------------
st.title("🌍 International Cost of Capital")
st.markdown(
    f"**{industry}** project in **{country}** ({currency}) vs. the U.S. (USD)  |  "
    f"tax rate: **{tax_label} {tax_used_pct:.2f}%**  |  debt share: **{debt_pct}%**  |  "
    f"ERP: **{erp_pct:.2f}%**"
)

failed = [r for r in (beta_res, bbb_res, tax_res, yld_res) if not r["ok"]]
if failed:
    st.warning(
        "Some data could not be fetched automatically: "
        + "; ".join(r["source"].split(" - ")[0] + " - " + (r["error"] or "") for r in failed)
        + ". Manual boxes are shown in the sidebar for any missing inputs. Try 'Refresh data'.",
        icon="⚠️",
    )

tab_res, tab_all, tab_assump, tab_src = st.tabs(
    ["📊 Results", "🏭 All industries", "📝 Assumptions & formulas", "🔗 Data sources"]
)

with tab_res:
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("🇺🇸 USD - United States")
        m1, m2 = st.columns(2)
        m1.metric("Cost of equity", pct(res["ke_usd"]))
        m2.metric("WACC", pct(res["wacc_usd"]))
        m3, m4 = st.columns(2)
        m3.metric("Pre-tax cost of debt", pct(res["kd_usd"]))
        m4.metric("After-tax cost of debt", pct(res["kd_usd_at"]))
    with c2:
        st.subheader(f"🌐 {currency} - {country}")
        m1, m2 = st.columns(2)
        m1.metric("Cost of equity", pct(res["ke_fc"]),
                  delta=f"{(res['ke_fc'] - res['ke_usd']) * 100:+.2f} pp vs USD", delta_color="off")
        m2.metric("WACC", pct(res["wacc_fc"]),
                  delta=f"{(res['wacc_fc'] - res['wacc_usd']) * 100:+.2f} pp vs USD", delta_color="off")
        m3, m4 = st.columns(2)
        m3.metric("Pre-tax cost of debt", pct(res["kd_fc"]),
                  delta=f"{(res['kd_fc'] - res['kd_usd']) * 100:+.2f} pp vs USD", delta_color="off")
        m4.metric("After-tax cost of debt", pct(res["kd_fc_at"]),
                  delta=f"{(res['kd_fc_at'] - res['kd_usd_at']) * 100:+.2f} pp vs USD", delta_color="off")

    st.markdown("#### Side-by-side detail")
    st.dataframe(disp_df, hide_index=True, use_container_width=True)
    st.caption(
        f"Implied {currency}/USD expected-inflation (depreciation) differential from the yield gap: "
        f"{res['diff'] * 100:+.2f}%.  D/E used to re-lever beta: {res['de']:.3f}."
    )

    d1, d2 = st.columns(2)
    csv_bytes = num_df.to_csv(index=False).encode("utf-8")
    d1.download_button(
        "⬇️ Download results (CSV)", csv_bytes, "cost_of_capital_results.csv",
        "text/csv", use_container_width=True,
    )
    xlsx_bytes = to_excel_bytes({
        "Selected project": num_df, "Inputs & sources": src_df, "All industries": all_df,
    })
    d2.download_button(
        "⬇️ Download full workbook (Excel)", xlsx_bytes, "cost_of_capital_results.xlsx",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
    )

with tab_all:
    st.markdown(
        f"All industries use the same tax rate ({tax_label}, {tax_used_pct:.2f}%), debt share, ERP, "
        "yields and spreads as above. A manual beta override applies only to the selected industry."
    )
    pct_cfg = st.column_config.NumberColumn(format="%.2f%%")
    st.dataframe(
        all_df, hide_index=True, use_container_width=True,
        column_config={
            "Unlevered beta": st.column_config.NumberColumn(format="%.3f"),
            "Levered beta": st.column_config.NumberColumn(format="%.3f"),
            "Cost of equity (USD)": pct_cfg,
            f"Cost of equity ({currency})": pct_cfg,
            "WACC (USD)": pct_cfg,
            f"WACC ({currency})": pct_cfg,
        },
    )
    if len(all_df) > 1:
        chart_df = (
            all_df.sort_values(f"WACC ({currency})", ascending=False)
            .set_index("Industry")[["WACC (USD)", f"WACC ({currency})"]]
        )
        st.markdown("#### WACC by industry (%)")
        st.bar_chart(chart_df, height=480)
    st.download_button(
        "⬇️ Download all-industry comparison (CSV)",
        all_df.to_csv(index=False).encode("utf-8"),
        "cost_of_capital_all_industries.csv", "text/csv",
    )

with tab_assump:
    st.markdown("### Main assumptions")
    st.markdown(
        f"""
- **Same project inputs in both currencies:** one tax rate (**{tax_label}**, {tax_used_pct:.2f}%),
  one target debt share ({debt_pct}%), and one equity risk premium ({erp_pct:.2f}%).
- **Beta:** the industry *unlevered* beta is re-levered at the target capital structure using the
  project tax rate: D/E = D/V ÷ E/V.
- **USD side:** risk-free rate = U.S. 10-year government yield; cost of debt = U.S. 10-year yield +
  Baa2/BBB spread for large non-financial service firms.
- **Foreign-currency side:** USD costs are converted with the yield differential, a Fisher /
  interest-rate-parity style relation. The 10-year yield gap is used as a proxy for the expected
  inflation (depreciation) difference between the two currencies.
- **Foreign BBB spread (auto):** the pre-tax USD cost of debt is converted with the same factor and the
  local 10-year yield is subtracted. You can overwrite it manually.
- **Tax shield:** the same project tax rate is applied to interest in both currencies.
- **Data caveat:** the OECD rate is the latest statutory (combined central + sub-central) rate in the
  report; Damodaran data is updated periodically (not daily); yields are the latest quotes on
  Trading Economics. Overrides always take priority over fetched values.
        """
    )
    st.markdown("### Formulas")
    st.latex(r"\beta_L=\beta_U\left[1+(1-t)\frac{D}{E}\right],\qquad \frac{D}{E}=\frac{D/V}{1-D/V}")
    st.latex(r"k_e^{USD}=r_f^{US}+\beta_L\times ERP")
    st.latex(r"k_d^{USD}=r_f^{US}+s_{BBB},\qquad k_d^{USD,AT}=k_d^{USD}(1-t)")
    st.latex(r"WACC^{USD}=\frac{E}{V}k_e^{USD}+\frac{D}{V}k_d^{USD}(1-t)")
    st.latex(r"1+k^{FC}=(1+k^{USD})\times\frac{1+y^{FC}}{1+y^{US}}\quad(\text{for } k_e \text{ and } k_d)")
    st.latex(r"s_{BBB}^{FC}=k_d^{FC}-y^{FC}=s_{BBB}^{USD}\times\frac{1+y^{FC}}{1+y^{US}}")
    st.latex(r"WACC^{FC}=\frac{E}{V}k_e^{FC}+\frac{D}{V}k_d^{FC}(1-t)")
    st.markdown(
        "If you overwrite the foreign BBB spread, the foreign pre-tax cost of debt becomes "
        "*local 10-year yield + manual spread*. Please verify that these formulas match those given in class."
    )

with tab_src:
    st.markdown("### Inputs used, sources and dates")
    st.dataframe(
        src_df, hide_index=True, use_container_width=True,
        column_config={"URL": st.column_config.LinkColumn("URL")},
    )
    st.markdown("### Fetch status")
    for r in (beta_res, bbb_res, tax_res, yld_res):
        label = f"{r['source']} - data date: {r['as_of']} - retrieved {r['retrieved']}"
        if r["ok"]:
            st.success(label, icon="✅")
        else:
            st.error(f"{r['source']} - failed: {r['error']}", icon="❌")
    st.caption(
        "Use the 'Refresh data' button in the sidebar to clear the cache and re-fetch every source. "
        "Data is cached for 6 hours otherwise."
    )

st.divider()
st.caption(
    "For educational use. Always verify inputs and calculations against the original sources "
    "before relying on the results."
)
