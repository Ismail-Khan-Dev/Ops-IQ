# 🔌 OpsIQ Model Context Protocol (MCP) Integration Guide
### Claude Desktop & Cursor IDE Setup

OpsIQ features the world's first **Native Model Context Protocol (MCP)** server specifically designed for high-growth Shopify DTC operations ($1M–$10M GMV).

By exposing your e-commerce workflows through MCP, you can converse directly with your store from **Claude Desktop** or **Cursor IDE**, executing complex operations—such as placing 3PL fulfillment holds, auditing Meta ad sets against stockouts, and negotiating customer return exchanges—using conversational natural language.

---

## ⚡ 1-Click Automated Setup

OpsIQ includes an auto-installer that configures both **Claude Desktop** and **Cursor IDE** on your system in seconds:

```powershell
# From the project root in PowerShell:
.\.venv\Scripts\python.exe scripts/setup_mcp.py
```

This script:
1. Detects your OS configuration path (`%APPDATA%\Claude\claude_desktop_config.json` on Windows).
2. Merges the `opsiq` server into your Claude configuration without touching your other MCP servers.
3. Configures `.cursor/mcp.json` for Cursor Composer.
4. Executes an automated stdio pipe handshake to verify that all 11 tools are registered and responsive.

---

## 🛠️ Manual Configuration Details

### 1. Claude Desktop
Config file path:
- **Windows:** `%APPDATA%\Claude\claude_desktop_config.json`
- **macOS:** `~/Library/Application Support/Claude/claude_desktop_config.json`

```json
{
  "mcpServers": {
    "opsiq": {
      "command": "c:\\Users\\HP\\Downloads\\ecom-ops-automation-system-main\\ecom-ops-automation-system-main\\.venv\\Scripts\\python.exe",
      "args": [
        "-m",
        "ecommerce_ops.mcp.cli"
      ],
      "env": {
        "PYTHONPATH": "c:\\Users\\HP\\Downloads\\ecom-ops-automation-system-main\\ecom-ops-automation-system-main",
        "API_KEY": "opsiq-dev-key-2024",
        "ENV": "development"
      }
    }
  }
}
```

### 2. Cursor IDE
OpsIQ includes a pre-configured `.cursor/mcp.json` in the root of the project:
```json
{
  "mcpServers": {
    "opsiq": {
      "command": "c:\\Users\\HP\\Downloads\\ecom-ops-automation-system-main\\ecom-ops-automation-system-main\\.venv\\Scripts\\python.exe",
      "args": [
        "-m",
        "ecommerce_ops.mcp.cli"
      ],
      "env": {
        "PYTHONPATH": "c:\\Users\\HP\\Downloads\\ecom-ops-automation-system-main\\ecom-ops-automation-system-main",
        "API_KEY": "opsiq-dev-key-2024",
        "ENV": "development"
      }
    }
  }
}
```

---

## 🧰 Available Operational Tools (11)

| Tool Name | Operational Purpose |
| :--- | :--- |
| `opsiq_assess_order_fraud` | Real-time fraud detection (0-100 risk score, proxy/VPN checks, zip mismatch). |
| `opsiq_hold_fulfillment_order` | Places an immediate 3PL fulfillment hold via Shopify Fulfillment Orders API. |
| `opsiq_release_fulfillment_order` | Releases a previously held 3PL order so the warehouse can pick/pack. |
| `opsiq_sync_meta_ad_spend` | Audits Shopify stock vs Meta Ads. Auto-pauses ad sets on 0-stock SKUs. |
| `opsiq_detect_bracketing_risk` | Detects multi-size/color bracketing and serial wardrobing abuse. |
| `opsiq_generate_up_exchange_offer` | Generates win-win post-purchase up-exchange and sweetener offers. |
| `opsiq_evaluate_return_economics` | Determines Keep-It vs Return based on reverse logistics fee thresholds. |
| `opsiq_recommend_order_swap` | Evaluates out-of-stock item substitution and margin preserved. |
| `opsiq_get_margin_metrics` | Fetches aggregated preserved GMV, avoided logistics costs, and software ROI. |
| `opsiq_verify_store_readiness` | 6-step pre-flight diagnostic auditing OAuth, 3PL support, and shadow guardrails. |
| `opsiq_list_pending_approvals` | Queries pending high-risk operational decisions in the HITL queue. |

---

## 💬 5 Real-World Prompts to Try in Claude Desktop

Once Claude Desktop is launched, you will see a small **Hammer (🔨) icon** indicating that the OpsIQ tools are connected. Try asking:

### Prompt 1: High-Risk Order Fraud Interception
> *"Claude, we just received Order #9812 for $850. The customer email is `temp123@disposable.net`, shipping zip is 90210, but billing zip is 10001. Assess this order for fraud and tell me if we need to place a 3PL fulfillment hold."*

### Prompt 2: Meta Ad Spend Stockout Audit
> *"Claude, check our inventory stock levels against our active Meta ad campaigns. Are we currently burning money on any sold-out SKUs? If so, pause those ad sets immediately and calculate how much ad spend we preserve per day."*

### Prompt 3: Wardrobing & Bracketing Detection
> *"Claude, Order #4402 contains 2 identical linen dresses in size Small and Medium for $240. The customer has a 35% historical return rate. Is this a bracketing order? What action should our fulfillment team take?"*

### Prompt 4: Up-Exchange & Keep-It Negotiation
> *"A customer wants to return a $95 winter fleece jacket because of sizing fit. Instead of issuing a full refund and paying return freight, generate 2 win-win exchange offers to preserve customer lifetime value."*

### Prompt 5: Live Executive ROI Summary
> *"Claude, show me our live OpsIQ executive ROI dashboard metrics. How much total GMV and net profit margin have our autonomous agents preserved this quarter?"*
