import argparse
import pandas as pd
import numpy as np
from ta.volatility import AverageTrueRange
from datetime import datetime, time as dtime
from typing import List, Optional
from util import (
    ensure_datetime_tz, filter_rth, opening_range_levels, allowed_direction, 
    calc_position_size, session_date_index, summarize_trades
)

NY_TZ = "America/New_York"
RISK_PCT = 0.01
MAX_LEV = 4.0
COMMISSION_PER_SHARE = 0.005
OPENING_RANGE_BARS = 5
ATR_LOOKBACK = 14

def compute_daily_atr14(daily_df: pd.DataFrame) -> pd.DataFrame:
    #For each symbol, compute ATR(14) on DAILY bars, then rename to 'atr14'.
    #Returns a DataFrame with columns: [date, symbol, atr14
    out = []
    for sym, g in daily_df.groupby("symbol"):
        g = g.sort_values("date").copy()
        atr = AverageTrueRange(high=g["high"], low=g["low"], close=g["close"], window=ATR_LOOKBACK).average_true_range()
        g["atr14"] = atr
        out.append(g[["date", "symbol", "atr14"]])
    return pd.concat(out, ignore_index=True)

def backtest_orb(minute_df: pd.DataFrame, daily_df: pd.DataFrame, symbols: List[str], start: Optional[str], end: Optional[str]) -> pd.DataFrame:
    #Run ORB backtest across given symbols and date range. One trade per symbol per day.
    #Returns a trades DataFrame.
    # Prep minute bars
    minute_df = minute_df.copy()
    minute_df = ensure_datetime_tz(minute_df, "timestamp", NY_TZ)
    minute_df = filter_rth(minute_df, "timestamp")

    # Prep daily ATR
    daily_df = daily_df.copy()
    daily_df["date"] = pd.to_datetime(daily_df["date"]).dt.date
    atr_df = compute_daily_atr14(daily_df)  # has 'date' as date
    # Join minute bars with that day's ATR(14) (we will use previous day's ATR for today)
    minute_df["date"] = session_date_index(minute_df["timestamp"])

    # Filter symbols if provided
    if symbols:
        minute_df = minute_df[minute_df["symbol"].isin(symbols)]
        daily_df = daily_df[daily_df["symbol"].isin(symbols)]
        atr_df = atr_df[atr_df["symbol"].isin(symbols)]

    # Date range filter (trading dates)
    if start:
        start_d = pd.to_datetime(start).date()
        minute_df = minute_df[minute_df["date"] >= start_d]
    if end:
        end_d = pd.to_datetime(end).date()
        minute_df = minute_df[minute_df["date"] <= end_d]

    trades = []
    # Group by symbol and trading date
    for (sym, day), g in minute_df.groupby(["symbol", "date"]):
        g = g.sort_values("timestamp")
        # ATR for this day: use prior day's ATR(14)
        prev_day = pd.to_datetime(day) - pd.Timedelta(days=1)
        prev_day = prev_day.date()
        atr_row = atr_df[(atr_df["symbol"] == sym) & (atr_df["date"] <= prev_day)].sort_values("date").tail(1)
        if atr_row.empty or pd.isna(atr_row["atr14"].iloc[0]):
            # skip day if not enough ATR history
            continue
        atr14 = float(atr_row["atr14"].iloc[0])
        atr10pct = 0.1 * atr14

        # Build 5-min opening range
        or_levels = opening_range_levels(g, "timestamp", bars=OPENING_RANGE_BARS)
        if or_levels is None:
            continue
        open_5, close_5, high_5, low_5 = or_levels
        bias = allowed_direction(open_5, close_5)
        if bias == "NONE":
            # doji day -> no trade
            continue

        # After first 5 minutes, scan for breakout in allowed direction
        after_or = g.iloc[OPENING_RANGE_BARS:]  # bars from 09:35 onwards
        if after_or.empty:
            continue

        entry_side = None
        entry_idx = None
        entry_price = None

        if bias == "BUY":
            # first bar that CLOSES > OR high
            mask = after_or["close"] > high_5
            if mask.any():
                entry_idx = mask.idxmax()  # first True index
                entry_side = "BUY"
                entry_price = float(after_or.loc[entry_idx, "close"])
        elif bias == "SELL":
            mask = after_or["close"] < low_5
            if mask.any():
                entry_idx = mask.idxmax()
                entry_side = "SELL"
                entry_price = float(after_or.loc[entry_idx, "close"])

        if entry_side is None:
            continue  # no breakout today

        # Position sizing
        qty = calc_position_size(
            account_size=25000.0,
            price=entry_price,
            atr10pct=atr10pct,
            risk_pct=RISK_PCT,
            max_leverage=MAX_LEV,
            min_shares=1
        )
        if qty <= 0:
            continue

        # Stop price
        stop_price = entry_price - atr10pct if entry_side == "BUY" else entry_price + atr10pct

        # Simulate forward from entry bar to EOD: stop or close at 16:00
        path = g.loc[entry_idx:]  # from entry bar inclusive
        exit_price = None
        exit_time = None
        exit_reason = None

        # Intraday stop check using bar lows/highs
        for _, row in path.iterrows():
            ts = row["timestamp"]
            hi = float(row["high"])
            lo = float(row["low"])
            # Stop trigger
            if entry_side == "BUY" and lo <= stop_price:
                exit_price = stop_price
                exit_time = ts
                exit_reason = "STOP"
                break
            if entry_side == "SELL" and hi >= stop_price:
                exit_price = stop_price
                exit_time = ts
                exit_reason = "STOP"
                break

        # If not stopped, exit at EOD (use last close at or before 16:00)
        if exit_price is None:
            # Find last bar at or before 16:00
            day_path = path.copy()
            t = day_path["timestamp"].dt
            day_path = day_path[(t.hour < 16) | ((t.hour == 16) & (t.minute == 0))]
            if day_path.empty:
                continue
            last_bar = day_path.iloc[-1]
            exit_price = float(last_bar["close"])
            exit_time = last_bar["timestamp"]
            exit_reason = "EOD"

        # PnL
        if entry_side == "BUY":
            gross = (exit_price - entry_price) * qty
        else:
            gross = (entry_price - exit_price) * qty

        commissions = qty * COMMISSION_PER_SHARE * 2  # entry+exit
        net = gross - commissions

        hold_minutes = int((exit_time - g.loc[entry_idx, "timestamp"]).total_seconds() // 60)

        trades.append({
            "date": day,
            "symbol": sym,
            "side": entry_side,
            "entry_time": g.loc[entry_idx, "timestamp"],
            "entry_price": round(entry_price, 4),
            "qty": int(qty),
            "stop_price": round(stop_price, 4),
            "exit_time": exit_time,
            "exit_price": round(exit_price, 4),
            "exit_reason": exit_reason,
            "gross_pnl": round(gross, 2),
            "commissions": round(commissions, 2),
            "net_pnl": round(net, 2),
            "hold_minutes": hold_minutes,
            "or_high": round(high_5, 4),
            "or_low": round(low_5, 4),
            "open5": round(open_5, 4),
            "close5": round(close_5, 4),
            "atr14_prev": round(atr14, 4),
            "atr10pct": round(atr10pct, 4),
        })

    trades_df = pd.DataFrame(trades)
    # sort for readability
    if not trades_df.empty:
        trades_df = trades_df.sort_values(["date", "symbol", "entry_time"]).reset_index(drop=True)
    return trades_df

def main():
    minute_df = pd.read_csv(args.minute_csv)
    daily_df = pd.read_csv(args.daily_csv)

    symbols = [s.strip() for s in args.symbols.split(",") if s.strip()] if args.symbols else []
    start = args.start if args.start else None
    end = args.end if args.end else None

    trades_df = backtest_orb(minute_df, daily_df, symbols, start, end)
    trades_df.to_csv(args.out_trades, index=False)

    # Print summary
    from orb_utils import summarize_trades
    summary = summarize_trades(trades_df)
    print("\n=== ORB Backtest Summary ===")
    for k, v in summary.items():
        if isinstance(v, float):
            print(f"{k:>16}: {v:.4f}")
        else:
            print(f"{k:>16}: {v}")
    print(f"\nSaved trades to: {args.out_trades}")

if __name__ == "__main__":
    main()
