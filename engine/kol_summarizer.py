"""Gemini LLM 摘要 — KOL 推文批量摘要 + AI Signal 语义评分"""
from google import genai
import config

_client = None


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client(api_key=config.GEMINI_API_KEY)
    return _client


def summarize_kol_tweets(tweets: list[dict], top_n: int = 7) -> list[dict]:
    """
    对筛选后的 KOL 推文批量生成摘要。
    tweets: [{username, text, priority, kol_type, ...}, ...]
    返回: [{username, summary}, ...]  (top_n 条)
    """
    if not tweets:
        return []

    # 按优先级取 top_n * 3 候选，再让 LLM 筛出最有价值的
    candidates = tweets[:top_n * 3]

    # 构建 prompt
    tweet_lines = []
    for i, t in enumerate(candidates):
        tweet_lines.append(f"[{i+1}] @{t['username']}: {t['text'][:300]}")

    prompt = f"""You are a crypto market analyst. Below are {len(candidates)} recent tweets from crypto KOLs.

Select the {top_n} most market-relevant tweets (ignore memes, price shilling, generic announcements).
For each selected tweet, write ONE concise English sentence (max 20 words) that captures the key market insight.

Format your response EXACTLY as:
@username: [one sentence summary]

Tweets:
{chr(10).join(tweet_lines)}"""

    try:
        client = _get_client()
        resp = client.models.generate_content(
            model=config.GEMINI_MODEL,
            contents=prompt,
        )
        text = resp.text.strip()
    except Exception as e:
        # LLM 失败时回退到简单截断
        return [
            {"username": t["username"], "summary": t["text"][:120]}
            for t in candidates[:top_n]
        ]

    # 解析输出: "@username: summary"
    results = []
    for line in text.split("\n"):
        line = line.strip()
        if line.startswith("@") and ": " in line:
            parts = line.split(": ", 1)
            username = parts[0].lstrip("@").strip()
            summary  = parts[1].strip()
            results.append({"username": username, "summary": summary})

    return results[:top_n]


def assess_kol_sentiment(summaries: list[dict]) -> str:
    """
    对 KOL 摘要整体做情绪判断: "bullish" / "bearish" / "neutral"
    """
    if not summaries:
        return "neutral"

    combined = " ".join(s["summary"] for s in summaries)
    prompt = f"""Based on these crypto KOL summaries, is the overall sentiment:
- bullish (optimistic, risk-on)
- bearish (pessimistic, risk-off)  
- neutral (mixed or unclear)

Summaries: {combined}

Reply with exactly ONE word: bullish, bearish, or neutral."""

    try:
        client = _get_client()
        resp = client.models.generate_content(
            model=config.GEMINI_MODEL,
            contents=prompt,
        )
        word = resp.text.strip().lower().split()[0]
        if word in ("bullish", "bearish", "neutral"):
            return word
    except Exception:
        pass
    return "neutral"


def summarize_news_headlines(news_items: list[dict]) -> list[str]:
    """
    对筛选后的新闻列表，生成简洁的一句话摘要列表。
    """
    if not news_items:
        return []

    lines = [f"- {item['title']}" for item in news_items]
    prompt = f"""You are a crypto market analyst. Summarize each headline in one clear English sentence (max 15 words).
Keep numbers if present. Be factual.

Format: • [summary]

Headlines:
{chr(10).join(lines)}"""

    try:
        client = _get_client()
        resp = client.models.generate_content(
            model=config.GEMINI_MODEL,
            contents=prompt,
        )
        summaries = []
        for line in resp.text.strip().split("\n"):
            line = line.strip()
            if line.startswith("•"):
                summaries.append(line[1:].strip())
            elif line.startswith("-"):
                summaries.append(line[1:].strip())
            elif line:
                summaries.append(line)
        return summaries[:len(news_items)]
    except Exception:
        # 回退：直接返回标题
        return [item["title"] for item in news_items]
