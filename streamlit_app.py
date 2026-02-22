"""
Finance Support Triage Agent — Streamlit Cloud (Single-Service)
================================================================
Self-contained Streamlit app that embeds ALL backend logic:
  • PostgreSQL via SQLAlchemy (no separate FastAPI service)
  • AI agent (Groq / LangChain) — ticket analysis + draft response
  • Multi-tier urgency classifier (Groq native client)
  • Gmail IMAP ingestion + SMTP reply
  • Enterprise analytics dashboard, inbox, priority queue, alerts
  • Auto-fetch every 5 min to keep the service alive

Deploy on Streamlit Cloud by pointing to this file.
Set secrets in Streamlit Cloud dashboard → App Settings → Secrets.
"""

import streamlit as st
from streamlit_autorefresh import st_autorefresh
import re
import os
import sys
import uuid
import enum
import json
import hashlib
import logging
import smtplib
import time as _time
from datetime import datetime, timedelta, timezone
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional
from collections import Counter
from pathlib import Path
import plotly.graph_objects as go
import plotly.express as px

# ── Add frontend directory to path for templates ──
_ROOT_DIR = Path(__file__).parent
_FRONTEND_DIR = _ROOT_DIR / "frontend"
if str(_FRONTEND_DIR) not in sys.path:
    sys.path.insert(0, str(_FRONTEND_DIR))

from templates import (
    icon, avatar, pri_badge, cat_badge, sent_badge, tag_html,
    top_bar, sidebar_header, nav_icon_cell, fetch_how_it_works,
    alert_bar, detail_actions, detail_header, insight_grid,
    email_row, welcome_empty, queue_section_header, section_header,
    chart_title_html, analytics_card, sla_breach_row,
    chart_title_inner, category_table, alert_ticket_card,
)

# ═══════════════════════════════════════════════════════
#  LOAD SECRETS  (Streamlit Cloud uses st.secrets, local uses .env)
# ═══════════════════════════════════════════════════════
from dotenv import load_dotenv

# Try local .env files
load_dotenv(os.path.join(_ROOT_DIR, "backend", ".env"))
load_dotenv(os.path.join(_ROOT_DIR, ".env"))


def _secret(key: str, default: str = "") -> str:
    """Get a secret from environment or st.secrets."""
    val = os.getenv(key, "")
    if val:
        return val
    try:
        return st.secrets.get(key, default)
    except Exception:
        return default


DATABASE_URL = _secret("DATABASE_URL")
GROQ_API_KEY = _secret("GROQ_API_KEY")
EMAIL_USER = _secret("EMAIL_USER")
EMAIL_PASSWORD = _secret("EMAIL_PASSWORD")

# ═══════════════════════════════════════════════════════
#  PYDANTIC SCHEMAS  (from backend/schemas.py)
# ═══════════════════════════════════════════════════════
from pydantic import BaseModel, Field
from enum import Enum as PyEnum


class Priority(str, PyEnum):
    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"


class Category(str, PyEnum):
    FRAUD = "Fraud"
    PAYMENT_ISSUE = "Payment Issue"
    GENERAL = "General"


class Sentiment(str, PyEnum):
    POSITIVE = "Positive"
    NEGATIVE = "Negative"
    NEUTRAL = "Neutral"
    URGENT = "Urgent"


class ExtractedEntities(BaseModel):
    customer_name: Optional[str] = Field(default=None)
    transaction_id: Optional[str] = Field(default=None)
    amount: Optional[str] = Field(default=None)


class TicketAnalysis(BaseModel):
    sentiment: Sentiment
    intent: str
    entities: ExtractedEntities
    priority: Priority
    category: Category
    summary: str


class TicketAnalysisWithDraft(TicketAnalysis):
    draft_response: str = Field(
        description=(
            "A professional, empathetic plain-text email reply (80-150 words). "
            "Start with 'Dear <customer_name>,' and end with "
            "'Best regards,\\nFinance Support Team\\nfinance-support@company.com'. "
            "For Fraud: express urgent concern, mention fraud team is investigating, "
            "provide hotline 1-800-FRAUD-HELP. "
            "For Payment Issue: acknowledge inconvenience, mention 2-3 business days resolution, "
            "include reference [REF-XXXXXX]. "
            "For General: be warm and helpful. "
            "Do NOT use markdown formatting."
        ),
    )


# ═══════════════════════════════════════════════════════
#  DATABASE (PostgreSQL via SQLAlchemy)
# ═══════════════════════════════════════════════════════
from sqlalchemy import (
    create_engine, Column, String, Text, Boolean, DateTime, Enum as SAEnum,
    text, inspect as sa_inspect,
)
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.dialects.postgresql import UUID as PGUUID
import enum as _enum


class TicketStatus(str, _enum.Enum):
    OPEN = "Open"
    NEW = "New"
    IN_PROGRESS = "In Progress"
    RESOLVED = "Resolved"
    CLOSED = "Closed"


class TicketPriority(str, _enum.Enum):
    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"


class TicketCategory(str, _enum.Enum):
    FRAUD = "Fraud"
    PAYMENT_ISSUE = "Payment Issue"
    GENERAL = "General"


Base = declarative_base()


class Ticket(Base):
    __tablename__ = "tickets"
    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    customer_name = Column(String(255), nullable=False)
    email_body = Column(Text, nullable=False)
    status = Column(SAEnum(TicketStatus, name="ticket_status", create_constraint=True),
                    nullable=False, default=TicketStatus.NEW)
    priority = Column(SAEnum(TicketPriority, name="ticket_priority", create_constraint=True),
                      nullable=False, default=TicketPriority.MEDIUM)
    category = Column(SAEnum(TicketCategory, name="ticket_category", create_constraint=True),
                      nullable=False, default=TicketCategory.GENERAL)
    sentiment = Column(String(50), nullable=True)
    intent = Column(String(500), nullable=True)
    summary = Column(Text, nullable=True)
    transaction_id = Column(String(100), nullable=True)
    amount = Column(String(50), nullable=True)
    draft_response = Column(Text, nullable=True)
    is_read = Column(Boolean, nullable=False, default=False, server_default="false")
    is_ai_draft_edited = Column(Boolean, nullable=False, default=False, server_default="false")
    created_at = Column(DateTime(timezone=True), nullable=False,
                        default=lambda: datetime.now(timezone.utc))


# ── Engine + Session ──
_db_url = DATABASE_URL
if _db_url and _db_url.startswith("postgres://"):
    _db_url = _db_url.replace("postgres://", "postgresql://", 1)

engine = None
SessionLocal = None

if _db_url:
    engine = create_engine(
        _db_url, echo=False,
        pool_size=5, max_overflow=10, pool_pre_ping=True,
    )
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    # ── Create tables + migrations on first run ──
    if "db_initialized" not in st.session_state:
        try:
            Base.metadata.create_all(bind=engine)
            with engine.begin() as conn:
                try:
                    conn.execute(text("ALTER TYPE ticket_status ADD VALUE IF NOT EXISTS 'Open'"))
                except Exception:
                    pass
                inspector = sa_inspect(engine)
                columns = [c["name"] for c in inspector.get_columns("tickets")]
                if "is_read" not in columns:
                    conn.execute(text("ALTER TABLE tickets ADD COLUMN is_read BOOLEAN NOT NULL DEFAULT FALSE"))
                if "is_ai_draft_edited" not in columns:
                    conn.execute(text("ALTER TABLE tickets ADD COLUMN is_ai_draft_edited BOOLEAN NOT NULL DEFAULT FALSE"))
            st.session_state.db_initialized = True
        except Exception as e:
            st.error(f"Database initialization failed: {e}")


def _get_db():
    """Return a new database session."""
    if SessionLocal is None:
        return None
    db = SessionLocal()
    return db


# ═══════════════════════════════════════════════════════
#  AI AGENT  (Groq + LangChain)
# ═══════════════════════════════════════════════════════
@st.cache_resource
def _get_llm():
    if not GROQ_API_KEY:
        return None
    from langchain_groq import ChatGroq
    return ChatGroq(
        model="llama-3.3-70b-versatile",
        api_key=GROQ_API_KEY, temperature=0,
        max_tokens=2048, request_timeout=60,
    )


