"""
Advanced multi-tier email urgency classifier using the native Groq client.

Architecture:
  • Model    : llama-3.1-8b-instant (fastest inference on Groq)
  • Client   : Native groq SDK — zero LangChain overhead
  • Temp     : 0.0 — deterministic, no sampling jitter
  • Tokens   : max_tokens=512 — room for detailed sub-category reasoning
  • Caching  : SHA-256 in-memory dedup avoids redundant API calls
  • Fallback : Graceful degradation to "Medium" on any API/timeout error

Taxonomy (3 urgency tiers × 11 sub-categories):
  HIGH   → Security_Breach, Fraud_Report, Transaction_Failure_Critical,
            Account_Lockout, Billing_Error
  MEDIUM → Dispute_Initiation, Feature_Malfunction, KYC_Compliance
  LOW    → General_Inquiry, Statement_Request, Feedback_Feature_Request,
            Status_Check

Author: Senior AI Engineer — HFT-grade classification pipeline
"""

import os
import json
import time
import hashlib
import logging
from typing import TypedDict, Literal

from groq import Groq
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("urgency_classifier")

# ─────────────────── Configuration ───────────────────

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
MODEL = "llama-3.1-8b-instant"
TEMPERATURE = 0.0
MAX_TOKENS = 512
TIMEOUT_SECONDS = 10  # hard deadline for the API call

# ─────────────────── Taxonomy ───────────────────

URGENCY_TAXONOMY = {
    "High": {
        "sla": "Immediate",
        "description": "Financial loss occurring, security breached, or user completely unable to access funds.",
        "subcategories": {
            "Security_Breach": (
                "Account hacked, unauthorized login from unknown location, "
                "OTP received without request, password changed without consent."
            ),
            "Fraud_Report": (
                "Unauthorized purchases, stolen card, unrecognized transactions, "
                "identity theft, card cloning."
            ),
            "Transaction_Failure_Critical": (
                "Large transfer ($1k+) failed but money deducted, salary payment "
                "didn't go through, refund not received, refund not credited, "
                "refund delayed beyond promised date, payment stuck in limbo, "
                "payment failed but amount debited. NOTE: If the customer says "
                "they have NOT received a refund that was promised, this is "
                "Transaction_Failure_Critical (High), NOT Dispute_Initiation."
            ),
            "Account_Lockout": (
                "Locked out of account with urgent financial need (rent, bills due), "
                "frozen account with no explanation, can't access funds."
            ),
            "Billing_Error": (
                "Charged for cancelled subscription, double-charged on recurring "
                "payment, unauthorized recurring charge, incorrect fee applied, "
                "subscription fee after cancellation. NOTE: If user explicitly says "
                "they cancelled but were still charged, this is Billing_Error (High), "
                "NOT Dispute_Initiation."
            ),
        },
    },
    "Medium": {
        "sla": "24 hours",
        "description": "User is inconvenienced or frustrated, but money is safe. Needs resolving but not a panic situation.",
        "subcategories": {
            "Dispute_Initiation": (
                "Wants to dispute a charge, double charge on statement, "
                "merchant overcharge, chargeback request. NOTE: If the customer "
                "is complaining about a refund not received or money not returned, "
                "that is Transaction_Failure_Critical (High), NOT Dispute_Initiation."
            ),
            "Feature_Malfunction": (
                "App crashes, can't download statement, can't update address, "
                "feature not working as expected, UI bug."
            ),
            "KYC_Compliance": (
                "Document rejected, need to update passport/ID details, "
                "verification pending, compliance hold on account."
            ),
        },
    },
    "Low": {
        "sla": "48 hours",
        "description": "General questions, feedback, or non-critical administrative tasks. No financial impact.",
        "subcategories": {
            "General_Inquiry": (
                "Interest rates, product features, supported transfers, "
                "eligibility questions, how-to questions."
            ),
            "Statement_Request": (
                "Tax certificate, account statement, transaction history, "
                "audit documents."
            ),
            "Feedback_Feature_Request": (
                "Feature suggestion, UI feedback, compliment, general opinion, "
                "dark mode request."
            ),
            "Status_Check": (
                "Card delivery status, application status, transfer status, "
                "refund processing update."
            ),
        },
    },
}

