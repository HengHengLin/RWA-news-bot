"""
RWA News Monitor v4.0
- 信息源精简：去掉低质量通用媒体，只保留高质量专业源
- 新增律动 BlockBeats 官方 RSS API（快讯级别）
- DeepSeek 二次过滤（判断是否真的与RWA相关）+ 一句话中文总结
- 去重改进：多层策略 + 更合理阈值
"""

import os, re, json, hashlib, unicodedata, requests, feedparser, argparse, time
from datetime import datetime, timezone, timedelta
from pathlib import Path

# ──────────────────────────────────────────────────────────────────
# 环境 & 常量
# ──────────────────────────────────────────────────────────────────

LARK_WEBHOOK       = os.environ.get("LARK_WEBHOOK_URL", "")
DEEPSEEK_API_KEY   = os.environ.get("DEEPSEEK_API_KEY", "")
SGT                = timezone(timedelta(hours=8))
SEEN_FILE          = Path(__file__).parent.parent / ".seen_articles.json"
HEALTH_FILE        = Path(__file__).parent.parent / ".feed_health.json"

LARK_SEND_INTERVAL = 13   # 秒，Lark 限 5条/分钟
LARK_MAX_RETRIES   = 3
FEED_FAIL_ALERT_N  = 3
INSTANT_MAX_PUSH   = 8

# ──────────────────────────────────────────────────────────────────
# ① 关键词（初筛用，DeepSeek 做二次精筛）
# ──────────────────────────────────────────────────────────────────

KEYWORDS = [
    # 核心概念（英文）
    "RWA", "real world asset", "real-world asset",
    "asset tokenization", "tokenized asset", "tokenisation",
    "tokenized treasury", "tokenized treasuries",
    "tokenized bond", "tokenized equity", "tokenized stock",
    "tokenized fund", "tokenized real estate",
    "tokenized gold", "tokenized silver",
    "tokenized commodity", "tokenized credit",
    "tokenized security", "on-chain treasury",
    "on-chain securities", "on-chain equity",
    "digital securities", "security token",
    "fractional ownership blockchain",

    # 核心概念（中文）
    "RWA赛道", "RWA项目", "RWA协议", "RWA市场",
    "现实世界资产", "真实世界资产", "现实资产上链",
    "资产代币化", "代币化资产", "链上资产",
    "代币化", "通证化", "上链",
    "链上黄金", "链上白银", "链上股票", "链上权益",
    "链上基金", "链上国债", "代币化黄金", "代币化白银",
    "代币化股票", "代币化债券", "代币化基金",
    "代币化国债", "股票代币", "股票化代币",
    "证券代币", "证券通证", "通证化证券",
    "美股代币", "美股通证", "股票通证化",
    "债券代币化", "房地产代币化", "黄金代币化",
    "国债代币化", "基金代币化",

    # Pre-IPO & IPO
    "Pre-IPO", "pre IPO", "pre-IPO token", "IPO Prime",
    "tokenized pre-IPO", "pre-IPO tokenization",
    "preSPAX", "预上市", "Pre-IPO代币", "上市前代币",
    "IPO tokenization", "private equity token",
    "tokenized private equity", "unicorn token",
    "Pre-IPO代币化", "上市前股权代币", "未上市股权",

    # TradFi
    "TradFi", "tradfi tokenization", "传统金融代币化",
    "传统资产上链", "机构级代币化", "机构级代币化平台",
    "institutional tokenization", "tokenized TradFi",
    "传统金融上链", "传统资产代币", "链上传统资产",
    "链上金融", "机构入场",

    # 监管 & 牌照
    "SEC tokenization", "SEC tokenized",
    "CFTC tokenization", "MiCA tokenization",
    "DTCC tokenization", "tokenization regulation",
    "DLT Pilot Regime", "牌照", "合规牌照", "数字资产牌照",
    "virtual asset license", "digital asset license",
    "证券牌照", "代币化监管",

    # 重点机构
    "Securitize", "Ondo Finance", "Backed Finance",
    "Maple Finance", "Centrifuge", "Goldfinch",
    "TrueFi", "Superstate", "Franklin Templeton BENJI",
    "BlackRock BUIDL", "OpenEden", "Matrixdock",
    "Swarm Markets", "Robinhood tokenized",
    "USD1", "Plume Network", "Mantra chain",

    # 交易所专项
    "Bitget tokenized", "Bitget stock", "Bitget IPO Prime",
    "Bitget RWA", "Bitget xStocks",
    "Binance tokenized stock", "Binance xStocks", "Binance RWA",
    "Binance Pre-IPO", "币安链上股票",
    "Bybit tokenized", "Bybit stock token", "Bybit RWA", "Bybit xStocks",
    "Gate tokenized", "Gate RWA", "Gate Pre-IPO",
    "OKX tokenized", "OKX RWA", "OKX xStocks",
    "Kraken xStocks", "Coinbase tokenized stock",

    # 股票代币化平台
    "xStocks", "StableStock", "MSX", "Jarsy", "PreStocks",
    "Ondo Global Markets", "Dinari", "tZERO",
    "股票代币平台", "股票通证平台",

    # 上新触发词
    "new tokenized asset", "launches tokenized",
    "lists tokenized", "adds stock token",
    "上线股票代币", "新增代币化资产",
    "leveraged token", "24/7 stock trading",
    "tokenized ETF", "tokenized index",
]

