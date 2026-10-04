import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from src import ui
from src.analysis import analyze
from src.dividends import project_income
from src.fmp import FMPError, RateLimitError, SymbolNotFound
from src.store import upsert
from src.ui import chip, fmt_big, fmt_money, fmt_num, fmt_pct
from src.valuation import Assumptions, dcf_value

st.set_page_config(page_title="Company", page_icon="🏢", layout="wide")
client = ui.sidebar_api()

with st.sidebar.expander("Valuation assumptions"):
    rf = st.slider("Risk-free rate (%)", 2.0, 6.0, 4.3, 0.1) / 100
    erp = st.slider("Equity risk premium (%)", 3.0, 8.0, 5.0, 0.1) / 100
    tg = st.slider("Terminal growth (%)", 1.0, 4.0, 2.5, 0.1) / 100
    buy_margin = st.slider("Margin of safety wanted (%)", 0, 40, 20, 5) / 100
assumptions = Assumptions(risk_free=rf, equity_risk_premium=erp, terminal_growth=tg, buy_margin=buy_margin)

st.title("🏢 Company analysis")
with st.form("ticker"):
    c1, c2 = st.columns([4, 1])
    sym = c1.text_input("US ticker", value=st.session_state.get("symbol", "AAPL")).upper().strip()
    submitted = c2.form_submit_button("Analyse", type="primary", width="stretch")
if client is None:
    st.info("Add your FMP API key in the sidebar.")
    st.stop()
st.session_state["symbol"] = sym

try:
    a = analyze(client, sym, deep=True, assumptions=assumptions)
except SymbolNotFound as e:
    st.error(str(e))
    st.stop()
except (RateLimitError, FMPError) as e:
    st.error(str(e))
    st.stop()

c, m, v, d, ins = a.company, a.metrics, a.valuation, a.dividend, a.insights
upsert([a.to_row()])  # keep the screener table in sync

# ---------------------------------------------------------------------- header
st.header(f"{c.name} ({c.symbol})")
st.caption(f"{c.sector} · {c.industry} · {c.profile.get('exchangeFullName', c.profile.get('exchange', ''))} · Market cap {fmt_big(c.market_cap)}")
k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("Price", fmt_money(m["price"]))
k2.metric("Fair value (median of models)", fmt_money(v["fair_value"]), fmt_pct(v["upside"]) if v["upside"] is not None else None)
k3.metric("Valuation verdict", v["verdict"])
k4.metric("Overall rating", a.overall["rating"], f"score {fmt_num(a.overall['score'], 0)}" if a.overall["score"] is not None else None)
k5.metric("Dividend yield", fmt_pct(d.get("yield_ttm")) if d.get("payer") else "None")

tab_sum, tab_val, tab_fin, tab_div, tab_fc, tab_raw = st.tabs(
    ["Summary", "Valuation", "Financials", "Dividends", "Earnings forecast", "All metrics"]
)

# --------------------------------------------------------------------- summary
with tab_sum:
    left, right = st.columns([1, 1])
    with left:
        st.subheader("Factor grades")
        rows = "".join(
            f"<tr><td style='padding:4px 12px 4px 0'>{f}</td><td>{chip(g['grade'])}</td>"
            f"<td style='padding-left:12px;color:#888'>{fmt_num(g['score'], 0)} · {g['n_metrics']} metrics</td></tr>"
            for f, g in a.grades.items()
        )
        st.markdown(f"<table>{rows}</table>", unsafe_allow_html=True)
        st.markdown(f"**Overall:** {chip(a.overall['grade'])}", unsafe_allow_html=True)
        scored = {f: g["score"] for f, g in a.grades.items() if g["score"] is not None}
        if len(scored) >= 3:
            fig = go.Figure(go.Scatterpolar(r=list(scored.values()) + [list(scored.values())[0]],
                                            theta=list(scored) + [list(scored)[0]], fill="toself"))
            fig.update_layout(polar=dict(radialaxis=dict(range=[0, 100])), height=330, margin=dict(t=20, b=20), showlegend=False)
            st.plotly_chart(fig, width="stretch")
    with right:
        st.subheader(f"Suggestion: {ins['action']}")
        st.info(ins["suggestion"])
        st.markdown("**Checklist**")
        for name, ok, detail in ins["checklist"]:
            st.write(f"{'✅' if ok else '❌'} {name} · _{detail}_")
    g_col, r_col = st.columns(2)
    with g_col:
        st.markdown("**Green flags**")
        for t in ins["green"] or ["None detected."]:
            st.write(f"🟢 {t}")
    with r_col:
        st.markdown("**Red flags**")
        for t in ins["red"] or ["None detected."]:
            st.write(f"🔴 {t}")
    for n in ins["notes"]:
        st.caption(n)
    if c.profile.get("description"):
        with st.expander("About the company"):
            st.write(c.profile["description"])

