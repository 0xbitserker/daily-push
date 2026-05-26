"""新闻 RSS 聚合 — CoinDesk / CoinTelegraph / Decrypt / TheBlock"""
import feedparser
from datetime import datetime, timezone, timedelta
import config


def get_news(hours: int = 24, max_items: int = 50) -> list[dict]:
    """
    从所有配置的 RSS 源拉取过去 N 小时的新闻。
    返回: [{title, summary, link, source, published}, ...]
    """
    cutoff = datetime.now(tz=timezone.utc) - timedelta(hours=hours)
    all_items = []

    for feed_cfg in config.NEWS_RSS_FEEDS:
        try:
            feed = feedparser.parse(feed_cfg["url"])
        except Exception:
            continue

        for entry in feed.entries[:30]:  # 每个源最多取 30 条
            pub = None
            if hasattr(entry, "published_parsed") and entry.published_parsed:
                pub = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)

            if pub and pub < cutoff:
                continue

            title   = getattr(entry, "title", "")
            summary = getattr(entry, "summary", "")[:300]
            link    = getattr(entry, "link", "")

            # 关键词过滤
            text_lower = (title + " " + summary).lower()
            if not any(kw in text_lower for kw in config.NEWS_KEYWORDS):
                continue

            all_items.append({
                "title":     title,
                "summary":   summary,
                "link":      link,
                "source":    feed_cfg["name"],
                "published": pub.isoformat() if pub else "",
            })

    # 去重（相同标题只保留一条）
    seen = set()
    deduped = []
    for item in all_items:
        key = item["title"].lower()[:60]
        if key not in seen:
            seen.add(key)
            deduped.append(item)

    # 按发布时间倒序，取 top N
    deduped.sort(key=lambda x: x["published"], reverse=True)
    return deduped[:max_items]


def filter_macro_news(news_items: list[dict], top_n: int = 6) -> list[dict]:
    """
    从新闻列表中筛选宏观/监管类高优先级新闻。
    优先级: 爆仓/黑客 > 监管 > 宏观数据 > 一般行业新闻
    """
    priority_keywords = {
        1: ["hack", "exploit", "rug", "drained", "attack", "liquidation", "$"],
        2: ["sec", "cftc", "regulation", "ban", "arrest", "court", "lawsuit"],
        3: ["fed", "fomc", "cpi", "inflation", "rate", "etf", "approval"],
        4: ["bitcoin", "btc", "ethereum", "eth", "ath", "record", "billion"],
    }

    def get_priority(item: dict) -> int:
        text = (item["title"] + " " + item["summary"]).lower()
        for p, keywords in sorted(priority_keywords.items()):
            if any(kw in text for kw in keywords):
                return p
        return 5

    scored = [(get_priority(item), item) for item in news_items]
    scored.sort(key=lambda x: (x[0], x[1]["published"]))
    return [item for _, item in scored[:top_n]]
