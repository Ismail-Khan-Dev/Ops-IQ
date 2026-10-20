# API Documentation

Complete API reference for OpsIQ E-Commerce Operations Automation System.

## Base URL

```
http://localhost:8000
```

## Authentication

All endpoints require authentication unless marked as public.

### API Key Authentication

```bash
curl -H "X-API-Key: your_api_key" http://localhost:8000/api/decisions
```

### JWT Token Authentication

```bash
# Login
curl -X POST http://localhost:8000/api/login \
  -H "Content-Type: application/json" \
  -d '{"api_key": "your_api_key"}'

# Use token
curl -H "Authorization: Bearer your_token" http://localhost:8000/api/decisions
```

## Rate Limiting

- **Per Minute**: 60 requests
- **Per Hour**: 1,000 requests

Rate limit headers:
```
X-RateLimit-Limit: 60
X-RateLimit-Remaining: 59
X-RateLimit-Reset: 1640000000
```

## Core Endpoints

### Health Check

```
GET /health
```

**Response**:
```json
{
  "status": "healthy",
  "version": "1.0.0",
  "uptime": 3600,
  "services": {
    "database": "connected",
    "redis": "connected",
    "agents": "running"
  }
}
```

### Login

```
POST /api/login
```

**Request**:
```json
{
  "api_key": "your_api_key",
  "operator_id": "optional_operator_id"
}
```

**Response**:
```json
{
  "success": true,
  "token": "jwt_token",
  "expires_at": "2025-12-21T10:00:00Z",
  "operator_id": "operator_123"
}
```

### Dashboard

```
GET /api/dashboard
```

**Response**:
```json
{
  "pending_decisions": 12,
  "approved_today": 45,
  "rejected_today": 3,
  "agents": {
    "fraud_detection": {"status": "active", "processed_today": 120},
    "inventory_management": {"status": "active", "alerts": 5},
    "price_optimization": {"status": "active", "updates_today": 89}
  },
  "metrics": {
    "revenue_today": 12500.00,
    "orders_today": 85,
    "conversion_rate": 0.032
  }
}
```

### Decisions

```
GET /api/decisions
```

**Query Parameters**:
- `status` (string): Filter by status (pending, approved, rejected)
- `agent` (string): Filter by agent type
- `limit` (integer): Number of results (default: 50)
- `offset` (integer): Pagination offset

**Response**:
```json
{
  "decisions": [
    {
      "id": "decision_123",
      "agent": "fraud_detection",
      "type": "order_risk_assessment",
      "status": "pending",
      "confidence": 0.87,
      "data": {
        "order_id": "ORD-001",
        "risk_score": 0.85,
        "factors": ["high_risk_address", "unusual_pattern"]
      },
      "created_at": "2025-12-20T14:30:00Z"
    }
  ],
  "total": 12,
  "has_more": false
}
```

### Approve Decision

```
POST /api/decisions/{decision_id}/approve
```

**Request**:
```json
{
  "notes": "Order verified via phone call",
  "operator_id": "operator_123"
}
```

**Response**:
```json
{
  "success": true,
  "decision_id": "decision_123",
  "status": "approved",
  "approved_by": "operator_123",
  "approved_at": "2025-12-20T15:00:00Z"
}
```

### Reject Decision

```
POST /api/decisions/{decision_id}/reject
```

**Request**:
```json
{
  "reason": "Confirmed fraudulent order",
  "notes": "Customer reported unauthorized purchase",
  "operator_id": "operator_123"
}
```

**Response**:
```json
{
  "success": true,
  "decision_id": "decision_123",
  "status": "rejected",
  "rejected_by": "operator_123",
  "rejected_at": "2025-12-20T15:00:00Z"
}
```

### Batch Actions

```
POST /api/batch-action
```

**Request**:
```json
{
  "ids": ["decision_123", "decision_124", "decision_125"],
  "action": "approve",
  "reason": "Bulk approval for verified orders",
  "operator_id": "operator_123"
}
```

**Response**:
```json
{
  "success": true,
  "processed": 3,
  "failed": 0,
  "results": [
    {"id": "decision_123", "status": "approved"},
    {"id": "decision_124", "status": "approved"},
    {"id": "decision_125", "status": "approved"}
  ]
}
```

## Agent Endpoints

### Agent Status

```
GET /api/agents/status
```

**Response**:
```json
{
  "agents": [
    {
      "name": "fraud_detection",
      "status": "active",
      "uptime": 3600,
      "processed_today": 120,
      "accuracy": 0.95,
      "last_activity": "2025-12-20T14:55:00Z"
    },
    {
      "name": "inventory_management",
      "status": "active",
      "uptime": 3600,
      "alerts": 5,
      "last_activity": "2025-12-20T14:50:00Z"
    }
  ]
}
```

