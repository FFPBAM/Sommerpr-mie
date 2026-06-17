"""
Aggregierte Kennzahlen über alle Rolling-Backtest-Szenarien.
"""

from __future__ import annotations
import numpy as np
import pandas as pd

from .simulation import (
    SimulationParams,
    run_rolling_backtest,
    run_single_backtest,
)


def summary_metrics(rolling_result: dict) -> dict:
    """Aggregiert die Pro-Szenario-Ergebnisse zu einem Dashboard-Dict."""
    results = rolling_result["results"]
    if len(results) == 0:
        return {"n_szenarien": 0}

    success_rate = float((~results["Erschöpft"]).mean())
    final_values = results["Endvermögen"]

    return {
        "n_szenarien": len(results),
        "erfolgsquote": success_rate,
        "endvermoegen_p10": float(final_values.quantile(0.10)),
        "endvermoegen_p50": float(final_values.quantile(0.50)),
        "endvermoegen_p90": float(final_values.quantile(0.90)),
        "endvermoegen_mean": float(final_values.mean()),
        "endvermoegen_min": float(final_values.min()),
        "endvermoegen_max": float(final_values.max()),
        "max_drawdown_median": float(results["MaxDrawdown"].median()),
        "max_drawdown_worst":  float(results["MaxDrawdown"].min()),
        "cagr_median":         float(results["CAGR_money"].median(skipna=True)),
        "volatilitaet_median": float(results["Volatilität"].median()),
        "erschoepfungsrate":   float(results["Erschöpft"].mean()),
    }


def equity_percentiles(rolling_result: dict,
                       quantiles: tuple[float, ...] = (0.10, 0.50, 0.90)
                       ) -> pd.DataFrame:
    """Berechnet je Monat-seit-Karrierestart die Perzentile der
    Equitykurve über alle Szenarien (Fan-Chart-Daten)."""
    equities = rolling_result["equities"]
    if equities.empty:
        return pd.DataFrame()
    perc = equities.quantile(list(quantiles), axis=1).T
    perc.columns = [f"P{int(q*100)}" for q in quantiles]
    return perc


def safe_withdrawal_rate(
    returns: pd.DataFrame,
    inflation: pd.Series,
    base_params: SimulationParams,
    target_success: float = 0.95,
    search_range: tuple[float, float] = (500.0, 50_000.0),
    tol: float = 50.0,
) -> dict:
    """Bisection-Suche nach der höchsten monatlichen Entnahme, bei der
    mindestens `target_success` (z.B. 95 %) der Rolling-Szenarien NICHT
    erschöpfen.

    Sucht im Bereich [search_range[0], search_range[1]] €/Monat.
    Genauigkeit: tol Euro.
    """
    lo, hi = search_range

    def success_at(w: float) -> float:
        p = SimulationParams(
            allocation=base_params.allocation,
            start_age=base_params.start_age,
            end_career_age=base_params.end_career_age,
            annual_contribution=base_params.annual_contribution,
            contribution_indexed=base_params.contribution_indexed,
            end_age=base_params.end_age,
            monthly_withdrawal=w,
            withdrawal_indexed=base_params.withdrawal_indexed,
            ter_annual=base_params.ter_annual,
            income_tax_rate=base_params.income_tax_rate,
        )
        res = run_rolling_backtest(returns, inflation, p)
        if len(res["results"]) == 0:
            return 0.0
        return float((~res["results"]["Erschöpft"]).mean())

    s_lo = success_at(lo)
    s_hi = success_at(hi)

    if s_lo < target_success:
        # Selbst bei minimaler Entnahme nicht erreichbar
        return {"swr_monatlich": None, "swr_jaehrlich": None,
                "info": f"Ziel {target_success:.0%} nicht erreichbar — "
                        f"selbst {lo:.0f} €/Monat erzielt nur {s_lo:.1%}."}
    if s_hi >= target_success:
        # Selbst bei maximaler Entnahme noch erfolgreich
        return {"swr_monatlich": hi, "swr_jaehrlich": hi*12,
                "info": f"Obergrenze {hi:.0f} €/Monat erreicht "
                        f"{s_hi:.1%} ≥ {target_success:.0%}."}

    # Bisection
    while hi - lo > tol:
        mid = (lo + hi) / 2
        s_mid = success_at(mid)
        if s_mid >= target_success:
            lo = mid
        else:
            hi = mid

    return {"swr_monatlich": lo,
            "swr_jaehrlich": lo * 12,
            "info": f"Bisection-Genauigkeit {tol:.0f} €/Monat erreicht."}
