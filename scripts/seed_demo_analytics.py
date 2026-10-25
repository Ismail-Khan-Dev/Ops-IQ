import sqlite3
import json
from datetime import datetime, timedelta, timezone

def seed_demo_analytics():
    conn = sqlite3.connect("opsiq_dev.db")
    cur = conn.cursor()

    now = datetime.now(timezone.utc)

    # 1. Update Agent Statuses
    agent_updates = [
        ("FraudAgent", "active", 42, "autonomous", 184, 192, 0.94),
        ("InventoryAgent", "active", 28, "autonomous", 145, 150, 0.91),
        ("PricingAgent", "active", 19, "supervised", 88, 95, 0.88),
        ("MarketingAgent", "active", 35, "autonomous", 112, 115, 0.93),
        ("ReviewsAgent", "active", 54, "autonomous", 230, 235, 0.96),
    ]

    for agent_id, status, streak, autonomy, approvals, decisions, conf in agent_updates:
        cur.execute("""
            UPDATE agent_status 
            SET status = ?, streak = ?, autonomy_level = ?, total_approvals = ?, total_decisions = ?, avg_confidence = ?
            WHERE agent_id = ?
        """, (status, streak, autonomy, approvals, decisions, conf, agent_id))

    # 2. Clear old audit entries and insert realistic 7-day operational timeline
    cur.execute("DELETE FROM audit_entries")

    agents_list = [
        ("FraudAgent", "fraud_hold", 450.0, 0.95),
        ("MarketingAgent", "pause_ad_set", 210.0, 0.96),
        ("InventoryAgent", "reorder_restock", 1450.0, 0.92),
        ("PricingAgent", "margin_protection", 380.0, 0.89),
        ("ReviewsAgent", "sentiment_flag", 0.0, 0.97),
        ("FraudAgent", "card_testing_mitigation", 890.0, 0.94),
        ("MarketingAgent", "stockout_prevention", 350.0, 0.91),
        ("InventoryAgent", "bracketing_prevention", 18.5, 0.93),
        ("PricingAgent", "up_exchange_upsell", 67.5, 0.90),
    ]

    decisions = ["auto-approved", "approved", "approved", "auto-approved", "auto-approved"]

    total_financial = 0.0
    for day_offset in range(6, -1, -1):
        day_date = now - timedelta(days=day_offset)
        # Create 5 events per day
        for i in range(5):
            agent, action_type, impact, conf = agents_list[(day_offset * 3 + i) % len(agents_list)]
            decision = decisions[(day_offset + i) % len(decisions)]
            timestamp_str = (day_date - timedelta(hours=i*2, minutes=15)).strftime("%Y-%m-%d %H:%M:%S")

            cur.execute("""
                INSERT INTO audit_entries (action_id, timestamp, agent, action_type, decision, operator, confidence_score, financial_impact, details)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                None,
                timestamp_str,
                agent,
                action_type,
                decision,
                "OpsIQ Autopilot" if decision == "auto-approved" else "Lead Operations Specialist",
                conf,
                impact,
                json.dumps({"verified_savings": impact, "risk_avoidance": True})
            ))
            total_financial += impact

    # 3. Add high-impact preserved margin entries
    high_impact_entries = [
        ("FraudAgent", "bot_wave_blocked", 12500.0, "auto-approved", 0.98),
        ("MarketingAgent", "meta_bleed_freeze", 4850.0, "approved", 0.97),
        ("InventoryAgent", "dead_stock_liquidation", 6400.0, "approved", 0.92),
    ]

    for agent, action_type, impact, decision, conf in high_impact_entries:
        timestamp_str = (now - timedelta(days=1, hours=3)).strftime("%Y-%m-%d %H:%M:%S")
        cur.execute("""
            INSERT INTO audit_entries (action_id, timestamp, agent, action_type, decision, operator, confidence_score, financial_impact, details)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            None,
            timestamp_str,
            agent,
            action_type,
            decision,
            "Autonomous Supervisor",
            conf,
            impact,
            json.dumps({"roi_verified": True, "source": "Shopify Plus Live Webhook"})
        ))
        total_financial += impact

    conn.commit()
    conn.close()
    print(f"Demo analytics seeded successfully! Total Financial Impact: ${total_financial:,.2f}")

if __name__ == "__main__":
    seed_demo_analytics()