### Set Agent Autonomy

```
PATCH /api/agents/{agent_id}/autonomy
```

Sets an agent's autonomy level (promote/demote). Graduation also happens automatically after 50 consecutive high-confidence decisions; this endpoint forces the level for an operator.

**Permission**: `agents:configure` (RBAC) / operator API key.

**Request**:
```json
{
  "level": "autonomous"
}
```

**Response**:
```json
{
  "agent_id": "FraudAgent",
  "status": "active",
  "streak": 51,
  "autonomy_level": "autonomous",
  "total_decisions": 128,
  "total_approvals": 121,
  "total_rejections": 7,
  "avg_confidence": 0.97
}
```

Allowed levels: `shadow`, `supervised`, `autonomous`. Unknown agents return `404`, invalid levels `400`.

### Trigger Agent

```
POST /api/agents/{agent_name}/trigger
```

**Request**:
```json
{
  "data": {
    "order_id": "ORD-001"
  }
}
```

**Response**:
```json
{
  "success": true,
  "agent": "fraud_detection",
  "task_id": "task_456",
  "status": "processing"
}
```

## Shopify Integration

### Start OAuth

```
GET /api/shopify/auth/authorize
```

**Query Parameters**:
- `shop` (string): Shopify store domain
- `state` (string): CSRF protection state

**Response**:
```json
{
  "authorization_url": "https://store.myshopify.com/admin/oauth/authorize?client_id=xxx&scope=xxx&state=xxx"
}
```

### OAuth Callback

```
GET /api/shopify/auth/callback
```

**Query Parameters**:
- `code` (string): Authorization code
- `state` (string): CSRF state
- `shop` (string): Store domain

**Response**:
```json
{
  "success": true,
  "shop": "store.myshopify.com",
  "access_token": "access_token",
  "scope": "read_products,write_products"
}
```

### Handle Webhook

```
POST /api/shopify/webhooks
```

**Headers**:
- `X-Shopify-Topic`: Webhook topic
- `X-Shopify-Hmac-Sha256`: HMAC signature

**Request**: Webhook payload

**Response**:
```json
{
  "received": true,
  "topic": "orders/create",
  "processed": true
}
```

### Trigger Sync

```
POST /api/shopify/sync
```

**Request**:
```json
{
  "sync_type": "full",
  "data_types": ["products", "orders", "customers"]
}
```

**Query Parameters**:
- `shop_domain` (optional string): Scope the sync to a specific store. The store must have an active OAuth credential (`ShopifyShopCredential`); otherwise a `400` is returned. When omitted, the environment-configured store is used.

**Response**:
```json
{
  "success": true,
  "sync_id": "sync_789",
  "status": "started",
  "estimated_duration": 300
}
```

### Get Products

```
GET /api/shopify/products
```

**Response**:
```json
{
  "products": [
    {
      "id": "PROD-001",
      "shopify_id": "123456789",
      "name": "Wireless Headphones",
      "price": 79.99,
      "inventory_quantity": 150,
      "status": "active"
    }
  ],
  "total": 50
}
```

### Get Orders

```
GET /api/shopify/orders
```

**Query Parameters**:
- `status` (string): Filter by status
- `limit` (integer): Number of results

**Response**:
```json
{
  "orders": [
    {
      "id": "ORD-001",
      "shopify_id": "987654321",
      "total": 279.98,
      "status": "fulfilled",
      "risk_score": 0.15
    }
  ],
  "total": 100
}
```

## Cart Recovery

### Analyze Cart

```
POST /api/cart-recovery/analyze
```

**Request**:
```json
{
  "cart_id": "CART-001",
  "customer_email": "customer@example.com",
  "items": [
    {"name": "Product A", "price": 49.99, "quantity": 1}
  ],
  "total": 49.99
}
```

**Response**:
```json
{
  "cart_id": "CART-001",
  "recovery_strategy": "discount_10_percent",
  "discount_code": "SAVE10-ABC123",
  "estimated_recovery_rate": 0.18,
  "recommended_actions": [
    "Send recovery email within 1 hour",
    "Include social proof"
  ]
}
```

### Execute Recovery

```
POST /api/cart-recovery/recover
```

**Request**:
```json
{
  "cart_id": "CART-001",
  "strategy": "discount_10_percent",
  "channel": "email"
}
```

**Response**:
```json
{
  "success": true,
  "cart_id": "CART-001",
  "recovery_id": "recovery_456",
  "email_sent": true,
  "discount_code": "SAVE10-ABC123"
}
```

### Recovery Analytics

```
GET /api/cart-recovery/analytics
```

