# OpsIQ Demo Environment

This directory contains demo data and configuration for running a self-contained demonstration of OpsIQ.

## Quick Start

```bash
# Start the demo environment
docker compose -f docker-compose.demo.yml up -d

# Wait for services to be ready
docker compose -f docker-compose.demo.yml ps

# Access the application
open http://localhost:8000

# Access Grafana dashboard
open http://localhost:3001
# Login: admin / demo
```

## Demo Scenarios

### 1. Fraud Detection

```bash
# Generate a demo order
curl -X POST http://localhost:8000/api/demo/demo/run/fraud_detection \
  -H "Authorization: Bearer your_api_key"

# Response:
# {
#   "status": "completed",
#   "result": {
#     "order_id": "DEMO-001",
#     "risk_score": 0.85,
#     "decision": "flagged",
#     "reason": "High-risk shipping address"
#   }
# }
```

### 2. Abandoned Cart Recovery

```bash
# Run cart recovery demo
curl -X POST http://localhost:8000/api/demo/demo/run/cart_recovery \
  -H "Authorization: Bearer your_api_key"

# Response:
# {
#   "status": "completed",
#   "result": {
#     "cart_id": "CART-001",
#     "recovery_strategy": "discount_10_percent",
#     "discount_code": "SAVE10-DEMO",
#     "email_sent": true
#   }
# }
```

### 3. Dynamic Pricing

```bash
# Run pricing optimization demo
curl -X POST http://localhost:8000/api/demo/demo/run/price_optimization \
  -H "Authorization: Bearer your_api_key"

# Response:
# {
#   "status": "completed",
#   "result": {
#     "product_id": "PROD-001",
#     "current_price": 49.99,
#     "optimized_price": 44.99,
#     "expected_volume_increase": "20%"
#   }
# }
```

### 4. Customer Support

```bash
# Run customer support demo
curl -X POST http://localhost:8000/api/demo/demo/run/customer_support \
  -H "Authorization: Bearer your_api_key"

# Response:
# {
#   "status": "completed",
#   "result": {
#     "ticket_id": "TICKET-001",
#     "sentiment": "negative",
#     "category": "billing",
#     "priority": "high",
#     "auto_response_generated": true
#   }
# }
```

## ROI Calculator

### Full ROI Calculation

```bash
curl -X POST http://localhost:8000/api/demo/roi/calculate \
  -H "Authorization: Bearer your_api_key" \
  -H "Content-Type: application/json" \
  -d '{
    "active_use_cases": ["fraud_detection", "inventory_management", "price_optimization"],
    "monthly_revenue": 150000,
    "period_months": 12
  }'

# Response:
# {
#   "total_investment": 25000.00,
#   "total_savings": 180000.00,
#   "net_benefit": 155000.00,
#   "roi_percent": 620.0,
#   "payback_period_months": 1.7,
#   "recommendations": [...]
# }
```

### Quick Estimate

```bash
curl -X POST http://localhost:8000/api/demo/roi/quick-estimate \
  -H "Authorization: Bearer your_api_key" \
  -H "Content-Type: application/json" \
  -d '{"monthly_revenue": 100000}'

# Response:
# {
#   "monthly_savings": 15000,
#   "annual_savings": 180000,
#   "roi_percent": 450,
#   "payback_months": 2.1,
#   "labor_hours_saved_monthly": 395
# }
```

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/demo/demo/status` | GET | Demo environment status |
| `/api/demo/demo/scenarios` | GET | List demo scenarios |
| `/api/demo/demo/run/{id}` | POST | Run a demo scenario |
| `/api/demo/roi/calculate` | POST | Full ROI calculation |
| `/api/demo/roi/quick-estimate` | POST | Quick ROI estimate |
| `/api/demo/roi/use-cases` | GET | List available use cases |

## Seed Data

The demo environment comes pre-loaded with:

- **5 Products** - Electronics and accessories
- **3 Customers** - With order history
- **3 Orders** - With risk scores
- **2 Abandoned Carts** - With recovery strategies
- **2 Support Tickets** - With sentiment analysis

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DEMO_MODE` | `true` | Enable demo mode |
| `ENV` | `demo` | Environment name |
| `DATABASE_URL` | PostgreSQL connection | Database URL |
| `REDIS_URL` | Redis connection | Redis URL |

## Accessing Services

| Service | URL | Credentials |
|---------|-----|-------------|
| Application | http://localhost:8000 | API key required |
| PostgreSQL | localhost:5433 | demo / demo_secret |
| Redis | localhost:6380 | - |
| Prometheus | http://localhost:9091 | - |
| Grafana | http://localhost:3001 | admin / demo |
