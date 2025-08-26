# Opening-Range-Breakout

Opening Range Breakout (ORB) research framework that:
- Builds the 5-minute opening range from 1-minute bars (09:30–09:34 ET).
- Applies a candle-direction filter:
  - Bullish 5-min candle → only long breakouts
  - Bearish 5-min candle → only short breakdowns
  - Doji → no trade
- Uses daily ATR(14) to set a stop distance = **10% of ATR(14)**.
- One trade per symbol per day:
  - Enter on breakout of the 5-min high (long) or low (short) depending on bias
  - Exit at stop intraday, otherwise flatten at the end of regular session (16:00 ET)
- Commission model: $0.005/share (configurable)

> This repo intentionally excludes live-trading code (market data streams, order routing).

## Data Format

### Minute Bars (per symbol or multi-symbol)
CSV with at least:
- `timestamp` (ISO string or "YYYY-MM-DD HH:MM:SS" in **America/New_York** time)
- `symbol`
- `open, high, low, close, volume`
