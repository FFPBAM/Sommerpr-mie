"""
Lädt die historischen Total-Return-Indizes aus der Excel und liefert
monatliche Return-Zeitreihen für die Backtest-Engine.

Spaltenmapping (Excel → Anlageklasse):
    NDDUWI Index   → Aktien (MSCI World, Net TR, EUR)
    REXP Index     → Renten (Deutscher Rentenindex, Performance)
    Gold           → Gold (EUR)
    Inflation DE   → Verbraucherpreisindex Deutschland
"""

from __future__ import annotations
from pathlib import Path
import pandas as pd
import numpy as np


ASSET_COLUMN_MAP = {
    "Aktien": "NDDUWI Index",
    "Renten": "REXP Index",
    "Gold":   "Gold",
}

INFLATION_COLUMN = "Inflation DE"


def load_raw(xlsx_path: str | Path) -> pd.DataFrame:
    """Liest das Sheet 'Import_Daten' und gibt einen DataFrame mit
    DatetimeIndex und numerischen Spalten zurück."""
    df = pd.read_excel(xlsx_path, sheet_name="Import_Daten")
    df = df.rename(columns={"Dates": "Date"})
    df["Date"] = pd.to_datetime(df["Date"])
    df = df.set_index("Date").sort_index()
    # Alle Spalten numerisch (Bloomberg-NaNs werden zu NaN)
    for col in df.columns:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def build_returns(
    xlsx_path: str | Path,
    cash_annual_yield: float = 0.0,
) -> tuple[pd.DataFrame, pd.Series]:
    """Berechnet monatliche Returns für alle Anlageklassen + Inflation.

    Parameters
    ----------
    xlsx_path : Pfad zur Excel.
    cash_annual_yield : nominaler Cash-Zinssatz p.a. (Default 0).

    Returns
    -------
    returns : DataFrame mit Spalten [Aktien, Renten, Gold, Cash], monatliche Returns.
    inflation : Series, monatliche Inflationsraten Deutschland.
    """
    raw = load_raw(xlsx_path)

    # Indexreihen → Monats-Returns (auf gemeinsamem Datumsraster)
    series = {}
    for asset, col in ASSET_COLUMN_MAP.items():
        s = raw[col].dropna()
        series[asset] = s.pct_change()

    returns = pd.concat(series, axis=1)

    # Cash: konstante monatliche Verzinsung
    monthly_cash = (1.0 + cash_annual_yield) ** (1/12) - 1.0
    returns["Cash"] = monthly_cash

    # Inflation aus CPI-Index → Monats-Inflation
    cpi = raw[INFLATION_COLUMN].dropna()
    inflation = cpi.pct_change()

    # Auf gemeinsame Periode trimmen, in der ALLE Asset-Returns existieren
    returns = returns.dropna(how="any")
    # Inflation auf denselben Index ausrichten (forward fill nur wenige Werte)
    inflation = inflation.reindex(returns.index).fillna(0.0)

    return returns, inflation


def available_period(returns: pd.DataFrame) -> tuple[pd.Timestamp, pd.Timestamp]:
    """Erster und letzter verfügbarer Monat über alle Assets."""
    return returns.index.min(), returns.index.max()


if __name__ == "__main__":
    # Smoke-Test
    p = Path(__file__).parent.parent / "data" / "Daten_Verrentung_EUR.xlsx"
    r, infl = build_returns(p, cash_annual_yield=0.02)
    print(f"Returns-Shape: {r.shape}")
    print(f"Zeitraum: {r.index.min().date()} → {r.index.max().date()}")
    print(r.describe().round(4))
    print(f"\nInflation DE (annualisiert, Schnitt): "
          f"{((1 + infl).prod() ** (12/len(infl)) - 1) * 100:.2f} % p.a.")
