# 🤖 TradeSync AI Agent

> A Modular AI-Powered Crypto Trading Engine for Signal Scoring, On-Chain Execution, and Future Autonomous Trading Agents.

---

## 🧠 What is TradeSync?

**TradeSync** is an AI-driven crypto trading agent designed to mimic the thinking process of a professional trader — but with **machine-speed logic**, real-time data ingestion, and full system modularity.

It collects key market signals (funding, open interest, CVD, price structure, etc.), scores them using custom rule-weighting models, and outputs high-quality **long/short bias alerts** to platforms like Discord or Telegram. These alerts include **confidence scores**, **natural-language rationale**, and optional signal modifiers like SL/TP targets or PnL zones.

> In future versions, TradeSync will also auto-execute trades across **Drift (Solana)** and **Hyperliquid (Custom L2)** using smart wallet logic, execution guards, and LLM-based override systems.

---

## 🧬 Core Vision & Philosophy

TradeSync is built on four key pillars:

1. **Data-Driven Scoring Logic**
   We don't guess. We evaluate. The system ingests real-time funding, delta, trend structure, and technical indicators — then computes a **bias score** based on configurable rules.

2. **Modular Execution Layer**
   Our system will support multiple backends (Drift, Hyperliquid, Base) using a **swappable execution interface** to stay flexible across chains and future infrastructure.

3. **AI Interpretation & Natural Language Alerts**
   All outputs are human-readable, LLM-ready, and structured for social and Discord delivery. No vague signals — only full rationale.

4. **Agent-Based Expansion**
   Future modules include: real-time chart parsing, Pine Script interop, PnL logging, self-improvement scoring loops, and autonomous trade journaling.

---

## ⚙️ What TradeSync Currently Does (v1)

### 🧪 1. Ingests Market Data:
- 📈 Price structure (support, resistance, trend)
- 🔁 Funding rate (bullish/bearish sentiment)
- 📊 Open interest (leverage exposure)
- 🔴 Delta (CVD / net taker flow)
- ⚙️ Technical indicators (VWAP, EMA, FVG, RSI, etc.)

### 🧠 2. Scores the Market:
- Configurable rule system assigns weights to each component
- Long/Short bias scores are calculated
- Confirmation filters applied (e.g., EMA trend must align with funding bias)
- Confidence output between `0–100` for each direction

### 📣 3. Sends Trade Alerts:
- Discord or Telegram bot messages
- Structured markdown:
  - 🔺 Long / 🔻 Short
  - 📊 Confidence score
  - 💡 Signal reason summary
  - ⛓️ Chain reference (e.g., Drift vs Hyperliquid)
  - 📉 Funding / CVD / OI summary
- Optionally includes SL/TP suggestions or Notion journal embeds

---

## 🚀 Future Roadmap

### ✅ Drift Protocol Integration (Solana)
- TradeSync will use `driftpy` SDK for order execution
- Phantom wallet auth
- Stop loss, TP, order type selection
- Real trade journaling + auto-PnL detection

### ✅ Hyperliquid Integration (Custom L2)
- On-chain execution via `hyperliquid-sdk`
- Faster low-latency environment for quant-style agents
- Will support trade loops, order retry systems, and LP-based modifiers

### ✅ Modular Executor Architecture
All future execution layers will follow this folder logic:

```
executor/
├── drift_exec.py # Drift trade logic
├── hyper_exec.py # Hyperliquid trade logic
├── exec_interface.py # Common interface wrapper
```

You can **plug in any protocol** as long as it respects the `exec_interface.py` function signature.

### 🧠 Future Features:

- ✅ PnL tracking and execution stats logging
- ✅ Pine Script signal scraper and parser
- ✅ AI-generated signal explanations using GPT / Claude / LLaMA
- ✅ Streamlit or Next.js web dashboard
- ✅ Voice or video parsing of trading commentary via Whisper (LLM journaling)
- ✅ AI journaling + TradeSync Memory Vault (LLM stores reasoning for each trade)
- ✅ Multi-agent coordination for signal conflict resolution

---

## 🗂 Folder Structure (Modular v1.0)

```bash
tradesync/
├── services/                  # Microservices
│   ├── ingest-gateway/        # Data ingestion service (8080)
│   ├── core-scorer/           # Technical bias & confidence (8001)
│   ├── fusion-engine/         # Confluence scoring & opps (8002)
│   ├── state-api/             # System state & action routing (8000)
│   ├── exec-drift-svc/        # Drift protocol execution (8003)
│   └── exec-hl-svc/           # Hyperliquid execution (8004)
│
├── core/                      # Shared core logic
│   ├── agent.py               # Agent base classes
│   ├── processor.py           # Data processing utils
│   └── scoring.py             # Scoring algorithms
│
├── executor/                  # Legacy trade execution logic (Deprecated)
│   ├── drift_exec.py          # Drift protocol executor
│   ├── hyper_exec.py          # Hyperliquid executor
│   └── exec_interface.py     # Unified method signature
│
├── alerts/                   # Alerting system
│   └── discord.py            # Discord integration
│
├── ops/                      # DevOps & Infrastructure
│   ├── compose.full.yml      # Full stack Docker compose
│   ├── compose.infra.yml     # Infrastructure only compose
│   └── sql/                  # Database schema
│
├── docs/                     # Documentation
├── tests/                    # Test suite
├── main.py                   # Entry point
├── requirements.txt          # Python dependencies
└── README.md                 # This file
```
## 🎛️ Environment Configuration (Phase 3C)

