def create_trade_log(path: str):
    try:
        with open(path, "x", newline="") as f:
            csv.writer(f).writerow([
                "date", "entry_time", "exit_time", "side", "shares",
                "entry_price", "sl", "tp", "exit_price", "gross_pnl"
            ])
    except FileExistsError:
        pass

def append_trade_log(path: str, row: List):
    with open(path, "a", newline="") as f:
        csv.writer(f).writerow(row)

create_trade_log(TRADE_LOG)

TRADE_LOG = 'ORB_TRADES.csv'