# ──────────────────────────────────────────────────────────────────
# ② 信息源（精简版，只保留高质量源）
# ──────────────────────────────────────────────────────────────────

RSS_FEEDS = [

    # ════════════════════════════════════════════════════
    # 梯队 1｜加密专业媒体（直接 RWA 覆盖，最高优先级）
    # ════════════════════════════════════════════════════
    {
        "name": "CoinTelegraph",
        "url": "https://cointelegraph.com/rss",
        "tier": 1, "lang": "en",  # ✅ 实测可用
    },
    {
        "name": "Blockworks",
        "url": "https://blockworks.co/feed/",
        "tier": 1, "lang": "en",  # ✅ 实测可用，机构级 RWA 报道
    },
    {
        "name": "The Defiant",
        "url": "https://thedefiant.io/api/feed",
        "tier": 1, "lang": "en",  # ✅ DeFi/RWA 专注媒体
    },
    {
        "name": "CryptoSlate RWA",
        "url": "https://cryptoslate.com/feed/rwa/",
        "tier": 1, "lang": "en",  # ✅ RWA 专栏
    },
    {
        "name": "CoinDesk",
        "url": "https://feeds.feedburner.com/CoinDesk",
        "tier": 1, "lang": "en",  # ✅ 实测可用
    },

    # ════════════════════════════════════════════════════
    # 梯队 2｜中文媒体（高质量，已实测）
    # ════════════════════════════════════════════════════
    {
        "name": "律动 BlockBeats 快讯",
        "url": "https://api.theblockbeats.news/v2/rss/newsflash?language=cn",
        "tier": 2, "lang": "zh",  # ✅ 官方 RSS API，快讯级别，质量最高
    },
    {
        "name": "律动 BlockBeats 文章",
        "url": "https://api.theblockbeats.news/v2/rss/article?language=cn",
        "tier": 2, "lang": "zh",  # ✅ 官方 RSS API，深度文章
    },
    {
        "name": "PANews 律动",
        "url": "https://www.panewslab.com/zh/rss",
        "tier": 2, "lang": "zh",  # ✅ 实测可用
    },
    {
        "name": "Odaily 星球日报",
        "url": "https://www.odaily.news/rss",
        "tier": 2, "lang": "zh",  # ✅ 实测可用
    },
    {
        "name": "吴说区块链",
        "url": "https://wublock.substack.com/feed",
        "tier": 2, "lang": "zh",  # ✅ Substack，交易所内幕覆盖好
    },

    # ════════════════════════════════════════════════════
    # 梯队 3｜Google News RSS（精简为6条，只保留最精准的查询）
    # 覆盖 Bloomberg/Reuters/FT 摘要 + 交易所公告报道
    # ════════════════════════════════════════════════════
    {
        "name": "Google News: RWA tokenization",
        "url": "https://news.google.com/rss/search?q=%22RWA%22+%22tokenization%22&hl=en&gl=US&ceid=US:en",
        "tier": 3, "lang": "en", "is_google_news": True,
    },
    {
        "name": "Google News: tokenized assets institutions",
        "url": "https://news.google.com/rss/search?q=%22tokenized%22+%22real+world+assets%22&hl=en&gl=US&ceid=US:en",
        "tier": 3, "lang": "en", "is_google_news": True,
    },
    {
        "name": "Google News: Pre-IPO tokenized",
        "url": "https://news.google.com/rss/search?q=%22Pre-IPO%22+%22tokenized%22+OR+%22IPO+Prime%22&hl=en&gl=US&ceid=US:en",
        "tier": 3, "lang": "en", "is_google_news": True,
    },
    {
        "name": "Google News: exchange stock tokens",
        "url": "https://news.google.com/rss/search?q=%22tokenized+stock%22+OR+%22xStocks%22+OR+%22stock+token%22&hl=en&gl=US&ceid=US:en",
        "tier": 3, "lang": "en", "is_google_news": True,
    },
    {
        "name": "Google News: Securitize Ondo Backed",
        "url": "https://news.google.com/rss/search?q=Securitize+OR+%22Ondo+Finance%22+OR+%22Backed+Finance%22&hl=en&gl=US&ceid=US:en",
        "tier": 3, "lang": "en", "is_google_news": True,
    },
    {
        "name": "Google News (中文): RWA 代币化",
        "url": "https://news.google.com/rss/search?q=RWA+%E4%BB%A3%E5%B8%81%E5%8C%96+OR+%E9%93%BE%E4%B8%8A%E8%82%A1%E7%A5%A8+OR+%E8%82%A1%E7%A5%A8%E4%BB%A3%E5%B8%81&hl=zh-CN&gl=CN&ceid=CN:zh-Hans",
        "tier": 3, "lang": "zh", "is_google_news": True,
    },
]

