from contextlib import asynccontextmanager
from typing import Optional, List
import os, re, smtplib, logging, asyncio
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from fastapi import FastAPI, HTTPException, Depends, Query, File, UploadFile, Form
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from dotenv import load_dotenv

from database import engine, Base, get_db
from models import Ticket, TicketStatus, TicketPriority, TicketCategory
from schemas import AnalyzeRequest, TicketAnalysis, ProcessTicketResponse
from agent import analyze_ticket, generate_draft_response, analyze_and_draft
from urgency_classifier import classify_urgency, get_parent_category

load_dotenv()

logger = logging.getLogger("email_sender")

SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
EMAIL_USER = os.getenv("EMAIL_USER", "")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD", "")


def _extract_recipient_email(email_body: str) -> str | None:
    """Pull the sender's email address from the stored email body (From: line)."""
    if not email_body:
        return None
    for line in email_body.split("\n"):
        stripped = line.strip()
        if stripped.lower().startswith("from:"):
            value = stripped.split(":", 1)[1].strip()
            match = re.search(r'[\w.+-]+@[\w-]+\.[\w.-]+', value)
            return match.group(0) if match else None
    return None


def _extract_subject(email_body: str) -> str:
    """Pull the subject from the stored email body."""
    if not email_body:
        return "Finance Support Response"
    for line in email_body.split("\n"):
        stripped = line.strip()
        if stripped.lower().startswith("subject:"):
            return "Re: " + stripped.split(":", 1)[1].strip()
    return "Finance Support Response"


