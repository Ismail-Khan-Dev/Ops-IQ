#!/usr/bin/env python3
"""
Demo script for clients to test the Customer Support Agent.
Run: python demo.py
"""

import requests
import json
from datetime import datetime

# Configuration
API_URL = "https://YOUR_APP_URL.railway.app"  # Replace after deployment
# API_URL = "http://localhost:8001"  # For local testing

DEMO_TICKETS = [
    {
        "ticket_id": "DEMO-001",
        "customer_email": "sarah@example.com",
        "subject": "Where is my order? #12345",
        "body": "I ordered 5 days ago and haven't received any shipping updates. Can you help?",
        "expected": "WISMO response with tracking info"
    },
    {
        "ticket_id": "DEMO-002",
        "customer_email": "mike@example.com",
        "subject": "Return request - wrong size",
        "body": "I received the wrong size. I ordered Medium but got Large. I want to return it.",
        "expected": "Return policy + RMA number"
    },
    {
        "ticket_id": "DEMO-003",
        "customer_email": "angry@example.com",
        "subject": "This is terrible!",
        "body": "Your product broke after 2 days! This is unacceptable! I want a refund NOW!",
        "expected": "Empathetic response + escalation"
    },
    {
        "ticket_id": "DEMO-004",
        "customer_email": "curious@example.com",
        "subject": "Do you have this in blue?",
        "body": "I saw the product in black. Do you have it in blue? Also, is it waterproof?",
        "expected": "Product info + availability"
    },
    {
        "ticket_id": "DEMO-005",
        "customer_email": "bulk@example.com",
        "subject": "Wholesale inquiry - 500 units",
        "body": "We want to order 500 units for our store. Can you offer bulk pricing?",
        "expected": "Sales lead + pricing tiers"
    }
]


def print_header(text):
    print("\n" + "=" * 60)
    print(f"  {text}")
    print("=" * 60)


def print_ticket(ticket):
    print(f"\n📧 Ticket: {ticket['ticket_id']}")
    print(f"   From: {ticket['customer_email']}")
    print(f"   Subject: {ticket['subject']}")
    print(f"   Body: {ticket['body']}")
    print(f"   Expected: {ticket['expected']}")


def test_health():
    """Test API health endpoint."""
    print_header("TESTING API HEALTH")
    try:
        response = requests.get(f"{API_URL}/health", timeout=10)
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Status: {data.get('status', 'unknown')}")
            print(f"✅ Agent: {data.get('agent', 'unknown')}")
            return True
        else:
            print(f"❌ Health check failed: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Connection error: {e}")
        return False


def test_ticket(ticket):
    """Test a single ticket."""
    print_ticket(ticket)

    try:
        response = requests.post(
            f"{API_URL}/api/v1/analyze",
            json=ticket,
            timeout=30
        )

        if response.status_code == 200:
            data = response.json()
            print(f"\n   🤖 AI Response:")
            print(f"   Sentiment: {data.get('sentiment', 'N/A')}")
            print(f"   Priority: {data.get('priority', 'N/A')}")
            print(f"   Category: {data.get('category', 'N/A')}")
            print(f"   Confidence: {data.get('confidence', 0):.0%}")
            print(f"   Requires Human: {'Yes' if data.get('requires_human') else 'No'}")
            print(f"\n   💬 Suggested Response:")
            for line in data.get('suggested_response', '').split('\n')[:5]:
                print(f"      {line}")
            return True
        else:
            print(f"   ❌ Error: {response.status_code} - {response.text}")
            return False
    except Exception as e:
        print(f"   ❌ Error: {e}")
        return False


def main():
    print_header("CUSTOMER SUPPORT AGENT - DEMO")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"API: {API_URL}")

    # Test health
    if not test_health():
        print("\n⚠️  API not reachable. Check the URL and try again.")
        print(f"   Current URL: {API_URL}")
        return

    # Test tickets
    print_header("TESTING SUPPORT TICKETS")

    passed = 0
    failed = 0

    for ticket in DEMO_TICKETS:
        if test_ticket(ticket):
            passed += 1
        else:
            failed += 1
        print("-" * 40)

    # Summary
    print_header("DEMO RESULTS")
    print(f"✅ Passed: {passed}/{len(DEMO_TICKETS)}")
    if failed:
        print(f"❌ Failed: {failed}/{len(DEMO_TICKETS)}")

    print("\n" + "=" * 60)
    print("  PRICING")
    print("=" * 60)
    print("""
    Starter Package:
    - Setup: $1,500 (one-time)
    - Includes: 1 AI agent, Shopify integration
    - 30 days support included

    Growth Package:
    - Setup: $3,000 (one-time)
    - Monthly: $1,000 retainer
    - Includes: 2 agents, full integration
    - Monthly reports + optimization

    Enterprise:
    - Custom pricing
    - Multi-agent deployment
    - SLA guarantee
    """)


if __name__ == "__main__":
    main()