# 低质量域名黑名单
# 注意：只屏蔽内容质量极差的源，不要过度屏蔽
# Google News real_url 提取不稳定，保守处理
BLOCKED_DOMAINS = {
    "beincrypto.com",
    "livebitcoinnews.com",
    "msn.com",
    "tradingview.com",
    "yellow.com",
    "citizen.co.za",
    "coinpedia.org",
    "zycrypto.com",
    "coinchapter.com",
    "thecoinrepublic.com",
    "u.today",
}

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

def jaccard(a: str, b: str, threshold: float = 0.4) -> bool:
    sa = set(normalize_title(a).split())
    sb = set(normalize_title(b).split())
    if not sa or not sb:
        return False
    return len(sa & sb) / len(sa | sb) >= threshold

def extract_entities(title: str) -> set:
    ENTITY_STOPWORDS = {
        "the","and","for","with","from","this","that","into","over",
        "has","have","its","are","was","been","will","can","but",
        "new","first","how","out","get","use","via","per",
        "opens","brings","launches","makes","gets","gives",
        "access","users","retail","guide","trade","profit",
        "subscribe","subscription","unlocking","masses",
    }
    tokens = re.findall(r"[A-Za-z][A-Za-z0-9]{2,}|\d+[MBKmb]?", title)
    return {t.lower() for t in tokens if t.lower() not in ENTITY_STOPWORDS}

def entity_overlap(a: str, b: str, threshold: float = 0.5, min_intersection: int = 2) -> bool:
    ea = extract_entities(a)
    eb = extract_entities(b)
    if len(ea) < 2 or len(eb) < 2:
        return False
    intersection = ea & eb
    if len(intersection) < min_intersection:
        return False
    return len(intersection) / min(len(ea), len(eb)) >= threshold

def strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text or "").strip()

def article_uid(url: str) -> str:
    return hashlib.md5(url.encode()).hexdigest()

def title_uid(title: str) -> str:
    return "t:" + hashlib.md5(normalize_title(title).encode()).hexdigest()

# ──────────────────────────────────────────────────────────────────
# DeepSeek API
# ──────────────────────────────────────────────────────────────────

