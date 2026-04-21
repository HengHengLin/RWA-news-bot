"""
RWA News Monitor v3.1
- 修复：update_health_and_alert 函数顺序问题（NameError）
- 修复：Messari RSS URL (404→新URL) / 区块律动(403) / 吴说(403) / CT中文(410) 已更新或移除
- 功能：中英文双语信息源 / 交易所公告监控 / Pre-IPO关键词 / 实时+日报双模式
- 防护：Lark限速+重试 / 冷启动保护 / 单次推送上限 / 标题hash去重 / 日报卡片拆分
"""

import os, re, json, hashlib, unicodedata, requests, feedparser, argparse, time
from datetime import datetime, timezone, timedelta
from pathlib import Path

# ──────────────────────────────────────────────────────────────────
# 环境 & 常量
# ──────────────────────────────────────────────────────────────────

LARK_WEBHOOK       = os.environ.get("LARK_WEBHOOK_URL", "")
SGT                = timezone(timedelta(hours=8))
SEEN_FILE          = Path(__file__).parent.parent / ".seen_articles.json"
HEALTH_FILE        = Path(__file__).parent.parent / ".feed_health.json"

LARK_SEND_INTERVAL = 13   # 秒，Lark 限 5条/分钟，13s 间隔保证不超限
LARK_MAX_RETRIES   = 3    # 单条推送最多重试次数
FEED_FAIL_ALERT_N  = 3    # 连续失败 N 次触发 Lark 告警

# 域名黑名单：这些来源是数据平台/价格聚合器，不是新闻，过滤掉
URL_BLACKLIST_DOMAINS = [
    "cryptorank.io",       # 数据平台，推的是价格页而非新闻
    "coingecko.com",       # 价格聚合
    "coinmarketcap.com",   # 价格聚合
    "dune.com",            # 链上数据
    "defillama.com",       # TVL 数据
]
INSTANT_MAX_PUSH   = 8    # 单次实时运行最多推送条数（防洪水）

# ──────────────────────────────────────────────────────────────────
# ① 关键词（中英双语，命中任意一个即触发）
# ──────────────────────────────────────────────────────────────────

