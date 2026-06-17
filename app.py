"""
Streamlit-App: Backtest Altersvorsorge für Profi-Fußballer (Sommerprämie).

Start lokal:
    streamlit run app.py
"""

from __future__ import annotations
import io
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

from backtest import (
    build_returns, available_period,
    SimulationParams, run_rolling_backtest,
    summary_metrics, equity_percentiles, safe_withdrawal_rate,
)


# ──────────────────────────────────────────────────────────────────────
# PAGE CONFIG
# ──────────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Vorsorge-Backtest Profisportler",
    page_icon="⚽",
    layout="wide",
)

st.title("⚽ Vorsorge-Backtest für Profi-Fußballer")
st.caption("Historischer Rolling-Backtest auf Basis monatlicher Total-Return-Daten (EUR) "
           "für Ansparphase + Entsparphase")


# ──────────────────────────────────────────────────────────────────────
# DATEN LADEN (cached)
# ──────────────────────────────────────────────────────────────────────
DEFAULT_DATA = Path(__file__).parent / "data" / "Daten_Verrentung_EUR.xlsx"


@st.cache_data(show_spinner=False)
def load_data(path: str, cash_yield: float):
    return build_returns(path, cash_annual_yield=cash_yield)


@st.cache_data(show_spinner=False)
def load_data_from_bytes(file_bytes: bytes, cash_yield: float):
    bio = io.BytesIO(file_bytes)
    return build_returns(bio, cash_annual_yield=cash_yield)


# ──────────────────────────────────────────────────────────────────────
# SIDEBAR – PARAMETER
# ──────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("📊 Datenquelle")
    uploaded = st.file_uploader("Eigene Excel hochladen (optional)",
                                 type=["xlsx"],
                                 help="Format wie Daten_Verrentung_EUR.xlsx")
    cash_yield = st.number_input("Cash-Verzinsung p.a. (nominal)",
                                  min_value=0.0, max_value=0.10,
                                  value=0.02, step=0.005, format="%.3f")

    st.divider()
    st.header("👤 Karriereprofil")
    start_age = st.number_input("Karrierestart (Alter)",
                                min_value=15, max_value=30, value=18)
    end_career_age = st.number_input("Karriereende (Alter)",
                                      min_value=start_age+1, max_value=45,
                                      value=35)
    end_age = st.number_input("Endalter (Lebensende-Szenario)",
                               min_value=end_career_age+1, max_value=100,
                               value=85)

    st.divider()
    st.header("💰 Ansparphase")
    annual_contribution = st.number_input("Jährliche Sommerprämie (€)",
                                           min_value=0, max_value=2_000_000,
                                           value=120_000, step=10_000)
    contribution_indexed = st.checkbox("Sparrate mit Inflation steigern",
                                        value=False)

    st.divider()
    st.header("🏖️ Entsparphase")
    monthly_withdrawal = st.number_input("Monatliche Entnahme (€)",
                                          min_value=0, max_value=100_000,
                                          value=8_000, step=500)
    withdrawal_indexed = st.checkbox("Entnahme mit Inflation steigern",
                                      value=True)

    st.divider()
    st.header("📈 Portfolio-Allokation")
    st.caption("Gewichte werden auf 100 % normalisiert.")
    w_aktien = st.slider("Aktien (MSCI World)", 0, 100, 60, 5)
    w_renten = st.slider("Renten (REXP Deutschland)", 0, 100, 25, 5)
    w_gold = st.slider("Gold (EUR)", 0, 100, 10, 5)
    w_cash = st.slider("Cash", 0, 100, 5, 5)

    total_w = w_aktien + w_renten + w_gold + w_cash
    if total_w == 0:
        st.error("Gesamtgewicht ist 0 — bitte mindestens eine Anlage > 0.")
        allocation = None
    else:
        allocation = {
            "Aktien": w_aktien / total_w,
            "Renten": w_renten / total_w,
            "Gold":   w_gold / total_w,
            "Cash":   w_cash / total_w,
        }
        if total_w != 100:
            st.info(f"Summe = {total_w} %, automatisch normalisiert.")

    st.divider()
    st.header("⚙️ Kosten & Steuern")
    ter_pct = st.slider("TER p.a. (%)", 0.0, 3.0, 0.50, 0.05)
    ter_annual = ter_pct / 100
    income_tax_pct = st.slider(
        "Einkommensteuer auf Sommerprämie (%)",
        0.0, 60.0, 42.0, 1.0,
        help="Im Netto-Szenario wird die Prämie vor der Investition um "
             "diesen Satz gekürzt. Das Brutto-Szenario investiert die "
             "volle Prämie.")
    income_tax_rate = income_tax_pct / 100
    st.caption("Vergleich: **Brutto** (volle Prämie investiert) vs. "
               "**Netto** (Prämie nach Einkommensteuer investiert).")

    run_button = st.button("🚀 Backtest starten", type="primary",
                           use_container_width=True)


