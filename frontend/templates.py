"""
Finance Support Triage Agent — HTML Templates
All reusable HTML fragments and template builders extracted from app.py.
"""


# ═══════════════════════════════════════════════════════
#  SVG ICON SYSTEM  (Lucide / Heroicons-style strokes)
# ═══════════════════════════════════════════════════════
_SVG_PATHS: dict[str, str] = {
    # ── Priority ──
    "alert-triangle":   '<path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L12.71 3.86a2 2 0 00-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/>',
    "clock":            '<circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>',
    "check-circle":     '<path d="M22 11.08V12a10 10 0 11-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/>',
    "circle-dot":       '<circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r="1"/>',
    # ── Status / Actions ──
    "shield-alert":     '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/>',
    "shield-check":     '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><polyline points="9 12 11 14 15 10"/>',
    "mail":             '<path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z"/><polyline points="22,6 12,13 2,6"/>',
    "mail-open":        '<path d="M21.2 8.4c.5.38.8.97.8 1.6v10a2 2 0 01-2 2H4a2 2 0 01-2-2V10a2 2 0 01.8-1.6l8-6a2 2 0 012.4 0l8 6z"/><polyline points="22 10 12 17 2 10"/>',
    "inbox":            '<polyline points="22 12 16 12 14 15 10 15 8 12 2 12"/><path d="M5.45 5.11L2 12v6a2 2 0 002 2h16a2 2 0 002-2v-6l-3.45-6.89A2 2 0 0016.76 4H7.24a2 2 0 00-1.79 1.11z"/>',
    "send":             '<line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/>',
    "check":            '<polyline points="20 6 9 17 4 12"/>',
    "x-circle":         '<circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/>',
    "trash-2":          '<polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2"/><line x1="10" y1="11" x2="10" y2="17"/><line x1="14" y1="11" x2="14" y2="17"/>',
    "arrow-left":       '<line x1="19" y1="12" x2="5" y2="12"/><polyline points="12 19 5 12 12 5"/>',
    "reply":            '<polyline points="9 17 4 12 9 7"/><path d="M20 18v-2a4 4 0 00-4-4H4"/>',
    "corner-up-right":  '<polyline points="15 14 20 9 15 4"/><path d="M4 20v-7a4 4 0 014-4h12"/>',
    "refresh-cw":       '<polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/><path d="M3.51 9a9 9 0 0114.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0020.49 15"/>',
    # ── Navigation ──
    "bar-chart-2":      '<line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/>',
    "zap":              '<polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/>',
    "tag":              '<path d="M20.59 13.41l-7.17 7.17a2 2 0 01-2.83 0L2 12V2h10l8.59 8.59a2 2 0 010 2.82z"/><line x1="7" y1="7" x2="7.01" y2="7"/>',
    "bell":             '<path d="M18 8A6 6 0 006 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 01-3.46 0"/>',
    "search":           '<circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>',
    # ── Category ──
    "credit-card":      '<rect x="1" y="4" width="22" height="16" rx="2" ry="2"/><line x1="1" y1="10" x2="23" y2="10"/>',
    "file-text":        '<path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/><polyline points="10 9 9 9 8 9"/>',
    # ── Finance / Metrics ──
    "dollar-sign":      '<line x1="12" y1="1" x2="12" y2="23"/><path d="M17 5H9.5a3.5 3.5 0 000 7h5a3.5 3.5 0 010 7H6"/>',
    "trending-up":      '<polyline points="23 6 13.5 15.5 8.5 10.5 1 18"/><polyline points="17 6 23 6 23 12"/>',
    "activity":         '<polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/>',
    "pie-chart":        '<path d="M21.21 15.89A10 10 0 118 2.83"/><path d="M22 12A10 10 0 0012 2v10z"/>',
    "building":         '<rect x="4" y="2" width="16" height="20" rx="2" ry="2"/><path d="M9 22v-4h6v4"/><path d="M8 6h.01"/><path d="M16 6h.01"/><path d="M12 6h.01"/><path d="M12 10h.01"/><path d="M12 14h.01"/><path d="M16 10h.01"/><path d="M16 14h.01"/><path d="M8 10h.01"/><path d="M8 14h.01"/>',
    "trophy":           '<path d="M6 9H4.5a2.5 2.5 0 010-5H6"/><path d="M18 9h1.5a2.5 2.5 0 000-5H18"/><path d="M4 22h16"/><path d="M10 22V8a6 6 0 00-6-6"/><path d="M14 22V8a6 6 0 016-6"/>',
    "brain":            '<path d="M9.5 2A2.5 2.5 0 0112 4.5v15a2.5 2.5 0 01-4.96.44A2.5 2.5 0 015 17.5a2.5 2.5 0 01.49-4.78A2.5 2.5 0 014 10a2.5 2.5 0 013.92-2.06A2.5 2.5 0 019.5 2z"/><path d="M14.5 2A2.5 2.5 0 0012 4.5v15a2.5 2.5 0 004.96.44A2.5 2.5 0 0019 17.5a2.5 2.5 0 00-.49-4.78A2.5 2.5 0 0020 10a2.5 2.5 0 00-3.92-2.06A2.5 2.5 0 0014.5 2z"/>',
    "timer":            '<circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12"/><path d="M9 1h6"/>',
    "lock":             '<rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0110 0v4"/>',
    "eye":              '<path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/>',
    "clipboard":        '<path d="M16 4h2a2 2 0 012 2v14a2 2 0 01-2 2H6a2 2 0 01-2-2V6a2 2 0 012-2h2"/><rect x="8" y="2" width="8" height="4" rx="1" ry="1"/>',
    "lightbulb":        '<path d="M9 18h6"/><path d="M10 22h4"/><path d="M15.09 14c.18-.98.65-1.74 1.41-2.5A4.65 4.65 0 0018 8 6 6 0 006 8c0 1 .23 2.23 1.5 3.5A4.61 4.61 0 018.91 14"/>',
    "download":         '<path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/>',
    "book-open":        '<path d="M2 3h6a4 4 0 014 4v14a3 3 0 00-3-3H2z"/><path d="M22 3h-6a4 4 0 00-4 4v14a3 3 0 013-3h7z"/>',
    "sliders":          '<line x1="4" y1="21" x2="4" y2="14"/><line x1="4" y1="10" x2="4" y2="3"/><line x1="12" y1="21" x2="12" y2="12"/><line x1="12" y1="8" x2="12" y2="3"/><line x1="20" y1="21" x2="20" y2="16"/><line x1="20" y1="12" x2="20" y2="3"/><line x1="1" y1="14" x2="7" y2="14"/><line x1="9" y1="8" x2="15" y2="8"/><line x1="17" y1="16" x2="23" y2="16"/>',
    "pin":              '<path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0118 0z"/><circle cx="12" cy="10" r="3"/>',
    "edit-3":           '<path d="M12 20h9"/><path d="M16.5 3.5a2.121 2.121 0 013 3L7 19l-4 1 1-4L16.5 3.5z"/>',
    "user":             '<path d="M20 21v-2a4 4 0 00-4-4H8a4 4 0 00-4 4v2"/><circle cx="12" cy="7" r="4"/>',
    "hash":             '<line x1="4" y1="9" x2="20" y2="9"/><line x1="4" y1="15" x2="20" y2="15"/><line x1="10" y1="3" x2="8" y2="21"/><line x1="16" y1="3" x2="14" y2="21"/>',
    # ── Sentiment ──
    "frown":            '<circle cx="12" cy="12" r="10"/><path d="M16 16s-1.5-2-4-2-4 2-4 2"/><line x1="9" y1="9" x2="9.01" y2="9"/><line x1="15" y1="9" x2="15.01" y2="9"/>',
    "meh":              '<circle cx="12" cy="12" r="10"/><line x1="8" y1="15" x2="16" y2="15"/><line x1="9" y1="9" x2="9.01" y2="9"/><line x1="15" y1="9" x2="15.01" y2="9"/>',
    "smile":            '<circle cx="12" cy="12" r="10"/><path d="M8 14s1.5 2 4 2 4-2 4-2"/><line x1="9" y1="9" x2="9.01" y2="9"/><line x1="15" y1="9" x2="15.01" y2="9"/>',
    # ── Misc ──
    "info":             '<circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/>',
    "alert-circle":     '<circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/>',
    "chevron-right":    '<polyline points="9 18 15 12 9 6"/>',
    "external-link":    '<path d="M18 13v6a2 2 0 01-2 2H5a2 2 0 01-2-2V8a2 2 0 012-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/>',
    "mail-x":           '<path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z"/><polyline points="22,6 12,13 2,6"/><line x1="16" y1="16" x2="22" y2="10"/>',
    "plug":             '<path d="M12 22v-5"/><path d="M9 8V1"/><path d="M15 8V1"/><path d="M18 8v5a6 6 0 01-12 0V8z"/>',
    "help-circle":      '<circle cx="12" cy="12" r="10"/><path d="M9.09 9a3 3 0 015.83 1c0 2-3 3-3 3"/><line x1="12" y1="17" x2="12.01" y2="17"/>',
    "fire":             '<path d="M8.5 14.5A2.5 2.5 0 0011 12c0-1.38-.5-2-1-3-1.072-2.143-.224-4.054 2-6 .5 2.5 2 4.9 4 6.5 2 1.6 3 3.5 3 5.5a7 7 0 11-14 0c0-1.153.433-2.294 1-3a2.5 2.5 0 002.5 2.5z"/>',
}


