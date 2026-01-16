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
├── services/                 # Microservices
│   ├── ingest-gateway/       # Data ingestion service
│   ├── core-scorer/          # Scoring and signal logic
│   └── state-api/            # API for state management
│
├── core/                     # Shared core logic
│   ├── agent.py              # Agent base classes
│   ├── processor.py          # Data processing utils
│   └── scoring.py            # Scoring algorithms
│
├── executor/                 # Trade execution logic
│   ├── drift_exec.py         # Drift protocol executor
│   ├── hyper_exec.py         # Hyperliquid executor
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

## 🛠 How to Run TradeSync

### 1. 📦 Install Requirements
```bash
pip install -r requirements.txt
```

### 2. 🚀 Start the Agent
```bash
python main.py
```

You will receive alerts via Discord (or Telegram if configured), based on live scored signals.

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