def send_reply_email(to_email: str, subject: str, body: str) -> bool:
    """Send the draft response to the customer via Gmail SMTP."""
    if not EMAIL_USER or not EMAIL_PASSWORD:
        logger.error("EMAIL_USER / EMAIL_PASSWORD not set — cannot send.")
        return False
    try:
        msg = MIMEMultipart("alternative")
        msg["From"] = EMAIL_USER
        msg["To"] = to_email
        msg["Subject"] = subject

        msg.attach(MIMEText(body, "plain"))

        html = (
            '<div style="font-family:Arial,sans-serif;font-size:14px;'
            'line-height:1.7;color:#333;">'
            + body.replace("\n", "<br>") +
            '<br><br><hr style="border:none;border-top:1px solid #ddd;">'
            '<small style="color:#888;">This is an automated response from '
            'Finance Support Triage Agent.</small></div>'
        )
        msg.attach(MIMEText(html, "html"))

        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(EMAIL_USER, EMAIL_PASSWORD)
            server.sendmail(EMAIL_USER, to_email, msg.as_string())

        logger.info(f"✅ Reply sent to {to_email}")
        return True
    except Exception as e:
        logger.error(f"❌ Failed to send email to {to_email}: {e}")
        return False


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Create database tables on startup and run lightweight migrations."""
    from sqlalchemy import text, inspect as sa_inspect
    print("📦 Creating database tables...")
    Base.metadata.create_all(bind=engine)

    # ── Lightweight migrations for existing databases ──
    with engine.begin() as conn:
        # 1. Add 'Open' to ticket_status enum if missing
        try:
            conn.execute(text(
                "ALTER TYPE ticket_status ADD VALUE IF NOT EXISTS 'Open'"
            ))
        except Exception:
            pass  # already exists or DB doesn't support ALTER TYPE

        # 2. Add is_read column if missing
        inspector = sa_inspect(engine)
        columns = [c["name"] for c in inspector.get_columns("tickets")]
        if "is_read" not in columns:
            conn.execute(text(
                "ALTER TABLE tickets ADD COLUMN is_read BOOLEAN NOT NULL DEFAULT FALSE"
            ))
            print("  ✅ Added is_read column to tickets table.")

        # 3. Add is_ai_draft_edited column if missing
        if "is_ai_draft_edited" not in columns:
            conn.execute(text(
                "ALTER TABLE tickets ADD COLUMN is_ai_draft_edited BOOLEAN NOT NULL DEFAULT FALSE"
            ))
            print("  ✅ Added is_ai_draft_edited column to tickets table.")

    print("✅ Database tables are ready.")

    # ── Background email polling (Railway keeps the process alive) ──
    EMAIL_POLL_INTERVAL = int(os.getenv("EMAIL_POLL_INTERVAL", "300"))  # seconds (5 min)
    ENABLE_EMAIL_POLLING = os.getenv("ENABLE_EMAIL_POLLING", "true").lower() == "true"
    _BACKEND_PORT = os.getenv("PORT", "8000")

    async def _background_email_poller():
        """Periodically fetch emails via IMAP in the background."""
        await asyncio.sleep(15)  # let the server fully start
        logger.info(f"📧 Background email poller started (interval={EMAIL_POLL_INTERVAL}s)")
        while True:
            try:
                import requests as _req
                resp = _req.post(
                    f"http://127.0.0.1:{_BACKEND_PORT}/fetch_emails?max_emails=5",
                    timeout=300,  # 5 min timeout (AI analysis can be slow)
                )
                if resp.ok:
                    data = resp.json()
                    fetched = data.get("fetched", 0)
                    if fetched > 0:
                        logger.info(f"📬 Background poller: {fetched} new email(s) processed")
                    else:
                        logger.debug("📧 No new emails")
                else:
                    logger.warning(f"📧 Background poller: API returned {resp.status_code}")
            except Exception as e:
                logger.warning(f"📧 Background poller error (will retry): {e}")
            await asyncio.sleep(EMAIL_POLL_INTERVAL)

    poll_task = None
    if ENABLE_EMAIL_POLLING:
        poll_task = asyncio.create_task(_background_email_poller())
        logger.info("📧 Email polling enabled (set ENABLE_EMAIL_POLLING=false to disable)")
    else:
        logger.info("📧 Email polling disabled")

    yield

    # Cleanup: cancel background task on shutdown
    if poll_task:
        poll_task.cancel()
        try:
            await poll_task
        except asyncio.CancelledError:
            pass


app = FastAPI(
    title="Finance Support Triage Agent",
    description="An AI-powered finance support triage agent",
    version="1.0.0",
    lifespan=lifespan,
)

# Allow Streamlit (port 8501) to call the API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def root():
    return {"message": "Finance Agent is Running"}


# =====================================================================
#  ENTERPRISE DASHBOARD METRICS
# =====================================================================

def _parse_amount(amount_str: str | None) -> float:
    """Extract a numeric dollar value from a string like '$3,000.00' or '3000'."""
    if not amount_str:
        return 0.0
    cleaned = re.sub(r'[^\d.]', '', amount_str)
    try:
        return float(cleaned)
    except (ValueError, TypeError):
        return 0.0


def _extract_merchants(email_body: str) -> list[str]:
    """Extract likely merchant/company names from an email body."""
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


def calculate_dashboard_metrics(db: Session) -> dict:
    """
    Compute enterprise-grade financial & operational KPIs from the tickets table.

    Returns a dict consumed by the /dashboard_metrics endpoint.
    """
    from datetime import datetime as _dt, timezone as _tz, timedelta as _td
    from collections import Counter as _Counter

    all_tickets = db.query(Ticket).order_by(Ticket.created_at.desc()).all()
    now = _dt.now(_tz.utc)

    _OPEN = {TicketStatus.OPEN, TicketStatus.NEW, TicketStatus.IN_PROGRESS}
    _CLOSED = {TicketStatus.RESOLVED, TicketStatus.CLOSED}

    open_tickets = [t for t in all_tickets if t.status in _OPEN]
    closed_tickets = [t for t in all_tickets if t.status in _CLOSED]
    fraud_tickets = [t for t in all_tickets if t.category == TicketCategory.FRAUD]
    fraud_open = [t for t in fraud_tickets if t.status in _OPEN]

    # ── 1. Total Disputed Volume (sum of amounts for open tickets) ──
    total_disputed = sum(_parse_amount(t.amount) for t in open_tickets)

    # ── 2. SLA Breaches (High priority, open > 4 hours) ──
    sla_threshold = now - _td(hours=4)
    sla_breaches = [
        t for t in open_tickets
        if t.priority == TicketPriority.HIGH
        and t.created_at
        and t.created_at < sla_threshold
    ]

    # ── 3. Fraud Exposure (sum of amounts for ALL fraud tickets) ──
    fraud_exposure = sum(_parse_amount(t.amount) for t in fraud_tickets)
    fraud_open_value = sum(_parse_amount(t.amount) for t in fraud_open)

    # ── 4. AI Success Rate (closed tickets where draft was NOT edited) ──
    ai_used = sum(1 for t in closed_tickets if not t.is_ai_draft_edited)
    ai_success_rate = (ai_used / len(closed_tickets) * 100) if closed_tickets else 0.0

    # ── 5. Avg Resolution Time ──
    resolution_hours = []
    for t in closed_tickets:
        if t.created_at:
            delta = (now - t.created_at).total_seconds() / 3600
            resolution_hours.append(delta)
    avg_resolution_h = sum(resolution_hours) / len(resolution_hours) if resolution_hours else 0

    # ── 6. Volume by Hour (last 48 hours) ──
    cutoff_48h = now - _td(hours=48)
    hourly_counts: dict[str, int] = {}
    for t in all_tickets:
        if t.created_at and t.created_at >= cutoff_48h:
            hour_key = t.created_at.strftime("%Y-%m-%d %H:00")
            hourly_counts[hour_key] = hourly_counts.get(hour_key, 0) + 1
    # Fill in missing hours
    volume_by_hour = []
    cur = cutoff_48h.replace(minute=0, second=0, microsecond=0)
    while cur <= now:
        key = cur.strftime("%Y-%m-%d %H:00")
        volume_by_hour.append({"hour": key, "count": hourly_counts.get(key, 0)})
        cur += _td(hours=1)

    # ── 7. Top Merchants / Issues ──
    merchant_counter: _Counter = _Counter()
    for t in all_tickets:
        for m in _extract_merchants(t.email_body):
            merchant_counter[m] += 1
    top_merchants = [{"name": n, "count": c} for n, c in merchant_counter.most_common(5)]

    # ── 8. Agent Leaderboard (group by customer_name as proxy for agent) ──
    # For a real system you'd have an assigned_agent column. We
    # simulate by treating unique customer_name groups as workload buckets.
    # In this MVP, the leaderboard shows category-level performance.
    category_perf = []
    for cat in [TicketCategory.FRAUD, TicketCategory.PAYMENT_ISSUE, TicketCategory.GENERAL]:
        cat_all = [t for t in all_tickets if t.category == cat]
        cat_closed = [t for t in cat_all if t.status in _CLOSED]
        cat_avg_h = 0.0
        if cat_closed:
            deltas = []
            for t in cat_closed:
                if t.created_at:
                    deltas.append((now - t.created_at).total_seconds() / 3600)
            cat_avg_h = sum(deltas) / len(deltas) if deltas else 0
        reopen = sum(1 for t in cat_all if t.status == TicketStatus.OPEN)
        category_perf.append({
            "category": cat.value,
            "total": len(cat_all),
            "closed": len(cat_closed),
            "avg_resolution_h": round(cat_avg_h, 1),
            "reopen_count": reopen,
            "reopen_rate": round(reopen / len(cat_all) * 100, 1) if cat_all else 0,
        })

    # ── 9. SLA breach detail list ──
    sla_detail = []
    for t in sla_breaches:
        hrs_open = (now - t.created_at).total_seconds() / 3600 if t.created_at else 0
        sla_detail.append({
            "id": str(t.id),
            "customer_name": t.customer_name,
            "amount": t.amount,
            "hours_open": round(hrs_open, 1),
            "category": t.category.value if t.category else "General",
        })

    return {
        "total_tickets": len(all_tickets),
        "open_tickets": len(open_tickets),
        "closed_tickets": len(closed_tickets),
        "total_disputed_volume": round(total_disputed, 2),
        "sla_breaches": len(sla_breaches),
        "sla_breach_detail": sla_detail,
        "fraud_alerts_open": len(fraud_open),
        "fraud_exposure_total": round(fraud_exposure, 2),
        "fraud_exposure_open": round(fraud_open_value, 2),
        "ai_success_rate": round(ai_success_rate, 1),
        "ai_drafts_used": ai_used,
        "avg_resolution_h": round(avg_resolution_h, 1),
        "volume_by_hour": volume_by_hour,
        "top_merchants": top_merchants,
        "category_performance": category_perf,
    }


@app.get("/dashboard_metrics")
def dashboard_metrics(db: Session = Depends(get_db)):
    """Enterprise-grade dashboard metrics for the Finance Triage analytics page."""
    try:
        return calculate_dashboard_metrics(db)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Metrics calculation failed: {str(e)}")


@app.post("/classify_urgency")
def classify_urgency_endpoint(request: AnalyzeRequest):
    """
    Advanced multi-tier urgency classification (3 tiers × 12 sub-categories).

    Returns JSON: {urgency, subcategory, confidence, reasoning, sla}
    Targets < 500 ms latency. Falls back to Medium on errors.
    """
    try:
        result = classify_urgency(request.email_body)
        return result
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Urgency classification failed: {str(e)}",
        )


@app.post("/analyze", response_model=TicketAnalysis)
def analyze_email(request: AnalyzeRequest):
    """
    Analyse a customer support email and return structured triage data.

    Accepts the raw email text and returns sentiment, intent,
    extracted entities, priority, category, and a summary.
    """
    try:
        result = analyze_ticket(request.email_body)
        return result
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Analysis failed: {str(e)}",
        )


# ---------- Map schema enums → ORM enums ----------

_PRIORITY_MAP = {
    "High": TicketPriority.HIGH,
    "Medium": TicketPriority.MEDIUM,
    "Low": TicketPriority.LOW,
}

_CATEGORY_MAP = {
    "Fraud": TicketCategory.FRAUD,
    "Payment Issue": TicketCategory.PAYMENT_ISSUE,
    "General": TicketCategory.GENERAL,
}


def _resolve_priority(email_text: str, agent_priority: str, agent_category: str):
    """
    Two-pass priority resolution:
      1. Agent (llama-3.3-70b) provides initial priority + category.
      2. Urgency classifier (llama-3.1-8b, 12 sub-categories) runs as a
         fast second opinion.

    Rules:
      • If the classifier returns a HIGHER urgency than the agent → promote.
      • If the classifier has confidence >= 0.75 → trust it outright.
      • Otherwise keep the agent's original priority.
      • Also return the classifier's subcategory + SLA for metadata.
    """
    try:
        clf = classify_urgency(email_text)
    except Exception:
        # Classifier failed — fall back to agent's judgement
        return agent_priority, agent_category, None

    clf_urgency = clf["urgency"]
    clf_confidence = clf["confidence"]
    clf_subcat = clf["subcategory"]
    clf_sla = clf["sla"]

    # Numeric ranking: High=3, Medium=2, Low=1
    _rank = {"High": 3, "Medium": 2, "Low": 1}
    agent_rank = _rank.get(agent_priority, 2)
    clf_rank = _rank.get(clf_urgency, 2)

    # Decide final priority
    if clf_confidence >= 0.75:
        # High-confidence classifier result takes precedence
        final_priority = clf_urgency
    elif clf_rank > agent_rank:
        # Classifier sees higher urgency — always promote
        final_priority = clf_urgency
    else:
        final_priority = agent_priority

    # Optionally upgrade category based on subcategory
    final_category = agent_category
    parent_cat = get_parent_category(clf_subcat)
    if final_priority == "High" and parent_cat == "Fraud" and agent_category != "Fraud":
        final_category = "Fraud"
    elif final_priority == "High" and parent_cat == "Payment Issue" and agent_category == "General":
        final_category = "Payment Issue"

    return final_priority, final_category, {
        "subcategory": clf_subcat,
        "sla": clf_sla,
        "confidence": clf_confidence,
        "reasoning": clf["reasoning"],
    }


@app.post("/process_ticket", response_model=ProcessTicketResponse)
def process_ticket(request: AnalyzeRequest, db: Session = Depends(get_db)):
    """
    End-to-end ticket processing pipeline:

    1. **Analyse** — Run AI analysis on the email (sentiment, intent, entities,
       priority, category, summary).
    2. **Draft** — Generate a personalised email reply based on the analysis.
    3. **Save** — Persist the ticket with all data to the PostgreSQL database.
    4. **Return** — Send back the ticket ID, full analysis, and draft response.
    """
    # ---- Step 1 + 2: Analyse the email AND generate draft (single LLM call) ----
    try:
        result = analyze_and_draft(request.email_body)
        analysis = result   # TicketAnalysisWithDraft extends TicketAnalysis
        draft = result.draft_response
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Analysis failed: {str(e)}",
        )

    # ---- Step 3: Priority override via urgency classifier ----
    final_pri, final_cat, clf_meta = _resolve_priority(
        request.email_body, analysis.priority.value, analysis.category.value,
    )

    # ---- Step 4: Save to database ----
    try:
        ticket = Ticket(
            customer_name=analysis.entities.customer_name or "Unknown",
            email_body=request.email_body,
            status="New",
            priority=_PRIORITY_MAP.get(final_pri, TicketPriority.MEDIUM),
            category=_CATEGORY_MAP.get(final_cat, TicketCategory.GENERAL),
            sentiment=analysis.sentiment.value,
            intent=analysis.intent,
            summary=analysis.summary,
            transaction_id=analysis.entities.transaction_id,
            amount=analysis.entities.amount,
            draft_response=draft,
        )
        db.add(ticket)
        db.commit()
        db.refresh(ticket)
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Database save failed: {str(e)}",
        )

    # ---- Step 4: Return result ----
    return ProcessTicketResponse(
        ticket_id=str(ticket.id),
        analysis=analysis,
        draft_response=draft,
        message="Ticket processed and saved successfully.",
    )


@app.post("/process_ticket_image")
async def process_ticket_image():
    """OCR image processing is disabled in this deployment to reduce build size."""
    raise HTTPException(
        status_code=501,
        detail="OCR image processing is not available in this deployment. Please paste the email text directly.",
    )


# =====================================================================
#  TICKET CRUD ENDPOINTS (used by the Streamlit frontend)
# =====================================================================

def _ticket_to_dict(ticket: Ticket) -> dict:
    """Serialise a Ticket ORM object to a plain dict."""
    return {
        "id": str(ticket.id),
        "customer_name": ticket.customer_name,
        "email_body": ticket.email_body,
        "status": ticket.status.value if ticket.status else "New",
        "priority": ticket.priority.value if ticket.priority else "Medium",
        "category": ticket.category.value if ticket.category else "General",
        "sentiment": ticket.sentiment,
        "intent": ticket.intent,
        "summary": ticket.summary,
        "transaction_id": ticket.transaction_id,
        "amount": ticket.amount,
        "draft_response": ticket.draft_response,
        "is_read": ticket.is_read if ticket.is_read is not None else False,
        "is_ai_draft_edited": ticket.is_ai_draft_edited if ticket.is_ai_draft_edited is not None else False,
        "created_at": ticket.created_at.isoformat() if ticket.created_at else None,
    }


@app.get("/tickets")
def list_tickets(
    status: Optional[str] = Query(None, description="Filter by status: Open, New, In Progress, Resolved, Closed"),
    db: Session = Depends(get_db),
):
    """Return all tickets, optionally filtered by status.

    Convenience aliases:
      ?status=open      → all unresolved tickets (Open + New + In Progress)
      ?status=resolved   → only Resolved tickets
    """
    query = db.query(Ticket).order_by(Ticket.created_at.desc())

    if status:
        low = status.strip().lower()
        # Alias: "open" matches all unresolved statuses
        if low == "open":
            query = query.filter(
                Ticket.status.in_([
                    TicketStatus.OPEN,
                    TicketStatus.NEW,
                    TicketStatus.IN_PROGRESS,
                ])
            )
        else:
            try:
                status_enum = TicketStatus(status)
                query = query.filter(Ticket.status == status_enum)
            except ValueError:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid status '{status}'. Must be one of: Open, New, In Progress, Resolved, Closed",
                )

    tickets = query.all()
    return [_ticket_to_dict(t) for t in tickets]


@app.get("/tickets/{ticket_id}")
def get_ticket(ticket_id: str, db: Session = Depends(get_db)):
    """Get a single ticket by ID."""
    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return _ticket_to_dict(ticket)


@app.put("/tickets/{ticket_id}/read")
def mark_ticket_read(ticket_id: str, db: Session = Depends(get_db)):
    """Mark a ticket as read (is_read = True). Idempotent."""
    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    if not ticket.is_read:
        ticket.is_read = True
        db.commit()
        db.refresh(ticket)
    return {"message": "Ticket marked as read.", "ticket": _ticket_to_dict(ticket)}


@app.patch("/tickets/{ticket_id}/approve")
def approve_ticket(ticket_id: str, db: Session = Depends(get_db)):
    """Approve the AI draft — marks ticket as 'In Progress'."""
    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    ticket.status = TicketStatus.IN_PROGRESS
    db.commit()
    db.refresh(ticket)
    return {"message": "Ticket approved. Draft response sent.", "ticket": _ticket_to_dict(ticket)}


@app.post("/approve_ticket/{ticket_id}")
def approve_and_close_ticket(ticket_id: str, db: Session = Depends(get_db)):
    """Approve the AI draft, send it via email, and close the ticket."""
    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    # --- Actually send the reply email ---
    email_sent = False
    recipient = _extract_recipient_email(ticket.email_body)
    if recipient and ticket.draft_response:
        subject = _extract_subject(ticket.email_body)
        email_sent = send_reply_email(recipient, subject, ticket.draft_response)
    elif not recipient:
        logger.warning(f"No recipient email found in ticket {ticket_id}")

    ticket.status = TicketStatus.RESOLVED
    db.commit()
    db.refresh(ticket)

    msg = (
        f"Ticket approved, response sent to {recipient}, and resolved."
        if email_sent
        else "Ticket approved and resolved, but email could not be sent."
    )
    return {
        "message": msg,
        "email_sent": email_sent,
        "recipient": recipient,
        "ticket": _ticket_to_dict(ticket),
    }


@app.patch("/tickets/{ticket_id}/reject")
def reject_ticket(ticket_id: str, db: Session = Depends(get_db)):
    """Reject the AI draft — marks ticket as 'Closed'."""
    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    ticket.status = TicketStatus.CLOSED
    db.commit()
    db.refresh(ticket)
    return {"message": "Ticket rejected and closed.", "ticket": _ticket_to_dict(ticket)}


# =====================================================================
#  EMAIL INGESTION ENDPOINT (triggered from the Streamlit frontend)
# =====================================================================

@app.post("/fetch_emails")
def fetch_emails_endpoint(
    db: Session = Depends(get_db),
    include_read: bool = Query(False, description="Also fetch already-read emails"),
    max_emails: int = Query(5, ge=1, le=50, description="Max emails to process"),
):
    """
    Connect to Gmail via IMAP, pull emails, analyse each one
    with the AI agent, save tickets, and return a summary.

    - By default only UNSEEN (unread) emails are fetched.
    - Set include_read=true to re-fetch ALL recent emails (useful for testing).
    """
    import os
    import imaplib
    import email as email_lib
    from email.header import decode_header as _decode_header
    import time as _time

    EMAIL_USER = os.getenv("EMAIL_USER")
    EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")

    if not EMAIL_USER or not EMAIL_PASSWORD:
        raise HTTPException(
            status_code=500,
            detail="EMAIL_USER and EMAIL_PASSWORD must be set in the .env file.",
        )

    _start = _time.time()
    print(f"📧 fetch_emails called  include_read={include_read}  max_emails={max_emails}")

    # ── Helper: decode MIME headers ──
    def _decode_hdr(value: str) -> str:
        if not value:
            return ""
        parts = []
        for part, charset in _decode_header(value):
            if isinstance(part, bytes):
                parts.append(part.decode(charset or "utf-8", errors="replace"))
            else:
                parts.append(part)
        return " ".join(parts)

    # ── Helper: extract plain-text body ──
    def _extract_body(msg) -> str:
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
                        import re
                        html = payload.decode(part.get_content_charset() or "utf-8", errors="replace")
                        body = re.sub(r"<[^>]+>", " ", html)
                        body = re.sub(r"\s+", " ", body).strip()
        else:
            payload = msg.get_payload(decode=True)
            if payload:
                body = payload.decode(msg.get_content_charset() or "utf-8", errors="replace")
        return body.strip()

    # ── Connect to Gmail ──
    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com", 993)
        mail.login(EMAIL_USER, EMAIL_PASSWORD)
        mail.select("INBOX")
        print(f"  ✅ Connected to Gmail as {EMAIL_USER}")
    except Exception as e:
        print(f"  ❌ IMAP connection failed: {e}")
        raise HTTPException(status_code=500, detail=f"IMAP connection failed: {e}")

    # ── Search for emails ──
    try:
        # Use date-based search instead of UNSEEN to catch emails that
        # were auto-marked as read by Gmail / phone within seconds.
        # This way we never miss emails. Duplicates are filtered by
        # the email_body check against the DB below.
        from datetime import datetime as _dt, timedelta as _td
        if include_read:
            search_criteria = "ALL"
        else:
            # Fetch emails from the last 2 days (IMAP SINCE uses date only, no time)
            since_date = (_dt.now() - _td(days=2)).strftime("%d-%b-%Y")
            search_criteria = f'(SINCE "{since_date}")'
        status, messages = mail.search(None, search_criteria)
        print(f"  🔍 Search criteria: {search_criteria}  status: {status}")

        if status != "OK":
            raise HTTPException(status_code=500, detail="Could not search mailbox.")

        email_ids = messages[0].split()
        # Take only the most recent N emails (last items = newest)
        email_ids = email_ids[-max_emails:] if len(email_ids) > max_emails else email_ids
        print(f"  📬 Found {len(email_ids)} email(s) to process")

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

                # ── Skip duplicates: check if an identical email_body already exists ──
                existing = db.query(Ticket).filter(
                    Ticket.email_body == full_text
                ).first()
                if existing:
                    skipped_dupes += 1
                    mail.store(eid, "+FLAGS", "\\Seen")
                    continue

                print(f"  📩 Processing: {subject[:60]}")

                # ── Analyse + Draft (single LLM call) ──
                try:
                    combined = analyze_and_draft(full_text)
                    analysis = combined
                    draft = combined.draft_response
                except Exception as ai_err:
                    err_str = str(ai_err)
                    # Detect quota / rate-limit errors and abort early
                    if "429" in err_str or "rate_limit" in err_str.lower() or "quota" in err_str.lower():
                        mail.close()
                        mail.logout()
                        elapsed = round(_time.time() - _start, 1)
                        print(f"  🚫 Groq API rate limit hit after {elapsed}s")
                        return {
                            "fetched": len(results),
                            "errors": len(errors) + 1,
                            "skipped_duplicates": skipped_dupes,
                            "tickets": results,
                            "error_details": [
                                "⚠️ Groq API rate limit reached (30 req/min). "
                                "Please wait 1-2 minutes and try again."
                            ],
                            "message": f"Processed {len(results)} email(s) before hitting rate limit.",
                            "quota_error": True,
                        }
                    raise

                # ── Priority override via urgency classifier ──
                final_pri, final_cat, clf_meta = _resolve_priority(
                    full_text, analysis.priority.value, analysis.category.value,
                )

                # ── Save ticket ──
                ticket = Ticket(
                    customer_name=analysis.entities.customer_name or sender.split("<")[0].strip() or "Unknown",
                    email_body=full_text,
                    status="New",
                    priority=_PRIORITY_MAP.get(final_pri, TicketPriority.MEDIUM),
                    category=_CATEGORY_MAP.get(final_cat, TicketCategory.GENERAL),
                    sentiment=analysis.sentiment.value,
                    intent=analysis.intent,
                    summary=analysis.summary,
                    transaction_id=analysis.entities.transaction_id,
                    amount=analysis.entities.amount,
                    draft_response=draft,
                )
                db.add(ticket)
                db.commit()
                db.refresh(ticket)

                mail.store(eid, "+FLAGS", "\\Seen")

                results.append({
                    "ticket_id": str(ticket.id),
                    "subject": subject,
                    "sender": sender,
                    "priority": final_pri,
                    "category": final_cat,
                })
                print(f"    ✅ Ticket {str(ticket.id)[:8]} | {final_pri} | {final_cat}  ({_time.time()-_start:.1f}s elapsed)")
            except Exception as e:
                errors.append(f"{subject if 'subject' in dir() else 'unknown'}: {str(e)}")
                print(f"    ❌ Error: {e}")
                continue

        mail.close()
        mail.logout()

        elapsed = round(_time.time() - _start, 1)
        msg = f"Fetched and processed {len(results)} email(s) in {elapsed}s."
        if skipped_dupes:
            msg += f" Skipped {skipped_dupes} duplicate(s)."
        print(f"  📊 Done: {msg}")

        return {
            "fetched": len(results),
            "errors": len(errors),
            "skipped_duplicates": skipped_dupes,
            "tickets": results,
            "error_details": errors[:10],
            "message": msg,
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"  ❌ Email processing failed: {e}")
        raise HTTPException(status_code=500, detail=f"Email processing failed: {e}")