# ------------------------------------------------------------------- valuation
with tab_val:
    if not v["models"] or v["fair_value"] is None:
        st.warning("Not enough data to value this company (needs positive EPS or free cash flow).")
    else:
        st.subheader(f"Fair value {fmt_money(v['fair_value'])}  (range {fmt_money(v['fair_low'])} – {fmt_money(v['fair_high'])}, confidence {v['confidence']})")
        st.caption(f"Entry price with a {buy_margin:.0%} margin of safety: **{fmt_money(v['entry_price'])}**")
        md = pd.DataFrame(v["models"]).dropna(subset=["value"])
        ref = []
        if v["graham_number"]:
            ref.append({"model": "Graham number (reference)", "value": v["graham_number"]})
        if v["analyst_target"]:
            ref.append({"model": "Analyst consensus target (reference)", "value": v["analyst_target"]})
        plot = pd.concat([md[["model", "value"]], pd.DataFrame(ref)], ignore_index=True)
        fig = px.bar(plot, x="value", y="model", orientation="h", text=plot["value"].map(lambda x: f"${x:,.0f}"))
        fig.add_vline(x=m["price"], line_dash="dash", line_color="red", annotation_text=f"Price {fmt_money(m['price'])}")
        fig.add_vline(x=v["fair_value"], line_color="green", annotation_text="Fair value", annotation_position="bottom")
        fig.update_layout(height=320, yaxis_title=None, xaxis_title="Value per share ($)", margin=dict(t=30, b=10))
        st.plotly_chart(fig, width="stretch")
        md["upside"] = md["upside"].map(fmt_pct)
        md["value"] = md["value"].map(fmt_money)
        st.dataframe(md.rename(columns={"model": "Model", "value": "Value/share", "upside": "vs price"}), hide_index=True, width="stretch")

        a1, a2, a3, a4 = st.columns(4)
        a1.metric("Growth used (stage 1)", fmt_pct(v["growth"]), help=v["growth_source"])
        a2.metric("Discount rate (CAPM)", fmt_pct(v["discount_rate"]))
        a3.metric("Terminal growth", fmt_pct(v["terminal_growth"]))
        a4.metric("Growth implied by price", fmt_pct(v["implied_growth"]), help="Reverse DCF: FCF growth for 5 years that justifies today's price.")

        if v["base_fcf"] and v["growth"] is not None:
            st.markdown("**DCF sensitivity** (value per share)")
            rates = [v["discount_rate"] + x for x in (-0.02, -0.01, 0, 0.01, 0.02)]
            grows = [v["growth"] + x for x in (-0.04, -0.02, 0, 0.02, 0.04)]
            grid = pd.DataFrame(
                [[dcf_value(v["base_fcf"], c.shares, g, r, v["terminal_growth"]) for g in grows] for r in rates],
                index=[f"{r:.1%}" for r in rates], columns=[f"{g:.1%}" for g in grows],
            )
            fig = px.imshow(grid, text_auto=".0f", aspect="auto", color_continuous_scale="RdYlGn", color_continuous_midpoint=m["price"],
                            labels=dict(x="Stage-1 growth", y="Discount rate"))
            fig.update_layout(height=300, margin=dict(t=10, b=10), coloraxis_showscale=False)
            st.plotly_chart(fig, width="stretch")
            st.caption("Green cells are worth more than today's price, red cells less.")
            with st.expander("DCF cash-flow schedule"):
                sch = pd.DataFrame(v["schedule"])
                st.dataframe(sch.assign(growth=sch["growth"].map(fmt_pct), fcf=sch["fcf"].map(fmt_big), pv=sch["pv"].map(fmt_big)),
                             hide_index=True, width="stretch")
    mult = {"P/E": m["pe"], "Forward P/E": m["fwd_pe"], "PEG": m["peg"], "P/S": m["ps"], "P/B": m["pb"], "P/FCF": m["p_fcf"],
            "EV/EBITDA": m["ev_ebitda"], "FCF yield": fmt_pct(m["fcf_yield"]), "Earnings yield": fmt_pct(m["earnings_yield"])}
    st.markdown("**Valuation multiples**")
    st.dataframe(pd.DataFrame({"Metric": list(mult), "Value": [x if isinstance(x, str) else fmt_num(x) for x in mult.values()]}).T,
                 width="stretch")

