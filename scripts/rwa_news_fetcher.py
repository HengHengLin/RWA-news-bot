"""
RWA News Monitor v3
新增：中文信息源 / 交易所公告监控 / Pre-IPO 关键词 / 股票代币化平台
去重：URL 精确 + 标题 Jaccard 相似度
"""

import os, re, json, hashlib, unicodedata, requests, feedparser, argparse, time
from datetime import datetime, timezone, timedelta
from pathlib import Path

# ──────────────────────────────────────────────────────────────────
# 环境 & 常量
# ──────────────────────────────────────────────────────────────────

LARK_WEBHOOK   = os.environ.get("LARK_WEBHOOK_URL", "")
SGT            = timezone(timedelta(hours=8))
SEEN_FILE      = Path(__file__).parent.parent / ".seen_articles.json"
HEALTH_FILE    = Path(__file__).parent.parent / ".feed_health.json"

# Lark 每分钟限 5 条，推送间隔 13s 保证不超限
LARK_SEND_INTERVAL = 13          # 秒
LARK_MAX_RETRIES   = 3           # 单条推送最多重试次数
FEED_FAIL_ALERT_N  = 3           # 连续失败 N 次触发告警

# ──────────────────────────────────────────────────────────────────
# ① 关键词（中英双语，命中任意一个即触发）
# ──────────────────────────────────────────────────────────────────

KEYWORDS = [

    # ── 核心概念 ─────────────────────────────────────────────────
    "RWA", "real world asset", "real-world asset",
    "asset tokenization", "tokenized asset", "tokenisation",
    "资产代币化", "现实世界资产", "链上资产", "代币化",
    "真实世界资产", "现实资产上链",

    # ── 资产类别（英文）──────────────────────────────────────────
    "tokenized treasury", "tokenized treasuries",
    "tokenized bond", "tokenized equity", "tokenized stock",
    "tokenized fund", "tokenized real estate",
    "tokenized gold", "tokenized silver",
    "tokenized commodity", "tokenized credit",
    "tokenized security", "on-chain treasury",
    "on-chain securities", "on-chain equity",
    "digital securities", "security token", "STO",
    "fractional ownership blockchain",

    # ── 资产类别（中文）──────────────────────────────────────────
    "链上黄金", "链上白银", "链上股票", "链上权益",
    "链上基金", "链上国债", "代币化黄金", "代币化白银",
    "代币化股票", "代币化债券", "代币化基金",
    "代币化国债", "股票代币", "股票化代币",
    "证券代币", "证券通证", "通证化证券",

    # ── Pre-IPO & IPO ─────────────────────────────────────────────
    "Pre-IPO", "pre IPO", "pre-IPO token", "IPO Prime",
    "tokenized pre-IPO", "pre-IPO tokenization",
    "preSPAX", "预上市", "Pre-IPO代币", "上市前代币",
    "IPO tokenization", "private equity token",
    "tokenized private equity", "unicorn token",

    # ── TradFi / 传统金融上链 ─────────────────────────────────────
    "TradFi", "tradfi tokenization", "传统金融代币化",
    "传统资产上链", "机构级代币化", "机构级代币化平台",
    "institutional tokenization", "tokenized TradFi",

    # ── 监管 & 牌照 ───────────────────────────────────────────────
    "SEC tokenization", "SEC tokenized", "SEC 代币化",
    "CFTC tokenization", "MiCA tokenization",
    "DTCC tokenization", "tokenization regulation",
    "DLT Pilot Regime", "牌照", "合规牌照", "数字资产牌照",
    "virtual asset license", "digital asset license",
    "证券牌照", "代币化监管",

    # ── 重点机构 / 协议 ───────────────────────────────────────────
    "Securitize", "Ondo Finance", "Backed Finance",
    "Maple Finance", "Centrifuge", "Goldfinch",
    "TrueFi", "Superstate", "Franklin Templeton BENJI",
    "BlackRock BUIDL", "OpenEden", "Matrixdock",
    "Swarm Markets", "Robinhood tokenized",
    "USD1", "Plume Network", "Mantra chain",

    # ── 交易所 TradFi 功能（重点监控）────────────────────────────
    # Bitget
    "Bitget tokenized", "Bitget stock", "Bitget IPO Prime",
    "Bitget stocks", "Bitget RWA", "Bitget xStocks",
    "IPO Prime Bitget",
    # Binance
    "Binance tokenized stock", "Binance on-chain stock",
    "Binance xStocks", "Binance RWA", "Binance Pre-IPO",
    "Binance chain stock", "币安链上股票", "币安股票代币",
    # Bybit
    "Bybit tokenized", "Bybit stock token", "Bybit RWA",
    "Bybit xStocks", "Bybit Pre-IPO",
    # Gate
    "Gate tokenized", "Gate stock", "Gate RWA",
    "Gate Pre-IPO", "Gate.io tokenized", "Gate.io stocks",
    "Gate pre-market", "Gate 股票代币",
    # OKX
    "OKX tokenized", "OKX stock token", "OKX RWA",
    "OKX xStocks",
    # Kraken
    "Kraken xStocks", "Kraken tokenized stock",
    "Kraken stock token",
    # Coinbase
    "Coinbase tokenized stock", "Coinbase stock token",

    # ── 股票代币化平台（专项监控）────────────────────────────────
    "xStocks", "StableStock", "MSX", "Jarsy", "PreStocks",
    "Republic tokenized", "Backed Finance",
    "Ondo Global Markets", "Dinari", "Swarm Markets",
    "tZERO", "INX tokenized", "TokenSoft",
    "股票代币平台", "股票通证平台",

    # ── 上新资产 / 功能更新触发词 ─────────────────────────────────
    "new tokenized asset", "launches tokenized",
    "lists tokenized", "adds stock token",
    "上线股票代币", "新增代币化资产", "上新代币", "上市代币",
    "leveraged token", "24/7 stock trading",
    "tokenized ETF", "tokenized index",
]