@st.cache_resource
def _get_chains():
    llm = _get_llm()
    if llm is None:
        return None, None
    from langchain_core.prompts import ChatPromptTemplate

    structured_llm = llm.with_structured_output(TicketAnalysisWithDraft)
    structured_llm_analysis_only = llm.with_structured_output(TicketAnalysis)

    COMBINED_SYSTEM_PROMPT = """\
You are a senior financial support triage agent AND a professional customer \
support writer. You will analyse an incoming customer email and produce:

A) STRUCTURED TRIAGE ANALYSIS
B) A PERSONALISED DRAFT REPLY

═══ PART A — ANALYSIS RULES ═══

SENTIMENT — Exactly one of: Positive, Negative, Neutral, Urgent
  • Positive — satisfied or sending thanks
  • Negative — frustrated, angry, or dissatisfied
  • Neutral  — informational or routine enquiry
  • Urgent   — immediate danger, fraud, or threats

INTENT — Short phrase (5-10 words) describing what the customer wants.

ENTITIES — Extract (set null if not found):
  • customer_name  — sender's full name
  • transaction_id — any transaction/reference ID (e.g. TXN-12345)
  • amount         — monetary amount (e.g. "$500.00")

PRIORITY (CRITICAL — follow these rules exactly):
  • High   — ANY of these: fraud, theft, unauthorised transactions, account
              compromise, security breach, stolen card, payment failed but money
              deducted, large failed transfers, salary/rent payment failures,
              refund not received/credited, account lockout with urgent need,
              billing error (charged after cancellation), critical transaction
              failures. If money is lost, stuck, or at risk → ALWAYS High.
  • Medium — disputes without money loss, app/feature malfunctions, KYC/document
              issues, non-critical payment questions, chargeback requests where
              money is safe.
  • Low    — general enquiries, information requests, feedback, feature requests,
              status checks, statement requests, thank-you notes.

CATEGORY:
  • Fraud         — fraud, theft, unauthorised access, suspicious activity,
                     security breach, stolen card, identity theft
  • Payment Issue — billing errors, refund requests, payment failures, disputes,
                     failed transfers, subscription charges, account lockout
  • General       — all other enquiries

SUMMARY — Concise 1-2 sentence summary for the support agent.

═══ PART B — DRAFT REPLY RULES ═══

Write a professional, empathetic plain-text email reply (80-150 words).

1. GREETING — "Dear <customer_name>," (or "Dear Valued Customer," if unknown).

2. TONE BY CATEGORY:
   • Fraud:
     – Express urgent concern and empathy
     – Assure account security is top priority
     – State fraud/security team is investigating
     – Advise "We have temporarily secured your account"
     – Provide hotline: 1-800-FRAUD-HELP
   • Payment Issue:
     – Acknowledge inconvenience with empathy
     – Payment/billing team is reviewing
     – Reference number: [REF-XXXXXX]
     – Resolution: 2-3 business days
   • General:
     – Polite, warm, professional
     – Helpful and informative
     – Offer further assistance

3. CLOSING — End with:
   "Best regards,
   Finance Support Team
   finance-support@company.com"

4. Do NOT use markdown. Plain text only.

Return ALL fields in a single JSON response.
"""

    combined_prompt = ChatPromptTemplate.from_messages([
        ("system", COMBINED_SYSTEM_PROMPT),
        ("human", "Analyse and draft a reply for the following customer email:\n\n{email_body}"),
    ])
    combined_chain = combined_prompt | structured_llm

    ANALYSIS_ONLY_SYSTEM_PROMPT = """\
You are a senior financial support triage agent. Analyse the incoming \
customer email and return a structured JSON report.

SENTIMENT — Exactly one of: Positive, Negative, Neutral, Urgent
INTENT — Short phrase (5-10 words) describing what the customer wants.
ENTITIES — Extract customer_name, transaction_id, amount (null if not found).
PRIORITY — High (fraud/theft/money at risk), Medium (billing/disputes/money safe), Low (general).
CATEGORY — Fraud, Payment Issue, or General.
SUMMARY — 1-2 sentence summary.
"""
    analysis_only_prompt = ChatPromptTemplate.from_messages([
        ("system", ANALYSIS_ONLY_SYSTEM_PROMPT),
        ("human", "Analyse the following customer email:\n\n{email_body}"),
    ])
    analysis_only_chain = analysis_only_prompt | structured_llm_analysis_only

    return combined_chain, analysis_only_chain


# ── Analysis cache ──
if "analysis_cache" not in st.session_state:
    st.session_state.analysis_cache = {}


def analyze_and_draft(email_body: str) -> TicketAnalysisWithDraft:
    if not email_body or not email_body.strip():
        raise ValueError("email_body cannot be empty.")
    clean = email_body.strip()
    key = hashlib.sha256(clean.encode()).hexdigest()
    cache = st.session_state.analysis_cache
    if key in cache:
        return cache[key]
    combined_chain, _ = _get_chains()
    if combined_chain is None:
        raise ValueError("GROQ_API_KEY is not set.")
    result: TicketAnalysisWithDraft = combined_chain.invoke({"email_body": clean})
    cache[key] = result
    return result


# ═══════════════════════════════════════════════════════
#  URGENCY CLASSIFIER  (Groq native client)
# ═══════════════════════════════════════════════════════
URGENCY_TAXONOMY = {
    "High": {
        "sla": "Immediate",
        "description": "Financial loss occurring, security breached, or user completely unable to access funds.",
        "subcategories": {
            "Security_Breach": "Account hacked, unauthorized login, OTP received without request, password changed without consent.",
            "Fraud_Report": "Unauthorized purchases, stolen card, unrecognized transactions, identity theft, card cloning.",
            "Transaction_Failure_Critical": "Large transfer failed but money deducted, salary payment didn't go through, refund not received/credited, payment stuck.",
            "Account_Lockout": "Locked out with urgent financial need, frozen account, can't access funds.",
            "Billing_Error": "Charged for cancelled subscription, double-charged, unauthorized recurring charge.",
        },
    },
    "Medium": {
        "sla": "24 hours",
        "description": "User inconvenienced but money is safe.",
        "subcategories": {
            "Dispute_Initiation": "Wants to dispute a charge, double charge, chargeback request.",
            "Feature_Malfunction": "App crashes, can't download statement, UI bug.",
            "KYC_Compliance": "Document rejected, need to update ID, verification pending.",
        },
    },
    "Low": {
        "sla": "48 hours",
        "description": "General questions, feedback, or non-critical tasks.",
        "subcategories": {
            "General_Inquiry": "Interest rates, product features, how-to questions.",
            "Statement_Request": "Tax certificate, account statement, transaction history.",
            "Feedback_Feature_Request": "Feature suggestion, compliment, dark mode request.",
            "Status_Check": "Card delivery status, application status, transfer status.",
        },
    },
}

_SUBCAT_TO_URGENCY = {}
_VALID_SUBCATEGORIES = set()
for _urg, _meta in URGENCY_TAXONOMY.items():
    for _sub in _meta["subcategories"]:
        _SUBCAT_TO_URGENCY[_sub] = _urg
        _VALID_SUBCATEGORIES.add(_sub)

_SUBCAT_TO_PARENT_CATEGORY = {
    "Security_Breach": "Fraud", "Fraud_Report": "Fraud",
    "Transaction_Failure_Critical": "Payment Issue",
    "Account_Lockout": "Payment Issue", "Billing_Error": "Payment Issue",
    "Dispute_Initiation": "Payment Issue",
    "Feature_Malfunction": "General", "KYC_Compliance": "General",
    "General_Inquiry": "General", "Statement_Request": "General",
    "Feedback_Feature_Request": "General", "Status_Check": "General",
}


def get_parent_category(subcategory: str) -> str:
    return _SUBCAT_TO_PARENT_CATEGORY.get(subcategory, "General")


@st.cache_resource
def _get_groq_client():
    if not GROQ_API_KEY:
        return None
    from groq import Groq
    return Groq(api_key=GROQ_API_KEY, timeout=10)


def _build_urgency_system_prompt() -> str:
    lines = [
        "You are an expert financial support urgency classifier. "
        "Given a customer email you MUST return ONLY a valid JSON object.\n",
        "CLASSIFICATION TAXONOMY", "=" * 50,
    ]
    for urgency, meta in URGENCY_TAXONOMY.items():
        lines.append(f"\n{urgency.upper()} URGENCY (SLA: {meta['sla']})")
        lines.append(f"Definition: {meta['description']}")
        lines.append("Sub-categories:")
        for subcat, examples in meta["subcategories"].items():
            lines.append(f"  • {subcat}: {examples}")
    lines.append("\n" + "=" * 50)
    all_subcats = ", ".join(sorted(_VALID_SUBCATEGORIES))
    lines.append(
        "\nRULES:\n"
        "1. Determine urgency (High/Medium/Low) by financial impact.\n"
        "2. Pick the best matching sub-category.\n"
        "3. If multiple, pick the HIGHEST urgency.\n"
        "4. Confidence 0.0-1.0.\n"
        "5. One-sentence reasoning.\n"
        "\nOUTPUT (pure JSON):\n"
        '{"urgency":"<High|Medium|Low>",'
        f'"subcategory":"<one of: {all_subcats}>",'
        '"confidence":<float>,"reasoning":"<sentence>","sla":"<Immediate|24 hours|48 hours>"}'
    )
    return "\n".join(lines)


_URGENCY_SYSTEM_PROMPT = _build_urgency_system_prompt()

# Urgency cache
if "urgency_cache" not in st.session_state:
    st.session_state.urgency_cache = {}

_FALLBACK_URGENCY = {
    "urgency": "Medium", "subcategory": "Feature_Malfunction",
    "confidence": 0.0, "reasoning": "Classification unavailable — defaulted to Medium.",
    "sla": "24 hours",
}


def classify_urgency(email_text: str) -> dict:
    if not email_text or not email_text.strip():
        return {**_FALLBACK_URGENCY, "reasoning": "Empty email body."}
    clean = email_text.strip()
    key = hashlib.sha256(clean.encode()).hexdigest()
    cache = st.session_state.urgency_cache
    if key in cache:
        return cache[key]
    client = _get_groq_client()
    if client is None:
        return {**_FALLBACK_URGENCY, "reasoning": "Groq client not available."}
    try:
        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {"role": "system", "content": _URGENCY_SYSTEM_PROMPT},
                {"role": "user", "content": f"Classify this customer email:\n\n{clean}"},
            ],
            temperature=0.0, max_tokens=512, stream=False,
        )
        raw = response.choices[0].message.content or ""
        text_r = raw.strip()
        if text_r.startswith("```"):
            text_r = text_r.split("\n", 1)[-1]
        if text_r.endswith("```"):
            text_r = text_r.rsplit("```", 1)[0]
        text_r = text_r.strip()
        data = json.loads(text_r)
        urgency = data.get("urgency", "Medium")
        if urgency not in ("High", "Medium", "Low"):
            urgency = "Medium"
        subcategory = data.get("subcategory", "")
        if subcategory not in _VALID_SUBCATEGORIES:
            tier_subcats = list(URGENCY_TAXONOMY[urgency]["subcategories"].keys())
            subcategory = tier_subcats[0] if tier_subcats else "General_Inquiry"
        expected_urgency = _SUBCAT_TO_URGENCY.get(subcategory, urgency)
        if expected_urgency != urgency:
            urgency = expected_urgency
        sla_map = {"High": "Immediate", "Medium": "24 hours", "Low": "48 hours"}
        confidence = max(0.0, min(1.0, float(data.get("confidence", 0.5))))
        result = {
            "urgency": urgency, "subcategory": subcategory,
            "confidence": confidence,
            "reasoning": str(data.get("reasoning", "No reasoning.")),
            "sla": sla_map.get(urgency, "24 hours"),
        }
    except Exception:
        result = {**_FALLBACK_URGENCY}
    cache[key] = result
    return result


