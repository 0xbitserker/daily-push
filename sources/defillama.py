"""DeFiLlama 数据源 — Funding Rate / OI / Perps Volume / Stablecoin"""
import httpx
from typing import Optional

BASE            = "https://api.llama.fi"
BASE_STABLECOIN = "https://stablecoins.llama.fi"
HEADERS = {"accept": "application/json"}


async def get_perps_overview() -> list[dict]:
    """
    拉取所有 Perp DEX 的 24h volume 概览。
    返回: [{name, slug, total24h, total7d, change_1d, ...}, ...]
    """
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.get(f"{BASE}/overview/perps", headers=HEADERS)
        resp.raise_for_status()
        data = resp.json()
        return data.get("protocols", [])


async def get_perp_volume_history(protocol_slug: str, days: int = 14) -> list[dict]:
    """
    拉取单个 Perp DEX 的日级 volume 历史。
    返回: [{date: str, volume: float}, ...]
    """
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(f"{BASE}/summary/derivatives/{protocol_slug}", headers=HEADERS)
        if resp.status_code != 200:
            return []
        data = resp.json()
        daily = data.get("totalDataChart", [])
        result = []
        for ts, vol in daily[-days:]:
            from datetime import datetime, timezone
            date_str = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")
            result.append({"date": date_str, "volume": vol})
        return result


async def get_funding_rate(protocol_slug: str) -> list[dict]:
    """
    拉取某协议的资金费率历史。
    返回: [{date, timestamp, symbol, fundingRate}, ...]
    """
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(
            f"{BASE}/derivatives/funding-rate/{protocol_slug}", headers=HEADERS
        )
        if resp.status_code != 200:
            return []
        return resp.json()


async def get_open_interest(protocol_slug: str) -> list[dict]:
    """
    拉取某协议的 OI 历史。
    返回: [{date, openInterest}, ...]
    """
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(
            f"{BASE}/derivatives/open-interest/{protocol_slug}", headers=HEADERS
        )
        if resp.status_code != 200:
            return []
        return resp.json()


async def get_stablecoin_summary() -> dict:
    """
    拉取全市场 stablecoin 总供应量 + 7d 变化。
    返回: {total_mcap: float, change_7d: float, coins: [...]}
    """
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(f"{BASE_STABLECOIN}/stablecoins", headers=HEADERS)
        resp.raise_for_status()
        data   = resp.json()
        coins  = data.get("peggedAssets", [])
        total  = sum(c.get("circulating", {}).get("peggedUSD", 0) for c in coins)
        total7d_ago = sum(
            c.get("circulatingPrevWeek", {}).get("peggedUSD", 0) for c in coins
        )
        return {
            "total_mcap": total,
            "change_7d":  total - total7d_ago,
            "coins": coins[:10],
        }