# ──────────────────────────────────────────────────────────────────
# ② 信息源（分四梯队）
# ──────────────────────────────────────────────────────────────────
#
# ✅ 已经过多源交叉确认的 RSS
# ⚠️ 来自聚合器引用，格式合理，上线建议验证一次
# 📌 Google News RSS（免费，覆盖 Bloomberg/Reuters/FT 摘要）
# 🏛️ 交易所/平台公告（官方 RSS 或 Google News 替代）
# 🇨🇳 中文媒体
#

RSS_FEEDS = [

    # ════════════════════════════════════════════════════════
    # 梯队 1｜英文加密专业媒体（RWA 直接覆盖，最高优先级）
    # ════════════════════════════════════════════════════════
    {
        "name": "CoinTelegraph",
        "url": "https://cointelegraph.com/rss",
        "tier": 1, "lang": "en",
        # ✅ 官方 RSS，全球最大加密媒体，RWA 专栏活跃
    },
    {
        "name": "Blockworks",
        "url": "https://blockworks.co/feed/",
        "tier": 1, "lang": "en",
        # ✅ chainfeeds 项目确认，机构级加密媒体
    },
    {
        "name": "Decrypt",
        "url": "https://decrypt.co/feed",
        "tier": 1, "lang": "en",
        # ✅ 多源确认，tokenization 覆盖好
    },
    {
        "name": "The Defiant",
        "url": "https://thedefiant.io/api/feed",
        "tier": 1, "lang": "en",
        # ✅ feedspot 确认，DeFi/RWA 专注媒体
    },
    {
        "name": "Messari",
        "url": "https://messari.io/rss",
        "tier": 1, "lang": "en",
        # ✅ 多源确认，研究级内容，机构视角
    },
    {
        "name": "CryptoSlate RWA",
        "url": "https://cryptoslate.com/feed/rwa/",
        "tier": 1, "lang": "en",
        # ⚠️ CryptoSlate 有 RWA 专栏，RSS 格式待验证
    },

    # ════════════════════════════════════════════════════════
    # 梯队 2｜中文加密媒体（覆盖亚洲/华语市场动态）
    # ════════════════════════════════════════════════════════
    {
        "name": "PANews 律动",
        "url": "https://www.panewslab.com/zh/rss",
        "tier": 2, "lang": "zh",
        # ✅ PANews 官网有 RSS 订阅入口（/zh/rss 或 /rss）
        # 备用：https://www.panewslab.com/rss
    },
    {
        "name": "动区动趋 BlockTempo",
        "url": "https://www.blocktempo.com/feed/",
        "tier": 2, "lang": "zh",
        # ✅ WordPress 建站，标准 /feed/ 路径，台湾最大链媒
    },
    {
        "name": "Odaily 星球日报",
        "url": "https://www.odaily.news/rss",
        "tier": 2, "lang": "zh",
        # ⚠️ Odaily 有 RSS 订阅（/rss 路径），国内头部加密媒体
    },
    {
        "name": "区块律动 BlockBeats",
        "url": "https://www.theblockbeats.info/rss",
        "tier": 2, "lang": "zh",
        # ⚠️ BlockBeats 站点有 RSS，路径待验证
    },
    {
        "name": "链新闻 ABMedia",
        "url": "https://abmedia.io/feed",
        "tier": 2, "lang": "zh",
        # ⚠️ 台湾链新闻，WordPress 架构，/feed 路径
    },
    {
        "name": "吴说区块链 WuBlock",
        "url": "https://wublock.substack.com/feed",
        "tier": 2, "lang": "zh",
        # ✅ Substack 出版物，RSS 格式固定为 /feed，有效
    },
    {
        "name": "ChainFeeds 精选（中文）",
        "url": "https://www.chainfeeds.xyz/rss",
        "tier": 2, "lang": "zh",
        # ✅ chainfeeds 项目自列，Web3 精选信息聚合
    },
    {
        "name": "CoinTelegraph 中文",
        "url": "https://cn.cointelegraph.com/rss",
        "tier": 2, "lang": "zh",
        # ✅ CoinTelegraph 有官方中文版，RSS 与英文版同架构
    },

    # ════════════════════════════════════════════════════════
    # 梯队 3｜英文通用加密媒体（配合关键词过滤，增加覆盖面）
    # ════════════════════════════════════════════════════════
    {
        "name": "CoinDesk",
        "url": "https://feeds.feedburner.com/CoinDesk",
        "tier": 3, "lang": "en",
        # ⚠️ feedburner 链接来自 chainfeeds 引用
    },
    {
        "name": "CryptoBriefing",
        "url": "https://cryptobriefing.com/feed/",
        "tier": 3, "lang": "en",
        # ⚠️ 多源确认
    },
    {
        "name": "AMBCrypto",
        "url": "https://ambcrypto.com/feed",
        "tier": 3, "lang": "en",
        # ⚠️ 多源确认
    },
    {
        "name": "NewsBTC",
        "url": "https://newsbtc.com/feed",
        "tier": 3, "lang": "en",
        # ⚠️ 多源确认
    },
    {
        "name": "CryptoNews",
        "url": "https://crypto.news/feed",
        "tier": 3, "lang": "en",
        # ⚠️ 多源确认
    },
    {
        "name": "Bitcoin Magazine",
        "url": "https://bitcoinmagazine.com/.rss/full/",
        "tier": 3, "lang": "en",
        # ⚠️ 多源确认
    },

    # ════════════════════════════════════════════════════════
    # 梯队 4｜交易所 & 平台公告（Google News RSS 代理）
    # ────────────────────────────────────────────────────────
    # 注：Binance/Bitget/Gate/Bybit 官方公告页为 JS 渲染，无原生 RSS。
    # 通过 Google News RSS 搜索这些交易所的公告和媒体报道，
    # 可以覆盖到 Cointelegraph、The Block、CoinDesk 等媒体
    # 对这些平台新上线功能/资产的第一手报道。
    # ════════════════════════════════════════════════════════
    {
        "name": "Google News: Binance tokenized stocks",
        "url": "https://news.google.com/rss/search?q=Binance+tokenized+stock+OR+%22Binance+xStocks%22+OR+%22Binance+Pre-IPO%22&hl=en&gl=US&ceid=US:en",
        "tier": 4, "lang": "en", "is_google_news": True,
        # 📌 Binance 链上股票 / Pre-IPO / RWA 动态
    },
    {
        "name": "Google News: Bitget IPO Prime stocks",
        "url": "https://news.google.com/rss/search?q=Bitget+%22IPO+Prime%22+OR+%22tokenized+stock%22+OR+%22xStocks%22&hl=en&gl=US&ceid=US:en",
        "tier": 4, "lang": "en", "is_google_news": True,
        # 📌 Bitget IPO Prime / 股票代币化动态
    },
    {
        "name": "Google News: Bybit Gate tokenized stocks",
        "url": "https://news.google.com/rss/search?q=Bybit+OR+Gate.io+%22tokenized+stock%22+OR+%22stock+token%22+OR+%22Pre-IPO%22&hl=en&gl=US&ceid=US:en",
        "tier": 4, "lang": "en", "is_google_news": True,
        # 📌 Bybit / Gate 股票代币动态
    },
    {
        "name": "Google News: xStocks StableStock Jarsy PreStocks",
        "url": "https://news.google.com/rss/search?q=xStocks+OR+StableStock+OR+Jarsy+OR+PreStocks+tokenized&hl=en&gl=US&ceid=US:en",
        "tier": 4, "lang": "en", "is_google_news": True,
        # 📌 专项股票代币化平台动态
    },
    {
        "name": "Google News: RWA tokenization",
        "url": "https://news.google.com/rss/search?q=RWA+tokenization&hl=en&gl=US&ceid=US:en",
        "tier": 4, "lang": "en", "is_google_news": True,
        # 📌 核心 RWA 词（覆盖 Bloomberg/Reuters/FT 摘要）
    },
    {
        "name": "Google News: real world assets blockchain",
        "url": "https://news.google.com/rss/search?q=%22real+world+assets%22+blockchain&hl=en&gl=US&ceid=US:en",
        "tier": 4, "lang": "en", "is_google_news": True,
    },
    {
        "name": "Google News: tokenized equity securities",
        "url": "https://news.google.com/rss/search?q=%22tokenized+equity%22+OR+%22tokenized+securities%22+OR+%22tokenized+stocks%22&hl=en&gl=US&ceid=US:en",
        "tier": 4, "lang": "en", "is_google_news": True,
    },
    {
        "name": "Google News: Pre-IPO crypto tokenized",
        "url": "https://news.google.com/rss/search?q=%22Pre-IPO%22+tokenized+OR+%22tokenized+pre-IPO%22+OR+%22IPO+Prime%22&hl=en&gl=US&ceid=US:en",
        "tier": 4, "lang": "en", "is_google_news": True,
        # 📌 Pre-IPO 代币化专项
    },
    {
        "name": "Google News: Securitize Ondo tokenization",
        "url": "https://news.google.com/rss/search?q=Securitize+OR+%22Ondo+Finance%22+tokenization&hl=en&gl=US&ceid=US:en",
        "tier": 4, "lang": "en", "is_google_news": True,
    },
    {
        "name": "Google News (中文): RWA 代币化 链上股票",
        "url": "https://news.google.com/rss/search?q=RWA+%E4%BB%A3%E5%B8%81%E5%8C%96+OR+%E9%93%BE%E4%B8%8A%E8%82%A1%E7%A5%A8+OR+%E8%82%A1%E7%A5%A8%E4%BB%A3%E5%B8%81&hl=zh-CN&gl=CN&ceid=CN:zh-Hans",
        "tier": 4, "lang": "zh", "is_google_news": True,
        # 📌 中文 Google News，覆盖新浪财经/东方财富等中文媒体
    },
    {
        "name": "Google News (中文): Pre-IPO 预上市 交易所",
        "url": "https://news.google.com/rss/search?q=Pre-IPO+%E4%BB%A3%E5%B8%81+OR+%E9%A2%84%E4%B8%8A%E5%B8%82+%E5%8C%BA%E5%9D%97%E9%93%BE&hl=zh-CN&gl=CN&ceid=CN:zh-Hans",
        "tier": 4, "lang": "zh", "is_google_news": True,
    },
]

