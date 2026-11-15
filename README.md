# 🌍 International Cost of Capital App

A Streamlit app that compares a project's **cost of equity, cost of debt and WACC in USD and in the currency of any selected country**, using the same project tax rate, debt share and equity risk premium in both currencies.

Compatible with **Python 3.12**.

## Features

- **Live data with a refresh button** (cached for 6 hours; the sidebar button clears the cache and re-fetches):
  - U.S. industry **unlevered betas** – [Damodaran `betas.xls`](https://pages.stern.nyu.edu/~adamodar/pc/datasets/betas.xls)
  - **BBB (Baa2) USD borrowing spread** for large non-financial service firms – [Damodaran ratings page](https://pages.stern.nyu.edu/adamodar/New_Home_Page/datafile/ratings.html)
  - **Corporate tax rates** – [OECD Corporate Tax Statistics 2024](https://www.oecd.org/en/publications/corporate-tax-statistics-2024_9c27d6e8-en/full-report/statutory-corporate-income-tax-rates_440f9286.html)
  - **10-year government bond yields** (U.S. and selected country) – [Trading Economics](https://tradingeconomics.com/bonds) (scraped, no API key)
- Sources, data dates and retrieval timestamps are shown in the **Data sources** tab.
- Select an **industry** and **target country**; adjust the **equity risk premium** and **target debt share**.
- **Manual overrides** (toggle switches) for the unlevered beta, U.S. tax rate, selected-country tax rate, USD BBB spread, U.S. 10-year yield and selected-country 10-year yield. The foreign-currency BBB spread can also be overridden; when the override is off, the auto-calculated value is displayed.
- **Tax-rate switch** between the U.S. and the selected-country corporate tax rate (applied to both currencies).
- **Side-by-side results**, explanation of assumptions and formulas, and an **all-industry comparison** (table + chart).
- **Downloads:** CSV (selected project, all industries) and a full Excel workbook.
- **Defaults on open:** Software (System & Application), United States as the selected country, U.S. tax rate, 6.5% equity risk premium, 30% debt financing.
- Purple-themed interface.

## Methodology

1. Re-lever the industry unlevered beta: `βL = βU × [1 + (1 − t) × D/E]`, with `D/E = (D/V) / (1 − D/V)`.
2. **USD:**
   - `Ke = rf(US) + βL × ERP`
   - `Kd = rf(US) + BBB spread`, after-tax `Kd × (1 − t)`
   - `WACC = E/V × Ke + D/V × Kd × (1 − t)`
3. **Foreign currency** (Fisher / interest-rate-parity style conversion using the 10-year yield differential as the expected inflation / depreciation gap):
   - `1 + K(FC) = (1 + K(USD)) × (1 + y(FC)) / (1 + y(US))` for both cost of equity and (auto) pre-tax cost of debt
   - Auto foreign BBB spread `= Kd(FC) − y(FC) = USD spread × (1 + y(FC)) / (1 + y(US))`
   - If the foreign BBB spread is overridden: `Kd(FC) = y(FC) + manual spread`
   - `WACC(FC) = E/V × Ke(FC) + D/V × Kd(FC) × (1 − t)`

> ⚠️ These formulas follow the standard approach; **verify them against the formulas given in class** and check the numbers independently before submitting.

## Project structure

```
.
├── app.py
├── requirements.txt
└── README.md
```

## Run locally

```bash
python3.12 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

## Deploy on Streamlit Community Cloud

1. Push `app.py`, `requirements.txt` and `README.md` to a GitHub repository.
2. Go to <https://share.streamlit.io>, sign in with GitHub and click **Create app**.
3. Choose the repository and branch, and set **Main file path** to `app.py`.
4. Under **Advanced settings**, choose **Python 3.12**, then click **Deploy**.

### Optional: force a purple theme

The app already injects CSS for a purple background. To also make Streamlit's own theme match, add `.streamlit/config.toml`:

```toml
[theme]
base = "dark"
primaryColor = "#c084fc"
backgroundColor = "#3b0f70"
secondaryBackgroundColor = "#5b21b6"
textColor = "#f5f0ff"
```

## Notes and limitations

- **Scraping can break.** The OECD, Damodaran and Trading Economics pages are HTML/Excel files that can change layout or block automated requests. If a fetch fails, the app tells you which one and shows a manual input for the missing value. Press **Refresh data** to retry.
- **Country coverage** depends on the OECD table and Trading Economics' bond page. If a country is missing a tax rate or yield, enter it manually. Country-to-currency mapping is built into `app.py` (`CURRENCY` dictionary); add entries to extend it.
- **Tax rates** are OECD statutory rates (combined central + sub-central) from the latest year available in the report (2024 edition).
- **Damodaran data** is updated periodically (typically each January), not daily. The industry list excludes the "Total Market" rows.
- The 10-year yield differential is a simple proxy for expected inflation/currency differences. It is not a forecast of exchange rates.
- Eurozone countries all use EUR but have different government yields; the selected country's own yield is used.
- For educational use only; not investment advice.

## Troubleshooting

- `xlrd` is required to read the old-format `betas.xls`; `lxml` is required for `pandas.read_html`. Both are in `requirements.txt`.
- HTTP 403 on OECD / Trading Economics is common when the app runs on a cloud host (these sites block data-center IPs, and Trading Economics also loads its tables with JavaScript). The app first tries a direct request, then retries through the free [r.jina.ai](https://r.jina.ai) reader, which renders the page and returns the tables as text. If both fail, press **Refresh data** later or use the manual overrides (and the built-in approximate OECD tax fallback).
