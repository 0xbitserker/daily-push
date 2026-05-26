"""AI Market Analyst — 基于异动数据生成深度市场洞察 + 交易提示"""
import asyncio
from google import genai
import config

_client = None


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client(api_key=config.GEMINI_API_KEY)
    return _client


async def _gemini_with_retry(prompt: str, max_retries: int = 3) -> str:
    """带指数退避重试的 Gemini 调用，429 时自动等待。"""
    client = _get_client()
    for attempt in range(max_retries):
        try:
            await asyncio.sleep(2 * attempt)  # 0s, 2s, 4s
            resp = client.models.generate_content(
                model=config.GEMINI_MODEL,
                contents=prompt,
            )
            return resp.text.strip()
        except Exception as e:
            err_str = str(e)
            if "429" in err_str or "Rate limit" in err_str or "Too Many Requests" in err_str:
                if attempt < max_retries - 1:
                    wait = 5 * (2 ** attempt)
                    print(f"  [Gemini] 429 rate limit, waiting {wait}s (attempt {attempt+1}/{max_retries})...")
                    await asyncio.sleep(wait)
                    continue
            if attempt == max_retries - 1:
                raise
    return ""


async def generate_market_insights(
    price_anomalies: list[dict],
    funding_anomalies: list[dict],
    stablecoin: dict,
    top_movers: list[dict],
    market_overview: dict,
    session: str = "morning",
) -> list[str]:
    """
    基于异动数据，让 AI 生成 2-3 条深度市场洞察。
    返回: ["insight 1", "insight 2", ...]
    """
    # 构建上下文
    context_parts = []

    # 价格异动
    if price_anomalies:
        price_lines = []
        for a in price_anomalies[:6]:
            tags = " | ".join(a.get("tags", []))
            chg = a.get("change", 0)
            price_lines.append(f"- {a['symbol']}: {tags} ({chg:+.1f}%)")
        context_parts.append(f"Price Anomalies:\n{chr(10).join(price_lines)}")

    # 资金费率异动
    if funding_anomalies:
        fr_lines = []
        for a in funding_anomalies[:5]:
            tags = " | ".join(a.get("tags", []))
            fr_lines.append(f"- {a['symbol']}: {tags}")
        context_parts.append(f"Funding Rate Anomalies:\n{chr(10).join(fr_lines)}")

    # 稳定币
    change_7d = stablecoin.get("change_7d", 0)
    total = stablecoin.get("total_mcap", 0)
    if total > 0:
        direction = "+" if change_7d > 0 else ""
        context_parts.append(
            f"Stablecoin Supply: ${total/1e9:.1f}B total, "
            f"{direction}${abs(change_7d)/1e9:.2f}B 7d change"
        )

    # Top movers
    if top_movers:
        mover_lines = []
        for m in top_movers[:5]:
            sym = m.get("symbol", "").replace("USDT", "")
            try:
                chg = float(m.get("priceChangePercent", 0))
            except (ValueError, TypeError):
                chg = 0
            mover_lines.append(f"- {sym}: {chg:+.1f}%")
        context_parts.append(f"Top Movers (Binance Perp):\n{chr(10).join(mover_lines)}")

    # BTC/ETH 基础
    btc_price = market_overview.get("btc_price", 0)
    eth_price = market_overview.get("eth_price", 0)
    btc_change = market_overview.get("btc_change_24h", 0)
    eth_change = market_overview.get("eth_change_24h", 0)
    if btc_price:
        context_parts.append(
            f"BTC: ${btc_price:,.0f} ({btc_change:+.1f}%) | "
            f"ETH: ${eth_price:,.0f} ({eth_change:+.1f}%)"
        )

    if not context_parts:
        return []

    # Session-specific analysis angle
    session_prompt = {
        "morning": (
            "Focus on: overnight US market recap, Asia session outlook, "
            "what happened while traders slept, key levels to watch today, "
            "funding rate implications for day session positioning."
        ),
        "evening": (
            "Focus on: today's full session recap, daily close analysis, "
            "overnight US session positioning, funding rate snapshot for next 8h, "
            "risk levels going into the night session."
        ),
    }
    focus = session_prompt.get(session, session_prompt["morning"])

    prompt = f"""You are a senior crypto derivatives analyst writing a daily briefing for active perp traders.

This is the {session.upper()} session brief. {focus}

Based on the market data below, generate exactly 2-3 concise market insights (each max 25 words).
Be specific with data points. Use English.

Format each insight as:
▸ [insight text]

Market Data:
{chr(10).join(context_parts)}"""

    try:
        text = await _gemini_with_retry(prompt)
        insights = []
        for line in text.split("\n"):
            line = line.strip()
            if not line:
                continue
            # Strip common bullet markers
            cleaned = line
            for prefix in ("▸", "•", "–", "-", "*", "►"):
                if cleaned.startswith(prefix):
                    cleaned = cleaned[len(prefix):].strip()
                    break
            # Accept any substantive line as an insight
            if cleaned and len(cleaned) > 10:
                insights.append(cleaned)
        # If no structured lines matched, split by sentences
        if not insights and len(text) > 20:
            import re
            sentences = re.split(r'(?<=[.!?])\s+', text)
            for s in sentences:
                s = s.strip()
                if len(s) > 15:
                    insights.append(s)
        return insights[:3]
    except Exception as e:
        print(f"  [AI Analysis] Gemini error: {e} — using rule-based fallback")
        insights = []
        # 价格异动
        big_pumps = [a for a in price_anomalies if a.get("change", 0) >= 10]
        big_dumps = [a for a in price_anomalies if a.get("change", 0) <= -10]
        if big_pumps:
            insights.append(f"{big_pumps[0]['symbol']} surged {big_pumps[0]['change']:+.1f}% — watch for continuation or mean reversion.")
        if big_dumps:
            insights.append(f"{big_dumps[0]['symbol']} dumped {big_dumps[0]['change']:+.1f}% — check for liquidation cascades.")
        # 资金费率异动
        neg_fr = [a for a in funding_anomalies if a.get("fr", 0) < -0.001]
        pos_fr = [a for a in funding_anomalies if a.get("fr", 0) > 0.001]
        if neg_fr:
            insights.append(f"Negative funding on {neg_fr[0]['symbol']} ({neg_fr[0]['fr']*100:.3f}%) — shorts paying, potential squeeze setup.")
        if pos_fr:
            insights.append(f"High positive funding on {pos_fr[0]['symbol']} ({pos_fr[0]['fr']*100:.3f}%) — longs crowded, squeeze risk.")
        # F&G
        fg = market_overview.get("fear_greed", {})
        fg_score = fg.get("score")
        if fg_score is not None:
            if fg_score < 30:
                insights.append(f"F&G at {fg_score} (Fear) — contrarian buy zone if fundamentals hold.")
            elif fg_score > 70:
                insights.append(f"F&G at {fg_score} (Greed) — market overextended, consider taking profits.")
        return insights[:3]