KEYWORDS = [

    # ── 核心概念（英文）──────────────────────────────────────────
    "RWA", "real world asset", "real-world asset",
    "asset tokenization", "tokenized asset", "tokenisation",

    # ── 核心概念（中文）— 覆盖各媒体不同表达习惯 ─────────────────
    # 动区动趋/PANews/Odaily 常用词形
    "RWA赛道", "RWA项目", "RWA协议", "RWA市场",
    "现实世界资产", "真实世界资产", "现实资产上链",
    "资产代币化", "代币化资产", "链上资产",
    "代币化",         # 单独匹配，覆盖「XXX代币化」句式
    "通证化",         # 部分媒体用「通证化」而非「代币化」
    "上链",           # 「资产上链」「股票上链」等句式

    # ── 资产类别（英文）──────────────────────────────────────────
    "tokenized treasury", "tokenized treasuries",
    "tokenized bond", "tokenized equity", "tokenized stock",
    "tokenized fund", "tokenized real estate",
    "tokenized gold", "tokenized silver",
    "tokenized commodity", "tokenized credit",
    "tokenized security", "on-chain treasury",
    "on-chain securities", "on-chain equity",
    "digital securities", "security token",
    "fractional ownership blockchain",

    # ── 资产类别（中文）──────────────────────────────────────────
    "链上黄金", "链上白银", "链上股票", "链上权益",
    "链上基金", "链上国债", "代币化黄金", "代币化白银",
    "代币化股票", "代币化债券", "代币化基金",
    "代币化国债", "股票代币", "股票化代币",
    "证券代币", "证券通证", "通证化证券",
    # 中文媒体常见说法补充
    "美股代币", "美股通证", "股票通证化",
    "债券代币化", "房地产代币化", "黄金代币化",
    "国债代币化", "基金代币化",

    # ── Pre-IPO & IPO ─────────────────────────────────────────────
    "Pre-IPO", "pre IPO", "pre-IPO token", "IPO Prime",
    "tokenized pre-IPO", "pre-IPO tokenization",
    "preSPAX", "预上市", "Pre-IPO代币", "上市前代币",
    "IPO tokenization", "private equity token",
    "tokenized private equity", "unicorn token",
    # 中文 Pre-IPO 表达
    "Pre-IPO代币化", "上市前股权代币", "未上市股权",

    # ── TradFi / 传统金融上链 ─────────────────────────────────────
    "TradFi", "tradfi tokenization", "传统金融代币化",
    "传统资产上链", "机构级代币化", "机构级代币化平台",
    "institutional tokenization", "tokenized TradFi",
    # 中文 TradFi 表达
    "传统金融上链", "传统资产代币", "链上传统资产",
    "链上金融", "机构入场",

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

    # ── 交易所专项监控 ────────────────────────────────────────────
    "Bitget tokenized", "Bitget stock", "Bitget IPO Prime",
    "Bitget stocks", "Bitget RWA", "Bitget xStocks",
    "Binance tokenized stock", "Binance on-chain stock",
    "Binance xStocks", "Binance RWA", "Binance Pre-IPO",
    "币安链上股票", "币安股票代币",
    "Bybit tokenized", "Bybit stock token", "Bybit RWA",
    "Bybit xStocks", "Bybit Pre-IPO",
    "Gate tokenized", "Gate stock", "Gate RWA",
    "Gate Pre-IPO", "Gate.io tokenized", "Gate 股票代币",
    "OKX tokenized", "OKX stock token", "OKX RWA", "OKX xStocks",
    "Kraken xStocks", "Kraken tokenized stock",
    "Coinbase tokenized stock", "Coinbase stock token",

    # ── 股票代币化平台专项 ────────────────────────────────────────
    "xStocks", "StableStock", "MSX", "Jarsy", "PreStocks",
    "Republic tokenized", "Ondo Global Markets",
    "Dinari", "tZERO", "INX tokenized", "TokenSoft",
    "股票代币平台", "股票通证平台",

    # ── 上新资产 / 功能更新触发词 ─────────────────────────────────
    "new tokenized asset", "launches tokenized",
    "lists tokenized", "adds stock token",
    "上线股票代币", "新增代币化资产", "上新代币", "上市代币",
    "leveraged token", "24/7 stock trading",
    "tokenized ETF", "tokenized index",
]

# ──────────────────────────────────────────────────────────────────
# ② 信息源
# 状态说明：✅已验证  ⚠️待验证  ❌已确认失效（保留注释供参考）
# ──────────────────────────────────────────────────────────────────

