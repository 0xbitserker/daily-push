"""RSSHub 数据源 — 通过自部署 RSSHub 实例拉取 Twitter KOL + 竞品 DEX 推文"""
import feedparser
import httpx
from datetime import datetime, timezone, timedelta
from typing import Optional
import config

RSSHUB_BASE = config.RSSHUB_BASE_URL


def _parse_feed_entries(feed_url: str, hours: int = 24) -> list[dict]:
    """
    解析 RSS/Atom feed，返回过去 N 小时内的条目。
    """
    try:
        feed = feedparser.parse(feed_url)
    except Exception:
        return []

    cutoff = datetime.now(tz=timezone.utc) - timedelta(hours=hours)
    results = []
    for entry in feed.entries:
        # 解析发布时间
        pub = None
        if hasattr(entry, "published_parsed") and entry.published_parsed:
            pub = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
        elif hasattr(entry, "updated_parsed") and entry.updated_parsed:
            pub = datetime(*entry.updated_parsed[:6], tzinfo=timezone.utc)

        if pub and pub < cutoff:
            continue  # 跳过 24h 之前的

        title   = getattr(entry, "title", "")
        summary = getattr(entry, "summary", "") or getattr(entry, "description", "")
        link    = getattr(entry, "link", "")

        # 过滤: 跳过纯转推 (RT @) 和空内容
        text = (title + " " + summary).strip()
        if text.startswith("RT @") or len(text) < 10:
            continue

        results.append({
            "author":    getattr(entry, "author", ""),
            "text":      text[:500],  # 截断防止过长
            "link":      link,
            "published": pub.isoformat() if pub else "",
        })

    return results


async def get_kol_tweets(username: str, hours: int = 24) -> list[dict]:
    """
    拉取单个 KOL 的推文（通过 RSSHub）。
    """
    if not RSSHUB_BASE:
        return []
    url = f"{RSSHUB_BASE}/twitter/user/{username}"
    return _parse_feed_entries(url, hours=hours)


async def get_all_kol_tweets(kol_list: list[dict], hours: int = 24) -> list[dict]:
    """
    批量拉取所有 KOL 的推文，返回合并列表（按优先级排序）。
    kol_list: config.KOL_LIST 格式 [{username, priority, type}, ...]
    """
    all_tweets = []
    for kol in kol_list:
        tweets = await get_kol_tweets(kol["username"], hours=hours)
        for t in tweets:
            t["username"] = kol["username"]
            t["priority"] = kol["priority"]
            t["kol_type"] = kol["type"]
        all_tweets.extend(tweets)

    # 按优先级排序（priority 值越小越靠前）
    all_tweets.sort(key=lambda x: (x["priority"], x.get("published", "")))
    return all_tweets


async def get_dex_announcements(twitter_handle: str, hours: int = 24) -> list[dict]:
    """
    拉取某 DEX 官方 Twitter 的公告推文。
    """
    return await get_kol_tweets(twitter_handle, hours=hours)
