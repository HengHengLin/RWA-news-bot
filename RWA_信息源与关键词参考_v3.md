# RWA News Bot v3 — 信息源 & 关键词完整参考

> 最后更新：2026-04-20
> 信息源总计：**32 个**（英文媒体 14 + 中文媒体 8 + Google News RSS 10）

---

## 一、信息源清单

### 可靠性说明
- ✅ 已通过多个独立来源交叉验证，RSS 端点真实存在
- ⚠️ 来源于第三方聚合器引用，格式合理，上线前建议验证一次
- 📌 Google News RSS（免费，可覆盖 Bloomberg/Reuters/FT/WSJ 摘要）

---

### 梯队 1｜英文加密专业媒体（RWA 直接覆盖，最高优先级）

| 媒体 | RSS URL | 状态 | 说明 |
|------|---------|------|------|
| **CoinTelegraph** | `https://cointelegraph.com/rss` | ✅ | 全球最大加密媒体，RWA 专栏活跃 |
| **Blockworks** | `https://blockworks.co/feed/` | ✅ | 机构级，RWA/DeFi 深度报道 |
| **Decrypt** | `https://decrypt.co/feed` | ✅ | tokenization 覆盖好 |
| **The Defiant** | `https://thedefiant.io/api/feed` | ✅ | DeFi/RWA 专注媒体 |
| **Messari** | `https://messari.io/rss` | ✅ | 研究级，机构视角 |
| **CryptoSlate RWA** | `https://cryptoslate.com/feed/rwa/` | ⚠️ | RWA 专栏分类 RSS，待验证 |

---

### 梯队 2｜中文加密媒体（覆盖华语市场 / 亚洲交易所动态）

| 媒体 | RSS URL | 状态 | 说明 |
|------|---------|------|------|
| **PANews 律动** | `https://www.panewslab.com/zh/rss` | ✅ | 官网有 RSS 入口，国内头部加密媒体 |
| **动区动趋 BlockTempo** | `https://www.blocktempo.com/feed/` | ✅ | WordPress /feed 路径，台湾最大链媒 |
| **Odaily 星球日报** | `https://www.odaily.news/rss` | ⚠️ | 国内头部，有 RSS 订阅功能 |
| **区块律动 BlockBeats** | `https://www.theblockbeats.info/rss` | ⚠️ | 国内知名，路径待验证 |
| **链新闻 ABMedia** | `https://abmedia.io/feed` | ⚠️ | 台湾链新闻，WordPress /feed |
| **吴说区块链** | `https://wublock.substack.com/feed` | ✅ | Substack /feed 路径固定，有效 |
| **ChainFeeds 精选** | `https://www.chainfeeds.xyz/rss` | ✅ | Web3 精选聚合，中文 |
| **CoinTelegraph 中文** | `https://cn.cointelegraph.com/rss` | ✅ | 官方中文版，与英文同架构 |

---

### 梯队 3｜英文通用加密媒体（配合关键词过滤，增加覆盖冗余）

| 媒体 | RSS URL | 状态 |
|------|---------|------|
| **CoinDesk** | `https://feeds.feedburner.com/CoinDesk` | ⚠️ |
| **CryptoBriefing** | `https://cryptobriefing.com/feed/` | ⚠️ |
| **AMBCrypto** | `https://ambcrypto.com/feed` | ⚠️ |
| **NewsBTC** | `https://newsbtc.com/feed` | ⚠️ |
| **CryptoNews** | `https://crypto.news/feed` | ⚠️ |
| **Bitcoin Magazine** | `https://bitcoinmagazine.com/.rss/full/` | ⚠️ |

---

### 梯队 4｜Google News RSS 专项搜索（覆盖传统金融媒体 + 交易所公告报道）

> **重要：** Binance、Bitget、Bybit、Gate 的官方公告页均为 JS 渲染，无原生 RSS。
> 通过 Google News RSS 搜索这些交易所的名称 + 关键词，可以抓到媒体对其新功能/
> 上线资产的第一手报道，同时覆盖 Bloomberg、Reuters、FT 的摘要内容。

| 搜索主题 | 覆盖内容 |
|---------|---------|
| Binance tokenized stocks / Pre-IPO | Binance 链上股票、Pre-IPO 新产品 |
| Bitget IPO Prime / xStocks | Bitget IPO Prime、股票代币新上线 |
| Bybit / Gate tokenized stocks | Bybit/Gate 股票代币动态 |
| xStocks / StableStock / Jarsy / PreStocks | 专项股票代币化平台动态 |
| RWA tokenization | 核心词，覆盖 Bloomberg/Reuters/FT |
| real world assets blockchain | 核心词变体 |
| tokenized equity/securities/stocks | 资产类别专项 |
| Pre-IPO tokenized / IPO Prime | Pre-IPO 代币化专项 |
| Securitize / Ondo tokenization | 头部机构专项 |
| 中文 RWA 代币化 / 链上股票 | 覆盖新浪财经、东方财富等中文媒体 |
| 中文 Pre-IPO 预上市 区块链 | 中文 Pre-IPO 动态 |

---

### 不可用 / 已排除信息源

| 媒体/平台 | 原因 | 替代方案 |
|---------|------|---------|
| Binance 官方公告 | JS 渲染，无原生 RSS | Google News RSS 监控 |
| Bitget 官方公告 | 同上 | Google News RSS 监控 |
| Gate.io 官方公告 | 同上 | Google News RSS 监控 |
| Bybit 官方公告 | 同上 | Google News RSS 监控 |
| The Block | 无公开 RSS，需付费 | 通过 CoinTelegraph/Blockworks 报道覆盖 |
| Financial Times | RSS 需付费订阅 | Google News RSS 获取摘要 |
| Bloomberg | 同上 | Google News RSS 获取摘要 |
| Reuters | 2024年关停公开 RSS | Google News RSS 获取摘要 |
| RWA.xyz News | 纯 JS 渲染，无 RSS | — |
| StableStock 官网 | 无 RSS | Google News RSS 搜索平台名 |
| Jarsy 官网 | 无 RSS | Google News RSS 搜索平台名 |
| PreStocks 官网 | 无 RSS | Google News RSS 搜索平台名 |