# Build flat lookup: subcategory → urgency level
_SUBCAT_TO_URGENCY: dict[str, str] = {}
_VALID_SUBCATEGORIES: set[str] = set()
for _urg, _meta in URGENCY_TAXONOMY.items():
    for _sub in _meta["subcategories"]:
        _SUBCAT_TO_URGENCY[_sub] = _urg
        _VALID_SUBCATEGORIES.add(_sub)

# ─────────────────── Groq Client (singleton) ───────────────────

_client: Groq | None = None


def _get_client() -> Groq:
    """Lazy-initialise the Groq client (one TCP pool for the process)."""
    global _client
    if _client is None:
        if not GROQ_API_KEY:
            raise RuntimeError(
                "GROQ_API_KEY is not set. "
                "Add it to your .env file: GROQ_API_KEY=gsk_..."
            )
        _client = Groq(api_key=GROQ_API_KEY, timeout=TIMEOUT_SECONDS)
    return _client


# ─────────────────── System Prompt ───────────────────

def _build_system_prompt() -> str:
    """Build the system prompt dynamically from the taxonomy dict."""
    lines = [
        "You are an expert financial support urgency classifier used inside a "
        "high-frequency triage pipeline. Given a customer email you MUST return "
        "ONLY a valid JSON object — no markdown, no backticks, no explanation "
        "outside the JSON.\n",
        "CLASSIFICATION TAXONOMY",
        "=" * 50,
    ]

    urgency_emoji = {"High": "RED", "Medium": "YELLOW", "Low": "GREEN"}

    for urgency, meta in URGENCY_TAXONOMY.items():
        lines.append(
            f"\n[{urgency_emoji[urgency]}] {urgency.upper()} URGENCY "
            f"(SLA: {meta['sla']})"
        )
        lines.append(f"Definition: {meta['description']}")
        lines.append("Sub-categories:")
        for subcat, examples in meta["subcategories"].items():
            lines.append(f"  • {subcat}: {examples}")

    lines.append("\n" + "=" * 50)
    lines.append(
        "\nCLASSIFICATION RULES:\n"
        "1. First determine the urgency level (High / Medium / Low) based on "
        "financial impact and time-sensitivity.\n"
        "2. Then pick the BEST matching sub-category from that urgency tier.\n"
        "3. If the email spans multiple sub-categories, pick the one with the "
        "HIGHEST urgency.\n"
        "4. Assign a confidence score (0.0–1.0) reflecting how clearly the "
        "email maps to that sub-category.\n"
        "5. Write a concise 1-sentence reasoning.\n"
        "6. Determine the SLA deadline based on urgency tier.\n"
    )

    all_subcats = ", ".join(sorted(_VALID_SUBCATEGORIES))
    lines.append(
        "REQUIRED OUTPUT FORMAT (pure JSON, nothing else):\n"
        "{\n"
        '  "urgency": "<High|Medium|Low>",\n'
        f'  "subcategory": "<one of: {all_subcats}>",\n'
        '  "confidence": <float 0.0-1.0>,\n'
        '  "reasoning": "<one concise sentence>",\n'
        '  "sla": "<Immediate|24 hours|48 hours>"\n'
        "}"
    )

    return "\n".join(lines)


SYSTEM_PROMPT = _build_system_prompt()

# ─────────────────── Result Type ───────────────────


class UrgencyResult(TypedDict):
    urgency: str        # "High" | "Medium" | "Low"
    subcategory: str    # One of the 12 sub-categories
    confidence: float   # 0.0 – 1.0
    reasoning: str      # 1-sentence explanation
    sla: str            # "Immediate" | "24 hours" | "48 hours"


# ─────────────────── In-memory Cache ───────────────────

_cache: dict[str, UrgencyResult] = {}


def _cache_key(text: str) -> str:
    return hashlib.sha256(text.strip().encode()).hexdigest()


# ─────────────────── Fallback ───────────────────

_FALLBACK: UrgencyResult = {
    "urgency": "Medium",
    "subcategory": "Feature_Malfunction",
    "confidence": 0.0,
    "reasoning": "Classification unavailable — defaulted to Medium urgency.",
    "sla": "24 hours",
}


