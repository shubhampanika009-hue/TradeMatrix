"""
main.py - FastAPI server.
  GET /api/candles   -> candles
  GET /api/analysis  -> FVG / OB / sweeps / signals
  WS  /ws            -> live stream (snapshot first, then updates every second)
  GET /              -> serves ../frontend/index.html
Run:  uvicorn main:app --reload --port 8000
Env : DATA_SOURCE=sim|yahoo   SYMBOL=RELIANCE.NS   INTERVAL=5m
"""
import asyncio
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from algo_engine import analyze
from data_feed import SimFeed, YahooFeed

SOURCE = os.getenv("DATA_SOURCE", "sim")
SYMBOL = os.getenv("SYMBOL", "RELIANCE.NS")
INTERVAL = os.getenv("INTERVAL", "5m")

feed = YahooFeed(SYMBOL, INTERVAL) if SOURCE == "yahoo" else SimFeed()
clients: set[WebSocket] = set()


def analysis():
    # Only CLOSED candles are analysed, so zones/signals never repaint.
    return analyze(feed.candles[:-1])


def snapshot():
    return {"type": "snapshot", "symbol": SYMBOL if SOURCE == "yahoo" else "SIM-NIFTY",
            "candles": feed.candles, "analysis": analysis()}


async def broadcast(msg):
    for ws in list(clients):
        try:
            await ws.send_json(msg)
        except Exception:
            clients.discard(ws)


async def ticker():
    while True:
        await asyncio.sleep(1)
        changed = await asyncio.to_thread(feed.step)
        if not changed or not clients:
            continue
        if feed.snapshot_on_update:
            await broadcast(snapshot())
        else:
            await broadcast({"type": "update", "candle": feed.candles[-1], "analysis": analysis()})


@asynccontextmanager
async def lifespan(_):
    task = asyncio.create_task(ticker())
    yield
    task.cancel()


app = FastAPI(title="SMC Analyzer", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.get("/api/candles")
def candles():
    return feed.candles


@app.get("/api/analysis")
def get_analysis():
    return analysis()


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await ws.accept()
    clients.add(ws)
    try:
        await ws.send_json(snapshot())
        while True:
            await ws.receive_text()   # keep the connection open
    except WebSocketDisconnect:
        pass
    finally:
        clients.discard(ws)


FRONTEND = Path(__file__).resolve().parent.parent / "frontend"
app.mount("/", StaticFiles(directory=FRONTEND, html=True), name="frontend")