# ═══════════════════════════════════════════════════════
#  ICON HELPER
# ═══════════════════════════════════════════════════════
def icon(name: str, color: str = "#6b7280", size: int = 20) -> str:
    """Return an inline SVG icon as an HTML string.  Lucide-style strokes."""
    paths = _SVG_PATHS.get(name, _SVG_PATHS["info"])
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" '
        f'viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2" '
        f'stroke-linecap="round" stroke-linejoin="round" '
        f'style="vertical-align:middle;flex-shrink:0;display:inline-block;">'
        f'{paths}</svg>'
    )


# ═══════════════════════════════════════════════════════
#  AVATAR HELPERS
# ═══════════════════════════════════════════════════════
_AV_COLORS = [
    "av-red", "av-blue", "av-green", "av-purple",
    "av-orange", "av-pink", "av-teal", "av-indigo",
]


def _initials(name: str) -> str:
    parts = name.strip().split()
    if len(parts) >= 2:
        return (parts[0][0] + parts[-1][0]).upper()
    return name[:2].upper() if name else "?"


def _av_color(name: str) -> str:
    return _AV_COLORS[hash(name) % len(_AV_COLORS)]


def avatar(name: str) -> str:
    return f'<div class="avatar {_av_color(name)}">{_initials(name)}</div>'


