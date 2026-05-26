import os
from dotenv import load_dotenv

load_dotenv()

# ── Credentials ──────────────────────────────────────────────────────────────
TWITTER_AUTH_TOKEN  = os.getenv("TWITTER_AUTH_TOKEN", "")
GEMINI_API_KEY      = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL        = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
TG_BOT_TOKEN        = os.getenv("TG_BOT_TOKEN", "")
TG_CHANNEL_ID       = os.getenv("TG_CHANNEL_ID", "")
TG_TOPIC_ID         = int(os.getenv("TG_TOPIC_ID", "0")) or None
RSSHUB_BASE_URL     = os.getenv("RSSHUB_BASE_URL", "").rstrip("/")
DEBUG_MODE          = os.getenv("DEBUG_MODE", "0") == "1"

# ── Anomaly thresholds ────────────────────────────────────────────────────────
FUNDING_RATE_SPIKE_ABS   = 0.0001   # 0.01% — 标记阈值
FUNDING_RATE_EXTREME_POS = 0.0005   # 0.05% — 多头拥挤预警
FUNDING_RATE_EXTREME_NEG = -0.0005  # -0.05% — 空头拥挤预警
OI_CHANGE_THRESHOLD      = 0.15     # 15% OI 变化
VOLUME_SPIKE_RATIO       = 2.0      # 24h volume / 7d avg > 2x
DEX_VOLUME_SPIKE_RATIO   = 1.5      # DEX 24h volume 较 7d avg 增幅

# ── AI Signal scoring ─────────────────────────────────────────────────────────
STABLECOIN_INFLOW_THRESHOLD  = 1_000_000_000   # $1B/周
STABLECOIN_OUTFLOW_THRESHOLD = 500_000_000     # $500M/周
BTC_PRICE_DROP_THRESHOLD     = -0.05           # -5%

# ── KOL list ─────────────────────────────────────────────────────────────────
# 优先级权重: 1(最高) → 5(最低)
KOL_LIST = [
    # ── Core perp / derivatives KOLs ──
    {"username": "HyperliquidX",   "priority": 1, "type": "dex"},
    {"username": "dYdX",           "priority": 1, "type": "dex"},
    {"username": "ApeX_Protocol",  "priority": 1, "type": "dex"},
    {"username": "aevo_xyz",       "priority": 1, "type": "dex"},
    {"username": "GMX_IO",         "priority": 1, "type": "dex"},
    {"username": "DriftProtocol",  "priority": 1, "type": "dex"},
    {"username": "StandX_io",      "priority": 1, "type": "dex"},
    {"username": "GRVTofficial",   "priority": 1, "type": "dex"},
    # ── On-chain analytics ──
    {"username": "glassnode",      "priority": 1, "type": "analytics"},
    {"username": "DefiLlama",      "priority": 1, "type": "analytics"},
    {"username": "coinglass_com",  "priority": 2, "type": "analytics"},
    {"username": "TheBlock__",     "priority": 2, "type": "media"},
    # ── Macro / markets ──
    {"username": "WatcherGuru",    "priority": 2, "type": "macro"},
    {"username": "CryptoHayes",    "priority": 2, "type": "trader"},
    {"username": "DocumentingBTC", "priority": 2, "type": "trader"},
    {"username": "inversebrah",    "priority": 2, "type": "trader"},
    {"username": "0xMert_",        "priority": 2, "type": "dev"},
    {"username": "PaulB_crypto",   "priority": 3, "type": "trader"},
    {"username": "CryptoCapo_",    "priority": 3, "type": "trader"},
    {"username": "il_Capo_Of_Crypto", "priority": 3, "type": "trader"},
    {"username": "CryptoWhale",    "priority": 2, "type": "whale"},
    {"username": "lookonchain",    "priority": 1, "type": "whale"},
    {"username": "OnchainLens",    "priority": 2, "type": "whale"},
    {"username": "spotonchain",    "priority": 2, "type": "whale"},
    # ── DeFi / protocol ──
    {"username": "Uniswap",        "priority": 3, "type": "protocol"},
    {"username": "aave",           "priority": 3, "type": "protocol"},
    {"username": "compoundfinance","priority": 3, "type": "protocol"},
    {"username": "MakerDAO",       "priority": 3, "type": "protocol"},
    # ── News ──
    {"username": "CoinDesk",       "priority": 3, "type": "media"},
    {"username": "Cointelegraph",  "priority": 3, "type": "media"},
    {"username": "DecryptMedia",   "priority": 3, "type": "media"},
]

# ── News RSS feeds ────────────────────────────────────────────────────────────
NEWS_RSS_FEEDS = [
    {"name": "CoinDesk",      "url": "https://www.coindesk.com/arc/outboundfeeds/rss/"},
    {"name": "CoinTelegraph", "url": "https://cointelegraph.com/rss"},
    {"name": "Decrypt",       "url": "https://decrypt.co/feed"},
    {"name": "TheBlock",      "url": "https://www.theblock.co/rss.xml"},
    {"name": "Reuters Crypto","url": "https://feeds.reuters.com/reuters/technologyNews"},
]

# Keywords for news filtering (case-insensitive)
NEWS_KEYWORDS = [
    "bitcoin", "btc", "ethereum", "eth", "crypto", "perp", "perpetual",
    "dex", "defi", "regulation", "sec", "cftc", "fed", "fomc", "cpi",
    "inflation", "etf", "liquidation", "stablecoin", "usdt", "usdc",
    "hack", "exploit", "rug", "airdrop", "listing", "hyperliquid",
]