RSS_FEEDS = [

    # ════════════════════════════════════════════════════
    # 梯队 1｜英文加密专业媒体
    # ════════════════════════════════════════════════════
    {
        "name": "CoinTelegraph",
        "url": "https://cointelegraph.com/rss",
        "tier": 1, "lang": "en",   # ✅ 实测可用
    },
    {
        "name": "Blockworks",
        "url": "https://blockworks.co/feed/",
        "tier": 1, "lang": "en",   # ✅ 实测可用
    },
    {
        "name": "Decrypt",
        "url": "https://decrypt.co/feed",
        "tier": 1, "lang": "en",   # ✅ 实测可用
    },
    {
        "name": "The Defiant",
        "url": "https://thedefiant.io/api/feed",
        "tier": 1, "lang": "en",   # ✅ 实测可用
    },
    {
        "name": "Messari",
        "url": "https://messari.io/news/rss",       # ← 原 /rss 已404，改为 /news/rss
        "tier": 1, "lang": "en",   # ⚠️ URL已更新，待验证
    },
    {
        "name": "CryptoSlate RWA",
        "url": "https://cryptoslate.com/feed/rwa/",
        "tier": 1, "lang": "en",   # ✅ 实测可用（返回0条是正常的，无新文章时如此）
    },

    # ════════════════════════════════════════════════════
    # 梯队 2｜中文加密媒体
    # ════════════════════════════════════════════════════
    {
        "name": "PANews 律动",
        "url": "https://www.panewslab.com/zh/rss",
        "tier": 2, "lang": "zh",   # ✅ 实测可用
    },
    {
        "name": "动区动趋 BlockTempo",
        "url": "https://www.blocktempo.com/feed/",
        "tier": 2, "lang": "zh",   # ✅ 实测可用
    },
    {
        "name": "Odaily 星球日报",
        "url": "https://www.odaily.news/rss",
        "tier": 2, "lang": "zh",   # ✅ 实测可用
    },
    {
        "name": "链新闻 ABMedia",
        "url": "https://abmedia.io/feed",
        "tier": 2, "lang": "zh",   # ✅ 实测可用
    },
    {
        "name": "吴说区块链 WuBlock",
        "url": "https://wublockchain.substack.com/feed",  # ← 原URL 403，改为新域名
        "tier": 2, "lang": "zh",   # ⚠️ URL已更新，待验证
    },
    # 以下已确认失效，注释保留：
    # {"name": "区块律动 BlockBeats", "url": "https://www.theblockbeats.info/rss"},  # 403
    # {"name": "ChainFeeds 精选", "url": "https://www.chainfeeds.xyz/rss"},          # 502
    # {"name": "CoinTelegraph 中文", "url": "https://cn.cointelegraph.com/rss"},     # 410 已下线

    # ════════════════════════════════════════════════════
    # 梯队 3｜英文通用媒体
    # ════════════════════════════════════════════════════
    {
        "name": "CoinDesk",
        "url": "https://feeds.feedburner.com/CoinDesk",
        "tier": 3, "lang": "en",   # ✅ 实测可用
    },
    # CryptoBriefing 已移除：内容质量差，大量推送与 RWA 无关的比特币预测文章
    {
        "name": "NewsBTC",
        "url": "https://newsbtc.com/feed",
        "tier": 3, "lang": "en",   # ✅ 实测可用
    },
    {
        "name": "CryptoNews",
        "url": "https://crypto.news/feed",
        "tier": 3, "lang": "en",   # ✅ 实测可用
    },
    {
        "name": "Bitcoin Magazine",
        "url": "https://bitcoinmagazine.com/.rss/full/",
        "tier": 3, "lang": "en",   # ✅ 实测可用
    },
    # 以下已确认失效，注释保留：
    # {"name": "AMBCrypto", "url": "https://ambcrypto.com/feed"},  # 403

    # ════════════════════════════════════════════════════
    # 梯队 4｜Google News RSS（覆盖 Bloomberg/Reuters/FT 摘要 + 交易所报道）
    # ════════════════════════════════════════════════════
    {
        "name": "Google News: Binance tokenized stocks",
        "url": "https://news.google.com/rss/search?q=Binance+tokenized+stock+OR+%22Binance+xStocks%22+OR+%22Binance+Pre-IPO%22&hl=en&gl=US&ceid=US:en",
        "tier": 4, "lang": "en", "is_google_news": True,
    },
    {
        "name": "Google News: Bitget IPO Prime stocks",
        "url": "https://news.google.com/rss/search?q=Bitget+%22IPO+Prime%22+OR+%22tokenized+stock%22+OR+%22xStocks%22&hl=en&gl=US&ceid=US:en",
        "tier": 4, "lang": "en", "is_google_news": True,
    },
    {
        "name": "Google News: Bybit Gate tokenized stocks",
        "url": "https://news.google.com/rss/search?q=Bybit+OR+Gate.io+%22tokenized+stock%22+OR+%22stock+token%22+OR+%22Pre-IPO%22&hl=en&gl=US&ceid=US:en",
        "tier": 4, "lang": "en", "is_google_news": True,
    },
    {
        "name": "Google News: xStocks StableStock Jarsy PreStocks",
        "url": "https://news.google.com/rss/search?q=xStocks+OR+StableStock+OR+Jarsy+OR+PreStocks+tokenized&hl=en&gl=US&ceid=US:en",
        "tier": 4, "lang": "en", "is_google_news": True,
    },
    {
        "name": "Google News: RWA tokenization",
        "url": "https://news.google.com/rss/search?q=RWA+tokenization&hl=en&gl=US&ceid=US:en",
        "tier": 4, "lang": "en", "is_google_news": True,
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
    },
    {
        "name": "Google News (中文): Pre-IPO 预上市 交易所",
        "url": "https://news.google.com/rss/search?q=Pre-IPO+%E4%BB%A3%E5%B8%81+OR+%E9%A2%84%E4%B8%8A%E5%B8%82+%E5%8C%BA%E5%9D%97%E9%93%BE&hl=zh-CN&gl=CN&ceid=CN:zh-Hans",
        "tier": 4, "lang": "zh", "is_google_news": True,
    },
]