# ──────────────────────────────────────────────────────────────────────
# HAUPT-PANEL
# ──────────────────────────────────────────────────────────────────────
if uploaded is not None:
    try:
        returns, inflation = load_data_from_bytes(uploaded.getvalue(), cash_yield)
    except Exception as e:
        st.error(f"Fehler beim Lesen der Excel: {e}")
        st.stop()
else:
    if not DEFAULT_DATA.exists():
        st.error(f"Standard-Datendatei nicht gefunden: {DEFAULT_DATA}. "
                  "Bitte Excel hochladen.")
        st.stop()
    returns, inflation = load_data(str(DEFAULT_DATA), cash_yield)

period_start, period_end = available_period(returns)
infl_annual = (1 + inflation).prod() ** (12/len(inflation)) - 1

c1, c2, c3 = st.columns(3)
c1.metric("Datenzeitraum", f"{period_start.year}–{period_end.year}",
          f"{len(returns)} Monate")
c2.metric("Anlageklassen", "Aktien / Renten / Gold / Cash")
c3.metric("∅ Inflation DE", f"{infl_annual*100:.2f} % p.a.")

with st.expander("📊 Datenvorschau"):
    st.dataframe(returns.tail(12).style.format("{:.2%}"), use_container_width=True)


# ──────────────────────────────────────────────────────────────────────
# BACKTEST AUSFÜHREN
# ──────────────────────────────────────────────────────────────────────
if not run_button:
    st.info("⬅️ Parameter in der Sidebar einstellen und **Backtest starten** klicken.")
    st.stop()

if allocation is None:
    st.error("Bitte gültige Allokation einstellen.")
    st.stop()

params_brutto = SimulationParams(
    allocation=allocation,
    start_age=start_age,
    end_career_age=end_career_age,
    end_age=end_age,
    annual_contribution=float(annual_contribution),
    contribution_indexed=contribution_indexed,
    monthly_withdrawal=float(monthly_withdrawal),
    withdrawal_indexed=withdrawal_indexed,
    ter_annual=ter_annual,
    income_tax_rate=0.0,
)
params_netto = SimulationParams(
    allocation=allocation,
    start_age=start_age,
    end_career_age=end_career_age,
    end_age=end_age,
    annual_contribution=float(annual_contribution),
    contribution_indexed=contribution_indexed,
    monthly_withdrawal=float(monthly_withdrawal),
    withdrawal_indexed=withdrawal_indexed,
    ter_annual=ter_annual,
    income_tax_rate=income_tax_rate,
)
# Default-Param für nachgelagerte Berechnungen (z.B. SWR): Netto-Szenario
params = params_netto

total_months = (end_age - start_age) * 12
n_possible = len(returns) - total_months + 1

if n_possible <= 0:
    st.error(f"❌ Lebenszyklus ist {total_months/12:.0f} Jahre, "
             f"verfügbare Historie nur {len(returns)/12:.1f} Jahre. "
             "Bitte Endalter senken oder Karrierestart anheben.")
    st.stop()

if n_possible < 10:
    st.warning(f"⚠️ Nur {n_possible} Rolling-Szenarien möglich – statistische "
                "Aussagekraft eingeschränkt. Endalter senken für mehr Szenarien.")

with st.spinner(f"Berechne {n_possible} Rolling-Szenarien (Brutto & Netto)…"):
    rolling_b = run_rolling_backtest(returns, inflation, params_brutto)
    summary_b = summary_metrics(rolling_b)
    perc_b = equity_percentiles(rolling_b, quantiles=(0.10, 0.25, 0.50, 0.75, 0.90))

    rolling_n = run_rolling_backtest(returns, inflation, params_netto)
    summary_n = summary_metrics(rolling_n)
    perc_n = equity_percentiles(rolling_n, quantiles=(0.10, 0.25, 0.50, 0.75, 0.90))

# Netto bleibt das "Haupt"-Szenario für nachgelagerte Detailansichten.
rolling, summary, perc = rolling_n, summary_n, perc_n


# ──────────────────────────────────────────────────────────────────────
# KENNZAHLEN-DASHBOARD – BRUTTO vs. NETTO VERGLEICH
# ──────────────────────────────────────────────────────────────────────
st.header("📊 Ergebnis-Dashboard: Vorher / Nachher (Steuern)")
st.caption(f"**Brutto** = volle Sommerprämie investiert · "
           f"**Netto** = Prämie nach {income_tax_pct:.0f} % Einkommensteuer investiert. "
           "Delta zeigt den Effekt der Versteuerung der Einzahlung.")