# ──────────────────────────────────────────────────────────────────
# 工具：文本处理 & 去重
# ──────────────────────────────────────────────────────────────────

def normalize_title(t: str) -> str:
    t = t.lower()
    t = unicodedata.normalize("NFKC", t)
    t = re.sub(r"[^\w\s]", " ", t)
    stopwords = {"the","a","an","in","on","of","to","for","and","or","is",
                 "are","was","were","has","have","its","this","that","with",
                 "by","at","from","as","be","it","new","says","said","的","了",
                 "在","是","与","及","将","已","于","对","其","等","有","为"}
    words = [w for w in t.split() if w not in stopwords and len(w) > 1]
    return " ".join(sorted(words))

def jaccard(a: str, b: str, threshold=0.55) -> bool:
    sa = set(normalize_title(a).split())
    sb = set(normalize_title(b).split())
    if not sa or not sb:
        return False
    return len(sa & sb) / len(sa | sb) >= threshold

def strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text or "").strip()

def article_uid(url: str) -> str:
    return hashlib.md5(url.encode()).hexdigest()

def title_uid(title: str) -> str:
    """
    标题指纹。Google News RSS 每次返回跳转 URL 不固定，
    同一篇文章每次 URL 不同，用标题 hash 作为去重 key。
    """
    return "t:" + hashlib.md5(normalize_title(title).encode()).hexdigest()

