"""HTML 模板渲染 + Telegram 消息自动拆分"""
import html


MAX_MSG_LEN = 4096  # Telegram 单条消息上限


def _fmt_volume(v: float) -> str:
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
    kol_summaries:     list[dict],       # [{username, summary}, ...]
    price_anomalies:   list[dict],       # from anomaly.detect_price_anomalies
    funding_anomalies: list[dict],       # from anomaly.detect_funding_anomalies
    dex_volumes:       list[dict],       # from anomaly.detect_dex_volume_anomalies
    dex_announcements: dict,             # {dex_name: [tweet_text, ...]}
    news_summaries:    list[str],        # from kol_summarizer.summarize_news_headlines
    stablecoin:        dict,             # from defillama.get_stablecoin_summary
    signal:            dict,             # from signal.score_signals
) -> str:
    """渲染完整日报 HTML 文本 (Telegram HTML parse_mode)。"""
    lines = []

    # ── Header ────────────────────────────────────────────────────────────────
    lines.append(f"📰 <b>PopDEX Perp Daily</b> | {date_str}")
    lines.append("━━━━━━━━━━━━━━━━━━━━━━")

    # ── Section 1: KOL & Whale Watch ─────────────────────────────────────────
    lines.append("")
    lines.append("👤 <b>KOL &amp; Whale Watch</b>")
    if kol_summaries:
        for item in kol_summaries:
            username = _esc(item["username"])
            summary  = _esc(item["summary"])
            lines.append(f"<b>@{username}</b>")
            lines.append(summary)
            lines.append("")
    else:
        lines.append("<i>No significant KOL updates in the last 24h.</i>")
        lines.append("")

    # ── Section 2: Market Anomalies ───────────────────────────────────────────
    lines.append("━━━━━━━━━━━━━━━━━━━━━━")
    lines.append("🔥 <b>Market Anomalies</b>")

    if price_anomalies:
        for a in price_anomalies[:5]:
            tag = _esc(" | ".join(a["tags"]))
            lines.append(f"• <b>{_esc(a['symbol'])}</b> — {tag}")

    if funding_anomalies:
        for a in funding_anomalies[:3]:
            tag = _esc(" | ".join(a["tags"]))
            lines.append(f"• <b>{_esc(a['symbol'])}</b> — {tag}")

    if not price_anomalies and not funding_anomalies:
        lines.append("• No significant anomalies detected")

    # Stablecoin 供应变化
    change_7d = stablecoin.get("change_7d", 0)
    total     = stablecoin.get("total_mcap", 0)
    direction = "↑" if change_7d > 0 else "↓"
    lines.append(
        f"• <b>Stablecoin</b> — Total {_fmt_volume(total)} | 7d change "
        f"{direction}{_esc(_fmt_volume(abs(change_7d)))}"
    )
    lines.append("")

    # ── Section 3: Competitor Radar ───────────────────────────────────────────
    lines.append("━━━━━━━━━━━━━━━━━━━━━━")
    lines.append("⚔️ <b>Competitor Radar</b>")

    radar_items = []
    for dex in dex_volumes:
        name    = dex["name"]
        vol_24h = dex["vol_24h"]
        tags    = dex.get("tags", [])
        ann = dex_announcements.get(name, [])[:1]
        ann_text = f" — {_esc(ann[0][:80])}" if ann else ""

        if tags or ann:
            vol_str = _esc(_fmt_volume(vol_24h))
            tag_str = _esc(" | ".join(tags)) if tags else ""
            radar_items.append(
                f"• <b>{_esc(name)}</b> — {vol_str} 24h vol{' | ' + tag_str if tag_str else ''}{ann_text}"
            )

    if radar_items:
        lines.extend(radar_items[:6])
    else:
        lines.append("• No notable competitor updates")
    lines.append("")

    # ── Section 4: Macro & Headlines ─────────────────────────────────────────
    lines.append("━━━━━━━━━━━━━━━━━━━━━━")
    lines.append("🌍 <b>Macro &amp; Headlines</b>")

    if news_summaries:
        for s in news_summaries[:6]:
            lines.append(f"• {_esc(s)}")
    else:
        lines.append("• No major macro headlines in the last 24h")
    lines.append("")

    # ── Section 5: AI Signal ──────────────────────────────────────────────────
    lines.append("━━━━━━━━━━━━━━━━━━━━━━")
    b  = signal.get("bullish", 0)
    be = signal.get("bearish", 0)
    n  = signal.get("neutral", 0)
    lines.append(f"📊 <b>AI Signal: Bullish {b} | Bearish {be} | Neutral {n}</b>")
    lines.append("")
    lines.append("<i>Sources: CoinGecko · DeFiLlama · Binance · RSSHub · Gemini</i>")

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