# ═══════════════════════════════════════════════════════
#  BADGE BUILDERS
# ═══════════════════════════════════════════════════════
def pri_badge(p: str) -> str:
    c = {"High": "b-high", "Medium": "b-medium", "Low": "b-low"}.get(p, "b-low")
    ic = {
        "High": icon("alert-triangle", "#dc2626", 14),
        "Medium": icon("clock", "#d97706", 14),
        "Low": icon("check-circle", "#16a34a", 14),
    }
    return f'<span class="badge {c}">{ic.get(p, icon("info", "#6b7280", 14))} {p}</span>'


def cat_badge(c: str) -> str:
    cls = {"Fraud": "b-fraud", "Payment Issue": "b-payment"}.get(c, "b-general")
    ic = {
        "Fraud": icon("shield-alert", "#dc2626", 14),
        "Payment Issue": icon("credit-card", "#2563eb", 14),
        "General": icon("file-text", "#6b7280", 14),
    }
    return f'<span class="badge {cls}">{ic.get(c, icon("file-text", "#6b7280", 14))} {c}</span>'


def sent_badge(s: str) -> str:
    cls = {"Negative": "b-neg", "Neutral": "b-neu", "Positive": "b-pos", "Urgent": "b-neg"}.get(s, "b-neu")
    ic = {
        "Negative": icon("frown", "#dc2626", 14),
        "Neutral": icon("meh", "#6b7280", 14),
        "Positive": icon("smile", "#16a34a", 14),
        "Urgent": icon("alert-triangle", "#dc2626", 14),
    }
    return f'<span class="badge {cls}">{ic.get(s, icon("help-circle", "#6b7280", 14))} {s or "Neutral"}</span>'


