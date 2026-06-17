"""
Backtest-Engine für ein einzelnes historisches Startdatum.

Modelliert:
- Ansparphase: monatliche Einzahlung, Allokation gemäß Zielgewichten,
  monatliches Rebalancing, TER-Abzug.
- Entsparphase: monatliche Entnahme (optional inflationsindexiert),
  Portfolio läuft weiter, bis Geld aufgebraucht oder Endalter erreicht.

Die Engine arbeitet auf monatlichen Returns und gibt die Equitykurve
zurück (Vermögen je Monatsende).
"""

from __future__ import annotations
from dataclasses import dataclass, field
import numpy as np
import pandas as pd


@dataclass
class SimulationParams:
    # Allokation: Dict {Aktien, Renten, Gold, Cash} → Anteile, Summe = 1
    allocation: dict[str, float]

    # Anspar-Eckdaten
    start_age: int = 18
    end_career_age: int = 35
    annual_contribution: float = 60_000.0  # € pro Jahr
    contribution_indexed: bool = False     # mit Inflation steigern?

    # Entspar-Eckdaten
    end_age: int = 90
    monthly_withdrawal: float = 5_000.0    # € pro Monat (Brutto)
    withdrawal_indexed: bool = True        # mit Inflation steigern?

    # Kosten
    ter_annual: float = 0.005              # 0,5 % p.a.

    # Steuern: Einkommensteuersatz auf die Sommerprämie (Einzahlung).
    # 0.0 = brutto (volle Prämie investiert),
    # >0  = netto (Prämie wird vor Investition um diesen Satz gekürzt).
    income_tax_rate: float = 0.0


def _validate_allocation(alloc: dict[str, float]) -> dict[str, float]:
    required = {"Aktien", "Renten", "Gold", "Cash"}
    missing = required - alloc.keys()
    if missing:
        raise ValueError(f"Allokation fehlt für: {missing}")
    total = sum(alloc[k] for k in required)
    if abs(total - 1.0) > 1e-6:
        raise ValueError(f"Allokation summiert zu {total:.4f}, nicht zu 1.0")
    return {k: alloc[k] for k in required}


def run_single_backtest(
    returns: pd.DataFrame,
    inflation: pd.Series,
    start_date: pd.Timestamp,
    params: SimulationParams,
) -> dict:
    """Führt EINEN Backtest mit gegebenem Startdatum durch.

    Returns
    -------
    dict mit:
        equity: pd.Series        – Vermögen je Monatsende
        phase: pd.Series         – "Anspar" oder "Entspar"
        depleted: bool           – Geld vor Endalter aufgebraucht?
        depleted_date: Timestamp – Datum der Erschöpfung (oder None)
        contributions_total: float
        withdrawals_total: float
        valid: bool              – ausreichend Daten vorhanden
    """
    alloc = _validate_allocation(params.allocation)
    asset_names = ["Aktien", "Renten", "Gold", "Cash"]
    weights = np.array([alloc[a] for a in asset_names])

    # Zeitachsen-Aufbau
    saving_months = (params.end_career_age - params.start_age) * 12
    retirement_months = (params.end_age - params.end_career_age) * 12
    total_months = saving_months + retirement_months

    # Verfügbare Returns ab start_date prüfen
    rets = returns.loc[start_date:]
    if len(rets) < total_months:
        return {
            "equity": pd.Series(dtype=float),
            "phase": pd.Series(dtype=object),
            "depleted": False,
            "depleted_date": None,
            "contributions_total": 0.0,
            "withdrawals_total": 0.0,
            "valid": False,
        }
    rets = rets.iloc[:total_months]
    infl = inflation.reindex(rets.index).fillna(0.0)

    # Monatliche TER (geometrisch aus jährlich)
    monthly_ter = (1.0 - params.ter_annual) ** (1/12) - 1.0  # negativ

    # Zustand
    portfolio_value = 0.0
    equity = np.zeros(total_months)
    phase  = np.empty(total_months, dtype=object)

    # Inflationsindex (kumuliert, startet bei 1.0)
    cum_infl = 1.0

    monthly_contribution = (params.annual_contribution / 12.0) * (1.0 - params.income_tax_rate)
    monthly_withdraw     = params.monthly_withdrawal

    contributions_total = 0.0
    withdrawals_total   = 0.0
    depleted = False
    depleted_date = None

    ret_matrix = rets[asset_names].to_numpy()
    infl_vec   = infl.to_numpy()

    for i in range(total_months):
        # 1) Marktbewegung dieses Monats
        period_return = float(np.dot(weights, ret_matrix[i]))
        portfolio_value *= (1.0 + period_return)

        # 2) TER abziehen (monatlich anteilig)
        portfolio_value *= (1.0 + monthly_ter)

        # 3) Inflation updaten
        cum_infl *= (1.0 + infl_vec[i])

        # 4) Cashflow je nach Phase
        if i < saving_months:
            phase[i] = "Anspar"
            contrib = monthly_contribution * (cum_infl if params.contribution_indexed else 1.0)
            portfolio_value += contrib
            contributions_total += contrib
        else:
            phase[i] = "Entspar"
            withdraw = monthly_withdraw * (cum_infl if params.withdrawal_indexed else 1.0)
            if portfolio_value >= withdraw:
                portfolio_value -= withdraw
                withdrawals_total += withdraw
            else:
                # Letzter Rest noch entnehmen, dann erschöpft
                withdrawals_total += portfolio_value
                portfolio_value = 0.0
                if not depleted:
                    depleted = True
                    depleted_date = rets.index[i]

        # 5) Rebalancing: ist implizit (Gewichte werden jeden Monat
        #    frisch auf das Gesamtvermögen angewandt), keine Tracking-
        #    Drift, weil wir das Portfolio nicht als Buckets führen.

        equity[i] = portfolio_value

    equity_s = pd.Series(equity, index=rets.index, name="Equity")
    phase_s  = pd.Series(phase,  index=rets.index, name="Phase")

    return {
        "equity": equity_s,
        "phase":  phase_s,
        "depleted": depleted,
        "depleted_date": depleted_date,
        "contributions_total": contributions_total,
        "withdrawals_total":   withdrawals_total,
        "valid": True,
    }


