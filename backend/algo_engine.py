"""
algo_engine.py - Smart Money Concepts (SMC) detection engine.

Input : closed candles -> list of {"time","open","high","low","close"}
Output: {"fvgs": [...], "order_blocks": [...], "sweeps": [...], "signals": [...]}
Pure Python (no pandas), so it is easy to read and test.
"""

SWING_N = 3          # candles on each side to confirm a swing high/low
OB_LOOKBACK = 10     # how far back to look for the Order Block candle
MIN_GAP_PCT = 0.0001 # ignore tiny FVGs (0.01% of price)
CONFLUENCE_BARS = 12 # a sweep within N bars before a signal => "A+" setup
MAX_ZONES = 12       # zones per type returned to the UI


def _swings(c, n=SWING_N):
    highs, lows = [], []
    for i in range(n, len(c) - n):
        window = range(i - n, i + n + 1)
        if all(c[i]["high"] > c[j]["high"] for j in window if j != i):
            highs.append(i)
        if all(c[i]["low"] < c[j]["low"] for j in window if j != i):
            lows.append(i)
    return highs, lows


def _zone(kind, side, top, bottom, start_idx, created_idx):
    return {"kind": kind, "side": side, "top": top, "bottom": bottom,
            "start_idx": start_idx, "created_idx": created_idx,
            "end_idx": None, "touched": False}


def _find_fvgs(c):
    zones = []
    for i in range(2, len(c)):
        a, d = c[i - 2], c[i]
        if d["low"] > a["high"] and (d["low"] - a["high"]) / d["close"] >= MIN_GAP_PCT:
            zones.append(_zone("FVG", "bull", d["low"], a["high"], i - 1, i))
        elif d["high"] < a["low"] and (a["low"] - d["high"]) / d["close"] >= MIN_GAP_PCT:
            zones.append(_zone("FVG", "bear", a["low"], d["high"], i - 1, i))
    return zones


def _find_order_blocks(c, sh, sl):
    """
    Bullish OB: last bearish candle before a close that breaks a swing high (BOS up).
    Bearish OB: last bullish candle before a close that breaks a swing low (BOS down).
    """
    zones, broken = [], set()
    for k in range(len(c)):
        confirmed_h = [i for i in sh if i + SWING_N <= k and ("h", i) not in broken]
        confirmed_l = [i for i in sl if i + SWING_N <= k and ("l", i) not in broken]
        for hi in confirmed_h:
            if c[k]["close"] > c[hi]["high"]:
                broken.add(("h", hi))
                for j in range(k - 1, max(hi, k - OB_LOOKBACK) - 1, -1):
                    if c[j]["close"] < c[j]["open"]:
                        zones.append(_zone("OB", "bull", c[j]["high"], c[j]["low"], j, k))
                        break
        for lo in confirmed_l:
            if c[k]["close"] < c[lo]["low"]:
                broken.add(("l", lo))
                for j in range(k - 1, max(lo, k - OB_LOOKBACK) - 1, -1):
                    if c[j]["close"] > c[j]["open"]:
                        zones.append(_zone("OB", "bear", c[j]["high"], c[j]["low"], j, k))
                        break
    return zones


def _find_sweeps(c, sh, sl):
    """
    Liquidity sweep = wick takes out a swing high/low, candle closes back inside.
    Sweep of highs (buy-side liquidity) -> bearish. Sweep of lows (sell-side) -> bullish.
    """
    sweeps, done = [], set()
    for k in range(len(c)):
        for hi in sh:
            if hi + SWING_N <= k and ("h", hi) not in done and c[k]["high"] > c[hi]["high"]:
                done.add(("h", hi))
                if c[k]["close"] < c[hi]["high"]:
                    sweeps.append({"kind": "SWEEP", "side": "bear", "label": "BSL sweep",
                                   "top": c[k]["high"], "bottom": c[hi]["high"],
                                   "start_idx": hi, "idx": k})
        for lo in sl:
            if lo + SWING_N <= k and ("l", lo) not in done and c[k]["low"] < c[lo]["low"]:
                done.add(("l", lo))
                if c[k]["close"] > c[lo]["low"]:
                    sweeps.append({"kind": "SWEEP", "side": "bull", "label": "SSL sweep",
                                   "top": c[lo]["low"], "bottom": c[k]["low"],
                                   "start_idx": lo, "idx": k})
    return sweeps


def _signals(c, zones, sweeps):
    """Walk candle by candle: first touch of an active zone => BUY / SELL signal."""
    out = []
    for i in range(len(c)):
        k = c[i]
        for z in zones:
            if z["end_idx"] is not None or z["created_idx"] >= i:
                continue
            bullish_candle = k["close"] > k["open"]
            bearish_candle = k["close"] < k["open"]
            if not z["touched"]:
                if z["side"] == "bull" and k["low"] <= z["top"] and k["close"] > z["bottom"] and bullish_candle:
                    z["touched"] = True
                    sl = z["bottom"] - (z["top"] - z["bottom"]) * 0.25
                    out.append(_mk_signal(c, i, "BUY", z, sl, sweeps))
                elif z["side"] == "bear" and k["high"] >= z["bottom"] and k["close"] < z["top"] and bearish_candle:
                    z["touched"] = True
                    sl = z["top"] + (z["top"] - z["bottom"]) * 0.25
                    out.append(_mk_signal(c, i, "SELL", z, sl, sweeps))
            # mitigation: zone invalid once price closes through it
            if z["side"] == "bull" and k["close"] < z["bottom"]:
                z["end_idx"] = i
            elif z["side"] == "bear" and k["close"] > z["top"]:
                z["end_idx"] = i
    return out


def _mk_signal(c, i, side, z, sl, sweeps):
    price = c[i]["close"]
    risk = abs(price - sl)
    tp = price + 2 * risk if side == "BUY" else price - 2 * risk
    want = "bull" if side == "BUY" else "bear"
    confluence = any(s["side"] == want and 0 <= i - s["idx"] <= CONFLUENCE_BARS for s in sweeps)
    return {"id": f'{c[i]["time"]}-{side}', "time": c[i]["time"], "side": side,
            "price": round(price, 2), "sl": round(sl, 2), "tp": round(tp, 2),
            "zone": z["kind"], "strength": "A+" if confluence else "B"}


def analyze(candles):
    if len(candles) < 20:
        return {"fvgs": [], "order_blocks": [], "sweeps": [], "signals": []}
    sh, sl = _swings(candles)
    fvgs = _find_fvgs(candles)
    obs = _find_order_blocks(candles, sh, sl)
    sweeps = _find_sweeps(candles, sh, sl)
    signals = _signals(candles, fvgs + obs, sweeps)

    def out_zone(z):
        end = z["end_idx"]
        return {"kind": z["kind"], "side": z["side"],
                "top": round(z["top"], 2), "bottom": round(z["bottom"], 2),
                "start_time": candles[z["start_idx"]]["time"],
                "end_time": candles[end]["time"] if end is not None else None}

    active = lambda zs: [out_zone(z) for z in zs if z["end_idx"] is None][-MAX_ZONES:]
    return {
        "fvgs": active(fvgs),
        "order_blocks": active(obs),
        "sweeps": [{"side": s["side"], "label": s["label"], "top": round(s["top"], 2),
                    "bottom": round(s["bottom"], 2),
                    "start_time": candles[s["start_idx"]]["time"],
                    "end_time": candles[s["idx"]]["time"]} for s in sweeps][-MAX_ZONES:],
        "signals": signals[-60:],
    }