# ═══════════════════════════════════════════════════════
#  PRIORITY RESOLUTION  (Agent + Urgency Classifier)
# ═══════════════════════════════════════════════════════
_PRIORITY_MAP = {"High": TicketPriority.HIGH, "Medium": TicketPriority.MEDIUM, "Low": TicketPriority.LOW}
_CATEGORY_MAP = {"Fraud": TicketCategory.FRAUD, "Payment Issue": TicketCategory.PAYMENT_ISSUE, "General": TicketCategory.GENERAL}


def _resolve_priority(email_text, agent_priority, agent_category):
    try:
        clf = classify_urgency(email_text)
    except Exception:
        return agent_priority, agent_category, None
    clf_urgency = clf["urgency"]
    clf_confidence = clf["confidence"]
    _rank = {"High": 3, "Medium": 2, "Low": 1}
    agent_rank = _rank.get(agent_priority, 2)
    clf_rank = _rank.get(clf_urgency, 2)
    if clf_confidence >= 0.75:
        final_priority = clf_urgency
    elif clf_rank > agent_rank:
        final_priority = clf_urgency
    else:
        final_priority = agent_priority
    final_category = agent_category
    parent_cat = get_parent_category(clf["subcategory"])
    if final_priority == "High" and parent_cat == "Fraud" and agent_category != "Fraud":
        final_category = "Fraud"
    elif final_priority == "High" and parent_cat == "Payment Issue" and agent_category == "General":
        final_category = "Payment Issue"
    return final_priority, final_category, {
        "subcategory": clf["subcategory"], "sla": clf["sla"],
        "confidence": clf_confidence, "reasoning": clf["reasoning"],
    }


# ═══════════════════════════════════════════════════════
#  EMAIL SEND / RECEIVE
# ═══════════════════════════════════════════════════════
logger = logging.getLogger("finance_triage")


def _extract_recipient_email(email_body: str) -> Optional[str]:
    if not email_body:
        return None
    for line in email_body.split("\n"):
        stripped = line.strip()
        if stripped.lower().startswith("from:"):
            value = stripped.split(":", 1)[1].strip()
            match = re.search(r'[\w.+-]+@[\w-]+\.[\w.-]+', value)
            return match.group(0) if match else None
    return None


def _extract_subject_email(email_body: str) -> str:
    if not email_body:
        return "Finance Support Response"
    for line in email_body.split("\n"):
        stripped = line.strip()
        if stripped.lower().startswith("subject:"):
            return "Re: " + stripped.split(":", 1)[1].strip()
    return "Finance Support Response"


def send_reply_email(to_email: str, subject: str, body: str) -> bool:
    if not EMAIL_USER or not EMAIL_PASSWORD:
        logger.error("EMAIL_USER / EMAIL_PASSWORD not set.")
        return False
    try:
        msg = MIMEMultipart("alternative")
        msg["From"] = EMAIL_USER
        msg["To"] = to_email
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain"))
        html = (
            '<div style="font-family:Arial,sans-serif;font-size:14px;line-height:1.7;color:#333;">'
            + body.replace("\n", "<br>")
            + '<br><br><hr style="border:none;border-top:1px solid #ddd;">'
            '<small style="color:#888;">This is an automated response from Finance Support Triage Agent.</small></div>'
        )
        msg.attach(MIMEText(html, "html"))
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(EMAIL_USER, EMAIL_PASSWORD)
            server.sendmail(EMAIL_USER, to_email, msg.as_string())
        return True
    except Exception as e:
        logger.error(f"Failed to send email: {e}")
        return False


def fetch_emails_from_gmail(include_read: bool = False, max_emails: int = 5) -> dict:
    """Connect to Gmail via IMAP, pull emails, analyse + save to PostgreSQL."""
    import imaplib
    import email as email_lib
    from email.header import decode_header as _decode_header

    if not EMAIL_USER or not EMAIL_PASSWORD:
        return {"fetched": 0, "errors": 1, "error_details": ["EMAIL credentials not set."],
                "tickets": [], "message": "Credentials missing."}

    db = _get_db()
    if db is None:
        return {"fetched": 0, "errors": 1, "error_details": ["DATABASE_URL not set."],
                "tickets": [], "message": "Database not configured."}

    _start = _time.time()

    def _decode_hdr(value):
        if not value:
            return ""
        parts = []
        for part, charset in _decode_header(value):
            if isinstance(part, bytes):
                parts.append(part.decode(charset or "utf-8", errors="replace"))
            else:
                parts.append(part)
        return " ".join(parts)

    def _extract_body(msg):
        body = ""
        if msg.is_multipart():
            for part in msg.walk():
                ct = part.get_content_type()
                cd = str(part.get("Content-Disposition", ""))
                if "attachment" in cd:
                    continue
                if ct == "text/plain":
                    payload = part.get_payload(decode=True)
                    if payload:
                        body = payload.decode(part.get_content_charset() or "utf-8", errors="replace")
                        break
                elif ct == "text/html" and not body:
                    payload = part.get_payload(decode=True)
                    if payload:
                        html = payload.decode(part.get_content_charset() or "utf-8", errors="replace")
                        body = re.sub(r"<[^>]+>", " ", html)
                        body = re.sub(r"\s+", " ", body).strip()
        else:
            payload = msg.get_payload(decode=True)
            if payload:
                body = payload.decode(msg.get_content_charset() or "utf-8", errors="replace")
        return body.strip()

    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com", 993)
        mail.login(EMAIL_USER, EMAIL_PASSWORD)
        mail.select("INBOX")
    except Exception as e:
        db.close()
        return {"fetched": 0, "errors": 1, "error_details": [f"IMAP connection failed: {e}"],
                "tickets": [], "message": str(e)}

    try:
        if include_read:
            search_criteria = "ALL"
        else:
            since_date = (datetime.now() - timedelta(days=2)).strftime("%d-%b-%Y")
            search_criteria = f'(SINCE "{since_date}")'
        status, messages = mail.search(None, search_criteria)
        if status != "OK":
            db.close()
            return {"fetched": 0, "errors": 1, "error_details": ["Could not search mailbox."],
                    "tickets": [], "message": "Search failed."}

        email_ids = messages[0].split()
        email_ids = email_ids[-max_emails:] if len(email_ids) > max_emails else email_ids

        results = []
        errors = []
        skipped_dupes = 0

        for eid in email_ids:
            try:
                st_fetch, msg_data = mail.fetch(eid, "(RFC822)")
                if st_fetch != "OK":
                    continue
                raw = msg_data[0][1]
                msg = email_lib.message_from_bytes(raw)
                subject = _decode_hdr(msg.get("Subject", "(No Subject)"))
                sender = _decode_hdr(msg.get("From", "(Unknown)"))
                body = _extract_body(msg)
                if not body or len(body.strip()) < 10:
                    mail.store(eid, "+FLAGS", "\\Seen")
                    continue
                full_text = f"From: {sender}\nSubject: {subject}\n\n{body}"

                # Skip duplicates
                existing = db.query(Ticket).filter(Ticket.email_body == full_text).first()
                if existing:
                    skipped_dupes += 1
                    mail.store(eid, "+FLAGS", "\\Seen")
                    continue

                # Analyse + Draft
                try:
                    combined = analyze_and_draft(full_text)
                    analysis = combined
                    draft = combined.draft_response
                except Exception as ai_err:
                    err_str = str(ai_err)
                    if "429" in err_str or "rate_limit" in err_str.lower() or "quota" in err_str.lower():
                        mail.close()
                        mail.logout()
                        db.close()
                        return {
                            "fetched": len(results), "errors": len(errors) + 1,
                            "skipped_duplicates": skipped_dupes, "tickets": results,
                            "error_details": ["Groq API rate limit reached. Wait 1-2 min."],
                            "message": f"Processed {len(results)} before rate limit.",
                            "quota_error": True,
                        }
                    raise

                # Priority override via urgency classifier
                final_pri, final_cat, clf_meta = _resolve_priority(
                    full_text, analysis.priority.value, analysis.category.value,
                )

                # Save ticket
                ticket = Ticket(
                    customer_name=analysis.entities.customer_name or sender.split("<")[0].strip() or "Unknown",
                    email_body=full_text, status="New",
                    priority=_PRIORITY_MAP.get(final_pri, TicketPriority.MEDIUM),
                    category=_CATEGORY_MAP.get(final_cat, TicketCategory.GENERAL),
                    sentiment=analysis.sentiment.value, intent=analysis.intent,
                    summary=analysis.summary,
                    transaction_id=analysis.entities.transaction_id,
                    amount=analysis.entities.amount, draft_response=draft,
                )
                db.add(ticket)
                db.commit()
                db.refresh(ticket)
                mail.store(eid, "+FLAGS", "\\Seen")

                results.append({
                    "ticket_id": str(ticket.id), "subject": subject,
                    "sender": sender, "priority": final_pri, "category": final_cat,
                })
            except Exception as e:
                errors.append(str(e))
                continue

        mail.close()
        mail.logout()
        db.close()
        elapsed = round(_time.time() - _start, 1)
        msg = f"Fetched and processed {len(results)} email(s) in {elapsed}s."
        if skipped_dupes:
            msg += f" Skipped {skipped_dupes} duplicate(s)."
        return {"fetched": len(results), "errors": len(errors),
                "skipped_duplicates": skipped_dupes, "tickets": results,
                "error_details": errors[:10], "message": msg}
    except Exception as e:
        db.close()
        return {"fetched": 0, "errors": 1, "error_details": [str(e)],
                "tickets": [], "message": str(e)}


# ═══════════════════════════════════════════════════════
#  DASHBOARD METRICS (computed directly from DB)
# ═══════════════════════════════════════════════════════
def _parse_amount(amount_str):
    if not amount_str:
        return 0.0
    cleaned = re.sub(r'[^\d.]', '', str(amount_str))
    try:
        return float(cleaned)
    except (ValueError, TypeError):
        return 0.0


