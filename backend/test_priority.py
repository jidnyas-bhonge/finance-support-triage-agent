"""Quick test: verify payment-failure emails get HIGH priority."""
import urllib.request
import json

tests = [
    ("Payment Failed + Debited",
     "Hi Team, I tried to place an order today, but the payment failed. "
     "However, Rs 2,499 has been debited from my account. Please look into "
     "this urgently. - Krati Patidar"),

    ("Refund Not Credited",
     "I cancelled my order last week and was informed that the refund would "
     "be processed within 5 days. It has been over a week and I still have "
     "not received my refund. Please resolve this immediately. - Krati Patidar"),

    ("Refund Not Received",
     "I have not received my refund yet. I was promised it would arrive "
     "within 3-5 business days but its been 10 days now. Please help. - Khushi"),

    ("Account Hacked",
     "URGENT: I see a login from an unknown IP. Someone hacked my account "
     "and made 3 transactions I did not authorize. Lock everything now!"),

    ("General Inquiry",
     "Hello, what are your savings account interest rates? Thanks!"),
]

print("=" * 70)
print("  PRIORITY RESOLUTION TEST — /classify_urgency endpoint")
print("=" * 70)

for label, body in tests:
    data = json.dumps({"email_body": body}).encode()
    req = urllib.request.Request(
        "http://127.0.0.1:8000/classify_urgency",
        data=data,
        headers={"Content-Type": "application/json"},
    )
    resp = urllib.request.urlopen(req)
    r = json.loads(resp.read())
    status = "PASS" if (
        ("Failed" in label or "Refund" in label) and r["urgency"] == "High"
        or "Hacked" in label and r["urgency"] == "High"
        or "General" in label and r["urgency"] == "Low"
    ) else "CHECK"
    print(f"\n[{status}] {label}")
    print(f"  Urgency : {r['urgency']}")
    print(f"  Subcat  : {r['subcategory']}")
    print(f"  SLA     : {r['sla']}")
    print(f"  Conf    : {r['confidence']}")
    print(f"  Reason  : {r['reasoning']}")

print("\n" + "=" * 70)