# ------------------------------------------------------------------- financials
with tab_fin:
    inc = pd.DataFrame(c.income)[::-1] if c.income else pd.DataFrame()
    cf = pd.DataFrame(c.cashflow)[::-1] if c.cashflow else pd.DataFrame()
    if inc.empty:
        st.warning("No statement data available.")
    else:
        hist = pd.DataFrame({"year": inc["date"].str[:4]})
        for col in ("revenue", "netIncome", "operatingIncome", "grossProfit"):
            hist[col] = inc.get(col)
        if not cf.empty and "freeCashFlow" in cf:
            hist["freeCashFlow"] = cf["freeCashFlow"].values[-len(hist):] if len(cf) >= len(hist) else None
        long = hist.melt("year", value_vars=[x for x in ("revenue", "operatingIncome", "netIncome", "freeCashFlow") if x in hist],
                         var_name="item", value_name="usd")
        fig = px.bar(long, x="year", y="usd", color="item", barmode="group")
        fig.update_layout(height=340, margin=dict(t=10), yaxis_title="USD")
        st.plotly_chart(fig, width="stretch")
        marg = pd.DataFrame({"year": hist["year"],
                             "Gross margin": hist["grossProfit"] / hist["revenue"],
                             "Operating margin": hist["operatingIncome"] / hist["revenue"],
                             "Net margin": hist["netIncome"] / hist["revenue"]}).melt("year", var_name="margin", value_name="v")
        fig = px.line(marg, x="year", y="v", color="margin", markers=True)
        fig.update_layout(height=300, yaxis_tickformat=".0%", yaxis_title=None, margin=dict(t=10))
        st.plotly_chart(fig, width="stretch")
    q1, q2, q3 = st.columns(3)
    q1.metric("Revenue CAGR (3y)", fmt_pct(m["rev_cagr_3y"]))
    q1.metric("EPS CAGR (3y)", fmt_pct(m["eps_cagr_3y"]))
    q2.metric("ROIC", fmt_pct(m["roic"]))
    q2.metric("ROE", fmt_pct(m["roe"]))
    q3.metric("Debt / equity", fmt_num(m["debt_to_equity"]))
    q3.metric("Net debt / EBITDA", fmt_num(m["net_debt_ebitda"]))

