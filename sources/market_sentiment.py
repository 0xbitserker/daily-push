"""Market sentiment data — Fear & Greed Index + CoinGecko Trending
Provides additional context for Market Overview and Anomaly Radar sections.
"""
import httpx


async def get_fear_greed() -> dict:
    """
    Fetch Crypto Fear & Greed Index from Alternative.me (free, no API key).
    Returns: {score: int, label: str, timestamp: str}
    Fallback: FearGreedChart.com if Alternative.me fails.
    """
    # Source 1: Alternative.me
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            resp = await c.get("https://api.alternative.me/fng/?limit=1")
            resp.raise_for_status()
            data = resp.json()
            d = data["data"][0]
            return {
                "score": int(d["value"]),
                "label": d["value_classification"],
                "timestamp": d.get("timestamp", ""),
                "source": "Alternative.me",
            }
    except Exception:
        pass

    # Source 2: FearGreedChart.com
    try:
        async with httpx.AsyncClient(timeout=10, follow_redirects=True) as c:
            resp = await c.get(
                "https://feargreedchart.com/api",
                params={"action": "crypto"},
            )
            if resp.status_code == 200:
                data = resp.json()
                fng = data.get("crypto_fng", {})
                score = fng.get("score")
                if score is not None:
                    return {
                        "score": int(score),
                        "label": fng.get("label", ""),
                        "timestamp": str(fng.get("ts", "")),
                        "source": "FearGreedChart",
                    }
    except Exception:
        pass

    return {"score": None, "label": "N/A", "timestamp": "", "source": ""}


async def get_trending_coins() -> list[dict]:
    """
    Fetch CoinGecko trending coins (free, no API key).
    Returns: [{name, symbol, market_cap_rank, price_btc}, ...]
    """
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            resp = await c.get("https://api.coingecko.com/api/v3/search/trending")
            resp.raise_for_status()
            data = resp.json()
            coins = data.get("coins", [])
            results = []
            for c_item in coins[:7]:
                item = c_item.get("item", {})
                results.append({
                    "name": item.get("name", ""),
                    "symbol": (item.get("symbol") or "").upper(),
                    "market_cap_rank": item.get("market_cap_rank"),
                    "price_btc": item.get("price_btc"),
                })
            return results
    except Exception:
        return []


async def get_market_sentiment() -> dict:
    """
    Fetch both fear/greed and trending in parallel.
    Returns: {fear_greed: {...}, trending: [...]}
    """
    import asyncio

    fg, trending = await asyncio.gather(
        get_fear_greed(),
        get_trending_coins(),
    )
    return {"fear_greed": fg, "trending": trending}
