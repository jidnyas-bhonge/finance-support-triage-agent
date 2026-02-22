"""
Finance Support Triage Agent — Professional Dashboard + Email Client
Analytics · Categorised Inbox · Blue-dot Read/Unread · Live Search

Restructured: CSS → static/styles.css, JS → static/script.js,
HTML templates → templates.py
"""

import streamlit as st
from streamlit_autorefresh import st_autorefresh
import requests
import re
import os
import time as _time
from pathlib import Path
from datetime import datetime, timedelta
from collections import Counter
import plotly.graph_objects as go
import plotly.express as px

# Import HTML template helpers from templates.py
from templates import (
    icon, avatar, pri_badge, cat_badge, sent_badge, tag_html,
    top_bar, sidebar_header, nav_icon_cell, fetch_how_it_works,
    alert_bar, detail_actions, detail_header, insight_grid,
    email_row, welcome_empty, queue_section_header, section_header,
    chart_title_html, analytics_card, sla_breach_row,
    chart_title_inner, category_table, alert_ticket_card,
)

# ═══════════════════════════════════════════════════════
#  CONFIG
# ═══════════════════════════════════════════════════════
API = os.environ.get("API_BASE_URL", "http://127.0.0.1:8000")
_DIR = Path(__file__).parent

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
}.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ═══════════════════════════════════════════════════════
#  LOAD EXTERNAL CSS
# ═══════════════════════════════════════════════════════
_css_path = _DIR / "static" / "styles.css"
with open(_css_path, encoding="utf-8") as f:
    st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════
#  AUTO-REFRESH
# ═══════════════════════════════════════════════════════
st_autorefresh(interval=30_000, limit=None, key="auto_refresh")

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
    """Extract the email address from the body."""
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
    """Check if a ticket is read (backend flag OR local session cache)."""
    return tkt.get("is_read", False) or tkt.get("id") in st.session_state.read_ids


def _search_match(tkt: dict, query: str) -> bool:
    """Return True if the ticket matches the search query."""
    if not query:
        return True
    q = query.lower()
    searchable = " ".join([
        tkt.get("email_body") or "",
        tkt.get("customer_name") or "",
        tkt.get("summary") or "",
        tkt.get("intent") or "",
        tkt.get("category") or "",
        tkt.get("priority") or "",
        tkt.get("sentiment") or "",
        tkt.get("transaction_id") or "",
        tkt.get("amount") or "",
        _extract_subject(tkt.get("email_body") or ""),
        _extract_email_addr(tkt.get("email_body") or ""),
    ]).lower()
    return all(word in searchable for word in q.split())


# ═══════════════════════════════════════════════════════
#  API LAYER
# ═══════════════════════════════════════════════════════
def _fetch_tickets(status: str = "All"):
    try:
        params = {} if status == "All" else {"status": status}
        r = requests.get(f"{API}/tickets", params=params, timeout=10)
        r.raise_for_status()
        return r.json()
    except requests.ConnectionError:
        st.toast("Backend offline — start FastAPI on port 8000.")
        return []
    except Exception as e:
        st.toast(f"Error: {e}")
        return []


def _api_approve(tid: str):
    try:
        r = requests.post(f"{API}/approve_ticket/{tid}", timeout=30)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        st.error(f"Approve failed: {e}")
        return None


def _api_close(tid: str):
    try:
        r = requests.patch(f"{API}/tickets/{tid}/reject", timeout=10)
        r.raise_for_status()
        return True
    except Exception as e:
        st.error(f"Close failed: {e}")
        return False


def _api_mark_read(tid: str):
    try:
        r = requests.put(f"{API}/tickets/{tid}/read", timeout=5)
        r.raise_for_status()
        return True
    except Exception:
        return False


def _api_fetch_emails(include_read: bool = False, max_emails: int = 5):
    try:
        r = requests.post(
            f"{API}/fetch_emails",
            params={"include_read": include_read, "max_emails": max_emails},
            timeout=600,
        )
        r.raise_for_status()
        return r.json()
    except requests.ConnectionError:
        st.error("Cannot connect to the backend API.")
        return None
    except Exception as e:
        st.error(f"Email fetch failed: {e}")
        return None