# -------------------------------------------------------------------- dividends
with tab_div:
    if not d.get("payer"):
        st.info("This company does not currently pay a dividend (none in the last 12 months).")
    else:
        st.subheader("Dividend grades")
        cols = st.columns(4)
        for col, (name, g) in zip(cols, d["grades"].items()):
            col.markdown(f"**{name}**<br>{chip(g['grade'])}", unsafe_allow_html=True)
        s1, s2, s3, s4, s5 = st.columns(5)
        s1.metric("Yield (TTM)", fmt_pct(d["yield_ttm"], 2))
        s2.metric("Forward yield", fmt_pct(d["yield_fwd"], 2))
        s3.metric("Annual dividend (fwd)", fmt_money(d["forward_dividend"]))
        s4.metric("Payments / year", d["frequency"] or "—")
        s5.metric("Last change", fmt_pct(d["last_change_pct"]))
        t1, t2, t3, t4, t5 = st.columns(5)
        t1.metric("Payout (earnings)", fmt_pct(d["payout_eps"], 0))
        t2.metric("Payout (free cash flow)", fmt_pct(d["payout_fcf"], 0))
        t3.metric("5y dividend CAGR", fmt_pct(d["cagr_5y"]))
        t4.metric("3y dividend CAGR", fmt_pct(d["cagr_3y"]))
        t5.metric("Years raised / no cut", f"{d['years_growth']} / {d['years_no_cut']}",
                  help="Limited to the dividend history your FMP plan returns.")
        if d["annual"]:
            ann = pd.DataFrame({"year": list(d["annual"]), "dividend": list(d["annual"].values())})
            ann["growth"] = ann["dividend"].pct_change()
            fig = px.bar(ann, x="year", y="dividend", text=ann["dividend"].map(lambda x: f"${x:.2f}"))
            fig.update_layout(height=320, margin=dict(t=10), yaxis_title="Dividends per share")
            st.plotly_chart(fig, width="stretch")
        st.markdown("**Income projection** (no reinvestment, dividend grows at the historical CAGR)")
        p1, p2 = st.columns(2)
        n_sh = p1.number_input("Shares owned", 1, 1_000_000, 100)
        gr = p2.slider("Annual dividend growth (%)", 0.0, 15.0, float((d["cagr_5y"] or d["cagr_3y"] or 0.03) * 100), 0.5) / 100
        proj = pd.DataFrame(project_income(n_sh, m["price"], d["yield_ttm"], gr, 10))
        fig = px.line(proj, x="year", y="annual_income", markers=True)
        fig.update_layout(height=280, margin=dict(t=10), xaxis_title="Years from now", yaxis_title="Annual dividend income ($)")
        st.plotly_chart(fig, width="stretch")
        st.caption(f"Yield on cost after 10 years: {fmt_pct(proj['yield_on_cost'].iloc[-1])}")

# --------------------------------------------------------------------- forecast
with tab_fc:
    fc = a.forecast
    if fc.empty:
        st.warning("No forecast data available.")
    else:
        if not (fc["kind"] == "analyst").any():
            st.warning("No analyst estimates returned (may be outside the free plan); showing historical data and a fade extrapolation.")
        e1, e2 = st.columns(2)
        for col, key, title in ((e1, "eps", "EPS (diluted)"), (e2, "revenue", "Revenue")):
            fig = px.bar(fc, x="year", y=key, color="kind", title=title,
                         color_discrete_map={"actual": "#4c78a8", "analyst": "#f58518", "extrapolated": "#bab0ac"})
            fig.update_layout(height=320, margin=dict(t=40))
            col.plotly_chart(fig, width="stretch")
        show = fc.copy()
        for col in ("revenue", "net_income"):
            show[col] = show[col].map(fmt_big)
        for col in ("revenue_growth", "eps_growth"):
            show[col] = show[col].map(fmt_pct)
        for col in ("eps", "eps_low", "eps_high"):
            show[col] = show[col].map(fmt_money)
        st.dataframe(show.drop(columns=["analysts"], errors="ignore"), hide_index=True, width="stretch")
        f1, f2, f3 = st.columns(3)
        f1.metric("Forward P/E", fmt_num(m["fwd_pe"]))
        f2.metric("Fwd EPS CAGR (analysts)", fmt_pct(m["fwd_eps_growth"]))
        f3.metric("Next earnings date", str(a.next_earnings) if a.next_earnings else "—")
    if not a.surprises.empty:
        st.subheader("Earnings surprises")
        sur = a.surprises.head(12).copy()
        fig = px.bar(sur, x="date", y="surprise_pct", color="beat", color_discrete_map={True: "#1b9e4b", False: "#d32f2f"})
        fig.update_layout(height=260, yaxis_tickformat=".0%", showlegend=False, margin=dict(t=10), yaxis_title="EPS surprise")
        st.plotly_chart(fig, width="stretch")
        sur["surprise_pct"] = sur["surprise_pct"].map(fmt_pct)
        st.dataframe(sur, hide_index=True, width="stretch")
        st.caption(f"Beat rate (last up to 8 quarters): {fmt_pct(m['eps_beat_rate'], 0)}")

# --------------------------------------------------------------------- all data
with tab_raw:
    dfm = pd.DataFrame({"metric": list(m), "value": [m[k] for k in m]})
    st.dataframe(dfm, hide_index=True, width="stretch", height=600)
st.caption(ui.DISCLAIMER)
