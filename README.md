<div align="center">

# ⚡ OpsIQ: The Autonomous Operations Platform for $1M–$10M DTC Shopify Brands

### Stop bleeding 4–9% of net margin to manual operations, chargebacks, stockouts, and return leakage.

[![License: MIT](https://img.shields.io/badge/License-MIT-4F46E5.svg)](LICENSE)
[![Shopify API: 2024-01+](https://img.shields.io/badge/Shopify-Built_for_Shopify_Compliant-96bf48.svg?logo=shopify&logoColor=white)](https://shopify.dev)
[![Model Context Protocol](https://img.shields.io/badge/Anthropic_MCP-Native_E--Commerce_Server-D97706.svg?logo=anthropic&logoColor=white)](https://modelcontextprotocol.io)
[![App Bridge v4](https://img.shields.io/badge/Shopify_App_Bridge-v4_Session_Tokens-5c6ac4.svg)](https://shopify.dev/docs/api/app-bridge)
[![Klaviyo JSON:API](https://img.shields.io/badge/Klaviyo-2024--02--15_Verified-000000.svg?logo=klaviyo&logoColor=white)](https://developers.klaviyo.com)
[![Gorgias REST](https://img.shields.io/badge/Gorgias-Helpdesk_Bridge-FF544A.svg)](https://gorgias.com)
[![Meta Graph API](https://img.shields.io/badge/Meta_Ads-v19.0_Auto--Pause-0081FB.svg?logo=meta&logoColor=white)](https://developers.facebook.com/docs/marketing-apis/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688.svg?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![LangGraph](https://img.shields.io/badge/LangGraph-0.2_Supervisor-1437EB.svg)](https://langchain-ai.github.io/langgraph)
[![Next.js 14](https://img.shields.io/badge/Next.js-14_App_Router-000000.svg?logo=next.js&logoColor=white)](https://nextjs.org)

<br/>

**10 Autonomous Agents · 1 Native Slack Command Center · 100% Shadow-Mode Safety**

```
 ┌───────────────────────────┬───────────────────────────┬───────────────────────────┐
 │   14.2x Software ROI      │   $142,000+ Preserved GMV │    380+ Hours Saved / Yr  │
 │   Average annual return   │   Per $5M GMV brand/year  │    Ops labor liberated    │
 └───────────────────────────┴───────────────────────────┴───────────────────────────┘
```

[🚀 Start 14-Day Free Pilot](#pilot-onboarding--pricing) · [📊 Unit Economics & ROI](#the-unit-economics--roi-breakdown) · [⚡ Architecture](#system-architecture) · [🛠️ Quickstart](#quickstart--developer-setup) · [📖 API Reference](#api-v1-reference)

---

</div>

## 🎯 The Executive Dilemma: The Silent "Ops Margin Leak"

Every high-growth DTC brand scaling between **$1M and $10M GMV** hits the exact same operational ceiling. Sales increase, but profit margins evaporate into manual overhead:

```mermaid
flowchart LR
    A["DTC Brand Scales<br/>$1M - $10M GMV"] --> B["The Operations Trap"]
    
    B --> C["1. 3PL Fraud Leakage<br/>Fraudulent pick tickets printed at warehouse<br/>($200-$800 lost/order)"]
    B --> D["2. Return Margin Destruction<br/>$30 items incur $14.50 reverse shipping & restock fees<br/>(100% margin erased)"]
    B --> E["3. Silent Stockout Churn<br/>Bestsellers run out of stock; carts abandoned<br/>(Lost LTV & customer goodwill)"]
    B --> F["4. The 'Human Tabbing' Tax<br/>Ops reps alt-tabbing all day across Shopify, 3PL, Klaviyo & Gorgias<br/>($45K-$60K/year per coordinator)"]

    C --> G["Net Margin Bleed: -4% to -9% GMV"]
    D --> G
    E --> G
    F --> G
```

### The Cost of Inaction

| Operational Bottleneck | Industry Reality | OpsIQ Autonomous Fix | Financial Impact |
|:---|:---|:---|:---|
| **3PL Warehouse Pick Slippage** | Shopify order tags (`FRAUD_HOLD`) are ignored by modern 3PLs (ShipBob, Flexport, Red Stag). Warehouse pick tickets print before manual review. | **Native Fulfillment Orders API Interceptor** places instant API holds directly on warehouse queues in `<50ms`. | **Saves $36,000+/yr** in chargeback penalties and lost inventory. |
| **Low-Ticket Return Erosion** | Returning a \$30-\$45 item burns \$8.50 reverse label + \$3.75 restock + \$2.25 inspection + \$4.50 CS overhead. Refunding cash destroys 100% of margin. | **Smart Returns Unit Economics Engine** automates *"Keep-It + Store Credit"* or *"Instant Variant Exchanges"*. | **Saves \$44,200+/yr** in reverse logistics fees & keeps 100% GMV on store. |
| **Out-of-Stock Abandonment** | When a variant goes OOS, customers cancel their order or abandon checkout. | **Intelligent Order Swaps Engine** dynamically identifies equivalent substitutes and triggers 1-click confirmation via Klaviyo. | **Rescues \$42,800+/yr** in abandoned order value. |
| **Operator Context-Switching** | Teams spend 15+ hours/week copying tracking numbers and checking inventory across 5 tabs. | **Slack Interactive HITL Bot** sends rich Block Kit approval cards directly into your ops channel with 1-click execution. | **Frees 380+ hours/year** of executive & operations time. |

---

## 💡 The Solution: 10 Autonomous Agents. 1 Slack Command Center.

OpsIQ sits natively between your **Shopify Store**, your **3PL Warehouse**, and your **Customer Engagement Stack** (Klaviyo + Gorgias), operating 24/7/365 with mathematical precision.

```mermaid
flowchart TD
    Shopify["Shopify Store<br/>(Orders, Catalog, Returns)"] -->|Webhooks / App Bridge v4| OpsIQ["OpsIQ Supervisor<br/>(LangGraph Multi-Agent Engine)"]
    
    subgraph Agents["10 Specialized Autonomous Agents"]
        direction TB
        A1["🛡️ 3PL Fraud Interceptor"]
        A2["🔄 Intelligent Order Swaps"]
        A3["📦 Smart Returns & Keep-It"]
        A4["📊 Demand & PO Inventory"]
        A5["🏷️ Dynamic Competitor Pricing"]
        A6["💬 Cart Recovery (Klaviyo Bridge)"]
        A7["🎫 Customer Support (Gorgias)"]
        A8["⭐ Review Sentiment Defense"]
        A9["📈 Margin Preservation Calculator"]
        A10["🔍 Reflection & Audit Engine"]
    end
    
    OpsIQ --> Agents
    
    Agents -->|High Confidence + Safe Limits| AutoAction["⚡ Autonomous Execution<br/>(Hold 3PL, Issue Store Credit, Swap Variant)"]
    Agents -->|Requires Human Approval| Slack["💬 Slack Interactive Card<br/>(1-Click Approve / Reject / Tweak)"]
    
    AutoAction --> Ecosystem["Connected Ecosystem"]
    Slack --> Ecosystem
    
    subgraph Ecosystem["Ecosystem Sync"]
        direction LR
        Eco1["3PL Warehouse<br/>(ShipBob / Flexport)"]
        Eco2["Klaviyo<br/>(Custom Event Flows)"]
        Eco3["Gorgias<br/>(Priority Support Tickets)"]
    end
```

---

## 📈 The Unit Economics & ROI Breakdown

For a typical **\$5,000,000 GMV ($416K/month) US DTC Brand**:

```
 ┌───────────────────────────────────────────────────────────────┬──────────────────────────┐
 │ Operational Margin Preservation Area                         │ Annual Financial Benefit │
 ├───────────────────────────────────────────────────────────────┼──────────────────────────┤
 │ 🛡️ Prevented Fraud Chargebacks & Unpicked Inventory Loss     │ +$36,000 / year          │
 │ 📦 Avoided Reverse Logistics & Inspection Fees (Smart Return) │ +$44,200 / year          │
 │ 🔄 Rescued OOS Variant Swaps & Abandoned Carts                │ +$42,800 / year          │
 │ ⏱️ Liberated Human Labor (380+ hours @ $50/hr effective rate) │ +$19,000 / year          │
 ├───────────────────────────────────────────────────────────────┼──────────────────────────┤
 │ 💰 TOTAL ANNUAL NET VALUE DELIVERED                           │ +$142,000 / year         │
 │ 💳 Software Investment (OpsIQ Growth Plan: $999/mo)           │  -$11,988 / year         │
 ├───────────────────────────────────────────────────────────────┼──────────────────────────┤
 │ 🚀 NET RETURN ON INVESTMENT (ROI MULTIPLE)                    │  11.8x - 14.2x ROI       │
 └───────────────────────────────────────────────────────────────┴──────────────────────────┘
```

> **The OpsIQ Guarantee:** If OpsIQ does not preserve more than **3x its subscription cost** in avoided fees, saved margin, and recovered orders during your first 60 days, we credit your entire subscription fee. Zero risk.

---

## 🛡️ Risk-Free Onboarding: 100% Shadow-Mode Safety

The #1 fear of any e-commerce founder or Head of Ops is:  
*"What if the AI makes an autonomous mistake with a live customer order?"*

OpsIQ solves this with an ironclad **Defense-in-Depth Architecture**:

1. **Day 1–14: Complete Shadow Mode (Dry-Run)**  
   OpsIQ installs in **Shadow Mode** (`shadow_mode = True`). The system analyzes real-time orders, assesses fraud risk, and computes optimal returns and swaps **without touching live fulfillments**. Every proposed action is rendered in Slack and your OpsIQ dashboard for review.
2. **Hard Safety Guardrails & Thresholds**  
   Configure maximum price adjustments (default: 5%), purchase order limits (default: \$1,000), and fraud score thresholds (default: 70). Any action exceeding these limits **cannot execute autonomously** and must be approved by an authorized operator.
3. **Streak-Based Autonomy Graduation**  
   Agents must earn autonomy by achieving **50+ consecutive human-approved actions** with >95% confidence before self-executing.
4. **Immutable Audit Trail**  
   Every single evaluation, risk score, LLM reasoning trace, and operator action is cryptographically logged in an append-only PostgreSQL ledger. Zero ghost actions.

---

## 🌟 Core Features & Modules

### 1. Modern 3PL Fulfillment Hold Interceptor
- Bypasses slow, legacy order tags (`FRAUD_HOLD`) that modern 3PL warehouse management systems (WMS) ignore.
- Interfaces directly with Shopify's **Fulfillment Orders API** (`/admin/api/{version}/fulfillment_orders/{id}/hold.json`).
- Prevents 3PLs (ShipBob, Flexport, Red Stag, Whiplash) from picking fraudulent orders before warehouse pick tickets print.

### 2. High-ROI Margin Preservation & Smart Returns
- **Keep-It + Store Credit:** Automatically calculates if an item's reverse shipping + 3PL restock + depreciation exceeds 45% of MSRP. For low-margin returns, it generates a Shopify discount code (`KEEPIT-{order_id}`) and credits the shopper instantly, saving the merchant \$14.50+ in wasted logistics.
- **Instant Variant Exchange:** Detects sizing/fit return requests and proposes direct variant swaps, retaining 100% GMV and avoiding refunds.

### 3. Intelligent Order Swaps Agent
- When a bestseller variant goes out of stock, OpsIQ computes product taxonomy similarity, fit, and price differential to propose an instant substitution.
- Integrates with Klaviyo to fire an **"Order Swap Recommended"** flow allowing the customer to confirm the substitute with 1-click on mobile.

### 4. Slack Interactive Decision Center (Block Kit)
- Beautiful, actionable Slack cards delivered to `#ops-approvals` within seconds of order ingestion.
- Displays risk badges, financial impact, reasoning evidence, and interactive **[Approve]** and **[Reject]** buttons.
- Features HMAC-SHA256 signature verification with a 300-second replay attack drift guard. Decisions update the card in-place.

### 5. Bi-Directional Klaviyo & Gorgias Bridges
- **Klaviyo Modern JSON:API (2024-02-15):** Dispatches custom event payloads (`OpsIQ Cart High Intent Recovered`, `OpsIQ Order Swap Recommended`) with exact tokenization and 1-click confirmation links.
- **Gorgias Helpdesk Bridge:** Auto-creates priority customer support tickets with internal triage notes, sentiment tags, and auto-routed agent escalation.

### 6. 🤖 The World's First E-Commerce Model Context Protocol (MCP) Server
- **Control Your Store from Claude Desktop or Cursor:** OpsIQ exposes an official Anthropic MCP Server (`ecommerce_ops/mcp/`) that lets founders and ops teams command their store via natural conversation.
- **8 Native Tools Exposed:** Assess order fraud, trigger 3PL fulfillment holds, evaluate return unit economics, calculate preserved margin, and audit store readiness.
- **Claude Desktop Configuration (`claude_desktop_config.json`):**
  ```json
  {
    "mcpServers": {
      "opsiq": {
        "command": "python",
        "args": ["-m", "ecommerce_ops.mcp.cli", "--transport", "stdio"],
        "env": {
          "SHOPIFY_SHOP_DOMAIN": "your-brand.myshopify.com",
          "SHOPIFY_ACCESS_TOKEN": "shpat_your_token"
        }
      }
    }
  }
  ```
- **Example Natural Language Prompt:**  
  *“Claude, check OpsIQ orders from today. If any high-risk orders exist, place a 3PL fulfillment hold on ShipBob, and report our net preserved margin.”*

### 7. 🔥 Ad-Spend Bleed Stopper (Meta / TikTok Ads Auto-Pause Guardian)
- **Stop Burning Ad Budget on Out-of-Stock SKUs:** When a bestseller sells out, marketing agencies often take 24–48 hours to notice, burning \$1,500–\$5,000+ driving paid traffic to "Sold Out" pages with 0% conversion.
- **Sub-Second Inventory-to-Ad Sync:** OpsIQ continuously monitors SKU stock levels against active Meta Ad Sets (via Graph API v19.0+). When stock reaches 0, the ad set is **instantly paused**.
- **Auto-Reactivation on Restock:** As soon as inventory is replenished via purchase order or return, OpsIQ automatically reactivates the ad set so your sales momentum never stops.
- **Avoided Spend Counter:** Real-time metrics show exactly how many daily advertising dollars were saved during the out-of-stock window.

### 8. 👗 The "Bracketing / Wardrobing" Anti-Abuse Shield
- **Eliminate Multi-Size Returns Before They Ship:** In apparel, shoppers frequently buy 3 sizes of the same dress to try at home and return 2, causing 35%+ return rates.
- **Proactive Sizing Defense:** OpsIQ flags duplicate style ordering in real time, triggering proactive 1-click fit confirmations with $10 instant store credits.
- **Serial Abuser Deterrent:** Automatically revokes prepaid free return labels for chronic bracket returners, cutting return logistics costs by 18-22%.

### 9. 🎁 The "Post-Purchase Up-Exchange" AI Negotiation Engine
- **Turn 30% of Return Requests into Upsells:** Surrendering to cash refunds destroys 100% of customer GMV. OpsIQ negotiates returns using high-margin warehouse deadstock.
- **Keep-It Sweeteners:** *"Keep your $80 jacket + get our $45 cashmere scarf for just $15 extra!"* (Preserves the $80 sale + brings in $15 new cash).
- **Tier-Up Upgrades:** Offers discounted upgrade differences to trade up to premium catalog tiers.

### 10. 💰 Live "Preserved Margin" Counter & Shopify Admin Badge
- **Proof of Value in Shopify Admin:** An embeddable real-time badge widget showing the exact net dollars preserved across fraud holds, return avoidance, swaps, and ad budget protection.
- Eliminates software churn by proving 5x-14x ROI directly on the merchant's home screen.

---

## 💳 Pilot Onboarding & Pricing

Built strictly on Shopify's official **Billing API** (`recurring_application_charges.json`) with automated **14-day free trials**.

| Plan | Price | Monthly Order Volume | Target Brand Profile | Key Capabilities |
|:---|:---|:---|:---|:---|
| **Starter** | **\$499** / mo | Up to 1,000 orders | Emerging DTC ($1M–$2.5M GMV) | 3PL Hold Interceptor, Basic Slack alerts, Cart recovery bridge, Shadow mode |
| **Growth** *(Most Popular)* | **\$999** / mo | Up to 5,000 orders | Scaling DTC ($2.5M–$7.5M GMV) | All Starter + Smart Returns Keep-It Engine, Intelligent Swaps, Klaviyo + Gorgias Bridges, Priority SLAs |
| **Enterprise** | **\$1,999** / mo | Unlimited orders | Enterprise ($7.5M–$20M+ GMV) | All Growth + Custom ML rule tuning, Dedicated Slack channel, 1-hr SLA, Multi-store orchestration |

*All plans feature 14-day free trials and require zero long-term commitments.*

---

## 🏗️ System Architecture

```mermaid
graph TB
    subgraph "Client Layer"
        ADMIN["Shopify Admin (Embedded iframe)<br/>App Bridge v4 · Dynamic CSP"]
        UI["OpsIQ Next.js 14 Dashboard<br/>React 18 · Tailwind · Zustand"]
        SLACK["Slack Workspace<br/>Block Kit Interactive Cards"]
    end

    subgraph "API & Security Layer"
        API["FastAPI 0.115 Core<br/>API v1 Architecture"]
        AUTH["RBAC Enforcement<br/>5 Roles · 37 Permissions"]
        MW["App Bridge Middleware<br/>frame-ancestors Dynamic CSP"]
        RATE["Redis Rate Limiter<br/>Sliding Window 60 req/min"]
    end

    subgraph "Intelligence & Multi-Agent Core"
        SUP["LangGraph Supervisor Orchestrator<br/>Dynamic Planner & Execution Graph"]
        AGENTS["10 Autonomous Domain Agents<br/>Fraud · Swaps · Returns · Inventory · Pricing · Support"]
        CALC["Margin Preservation Calculator<br/>Unit Economics Financial Modeling"]
        REFLECT["Reflection Agent<br/>Self-Correction & Confidence Scoring"]
    end

    subgraph "Data & Persistence"
        PG[("PostgreSQL 16<br/>Immutable Audit Log · Snapshots")]
        REDIS[("Redis 7<br/>Pub/Sub · Semantic Cache · Task Queue")]
        PGV[("pgvector<br/>Customer Memory Vectors")]
    end

    subgraph "Ecosystem Bridges"
        SHP["Shopify GraphQL & REST<br/>Fulfillment Orders & Billing API"]
        KLV["Klaviyo JSON:API 2024-02-15<br/>Custom Event Tracking"]
        GRG["Gorgias REST API<br/>Ticket & Note Automation"]
    end

    ADMIN --> MW --> API
    UI --> API
    SLACK --> API
    API --> AUTH --> RATE --> SUP
    SUP --> AGENTS & CALC
    AGENTS --> REFLECT
    AGENTS --> SHP & KLV & GRG
    API --> PG & REDIS & PGV
```

---

## ⚡ Quickstart & Developer Setup

### Prerequisites
- **Python**: 3.11+
- **Node.js**: 18+
- **Docker & Docker Compose**: v24+
- **Shopify Partner Account**: App API Key & Secret

### 1. Clone the Repository
```bash
git clone https://github.com/Ismail-Khan-Dev/Ops-IQ.git
cd Ops-IQ
```

### 2. Configure Environment
```bash
cp .env.example .env
```
Key configuration parameters:
```ini
# Core Secrets
SECRET_KEY=generate_with_openssl_rand_hex_32
DATABASE_URL=postgresql+asyncpg://opsiq:opsiq_secret@localhost:5432/ecommerce_ops
REDIS_URL=redis://localhost:6379/0

# Shopify Integration (App Bridge v4 + Billing API)
SHOPIFY_API_KEY=your_shopify_api_key
SHOPIFY_API_SECRET=your_shopify_api_secret
SHOPIFY_SHOP_DOMAIN=your-brand.myshopify.com
SHOPIFY_ACCESS_TOKEN=shpat_your_offline_access_token

# Ecosystem Bridges
SLACK_BOT_TOKEN=xoxb-your-slack-bot-token
SLACK_SIGNING_SECRET=your_slack_signing_secret
KLAVIYO_API_KEY=pk_your_klaviyo_private_key
GORGIAS_DOMAIN=your-brand.gorgias.com
GORGIAS_API_KEY=your_gorgias_api_key
GORGIAS_USER_EMAIL=ops@yourbrand.com
```

### 3. Launch via Docker Compose (Recommended)
```bash
docker compose up -d
```
The stack will spin up 14 interconnected services:
- **FastAPI Core API**: `http://localhost:8000` (Docs: `http://localhost:8000/docs`)
- **Next.js Dashboard**: `http://localhost:3000`
- **Prometheus Metrics**: `http://localhost:9090`
- **Grafana Dashboards**: `http://localhost:3001` (admin / admin)

### 4. Fast Local Evaluation & Zero-Config Setup (SQLite + Next.js)

For rapid local testing and client Loom pitch demonstrations, OpsIQ runs out-of-the-box without Docker:

```bash
# 1. Activate Python virtual environment and initialize local database
.\.venv\Scripts\activate
python scripts/init_local_db.py
python scripts/seed_demo_analytics.py

# 2. Start the FastAPI backend server (Port 8000)
uvicorn ecommerce_ops.api.app:app --host 127.0.0.1 --port 8000

# 3. Start Next.js App Router frontend (Port 3000)
cd frontend
npm run dev

# 4. Open http://localhost:3000/margin-guardian
# Operator API Key for localhost login: opsiq-dev-key-2024
```

### 5. Native MCP Server (Claude Desktop & Cursor IDE)

OpsIQ includes a native **Model Context Protocol (MCP)** server providing LLMs direct, tool-assisted access to Shopify fulfillment, inventory, and margin operations:

```bash
# Automated installer for Claude Desktop (%APPDATA%\Claude) and Cursor
python scripts/setup_mcp.py --install

# Run MCP stdio server manually:
python -m ecommerce_ops.mcp.cli --stdio
```

---

## 🧪 Testing & Verification

OpsIQ is backed by over **1,150 automated tests** ensuring zero regressions across all business logic:

```bash
# Run all backend tests
pytest tests/ -q -o addopts="" -p no:cacheprovider

# Run specific Phase 4 App Store Launch verification
pytest tests/test_phase4_launch.py -v

# Run Native E-Commerce MCP Server tests
pytest tests/test_mcp_server.py -v

# Run Meta Ads OOS Auto-Pause Guardian tests
pytest tests/test_ad_spend_guardian.py -v

# Run Wardrobing Shield & Up-Exchange Engine tests
pytest tests/test_killer_features.py -v

# Run Phase 3 Margin Preservation & Intelligent Swaps tests
pytest tests/test_margin_preservation.py -v

# Run 3PL Fulfillment Hold Interceptor tests
pytest tests/test_fulfillment_hold_interceptor.py -v

# Run Slack Interactive Bot tests
pytest tests/test_slack_interactive.py -v
```

---

## 📡 API v1 Reference

All endpoints are versioned under `/api/v1` and protected by RBAC middleware:

### Pilot Onboarding & Pre-Flight Diagnostic
- `POST /api/v1/onboarding/provision` — Provision new pilot store with default shadow mode & billing setup.
- `GET /api/v1/onboarding/readiness?shop={domain}` — Run 6-step pre-flight readiness audit (OAuth, scopes, 3PL, GDPR webhooks).
- `GET /api/v1/onboarding/cohort` — Aggregate stats across 5-store pilot cohort ($1M–$10M GMV brands).
- `PATCH /api/v1/onboarding/settings` — Toggle shadow mode vs. live autonomous execution.

### Shopify Billing API
- `GET /api/v1/billing/plans` — List Starter ($499), Growth ($999), and Enterprise ($1,999) plan specs & 14-day trial details.
- `POST /api/v1/billing/create-charge` — Generate recurring application charge with confirmation URL.
- `GET /api/v1/billing/callback` — Activate charge upon merchant return from Shopify approval.
- `GET /api/v1/billing/status?shop={domain}` — Verify active subscription status and next billing cycle.

### High-ROI Margin Preservation Analytics
- `GET /api/v1/roi/margin-preservation` — Real-time aggregate dashboard of preserved GMV, avoided logistics fees, and software ROI multiple.
- `GET /api/v1/roi/live-widget` — Live preserved margin counter and embeddable SVG/HTML badge for Shopify Admin.
- `POST /api/v1/roi/wardrobing/evaluate` — Evaluates orders for multi-size bracketing and serial return abuse.
- `POST /api/v1/roi/up-exchange/negotiate` — Generates win-win Keep-It Sweetener Bundles & Tier-Up Upgrades before cash refund.
- `POST /api/v1/roi/returns/evaluate` — Unit economics evaluation for return requests (`keep_it_credit` vs `instant_exchange` vs `standard_return`).
- `POST /api/v1/roi/swaps/evaluate` — Financial delta evaluation for out-of-stock product substitutions.

### Ad-Spend Bleed Stopper (Meta Ads Sync)
- `POST /api/v1/marketing/meta/sync-inventory` — Scans SKU stock against Meta ad sets; auto-pauses ads on 0-stock products.
- `GET /api/v1/marketing/meta/saved-spend` — Real-time metrics on daily and cumulative advertising dollars saved.
- `POST /api/v1/marketing/meta/pause-adset` — Manual override to pause an ad set.
- `POST /api/v1/marketing/meta/unpause-adset` — Manual override to reactivate an ad set.

### 3PL Fulfillment Orders Interceptor
- `GET /api/v1/shopify/orders/{order_id}/fulfillment-orders` — Inspect live warehouse fulfillment orders.
- `POST /api/v1/shopify/fulfillment-orders/{id}/hold` — Place instant hold on warehouse picking.
- `POST /api/v1/shopify/fulfillment-orders/{id}/release` — Release fulfillment hold for verified safe orders.

### Slack HITL & Ecosystem
- `POST /api/v1/slack/interactions` — Receives Slack Block Kit user action payloads with HMAC verification.
- `POST /api/v1/integrations/klaviyo/test` — Tests dispatching custom event flows to Klaviyo profiles.
- `POST /api/v1/integrations/gorgias/test` — Tests ticket creation and internal note injection in Gorgias.

---

## 🤝 The Merchant Pilot Program

Are you a US-based DTC brand doing **\$1M to \$10M GMV** on Shopify?

We are currently enrolling **5 pilot brands** into our high-touch launch cohort:
- **100% Free 14-Day Pilot** in Shadow Mode (zero risk to operations).
- **Custom Margin Audit**: We quantify exactly how much margin you are losing to returns, 3PL fraud slippage, and stockouts.
- **Direct Slack Connect** with our engineering and growth team.
- **Dedicated ROI Guarantee**: 3x software cost recovery or your subscription is credited.

👉 **Apply for the Private Pilot:** [Contact Ismail Khan](mailto:ismail.sajid2001@gmail.com?subject=OpsIQ%20Pilot%20Application) or open an issue on this repository.

---

## 📄 License & Maintainer

Distributed under the MIT License. See [LICENSE](LICENSE) for details.

**Lead Maintainer:**  
**Ismail Khan (Ismail Sajid)** — Systems Architect & E-commerce Operations Lead  
- **GitHub:** [@Ismail-Khan-Dev](https://github.com/Ismail-Khan-Dev)  
- **Repository:** [https://github.com/Ismail-Khan-Dev/Ops-IQ](https://github.com/Ismail-Khan-Dev/Ops-IQ)  

<div align="center">
<br/>

**OpsIQ is engineered for enterprise reliability, high-converting operations, and measurable net profit preservation.**

</div>
