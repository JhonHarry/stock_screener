# Valuation Screener

A free, open-source stock analysis tool inspired by Seeking Alpha: find quality companies and check whether the price is good.
Built with Streamlit and the [Financial Modeling Prep](https://site.financialmodelingprep.com/) (FMP) free API.

> Educational tool, not investment advice. Free-plan data can be incomplete; always verify against company filings.

## Features

- **Screener**: rank many stocks, filter by sector, score, upside, yield, forward P/E; presets for *Undervalued quality*, *Dividend growth*, *GARP*, *Deep value*.
- **Factor grades (A+ to F)**: Valuation, Growth, Profitability, Financial Health, Momentum and Analyst Outlook, plus an overall rating (Strong Buy to Strong Sell).
- **Fair value**: median of a 10-year DCF, Graham growth formula, 5-year EPS x exit P/E, and a dividend-discount model; margin of safety, entry price, DCF sensitivity table, and a reverse DCF (growth implied by the price).
- **Dividends tab**: yield, forward yield, payout vs earnings and FCF, 3/5-year CAGR, raise streak, Safety / Growth / Yield / Consistency grades, income projection.
- **Earnings forecast tab**: actuals, analyst consensus, fade extrapolation, forward P/E, EPS surprise history, next earnings date.
- **Extras**: green/red flags (earnings quality, dilution, leverage, payout risk, moat proxy), buy checklist, plain-language suggestion.
- **GitHub-native updates**: a scheduled Action refreshes `data/results.csv` on weekdays, so the repo history tracks your screener over time.

## Quick start

```bash
git clone https://github.com/<you>/valuation-screener.git
cd valuation-screener
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                                   # put your free FMP key in it
streamlit run app.py
```

Get a free key at <https://site.financialmodelingprep.com/register> (no card needed, 250 calls/day).

## API budget (free plan)

A lean analysis costs about 7 calls, a deep one about 10. Responses are cached in `data/cache.sqlite`
(profile and statements 7 days, ratios 1 day, estimates 3 days), and the client stops at 240 calls/day. In practice:
analyse a few dozen tickers a day, and let the scheduled job slowly cover `data/universe.csv` (about 100 large caps; edit it freely).

```bash
python -m src.cli refresh --max 25     # analyse the 25 stalest tickers
python -m src.cli analyze KO PEP       # specific tickers
python -m src.cli usage
```

## Automatic updates on GitHub

1. Repo **Settings > Secrets and variables > Actions > New repository secret**: name `FMP_API_KEY`.
2. The **Refresh screener data** workflow runs each weekday (or manually under *Actions*) and commits `data/results.csv`.
3. **CI** runs the test-suite on every push.

## Project layout

```
app.py, pages/        Streamlit UI (Home, Screener, Company, Methodology)
src/fmp.py            FMP client: SQLite cache, daily budget, graceful 402/403 handling
src/metrics.py        raw statements -> metrics         src/scoring.py     factor grades
src/valuation.py      DCF / Graham / DDM / reverse DCF  src/dividends.py   dividend analytics
src/forecast.py       forecast + surprises              src/insights.py    flags, checklist, suggestion
src/analysis.py       orchestration                     src/store.py       results.csv store
tests/                unit + Streamlit smoke tests (no network)
```

## Honest limitations

- Grades use absolute thresholds, not Seeking Alpha's proprietary sector-relative model. Tune anchors in `src/scoring.py`.
- Some endpoints (analyst estimates, long history) may be limited on the free plan; missing data is skipped, never invented.
- Field names follow FMP's `/stable` API. If FMP renames a field, adjust the aliases in `src/metrics.py`.
- Financial companies (banks, insurers) need different metrics; debt ratios and FCF models are less meaningful for them.

## Ideas / roadmap

Sector-relative percentiles once enough stocks are stored, EPS revision history (needs a paid feed), peer comparison,
portfolio tracker, price/valuation alerts by email, SEC filings red-flag scan.

## License

MIT