def deepseek_filter_and_summarize(articles: list) -> list:
    """
    批量调用 DeepSeek：
    1. 判断每篇文章是否真的与 RWA/链上资产/代币化相关
    2. 对相关文章生成一句话中文总结（30字以内）
    无 API Key 时跳过，直接返回原列表（保持兼容）
    """
    if not DEEPSEEK_API_KEY or not articles:
        return articles

    # 构建批量请求内容，一次调用处理所有文章，节省 token
    items = []
    for i, a in enumerate(articles):
        items.append(f"[{i}] 标题：{a['title']}\n摘要：{(a.get('summary') or '')[:150]}")

    prompt = """你是一个专注于 RWA（Real World Assets，现实世界资产代币化）领域的信息筛选助手。

以下是一批新闻文章，请对每篇做两件事：
1. 判断是否与以下主题真正相关（相关性评分 1-3，3=强相关，2=一般相关，1=不相关）：
   - RWA/现实世界资产代币化
   - 链上股票/债券/黄金/基金等资产
   - Pre-IPO 代币化
   - 传统金融机构进入区块链/代币化领域
   - 主流交易所的股票代币/RWA 新产品
   - 相关监管政策

2. 如果评分 ≥ 2，用中文写一句话总结（30字以内），说明这条新闻的核心信息点

请严格按以下 JSON 格式返回，不要有任何额外文字：
[{"id":0,"score":3,"summary":"BlackRock推出以太坊上代币化货币市场基金BUIDL，机构需求推动规模突破5亿美元"},{"id":1,"score":1,"summary":""},...]

文章列表：
""" + "\n\n".join(items)

    try:
        resp = requests.post(
            "https://api.deepseek.com/chat/completions",
            headers={
                "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": "deepseek-chat",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.1,
                "max_tokens": 1000,
            },
            timeout=30,
        )
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"].strip()

        # 清理可能的 markdown 代码块
        content = re.sub(r"```json|```", "", content).strip()
        results = json.loads(content)

        # 应用结果
        filtered = []
        for item in results:
            idx   = item.get("id", -1)
            score = item.get("score", 1)
            summary = item.get("summary", "")
            if 0 <= idx < len(articles) and score >= 2:
                a = articles[idx].copy()
                if summary:
                    a["ai_summary"] = summary
                filtered.append(a)

        kept = len(filtered)
        dropped = len(articles) - kept
        print(f"[DeepSeek] 过滤前 {len(articles)} 篇 → 保留 {kept} 篇，过滤掉 {dropped} 篇不相关")
        return filtered

    except Exception as e:
        print(f"[WARN] DeepSeek 调用失败，跳过 AI 过滤: {e}")
        return articles  # 失败时返回原列表，不影响正常推送

