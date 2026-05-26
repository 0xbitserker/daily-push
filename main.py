"""
PopDEX Daily Brief — 主入口
定位：交易员作战简报（行情分析 + 资产异动 + AI洞察）
用法：
  python main.py --session morning   # 早间简报 (9AM Beijing)
  python main.py --session evening   # 晚间简报 (9PM Beijing)
  python main.py                      # 默认 morning
"""
import asyncio
import argparse
import traceback
from datetime import datetime, timezone

import config
from sources.coingecko      import get_top_coins
from sources.defillama      import get_stablecoin_summary, get_perps_overview
from sources.multi_funding   import get_funding_rates_multi
from sources.market_sentiment import get_market_sentiment
from sources.binance         import get_top_movers_24h
from sources.rsshub          import get_all_kol_tweets
from sources.news_rss      import get_news, filter_macro_news
from sources.kol_fallback   import generate_trader_insights

from engine.anomaly         import detect_funding_anomalies, detect_price_anomalies
from engine.kol_summarizer  import summarize_kol_tweets, assess_kol_sentiment, summarize_news_headlines
from engine.signal          import score_signals
from engine.market_analyst  import generate_market_insights, generate_trading_brief
from engine.renderer        import render_daily, split_messages

from push.telegram import send_messages


async def run_daily(session: str = "morning"):
    session = session.lower()
    if session not in ("morning", "evening"):
        session = "morning"

    date_str = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
    session_label = "☀️ Morning" if session == "morning" else "🌙 Evening"
    print(f"[{date_str}] Starting PopDEX {session_label} Brief...")

    # ── 1. 并行拉取所有数据源 ───────────────────────────────────────
    print("  [1/5] Fetching data sources...")

    rsshub_configured = bool(config.RSSHUB_BASE_URL and "your-rsshub" not in config.RSSHUB_BASE_URL)

    (
        top_coins,
        stablecoin_data,
        funding_data,
        top_movers,
        market_sent,
        all_kol_tweets,
        news_items,
    ) = await asyncio.gather(
        get_top_coins(100),
        get_stablecoin_summary(),
        get_funding_rates_multi(),
        get_top_movers_24h(30),
        get_market_sentiment(),
        get_all_kol_tweets(config.KOL_LIST, hours=24) if rsshub_configured else asyncio.sleep(0, result=[]),
        asyncio.to_thread(get_news, 24, 80),
        return_exceptions=True,
    )

    # 处理异常（数据源失败时用空值兜底）
    def safe(val, default):
        return default if isinstance(val, Exception) else val

    top_coins       = safe(top_coins, [])
    stablecoin_data = safe(stablecoin_data, {"total_mcap": 0, "change_7d": 0, "coins": []})
    funding_data    = safe(funding_data, [])
    top_movers      = safe(top_movers, [])
    market_sent     = safe(market_sent, {"fear_greed": {"score": None}, "trending": []})
    all_kol_tweets  = safe(all_kol_tweets, [])
    news_items      = safe(news_items, [])

    if not funding_data:
        print("  [WARN] All funding sources failed, using empty list")

    # top_movers fallback
    if not top_movers:
        print("  [WARN] top_movers unavailable, deriving from CoinGecko...")
        sorted_co_ins = sorted(top_coins[:50], key=lambda c: abs(c.get("price_change_percentage_24h", 0)), reverse=True)
        top_movers = []
        for c in sorted_co_ins[:15]:
            top_movers.append({
                "symbol": (c.get("symbol") or "").upper() + "USDT",
                "priceChangePercent": c.get("price_change_percentage_24h", 0),
                "lastPrice": c.get("current_price", 0),
            })

    # ── 构建市场概况 ──────────────────────────────────────────────────
    market_overview = {}
    for coin in top_coins:
        sym = (coin.get("symbol") or "").upper()
        if sym == "BTC":
            market_overview["btc_price"] = coin.get("current_price", 0)
            market_overview["btc_change_24h"] = coin.get("price_change_percentage_24h", 0)
            market_overview["btc_dom"] = (
                coin.get("market_cap_percentage", {}).get("btc", 0)
                if isinstance(coin.get("market_cap_percentage"), dict) else 0
            )
        elif sym == "ETH":
            market_overview["eth_price"] = coin.get("current_price", 0)
            market_overview["eth_change_24h"] = coin.get("price_change_percentage_24h", 0)

    total_mcap = sum(((c.get("market_cap", 0) or 0) for c in top_coins[:50]))
    market_overview["total_mcap"] = total_mcap

    total_mcap_prev = total_mcap
    for coin in top_coins[:50]:
        mc = (coin.get("market_cap", 0) or 1)
        ch = (coin.get("price_change_percentage_24h", 0) or 0)
        total_mcap_prev -= mc * ch / (100 + ch) if ch != 0 else 0
    market_overview["total_change_24h"] = (
        ((total_mcap - total_mcap_prev) / total_mcap_prev * 100) if total_mcap_prev > 0 else 0
    )

    # Fear & Greed + Trending
    fg = market_sent.get("fear_greed", {})
    market_overview["fear_greed"] = fg
    market_overview["trending"] = market_sent.get("trending", [])

    print(f"  Data: {len(top_coins)} coins, {len(funding_data)} funding rates, "
          f"{len(all_kol_tweets)} KOL tweets, {len(news_items)} news items")

    # ── 2. 异动检测 ─────────────────────────────────────────────────
    print("  [2/5] Running anomaly detection...")
    price_anomalies   = detect_price_anomalies(top_coins)
    funding_anomalies = detect_funding_anomalies(funding_data)

    print(f"  Anomalies: {len(price_anomalies)} price, {len(funding_anomalies)} funding")

    # ── 3. KOL fallback（必须在异动检测之后）──────────────────────────
    kol_fallback_used = False
    if not all_kol_tweets and not rsshub_configured:
        print("  [KOL] RSSHub not deployed, generating synthetic KOL insights...")
        fear_greed_dict = market_sent.get("fear_greed", {})
        trending_list   = market_sent.get("trending", [])
        kol_fallback = await generate_trader_insights(
            top_movers, funding_anomalies, price_anomalies,
            fear_greed_dict, trending_list,
        )
        if kol_fallback:
            all_kol_tweets = kol_fallback
            kol_fallback_used = True
            print(f"  [KOL] Generated {len(kol_fallback)} synthetic insights")

    # ── 4. LLM 处理 ─────────────────────────────────────────────────
    print("  [3/5] Running LLM summarization...")
    # KOL fallback 数据已含 summary，直接使用；否则走正常摘要流程
    if kol_fallback_used:
        kol_summaries  = [
            {"username": t["username"], "summary": t["summary"]}
            for t in all_kol_tweets
        ]
    else:
        kol_summaries  = await summarize_kol_tweets(all_kol_tweets, top_n=5)
    kol_sentiment  = await assess_kol_sentiment(kol_summaries)
    macro_news     = filter_macro_news(news_items, top_n=5)
    news_summaries = await summarize_news_headlines(macro_news)

    print(f"  LLM: {len(kol_summaries)} KOL summaries, sentiment={kol_sentiment}, "
          f"{len(news_summaries)} news summaries")

    # ── 5. AI 深度分析 + 交易提示 ───────────────────────────────────
    print("  [4/5] Running AI market analysis...")
    market_insights = await generate_market_insights(
        price_anomalies=price_anomalies,
        funding_anomalies=funding_anomalies,
        stablecoin=stablecoin_data,
        top_movers=top_movers,
        market_overview=market_overview,
        session=session,
    )

    # 信号评分
    signal = score_signals(
        funding_anomalies=funding_anomalies,
        price_anomalies=price_anomalies,
        stablecoin=stablecoin_data,
        kol_sentiment=kol_sentiment,
    )

    # 交易提示
    trading_brief = await generate_trading_brief(
        price_anomalies=price_anomalies,
        funding_anomalies=funding_anomalies,
        stablecoin=stablecoin_data,
        kol_sentiment=kol_sentiment,
        signal_reasons=signal.get("reasons", {}),
        session=session,
    )

    print(f"  Insights: {len(market_insights)}, "
          f"Signal: Bullish {signal['bullish']} | Bearish {signal['bearish']} | Neutral {signal['neutral']}, "
          f"Trading: {trading_brief.get('score', 'N/A')}")

    # ── 6. 渲染 + 推送 ─────────────────────────────────────────────
    print("  [5/5] Rendering and pushing...")
    daily_text = render_daily(
        date_str=date_str,
        market_overview=market_overview,
        price_anomalies=price_anomalies,
        funding_anomalies=funding_anomalies,
        market_insights=market_insights,
        kol_summaries=kol_summaries,
        news_summaries=news_summaries,
        stablecoin=stablecoin_data,
        trading_brief=trading_brief,
        session=session,
    )

    messages = split_messages(daily_text)
    print(f"  Rendered: {len(daily_text)} chars -> {len(messages)} message(s)")

    success = await send_messages(messages)
    status = "SUCCESS" if success else "FAILED"
    print(f"  Push: {status}")
    return success


def main():
    parser = argparse.ArgumentParser(description="PopDEX Daily Brief")
    parser.add_argument(
        "--session", "-s",
        choices=["morning", "evening"],
        default=None,
        help="Brief session: morning (9AM) or evening (9PM Beijing time). "
             "Omit to auto-detect based on current hour (9→morning, 21→evening).",
    )
    args = parser.parse_args()

    # 自动判断 session：Railway Cron 每小时触发，只在 9 点和 21 点执行
    if args.session is None:
        beijing_hour = datetime.now(tz=timezone.utc).hour + 8
        beijing_hour = beijing_hour % 24
        if beijing_hour == 9:
            args.session = "morning"
        elif beijing_hour == 21:
            args.session = "evening"
        else:
            print(f"[SKIP] Current Beijing hour is {beijing_hour}, not a scheduled push time (9 or 21).")
            return

    try:
        asyncio.run(run_daily(session=args.session))
    except Exception:
        print("[FATAL] Unhandled exception:")
        traceback.print_exc()
        raise


if __name__ == "__main__":
    main()