# 单次实时运行最多推送条数（防止缓存丢失后洪水推送）
INSTANT_MAX_PUSH = 8

# ──────────────────────────────────────────────────────────────────
# 抓取
# ──────────────────────────────────────────────────────────────────

def fetch_all(hours_back: int = 25) -> list[dict]:
    cutoff = datetime.now(SGT) - timedelta(hours=hours_back)
    articles = []
    status_lines = []

    for cfg in RSS_FEEDS:
        try:
            feed = feedparser.parse(
                cfg["url"],
                agent="Mozilla/5.0 (compatible; RWA-NewsBot/3.0; +https://github.com)"
            )
            if feed.get("status", 200) >= 400:
                raise Exception(f"HTTP {feed.get('status')}")

            count = 0
            for entry in feed.entries[:40]:
                pub = entry.get("published_parsed") or entry.get("updated_parsed")
                pub_dt = datetime(*pub[:6], tzinfo=timezone.utc).astimezone(SGT) if pub else datetime.now(SGT)
                if pub_dt < cutoff:
                    continue

                title   = entry.get("title", "").strip()
                url     = entry.get("link", "").strip()
                summary = strip_html(entry.get("summary", entry.get("description", "")))[:500]
                if not title or not url:
                    continue

                # 中文乱码修复：GBK 编码的 RSS 经 feedparser 解析后可能出现
                # \u00xx 形式的乱码，尝试 latin-1 → utf-8 重新解码
                try:
                    title   = title.encode("latin-1").decode("utf-8")
                    summary = summary.encode("latin-1").decode("utf-8")
                except (UnicodeEncodeError, UnicodeDecodeError):
                    pass  # 编码正常，跳过

                articles.append({
                    "source":    cfg["name"],
                    "tier":      cfg.get("tier", 3),
                    "lang":      cfg.get("lang", "en"),
                    "title":     title,
                    "url":       url,
                    "summary":   summary,
                    "published": pub_dt.strftime("%Y-%m-%d %H:%M SGT"),
                    "pub_dt":    pub_dt,
                    "is_gn":     cfg.get("is_google_news", False),
                })
                count += 1

            status_lines.append(f"  ✅ [{cfg['lang'].upper()}] {cfg['name']}: {count} 条")

        except Exception as e:
            status_lines.append(f"  ❌ [{cfg.get('lang','?').upper()}] {cfg['name']}: {e}")

    print("[信息源状态]")
    for s in status_lines:
        print(s)

    # 健康检查：连续失败源告警
    update_health_and_alert(status_lines)

    return articles