def tag_html(cat: str) -> str:
    cls = {"Fraud": "tag-fraud", "Payment Issue": "tag-payment"}.get(cat, "tag-general")
    return f'<span class="eml-tag {cls}">{cat}</span>'


# ═══════════════════════════════════════════════════════
#  LAYOUT HTML BUILDERS
# ═══════════════════════════════════════════════════════
def top_bar(title: str) -> str:
    return (
        '<div class="top-bar">'
        '<div class="top-logo"><div class="top-logo-icon">FT</div>'
        f'<span>{title}</span></div></div>'
    )


def sidebar_header() -> str:
    return (
        '<div style="display:flex;align-items:center;gap:10px;padding:6px 0 2px;">'
        '<div class="avatar av-indigo" style="width:34px;height:34px;font-size:.72rem;">FT</div>'
        "<div>"
        '<div style="font-size:.72rem;color:#9ca3af !important;">Welcome</div>'
        '<div style="font-size:.88rem;font-weight:700;color:#1a1a2e !important;">Finance Triage</div>'
        "</div></div>"
    )


def nav_icon_cell(icon_name: str, is_active: bool) -> str:
    clr = "#4f46e5" if is_active else "#6b7280"
    return (
        f'<div style="display:flex;align-items:center;justify-content:center;height:38px;">'
        f'{icon(icon_name, clr, 18)}</div>'
    )


def fetch_how_it_works() -> str:
    return (
        '<div class="fetch-card">'
        '<div style="display:flex;gap:12px;align-items:flex-start;">'
        f'<span style="font-size:1.2rem;">{icon("lightbulb", "#f59e0b", 22)}</span>'
        "<div>"
        '<div style="font-weight:700;color:#1a1a2e;margin-bottom:3px;font-size:.92rem;">How it works</div>'
        '<div style="color:#6b7280;font-size:.82rem;line-height:1.8;">'
        "1. Click <b>Fetch Emails</b> below<br/>"
        "2. Connects to your Gmail inbox via IMAP<br/>"
        "3. Fetches emails from the <b>last 2 days</b><br/>"
        "4. Emails are analysed by AI (Groq Llama 3.3)<br/>"
        "5. Tickets created and sorted by urgency — duplicates auto-skipped"
        "</div></div></div></div>"
    )


def alert_bar(style: str, icon_name: str, icon_color: str, content: str) -> str:
    return (
        f'<div class="alert-bar {style}"><span class="ab-icon">'
        f'{icon(icon_name, icon_color, 18)}</span>'
        f'<div class="ab-text">{content}</div></div>'
    )


def detail_actions() -> str:
    return (
        '<div class="detail-actions">'
        f'<span class="action-btn"><span class="action-icon">{icon("reply", "#6b7280", 15)}</span> Reply</span>'
        f'<span class="action-btn"><span class="action-icon">{icon("reply", "#6b7280", 15)}</span> Reply All</span>'
        f'<span class="action-btn"><span class="action-icon">{icon("corner-up-right", "#6b7280", 15)}</span> Forward</span>'
        f'<span class="action-btn"><span class="action-icon">{icon("trash-2", "#6b7280", 15)}</span> Delete</span>'
        "</div>"
    )


def detail_header(subject: str, sender: str, time: str, priority: str, category: str, status: str) -> str:
    return (
        f'<div class="detail-subject-line">{subject}</div>'
        f'<div class="detail-from">{avatar(sender)}<div>'
        f'<div class="detail-from-name">{sender}</div>'
        f'<div class="detail-from-time">{time}</div></div>'
        f'<div style="margin-left:auto;display:flex;gap:5px;flex-wrap:wrap;">'
        f'{pri_badge(priority)} {cat_badge(category)} '
        f'<span class="badge b-status">{icon("pin", "#4f46e5", 13)} {status}</span>'
        f"</div></div>"
    )