# ──────────────────────────────────────────────────────────────────
# 工具函数
# ──────────────────────────────────────────────────────────────────

def normalize_title(t: str) -> str:
    t = t.lower()
    t = unicodedata.normalize("NFKC", t)
    t = re.sub(r"[^\w\s]", " ", t)
    stopwords = {
        "the","a","an","in","on","of","to","for","and","or","is","are",
        "was","were","has","have","its","this","that","with","by","at",
        "from","as","be","it","new","says","said",
        "的","了","在","是","与","及","将","已","于","对","其","等","有","为",
    }
    words = [w for w in t.split() if w not in stopwords and len(w) > 1]
    return " ".join(sorted(words))

def jaccard(a: str, b: str, threshold: float = 0.55) -> bool:
    sa = set(normalize_title(a).split())
    sb = set(normalize_title(b).split())
    if not sa or not sb:
        return False
    return len(sa & sb) / len(sa | sb) >= threshold

def strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text or "").strip()

def extract_summary(entry: dict, max_chars: int = 150) -> str:
    """
    从 RSS entry 提取摘要，不依赖大模型：
    1. 优先用 summary/description 字段（清理HTML后取前150字）
    2. 如果太短（<30字），尝试 content 字段（部分源有全文）
    3. 都没有则返回空字符串
    最后做句子截断：不在句子中间断开，尽量在句号/问号处截断
    """
    # 尝试各字段
    raw = ""
    for field in ["summary", "description"]:
        val = entry.get(field, "")
        cleaned = strip_html(val).strip()
        if len(cleaned) > len(raw):
            raw = cleaned

    # content 字段（部分源提供全文）
    content_list = entry.get("content", [])
    if content_list and len(raw) < 30:
        for c in content_list:
            val = strip_html(c.get("value", "")).strip()
            if len(val) > len(raw):
                raw = val

    if not raw:
        return ""

    # 清理多余空白
    raw = re.sub(r"\s+", " ", raw).strip()

    if len(raw) <= max_chars:
        return raw

    # 在 max_chars 以内找最近的句子结束符断开，避免截断在词中间
    truncated = raw[:max_chars]
    for sep in ["。", "！", "？", ". ", "! ", "? "]:
        pos = truncated.rfind(sep)
        if pos > max_chars * 0.5:   # 找到且不太靠前
            return truncated[:pos + len(sep)].strip()

    # 找不到句号就在最近空格处截断
    pos = truncated.rfind(" ")
    if pos > max_chars * 0.5:
        return truncated[:pos].strip() + "…"

    return truncated.strip() + "…"


def article_uid(url: str) -> str:
    return hashlib.md5(url.encode()).hexdigest()

def title_uid(title: str) -> str:
    """标题指纹，用于 Google News 跳转URL去重（每次URL不同但标题固定）"""
    return "t:" + hashlib.md5(normalize_title(title).encode()).hexdigest()

