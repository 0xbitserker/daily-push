"""Multi-exchange funding rate aggregation — Bitget + MEXC + Hyperliquid + OKX
When Binance returns 451, we fall back to these free public APIs.
All endpoints are public, no API key required.
"""
import httpx

# Top perp symbols to check (normalized to each exchange format)
_TOP_SYMBOLS = [
    "BTC", "ETH", "SOL", "BNB", "XRP", "DOGE", "ADA", "AVAX", "DOT", "LINK",
    "MATIC", "UNI", "ATOM", "FIL", "APT", "OP", "ARB", "NEAR", "SUI", "SEI",
    "WIF", "PEPE", "FLOKI", "PENDLE", "ENA", "ETHFI", "WLD", "TON", "TRX", "LTC",
    "BCH", "AAVE", "MKR", "SNX", "DYDX", "GMX", "BLUR", "JUP", "PYTH", "STRK",
    "TIA", "INJ", "RUNE", "SAGA", "JTO", "BOME", "NOT", "IO", "ZRO", "RENDER",
]


async def _fetch_bitget() -> list[dict]:
    """Bitget USDT futures tickers — ~574 symbols, includes fundingRate."""
    async with httpx.AsyncClient(timeout=15) as c:
        resp = await c.get(
            "https://api.bitget.com/api/v2/mix/market/tickers",
            params={"productType": "USDT-FUTURES", "limit": "100"},
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != "00000":
            return []
        results = []
        for t in data["data"]:
            try:
                fr = float(t.get("fundingRate", 0) or 0)
                mark = float(t.get("markPrice", 0) or 0)
                symbol = t.get("symbol", "")  # e.g. BTCUSDT
            except (ValueError, TypeError):
                continue
            base = symbol.replace("USDT", "").replace("BCH", "BCH")
            results.append({
                "symbol": symbol.upper(),
                "base": base,
                "lastFundingRate": fr,
                "markPrice": mark,
                "exchange": "bitget",
            })
        return results


async def _fetch_mexc() -> list[dict]:
    """MEXC contract tickers — includes fundingRate."""
    async with httpx.AsyncClient(timeout=15) as c:
        resp = await c.get(
            "https://contract.mexc.com/api/v1/contract/ticker",
        )
        if resp.status_code != 200:
            return []
        data = resp.json()
        if not isinstance(data, list):
            return []
        results = []
        for t in data:
            try:
                symbol = t.get("symbol", "")  # e.g. BTC_USDT
                fr = float(t.get("fundingRate", 0) or 0)
                mark = float(t.get("lastPrice", 0) or 0)
                vol = float(t.get("volume24h", 0) or 0)
            except (ValueError, TypeError):
                continue
            results.append({
                "symbol": symbol.replace("_", "").upper(),  # BTCUSDT
                "base": symbol.split("_")[0].upper() if "_" in symbol else symbol,
                "lastFundingRate": fr,
                "markPrice": mark,
                "volume24h": vol,
                "exchange": "mexc",
            })
        return results


async def _fetch_hyperliquid() -> list[dict]:
    """Hyperliquid perp DEX — ~230 assets with funding + OI."""
    async with httpx.AsyncClient(timeout=15) as c:
        resp = await c.post(
            "https://api.hyperliquid.xyz/info",
            json={"type": "metaAndAssetCtxs"},
        )
        resp.raise_for_status()
        data = resp.json()
        if not isinstance(data, list) or len(data) < 2:
            return []

        universe = data[0].get("universe", [])
        ctxs = data[1]
        if not isinstance(ctxs, list):
            return []

        results = []
        for i, u in enumerate(universe):
            if i >= len(ctxs):
                break
            cx = ctxs[i]
            try:
                name = u.get("name", "").upper()
                fr = float(cx.get("funding", 0) or 0)
                mark = float(cx.get("markPx", 0) or 0)
                oi = float(cx.get("openInterest", 0) or 0)
            except (ValueError, TypeError):
                continue
            results.append({
                "symbol": name + "USDT",
                "base": name,
                "lastFundingRate": fr,
                "markPrice": mark,
                "openInterest": oi,
                "exchange": "hyperliquid",
            })
        return results


async def _fetch_okx_batch(symbols: list[str] = None) -> list[dict]:
    """OKX public funding rate — batch by instId (BTC-USDT-SWAP format)."""
    if symbols is None:
        symbols = _TOP_SYMBOLS[:20]

    results = []
    async with httpx.AsyncClient(timeout=15) as c:
        for sym in symbols:
            try:
                resp = await c.get(
                    "https://www.okx.com/api/v5/public/funding-rate",
                    params={"instId": f"{sym}-USDT-SWAP"},
                )
                data = resp.json()
                if data.get("code") == "0" and data.get("data"):
                    d = data["data"][0]
                    results.append({
                        "symbol": sym + "USDT",
                        "base": sym,
                        "lastFundingRate": float(d.get("fundingRate", 0) or 0),
                        "nextFundingRate": float(d.get("nextFundingRate", 0) or 0),
                        "markPrice": 0,  # OKX funding endpoint doesn't include price
                        "exchange": "okx",
                    })
            except Exception:
                continue
    return results


async def get_funding_rates_multi() -> list[dict]:
    """
    Aggregate funding rates from multiple exchanges.
    Returns unified format: [{symbol, base, lastFundingRate, markPrice, exchange}, ...]
    Tries all sources in parallel; merges and deduplicates by base symbol.
    """
    import asyncio

    results = await asyncio.gather(
        _fetch_bitget(),
        _fetch_mexc(),
        _fetch_hyperliquid(),
        _fetch_okx_batch(),
        return_exceptions=True,
    )

    all_rates = []
    sources_used = []
    source_names = ["Bitget", "MEXC", "Hyperliquid", "OKX"]
    for i, r in enumerate(results):
        if isinstance(r, list) and r:
            all_rates.extend(r)
            sources_used.append(source_names[i])

    print(f"  [MULTI-FUNDING] Sources: {', '.join(sources_used)}, total rates: {len(all_rates)}")

    # Deduplicate: for each base symbol, keep the one with the highest absolute funding rate
    best = {}
    for r in all_rates:
        base = r.get("base", "").upper()
        fr = abs(r.get("lastFundingRate", 0))
        if not base:
            continue
        if base not in best or fr > abs(best[base].get("lastFundingRate", 0)):
            best[base] = r

    return list(best.values())