async def generate_trading_brief(
    price_anomalies: list[dict],
    funding_anomalies: list[dict],
    stablecoin: dict,
    kol_sentiment: str,
    signal_reasons: dict,
    session: str = "morning",
) -> dict:
    """
    生成交易提示：综合评分 + 关键关注点。
    返回: {
        score: "BULLISH" / "BEARISH" / "NEUTRAL",
        confidence: int (1-5),
        key_levels: ["BTC resistance at $X", ...],
        watch_list: ["COIN — reason", ...],
        risks: ["risk description", ...],
    }
    """
    # 构建上下文
    context_lines = []

    # 异动汇总
    big_pumps = [a for a in price_anomalies if a.get("change", 0) >= 15]
    big_dumps = [a for a in price_anomalies if a.get("change", 0) <= -15]
    if big_pumps:
        context_lines.append(
            f"Strong pumps (15%+): {', '.join(a['symbol'] for a in big_pumps[:5])}"
        )
    if big_dumps:
        context_lines.append(
            f"Sharp dumps (-15%+): {', '.join(a['symbol'] for a in big_dumps[:5])}"
        )

    # Funding extremes
    crowded_longs = [a for a in funding_anomalies if a.get("fr", 0) > 0.0005]
    crowded_shorts = [a for a in funding_anomalies if a.get("fr", 0) < -0.0005]
    if crowded_longs:
        items = [f"{a['symbol']}({a['fr']*100:.4f}%)" for a in crowded_longs[:5]]
        context_lines.append(f"Crowded longs: {', '.join(items)}")
    if crowded_shorts:
        items = [f"{a['symbol']}({a['fr']*100:.4f}%)" for a in crowded_shorts[:5]]
        context_lines.append(f"Crowded shorts: {', '.join(items)}")

    # Stablecoin
    change_7d = stablecoin.get("change_7d", 0)
    if abs(change_7d) > 500_000_000:
        direction = "inflow" if change_7d > 0 else "outflow"
        context_lines.append(f"Stablecoin {direction}: ${abs(change_7d)/1e9:.2f}B this week")

    # Signal reasons
    if signal_reasons:
        for category in ("bullish", "bearish", "neutral"):
            reasons = signal_reasons.get(category, [])
            for r in reasons[:2]:
                context_lines.append(f"[{category}] {r}")

    context_lines.append(f"KOL sentiment: {kol_sentiment}")

    if not context_lines:
        return {
            "score": "NEUTRAL",
            "confidence": 2,
            "key_levels": [],
            "watch_list": [],
            "risks": [],
        }

    # Session-specific trading angle
    trading_focus = {
        "morning": (
            "Provide actionable guidance for the ASIA DAY SESSION ahead. "
            "Suggest entry zones, breakout levels to watch, and morning momentum plays."
        ),
        "evening": (
            "Provide actionable guidance for the US OVERNIGHT SESSION ahead. "
            "Suggest position sizing for night trades, key levels for stop-loss, "
            "and whether to carry positions overnight."
        ),
    }
    focus_line = trading_focus.get(session, trading_focus["morning"])

    prompt = f"""You are a perp trading strategist. {focus_line}

Based on the market data below, provide:

1. Overall bias: BULLISH, BEARISH, or NEUTRAL
2. Confidence: 1-5 scale
3. Key levels: 2-3 critical price levels to watch (e.g. "BTC resistance at $72K")
4. Watch list: 2-3 tokens worth attention today with brief reason
5. Risks: 1-2 risk factors traders should be aware of

Format EXACTLY as:
BIAS: [BULLISH/BEARISH/NEUTRAL]
CONFIDENCE: [1-5]
LEVELS:
- [level 1]
- [level 2]
WATCH:
- [token — reason]
- [token — reason]
RISKS:
- [risk 1]
- [risk 2]

Market Data:
{chr(10).join(context_lines)}"""

    try:
        text = await _gemini_with_retry(prompt)
        result = {
            "score": "NEUTRAL",
            "confidence": 2,
            "key_levels": [],
            "watch_list": [],
            "risks": [],
        }

        current_section = None
        for line in text.split("\n"):
            line = line.strip()
            if not line:
                continue

            if line.startswith("BIAS:"):
                word = line.split(":")[1].strip().upper()
                if word in ("BULLISH", "BEARISH", "NEUTRAL"):
                    result["score"] = word
            elif line.startswith("CONFIDENCE:"):
                try:
                    result["confidence"] = int(line.split(":")[1].strip())
                except (ValueError, IndexError):
                    pass
            elif line.startswith("LEVELS:"):
                current_section = "levels"
            elif line.startswith("WATCH:"):
                current_section = "watch"
            elif line.startswith("RISKS:"):
                current_section = "risks"
            elif line.startswith("- "):
                content = line[2:].strip()
                if current_section == "levels":
                    result["key_levels"].append(content)
                elif current_section == "watch":
                    result["watch_list"].append(content)
                elif current_section == "risks":
                    result["risks"].append(content)

        return result
    except Exception as e:
        print(f"  [Trading Brief] Gemini error: {e} — using rule-based fallback")
        # Rule-based fallback
        bullish_count = len(signal_reasons.get("bullish", []))
        bearish_count = len(signal_reasons.get("bearish", []))
        if bullish_count > bearish_count:
            score = "BULLISH"
            confidence = min(3 + bullish_count, 5)
        elif bearish_count > bullish_count:
            score = "BEARISH"
            confidence = min(3 + bearish_count, 5)
        else:
            score = "NEUTRAL"
            confidence = 2

        key_levels = []
        for a in price_anomalies[:3]:
            sym = a["symbol"]
            chg = a["change"]
            if chg > 15:
                key_levels.append(f"{sym} resistance (pumped +{chg:.1f}%)")
            elif chg < -15:
                key_levels.append(f"{sym} support (dumped {chg:.1f}%)")

        watch_list = []
        for a in funding_anomalies[:3]:
            watch_list.append(f"{a['symbol']} — funding {a['fr']*100:.4f}%")

        risks = []
        change_7d = stablecoin.get("change_7d", 0)
        if change_7d < -1e9:
            risks.append(f"Stablecoin outflow ${abs(change_7d)/1e9:.1f}B — capital exiting")
        if not key_levels:
            risks.append("No major anomalies — range-bound session likely")

        return {
            "score": score,
            "confidence": confidence,
            "key_levels": key_levels[:3],
            "watch_list": watch_list[:3],
            "risks": risks[:2],
        }