def _delta_pct(netto: float, brutto: float) -> str:
    if brutto == 0:
        return "—"
    return f"{(netto - brutto) / abs(brutto) * 100:+.1f} %"


col_b, col_n = st.columns(2, gap="large")

with col_b:
    st.subheader("💶 Brutto (vor Steuer)")
    b1, b2 = st.columns(2)
    b1.metric("Erfolgsquote", f"{summary_b['erfolgsquote']*100:.1f} %")
    b2.metric("Endvermögen (Median)", f"{summary_b['endvermoegen_p50']:,.0f} €")
    b3, b4 = st.columns(2)
    b3.metric("Endvermögen P10", f"{summary_b['endvermoegen_p10']:,.0f} €")
    b4.metric("Endvermögen P90", f"{summary_b['endvermoegen_p90']:,.0f} €")

with col_n:
    st.subheader("💴 Netto (nach Steuer)")
    n1, n2 = st.columns(2)
    n1.metric("Erfolgsquote", f"{summary_n['erfolgsquote']*100:.1f} %",
              delta=f"{(summary_n['erfolgsquote']-summary_b['erfolgsquote'])*100:+.1f} pp")
    n2.metric("Endvermögen (Median)", f"{summary_n['endvermoegen_p50']:,.0f} €",
              delta=_delta_pct(summary_n['endvermoegen_p50'], summary_b['endvermoegen_p50']))
    n3, n4 = st.columns(2)
    n3.metric("Endvermögen P10", f"{summary_n['endvermoegen_p10']:,.0f} €",
              delta=_delta_pct(summary_n['endvermoegen_p10'], summary_b['endvermoegen_p10']))
    n4.metric("Endvermögen P90", f"{summary_n['endvermoegen_p90']:,.0f} €",
              delta=_delta_pct(summary_n['endvermoegen_p90'], summary_b['endvermoegen_p90']))

st.divider()

# Direkter Vergleich der Median-Endvermögen als Balken
diff_abs = summary_n['endvermoegen_p50'] - summary_b['endvermoegen_p50']
fig_cmp = go.Figure(go.Bar(
    x=["Brutto (vor Steuer)", "Netto (nach Steuer)"],
    y=[summary_b['endvermoegen_p50'], summary_n['endvermoegen_p50']],
    marker=dict(color=["rgb(44,160,44)", "rgb(31,119,180)"]),
    text=[f"{summary_b['endvermoegen_p50']:,.0f} €",
          f"{summary_n['endvermoegen_p50']:,.0f} €"],
    textposition="auto",
))
fig_cmp.update_layout(
    title=f"Median-Endvermögen im Vergleich · Differenz {diff_abs:,.0f} €",
    yaxis_title="Endvermögen (€)",
    yaxis=dict(tickformat=",.0f"),
    height=350,
    margin=dict(l=10, r=10, t=50, b=10),
)
st.plotly_chart(fig_cmp, use_container_width=True)


# ──────────────────────────────────────────────────────────────────────
# EQUITY-FAN-CHART
# ──────────────────────────────────────────────────────────────────────
st.subheader("📈 Equitykurve – Rolling-Szenarien (Fan-Chart, Netto)")
st.caption("Band = P10–P90 / P25–P75 des Netto-Szenarios. "
           "Die gestrichelte grüne Linie zeigt den Brutto-Median zum Vergleich.")

x_years = perc.index / 12 + start_age  # X-Achse als Alter

fig = go.Figure()

# P10–P90-Band
fig.add_trace(go.Scatter(
    x=x_years, y=perc["P90"], name="P90",
    line=dict(width=0), showlegend=False,
))
fig.add_trace(go.Scatter(
    x=x_years, y=perc["P10"], name="P10–P90 Bereich",
    fill="tonexty", fillcolor="rgba(31,119,180,0.15)",
    line=dict(width=0),
))
# P25–P75-Band
fig.add_trace(go.Scatter(
    x=x_years, y=perc["P75"], name="P75",
    line=dict(width=0), showlegend=False,
))
fig.add_trace(go.Scatter(
    x=x_years, y=perc["P25"], name="P25–P75 Bereich",
    fill="tonexty", fillcolor="rgba(31,119,180,0.30)",
    line=dict(width=0),
))
# Median
fig.add_trace(go.Scatter(
    x=x_years, y=perc["P50"], name="Median Netto (P50)",
    line=dict(color="rgb(31,119,180)", width=3),
))
# Brutto-Median zum Vergleich
x_years_b = perc_b.index / 12 + start_age
fig.add_trace(go.Scatter(
    x=x_years_b, y=perc_b["P50"], name="Median Brutto (P50)",
    line=dict(color="rgb(44,160,44)", width=2, dash="dash"),
))

