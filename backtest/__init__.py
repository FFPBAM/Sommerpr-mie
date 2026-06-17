"""Backtest-Paket für die Fußballer-Altersvorsorge-Simulation."""

from .data_loader import build_returns, available_period
from .simulation import SimulationParams, run_single_backtest, run_rolling_backtest
from .metrics import summary_metrics, equity_percentiles, safe_withdrawal_rate

__all__ = [
    "build_returns", "available_period",
    "SimulationParams", "run_single_backtest", "run_rolling_backtest",
    "summary_metrics", "equity_percentiles", "safe_withdrawal_rate",
]