# ──────────────────────────────────────────────────────────────────
# 过滤 & 去重
# ──────────────────────────────────────────────────────────────────

def filter_keywords(articles: list[dict]) -> list[dict]:
    out = []
    for a in articles:
        text = f"{a['title']} {a['summary']}".lower()
        matched = [kw for kw in KEYWORDS if kw.lower() in text]
        if matched:
            a["matched_kws"] = matched[:6]
            out.append(a)
    return out

def deduplicate(articles: list[dict]) -> list[dict]:
    """
    tier 升序 + 时间升序排序（最优质、最早的版本被保留）
    两层去重：URL精确 + 标题Jaccard相似度(0.55)
    """
    sorted_arts = sorted(articles, key=lambda x: (x["tier"], x["pub_dt"]))
    seen_urls   = set()
    seen_titles = []
    unique      = []

    for a in sorted_arts:
        uid = article_uid(a["url"])
        if uid in seen_urls:
            continue
        if any(jaccard(a["title"], t) for t in seen_titles):
            continue
        seen_urls.add(uid)
        seen_titles.append(a["title"])
        unique.append(a)

    return unique

# ──────────────────────────────────────────────────────────────────
# Lark 推送
# ──────────────────────────────────────────────────────────────────

def _post_lark(body: dict, label: str, _last_send: list = [0.0]):
    """
    推送单条 Lark 消息。
    - 自动限速：两次推送之间至少间隔 LARK_SEND_INTERVAL 秒（Lark 限 5条/分钟）
    - 自动重试：失败最多重试 LARK_MAX_RETRIES 次，指数退避
    """
    if not LARK_WEBHOOK:
        print(f"[DRY RUN] {label}")
        return

    # 限速：距上次发送不足间隔则等待
    elapsed = time.time() - _last_send[0]
    if elapsed < LARK_SEND_INTERVAL:
        time.sleep(LARK_SEND_INTERVAL - elapsed)

    for attempt in range(1, LARK_MAX_RETRIES + 1):
        try:
            r = requests.post(LARK_WEBHOOK, json=body, timeout=12)
            _last_send[0] = time.time()
            if r.status_code == 200:
                resp_json = r.json() if r.content else {}
                if resp_json.get("code", 0) != 0:
                    msg = resp_json.get("msg", "unknown")
                    print(f"[WARN] Lark 业务错误 code={resp_json['code']} msg={msg}（{label}）")
                    if attempt < LARK_MAX_RETRIES:
                        time.sleep(2 ** attempt)
                        continue
                else:
                    print(f"[OK] {label}")
                    return
            else:
                print(f"[WARN] HTTP {r.status_code}（{label}），第{attempt}次")
                if attempt < LARK_MAX_RETRIES:
                    time.sleep(2 ** attempt)
        except Exception as e:
            print(f"[ERR] 网络异常（{label}）第{attempt}次: {e}")
            if attempt < LARK_MAX_RETRIES:
                time.sleep(2 ** attempt)

    print(f"[ERR] 推送彻底失败，已放弃: {label}")

