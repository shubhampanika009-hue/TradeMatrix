"""
data_feed.py - market data sources.

SimFeed   : simulated live market (works offline, great for testing SMC logic).
YahooFeed : real data via yfinance (polled; Yahoo is delayed, not tick-by-tick).
Zerodha / Angel One: see the ZerodhaFeed stub at the bottom.

Every feed exposes:  .name, .candles (list of dict), .step() -> bool (True if data changed)
"""
import random
import time

MAX_CANDLES = 500


class SimFeed:
    name = "sim"
    snapshot_on_update = False

    def __init__(self, start=24000.0, tf=60, ticks_per_candle=10, history=300):
        self.price, self.tf, self.tpc = start, tf, ticks_per_candle
        self.vol = start * 0.0002          # per-tick volatility
        self.drift = 0.0
        self.candles, self._n = [], 0
        self._new_candle(int(time.time()) // tf * tf - tf * history)
        for _ in range(history * ticks_per_candle):
            self._tick()

    def _new_candle(self, t):
        p = self.price
        self.candles.append({"time": t, "open": p, "high": p, "low": p, "close": p})
        self._n = 0
        del self.candles[:-MAX_CANDLES]

    def _tick(self):
        if random.random() < 0.005:                      # regime change (trend flip)
            self.drift = random.choice([-1, 1]) * self.vol * 0.4
        shock = random.gauss(self.drift, self.vol)
        if random.random() < 0.015:                      # impulsive move => creates FVG/OB
            shock *= 6
        self.price += shock
        c = self.candles[-1]
        c["close"] = self.price
        c["high"] = max(c["high"], self.price)
        c["low"] = min(c["low"], self.price)
        self._n += 1
        if self._n >= self.tpc:                          # 10 ticks = 1 simulated candle
            self._new_candle(c["time"] + self.tf)

    def step(self):
        self._tick()
        return True


class YahooFeed:
    name = "yahoo"
    snapshot_on_update = True

    def __init__(self, symbol="RELIANCE.NS", interval="5m", period="5d",
                 refresh_sec=30, tz_offset=19800):   # 19800 = IST (UTC+5:30)
        self.symbol, self.interval, self.period = symbol, interval, period
        self.refresh_sec, self.tz_offset = refresh_sec, tz_offset
        self.candles, self._last = [], 0
        self.step()

    def step(self):
        if time.time() - self._last < self.refresh_sec:
            return False
        self._last = time.time()
        try:
            import yfinance as yf
            df = yf.Ticker(self.symbol).history(period=self.period, interval=self.interval)
            self.candles = [
                {"time": int(ts.timestamp()) + self.tz_offset, "open": float(r.Open),
                 "high": float(r.High), "low": float(r.Low), "close": float(r.Close)}
                for ts, r in df.iterrows()
            ][-MAX_CANDLES:]
            return True
        except Exception as e:
            print("Yahoo fetch failed:", e)
            return False


class ZerodhaFeed:
    """
    Stub: connect Zerodha KiteTicker (or Angel One SmartWebSocket) here.
    1) pip install kiteconnect
    2) KiteTicker(api_key, access_token).on_ticks -> build 1m/5m candles from ticks
    3) keep self.candles in the same dict format and return True from step()
    """
    name = "zerodha"
    snapshot_on_update = False
    candles = []

    def step(self):
        raise NotImplementedError("Add your KiteTicker integration here")