# ──────────────────────────────────────────────────────────────────
# 信息源健康监控（必须定义在 fetch_all 之前）
# ──────────────────────────────────────────────────────────────────

def load_health() -> dict:
    if HEALTH_FILE.exists():
        try:
            return json.loads(HEALTH_FILE.read_text())
        except Exception:
            pass
    return {}

def save_health(health: dict):
    HEALTH_FILE.write_text(json.dumps(health))

def update_health_and_alert(status_lines: list):
    """
    解析 fetch_all 状态行，更新连续失败计数。
    某个源连续失败 FEED_FAIL_ALERT_N 次时，推送 Lark 红色告警。
    """
    health = load_health()
    alerts = []

    for line in status_lines:
        # 格式：  ✅ [EN] CoinTelegraph: 1 条
        #        ❌ [ZH] 吴说区块链 WuBlock: HTTP 403
        # 取 [XX] 后面的部分，再以最后一个冒号分割，左边是名字，右边是错误
        after_bracket = line.split("]", 1)[-1].strip() if "]" in line else line.strip()
        if ":" in after_bracket:
            name = after_bracket.rsplit(":", 1)[0].strip()
            err  = after_bracket.rsplit(":", 1)[1].strip()
        else:
            name = after_bracket.strip()
            err  = "未知错误"

        if "✅" in line:
            health[name] = 0
        elif "❌" in line:
            health[name] = health.get(name, 0) + 1
            if health[name] == FEED_FAIL_ALERT_N:
                alerts.append(f"• **{name}** 已连续失败 {health[name]} 次（{err}）")

    save_health(health)

    if alerts and LARK_WEBHOOK:
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
                        "content": "💡 应急：在 RSS_FEEDS 中注释该源，或更新 URL"}]},
                ],
            },
        }
        try:
            requests.post(LARK_WEBHOOK, json=body, timeout=12)
            print(f"[告警] 已推送信息源异常告警：{len(alerts)} 个源")
        except Exception as e:
            print(f"[ERR] 告警推送失败: {e}")

# ──────────────────────────────────────────────────────────────────
# 抓取
# ──────────────────────────────────────────────────────────────────

