import pandas as pd
import numpy as np
from typing import Optional, Tuple, Iterable, Dict

def ensure_datetime_tz(df: pd.DataFrame, ts_col: str = "timestamp", tz: str = "America/New_York") -> pd.DataFrame:
    #Convert a timestamp column to timezone-aware NY time.
    df = df.copy()
    df[ts_col] = pd.to_datetime(df[ts_col], utc=False, errors="coerce")
    if df[ts_col].dt.tz is None:
        # Localize (assume input is already NY local clock)
        df[ts_col] = df[ts_col].dt.tz_localize(tz)
    else:
        # Convert to NY
        df[ts_col] = df[ts_col].dt.tz_convert(tz)
    return df

def filter_rth(df_min: pd.DataFrame, ts_col: str = "timestamp") -> pd.DataFrame:
    #Keep only regular trading hours: 09:30:00–15:59:59 for processing, and include 16:00 for EOD mark.
    df = df_min.copy()
    t = df[ts_col].dt
    is_rth = (t.hour > 9) | ((t.hour == 9) & (t.minute >= 30))
    is_rth = is_rth & ((t.hour < 16) | ((t.hour == 16) & (t.minute == 0)))
    return df[is_rth].sort_values(ts_col)

def opening_range_levels(minute_day: pd.DataFrame, ts_col: str = "timestamp", bars: int = 5) -> Optional[Tuple[float, float, float, float]]:
    #Given one trading day's 1-min bars (RTH only), compute the 5-min candle (09:30–09:34) and OR levels.
    #Returns: (open_5, close_5, high_5, low_5) or None if insufficient data.
    day = minute_day.sort_values(ts_col)
    first5 = day.iloc[:bars]
    if len(first5) < bars:
        return None
    open_5 = float(first5.iloc[0].open)
    close_5 = float(first5.iloc[-1].close)
    high_5 = float(first5.high.max())
    low_5  = float(first5.low.min())
    return open_5, close_5, high_5, low_5

def allowed_direction(open_5: float, close_5: float) -> str:
    #BUY if bullish, SELL if bearish, NONE if doji.
    if close_5 > open_5:
        return "BUY"
    if close_5 < open_5:
        return "SELL"
    return "NONE"

def calc_position_size(account_size: float, price: float, atr10pct: float, risk_pct: float = 0.01, max_leverage: float = 4.0, min_shares: int = 1) -> int:
    #Shares by risk: (account_size * risk_pct) / atr10pct
    #Shares by exposure cap: (max_leverage * account_size) / price
    if atr10pct <= 0 or price <= 0:
        return 0
    shares_risk = (account_size * risk_pct) / atr10pct
    shares_expo = (max_leverage * account_size) / price
    qty = int(max(min_shares, np.floor(min(shares_risk, shares_expo))))
    return qty

def session_date_index(ts: pd.Series) -> pd.Series:
    #Map timestamps to the trading 'date' in NY (date component of NY-localized timestamps).
    return ts.dt.tz_convert("America/New_York").dt.date

def summarize_trades(trades: pd.DataFrame) -> Dict[str, float]:
    #Compute basic stats on per-trade results.
    if trades.empty:
        return {
            "trades": 0, "win_rate": 0.0, "avg_gross": 0.0, "avg_net": 0.0,
            "expectancy_net": 0.0, "median_hold_min": 0.0
        }
    wins = (trades["net_pnl"] > 0).mean()
    avg_gross = trades["gross_pnl"].mean()
    avg_net = trades["net_pnl"].mean()
    expectancy = avg_net  # per-trade expectancy
    hold_m = trades["hold_minutes"].median() if "hold_minutes" in trades else np.nan
    return {
        "trades": int(len(trades)),
        "win_rate": float(wins),
        "avg_gross": float(avg_gross),
        "avg_net": float(avg_net),
        "expectancy_net": float(expectancy),
        "median_hold_min": float(hold_m if pd.notnull(hold_m) else 0.0)
    }
