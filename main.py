"""
PopDEX Perp Daily Push Tool — 主入口
每日 UTC 00:00 由 Railway Cron 触发
"""
import asyncio
import traceback
from datetime import datetime, timezone

import config
from sources.coingecko import get_top_coins
from sources.defillama  import get_perps_overview, get_stablecoin_summary
from sources.binance    import get_funding_rates, get_top_movers_24h
from sources.rsshub     import get_all_kol_tweets, get_dex_announcements
from sources.news_rss   import get_news, filter_macro_news

from engine.anomaly       import detect_funding_anomalies, detect_price_anomalies, detect_dex_volume_anomalies
from engine.kol_summarizer import summarize_kol_tweets, assess_kol_sentiment, summarize_news_headlines
from engine.signal        import score_signals
from engine.renderer      import render_daily, split_messages

from push.telegram import send_messages


async def run_daily():
    date_str = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
    print(f"[{date_str}] Starting PopDEX Daily generation...")

    # ── 1. 并行拉取所有数据源 ───────────────────────────────────────────────
    print("  [1/5] Fetching data sources...")
    (
        top_coins,
        perps_overview,
        stablecoin_data,
        funding_data,
        top_movers,
        all_kol_tweets,
        news_items,
    ) = await asyncio.gather(
        get_top_coins(100),
        get_perps_overview(),
        get_stablecoin_summary(),
        get_funding_rates(),           # 全量 Binance perp funding rates
        get_top_movers_24h(30),
        get_all_kol_tweets(config.KOL_LIST, hours=24),
        asyncio.to_thread(get_news, 24, 80),  # RSS 是同步的，用线程包装
        return_exceptions=True,
    )

    # 处理异常（数据源失败时用空值兜底）
    def safe(val, default):
        return default if isinstance(val, Exception) else val

    top_coins      = safe(top_coins, [])
    perps_overview = safe(perps_overview, [])
    stablecoin_data= safe(stablecoin_data, {"total_mcap": 0, "change_7d": 0, "coins": []})
    funding_data   = safe(funding_data, [])
    top_movers     = safe(top_movers, [])
    all_kol_tweets = safe(all_kol_tweets, [])
    news_items     = safe(news_items, [])

    print(f"  Data: {len(top_coins)} coins, {len(perps_overview)} perp protocols, "
          f"{len(funding_data)} funding rates, {len(all_kol_tweets)} KOL tweets, "
          f"{len(news_items)} news items")

    # ── 2. 拉取竞品 DEX 公告 ────────────────────────────────────────────────
    print("  [2/5] Fetching DEX announcements...")
    dex_announcement_tasks = {
        dex["name"]: get_dex_announcements(dex["twitter"], hours=24)
        for dex in config.DEX_LIST
    }
    dex_results = await asyncio.gather(*dex_announcement_tasks.values(), return_exceptions=True)
    dex_announcements = {}
    for dex, result in zip(config.DEX_LIST, dex_results):
        if isinstance(result, list):
            dex_announcements[dex["name"]] = [t["text"] for t in result[:2]]
        else:
            dex_announcements[dex["name"]] = []

    # ── 3. 异动检测 ─────────────────────────────────────────────────────────
    print("  [3/5] Running anomaly detection...")
    price_anomalies   = detect_price_anomalies(top_coins)
    funding_anomalies = detect_funding_anomalies(funding_data)
    dex_volumes       = detect_dex_volume_anomalies(perps_overview, config.DEX_LIST)

    print(f"  Anomalies: {len(price_anomalies)} price, "
          f"{len(funding_anomalies)} funding, {len(dex_volumes)} DEX volumes")

    # ── 4. LLM 处理 ─────────────────────────────────────────────────────────
    print("  [4/5] Running LLM summarization...")
    kol_summaries  = summarize_kol_tweets(all_kol_tweets, top_n=7)
    kol_sentiment  = assess_kol_sentiment(kol_summaries)
    macro_news     = filter_macro_news(news_items, top_n=6)
    news_summaries = summarize_news_headlines(macro_news)

    print(f"  LLM: {len(kol_summaries)} KOL summaries, sentiment={kol_sentiment}, "
          f"{len(news_summaries)} news summaries")

    # ── 5. 评分 + 渲染 ──────────────────────────────────────────────────────
    print("  [5/5] Scoring and rendering...")
    signal = score_signals(
        funding_anomalies=funding_anomalies,
        price_anomalies=price_anomalies,
        stablecoin=stablecoin_data,
        dex_volumes=dex_volumes,
        kol_sentiment=kol_sentiment,
    )

    daily_text = render_daily(
        date_str=date_str,
        kol_summaries=kol_summaries,
        price_anomalies=price_anomalies,
        funding_anomalies=funding_anomalies,
        dex_volumes=dex_volumes,
        dex_announcements=dex_announcements,
        news_summaries=news_summaries,
        stablecoin=stablecoin_data,
        signal=signal,
    )

    messages = split_messages(daily_text)
    print(f"  Rendered: {len(daily_text)} chars → {len(messages)} message(s)")
    print(f"  Signal: Bullish {signal['bullish']} | Bearish {signal['bearish']} | Neutral {signal['neutral']}")

    # ── 6. 推送 ────────────────────────────────────────────────────────────
    success = await send_messages(messages)
    status = "✅ SUCCESS" if success else "❌ FAILED"
    print(f"  Push: {status}")
    return success


def main():
    try:
        asyncio.run(run_daily())
    except Exception:
        print("[FATAL] Unhandled exception:")
        traceback.print_exc()
        raise


if __name__ == "__main__":
    main()