def fetch_all(hours_back: float = 25) -> list:
    cutoff = datetime.now(SGT) - timedelta(hours=hours_back)
    articles = []
    status_lines = []

    for cfg in RSS_FEEDS:
        try:
            feed = feedparser.parse(
                cfg["url"],
                agent="Mozilla/5.0 (compatible; RWA-NewsBot/3.1; +https://github.com)"
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
                summary = extract_summary(entry)
                if not title or not url:
                    continue

                # 黑名单域名过滤：数据平台链接不是新闻，跳过
                if any(domain in url for domain in URL_BLACKLIST_DOMAINS):
                    continue

                # 中文乱码修复（GBK→UTF-8）
                try:
                    title   = title.encode("latin-1").decode("utf-8")
                    summary = summary.encode("latin-1").decode("utf-8")
                except (UnicodeEncodeError, UnicodeDecodeError):
                    pass

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

    update_health_and_alert(status_lines)
    return articles

# ──────────────────────────────────────────────────────────────────
# 过滤 & 去重
# ──────────────────────────────────────────────────────────────────

def filter_keywords(articles: list) -> list:
    out = []
    for a in articles:
        text = f"{a['title']} {a['summary']}".lower()
        matched = [kw for kw in KEYWORDS if kw.lower() in text]
        if matched:
            a["matched_kws"] = matched[:6]
            out.append(a)
    return out

# 跨语言去重用的实体词提取（品牌名/数字/英文专有名词在中英文标题里都一样）
def extract_entities(title: str) -> set:
    """
    提取标题里的实体：纯英文词、数字、品牌名（大写开头词）
    用于跨语言去重——同一事件的中文和英文标题，实体集合高度重叠
    例：'Bitget IPO Prime preSPAX 认购超1亿' 和 'Bitget IPO Prime preSPAX exceeds $100M'
        实体集合都是 {'Bitget', 'IPO', 'Prime', 'preSPAX'}
    """
    # 提取所有英文词（长度>=3，包含大小写）和数字
    tokens = re.findall(r'[A-Za-z][A-Za-z0-9]{2,}|\d+[MBKmb]?', title)
    return {t.lower() for t in tokens}

def entity_overlap(title_a: str, title_b: str, threshold: float = 0.6, min_intersection: int = 4) -> bool:
    """
    跨语言去重：用较小标题的实体集作分母，判断核心词命中比例。
    要求交集至少 min_intersection 个词，避免 Bitget+IPO+Prime 等通用词误合并不同事件。
    """
    ea = extract_entities(title_a)
    eb = extract_entities(title_b)
    if len(ea) < 2 or len(eb) < 2:
        return False
    intersection = ea & eb
    if len(intersection) < min_intersection:
        return False
    smaller = min(len(ea), len(eb))
    return len(intersection) / smaller >= threshold

def deduplicate(articles: list) -> list:
    sorted_arts = sorted(articles, key=lambda x: (x["tier"], x["pub_dt"]))
    seen_urls   = set()
    seen_titles = []
    unique      = []
    for a in sorted_arts:
        if article_uid(a["url"]) in seen_urls:
            continue
        # 同语言：Jaccard 词集合相似度
        if any(jaccard(a["title"], t) for t in seen_titles):
            continue
        # 跨语言：实体名重叠度（处理中英文报道同一事件）
        if any(entity_overlap(a["title"], t) for t in seen_titles):
            continue
        seen_urls.add(article_uid(a["url"]))
        seen_titles.append(a["title"])
        unique.append(a)
    return unique

# ──────────────────────────────────────────────────────────────────
# Lark 推送（限速 + 重试）
# ──────────────────────────────────────────────────────────────────

_last_send_time = [0.0]  # 模块级共享状态，跟踪上次发送时间

def _post_lark(body: dict, label: str):
    if not LARK_WEBHOOK:
        print(f"[DRY RUN] {label}")
        return

    elapsed = time.time() - _last_send_time[0]
    if elapsed < LARK_SEND_INTERVAL:
        time.sleep(LARK_SEND_INTERVAL - elapsed)

    for attempt in range(1, LARK_MAX_RETRIES + 1):
        try:
            r = requests.post(LARK_WEBHOOK, json=body, timeout=12)
            _last_send_time[0] = time.time()
            if r.status_code == 200:
                resp = r.json() if r.content else {}
                if resp.get("code", 0) != 0:
                    print(f"[WARN] Lark code={resp['code']} msg={resp.get('msg')}（{label}）")
                    if attempt < LARK_MAX_RETRIES:
                        time.sleep(2 ** attempt)
                        continue
                else:
                    print(f"[OK] {label}")
                    return
            else:
                print(f"[WARN] HTTP {r.status_code}（{label}）第{attempt}次")
                if attempt < LARK_MAX_RETRIES:
                    time.sleep(2 ** attempt)
        except Exception as e:
            print(f"[ERR] 网络异常（{label}）第{attempt}次: {e}")
            if attempt < LARK_MAX_RETRIES:
                time.sleep(2 ** attempt)

    print(f"[ERR] 推送失败，已放弃: {label}")


def push_instant(a: dict):
    lang_flag = "🇨🇳" if a.get("lang") == "zh" else "🌐"
    kw_str = "  ".join([f"`{k}`" for k in a.get("matched_kws", [])[:5]])

    kws_lower = str(a.get("matched_kws", "")).lower()
    if any(k in kws_lower for k in ["pre-ipo", "ipo prime", "pre ipo", "预上市"]):
        badge, color = "🔮 Pre-IPO", "purple"
    elif any(k in a["title"].lower() for k in ["binance","bitget","bybit","gate","okx","kraken","coinbase"]):
        badge, color = "🏦 交易所动态", "orange"
    elif any(k in kws_lower for k in ["tradfi","xstocks","stablestock","jarsy","prestocks"]):
        badge, color = "📈 股票代币化", "indigo"
    else:
        badge, color = "📡 RWA 快讯", "blue"

    body = {
        "msg_type": "interactive",
        "card": {
            "config": {"wide_screen_mode": True},
            "header": {"title": {"tag": "plain_text", "content": f"{lang_flag} {badge}"}, "template": color},
            "elements": [
                {"tag": "div", "text": {"tag": "lark_md", "content": f"**{a['title']}**"}},
                {"tag": "div", "text": {"tag": "lark_md", "content": a["summary"] or "_（无摘要）_"}},
                {"tag": "hr"},
                {"tag": "div", "fields": [
                    {"is_short": True, "text": {"tag": "lark_md", "content": f"**来源**\n{a['source']}"}},
                    {"is_short": True, "text": {"tag": "lark_md", "content": f"**时间**\n{a['published']}"}},
                ]},
                {"tag": "div", "text": {"tag": "lark_md", "content": f"**命中关键词** · {kw_str}"}},
                {"tag": "action", "actions": [
                    {"tag": "button", "text": {"tag": "plain_text", "content": "阅读原文 →"},
                     "type": "primary", "url": a["url"]}
                ]},
            ],
        },
    }
    _post_lark(body, f"即时 [{a['source']}] {a['title'][:55]}")


def push_daily_digest(articles: list):
    if not articles:
        print("[INFO] 今日无 RWA 相关新闻，跳过推送")
        return

    today = datetime.now(SGT).strftime("%Y年%m月%d日")

    groups = {
        "🔮 Pre-IPO 动态":  [],
        "🏦 交易所 & 平台":  [],
        "📈 股票代币化":     [],
        "🌐 英文 RWA 资讯":  [],
        "🇨🇳 中文 RWA 资讯": [],
    }

    for a in articles:
        kws = " ".join(a.get("matched_kws", [])).lower()
        tl  = a["title"].lower()
        if any(k in kws for k in ["pre-ipo","ipo prime","pre ipo","预上市","prespacex"]):
            groups["🔮 Pre-IPO 动态"].append(a)
        elif any(k in tl for k in ["binance","bitget","bybit","gate","okx","kraken","coinbase"]):
            groups["🏦 交易所 & 平台"].append(a)
        elif any(k in kws for k in ["xstocks","stablestock","jarsy","prestocks","链上股票","股票代币","stock token","tokenized stock"]):
            groups["📈 股票代币化"].append(a)
        elif a.get("lang") == "zh":
            groups["🇨🇳 中文 RWA 资讯"].append(a)
        else:
            groups["🌐 英文 RWA 资讯"].append(a)

    total    = sum(len(v) for v in groups.values())
    zh_count = len(groups["🇨🇳 中文 RWA 资讯"])

    elements = [
        {"tag": "div", "text": {"tag": "lark_md",
            "content": f"今日去重后共 **{total}** 条 RWA 资讯 · 中文 {zh_count} 条 · 英文 {total - zh_count} 条"}},
        {"tag": "hr"},
    ]
    for group_name, arts in groups.items():
        if not arts:
            continue
        lines = [f"**{group_name}** · {len(arts)} 条"]
        for a in arts[:8]:
            flag = "🇨🇳 " if a.get("lang") == "zh" else ""
            # 标题行（可点击链接）
            lines.append(f"• {flag}[{a['title'][:75]}]({a['url']})")
            # 摘要行：有内容才显示，限60字，灰色字体作为副标题
            summary = (a.get("summary") or "").strip()
            if summary:
                short = summary[:60] + ("…" if len(summary) > 60 else "")
                lines.append(f"  <font color='grey'>{short}</font>")
        elements.append({"tag": "div", "text": {"tag": "lark_md", "content": "\n".join(lines)}})
        elements.append({"tag": "hr"})

    elements.append({"tag": "note", "elements": [{"tag": "plain_text",
        "content": f"🤖 RWA NewsBot v3.1 · {datetime.now(SGT).strftime('%H:%M SGT')} · {len(RSS_FEEDS)} 个信息源"}]})

    body = {
        "msg_type": "interactive",
        "card": {
            "config": {"wide_screen_mode": True},
            "header": {"title": {"tag": "plain_text", "content": f"📰 RWA 日报 · {today}"}, "template": "green"},
            "elements": elements,
        },
    }

    # 卡片超长保护：>38 个 element 时拆成两条
    MAX_ELEMENTS = 38
    if len(elements) > MAX_ELEMENTS:
        body2 = {**body, "card": {**body["card"],
            "header": {**body["card"]["header"],
                "title": {"tag": "plain_text", "content": f"📰 RWA 日报续 · {today}"}},
            "elements": elements[MAX_ELEMENTS:]}}
        body["card"]["elements"] = elements[:MAX_ELEMENTS] + [
            {"tag": "note", "elements": [{"tag": "plain_text", "content": "（内容过多，续见下一条）"}]}]
        _post_lark(body,  f"日报推送（上）{total} 条")
        _post_lark(body2, f"日报推送（下）{total} 条")
    else:
        _post_lark(body, f"日报推送 {total} 条")

# ──────────────────────────────────────────────────────────────────
# 缓存管理
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
    if len(cache) > 3000:
        cache = dict(list(cache.items())[-3000:])
    SEEN_FILE.write_text(json.dumps(cache))

def is_seen(a: dict, cache: dict) -> bool:
    return article_uid(a["url"]) in cache or title_uid(a["title"]) in cache

def mark_seen(a: dict, cache: dict):
    cache[article_uid(a["url"])] = a["title"]
    cache[title_uid(a["title"])]  = a["title"]

# ──────────────────────────────────────────────────────────────────
# 主入口
# ──────────────────────────────────────────────────────────────────

def run_instant():
    print(f"\n[{datetime.now(SGT).strftime('%H:%M SGT')}] ▶ 实时监控")
    cache = load_cache()

    is_cold_start = len(cache) == 0
    hours_back    = 0.5 if is_cold_start else 2
    if is_cold_start:
        print("[⚠️ 冷启动] 缓存为空，只处理最近30分钟，防止洪水推送")

    raw     = fetch_all(hours_back=hours_back)
    matched = filter_keywords(raw)
    new     = [a for a in matched if not is_seen(a, cache)]
    deduped = deduplicate(new)

    to_push  = deduped[:INSTANT_MAX_PUSH]
    to_cache = deduped[INSTANT_MAX_PUSH:]

    for a in to_push:
        push_instant(a)
        mark_seen(a, cache)

    for a in to_cache:
        mark_seen(a, cache)

    if to_cache:
        print(f"[⚠️ 限流] {len(to_cache)} 条超出单次上限({INSTANT_MAX_PUSH})，已缓存但未推送")

    save_cache(cache)
    print(f"[完成] 原始 {len(raw)} → 匹配 {len(matched)} → 新增 {len(new)} → 去重 {len(deduped)} → 推送 {len(to_push)} 条\n")


def run_daily():
    print(f"\n[{datetime.now(SGT).strftime('%H:%M SGT')}] ▶ 生成日报")
    raw     = fetch_all(hours_back=25)
    matched = filter_keywords(raw)
    deduped = deduplicate(matched)
    deduped.sort(key=lambda x: x["pub_dt"], reverse=True)
    print(f"[统计] 原始 {len(raw)} → 匹配 {len(matched)} → 去重后 {len(deduped)} 条")
    push_daily_digest(deduped)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["instant", "daily"], default="daily")
    args = parser.parse_args()
    run_instant() if args.mode == "instant" else run_daily()