def _parse_response(raw: str) -> UrgencyResult:
    """
    Parse the LLM response into a validated UrgencyResult.
    Strips any stray markdown fences the model might add.
    """
    text = raw.strip()
    # Strip ```json ... ``` wrapper if the model ignores instructions
    if text.startswith("```"):
        text = text.split("\n", 1)[-1]
    if text.endswith("```"):
        text = text.rsplit("```", 1)[0]
    text = text.strip()

    data = json.loads(text)

    # Validate urgency
    urgency = data.get("urgency", "Medium")
    if urgency not in ("High", "Medium", "Low"):
        urgency = "Medium"

    # Validate subcategory — cross-check against taxonomy
    subcategory = data.get("subcategory", "")
    if subcategory not in _VALID_SUBCATEGORIES:
        # Try to infer from urgency level — pick first subcategory
        tier_subcats = list(URGENCY_TAXONOMY[urgency]["subcategories"].keys())
        subcategory = tier_subcats[0] if tier_subcats else "General_Inquiry"

    # Enforce consistency: subcategory must belong to stated urgency
    expected_urgency = _SUBCAT_TO_URGENCY.get(subcategory, urgency)
    if expected_urgency != urgency:
        # Trust the subcategory — it's more specific
        urgency = expected_urgency

    # Determine SLA from urgency
    sla_map = {"High": "Immediate", "Medium": "24 hours", "Low": "48 hours"}
    sla = sla_map.get(urgency, "24 hours")

    confidence = float(data.get("confidence", 0.5))
    confidence = max(0.0, min(1.0, confidence))

    reasoning = str(data.get("reasoning", "No reasoning provided."))

    return UrgencyResult(
        urgency=urgency,
        subcategory=subcategory,
        confidence=confidence,
        reasoning=reasoning,
        sla=sla,
    )


# ─────────────────── Public API ───────────────────

def classify_urgency(email_text: str) -> UrgencyResult:
    """
    Classify the urgency of a finance support email.

    Returns a dict with keys: urgency, subcategory, confidence, reasoning, sla.
    Uses 3-tier taxonomy with 12 sub-categories for precise triage.
    Falls back to Medium urgency on any error.
    """
    if not email_text or not email_text.strip():
        return {**_FALLBACK, "reasoning": "Empty email body — defaulted to Medium."}

    clean = email_text.strip()
    key = _cache_key(clean)

    # ── Cache hit → instant return ──
    if key in _cache:
        logger.debug("Urgency cache hit for key=%s", key[:12])
        return _cache[key]

    # ── API call ──
    t0 = time.perf_counter()
    try:
        client = _get_client()
        response = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"Classify this customer email:\n\n{clean}"},
            ],
            temperature=TEMPERATURE,
            max_tokens=MAX_TOKENS,
            stream=False,
        )
        raw = response.choices[0].message.content or ""
        result = _parse_response(raw)

    except json.JSONDecodeError as exc:
        logger.warning("Urgency classifier JSON parse error: %s", exc)
        result = {**_FALLBACK, "reasoning": f"JSON parse error — defaulted to Medium. ({exc})"}

    except Exception as exc:
        logger.warning("Urgency classifier API error: %s", exc)
        result = {**_FALLBACK, "reasoning": f"API error — defaulted to Medium. ({type(exc).__name__})"}

    elapsed_ms = (time.perf_counter() - t0) * 1000
    logger.info(
        "Urgency classified in %.0f ms → %s / %s (%.2f)",
        elapsed_ms, result["urgency"], result["subcategory"], result["confidence"],
    )

    # ── Cache store ──
    _cache[key] = result
    return result


# ─────────────────── Helper: Map subcategory → parent category ───────────────────

_SUBCAT_TO_PARENT_CATEGORY = {
    "Security_Breach": "Fraud",
    "Fraud_Report": "Fraud",
    "Transaction_Failure_Critical": "Payment Issue",
    "Account_Lockout": "Payment Issue",
    "Billing_Error": "Payment Issue",
    "Dispute_Initiation": "Payment Issue",
    "Feature_Malfunction": "General",
    "KYC_Compliance": "General",
    "General_Inquiry": "General",
    "Statement_Request": "General",
    "Feedback_Feature_Request": "General",
    "Status_Check": "General",
}