def _api_dashboard_metrics():
    """Fetch enterprise dashboard metrics from the backend."""
    try:
        r = requests.get(f"{API}/dashboard_metrics", timeout=15)
        r.raise_for_status()
        return r.json()
    except Exception:
        return None


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
    st.caption("v4.0 • Finance Triage Dashboard")


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

    # ── Fetch computed metrics from backend ──
    metrics = _api_dashboard_metrics()

    if not metrics:
        # Fallback: compute locally from all_tickets
        total = len(all_tickets)
        _UNR = {"Open", "New", "In Progress"}
        unresolved = [t for t in all_tickets if t.get("status") in _UNR]
        resolved = [t for t in all_tickets if t.get("status") in ("Resolved", "Closed")]
        st.warning("Could not fetch metrics from backend — showing basic stats.")

        def _parse_amt(s):
            if not s: return 0.0
            cleaned = re.sub(r'[^\d.]', '', s)
            try: return float(cleaned)
            except: return 0.0

        metrics = {
            "total_tickets": total,
            "open_tickets": len(unresolved),
            "closed_tickets": len(resolved),
            "total_disputed_volume": sum(_parse_amt(t.get("amount")) for t in unresolved),
            "sla_breaches": 0,
            "sla_breach_detail": [],
            "fraud_alerts_open": sum(1 for t in unresolved if t.get("category") == "Fraud"),
            "fraud_exposure_total": sum(_parse_amt(t.get("amount")) for t in all_tickets if t.get("category") == "Fraud"),
            "fraud_exposure_open": sum(_parse_amt(t.get("amount")) for t in unresolved if t.get("category") == "Fraud"),
            "ai_success_rate": 0,
            "ai_drafts_used": 0,
            "avg_resolution_h": 0,
            "volume_by_hour": [],
            "top_merchants": [],
            "category_performance": [],
        }

    # ── Helper: format currency ──
    def _fmt_currency(val):
        if val >= 1_000_000:
            return f"${val/1_000_000:,.1f}M"
        if val >= 1_000:
            return f"${val:,.0f}"
        return f"${val:,.2f}"

    # ── Helper: format hours ──
    def _fmt_hours(h):
        if h < 1: return f"{h*60:.0f}m"
        if h < 24: return f"{h:.1f}h"
        return f"{h/24:.1f}d"

    # ════════════════════════════════════════════════════
    # ROW 1: THE "PANIC" ROW — Key Financial Risks
    # ════════════════════════════════════════════════════
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

    # ── SLA Breach Detail Table (if any) ──
    sla_detail = metrics.get("sla_breach_detail", [])
    if sla_detail:
        with st.expander(f"{len(sla_detail)} SLA Breach Detail(s)", expanded=False):
            for b in sla_detail:
                st.markdown(
                    sla_breach_row(
                        b.get("customer_name", "Unknown"),
                        b.get("category", "General"),
                        b.get("hours_open", 0),
                        b.get("amount") or "N/A",
                    ),
                    unsafe_allow_html=True,
                )

    st.markdown("")

    # ════════════════════════════════════════════════════
    # ROW 2: OPERATIONAL HEALTH
    # ════════════════════════════════════════════════════
    st.markdown(chart_title_html("activity", "#4f46e5", "OPERATIONAL HEALTH"), unsafe_allow_html=True)
    op1, op2 = st.columns(2)

    # ── Chart 1: Incoming Volume by Hour ──
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
                x=labels, y=counts,
                mode='lines+markers',
                line=dict(color='#4f46e5', width=2.5),
                marker=dict(size=4, color='#4f46e5'),
                fill='tozeroy',
                fillcolor='rgba(79, 70, 229, 0.08)',
                hovertemplate='%{x}<br>Tickets: %{y}<extra></extra>',
            ))
            fig.update_layout(
                height=300,
                margin=dict(l=10, r=10, t=10, b=30),
                plot_bgcolor='rgba(0,0,0,0)',
                paper_bgcolor='rgba(0,0,0,0)',
                xaxis=dict(showgrid=False, tickangle=-45, tickfont=dict(size=9, color='#9ca3af'), nticks=12),
                yaxis=dict(showgrid=True, gridcolor='#f3f4f6', tickfont=dict(size=10, color='#9ca3af')),
                hoverlabel=dict(bgcolor='#1a1a2e', font_color='white', font_size=12),
            )
            st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})
        else:
            st.caption("No volume data in the last 48 hours.")
        st.markdown('</div>', unsafe_allow_html=True)

    # ── Chart 2: Top 5 Merchants ──
    with op2:
        st.markdown('<div class="chart-card">', unsafe_allow_html=True)
        st.markdown(chart_title_inner("building", "#4f46e5", "Top 5 Merchants / Entities Mentioned"), unsafe_allow_html=True)
        top_m = metrics.get("top_merchants", [])
        if top_m:
            names = [m["name"] for m in top_m]
            cnts = [m["count"] for m in top_m]
            fig2 = go.Figure()
            fig2.add_trace(go.Bar(
                y=names[::-1], x=cnts[::-1],
                orientation='h',
                marker=dict(
                    color=['#4f46e5', '#6366f1', '#818cf8', '#a5b4fc', '#c7d2fe'][:len(names)][::-1],
                    cornerradius=4,
                ),
                hovertemplate='%{y}: %{x} mentions<extra></extra>',
            ))
            fig2.update_layout(
                height=300,
                margin=dict(l=10, r=10, t=10, b=10),
                plot_bgcolor='rgba(0,0,0,0)',
                paper_bgcolor='rgba(0,0,0,0)',
                xaxis=dict(showgrid=True, gridcolor='#f3f4f6', tickfont=dict(size=10, color='#9ca3af')),
                yaxis=dict(tickfont=dict(size=11, color='#1a1a2e', family='Inter')),
                hoverlabel=dict(bgcolor='#1a1a2e', font_color='white', font_size=12),
            )
            st.plotly_chart(fig2, width="stretch", config={"displayModeBar": False})
        else:
            st.caption("No merchant data extracted yet. Merchants are identified from email bodies.")
        st.markdown('</div>', unsafe_allow_html=True)

    st.markdown("")

    # ════════════════════════════════════════════════════
    # ROW 3: AGENT PERFORMANCE
    # ════════════════════════════════════════════════════
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

    # ── Category Performance Leaderboard ──
    cat_perf = metrics.get("category_performance", [])
    if cat_perf:
        st.markdown('<div class="chart-card">', unsafe_allow_html=True)
        st.markdown(chart_title_inner("trophy", "#f59e0b", "Category Performance Leaderboard"), unsafe_allow_html=True)
        st.markdown(category_table(cat_perf, _fmt_hours), unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)

    st.markdown("")

    # ── Bottom row: Priority Distribution + Status Overview ──
    st.markdown(chart_title_html("pie-chart", "#4f46e5", "DISTRIBUTION OVERVIEW"), unsafe_allow_html=True)
    d1, d2, d3 = st.columns(3)

    # Priority donut
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
            st.plotly_chart(fig_p, width="stretch", config={"displayModeBar": False})
        else:
            st.caption("No unresolved tickets.")
        st.markdown('</div>', unsafe_allow_html=True)

    # Category donut
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
            st.plotly_chart(fig_c, width="stretch", config={"displayModeBar": False})
        else:
            st.caption("No tickets yet.")
        st.markdown('</div>', unsafe_allow_html=True)

    # Status donut
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
            st.plotly_chart(fig_s, width="stretch", config={"displayModeBar": False})
        else:
            st.caption("No tickets yet.")
        st.markdown('</div>', unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════
#  PAGE: INBOX  (with Search + Category Tabs + Blue Dot)
# ══════════════════════════════════════════════════════════
elif st.session_state.tab == "inbox":
    st.markdown(top_bar("Inbox"), unsafe_allow_html=True)

    # ── Working Search Box (live / keystroke filtering) ──
    def _on_search_change():
        st.session_state.search_query = st.session_state.search_input

    search_query = st.text_input(
        "Search",
        value=st.session_state.search_query,
        placeholder="Search by keyword, subject, sender, email, category, amount…",
        key="search_input",
        label_visibility="collapsed",
        on_change=_on_search_change,
    )
    st.session_state.search_query = search_query

    # ── Load external JS for live search debounce ──
    _js_path = _DIR / "static" / "script.js"
    with open(_js_path, encoding="utf-8") as f:
        st.markdown(f"<script>{f.read()}</script>", unsafe_allow_html=True)

    # ── Auto-mark selected ticket as read ──
    sel_id = st.session_state.sel
    if sel_id and sel_id not in st.session_state.read_ids:
        _api_mark_read(sel_id)
        st.session_state.read_ids.add(sel_id)

    # ── Apply search filter ──
    display_tickets = [t for t in tickets if _search_match(t, search_query)]

    if search_query:
        st.markdown(
            alert_bar("ab-blue", "search", "#2563eb",
                      f'Found <b>{len(display_tickets)}</b> result(s) for "<b>{search_query}</b>"'),
            unsafe_allow_html=True,
        )

    # ── Email row renderer (shared by all tabs) ──
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

    # ── Email list renderer ──
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

    # ── Split into tabs ──
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
