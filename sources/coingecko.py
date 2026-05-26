"""CoinGecko 数据源 — 代币价格 / 涨跌幅 / 交易量"""
import httpx
from typing import Optional

BASE = "https://api.coingecko.com/api/v3"
HEADERS = {"accept": "application/json"}


async def get_top_coins(limit: int = 100) -> list[dict]:
    """
    拉取 Top N 代币的市场数据。
    返回字段: id, symbol, name, current_price, price_change_percentage_24h,
               total_volume, market_cap
    """
    params = {
        "vs_currency": "usd",
        "order": "market_cap_desc",
        "per_page": limit,
        "page": 1,
        "sparkline": "false",
        "price_change_percentage": "24h",
    }
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(f"{BASE}/coins/markets", params=params, headers=HEADERS)
        resp.raise_for_status()
        return resp.json()


async def get_coin_history(coin_id: str, days: int = 14) -> Optional[list[dict]]:
    """
    拉取单个代币过去 N 天的每日价格历史（用于回测）。
    返回: [{date: str, price: float, volume: float}, ...]
    """
    params = {"vs_currency": "usd", "days": days, "interval": "daily"}
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(
            f"{BASE}/coins/{coin_id}/market_chart", params=params, headers=HEADERS
        )
        if resp.status_code != 200:
            return None
        data = resp.json()
        prices  = data.get("prices", [])
        volumes = data.get("total_volumes", [])
        result = []
        for i, (ts, price) in enumerate(prices):
            from datetime import datetime, timezone
            date_str = datetime.fromtimestamp(ts / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
            vol = volumes[i][1] if i < len(volumes) else 0
            result.append({"date": date_str, "price": price, "volume": vol})
        return result
