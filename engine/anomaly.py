"""异动检测引擎 — 基于规则阈值自动标记行情异动"""
from typing import Optional
import config


def detect_funding_anomalies(funding_data: list[dict]) -> list[dict]:
    """
    检测资金费率异动。
    funding_data: Binance premiumIndex 列表
    [{symbol, lastFundingRate, markPrice, ...}, ...]
    """
    anomalies = []
    for item in funding_data:
        symbol = item.get("symbol", "")
        if not symbol.endswith("USDT"):
            continue

        try:
            fr = float(item.get("lastFundingRate", 0))
        except (ValueError, TypeError):
            continue

        # 跳过小市值合约（只看有显示度的）
        try:
            mark_price = float(item.get("markPrice", 0))
        except (ValueError, TypeError):
            continue

        tags = []
        if fr > config.FUNDING_RATE_EXTREME_POS:
            tags.append(f"Funding +{fr*100:.4f}% ⚠️ 多头拥挤")
        elif fr < config.FUNDING_RATE_EXTREME_NEG:
            tags.append(f"Funding {fr*100:.4f}% ⚠️ 空头拥挤")
        elif abs(fr) > config.FUNDING_RATE_SPIKE_ABS:
            direction = "+" if fr > 0 else ""
            tags.append(f"Funding {direction}{fr*100:.4f}%")

        if tags:
            coin = symbol.replace("USDT", "")
            anomalies.append({
                "symbol":   coin,
                "fr":       fr,
                "tags":     tags,
                "severity": "high" if abs(fr) > config.FUNDING_RATE_EXTREME_POS else "medium",
            })

    # 按绝对值降序
    anomalies.sort(key=lambda x: abs(x["fr"]), reverse=True)
    return anomalies[:10]


def detect_price_anomalies(coins: list[dict]) -> list[dict]:
    """
    检测价格 / 交易量异动。
    coins: CoinGecko /coins/markets 返回数据
    """
    anomalies = []
    for coin in coins[:50]:  # 只看 Top 50
        change = coin.get("price_change_percentage_24h") or 0
        volume = coin.get("total_volume") or 0
        symbol = (coin.get("symbol") or "").upper()
        name   = coin.get("name", "")

        tags = []
        if change >= 15:
            tags.append(f"+{change:.1f}% 24h 🚀")
        elif change <= -15:
            tags.append(f"{change:.1f}% 24h 📉")
        elif change >= 8:
            tags.append(f"+{change:.1f}% 24h ↑")
        elif change <= -8:
            tags.append(f"{change:.1f}% 24h ↓")

        if tags:
            anomalies.append({
                "symbol": symbol,
                "name":   name,
                "change": change,
                "volume": volume,
                "tags":   tags,
            })

    anomalies.sort(key=lambda x: abs(x["change"]), reverse=True)
    return anomalies[:8]


def detect_dex_volume_anomalies(
    perps_overview: list[dict],
    dex_list: list[dict],
) -> list[dict]:
    """
    检测 Perp DEX 交易量异动。
    perps_overview: DeFiLlama /overview/perps protocols 列表
    """
    # 建立 slug → data 映射
    slug_map = {p.get("slug", "").lower(): p for p in perps_overview}
    # 也用 name 映射作为 fallback
    name_map = {p.get("name", "").lower(): p for p in perps_overview}

    anomalies = []
    for dex in dex_list:
        slug = dex.get("defillama_id", "").lower()
        data = slug_map.get(slug) or name_map.get(dex["name"].lower())
        if not data:
            continue

        vol_24h = data.get("total24h") or 0
        vol_7d  = data.get("total7d") or 0
        avg_7d  = vol_7d / 7 if vol_7d else 0

        if avg_7d == 0:
            continue

        ratio = vol_24h / avg_7d
        tags = []
        if ratio >= config.DEX_VOLUME_SPIKE_RATIO:
            tags.append(f"Volume ${vol_24h/1e9:.2f}B (+{(ratio-1)*100:.0f}% vs 7d avg) 🔥")
        elif ratio <= 0.5:
            tags.append(f"Volume ${vol_24h/1e9:.2f}B (-{(1-ratio)*100:.0f}% vs 7d avg) ❄️")

        # 即便没有异动也记录基础 volume（用于 Competitor Radar 板块）
        anomalies.append({
            "name":    dex["name"],
            "vol_24h": vol_24h,
            "avg_7d":  avg_7d,
            "ratio":   ratio,
            "tags":    tags,
            "change_1d": data.get("change_1d", 0),
        })

    anomalies.sort(key=lambda x: x["vol_24h"], reverse=True)
    return anomalies