---

## 二、关键词完整清单

### 核心概念（中英双语）
```
RWA / real world asset / real-world asset / asset tokenization
tokenized asset / tokenisation
资产代币化 / 现实世界资产 / 链上资产 / 代币化
真实世界资产 / 现实资产上链
```

### 资产类别（英文）
```
tokenized treasury / tokenized treasuries
tokenized bond / tokenized equity / tokenized stock
tokenized fund / tokenized real estate
tokenized gold / tokenized silver
tokenized commodity / tokenized credit / tokenized security
on-chain treasury / on-chain securities / on-chain equity
digital securities / security token / STO
fractional ownership blockchain
```

### 资产类别（中文）
```
链上黄金 / 链上白银 / 链上股票 / 链上权益
链上基金 / 链上国债 / 代币化黄金 / 代币化白银
代币化股票 / 代币化债券 / 代币化基金
代币化国债 / 股票代币 / 股票化代币
证券代币 / 证券通证 / 通证化证券
```

### Pre-IPO & IPO
```
Pre-IPO / pre IPO / pre-IPO token / IPO Prime
tokenized pre-IPO / pre-IPO tokenization
preSPAX / 预上市 / Pre-IPO代币 / 上市前代币
IPO tokenization / private equity token
tokenized private equity / unicorn token
```

### TradFi / 传统金融上链
```
TradFi / tradfi tokenization / 传统金融代币化
传统资产上链 / 机构级代币化 / 机构级代币化平台
institutional tokenization / tokenized TradFi
```

### 监管 & 牌照
```
SEC tokenization / SEC tokenized / SEC 代币化
CFTC tokenization / MiCA tokenization
DTCC tokenization / tokenization regulation
DLT Pilot Regime / 牌照 / 合规牌照 / 数字资产牌照
virtual asset license / digital asset license
证券牌照 / 代币化监管
```

### 重点机构 / 协议
```
Securitize / Ondo Finance / Backed Finance / Maple Finance
Centrifuge / Goldfinch / TrueFi / Superstate
Franklin Templeton BENJI / BlackRock BUIDL
OpenEden / Matrixdock / Swarm Markets
Robinhood tokenized / USD1 / Plume Network / Mantra chain
```

### 交易所专项监控词
```
Bitget: Bitget tokenized / Bitget stock / Bitget IPO Prime / Bitget RWA / Bitget xStocks
Binance: Binance tokenized stock / Binance on-chain stock / Binance xStocks / Binance RWA
         Binance Pre-IPO / 币安链上股票 / 币安股票代币
Bybit: Bybit tokenized / Bybit stock token / Bybit RWA / Bybit xStocks / Bybit Pre-IPO
Gate: Gate tokenized / Gate stock / Gate RWA / Gate Pre-IPO / Gate.io tokenized / Gate 股票代币
OKX: OKX tokenized / OKX stock token / OKX RWA / OKX xStocks
Kraken: Kraken xStocks / Kraken tokenized stock
Coinbase: Coinbase tokenized stock / Coinbase stock token
```

### 股票代币化平台专项
```
xStocks / StableStock / MSX / Jarsy / PreStocks
Republic tokenized / Backed Finance / Ondo Global Markets
Dinari / Swarm Markets / tZERO / INX tokenized
TokenSoft / 股票代币平台 / 股票通证平台
```

### 新上线 / 功能更新触发词
```
new tokenized asset / launches tokenized / lists tokenized / adds stock token
上线股票代币 / 新增代币化资产 / 上新代币 / 上市代币
leveraged token / 24/7 stock trading
tokenized ETF / tokenized index
```

---

## 三、Lark 消息分类规则

日报会自动按以下5类分组展示：

| 分组 | 触发条件 | 卡片颜色 |
|------|---------|---------|
| 🔮 Pre-IPO 动态 | 标题/关键词含 pre-ipo / IPO Prime / 预上市 | purple |
| 🏦 交易所 & 平台 | 标题含 binance/bitget/bybit/gate/okx/kraken | orange |
| 📈 股票代币化 | 关键词含 xstocks/stablestock/jarsy/链上股票 等 | indigo |
| 🌐 英文 RWA 资讯 | 其余英文来源 | blue |
| 🇨🇳 中文 RWA 资讯 | lang=zh 的中文媒体内容 | green |

---

## 四、运维建议

1. **上线第一天**：手动跑 `--mode instant`，查看 ✅/❌ 状态，对 ❌ 的源逐一排查 URL
2. **中文源优先验证**：PANews、Odaily、BlockBeats 的 RSS URL 用浏览器直接打开确认返回 XML
3. **交易所公告**：Google News RSS 的 query 可以随时在 `RSS_FEEDS` 里调整追加，例如新加入 `OKX Pre-IPO` 等词
4. **新平台出现时**：直接在 `KEYWORDS` 里加平台名，同时在 `RSS_FEEDS` 里加一条对应的 Google News RSS
5. **关键词误报**：如发现大量不相关内容被推送，可提高 `jaccard` 去重阈值（0.55 → 0.65），
   或在 `KEYWORDS` 中删除过于泛化的词

---

*本文档由 RWA News Bot v3 配套生成 · 如需更新联系项目维护者*