TradeSync uses a `.env` file for configuration. Below are the key Phase 3C variables that control safety guardrails and the news feed:

```bash
# Phase 3C - Market Microstructure & Risk Guardian
MAX_SPREAD_BPS=50.0            # Max bid-ask spread in bps for hard block
OPTIMAL_SPREAD_BPS=2.0         # Spread below which no penalty is applied
MIN_DEPTH_25BP_USD=100000      # Min USD depth required within 25bp of mid
MAX_IMPACT_BPS_5K=25.0         # Max price impact for $5k order in bps
MIN_LIQUIDITY_SCORE=0.3        # Min composite liquidity score (0-1)
MARGIN_STRESS_THRESHOLD=0.8    # Max margin utilization before block
MAX_EXPOSURE_PER_SYMBOL_USD=25000 # Max USD exposure per individual symbol

# Phase 3C - Macro Feed
MACRO_FEED_CACHE_TTL=300       # Cache headlines for 5 minutes
MACRO_RSS_SOURCES='[...]'      # JSON array of RSS news sources
```

---

## 🛠 How to Run TradeSync

### 1. 📦 Install Requirements
```bash
pip install -r requirements.txt
```

### 3. Start the Services (Full Stack)
```bash
docker compose -f ops/compose.full.yml --env-file .env up -d --build
```

### 4. Start the Dashboard (Cockpit UI)
```bash
cd services/cockpit-ui
npm install
npm run dev
```
The dashboard will be available at `http://localhost:3000`.

---

## 🎛️ Cockpit UI & Mock Data
As of **Step 0 / Phase 3A**, the Cockpit UI is fully operational but runs in **Mock/Dry-Run mode**:
- **Execution**: The backend executors (`exec-*-svc`) are configured with `DRY_RUN=true`.
- **Wallets**: No real Solana/Hyperliquid private keys are configured yet.
- **Positions**: The "Live Positions" seen in the UI are generated mock data to demonstrate the dashboard's capabilities.

---

## 📡 API & Compatibility (Step 0)

TradeSync uses a standardized API contract for all clients.

### Canonical Routes (state-api)
- `GET /state/health` - Aggregated health
- `GET /state/snapshot` - High-level summary
- `GET /state/opportunities` - Actionable signals
- `GET /state/evidence` - Signals/Events for an opportunity
- `POST /actions/preview` - Risk-guarded execution plan
- `POST /actions/execute` - Confirm and route order

### Legacy Aliases (Backward Compatible)
| Legacy Path | Canonical Successor |
| :--- | :--- |
| `/opps` | `/state/opportunities` |
| `/preview` | `/actions/preview` |
| `/execute` | `/actions/execute` |
| `/execution/status` | `/state/execution/status` |

> [!IMPORTANT]
> Legacy aliases return `Deprecation: true` headers and point to successors in the `Link` header.

---

## 👨‍🔧 Tech Stack

| Layer | Tool | Purpose |
|-------|------|---------|
| Core Logic | Python | Main signal logic, modular file structure |
| Market Data | yfinance, ta, HTTP APIs | Collects live CVD, OI, price, funding |
| AI Layer (Future) | LangChain, OpenAI | LLM-based reasoning and explanation generation |
| Voice Parser | openai-whisper | (Optional) Parse voice logs into journal insight |
| Alerts | discord-webhook, requests | Sends formatted alerts to Discord/Telegram |
| Execution Layer | driftpy, hyperliquid-sdk | On-chain trade placement logic |
| Frontend (Future) | Streamlit, Next.js | Build dashboard UI for metrics and control panel |
| Env Config | python-dotenv | API key storage and environment control |

---

## 🧩 Contributions & Customization

You can build custom logic modules in:

- `agent/core.py` → Custom scoring logic
- `executor/` → Add new protocol backends
- `alerts/` → Extend to SMS, Email, Slack, etc.
- `data/fetch_data.py` → Add Binance, Bybit, or on-chain feeds
- `main.py` → Plug-in prompt overrides, test suites, CLI args

Custom rule templates (like VibeCoding's logic trees) are encouraged — just add your logic modules and import them inside `core.py`.

---

## 👨‍🚀 Built For:

- AI traders who want autonomous signal agents
- On-chain execution researchers
- Perp strategy developers (solidity, python, pine-script)
- Builders blending human intuition + AI modeling
- Trading signal groups that want full control over alerts

---

## 🧠 Philosophy

*"A trader's instinct can be cloned — if you have their inputs, structure, and timeframes. TradeSync was made to do exactly that."*

We believe LLMs, delta, trend structure, and perpetual market data can be blended into next-gen AI agents that outperform discretionary traders and unlock automated edge at scale.

---

## 📬 Contact

**Created by:** Chasedndt
- **GitHub:** [https://github.com/chasedndt]
- **Discord:** [StrikeZone Crypto]
- **Twitter:** [@Chaser.sol]

---

*Made with ❤️ for the crypto trading community*