def insight_grid(category: str, sentiment: str, intent: str, amount: str) -> str:
    return (
        f'<div class="insight-grid">'
        f'<div class="insight-box"><div class="insight-label">Category</div>{cat_badge(category)}</div>'
        f'<div class="insight-box"><div class="insight-label">Sentiment</div>{sent_badge(sentiment)}</div>'
        f'<div class="insight-box"><div class="insight-label">Intent</div><div class="insight-value">{intent}</div></div>'
        f'<div class="insight-box"><div class="insight-label">Amount</div><div class="insight-value">{amount}</div></div>'
        f"</div>"
    )


def email_row(sender: str, subject: str, preview: str, priority: str, category: str,
              time: str, is_read: bool, selected: bool) -> str:
    row_cls = "selected" if selected else ("is-read" if is_read else "")
    pd_cls = {"High": "pd-high", "Medium": "pd-medium", "Low": "pd-low"}.get(priority, "pd-low")
    sender_style = "" if not is_read else "font-weight:400;color:#6b7280;"
    subject_style = "font-weight:700;" if not is_read else "font-weight:400;color:#6b7280;"
    dot_html = '<div class="unread-dot"></div>' if not is_read else '<div class="read-dot"></div>'

    return (
        f'<div class="eml-row {row_cls}">'
        f'{avatar(sender)}'
        f'<div class="eml-meta">'
        f'<div class="eml-sender" style="{sender_style}"><span class="p-dot {pd_cls}"></span>{sender}</div>'
        f'<div class="eml-subject" style="{subject_style}">{subject}</div>'
        f'<div class="eml-preview">{preview}</div></div>'
        f'<div class="eml-right">'
        f'<div class="eml-time">{time}</div>'
        f'{tag_html(category)}</div>'
        f'{dot_html}'
        f'</div>'
    )


def welcome_empty(message: str = "No tickets here",
                   sub: str = "Tickets matching this filter will appear here.") -> str:
    return (
        f'<div class="welcome"><div class="welcome-icon">{icon("mail-open", "#9ca3af", 44)}</div>'
        f'<div class="welcome-title">{message}</div>'
        f'<div class="welcome-sub">{sub}</div></div>'
    )


def queue_section_header(icon_html: str, title: str, count: int, qc_class: str) -> str:
    return (
        f'<div class="queue-sec"><div class="queue-hdr">'
        f'<span style="font-size:1rem;">{icon_html}</span>'
        f'<span class="queue-title">{title}</span>'
        f'<span class="queue-cnt {qc_class}">{count}</span>'
        f"</div></div>"
    )


def section_header(icon_name: str, text: str) -> str:
    return f'<div class="section-hdr">{icon(icon_name, "#4f46e5", 15)} {text}</div>'


def chart_title_html(icon_name: str, icon_color: str, text: str) -> str:
    return f'<div class="chart-title" style="margin-bottom:8px;">{icon(icon_name, icon_color, 18)} {text}</div>'


def analytics_card(color_class: str, icon_name: str, icon_color: str,
                    label: str, value: str, sub: str, extra_style: str = "") -> str:
    return (
        f'<div class="a-card {color_class}">'
        f'<div class="a-card-icon">{icon(icon_name, icon_color, 26)}</div>'
        f'<div class="a-card-label">{label}</div>'
        f'<div class="a-card-num" style="{extra_style}">{value}</div>'
        f'<div class="a-card-sub">{sub}</div>'
        f'</div>'
    )


def sla_breach_row(customer: str, category: str, hours: float, amount: str) -> str:
    return (
        f'<div class="alert-bar ab-red">'
        f'<span class="ab-icon">{icon("clock", "#dc2626", 18)}</span>'
        f'<div class="ab-text">'
        f'<b>{customer}</b> — {category} — '
        f'Open for <b>{hours:.1f}h</b> — Amount: {amount}'
        f'</div></div>'
    )