def run_rolling_backtest(
    returns: pd.DataFrame,
    inflation: pd.Series,
    params: SimulationParams,
) -> dict:
    """Iteriert über alle möglichen Startmonate und führt jeweils einen
    vollständigen Lebenszyklus-Backtest durch.

    Returns
    -------
    dict mit:
        equities: DataFrame (Index = Monat ab Karrierestart 0…N,
                            Spalten = Startjahr)
        results: DataFrame mit Pro-Szenario-Kennzahlen
        params: SimulationParams (Echo)
    """
    saving_months = (params.end_career_age - params.start_age) * 12
    retirement_months = (params.end_age - params.end_career_age) * 12
    total_months = saving_months + retirement_months

    # Alle Startdaten, für die genug Historie übrig ist
    all_dates = returns.index
    valid_starts = all_dates[: len(all_dates) - total_months + 1]

    equity_curves = {}
    rows = []

    for start in valid_starts:
        res = run_single_backtest(returns, inflation, start, params)
        if not res["valid"]:
            continue

        eq = res["equity"]
        # Normalisierte Zeitachse: Monat 0 = Karrierestart
        eq_indexed = eq.reset_index(drop=True)
        eq_indexed.index.name = "Monat"
        equity_curves[start.strftime("%Y-%m")] = eq_indexed

        # Kennzahlen pro Lauf
        final_value = float(eq.iloc[-1])
        peak = eq.cummax()
        dd = (eq - peak) / peak.replace(0, np.nan)
        max_dd = float(dd.min()) if dd.notna().any() else 0.0

        # CAGR über GESAMTZEITRAUM (auf Endvermögen vs. Summe Einzahlungen)
        # Hinweis: das ist NICHT die reine Marktrendite — wir nehmen sie
        # zusätzlich getrennt unten als money-weighted Approximation.
        years = total_months / 12.0
        if res["contributions_total"] > 0:
            cagr_money = (final_value / res["contributions_total"]) ** (1/years) - 1.0 \
                         if final_value > 0 else np.nan
        else:
            cagr_money = np.nan

        # Volatilität (annualisiert) der Portfolio-Returns
        # Aus Equitykurve approximieren wir nicht direkt — Cashflows verzerren.
        # Stattdessen direkt aus Gewichten * Returns rechnen.
        alloc = params.allocation
        w = np.array([alloc["Aktien"], alloc["Renten"], alloc["Gold"], alloc["Cash"]])
        slice_rets = returns.loc[start:].iloc[:total_months][["Aktien","Renten","Gold","Cash"]]
        port_rets = slice_rets.to_numpy() @ w
        vol_annual = float(np.std(port_rets, ddof=1) * np.sqrt(12))

        rows.append({
            "Startdatum": start,
            "Endvermögen": final_value,
            "MaxDrawdown": max_dd,
            "CAGR_money": cagr_money,
            "Volatilität": vol_annual,
            "Eingezahlt_total": res["contributions_total"],
            "Entnommen_total": res["withdrawals_total"],
            "Erschöpft": res["depleted"],
            "Erschöpfungsdatum": res["depleted_date"],
        })

    equities_df = pd.DataFrame(equity_curves)
    if rows:
        results_df = pd.DataFrame(rows).set_index("Startdatum")
    else:
        results_df = pd.DataFrame(
            columns=["Endvermögen", "MaxDrawdown", "CAGR_money",
                     "Volatilität", "Eingezahlt_total", "Entnommen_total",
                     "Erschöpft", "Erschöpfungsdatum"]
        )
        results_df.index.name = "Startdatum"

    return {
        "equities": equities_df,
        "results":  results_df,
        "params":   params,
    }