# Karriereende-Marker
fig.add_vline(x=end_career_age, line_dash="dash", line_color="red",
              annotation_text=f"Karriereende (Alter {end_career_age})",
              annotation_position="top")

fig.update_layout(
    xaxis_title="Alter",
    yaxis_title="Vermögen (€)",
    yaxis=dict(tickformat=",.0f"),
    hovermode="x unified",
    height=500,
    margin=dict(l=10, r=10, t=30, b=10),
)
st.plotly_chart(fig, use_container_width=True)


# ──────────────────────────────────────────────────────────────────────
# ENDVERMÖGEN-VERTEILUNG
# ──────────────────────────────────────────────────────────────────────
col_left, col_right = st.columns(2)

with col_left:
    st.subheader("💼 Endvermögen-Verteilung")
    final_values = rolling["results"]["Endvermögen"]
    fig_hist = go.Figure(go.Histogram(
        x=final_values, nbinsx=30,
        marker=dict(color="rgb(31,119,180)"),
    ))
    fig_hist.add_vline(x=summary["endvermoegen_p50"], line_dash="dash",
                       line_color="red",
                       annotation_text=f"Median: {summary['endvermoegen_p50']:,.0f} €",
                       annotation_position="top right")
    fig_hist.update_layout(
        xaxis_title="Endvermögen (€)",
        yaxis_title="Anzahl Szenarien",
        xaxis=dict(tickformat=",.0f"),
        height=400,
        margin=dict(l=10, r=10, t=10, b=10),
    )
    st.plotly_chart(fig_hist, use_container_width=True)

with col_right:
    st.subheader("📉 Max Drawdown-Verteilung")
    dd_values = rolling["results"]["MaxDrawdown"] * 100
    fig_dd = go.Figure(go.Histogram(
        x=dd_values, nbinsx=20,
        marker=dict(color="rgb(214,39,40)"),
    ))
    fig_dd.update_layout(
        xaxis_title="Max Drawdown (%)",
        yaxis_title="Anzahl Szenarien",
        height=400,
        margin=dict(l=10, r=10, t=10, b=10),
    )
    st.plotly_chart(fig_dd, use_container_width=True)


# ──────────────────────────────────────────────────────────────────────
# SAFE WITHDRAWAL RATE
# ──────────────────────────────────────────────────────────────────────
st.subheader("🎯 Safe Withdrawal Rate (SWR)")
st.caption("Höchste monatliche Entnahme, bei der mindestens 95 % der "
           "historischen Szenarien NICHT erschöpfen — bei aktueller Allokation, "
           "Sparrate und Karriereprofil.")

if st.button("SWR berechnen (dauert etwas länger)"):
    with st.spinner("Bisection-Suche…"):
        swr = safe_withdrawal_rate(returns, inflation, params,
                                    target_success=0.95)
    if swr["swr_monatlich"] is None:
        st.error(swr["info"])
    else:
        cA, cB = st.columns(2)
        cA.metric("SWR monatlich", f"{swr['swr_monatlich']:,.0f} €")
        cB.metric("SWR jährlich",  f"{swr['swr_jaehrlich']:,.0f} €")
        st.caption(swr["info"])


# ──────────────────────────────────────────────────────────────────────
# TABELLE ALLER SZENARIEN
# ──────────────────────────────────────────────────────────────────────
with st.expander("🔍 Pro-Szenario-Tabelle"):
    df_show = rolling["results"].copy()
    df_show.index = df_show.index.strftime("%Y-%m")
    df_show["MaxDrawdown"] = df_show["MaxDrawdown"] * 100
    df_show["CAGR_money"] = df_show["CAGR_money"] * 100
    df_show["Volatilität"] = df_show["Volatilität"] * 100
    st.dataframe(
        df_show.style.format({
            "Endvermögen": "{:,.0f} €",
            "MaxDrawdown": "{:.1f} %",
            "CAGR_money":  "{:.2f} %",
            "Volatilität": "{:.2f} %",
            "Eingezahlt_total": "{:,.0f} €",
            "Entnommen_total":  "{:,.0f} €",
        }),
        use_container_width=True,
    )

    # CSV-Download
    csv = rolling["results"].to_csv().encode("utf-8")
    st.download_button("⬇️ Als CSV herunterladen",
                       csv, "backtest_szenarien.csv", "text/csv")


st.divider()
st.caption("⚠️ Diese Simulation dient ausschließlich zu Anschauungs- und "
           "Forschungszwecken. Sie stellt keine Anlageberatung dar. "
           "Vergangene Wertentwicklung ist kein verlässlicher Indikator "
           "für zukünftige Ergebnisse.")
