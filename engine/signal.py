"""AI Signal 评分引擎 — 基于规则给出 Bullish / Bearish / Neutral 信号"""
import config


def score_signals(
    funding_anomalies: list[dict],
    price_anomalies:   list[dict],
    stablecoin:        dict,
    dex_volumes:       list[dict],
    kol_sentiment:     str = "neutral",  # "bullish" / "bearish" / "neutral"
) -> dict:
    """
    综合各维度数据，输出 AI Signal 评分。
    返回: {
        bullish: int,
        bearish: int,
        neutral: int,
        total: int,
        reasons: {bullish: [...], bearish: [...], neutral: [...]}
    }
    """
    bullish_reasons = []
    bearish_reasons = []
    neutral_reasons = []

    # ── 1. Funding Rate 信号 ─────────────────────────────────────────────────
    extreme_pos = [a for a in funding_anomalies if a["fr"] > config.FUNDING_RATE_EXTREME_POS]
    extreme_neg = [a for a in funding_anomalies if a["fr"] < config.FUNDING_RATE_EXTREME_NEG]

    if len(extreme_pos) >= 3:
        bearish_reasons.append(
            f"Funding rate extreme positive on {len(extreme_pos)} pairs (crowded longs)"
        )
    elif len(extreme_neg) >= 3:
        bullish_reasons.append(
            f"Funding rate extreme negative on {len(extreme_neg)} pairs (crowded shorts → squeeze potential)"
        )
    else:
        neutral_reasons.append("Funding rates within normal range")

    # ── 2. Stablecoin 供应 信号 ──────────────────────────────────────────────
    change_7d = stablecoin.get("change_7d", 0)
    if change_7d > config.STABLECOIN_INFLOW_THRESHOLD:
        bullish_reasons.append(
            f"Stablecoin supply +${change_7d/1e9:.1f}B this week → fresh capital entering"
        )
    elif change_7d < -config.STABLECOIN_OUTFLOW_THRESHOLD:
        bearish_reasons.append(
            f"Stablecoin supply -{abs(change_7d)/1e9:.1f}B this week → capital exiting"
        )
    else:
        neutral_reasons.append(
            f"Stablecoin supply change ${change_7d/1e6:.0f}M (stable)"
        )

    # ── 3. DEX Volume 信号 ───────────────────────────────────────────────────
    if dex_volumes:
        rising  = sum(1 for d in dex_volumes if d.get("ratio", 1) > 1.2)
        falling = sum(1 for d in dex_volumes if d.get("ratio", 1) < 0.8)
        total   = len(dex_volumes)

        if rising > total * 0.6:
            bullish_reasons.append(
                f"DEX volumes rising across {rising}/{total} tracked perp protocols"
            )
        elif falling > total * 0.6:
            bearish_reasons.append(
                f"DEX volumes declining across {falling}/{total} tracked perp protocols"
            )
        else:
            neutral_reasons.append("DEX volumes mixed across protocols")

    # ── 4. Price Momentum 信号 ───────────────────────────────────────────────
    big_pumps  = [a for a in price_anomalies if a["change"] >= 15]
    big_dumps  = [a for a in price_anomalies if a["change"] <= -15]

    if len(big_pumps) >= 3:
        bullish_reasons.append(
            f"{len(big_pumps)} tokens up 15%+ in 24h → broad risk-on momentum"
        )
    elif len(big_dumps) >= 3:
        bearish_reasons.append(
            f"{len(big_dumps)} tokens down 15%+ in 24h → broad risk-off selling"
        )
    else:
        neutral_reasons.append("Price momentum mixed — no broad directional bias")

    # ── 5. KOL Sentiment 信号 ────────────────────────────────────────────────
    if kol_sentiment == "bullish":
        bullish_reasons.append("KOL sentiment majority bullish")
    elif kol_sentiment == "bearish":
        bearish_reasons.append("KOL sentiment majority bearish")
    else:
        neutral_reasons.append("KOL sentiment mixed / neutral")

    return {
        "bullish": len(bullish_reasons),
        "bearish": len(bearish_reasons),
        "neutral": len(neutral_reasons),
        "total":   len(bullish_reasons) + len(bearish_reasons) + len(neutral_reasons),
        "reasons": {
            "bullish": bullish_reasons,
            "bearish": bearish_reasons,
            "neutral": neutral_reasons,
        },
    }
