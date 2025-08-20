class IBHist(EWrapper, EClient):
    def __init__(self):
        EClient.__init__(self, self)
        self.next_valid_id = None
        self._bars = {}
        self._done = {}

    def nextValidId(self, orderId: int):
        self.next_valid_id = orderId

    def historicalData(self, reqId: int, bar: BarData):
        self._bars.setdefault(reqId, []).append(bar)

    def historicalDataEnd(self, reqId: int, start: str, end: str):
        self._done[reqId] = True

    def error(self, reqId, code, msg, *args):
        print(f"[IBHist] error {reqId} {code} {msg}")

    def fetch_daily_bars(self, symbol: str, days: int = HIST_DAYS, timeout=30.0) -> List[BarData]:
        while self.next_valid_id is None:
            time.sleep(0.05)
        reqId = int(time.time() * 1000) % 2_147_483_647
        self._bars[reqId] = []
        self._done[reqId] = False

        c = Contract()
        c.symbol = symbol
        c.secType = "STK"
        c.exchange = "SMART"
        c.currency = "USD"

        self.reqHistoricalData(reqId, c, "", f"{days} D", "1 day", "TRADES", 1, 1, False, [])
        t0 = time.time()
        while not self._done.get(reqId, False) and (time.time() - t0) < timeout:
            time.sleep(0.05)
        return list(self._bars.get(reqId, []))

def compute_atr(bars: List[BarData]) -> Optional[float]:
    if len(bars) < ATR_LOOKBACK + 1:
        return None
    df = pd.DataFrame([{
        "open": float(b.open),
        "high": float(b.high),
        "low": float(b.low),
        "close": float(b.close)
    } for b in bars])
    df = df.sort_index().reset_index(drop=True)
    df['atr'] = ta.volatility.AverageTrueRange(
        high=df['high'], low=df['low'], close=df['close'], window=ATR_LOOKBACK).average_true_range()
    return float(df['atr'].iloc[-1])

def fetch_atr(symbol: str) -> Optional[float]:
    hist = IBHist()
    hist.connect(IB_HOST, IB_PORT, IB_CLIENT_ID + 99)
    threading.Thread(target=hist.run, daemon=True).start()
    while hist.next_valid_id is None:
        time.sleep(0.05)
    bars = hist.fetch_daily_bars(symbol)
    atr = compute_atr14_ta(bars)
    hist.disconnect()
    return atr