def push_instant(a: dict):
    lang_flag = "🇨🇳" if a.get("lang") == "zh" else "🌐"
    kw_str = "  ".join([f"`{k}`" for k in a.get("matched_kws", [])[:5]])

    # 判断类型标签
    is_preipo   = any(k in str(a.get("matched_kws","")).lower() for k in ["pre-ipo","pre ipo","ipo prime","预上市"])
    is_exchange = any(k in a["title"].lower() for k in ["binance","bitget","bybit","gate","okx","kraken","coinbase"])
    is_tradfi   = any(k in str(a.get("matched_kws","")).lower() for k in ["tradfi","xstocks","stablestock","jarsy","prestocks"])

    if is_preipo:
        badge = "🔮 Pre-IPO"
        color = "purple"
    elif is_exchange:
        badge = "🏦 交易所动态"
        color = "orange"
    elif is_tradfi:
        badge = "📈 股票代币化"
        color = "indigo"
    else:
        badge = "📡 RWA 快讯"
        color = "blue"

    body = {
        "msg_type": "interactive",
        "card": {
            "config": {"wide_screen_mode": True},
            "header": {
                "title": {"tag": "plain_text", "content": f"{lang_flag} {badge}"},
                "template": color,
            },
            "elements": [
                {"tag": "div", "text": {"tag": "lark_md", "content": f"**{a['title']}**"}},
                {"tag": "div", "text": {"tag": "lark_md", "content": a["summary"] or "_（无摘要）_"}},
                {"tag": "hr"},
                {
                    "tag": "div",
                    "fields": [
                        {"is_short": True, "text": {"tag": "lark_md", "content": f"**来源**\n{a['source']}"}},
                        {"is_short": True, "text": {"tag": "lark_md", "content": f"**时间**\n{a['published']}"}},
                    ],
                },
                {"tag": "div", "text": {"tag": "lark_md", "content": f"**命中关键词** · {kw_str}"}},
                {"tag": "action", "actions": [
                    {"tag": "button", "text": {"tag": "plain_text", "content": "阅读原文 →"},
                     "type": "primary", "url": a["url"]}
                ]},
            ],
        },
    }
    _post_lark(body, f"即时 [{a['source']}] {a['title'][:55]}")