def chart_title_inner(icon_name: str, icon_color: str, text: str) -> str:
    return f'<div class="chart-title">{icon(icon_name, icon_color, 16)} {text}</div>'


def category_table(cat_perf: list, fmt_hours_fn) -> str:
    """Build the category performance leaderboard HTML table."""
    cat_icons = {
        "Fraud": icon("shield-alert", "#dc2626", 15),
        "Payment Issue": icon("credit-card", "#2563eb", 15),
        "General": icon("file-text", "#6b7280", 15),
    }
    table_html = (
        '<table style="width:100%;border-collapse:collapse;font-size:.84rem;">'
        '<thead><tr style="border-bottom:2px solid #e5e7eb;text-align:left;">'
        '<th style="padding:10px 12px;font-weight:700;color:#6b7280;font-size:.68rem;text-transform:uppercase;letter-spacing:.5px;">Category</th>'
        '<th style="padding:10px 12px;font-weight:700;color:#6b7280;font-size:.68rem;text-transform:uppercase;letter-spacing:.5px;">Total</th>'
        '<th style="padding:10px 12px;font-weight:700;color:#6b7280;font-size:.68rem;text-transform:uppercase;letter-spacing:.5px;">Closed</th>'
        '<th style="padding:10px 12px;font-weight:700;color:#6b7280;font-size:.68rem;text-transform:uppercase;letter-spacing:.5px;">Avg Resolution</th>'
        '<th style="padding:10px 12px;font-weight:700;color:#6b7280;font-size:.68rem;text-transform:uppercase;letter-spacing:.5px;">Reopen Rate</th>'
        '</tr></thead><tbody>'
    )
    for cp in cat_perf:
        cat_name = cp.get("category", "")
        ic = cat_icons.get(cat_name, icon("file-text", "#6b7280", 15))
        reopen_rate = cp.get("reopen_rate", 0)
        reopen_color = "#dc2626" if reopen_rate > 10 else ("#d97706" if reopen_rate > 5 else "#22c55e")
        avg_h = cp.get("avg_resolution_h", 0)
        table_html += (
            f'<tr style="border-bottom:1px solid #f3f4f6;">'
            f'<td style="padding:12px;font-weight:600;color:#1a1a2e;">{ic} {cat_name}</td>'
            f'<td style="padding:12px;font-weight:700;color:#1a1a2e;">{cp.get("total", 0)}</td>'
            f'<td style="padding:12px;color:#22c55e;font-weight:600;">{cp.get("closed", 0)}</td>'
            f'<td style="padding:12px;color:#6b7280;">{fmt_hours_fn(avg_h)}</td>'
            f'<td style="padding:12px;font-weight:700;color:{reopen_color};">{reopen_rate:.1f}%</td>'
            f'</tr>'
        )
    table_html += '</tbody></table>'
    return table_html


def alert_ticket_card(sender: str, subject: str, summary: str,
                       priority: str, category: str, sentiment: str,
                       time: str, reasons: list) -> str:
    return (
        f'<div class="queue-sec" style="border-left:3px solid #ef4444;">'
        f'<div style="display:flex;gap:14px;align-items:center;">'
        f'{avatar(sender)}'
        f'<div style="flex:1;min-width:0;">'
        f'<div style="font-weight:700;color:#1a1a2e;font-size:.88rem;">{sender}</div>'
        f'<div style="color:#6b7280;font-size:.82rem;margin-top:1px;">{subject}</div>'
        f'<div style="color:#9ca3af;font-size:.76rem;margin-top:2px;">{summary[:100]}</div>'
        f'<div style="margin-top:6px;display:flex;gap:5px;flex-wrap:wrap;">'
        f'{pri_badge(priority)} {cat_badge(category)} {sent_badge(sentiment)}</div></div>'
        f'<div style="text-align:right;">'
        f'<div style="font-size:.68rem;color:#9ca3af;">{time}</div>'
        f'<div style="font-size:.64rem;color:#dc2626;font-weight:600;margin-top:3px;">'
        f'{"  •  ".join(reasons)}</div>'
        f"</div></div></div>"
    )
