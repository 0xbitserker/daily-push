"""Binance Futures API — Funding Rate / Open Interest 补充数据源（无需 API Key）"""
import httpx
from typing import Optional

BASE = "https://fapi.binance.com"


async def get_funding_rates(symbols: list[str] = None) -> list[dict]:
    """
    拉取 Binance 永续合约当前资金费率。
    symbols: None 时拉取全部，否则只拉指定交易对。
    返回: [{symbol, fundingRate, fundingTime, markPrice}, ...]
    """
    async with httpx.AsyncClient(timeout=15) as client:
        if symbols:
            results = []
            for sym in symbols:
                resp = await client.get(
                    f"{BASE}/fapi/v1/premiumIndex",
                    params={"symbol": sym},
                    timeout=10,
                )
                if resp.status_code == 200:
                    results.append(resp.json())
            return results
        else:
            resp = await client.get(f"{BASE}/fapi/v1/premiumIndex", timeout=15)
            resp.raise_for_status()
            return resp.json()


async def get_open_interest(symbol: str) -> Optional[dict]:
    """
    拉取单个交易对的当前 OI。
    返回: {symbol, openInterest, time}
    """
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(
            f"{BASE}/fapi/v1/openInterest", params={"symbol": symbol}
        )
        if resp.status_code != 200:
            return None
        return resp.json()


async def get_oi_history(symbol: str, period: str = "1d", limit: int = 14) -> list[dict]:
    """
    拉取 OI 历史（用于回测）。
    period: "5m","15m","30m","1h","2h","4h","6h","12h","1d"
    """
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(
            f"{BASE}/futures/data/openInterestHist",
            params={"symbol": symbol, "period": period, "limit": limit},
        )
        if resp.status_code != 200:
            return []
        return resp.json()


async def get_top_movers_24h(top_n: int = 20) -> list[dict]:
    """
    拉取 24h 涨跌幅最大的永续合约。
    返回: [{symbol, priceChangePercent, volume, lastPrice}, ...]
    """
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(f"{BASE}/fapi/v1/ticker/24hr")
        resp.raise_for_status()
        tickers = resp.json()
        sorted_tickers = sorted(
            tickers,
            key=lambda x: abs(float(x.get("priceChangePercent", 0))),
            reverse=True,
        )
        return sorted_tickers[:top_n]