def push_daily_digest(articles: list[dict]):
    if not articles:
        print("[INFO] 今日无 RWA 相关新闻，跳过推送")
        return

    today = datetime.now(SGT).strftime("%Y年%m月%d日")

    # 按类别分组
    groups = {
        "🔮 Pre-IPO 动态":   [],
        "🏦 交易所 & 平台":   [],
        "📈 股票代币化":      [],
        "🌐 英文 RWA 资讯":   [],
        "🇨🇳 中文 RWA 资讯":  [],
    }

    for a in articles:
        kws_str = " ".join(a.get("matched_kws", [])).lower()
        title_l = a["title"].lower()
        is_preipo = any(k in kws_str for k in ["pre-ipo","ipo prime","pre ipo","预上市","preSPAX".lower()])
        is_exch   = any(k in title_l for k in ["binance","bitget","bybit","gate","okx","kraken","coinbase"])
        is_stock  = any(k in kws_str for k in ["xstocks","stablestock","jarsy","prestocks","链上股票","股票代币","stock token","tokenized stock"])

        if is_preipo:
            groups["🔮 Pre-IPO 动态"].append(a)
        elif is_exch:
            groups["🏦 交易所 & 平台"].append(a)
        elif is_stock:
            groups["📈 股票代币化"].append(a)
        elif a.get("lang") == "zh":
            groups["🇨🇳 中文 RWA 资讯"].append(a)
        else:
            groups["🌐 英文 RWA 资讯"].append(a)

    total = sum(len(v) for v in groups.values())
    zh_count = len(groups["🇨🇳 中文 RWA 资讯"]) + sum(
        1 for a in articles if a.get("lang") == "zh"
    )

    elements = [
        {"tag": "div", "text": {"tag": "lark_md",
            "content": f"今日去重后共 **{total}** 条 RWA 资讯 · "
                       f"中文 {len(groups['🇨🇳 中文 RWA 资讯'])} 条 · 英文 {total - len(groups['🇨🇳 中文 RWA 资讯'])} 条"}},
        {"tag": "hr"},
    ]

    for group_name, arts in groups.items():
        if not arts:
            continue
        lines = [f"**{group_name}** · {len(arts)} 条"]
        for a in arts[:8]:
            lang_flag = "🇨🇳" if a.get("lang") == "zh" else ""
            lines.append(f"• {lang_flag} [{a['title'][:75]}]({a['url']})")
        elements.append({"tag": "div", "text": {"tag": "lark_md", "content": "\n".join(lines)}})
        elements.append({"tag": "hr"})

    elements.append({"tag": "note", "elements": [{"tag": "plain_text",
        "content": f"🤖 RWA NewsBot v3 · {datetime.now(SGT).strftime('%H:%M SGT')} · Jaccard 去重 · {len(RSS_FEEDS)} 个信息源"}]})

    body = {
        "msg_type": "interactive",
        "card": {
            "config": {"wide_screen_mode": True},
            "header": {
                "title": {"tag": "plain_text", "content": f"📰 RWA 日报 · {today}"},
                "template": "green",
            },
            "elements": elements,
        },
    }
    # ── 卡片超长保护 ─────────────────────────────────────────────
    # Lark 卡片 elements 过多时渲染失败（经验值 >40 个 element 开始不稳定）。
    # 超出时拆成两条消息发送。
    MAX_ELEMENTS = 38
    if len(elements) > MAX_ELEMENTS:
        body1 = {k: v for k, v in body.items()}
        body1["card"] = {**body["card"], "elements": elements[:MAX_ELEMENTS] + [
            {"tag": "note", "elements": [{"tag": "plain_text",
             "content": f"（内容过多，续见下一条消息）"}]}
        ]}
        body2 = {k: v for k, v in body.items()}
        body2["card"] = {**body["card"],
            "header": {**body["card"]["header"],
                "title": {"tag": "plain_text", "content": f"📰 RWA 日报续 · {today}"}},
            "elements": elements[MAX_ELEMENTS:]
        }
        _post_lark(body1, f"日报推送（上）{total} 条")
        _post_lark(body2, f"日报推送（下）{total} 条")
    else:
        _post_lark(body, f"日报推送 {total} 条")

# ──────────────────────────────────────────────────────────────────
# 实时缓存
# ──────────────────────────────────────────────────────────────────

def load_cache() -> dict:
    if SEEN_FILE.exists():
        try:
            data = json.loads(SEEN_FILE.read_text())
            return data if isinstance(data, dict) else {h: "" for h in data}
        except Exception:
            pass
    return {}

def save_cache(cache: dict):
    # 只保留最近 3000 条，防止文件无限增长
    if len(cache) > 3000:
        cache = dict(list(cache.items())[-3000:])
    SEEN_FILE.write_text(json.dumps(cache))

def is_seen(a: dict, cache: dict) -> bool:
    """
    双重查缓存：
    1. URL hash（精确匹配，适用于普通 RSS）
    2. 标题 hash（适用于 Google News 跳转 URL 每次不同的情况）
    """
    return article_uid(a["url"]) in cache or title_uid(a["title"]) in cache

def mark_seen(a: dict, cache: dict):
    """同时写入 URL hash 和标题 hash"""
    cache[article_uid(a["url"])] = a["title"]
    cache[title_uid(a["title"])]  = a["title"]

# ──────────────────────────────────────────────────────────────────
# 主入口
# ──────────────────────────────────────────────────────────────────

