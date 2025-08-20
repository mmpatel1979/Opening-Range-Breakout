def strategy(days, p, orb_m, target_R, risk, max_Lev, AUM_0, commission):
    start_time = time.time()
    str_df = pd.DataFrame({'Date': days, 'AUM': np.nan, 'pnl_R': np.nan})
    str_df.loc[0, 'AUM'] = AUM_0

    or_candles = orb_m
    day_groups = dict(tuple(p.groupby(p['day'].dt.date)))

    for t in range(1, len(days)):
        current_day = days[t].date()
        if current_day not in day_groups:
            str_df.loc[t, 'pnl_R'] = 0
            str_df.loc[t, 'AUM'] = str_df.loc[t-1, 'AUM']
            continue

        day_data = day_groups[current_day]
        if len(day_data) <= or_candles:
            str_df.loc[t, 'pnl_R'] = 0
            str_df.loc[t, 'AUM'] = str_df.loc[t-1, 'AUM']
            continue

        OHLC = day_data[['open', 'high', 'low', 'close']].values
        split_adj = OHLC[0, 0] / day_data['dOpen'].iloc[0]
        atr_raw = day_data['ATR'].iloc[0] * split_adj
        side = np.sign(OHLC[or_candles-1, 3] - OHLC[0, 0])
        entry = OHLC[or_candles, 0] if len(OHLC) > or_candles else np.nan

        if side == 1:
            stop = abs(np.min(OHLC[:or_candles, 2]) / entry - 1)
        elif side == -1:
            stop = abs(np.max(OHLC[:or_candles, 1]) / entry - 1)
        else:
            stop = np.nan

        if side == 0 or math.isnan(stop) or math.isnan(entry):
            str_df.loc[t, 'pnl_R'] = 0
            str_df.loc[t, 'AUM'] = str_df.loc[t-1, 'AUM']
            continue

        if entry == 0 or stop == 0:
            shares = 0
        else:
            shares = math.floor(min(
                str_df.loc[t-1, 'AUM'] * risk / (entry * stop),
                max_Lev * str_df.loc[t-1, 'AUM'] / entry
            ))

        if shares == 0:
            str_df.loc[t, 'pnl_R'] = 0
            str_df.loc[t, 'AUM'] = str_df.loc[t-1, 'AUM']
            continue

        OHLC_post_entry = OHLC[or_candles:, :]

        if side == 1:  # Long
            stop_price = entry * (1 - stop)
            target_price = entry * (1 + target_R * stop) if np.isfinite(target_R) else float('inf')
            stop_hits = OHLC_post_entry[:, 2] <= stop_price
            target_hits = OHLC_post_entry[:, 1] > target_price
        else:  # Short
            stop_price = entry * (1 + stop)
            target_price = entry * (1 - target_R * stop) if np.isfinite(target_R) else 0
            stop_hits = OHLC_post_entry[:, 1] >= stop_price
            target_hits = OHLC_post_entry[:, 2] < target_price

        if side == 1:
            if np.any(stop_hits) and np.any(target_hits):
                idx_stop = np.argmax(stop_hits)
                idx_target = np.argmax(target_hits)
                if idx_target < idx_stop:
                    PnL_T = max(target_price, OHLC_post_entry[idx_target, 0]) - entry
                else:
                    PnL_T = min(stop_price, OHLC_post_entry[idx_stop, 0]) - entry
            elif np.any(stop_hits):
                idx_stop = np.argmax(stop_hits)
                PnL_T = min(stop_price, OHLC_post_entry[idx_stop, 0]) - entry
            elif np.any(target_hits):
                idx_target = np.argmax(target_hits)
                PnL_T = max(target_price, OHLC_post_entry[idx_target, 0]) - entry
            else:
                PnL_T = OHLC_post_entry[-1, 3] - entry
        else:
            if np.any(stop_hits) and np.any(target_hits):
                idx_stop = np.argmax(stop_hits)
                idx_target = np.argmax(target_hits)
                if idx_target < idx_stop:
                    PnL_T = entry - min(target_price, OHLC_post_entry[idx_target, 0])
                else:
                    PnL_T = entry - max(stop_price, OHLC_post_entry[idx_stop, 0])
            elif np.any(stop_hits):
                idx_stop = np.argmax(stop_hits)
                PnL_T = entry - max(stop_price, OHLC_post_entry[idx_stop, 0])
            elif np.any(target_hits):
                idx_target = np.argmax(target_hits)
                PnL_T = entry - min(target_price, OHLC_post_entry[idx_target, 0])
            else:
                PnL_T = entry - OHLC_post_entry[-1, 3]

        prev_AUM = str_df.loc[t-1, 'AUM']
        str_df.loc[t, 'AUM'] = prev_AUM + shares * PnL_T - shares * commission * 2
        str_df.loc[t, 'pnl_R'] = (str_df.loc[t, 'AUM'] - prev_AUM) / (risk * prev_AUM)

    print(f"Backtest completed in {round(time.time() - start_time, 2)} sec")
    print(f"Final AUM: ${str_df['AUM'].iloc[-1]:,.2f}")
    print(f"Total Return: {(str_df['AUM'].iloc[-1]/AUM_0 - 1)*100:.2f}%")
    return str_df