def get_parent_category(subcategory: str) -> str:
    """Map a fine-grained subcategory to the broad category (Fraud/Payment Issue/General)."""
    return _SUBCAT_TO_PARENT_CATEGORY.get(subcategory, "General")


# ─────────────────── CLI Quick Test ───────────────────

if __name__ == "__main__":
    samples = [
        # HIGH — Security_Breach
        (
            "URGENT: I just received an OTP code I didn't request, and I can see "
            "a login from an IP in Russia. My account has been compromised! "
            "Please lock everything immediately."
        ),
        # HIGH — Fraud_Report
        (
            "I didn't make a purchase of $4,200 at ElectroMart. My card ending "
            "in 7891 was stolen yesterday. Please freeze my account and reverse "
            "the transactions."
        ),
        # HIGH — Transaction_Failure_Critical
        (
            "My salary transfer of $12,500 failed but the money was deducted "
            "from the sender's account. This is extremely urgent — I need to "
            "pay rent today. Transaction ID: TXN-998877."
        ),
        # HIGH — Account_Lockout
        (
            "I am completely locked out of my account and I have a mortgage "
            "payment due today. I've tried resetting my password three times. "
            "Please help me regain access immediately."
        ),
        # HIGH — Billing_Error
        (
            "I cancelled my premium subscription last month but was charged "
            "$49.99 again today. This is the second time this has happened. "
            "I want a refund and confirmation of cancellation."
        ),
        # MEDIUM — Dispute_Initiation
        (
            "I want to dispute a charge of $89.00 from Amazon on my February "
            "statement. I returned the item and never received a refund. "
            "Please open a dispute case."
        ),
        # MEDIUM — Feature_Malfunction
        (
            "The mobile app crashes every time I try to download my bank "
            "statement. I've tried reinstalling but the issue persists. "
            "Running iOS 18.2."
        ),
        # MEDIUM — KYC_Compliance
        (
            "My uploaded passport was rejected during verification. The image "
            "was clear and within the size limit. Why was it rejected? I need "
            "to update my details for compliance."
        ),
        # LOW — General_Inquiry
        (
            "Hello, I'd like to know what your current interest rates are for "
            "savings accounts. Also, do you support international wire transfers "
            "to EU countries? Thanks!"
        ),
        # LOW — Statement_Request
        (
            "Could you please send me my 2025 tax certificate and the full "
            "year account statement? I need them for my tax filing."
        ),
        # LOW — Feedback_Feature_Request
        (
            "Just a suggestion — you should really add a dark mode to the app. "
            "The current white UI is very bright at night. Otherwise, love the "
            "new update!"
        ),
        # LOW — Status_Check
        (
            "Hi, I applied for a new debit card two weeks ago. What is the "
            "current status of my card delivery? My application reference is "
            "APP-445566."
        ),
    ]

    print("=" * 78)
    print("  URGENCY CLASSIFIER v2 — TAXONOMY TEST (Groq llama-3.1-8b-instant)")
    print("  3 Tiers × 12 Sub-categories")
    print("=" * 78)

    for i, email in enumerate(samples, 1):
        t0 = time.perf_counter()
        result = classify_urgency(email)
        elapsed = (time.perf_counter() - t0) * 1000

        urg = result["urgency"]
        urg_color = {"High": "RED", "Medium": "YLW", "Low": "GRN"}.get(urg, "???")

        print(f"\n{'─' * 78}")
        print(f"  Sample #{i:02d}  |  Latency: {elapsed:.0f} ms  |  [{urg_color}]")
        print(f"{'─' * 78}")
        print(f"  Urgency      : {urg}")
        print(f"  Subcategory  : {result['subcategory']}")
        print(f"  Parent Cat   : {get_parent_category(result['subcategory'])}")
        print(f"  Confidence   : {result['confidence']:.2f}")
        print(f"  SLA          : {result['sla']}")
        print(f"  Reasoning    : {result['reasoning']}")

    print(f"\n{'=' * 78}")
    print("  DONE — All 12 sub-categories tested.")
    print(f"{'=' * 78}")