def run_instant():
    print(f"\n[{datetime.now(SGT).strftime('%H:%M SGT')}] ▶ 实时监控")
    cache = load_cache()

    # ── 冷启动保护 ──────────────────────────────────────────────
    # 如果缓存为空（首次运行 or 缓存被清除），
    # 只处理最近 30 分钟的文章，避免一次性推几十条。
    is_cold_start = len(cache) == 0
    hours_back = 0.5 if is_cold_start else 2
    if is_cold_start:
        print("[⚠️ 冷启动] 缓存为空，只处理最近30分钟的文章，防止洪水推送")

    raw     = fetch_all(hours_back=hours_back)
    matched = filter_keywords(raw)

    # 过滤掉已推送（URL hash 或 标题 hash 命中）
    new     = [a for a in matched if not is_seen(a, cache)]
    deduped = deduplicate(new)

    # ── 单次推送上限 ─────────────────────────────────────────────
    # 即使去重后仍有很多条（例如缓存刚恢复），也最多推 INSTANT_MAX_PUSH 条，
    # 剩余的只写入缓存（下次不再推），不发 Lark 消息。
    to_push  = deduped[:INSTANT_MAX_PUSH]
    to_cache = deduped[INSTANT_MAX_PUSH:]  # 超出上限的只缓存不推

    pushed = 0
    for a in to_push:
        push_instant(a)
        mark_seen(a, cache)
        pushed += 1

    # 超出上限的文章也写入缓存，避免下次再被推送
    for a in to_cache:
        mark_seen(a, cache)

    if to_cache:
        print(f"[⚠️ 限流] {len(to_cache)} 条超出单次上限({INSTANT_MAX_PUSH})，已缓存但未推送")

    save_cache(cache)
    print(f"[完成] 原始 {len(raw)} → 关键词匹配 {len(matched)} → "
          f"新增未见 {len(new)} → 去重 {len(deduped)} → 实际推送 {pushed} 条\n")


def run_daily():
    print(f"\n[{datetime.now(SGT).strftime('%H:%M SGT')}] ▶ 生成日报")
    raw     = fetch_all(hours_back=25)
    matched = filter_keywords(raw)
    deduped = deduplicate(matched)
    deduped.sort(key=lambda x: x["pub_dt"], reverse=True)
    print(f"[统计] 原始 {len(raw)} → 关键词匹配 {len(matched)} → 去重后 {len(deduped)} 条")
    push_daily_digest(deduped)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["instant", "daily"], default="daily")
    args = parser.parse_args()
    run_instant() if args.mode == "instant" else run_daily()


# ──────────────────────────────────────────────────────────────────
# 信息源健康监控
# ──────────────────────────────────────────────────────────────────

def load_health() -> dict:
    """加载信息源连续失败计数 {feed_name: fail_count}"""
    if HEALTH_FILE.exists():
        try:
            return json.loads(HEALTH_FILE.read_text())
        except Exception:
            pass
    return {}

def save_health(health: dict):
    HEALTH_FILE.write_text(json.dumps(health))

def update_health_and_alert(status_lines: list[str]):
    """
    解析 fetch_all 的状态行，更新连续失败计数。
    某个源连续失败 FEED_FAIL_ALERT_N 次，推送一条 Lark 告警。
    """
    health = load_health()
    alerts = []

    for line in status_lines:
        # 解析格式：  ✅ [EN] CoinTelegraph: 5 条  或  ❌ [ZH] Odaily: HTTP 403
        if "✅" in line:
            name = line.split("]", 1)[-1].split(":")[0].strip()
            health[name] = 0  # 成功，重置计数
        elif "❌" in line:
            name = line.split("]", 1)[-1].split(":")[0].strip()
            health[name] = health.get(name, 0) + 1
            count = health[name]
            if count == FEED_FAIL_ALERT_N:
                err = line.split(":", 2)[-1].strip() if ":" in line else "未知错误"
                alerts.append(f"• **{name}** 已连续失败 {count} 次（{err}）")

    save_health(health)

    if alerts:
        body = {
            "msg_type": "interactive",
            "card": {
                "config": {"wide_screen_mode": True},
                "header": {
                    "title": {"tag": "plain_text", "content": "⚠️ RWA Bot 信息源异常告警"},
                    "template": "red",
                },
                "elements": [
                    {"tag": "div", "text": {"tag": "lark_md",
                        "content": "以下信息源**连续失败 {} 次**，请检查：\n\n{}".format(
                            FEED_FAIL_ALERT_N, "\n".join(alerts)
                        )}},
                    {"tag": "note", "elements": [{"tag": "plain_text",
                        "content": "💡 应急：检查 RSS URL 是否变更，或在 RSS_FEEDS 中临时注释该源"}]},
                ],
            },
        }
        _post_lark(body, f"信息源告警：{len(alerts)} 个源异常")
