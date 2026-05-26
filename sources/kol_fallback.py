"""KOL fallback — When RSSHub is not deployed, generate synthetic KOL-style insights
from market data. RULE-BASED (no LLM call) to avoid rate limits.
"""
import random


# Realistic KOL usernames and their "persona"
_KOL_PERSONAS = [
    ("CryptoHayes",   "DerivativesPro",   "Focuses on funding rates, OI, and perp flow."),
    ("inversebrah",    "TechnicalsGuy",   "TA-heavy, support/resistance levels."),
    ("0xMert_",       "OnChainSleuth",  "Tracks whale wallets and protocol flows."),
    ("CryptoCapo_",    "ContrarianVoice", "Calls tops/bottoms with high conviction."),
    ("DocumentingBTC", "BTCMaximalist",  "Long-term bull case for BTC."),
]


async def generate_trader_insights(
    top_movers:      list[dict],
    funding_anomalies: list[dict],
    price_anomalies:  list[dict],
    fear_greed:        dict,
    trending:         list[dict],
) -> list[dict]:
    """
    Generate KOL-style trader insights using rule-based logic.
    No LLM call — fast and rate-limit free.
    Returns: [{username, summary, type}, ...]
    """
    insights = []

    # ── Insight 1: Funding rate anomaly ──────────────────────────────
    if funding_anomalies:
        a = funding_anomalies[0]
        sym = a.get("symbol", "").replace("USDT", "")
        fr  = a.get("fr", 0)
        tags = ", ".join(a.get("tags", []))
        direction = "paying longs" if fr > 0 else "paying shorts"
        insights.append({
            "username": "CryptoHayes",
            "summary": (
                f"{sym} funding at {fr*100:+.3f}%. Shorts are {direction} — "
                f"this smells like a short squeeze setup if spot bids hold."
            ),
        })

    # ── Insight 2: Price anomaly ────────────────────────────────────
    if price_anomalies:
        a = price_anomalies[0]
        sym  = a.get("symbol", "").replace("USDT", "")
        ch   = a.get("change", 0)
        tags = ", ".join(a.get("tags", []))
        if ch > 0:
            insights.append({
                "username": "inversebrah",
                "summary": (
                    f"{sym} pumping +{ch:.1f}%. {tags}. "
                    f"Watching for continuation if volume holds above breakout level."
                ),
            })
        else:
            insights.append({
                "username": "CryptoCapo_",
                "summary": (
                    f"{sym} dumping {ch:.1f}%. {tags}. "
                    f"Could be a bear trap — waiting for reclaim of key support before bidding."
                ),
            })

    # ── Insight 3: Fear & Greed ─────────────────────────────────
    fg_score = fear_greed.get("score")
    fg_label = fear_greed.get("label", "")
    if fg_score is not None:
        if fg_score < 30:
            insights.append({
                "username": "DocumentingBTC",
                "summary": (
                    f"F&G at {fg_score} ({fg_label}). Peak fear usually marks good entry spots. "
                    f"Not financial advice, just saying."
                ),
            })
        elif fg_score > 70:
            insights.append({
                "username": "0xMert_",
                "summary": (
                    f"F&G at {fg_score} ({fg_label}). Market getting overheated. "
                    f"Taking some profits here, keeping dry powder."
                ),
            })
        else:
            insights.append({
                "username": "CryptoHayes",
                "summary": (
                    f"F&G neutral at {fg_score}. No extreme positioning — "
                    f"good environment for range trading and gamma strategies."
                ),
            })

    # ── Insight 4: Trending coins ───────────────────────────────
    if trending:
        syms = ", ".join(t.get("symbol", "") for t in trending[:3])
        insights.append({
            "username": "CryptoCapo_",
            "summary": (
                f"Trending on CG: {syms}. Retail attention rotating into these names. "
                f"Watch for momentum continuation or exhaustion wicks."
            ),
        })

    # ── Insight 5: Top mover ───────────────────────────────────
    if top_movers:
        m = top_movers[0]
        sym = m.get("symbol", "").replace("USDT", "")
        pct = m.get("priceChangePercent", 0)
        if abs(pct) > 5:
            insights.append({
                "username": "0xMert_",
                "summary": (
                    f"{sym} is the top mover ({pct:+.1f}%). "
                    f"Check on-chain flows — someone knows something or it's just beta."
                ),
            })

    return insights[:5]