def _extract_merchants(email_body):
    known = [
        "PayPal", "Uber", "Amazon", "Netflix", "Stripe", "Venmo", "Zelle",
        "Cash App", "Apple Pay", "Google Pay", "Square", "Shopify", "Razorpay",
        "Coinbase", "Robinhood", "Wise", "Western Union", "MoneyGram",
        "Chase", "Wells Fargo", "Bank of America", "Citi", "HDFC", "ICICI",
        "SBI", "PhonePe", "Paytm", "GPay", "Flipkart", "Swiggy", "Zomato",
    ]
    found = []
    if not email_body:
        return found
    body_lower = email_body.lower()
    for m in known:
        if m.lower() in body_lower:
            found.append(m)
    return found


def calculate_dashboard_metrics(db) -> dict:
    now = datetime.now(timezone.utc)
    all_tickets = db.query(Ticket).order_by(Ticket.created_at.desc()).all()

    _OPEN = {TicketStatus.OPEN, TicketStatus.NEW, TicketStatus.IN_PROGRESS}
    _CLOSED = {TicketStatus.RESOLVED, TicketStatus.CLOSED}
    open_tickets = [t for t in all_tickets if t.status in _OPEN]
    closed_tickets = [t for t in all_tickets if t.status in _CLOSED]
    fraud_tickets = [t for t in all_tickets if t.category == TicketCategory.FRAUD]
    fraud_open = [t for t in fraud_tickets if t.status in _OPEN]

    total_disputed = sum(_parse_amount(t.amount) for t in open_tickets)
    sla_threshold = now - timedelta(hours=4)
    sla_breaches = [
        t for t in open_tickets
        if t.priority == TicketPriority.HIGH and t.created_at and t.created_at < sla_threshold
    ]
    fraud_exposure = sum(_parse_amount(t.amount) for t in fraud_tickets)
    fraud_open_value = sum(_parse_amount(t.amount) for t in fraud_open)

    ai_used = sum(1 for t in closed_tickets if not t.is_ai_draft_edited)
    ai_success_rate = (ai_used / len(closed_tickets) * 100) if closed_tickets else 0.0

    resolution_hours = []
    for t in closed_tickets:
        if t.created_at:
            delta = (now - t.created_at).total_seconds() / 3600
            resolution_hours.append(delta)
    avg_resolution_h = sum(resolution_hours) / len(resolution_hours) if resolution_hours else 0

    cutoff_48h = now - timedelta(hours=48)
    hourly_counts = {}
    for t in all_tickets:
        if t.created_at and t.created_at >= cutoff_48h:
            hour_key = t.created_at.strftime("%Y-%m-%d %H:00")
            hourly_counts[hour_key] = hourly_counts.get(hour_key, 0) + 1
    volume_by_hour = []
    cur = cutoff_48h.replace(minute=0, second=0, microsecond=0)
    while cur <= now:
        key = cur.strftime("%Y-%m-%d %H:00")
        volume_by_hour.append({"hour": key, "count": hourly_counts.get(key, 0)})
        cur += timedelta(hours=1)

    merchant_counter = Counter()
    for t in all_tickets:
        for m in _extract_merchants(t.email_body):
            merchant_counter[m] += 1
    top_merchants = [{"name": n, "count": c} for n, c in merchant_counter.most_common(5)]

    category_perf = []
    for cat in [TicketCategory.FRAUD, TicketCategory.PAYMENT_ISSUE, TicketCategory.GENERAL]:
        cat_all = [t for t in all_tickets if t.category == cat]
        cat_closed = [t for t in cat_all if t.status in _CLOSED]
        cat_avg_h = 0.0
        if cat_closed:
            deltas = [(now - t.created_at).total_seconds() / 3600 for t in cat_closed if t.created_at]
            cat_avg_h = sum(deltas) / len(deltas) if deltas else 0
        reopen = sum(1 for t in cat_all if t.status == TicketStatus.OPEN)
        category_perf.append({
            "category": cat.value, "total": len(cat_all), "closed": len(cat_closed),
            "avg_resolution_h": round(cat_avg_h, 1), "reopen_count": reopen,
            "reopen_rate": round(reopen / len(cat_all) * 100, 1) if cat_all else 0,
        })

    sla_detail = []
    for t in sla_breaches:
        hrs_open = (now - t.created_at).total_seconds() / 3600 if t.created_at else 0
        sla_detail.append({
            "id": str(t.id), "customer_name": t.customer_name,
            "amount": t.amount, "hours_open": round(hrs_open, 1),
            "category": t.category.value if t.category else "General",
        })

    return {
        "total_tickets": len(all_tickets), "open_tickets": len(open_tickets),
        "closed_tickets": len(closed_tickets),
        "total_disputed_volume": round(total_disputed, 2),
        "sla_breaches": len(sla_breaches), "sla_breach_detail": sla_detail,
        "fraud_alerts_open": len(fraud_open),
        "fraud_exposure_total": round(fraud_exposure, 2),
        "fraud_exposure_open": round(fraud_open_value, 2),
        "ai_success_rate": round(ai_success_rate, 1), "ai_drafts_used": ai_used,
        "avg_resolution_h": round(avg_resolution_h, 1),
        "volume_by_hour": volume_by_hour, "top_merchants": top_merchants,
        "category_performance": category_perf,
    }


# ═══════════════════════════════════════════════════════
#  DIRECT DB LAYER  (replaces all HTTP API calls)
# ═══════════════════════════════════════════════════════
def _ticket_to_dict(ticket: Ticket) -> dict:
    return {
        "id": str(ticket.id), "customer_name": ticket.customer_name,
        "email_body": ticket.email_body,
        "status": ticket.status.value if ticket.status else "New",
        "priority": ticket.priority.value if ticket.priority else "Medium",
        "category": ticket.category.value if ticket.category else "General",
        "sentiment": ticket.sentiment, "intent": ticket.intent,
        "summary": ticket.summary, "transaction_id": ticket.transaction_id,
        "amount": ticket.amount, "draft_response": ticket.draft_response,
        "is_read": ticket.is_read if ticket.is_read is not None else False,
        "is_ai_draft_edited": ticket.is_ai_draft_edited if ticket.is_ai_draft_edited is not None else False,
        "created_at": ticket.created_at.isoformat() if ticket.created_at else None,
    }


@st.cache_data(ttl=30, show_spinner=False)
def _fetch_tickets(status: str = "All"):
    db = _get_db()
    if db is None:
        return []
    try:
        query = db.query(Ticket).order_by(Ticket.created_at.desc())
        if status and status != "All":
            low = status.strip().lower()
            if low == "open":
                query = query.filter(Ticket.status.in_([
                    TicketStatus.OPEN, TicketStatus.NEW, TicketStatus.IN_PROGRESS,
                ]))
            else:
                try:
                    status_enum = TicketStatus(status)
                    query = query.filter(Ticket.status == status_enum)
                except ValueError:
                    pass
        tickets = query.all()
        return [_ticket_to_dict(t) for t in tickets]
    except Exception as e:
        logger.error(f"DB Error fetching tickets: {e}")
        return []
    finally:
        db.close()


def _api_approve(tid: str):
    db = _get_db()
    if db is None:
        return None
    try:
        ticket = db.query(Ticket).filter(Ticket.id == tid).first()
        if not ticket:
            st.error("Ticket not found.")
            return None
        email_sent = False
        recipient = _extract_recipient_email(ticket.email_body)
        if recipient and ticket.draft_response:
            subject = _extract_subject_email(ticket.email_body)
            email_sent = send_reply_email(recipient, subject, ticket.draft_response)
        ticket.status = TicketStatus.RESOLVED
        db.commit()
        db.refresh(ticket)
        _fetch_tickets.clear()
        _api_dashboard_metrics.clear()
        msg = (f"Ticket approved, response sent to {recipient}, and resolved."
               if email_sent else "Ticket approved and resolved, but email could not be sent.")
        return {"message": msg, "email_sent": email_sent, "recipient": recipient,
                "ticket": _ticket_to_dict(ticket)}
    except Exception as e:
        db.rollback()
        st.error(f"Approve failed: {e}")
        return None
    finally:
        db.close()


def _api_close(tid: str):
    db = _get_db()
    if db is None:
        return False
    try:
        ticket = db.query(Ticket).filter(Ticket.id == tid).first()
        if not ticket:
            return False
        ticket.status = TicketStatus.CLOSED
        db.commit()
        _fetch_tickets.clear()
        _api_dashboard_metrics.clear()
        return True
    except Exception as e:
        db.rollback()
        st.error(f"Close failed: {e}")
        return False
    finally:
        db.close()


def _api_mark_read(tid: str):
    db = _get_db()
    if db is None:
        return False
    try:
        ticket = db.query(Ticket).filter(Ticket.id == tid).first()
        if not ticket:
            return False
        if not ticket.is_read:
            ticket.is_read = True
            db.commit()
        return True
    except Exception:
        return False
    finally:
        db.close()


def _api_fetch_emails(include_read: bool = False, max_emails: int = 5):
    try:
        result = fetch_emails_from_gmail(include_read=include_read, max_emails=max_emails)
        if result and result.get("fetched", 0) > 0:
            _fetch_tickets.clear()
            _api_dashboard_metrics.clear()
        return result
    except Exception as e:
        st.error(f"Email fetch failed: {e}")
        return None


@st.cache_data(ttl=60, show_spinner=False)
def _api_dashboard_metrics():
    db = _get_db()
    if db is None:
        return None
    try:
        return calculate_dashboard_metrics(db)
    except Exception:
        return None
    finally:
        db.close()