**Response**:
```json
{
  "period": "last_30_days",
  "carts_abandoned": 450,
  "recovery_emails_sent": 400,
  "carts_recovered": 81,
  "recovery_rate": 0.18,
  "revenue_recovered": 12500.00,
  "top_strategies": [
    {"strategy": "discount_10_percent", "recovery_rate": 0.22},
    {"strategy": "free_shipping", "recovery_rate": 0.19}
  ]
}
```

## Customer Support

### Create Ticket

```
POST /api/customer-support/tickets
```

**Request**:
```json
{
  "customer_email": "customer@example.com",
  "subject": "Order issue",
  "message": "My order hasn't arrived yet",
  "priority": "high"
}
```

**Response**:
```json
{
  "ticket_id": "TICKET-001",
  "status": "open",
  "sentiment": "negative",
  "category": "order_issue",
  "priority": "high",
  "estimated_response_time": "2 hours"
}
```

### Resolve Ticket

```
POST /api/customer-support/resolve
```

**Request**:
```json
{
  "ticket_id": "TICKET-001",
  "resolution": "Order shipped via express delivery",
  "satisfaction_rating": 5
}
```

**Response**:
```json
{
  "success": true,
  "ticket_id": "TICKET-001",
  "status": "resolved",
  "resolved_at": "2025-12-20T16:00:00Z"
}
```

### Support Analytics

```
GET /api/customer-support/analytics
```

**Response**:
```json
{
  "period": "last_30_days",
  "tickets_received": 250,
  "auto_resolved": 180,
  "escalated": 70,
  "average_response_time_hours": 2.5,
  "customer_satisfaction": 4.2,
  "top_categories": [
    {"category": "order_issue", "count": 100},
    {"category": "billing", "count": 75}
  ]
}
```

## Memory System

### Store Memory

```
POST /api/memory/store
```

**Request**:
```json
{
  "content": "Customer prefers wireless headphones",
  "memory_type": "preference",
  "importance": 0.8,
  "tags": ["customer", "preference", "audio"]
}
```

**Response**:
```json
{
  "memory_id": "mem_123",
  "stored": true,
  "embedding_id": "emb_456"
}
```

### Semantic Search

```
POST /api/memory/search
```

**Request**:
```json
{
  "query": "headphone preferences",
  "limit": 5,
  "filters": {
    "memory_type": "preference"
  }
}
```

**Response**:
```json
{
  "results": [
    {
      "memory_id": "mem_123",
      "content": "Customer prefers wireless headphones",
      "similarity": 0.92,
      "importance": 0.8,
      "created_at": "2025-12-15T10:00:00Z"
    }
  ],
  "total": 1
}
```

### List Sessions

```
GET /api/memory/sessions
```

**Response**:
```json
{
  "sessions": [
    {
      "session_id": "sess_123",
      "user_id": "user_456",
      "started_at": "2025-12-20T14:00:00Z",
      "last_activity": "2025-12-20T15:00:00Z",
      "memory_count": 15
    }
  ]
}
```

## Security

### Create User

```
POST /security/users
```

**Request**:
```json
{
  "email": "user@example.com",
  "name": "John Doe",
  "role": "operator",
  "permissions": ["read_orders", "approve_decisions"]
}
```

**Response**:
```json
{
  "id": "user_123",
  "email": "user@example.com",
  "role": "operator",
  "created_at": "2025-12-20T15:00:00Z"
}
```

### Create API Key

```
POST /security/api-keys
```

**Request**:
```json
{
  "name": "Production API Key",
  "role": "operator",
  "expires_days": 90
}
```

**Response**:
```json
{
  "id": "key_123",
  "key": "eops_abc123xyz...",
  "name": "Production API Key",
  "role": "operator",
  "expires_at": "2026-03-20T15:00:00Z"
}
```

### List Roles

```
GET /security/roles
```

**Response**:
```json
{
  "roles": [
    {
      "name": "super_admin",
      "display_name": "Super Admin",
      "description": "Full system access",
      "permissions_count": 30,
      "is_system": true
    },
    {
      "name": "admin",
      "display_name": "Admin",
      "description": "User management and configuration",
      "permissions_count": 25,
      "is_system": true
    }
  ]
}
```

### Check Permissions

```
POST /security/check-permissions
```

**Request**:
```json
{
  "permissions": ["approve_decisions", "manage_users"]
}
```

**Response**:
```json
{
  "allowed": false,
  "role": "operator",
  "missing_permissions": ["manage_users"]
}
```

### Audit Summary

```
GET /security/audit/summary?hours=24
```

**Response**:
```json
{
  "period_hours": 24,
  "total_events": 1250,
  "successful_events": 1240,
  "failed_events": 10,
  "success_rate": 0.992,
  "event_types": {
    "authentication": 500,
    "authorization": 400,
    "data_access": 350
  }
}
```

## Observability

### Get Traces

```
GET /api/observability/traces
```

