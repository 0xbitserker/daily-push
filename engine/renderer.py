"""HTML 模板渲染 — PopDEX 交易员作战简报 + Telegram 消息自动拆分"""
import html


MAX_MSG_LEN = 4096  # Telegram 单条消息上限


def _fmt_volume(v: float) -> str:
    if v >= 1e12:
        return f"${v/1e12:.2f}T"
    if v >= 1e9:
        return f"${v/1e9:.2f}B"
    if v >= 1e6:
        return f"${v/1e6:.0f}M"
    return f"${v:.0f}"


def _esc(text: str) -> str:
    """HTML-escape user-supplied text to prevent injection."""
    return html.escape(str(text))


def render_daily(
    date_str:          str,
    market_overview:   dict,             # {btc_price, eth_price, btc_change, eth_change, total_mcap, total_change, btc_dom, fear_greed, trending}
    price_anomalies:   list[dict],       # [{symbol, tags, change, volume}, ...]
    funding_anomalies: list[dict],       # [{symbol, fr, tags}, ...]
    market_insights:   list[str],        # AI 生成的市场洞察
    kol_summaries:     list[dict],       # [{username, summary}, ...]
    news_summaries:    list[str],        # 新闻摘要列表
    stablecoin:        dict,             # {total_mcap, change_7d, coins}
    trading_brief:     dict,             # {score, confidence, key_levels, watch_list, risks}
    session:           str = "morning",
) -> str:
    """渲染完整作战简报 HTML 文本 (Telegram HTML parse_mode)。"""
    lines = []

    # Session-specific header
    session_config = {
        "morning": {
            "icon": "☀️",
            "title": "PopDEX Morning Brief",
            "subtitle": "Overnight Recap & Day Ahead",
            "brief_title": "Day Session Playbook",
            "brief_icon": "🎯",
            "footer_hint": "Good morning, traders",
        },
        "evening": {
            "icon": "🌙",
            "title": "PopDEX Evening Brief",
            "subtitle": "Today's Wrap & Night Ahead",
            "brief_title": "Overnight Playbook",
            "brief_icon": "🎯",
            "footer_hint": "Good evening, traders",
        },
    }
    sc = session_config.get(session, session_config["morning"])

    # ── Header ────────────────────────────────────────────────────────────────
    lines.append(f"{sc['icon']} <b>{sc['title']}</b> | {_esc(date_str)}")
    lines.append(f"  <i>{sc['subtitle']}</i>")
    lines.append("━━━━━━━━━━━━━━━━━━━━━━")

    # ── Section 1: 市场概况 ──────────────────────────────────────────────────
    lines.append("")
    lines.append("📊 <b>Market Overview</b>")

    btc_price = market_overview.get("btc_price", 0)
    eth_price = market_overview.get("eth_price", 0)
    btc_ch = market_overview.get("btc_change_24h", 0)
    eth_ch = market_overview.get("eth_change_24h", 0)

    if btc_price:
        btc_icon = "🔴" if btc_ch >= 0 else "🟢"
        eth_icon = "🔴" if eth_ch >= 0 else "🟢"
        lines.append(f"  BTC {_esc('${:,.0f}'.format(btc_price))} {btc_icon} {btc_ch:+.1f}%")
        lines.append(f"  ETH {_esc('${:,.0f}'.format(eth_price))} {eth_icon} {eth_ch:+.1f}%")

    total_mcap = market_overview.get("total_mcap", 0)
    total_ch = market_overview.get("total_change_24h", 0)
    btc_dom = market_overview.get("btc_dom", 0)
    if total_mcap:
        mcap_icon = "🔴" if total_ch >= 0 else "🟢"
        lines.append(
            f"  MC {_esc(_fmt_volume(total_mcap))} {mcap_icon} {total_ch:+.1f}% | "
            f"BTC Dom {_esc(f'{btc_dom:.1f}%' if btc_dom else 'N/A')}"
        )

    # Fear & Greed Index
    fg = market_overview.get("fear_greed", {})
    fg_score = fg.get("score")
    if fg_score is not None:
        try:
            fg_score_int = int(fg_score)
            fg_icon = "🟢" if fg_score_int < 40 else ("🔴" if fg_score_int > 60 else "⚪")
        except (ValueError, TypeError):
            fg_icon = "⚪"
        fg_label = fg.get("label", "")
        lines.append(f"  F&G {fg_icon} <b>{fg_score}</b> {_esc(fg_label)}")

    # Trending coins
    trending = market_overview.get("trending", [])
    if trending:
        trend_syms = ", ".join(t.get("symbol", "") for t in trending[:5])
        lines.append(f"  🔥 Trending: {_esc(trend_syms)}")

    # Stablecoin supply
    sc_total = stablecoin.get("total_mcap", 0)
    sc_change = stablecoin.get("change_7d", 0)
    if sc_total > 0:
        sc_dir = "↑" if sc_change >= 0 else "↓"
        lines.append(
            f"  Stablecoin {_esc(_fmt_volume(sc_total))} | 7d {sc_dir}{_esc(_fmt_volume(abs(sc_change)))}"
        )

    # ── Section 2: 异动雷达 ──────────────────────────────────────────────────
    lines.append("")
    lines.append("━━━━━━━━━━━━━━━━━━━━━━")
    lines.append("⚡ <b>Anomaly Radar</b>")

    has_anomalies = False

    # 价格异动
    if price_anomalies:
        has_anomalies = True
        lines.append("  <b>Price Moves</b>")
        for a in price_anomalies[:6]:
            tag = _esc(" | ".join(a["tags"]))
            lines.append(f"    • <b>{_esc(a['symbol'])}</b> — {tag}")

    # 资金费率异动
    if funding_anomalies:
        has_anomalies = True
        lines.append("  <b>Funding Rate</b>")
        for a in funding_anomalies[:5]:
            tag = _esc(" | ".join(a["tags"]))
            lines.append(f"    • <b>{_esc(a['symbol'])}</b> — {tag}")

    if not has_anomalies:
        lines.append("  <i>No significant anomalies detected</i>")

    # ── Section 3: AI 深度分析 ──────────────────────────────────────────────────
    lines.append("")
    lines.append("━━━━━━━━━━━━━━━━━━━━━━")
    lines.append("🧠 <b>AI Analysis</b>")

    if market_insights:
        for insight in market_insights:
            lines.append(f"  {_esc(insight)}")
    else:
        lines.append("  <i>Insufficient data for analysis</i>")

    # ── Section 4: KOL Watch ──────────────────────────────────────────────────
    lines.append("")
    lines.append("━━━━━━━━━━━━━━━━━━━━━━")
    lines.append("👀 <b>KOL Watch</b>")

    if kol_summaries:
        for item in kol_summaries:
            username = _esc(item["username"])
            summary = _esc(item["summary"])
            lines.append(f"  <b>@{username}</b>")
            lines.append(f"    {summary}")
            lines.append("")
    else:
        lines.append("  <i>No significant KOL updates in the last 24h</i>")
        lines.append("")

    # ── Section 5: 要闻速览 ──────────────────────────────────────────────────
    lines.append("━━━━━━━━━━━━━━━━━━━━━━")
    lines.append("📰 <b>Key Headlines</b>")

    if news_summaries:
        for s in news_summaries[:5]:
            lines.append(f"  • {_esc(s)}")
    else:
        lines.append("  <i>No major headlines</i>")

    # ── Section 6: 交易提示 ──────────────────────────────────────────────────
    lines.append("")
    lines.append("━━━━━━━━━━━━━━━━━━━━━━")
    lines.append(f"{sc['brief_icon']} <b>{sc['brief_title']}</b>")

    score = trading_brief.get("score", "NEUTRAL")
    confidence = trading_brief.get("confidence", 2)

    # Score badge
    score_map = {
        "BULLISH":  ("🔴 BULLISH", "Long-biased, watch for pullback entries"),
        "BEARISH": ("🟢 BEARISH", "Short-biased, tight stops recommended"),
        "NEUTRAL":  ("⚪ NEUTRAL", "Range-Bound, avoid large positions"),
    }
    badge, hint = score_map.get(score, score_map["NEUTRAL"])
    conf_bar = "█" * confidence + "░" * (5 - confidence)
    lines.append(f"  <b>{badge}</b> | Conf {conf_bar} {confidence}/5")
    lines.append(f"  <i>{hint}</i>")

    # Key levels
    if trading_brief.get("key_levels"):
        lines.append("  <b>Levels</b>")
        for lv in trading_brief["key_levels"][:3]:
            lines.append(f"    • {_esc(lv)}")

    # Watch list
    if trading_brief.get("watch_list"):
        lines.append("  <b>Watch</b>")
        for w in trading_brief["watch_list"][:4]:
            lines.append(f"    • {_esc(w)}")

    # Risks
    if trading_brief.get("risks"):
        lines.append("  <b>Risks</b>")
        for r in trading_brief["risks"][:3]:
            lines.append(f"    ⚠️ {_esc(r)}")

    # ── Footer ───────────────────────────────────────────────────────────────
    lines.append("")
    sources = "CoinGecko · DeFiLlama · Bitget · MEXC · Hyperliquid · OKX · Gemini"
    lines.append(f"<i>{sc['footer_hint']} · PopDEX · {sources}</i>")

    return "\n".join(lines)


def split_messages(text: str, max_len: int = MAX_MSG_LEN) -> list[str]:
    """
    将长日报按 Section 拆分为多条 Telegram 消息。
    按 ━━━ 分隔线切割，每条 < max_len 字符。
    """
    if len(text) <= max_len:
        return [text]

    parts = text.split("━━━━━━━━━━━━━━━━━━━━━━")
    messages = []
    current = ""
    for part in parts:
        chunk = ("━━━━━━━━━━━━━━━━━━━━━━\n" if current else "") + part
        if len(current) + len(chunk) <= max_len:
            current += chunk
        else:
            if current:
                messages.append(current.strip())
            current = part
    if current:
        messages.append(current.strip())

    return messages or [text[:max_len]]