# ═══════════════════════════════════════════════════════
#  STREAMLIT PAGE CONFIG
# ═══════════════════════════════════════════════════════
st.set_page_config(
    page_title="Finance Triage",
    page_icon="FT",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ═══════════════════════════════════════════════════════
#  SESSION STATE
# ═══════════════════════════════════════════════════════
for k, v in {
    "sel": None,
    "tickets": [],
    "all_tickets": [],
    "fetch_res": None,
    "tab": "dashboard",
    "page": "main",
    "read_ids": set(),
    "search_query": "",
    "last_auto_fetch": 0,
}.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ═══════════════════════════════════════════════════════
#  LOAD EXTERNAL CSS / JS  (cached — read once, never re-read)
# ═══════════════════════════════════════════════════════
@st.cache_resource
def _load_css():
    _p = _FRONTEND_DIR / "static" / "styles.css"
    return _p.read_text(encoding="utf-8") if _p.exists() else ""


@st.cache_resource
def _load_js():
    _p = _FRONTEND_DIR / "static" / "script.js"
    return _p.read_text(encoding="utf-8") if _p.exists() else ""


_css_content = _load_css()
if _css_content:
    st.markdown(f"<style>{_css_content}</style>", unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════
#  AUTO-REFRESH: every 5 min (300,000 ms) to keep alive
# ═══════════════════════════════════════════════════════
st_autorefresh(interval=300_000, limit=None, key="auto_refresh_5min")

# ── Auto-fetch emails on each refresh cycle ──
_now = _time.time()
_FETCH_INTERVAL = 300  # 5 minutes
if (_now - st.session_state.last_auto_fetch) >= _FETCH_INTERVAL:
    if EMAIL_USER and EMAIL_PASSWORD and DATABASE_URL:
        try:
            _auto_result = fetch_emails_from_gmail(include_read=False, max_emails=5)
            _auto_fetched = _auto_result.get("fetched", 0) if _auto_result else 0
            if _auto_fetched > 0:
                st.toast(f"Auto-fetched {_auto_fetched} new email(s)", icon="📬")
                _fetch_tickets.clear()
                _api_dashboard_metrics.clear()
        except Exception:
            pass  # silently fail on auto-fetch
    st.session_state.last_auto_fetch = _now

# ═══════════════════════════════════════════════════════
#  HELPERS
# ═══════════════════════════════════════════════════════
_PRI_ORDER = {"High": 0, "Medium": 1, "Low": 2}


def _fmt_time(ts: str) -> str:
    if not ts:
        return ""
    try:
        dt = datetime.fromisoformat(ts)
        now = datetime.now(dt.tzinfo) if dt.tzinfo else datetime.now()
        diff = now - dt
        if dt.date() == now.date():
            mins = int(diff.total_seconds() / 60)
            if mins < 1:
                return "Just now"
            if mins < 60:
                return f"{mins}m ago"
            return dt.strftime("%I:%M %p")
        if dt.date() == (now - timedelta(days=1)).date():
            return "Yesterday"
        if diff.days < 7:
            return f"{diff.days}d ago"
        return dt.strftime("%b %d")
    except Exception:
        return str(ts)[:10]


def _fmt_full(ts: str) -> str:
    if not ts:
        return "N/A"
    try:
        return datetime.fromisoformat(ts).strftime("%H:%M, %A, %b %d")
    except Exception:
        return ts


def _date_group(ts: str) -> str:
    if not ts:
        return "Unknown"
    try:
        dt = datetime.fromisoformat(ts)
        now = datetime.now(dt.tzinfo) if dt.tzinfo else datetime.now()
        if dt.date() == now.date():
            return "Today"
        if dt.date() == (now - timedelta(days=1)).date():
            return "Yesterday"
        if (now - dt).days < 7:
            return "This Week"
        return "Earlier"
    except Exception:
        return "Earlier"


def _extract_subject(body: str) -> str:
    if not body:
        return "No Subject"
    for line in body.split("\n"):
        if line.strip().lower().startswith("subject:"):
            return line.split(":", 1)[1].strip()[:80]
    return body.strip()[:55] + ("…" if len(body.strip()) > 55 else "")


def _extract_sender(body: str, customer_name: str) -> str:
    if customer_name and customer_name != "Unknown":
        return customer_name
    if body:
        for line in body.split("\n"):
            if line.strip().lower().startswith("from:"):
                s = line.split(":", 1)[1].strip()
                name = re.sub(r"<[^>]+>", "", s).strip()
                return name[:30] if name else s[:30]
    return "Unknown Sender"


def _extract_email_addr(body: str) -> str:
    if not body:
        return ""
    for line in body.split("\n"):
        if line.strip().lower().startswith("from:"):
            match = re.search(r'[\w.+-]+@[\w-]+\.[\w.-]+', line)
            if match:
                return match.group(0)
    return ""


def _get_preview(body: str) -> str:
    if not body:
        return ""
    parts = []
    for l in body.strip().split("\n"):
        if l.strip().lower().startswith(("from:", "to:", "subject:", "date:")):
            continue
        if l.strip():
            parts.append(l.strip())
    return " ".join(parts)[:100]


def _get_body(body: str) -> str:
    if not body:
        return ""
    lines = []
    for l in body.strip().split("\n"):
        if l.strip().lower().startswith(("from:", "to:", "subject:", "date:")):
            continue
        lines.append(l)
    return "\n".join(lines).strip()


def _is_ticket_read(tkt: dict) -> bool:
    return tkt.get("is_read", False) or tkt.get("id") in st.session_state.read_ids


def _search_match(tkt: dict, query: str) -> bool:
    if not query:
        return True
    q = query.lower()
    searchable = " ".join([
        tkt.get("email_body") or "", tkt.get("customer_name") or "",
        tkt.get("summary") or "", tkt.get("intent") or "",
        tkt.get("category") or "", tkt.get("priority") or "",
        tkt.get("sentiment") or "", tkt.get("transaction_id") or "",
        tkt.get("amount") or "",
        _extract_subject(tkt.get("email_body") or ""),
        _extract_email_addr(tkt.get("email_body") or ""),
    ]).lower()
    return all(word in searchable for word in q.split())


# ═══════════════════════════════════════════════════════
#  SIDEBAR
# ═══════════════════════════════════════════════════════
with st.sidebar:
    st.markdown(sidebar_header(), unsafe_allow_html=True)

    if st.button("Fetch New Emails", key="sb_fetch", use_container_width=True, type="primary"):
        st.session_state.page = "fetch"
        st.session_state.sel = None
        st.rerun()

    st.markdown("---")
    st.markdown("### Navigation")

    # Load all tickets once for the sidebar
    all_tickets = _fetch_tickets("All")
    st.session_state.all_tickets = all_tickets

    # Sync read_ids from backend data
    for _t in all_tickets:
        if _t.get("is_read"):
            st.session_state.read_ids.add(_t.get("id"))

    _UNRESOLVED = {"Open", "New", "In Progress"}
    new_ct = sum(1 for t in all_tickets if t.get("status") in _UNRESOLVED and not _is_ticket_read(t))
    high_ct = sum(1 for t in all_tickets if t.get("priority") == "High" and t.get("status") in _UNRESOLVED)
    fraud_ct = sum(1 for t in all_tickets if t.get("category") == "Fraud")
    resolved_ct = sum(1 for t in all_tickets if t.get("status") in ("Resolved", "Closed"))

    nav_items = [
        ("dashboard", "bar-chart-2", "Analytics",       None),
        ("inbox",     "inbox",       "Inbox",           new_ct if new_ct else None),
        ("queue",     "zap",         "Priority Queue",  high_ct if high_ct else None),
        ("category",  "tag",         "By Category",     None),
        ("alerts",    "bell",        "Alerts",          fraud_ct if fraud_ct else None),
    ]

    for key, icon_name, label, count in nav_items:
        suffix = f" ({count})" if count else ""
        is_active = st.session_state.tab == key and st.session_state.page == "main"
        btn_type = "primary" if is_active else "secondary"
        ic, bc = st.columns([1, 7])
        with ic:
            st.markdown(nav_icon_cell(icon_name, is_active), unsafe_allow_html=True)
        with bc:
            if st.button(f"{label}{suffix}", key=f"nav_{key}", use_container_width=True, type=btn_type):
                st.session_state.tab = key
                st.session_state.page = "main"
                st.session_state.sel = None
                st.rerun()

    st.markdown("---")
    st.markdown("### Filters")
    status_filter = st.selectbox(
        "Status", ["All", "New", "In Progress", "Resolved", "Closed"],
        label_visibility="collapsed",
    )
    priority_filter = st.radio(
        "Priority", ["All", "High", "Medium", "Low"],
        horizontal=True, label_visibility="collapsed",
    )

    filtered = all_tickets
    if status_filter != "All":
        filtered = [t for t in filtered if t.get("status") == status_filter]
    if priority_filter != "All":
        filtered = [t for t in filtered if t.get("priority") == priority_filter]
    st.session_state.tickets = filtered

    st.markdown("---")
    st.markdown("### Quick Stats")
    m1, m2 = st.columns(2)
    m1.metric("Total", len(all_tickets))
    m2.metric("Unread", new_ct)
    m3, m4 = st.columns(2)
    m3.metric("Fraud", fraud_ct)
    m4.metric("Resolved", resolved_ct)

    if st.button("Refresh", use_container_width=True):
        st.session_state.sel = None
        st.rerun()

    st.markdown("---")
    st.caption("v4.0 • Finance Triage • Single-Service Deploy")


# ═══════════════════════════════════════════════════════
#  PAGE: FETCH EMAILS
# ═══════════════════════════════════════════════════════
if st.session_state.page == "fetch":
    st.markdown(top_bar("Fetch Emails"), unsafe_allow_html=True)
    st.markdown(fetch_how_it_works(), unsafe_allow_html=True)

    c1, c2, _ = st.columns([1, 1, 1])
    with c1:
        include_read = st.checkbox("Include already-read emails", value=False)
    with c2:
        max_emails = st.slider("Max emails", 1, 50, 5, 1)

    bc, _ = st.columns([1, 2])
    with bc:
        if st.button("Fetch Emails Now", type="primary", use_container_width=True):
            with st.spinner("Connecting to Gmail and processing emails…"):
                result = _api_fetch_emails(include_read=include_read, max_emails=max_emails)
            st.session_state.fetch_res = result

    result = st.session_state.fetch_res
    if result:
        fetched = result.get("fetched", 0)
        errs = result.get("errors", 0)
        skipped = result.get("skipped_duplicates", 0)
        quota_error = result.get("quota_error", False)

        if quota_error:
            st.markdown(
                alert_bar("ab-red", "x-circle", "#dc2626",
                          f"<b>Rate Limit Hit</b> — Processed {fetched} email(s). Wait 1-2 min and retry."),
                unsafe_allow_html=True,
            )
        if fetched > 0:
            parts = [f"{fetched} processed"]
            if skipped:
                parts.append(f"{skipped} duplicates skipped")
            if errs:
                parts.append(f"{errs} errors")
            st.markdown(
                alert_bar("ab-green", "check-circle", "#16a34a",
                          f'<b>{result.get("message","Done!")}</b> — {"  •  ".join(parts)}'),
                unsafe_allow_html=True,
            )
            for i, t in enumerate(result.get("tickets", [])):
                tc1, tc2, tc3, tc4 = st.columns([3, 1, 1, 1])
                with tc1:
                    st.markdown(f"**{t.get('subject','N/A')}**")
                    st.caption(t.get("sender", ""))
                with tc2:
                    st.markdown(pri_badge(t.get("priority", "Medium")), unsafe_allow_html=True)
                with tc3:
                    st.markdown(cat_badge(t.get("category", "General")), unsafe_allow_html=True)
                with tc4:
                    st.code(t.get("ticket_id", "")[:8])
                if i < len(result.get("tickets", [])) - 1:
                    st.divider()
        else:
            st.markdown(
                alert_bar("ab-amber", "mail-open", "#d97706",
                          '<b>No new emails.</b> Try enabling "Include already-read emails".'),
                unsafe_allow_html=True,
            )
        if errs > 0:
            with st.expander(f"{errs} error(s)"):
                for e in result.get("error_details", []):
                    st.code(e)
    st.stop()


# ═══════════════════════════════════════════════════════
#  COMMON: tickets + top bar
# ═══════════════════════════════════════════════════════
tickets = st.session_state.tickets
all_tickets = st.session_state.all_tickets


# ──────────────────────────────────────────────────────
#  DETAIL VIEW HELPER
# ──────────────────────────────────────────────────────
def _render_detail(ticket: dict, key_prefix: str = "d"):
    _p   = ticket.get("priority", "Medium")
    _c   = ticket.get("category", "General")
    _st  = ticket.get("status", "New")
    _sdr = _extract_sender(ticket.get("email_body", ""), ticket.get("customer_name", ""))
    _sub = _extract_subject(ticket.get("email_body", ""))
    _tm  = _fmt_full(ticket.get("created_at"))
    _bd  = _get_body(ticket.get("email_body", ""))
    tid  = ticket.get("id", "")
    kp   = key_prefix

    st.markdown('<div class="detail-card">', unsafe_allow_html=True)
    st.markdown(detail_actions(), unsafe_allow_html=True)
    st.markdown(detail_header(_sub, _sdr, _tm, _p, _c, _st), unsafe_allow_html=True)
    st.markdown(f'<div class="detail-body">{_bd}</div></div>', unsafe_allow_html=True)

    st.markdown(section_header("brain", "AI Analysis"), unsafe_allow_html=True)
    st.markdown(
        insight_grid(_c, ticket.get("sentiment", "Neutral"),
                     ticket.get("intent", "N/A"), ticket.get("amount") or "N/A"),
        unsafe_allow_html=True,
    )
    e1, e2, e3 = st.columns(3)
    e1.metric("Customer", ticket.get("customer_name") or "N/A")
    e2.metric("Transaction ID", ticket.get("transaction_id") or "N/A")
    e3.metric("Amount", ticket.get("amount") or "N/A")
    st.markdown(f"**{icon('file-text', '#4f46e5', 15)} Summary:** {ticket.get('summary', 'N/A')}", unsafe_allow_html=True)

    st.markdown(section_header("edit-3", "Draft Response"), unsafe_allow_html=True)
    draft = st.text_area(
        "draft", value=ticket.get("draft_response", ""),
        height=170, key=f"draft_{kp}_{tid}", label_visibility="collapsed",
    )
    if _st in ("New", "Open", "In Progress"):
        b1, b2, b3 = st.columns([1, 1, 1])
        with b1:
            if st.button("Approve & Send", key=f"ap_{kp}_{tid}", type="primary", use_container_width=True):
                with st.spinner("Sending email…"):
                    res = _api_approve(tid)
                if res:
                    if res.get("email_sent"):
                        st.success(f"Sent to {res.get('recipient', 'customer')} & resolved!")
                    else:
                        st.warning("Resolved but email could not be sent.")
                    _time.sleep(1.5)
                    st.session_state.sel = None
                    st.rerun()
        with b2:
            if st.button("Close Ticket", key=f"cl_{kp}_{tid}", use_container_width=True):
                with st.spinner("Closing…"):
                    if _api_close(tid):
                        st.warning("Ticket closed without reply.")
                        st.session_state.sel = None
                        st.rerun()
        with b3:
            if st.button("← Back to list", key=f"bk_{kp}_{tid}", use_container_width=True):
                st.session_state.sel = None
                st.rerun()
    else:
        c1, c2 = st.columns(2)
        with c1:
            st.info(f"This ticket is **{_st}**.")
        with c2:
            if st.button("← Back to list", key=f"bk2_{kp}_{tid}", use_container_width=True):
                st.session_state.sel = None
                st.rerun()


# ══════════════════════════════════════════════════════════
#  PAGE: ENTERPRISE ANALYTICS DASHBOARD
# ══════════════════════════════════════════════════════════
if st.session_state.tab == "dashboard":
    st.markdown(top_bar("Finance Triage — Enterprise Analytics"), unsafe_allow_html=True)

    metrics = _api_dashboard_metrics()

    if not metrics:
        total = len(all_tickets)
        _UNR = {"Open", "New", "In Progress"}
        unresolved = [t for t in all_tickets if t.get("status") in _UNR]
        resolved = [t for t in all_tickets if t.get("status") in ("Resolved", "Closed")]
        st.warning("Could not fetch metrics from database — showing basic stats.")
        metrics = {
            "total_tickets": total, "open_tickets": len(unresolved),
            "closed_tickets": len(resolved),
            "total_disputed_volume": sum(_parse_amount(t.get("amount")) for t in unresolved),
            "sla_breaches": 0, "sla_breach_detail": [],
            "fraud_alerts_open": sum(1 for t in unresolved if t.get("category") == "Fraud"),
            "fraud_exposure_total": sum(_parse_amount(t.get("amount")) for t in all_tickets if t.get("category") == "Fraud"),
            "fraud_exposure_open": sum(_parse_amount(t.get("amount")) for t in unresolved if t.get("category") == "Fraud"),
            "ai_success_rate": 0, "ai_drafts_used": 0, "avg_resolution_h": 0,
            "volume_by_hour": [], "top_merchants": [], "category_performance": [],
        }

    def _fmt_currency(val):
        if val >= 1_000_000: return f"${val/1_000_000:,.1f}M"
        if val >= 1_000: return f"${val:,.0f}"
        return f"${val:,.2f}"

    def _fmt_hours(h):
        if h < 1: return f"{h*60:.0f}m"
        if h < 24: return f"{h:.1f}h"
        return f"{h/24:.1f}d"

    # ROW 1: KEY FINANCIAL RISKS
    st.markdown(chart_title_html("alert-triangle", "#ef4444", "KEY FINANCIAL RISKS"), unsafe_allow_html=True)
    p1, p2, p3, p4 = st.columns(4)

    disputed_vol = metrics.get("total_disputed_volume", 0)
    with p1:
        st.markdown(
            analytics_card("ac-red", "dollar-sign", "#ef4444",
                           "Total Disputed Value", _fmt_currency(disputed_vol),
                           f'{metrics.get("open_tickets",0)} open tickets'),
            unsafe_allow_html=True,
        )

    fraud_open_ct = metrics.get("fraud_alerts_open", 0)
    fraud_open_val = metrics.get("fraud_exposure_open", 0)
    with p2:
        fraud_color_cls = "ac-red" if fraud_open_ct > 0 else "ac-green"
        st.markdown(
            analytics_card(fraud_color_cls, "shield-alert", "#ef4444",
                           "Active Fraud Alerts",
                           f'{fraud_open_ct} Alert{"s" if fraud_open_ct != 1 else ""}',
                           f"{_fmt_currency(fraud_open_val)} exposure"),
            unsafe_allow_html=True,
        )

    sla_ct = metrics.get("sla_breaches", 0)
    with p3:
        sla_cls = "ac-red" if sla_ct > 0 else "ac-green"
        sla_text_style = "color:#dc2626;font-weight:800;" if sla_ct > 0 else ""
        st.markdown(
            analytics_card(sla_cls, "clock", "#f59e0b",
                           "SLA Breaches", str(sla_ct),
                           "High priority &gt; 4h open", sla_text_style),
            unsafe_allow_html=True,
        )

    fraud_total = metrics.get("fraud_exposure_total", 0)
    with p4:
        st.markdown(
            analytics_card("ac-amber", "shield-check", "#f59e0b",
                           "Fraud Exposure (All-Time)", _fmt_currency(fraud_total),
                           f'{metrics.get("fraud_alerts_open",0)} unresolved'),
            unsafe_allow_html=True,
        )

    sla_detail = metrics.get("sla_breach_detail", [])
    if sla_detail:
        with st.expander(f"{len(sla_detail)} SLA Breach Detail(s)", expanded=False):
            for b in sla_detail:
                st.markdown(
                    sla_breach_row(b.get("customer_name", "Unknown"), b.get("category", "General"),
                                   b.get("hours_open", 0), b.get("amount") or "N/A"),
                    unsafe_allow_html=True,
                )

    st.markdown("")

    # ROW 2: OPERATIONAL HEALTH
    st.markdown(chart_title_html("activity", "#4f46e5", "OPERATIONAL HEALTH"), unsafe_allow_html=True)
    op1, op2 = st.columns(2)

    with op1:
        st.markdown('<div class="chart-card">', unsafe_allow_html=True)
        st.markdown(chart_title_inner("trending-up", "#4f46e5", "Incoming Volume by Hour (Last 48h)"), unsafe_allow_html=True)
        vol_data = metrics.get("volume_by_hour", [])
        if vol_data:
            hours = [v["hour"] for v in vol_data]
            counts = [v["count"] for v in vol_data]
            labels = []
            for h in hours:
                try:
                    dt = datetime.strptime(h, "%Y-%m-%d %H:%M")
                    labels.append(dt.strftime("%b %d %H:%M"))
                except Exception:
                    labels.append(h)
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=labels, y=counts, mode='lines+markers',
                line=dict(color='#4f46e5', width=2.5),
                marker=dict(size=4, color='#4f46e5'),
                fill='tozeroy', fillcolor='rgba(79, 70, 229, 0.08)',
                hovertemplate='%{x}<br>Tickets: %{y}<extra></extra>',
            ))
            fig.update_layout(
                height=300, margin=dict(l=10, r=10, t=10, b=30),
                plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)',
                xaxis=dict(showgrid=False, tickangle=-45, tickfont=dict(size=9, color='#9ca3af'), nticks=12),
                yaxis=dict(showgrid=True, gridcolor='#f3f4f6', tickfont=dict(size=10, color='#9ca3af')),
                hoverlabel=dict(bgcolor='#1a1a2e', font_color='white', font_size=12),
            )
            st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
        else:
            st.caption("No volume data in the last 48 hours.")
        st.markdown('</div>', unsafe_allow_html=True)

    with op2:
        st.markdown('<div class="chart-card">', unsafe_allow_html=True)
        st.markdown(chart_title_inner("building", "#4f46e5", "Top 5 Merchants / Entities Mentioned"), unsafe_allow_html=True)
        top_m = metrics.get("top_merchants", [])
        if top_m:
            names = [m["name"] for m in top_m]
            cnts = [m["count"] for m in top_m]
            fig2 = go.Figure()
            fig2.add_trace(go.Bar(
                y=names[::-1], x=cnts[::-1], orientation='h',
                marker=dict(
                    color=['#4f46e5', '#6366f1', '#818cf8', '#a5b4fc', '#c7d2fe'][:len(names)][::-1],
                    cornerradius=4,
                ),
                hovertemplate='%{y}: %{x} mentions<extra></extra>',
            ))
            fig2.update_layout(
                height=300, margin=dict(l=10, r=10, t=10, b=10),
                plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)',
                xaxis=dict(showgrid=True, gridcolor='#f3f4f6', tickfont=dict(size=10, color='#9ca3af')),
                yaxis=dict(tickfont=dict(size=11, color='#1a1a2e', family='Inter')),
                hoverlabel=dict(bgcolor='#1a1a2e', font_color='white', font_size=12),
            )
            st.plotly_chart(fig2, use_container_width=True, config={"displayModeBar": False})
        else:
            st.caption("No merchant data extracted yet.")
        st.markdown('</div>', unsafe_allow_html=True)

    st.markdown("")

    # ROW 3: AGENT PERFORMANCE
    st.markdown(chart_title_html("brain", "#4f46e5", "AGENT & AI PERFORMANCE"), unsafe_allow_html=True)
    a1, a2, a3, a4 = st.columns(4)
    ai_rate = metrics.get("ai_success_rate", 0)
    avg_res = metrics.get("avg_resolution_h", 0)
    with a1:
        st.markdown(
            analytics_card("ac-indigo", "brain", "#4f46e5",
                           "AI Draft Acceptance", f"{ai_rate:.0f}%",
                           f'{metrics.get("ai_drafts_used",0)} drafts sent as-is'),
            unsafe_allow_html=True,
        )
    with a2:
        st.markdown(
            analytics_card("ac-blue", "timer", "#3b82f6",
                           "Avg Resolution Time", _fmt_hours(avg_res),
                           f'{metrics.get("closed_tickets",0)} tickets resolved'),
            unsafe_allow_html=True,
        )
    with a3:
        st.markdown(
            analytics_card("ac-green", "inbox", "#22c55e",
                           "Total Tickets", str(metrics.get("total_tickets", 0)),
                           f'{metrics.get("open_tickets",0)} open / {metrics.get("closed_tickets",0)} closed'),
            unsafe_allow_html=True,
        )
    with a4:
        resolve_pct = (metrics.get("closed_tickets", 0) / metrics.get("total_tickets", 1) * 100) if metrics.get("total_tickets") else 0
        st.markdown(
            analytics_card("ac-purple", "check-circle", "#8b5cf6",
                           "Resolution Rate", f"{resolve_pct:.0f}%",
                           f'{metrics.get("closed_tickets",0)} of {metrics.get("total_tickets",0)}'),
            unsafe_allow_html=True,
        )

    st.markdown("")

    cat_perf = metrics.get("category_performance", [])
    if cat_perf:
        st.markdown('<div class="chart-card">', unsafe_allow_html=True)
        st.markdown(chart_title_inner("trophy", "#f59e0b", "Category Performance Leaderboard"), unsafe_allow_html=True)
        st.markdown(category_table(cat_perf, _fmt_hours), unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)

    st.markdown("")

    # DISTRIBUTION OVERVIEW
    st.markdown(chart_title_html("pie-chart", "#4f46e5", "DISTRIBUTION OVERVIEW"), unsafe_allow_html=True)
    d1, d2, d3 = st.columns(3)

    with d1:
        st.markdown('<div class="chart-card">', unsafe_allow_html=True)
        st.markdown('<div class="chart-title">Priority Split</div>', unsafe_allow_html=True)
        _UNR = {"Open", "New", "In Progress"}
        unresolved_tix = [t for t in all_tickets if t.get("status") in _UNR]
        pri_counts = Counter(t.get("priority", "Low") for t in unresolved_tix)
        labels_p = ["High", "Medium", "Low"]
        vals_p = [pri_counts.get(l, 0) for l in labels_p]
        colors_p = ["#ef4444", "#f59e0b", "#22c55e"]
        if sum(vals_p) > 0:
            fig_p = go.Figure(go.Pie(
                labels=labels_p, values=vals_p, hole=0.55,
                marker=dict(colors=colors_p), textinfo='label+value',
                textfont=dict(size=11),
                hovertemplate='%{label}: %{value} tickets<extra></extra>',
            ))
            fig_p.update_layout(height=250, margin=dict(l=0, r=0, t=0, b=0), paper_bgcolor='rgba(0,0,0,0)', showlegend=False)
            st.plotly_chart(fig_p, use_container_width=True, config={"displayModeBar": False})
        else:
            st.caption("No unresolved tickets.")
        st.markdown('</div>', unsafe_allow_html=True)

    with d2:
        st.markdown('<div class="chart-card">', unsafe_allow_html=True)
        st.markdown('<div class="chart-title">Category Split</div>', unsafe_allow_html=True)
        cat_counts = Counter(t.get("category", "General") for t in all_tickets)
        labels_c = ["Fraud", "Payment Issue", "General"]
        vals_c = [cat_counts.get(l, 0) for l in labels_c]
        colors_c = ["#dc2626", "#3b82f6", "#6b7280"]
        if sum(vals_c) > 0:
            fig_c = go.Figure(go.Pie(
                labels=labels_c, values=vals_c, hole=0.55,
                marker=dict(colors=colors_c), textinfo='label+value',
                textfont=dict(size=11),
                hovertemplate='%{label}: %{value} tickets<extra></extra>',
            ))
            fig_c.update_layout(height=250, margin=dict(l=0, r=0, t=0, b=0), paper_bgcolor='rgba(0,0,0,0)', showlegend=False)
            st.plotly_chart(fig_c, use_container_width=True, config={"displayModeBar": False})
        else:
            st.caption("No tickets yet.")
        st.markdown('</div>', unsafe_allow_html=True)

    with d3:
        st.markdown('<div class="chart-card">', unsafe_allow_html=True)
        st.markdown('<div class="chart-title">Status Split</div>', unsafe_allow_html=True)
        status_counts = Counter(t.get("status", "New") for t in all_tickets)
        labels_s = ["New", "Open", "In Progress", "Resolved", "Closed"]
        vals_s = [status_counts.get(l, 0) for l in labels_s]
        colors_s = ["#3b82f6", "#6366f1", "#f59e0b", "#22c55e", "#6b7280"]
        if sum(vals_s) > 0:
            fig_s = go.Figure(go.Pie(
                labels=labels_s, values=vals_s, hole=0.55,
                marker=dict(colors=colors_s), textinfo='label+value',
                textfont=dict(size=11),
                hovertemplate='%{label}: %{value}<extra></extra>',
            ))
            fig_s.update_layout(height=250, margin=dict(l=0, r=0, t=0, b=0), paper_bgcolor='rgba(0,0,0,0)', showlegend=False)
            st.plotly_chart(fig_s, use_container_width=True, config={"displayModeBar": False})
        else:
            st.caption("No tickets yet.")
        st.markdown('</div>', unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════
#  PAGE: INBOX
# ══════════════════════════════════════════════════════════
elif st.session_state.tab == "inbox":
    st.markdown(top_bar("Inbox"), unsafe_allow_html=True)

    def _on_search_change():
        st.session_state.search_query = st.session_state.search_input

    search_query = st.text_input(
        "Search", value=st.session_state.search_query,
        placeholder="Search by keyword, subject, sender, email, category, amount…",
        key="search_input", label_visibility="collapsed",
        on_change=_on_search_change,
    )
    st.session_state.search_query = search_query

    # Load external JS for live search debounce (cached)
    _js_content = _load_js()
    if _js_content:
        st.markdown(f"<script>{_js_content}</script>", unsafe_allow_html=True)

    # Auto-mark selected ticket as read
    sel_id = st.session_state.sel
    if sel_id and sel_id not in st.session_state.read_ids:
        _api_mark_read(sel_id)
        st.session_state.read_ids.add(sel_id)

    display_tickets = [t for t in tickets if _search_match(t, search_query)]

    if search_query:
        st.markdown(
            alert_bar("ab-blue", "search", "#2563eb",
                      f'Found <b>{len(display_tickets)}</b> result(s) for "<b>{search_query}</b>"'),
            unsafe_allow_html=True,
        )

    def _render_email_row(tkt, key_prefix, sel_id):
        tid = tkt.get("id", "")
        sender = _extract_sender(tkt.get("email_body", ""), tkt.get("customer_name", ""))
        subject = _extract_subject(tkt.get("email_body", ""))
        preview = _get_preview(tkt.get("email_body", ""))
        pri = tkt.get("priority", "Medium")
        cat = tkt.get("category", "General")
        ts = _fmt_time(tkt.get("created_at"))
        is_read = _is_ticket_read(tkt)
        selected = tid == sel_id
        st.markdown(
            email_row(sender, subject, preview, pri, cat, ts, is_read, selected),
            unsafe_allow_html=True,
        )
        if st.button("Open", key=f"{key_prefix}_{tid}", use_container_width=True):
            st.session_state.sel = tid
            st.rerun()

    def _render_email_list(ticket_list, key_prefix, sel_id):
        sorted_tix = sorted(
            ticket_list,
            key=lambda t: (
                _PRI_ORDER.get(t.get("priority", "Low"), 2),
                -(datetime.fromisoformat(t["created_at"]).timestamp() if t.get("created_at") else 0),
            ),
        )
        if not sorted_tix:
            st.markdown(welcome_empty(), unsafe_allow_html=True)
            return

        if sel_id and sel_id in {t["id"] for t in sorted_tix}:
            list_col, detail_col = st.columns([2, 3])
        else:
            list_col = st.container()
            detail_col = None

        with list_col:
            groups: dict[str, list] = {}
            for t in sorted_tix:
                g = _date_group(t.get("created_at"))
                groups.setdefault(g, []).append(t)

            st.markdown('<div class="email-list">', unsafe_allow_html=True)
            for grp_name, grp_tix in groups.items():
                st.markdown(f'<div class="date-group">{grp_name}</div>', unsafe_allow_html=True)
                for tkt in grp_tix:
                    _render_email_row(tkt, key_prefix, sel_id)
            st.markdown("</div>", unsafe_allow_html=True)

        if sel_id and detail_col:
            with detail_col:
                tkt = next((t for t in sorted_tix if t.get("id") == sel_id), None)
                if tkt:
                    _render_detail(tkt, key_prefix)
                else:
                    st.warning("Ticket not found.")
                    if st.button("← Back"):
                        st.session_state.sel = None
                        st.rerun()

    _UNRESOLVED = {"Open", "New", "In Progress"}
    unresolved = [t for t in display_tickets if t.get("status") in _UNRESOLVED]
    resolved = [t for t in display_tickets if t.get("status") in ("Resolved", "Closed")]
    fraud_list = [t for t in unresolved if t.get("category") == "Fraud"]
    payment_list = [t for t in unresolved if t.get("category") == "Payment Issue"]
    general_list = [t for t in unresolved if t.get("category") == "General"]

    unread_count = sum(1 for t in unresolved if not _is_ticket_read(t))
    tab_labels = [
        f"Inbox ({len(unresolved)})" + (f" · {unread_count} unread" if unread_count else ""),
        f"Fraud ({len(fraud_list)})",
        f"Payments ({len(payment_list)})",
        f"General ({len(general_list)})",
        f"Resolved ({len(resolved)})",
    ]
    t_inbox, t_fraud, t_payment, t_general, t_resolved = st.tabs(tab_labels)

    with t_inbox:
        _render_email_list(unresolved, "ui", sel_id)
    with t_fraud:
        _render_email_list(fraud_list, "uf", sel_id)
    with t_payment:
        _render_email_list(payment_list, "up", sel_id)
    with t_general:
        _render_email_list(general_list, "ug", sel_id)
    with t_resolved:
        _render_email_list(resolved, "ur", sel_id)


# ──────────────────────────────────────────────────────
#  TAB: PRIORITY QUEUE
# ──────────────────────────────────────────────────────
elif st.session_state.tab == "queue":
    st.markdown(top_bar("Priority Queue"), unsafe_allow_html=True)

    if st.session_state.sel:
        tkt = next((t for t in tickets if t.get("id") == st.session_state.sel), None)
        if tkt:
            _render_detail(tkt)
            st.stop()

    for icon_html, title, pri, qc in [
        (icon("alert-triangle", "#ef4444", 18), "High Priority — Immediate", "High", "qc-r"),
        (icon("clock", "#f59e0b", 18), "Medium Priority — Review Soon", "Medium", "qc-a"),
        (icon("check-circle", "#22c55e", 18), "Low Priority — When Available", "Low", "qc-g"),
    ]:
        grp = [t for t in tickets if t.get("priority") == pri]
        st.markdown(queue_section_header(icon_html, title, len(grp), qc), unsafe_allow_html=True)
        if grp:
            for t in grp:
                sender = _extract_sender(t.get("email_body", ""), t.get("customer_name", ""))
                subject = _extract_subject(t.get("email_body", ""))
                c1, c2, c3 = st.columns([4, 1, 1])
                with c1:
                    st.markdown(f"{avatar(sender)} **{sender}** — {subject}", unsafe_allow_html=True)
                    st.caption(t.get("summary", "")[:100])
                with c2:
                    st.markdown(cat_badge(t.get("category", "General")), unsafe_allow_html=True)
                with c3:
                    if st.button("Open →", key=f"q_{t['id']}", use_container_width=True):
                        st.session_state.sel = t["id"]
                        st.session_state.tab = "inbox"
                        st.rerun()
        else:
            st.caption(f"  No {pri.lower()} priority emails")
        st.markdown("")


# ──────────────────────────────────────────────────────
#  TAB: BY CATEGORY
# ──────────────────────────────────────────────────────
elif st.session_state.tab == "category":
    st.markdown(top_bar("By Category"), unsafe_allow_html=True)

    if st.session_state.sel:
        tkt = next((t for t in tickets if t.get("id") == st.session_state.sel), None)
        if tkt:
            _render_detail(tkt)
            st.stop()

    for icon_html, title, cat, cc in [
        (icon("shield-alert", "#dc2626", 18), "Fraud", "Fraud", "qc-r"),
        (icon("credit-card", "#f59e0b", 18), "Payment Issues", "Payment Issue", "qc-a"),
        (icon("file-text", "#22c55e", 18), "General Inquiries", "General", "qc-g"),
    ]:
        grp = [t for t in tickets if t.get("category") == cat]
        st.markdown(queue_section_header(icon_html, title, len(grp), cc), unsafe_allow_html=True)
        if grp:
            for t in grp:
                sender = _extract_sender(t.get("email_body", ""), t.get("customer_name", ""))
                subject = _extract_subject(t.get("email_body", ""))
                c1, c2, c3 = st.columns([4, 1, 1])
                with c1:
                    st.markdown(f"{avatar(sender)} **{sender}** — {subject}", unsafe_allow_html=True)
                    st.caption(t.get("summary", "")[:100])
                with c2:
                    st.markdown(pri_badge(t.get("priority", "Medium")), unsafe_allow_html=True)
                with c3:
                    if st.button("Open →", key=f"c_{t['id']}", use_container_width=True):
                        st.session_state.sel = t["id"]
                        st.session_state.tab = "inbox"
                        st.rerun()
        else:
            st.caption(f"  No {title.lower()}")
        st.markdown("")


# ──────────────────────────────────────────────────────
#  TAB: ALERTS
# ──────────────────────────────────────────────────────
elif st.session_state.tab == "alerts":
    st.markdown(top_bar("Alerts"), unsafe_allow_html=True)

    if st.session_state.sel:
        tkt = next((t for t in tickets if t.get("id") == st.session_state.sel), None)
        if tkt:
            _render_detail(tkt)
            st.stop()

    alert_tix = []
    seen: set = set()
    for t in tickets:
        if t["id"] in seen:
            continue
        if (
            t.get("category") == "Fraud"
            or t.get("priority") == "High"
            or t.get("sentiment") in ("Urgent", "Negative")
        ):
            seen.add(t["id"])
            alert_tix.append(t)

    if not alert_tix:
        st.markdown(
            alert_bar("ab-green", "check-circle", "#16a34a",
                      "<b>All clear!</b> No alerts right now."),
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            alert_bar("ab-red", "bell", "#dc2626",
                      f'<b>{len(alert_tix)} Active Alert{"s" if len(alert_tix) > 1 else ""}</b> — '
                      f"Emails needing immediate attention."),
            unsafe_allow_html=True,
        )
        for t in alert_tix:
            sender = _extract_sender(t.get("email_body", ""), t.get("customer_name", ""))
            subject = _extract_subject(t.get("email_body", ""))
            pri = t.get("priority", "Medium")
            cat = t.get("category", "General")
            snt = t.get("sentiment", "Neutral")
            reasons = []
            if cat == "Fraud":
                reasons.append("Fraud")
            if pri == "High":
                reasons.append("High Priority")
            if snt in ("Urgent", "Negative"):
                reasons.append(f"{snt}")

            st.markdown(
                alert_ticket_card(sender, subject, t.get("summary", ""),
                                   pri, cat, snt, _fmt_time(t.get("created_at")), reasons),
                unsafe_allow_html=True,
            )
            if st.button("View Details →", key=f"al_{t['id']}", use_container_width=True):
                st.session_state.sel = t["id"]
                st.session_state.tab = "inbox"
                st.rerun()