# ──────────────────────────────────────────────────────────────────
# 信息源健康监控（必须在 fetch_all 之前定义）
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
    health = load_health()
    alerts = []

    for line in status_lines:
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
    cutoff   = datetime.now(SGT) - timedelta(hours=hours_back)
    articles = []
    status_lines = []

    for cfg in RSS_FEEDS:
        try:
            feed = feedparser.parse(
                cfg["url"],
                agent="Mozilla/5.0 (compatible; RWA-NewsBot/4.0; +https://github.com)"
            )
            if feed.get("status", 200) >= 400:
                raise Exception(f"HTTP {feed.get('status')}")

            count = 0
            for entry in feed.entries[:40]:
                pub    = entry.get("published_parsed") or entry.get("updated_parsed")
                pub_dt = datetime(*pub[:6], tzinfo=timezone.utc).astimezone(SGT) if pub else datetime.now(SGT)
                if pub_dt < cutoff:
                    continue

                title   = entry.get("title", "").strip()
                url     = entry.get("link", "").strip()
                summary = strip_html(entry.get("summary", entry.get("description", "")))[:400]

                if not title or not url:
                    continue

                # 中文乱码修复
                try:
                    title   = title.encode("latin-1").decode("utf-8")
                    summary = summary.encode("latin-1").decode("utf-8")
                except (UnicodeEncodeError, UnicodeDecodeError):
                    pass

                # Google News 真实来源 URL
                real_url = ""
                if cfg.get("is_google_news", False):
                    src_href = entry.get("source", {}).get("href", "")
                    if src_href:
                        real_url = src_href.lower()
                    else:
                        for lnk in entry.get("links", []):
                            href = lnk.get("href", "")
                            if href and "google.com" not in href:
                                real_url = href.lower()
                                break

                articles.append({
                    "source":   cfg["name"],
                    "tier":     cfg.get("tier", 3),
                    "lang":     cfg.get("lang", "en"),
                    "title":    title,
                    "url":      url,
                    "real_url": real_url,
                    "summary":  summary,
                    "published": pub_dt.strftime("%Y-%m-%d %H:%M SGT"),
                    "pub_dt":   pub_dt,
                    "is_gn":    cfg.get("is_google_news", False),
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

def filter_blocked_domains(articles: list) -> list:
    out = []
    for a in articles:
        check = a.get("url", "").lower() + " " + a.get("real_url", "").lower()
        if not any(d in check for d in BLOCKED_DOMAINS):
            out.append(a)
        else:
            print(f"  [过滤] 黑名单域名: {a['title'][:50]}")
    return out

def filter_keywords(articles: list) -> list:
    out = []
    for a in articles:
        text    = f"{a['title']} {a['summary']}".lower()
        matched = [kw for kw in KEYWORDS if kw.lower() in text]
        if matched:
            a["matched_kws"] = matched[:6]
            out.append(a)
    return out

def deduplicate(articles: list) -> list:
    """
    三层去重：
    1. URL 精确去重
    2. 标题 Jaccard 相似度（阈值 0.4，比之前更激进）
    3. 实体重叠度（处理同一事件被不同媒体报道，或中英文报道同一事件）
    保留策略：tier 越小越优先
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
        if any(entity_overlap(a["title"], t) for t in seen_titles):
            continue
        seen_urls.add(uid)
        seen_titles.append(a["title"])
        unique.append(a)

    return unique

# ──────────────────────────────────────────────────────────────────
# Lark 推送
# ──────────────────────────────────────────────────────────────────

_last_send_time = [0.0]

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
                    print(f"[WARN] Lark code={resp['code']}（{label}）")
                    if attempt < LARK_MAX_RETRIES:
                        time.sleep(2 ** attempt)
                        continue
                else:
                    print(f"[OK] {label}")
                    return
            else:
                if attempt < LARK_MAX_RETRIES:
                    time.sleep(2 ** attempt)
        except Exception as e:
            print(f"[ERR] 推送异常第{attempt}次: {e}")
            if attempt < LARK_MAX_RETRIES:
                time.sleep(2 ** attempt)

    print(f"[ERR] 推送失败，放弃: {label}")


def push_instant(a: dict):
    lang_flag = "🇨🇳" if a.get("lang") == "zh" else "🌐"
    kw_str    = "  ".join([f"`{k}`" for k in a.get("matched_kws", [])[:4]])

    kws_lower = str(a.get("matched_kws", "")).lower()
    title_l   = a["title"].lower()
    if any(k in kws_lower for k in ["pre-ipo","ipo prime","pre ipo","预上市"]):
        badge, color = "🔮 Pre-IPO", "purple"
    elif any(k in title_l for k in ["binance","bitget","bybit","gate","okx","kraken","coinbase"]):
        badge, color = "🏦 交易所动态", "orange"
    elif any(k in kws_lower for k in ["xstocks","stablestock","jarsy","prestocks","链上股票","股票代币"]):
        badge, color = "📈 股票代币化", "indigo"
    else:
        badge, color = "📡 RWA 快讯", "blue"

    # 优先用 AI 总结，没有的话不显示摘要
    ai_summary = a.get("ai_summary", "")

    elements = [
        {"tag": "div", "text": {"tag": "lark_md", "content": f"**{a['title']}**"}},
    ]
    if ai_summary:
        elements.append(
            {"tag": "div", "text": {"tag": "lark_md", "content": f"💡 {ai_summary}"}}
        )
    elements += [
        {"tag": "hr"},
        {"tag": "div", "fields": [
            {"is_short": True, "text": {"tag": "lark_md", "content": f"**来源**\n{a['source']}"}},
            {"is_short": True, "text": {"tag": "lark_md", "content": f"**时间**\n{a['published']}"}},
        ]},
        {"tag": "div", "text": {"tag": "lark_md", "content": f"**关键词** · {kw_str}"}},
        {"tag": "action", "actions": [
            {"tag": "button", "text": {"tag": "plain_text", "content": "阅读原文 →"},
             "type": "primary", "url": a["url"]}
        ]},
    ]

    body = {
        "msg_type": "interactive",
        "card": {
            "config": {"wide_screen_mode": True},
            "header": {"title": {"tag": "plain_text", "content": f"{lang_flag} {badge}"}, "template": color},
            "elements": elements,
        },
    }
    _post_lark(body, f"即时 [{a['source']}] {a['title'][:50]}")


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
        kws   = " ".join(a.get("matched_kws", [])).lower()
        tl    = a["title"].lower()
        if any(k in kws for k in ["pre-ipo","ipo prime","pre ipo","预上市","prespax"]):
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
    ai_label = " · AI精筛" if DEEPSEEK_API_KEY else ""

    elements = [
        {"tag": "div", "text": {"tag": "lark_md",
            "content": f"今日去重后共 **{total}** 条 RWA 资讯 · 中文 {zh_count} 条 · 英文 {total - zh_count} 条{ai_label}"}},
        {"tag": "hr"},
    ]

    for group_name, arts in groups.items():
        if not arts:
            continue
        lines = [f"**{group_name}** · {len(arts)} 条"]
        for a in arts[:8]:
            flag       = "🇨🇳 " if a.get("lang") == "zh" else ""
            ai_summary = a.get("ai_summary", "")
            # 标题完整显示（不截断）
            lines.append(f"• {flag}[{a['title']}]({a['url']})")
            # AI 总结显示在标题下方，用小字体缩进
            if ai_summary:
                lines.append(f"  💡 {ai_summary}")
        elements.append({"tag": "div", "text": {"tag": "lark_md", "content": "\n".join(lines)}})
        elements.append({"tag": "hr"})

    ai_note = "DeepSeek AI 精筛 · " if DEEPSEEK_API_KEY else ""
    elements.append({"tag": "note", "elements": [{"tag": "plain_text",
        "content": f"🤖 RWA NewsBot v4.0 · {ai_note}{datetime.now(SGT).strftime('%H:%M SGT')} · {len(RSS_FEEDS)} 个信息源"}]})

    body = {
        "msg_type": "interactive",
        "card": {
            "config": {"wide_screen_mode": True},
            "header": {"title": {"tag": "plain_text", "content": f"📰 RWA 日报 · {today}"}, "template": "green"},
            "elements": elements,
        },
    }

    MAX_ELEMENTS = 38
    if len(elements) > MAX_ELEMENTS:
        body2 = {**body, "card": {**body["card"],
            "header": {**body["card"]["header"],
                "title": {"tag": "plain_text", "content": f"📰 RWA 日报续 · {today}"}},
            "elements": elements[MAX_ELEMENTS:]}}
        body["card"]["elements"] = elements[:MAX_ELEMENTS] + [
            {"tag": "note", "elements": [{"tag": "plain_text", "content": "（内容过多，续见下一条）"}]}]
        _post_lark(body,  f"日报（上）{total} 条")
        _post_lark(body2, f"日报（下）{total} 条")
    else:
        _post_lark(body, f"日报 {total} 条")

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
    cache[title_uid(a["title"])] = a["title"]

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
    matched = filter_keywords(filter_blocked_domains(raw))
    new     = [a for a in matched if not is_seen(a, cache)]
    deduped = deduplicate(new)

    # DeepSeek 二次过滤 + 生成摘要
    final   = deepseek_filter_and_summarize(deduped)

    to_push  = final[:INSTANT_MAX_PUSH]
    to_cache = final[INSTANT_MAX_PUSH:]

    for a in to_push:
        push_instant(a)
        mark_seen(a, cache)

    for a in to_cache:
        mark_seen(a, cache)

    if to_cache:
        print(f"[限流] {len(to_cache)} 条超出单次上限({INSTANT_MAX_PUSH})，已缓存但未推送")

    save_cache(cache)
    print(f"[完成] 原始 {len(raw)} → 关键词 {len(matched)} → 新增 {len(new)} → 去重 {len(deduped)} → AI筛后 {len(final)} → 推送 {len(to_push)} 条\n")


def run_daily():
    print(f"\n[{datetime.now(SGT).strftime('%H:%M SGT')}] ▶ 生成日报")

    raw     = fetch_all(hours_back=25)
    matched = filter_keywords(filter_blocked_domains(raw))
    deduped = deduplicate(matched)
    deduped.sort(key=lambda x: x["pub_dt"], reverse=True)

    # DeepSeek 二次过滤 + 生成摘要
    final   = deepseek_filter_and_summarize(deduped)

    print(f"[统计] 原始 {len(raw)} → 关键词 {len(matched)} → 去重 {len(deduped)} → AI筛后 {len(final)} 条")
    push_daily_digest(final)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["instant", "daily"], default="daily")
    args = parser.parse_args()
    run_instant() if args.mode == "instant" else run_daily()