**Response**:
```json
{
  "traces": [
    {
      "trace_id": "trace_123",
      "name": "fraud_detection_order",
      "start_time": "2025-12-20T14:30:00Z",
      "end_time": "2025-12-20T14:30:01Z",
      "duration_ms": 1200,
      "status": "success"
    }
  ]
}
```

### Get Evaluations

```
GET /api/observability/evaluations
```

**Response**:
```json
{
  "evaluations": [
    {
      "eval_id": "eval_123",
      "trace_id": "trace_123",
      "metrics": {
        "accuracy": 0.95,
        "latency_ms": 1200,
        "cost_usd": 0.002
      },
      "score": 0.92
    }
  ]
}
```

## Demo

### Calculate ROI

```
POST /api/demo/roi/calculate
```

**Request**:
```json
{
  "active_use_cases": ["fraud_detection", "inventory_management"],
  "monthly_revenue": 150000,
  "period_months": 12
}
```

**Response**:
```json
{
  "total_investment": 25000.00,
  "total_savings": 180000.00,
  "net_benefit": 155000.00,
  "roi_percent": 620.0,
  "payback_period_months": 1.7,
  "recommendations": [
    "Excellent ROI! Consider scaling implementation to all use cases.",
    "Highest ROI use case: Price Optimization (600%)"
  ]
}
```

### Run Demo Scenario

```
POST /api/demo/demo/run/{scenario_id}
```

**Path Parameters**:
- `scenario_id` (string): Scenario to run (fraud_detection, cart_recovery, price_optimization, customer_support)

**Response**:
```json
{
  "status": "completed",
  "result": {
    "order_id": "DEMO-001",
    "risk_score": 0.85,
    "decision": "flagged",
    "processing_time_ms": 1250
  }
}
```

## Pipeline Trigger

### Trigger Pipeline Run

```
POST /api/run
```

**Request** (optional body):
```json
{
  "shop_domain": "my-other-store.myshopify.com"
}
```

**Parameters**:
- `shop_domain` (optional string): Run the pipeline against a specific store. The store must have an active OAuth credential; the pipeline falls back to the environment store when omitted. The response echoes `shop_domain`.

**Response**:
```json
{
  "status": "started",
  "run_id": "run_123",
  "shop_domain": "my-other-store.myshopify.com"
}
```

## Integrations

### Outbound Webhooks

All endpoints require the `integrations:manage` permission (admin by default).

#### List Webhooks

```
GET /api/integrations/webhooks
```

**Response**:
```json
{
  "webhooks": [
    {
      "id": 1,
      "name": "orders-webhook",
      "url": "https://hooks.example.com/h/acct/9",
      "events": ["hitl_request", "daily_summary"],
      "enabled": true,
      "created_at": "2026-08-19T00:00:00Z"
    }
  ]
}
```

#### Create Webhook

```
POST /api/integrations/webhooks
```

**Request**:
```json
{
  "name": "orders-webhook",
  "url": "https://hooks.example.com/h/acct/9",
  "events": ["hitl_request", "daily_summary"],
  "secret": "optional-shared-secret",
  "enabled": true
}
```

**Notes**:
- `url` must be `https://`; `events` must be known event types (or `["*"]` for all).
- A unique `name` is enforced (409 on duplicates).
- When `secret` is set, dispatched payloads include an `X-Ecom-Ops-Signature` header (HMAC-SHA256 hex of the body).

**Response**: `201` with the serialized webhook (see list shape).

#### Update Webhook

```
PATCH /api/integrations/webhooks/{id}
```

Partial update of `name`, `url`, `events`, `secret`, or `enabled`.

#### Delete Webhook

```
DELETE /api/integrations/webhooks/{id}
```

#### Test Webhook

```
POST /api/integrations/webhooks/{id}/test
```

Sends a test payload to the webhook URL. **Response**: `200` on success.

## Error Responses

### 400 Bad Request

```json
{
  "error": "bad_request",
  "message": "Invalid request parameters",
  "details": {
    "field": "email",
    "issue": "Invalid email format"
  }
}
```

### 401 Unauthorized

```json
{
  "error": "unauthorized",
  "message": "Invalid or missing API key"
}
```

### 403 Forbidden

```json
{
  "error": "forbidden",
  "message": "Insufficient permissions",
  "required_permissions": ["approve_decisions"]
}
```

### 404 Not Found

```json
{
  "error": "not_found",
  "message": "Resource not found",
  "resource": "decision",
  "id": "decision_123"
}
```

### 429 Rate Limited

```json
{
  "error": "rate_limited",
  "message": "Too many requests",
  "retry_after": 60
}
```

### 500 Internal Server Error

```json
{
  "error": "internal_server_error",
  "message": "An unexpected error occurred",
  "request_id": "req_123"
}
```
