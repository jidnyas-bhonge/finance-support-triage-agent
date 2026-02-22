"""
Finance Support Triage Agent — Professional Dashboard + Email Client
Analytics · Categorised Inbox · Blue-dot Read/Unread · Live Search
"""

import streamlit as st
from streamlit_autorefresh import st_autorefresh
import requests
import re
import os
import time as _time
from datetime import datetime, timedelta
from collections import Counter
import plotly.graph_objects as go
import plotly.express as px

# ═══════════════════════════════════════════════════════
#  CONFIG
# ═══════════════════════════════════════════════════════
API = os.environ.get("API_BASE_URL", "http://127.0.0.1:8000")

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
#  GLOBAL CSS
# ═══════════════════════════════════════════════════════
st.markdown(
    """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap');
@import url('https://fonts.googleapis.com/icon?family=Material+Icons+Outlined');

/* ─── Reset ─── */
header[data-testid="stHeader"]                               { background:#f8f9fb !important; }
[data-testid="stToolbar"], [data-testid="stDecoration"],
#MainMenu, footer                                            { display:none !important; }
[data-testid="collapsedControl"],
button[data-testid="stSidebarCollapseButton"],
button[data-testid="stSidebarNavCollapseButton"]             { display:none !important; }

/* ─── Sidebar ─── */
section[data-testid="stSidebar"] {
    transform:none !important;
    min-width:250px !important; width:250px !important;
    visibility:visible !important; display:flex !important;
    background:#ffffff !important;
    border-right:1px solid #e5e7eb !important;
    box-shadow:2px 0 8px rgba(0,0,0,.03) !important;
}
section[data-testid="stSidebar"] > div { overflow-y:auto; }
section[data-testid="stSidebar"] * { color:#6b7280 !important; }
section[data-testid="stSidebar"] .stMarkdown h3 {
    color:#1a1a2e !important; font-weight:700 !important; font-size:.72rem !important;
    text-transform:uppercase; letter-spacing:.8px; margin-top:16px !important;
}
section[data-testid="stSidebar"] hr { border-color:#e5e7eb !important; margin:6px 0 !important; }
section[data-testid="stSidebar"] .stButton>button {
    background:#fff !important; border:1px solid #e5e7eb !important;
    color:#6b7280 !important; border-radius:10px !important;
    font-weight:500 !important; font-size:.82rem !important;
    transition:all .15s ease !important; text-align:left !important;
}
section[data-testid="stSidebar"] .stButton>button:hover {
    background:#f3f4f6 !important; border-color:#d1d5db !important;
}
section[data-testid="stSidebar"] [data-testid="stMetric"] {
    background:#f8f9fb; border:1px solid #e5e7eb;
    border-radius:10px; padding:10px 8px;
}
section[data-testid="stSidebar"] [data-testid="stMetricLabel"] {
    font-size:.58rem !important; font-weight:700 !important;
    text-transform:uppercase; letter-spacing:.5px; color:#9ca3af !important;
}
section[data-testid="stSidebar"] [data-testid="stMetricValue"] {
    font-weight:700 !important; color:#1a1a2e !important; font-size:1.2rem !important;
}

/* ─── Global ─── */
html, body, .stApp {
    font-family:'Inter',-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif !important;
    background:#f8f9fb !important; color:#1a1a2e !important;
}
.block-container { padding:1rem 1.5rem !important; max-width:1800px; }

/* ─── Top Bar ─── */
.top-bar {
    display:flex; align-items:center; gap:14px; padding:10px 0 14px;
}
.top-logo { display:flex; align-items:center; gap:9px; font-size:1.15rem; font-weight:800; color:#1a1a2e; }
.top-logo-icon {
    width:34px; height:34px; border-radius:9px;
    background:linear-gradient(135deg,#4f46e5,#7c3aed);
    display:flex; align-items:center; justify-content:center;
    color:#fff; font-size:.82rem; font-weight:800;
}

/* ─── Analytics Cards ─── */
.a-card {
    background:#fff; border:1px solid #e5e7eb; border-radius:14px;
    padding:20px; position:relative; overflow:hidden;
    box-shadow:0 1px 4px rgba(0,0,0,.04); transition:all .15s ease;
}
.a-card:hover { transform:translateY(-2px); box-shadow:0 6px 16px rgba(0,0,0,.07); }
.a-card::before { content:''; position:absolute; top:0; left:0; right:0; height:3px; }
.ac-indigo::before { background:linear-gradient(90deg,#4f46e5,#7c3aed); }
.ac-red::before    { background:#ef4444; }
.ac-amber::before  { background:#f59e0b; }
.ac-green::before  { background:#22c55e; }
.ac-blue::before   { background:#3b82f6; }
.ac-purple::before { background:#8b5cf6; }
.a-card-label {
    font-size:.62rem; font-weight:700; text-transform:uppercase;
    letter-spacing:.7px; color:#9ca3af; margin-bottom:6px;
}
.a-card-num { font-size:1.9rem; font-weight:800; color:#1a1a2e; line-height:1; }
.a-card-sub { font-size:.72rem; color:#6b7280; margin-top:4px; }
.a-card-icon {
    position:absolute; top:14px; right:16px;
    font-size:1.6rem; opacity:.15;
}

/* ─── Chart Section ─── */
.chart-card {
    background:#fff; border:1px solid #e5e7eb; border-radius:14px;
    padding:20px 22px; box-shadow:0 1px 4px rgba(0,0,0,.04);
}
.chart-title {
    font-size:.76rem; font-weight:700; color:#1a1a2e;
    text-transform:uppercase; letter-spacing:.5px; margin-bottom:14px;
}
.bar-row { display:flex; align-items:center; gap:10px; margin-bottom:8px; }
.bar-label { font-size:.74rem; font-weight:600; color:#6b7280; min-width:90px; }
.bar-track { flex:1; height:22px; background:#f3f4f6; border-radius:6px; overflow:hidden; }
.bar-fill {
    height:100%; border-radius:6px; display:flex; align-items:center;
    padding-left:8px; font-size:.64rem; font-weight:700; color:#fff;
    transition:width .3s ease;
}
.bar-count { font-size:.72rem; font-weight:700; color:#1a1a2e; min-width:28px; text-align:right; }

/* ─── Donut legend ─── */
.legend-item {
    display:flex; align-items:center; gap:8px; padding:6px 0;
    border-bottom:1px solid #f3f4f6;
}
.legend-dot { width:10px; height:10px; border-radius:50%; flex-shrink:0; }
.legend-label { font-size:.78rem; color:#6b7280; flex:1; }
.legend-val { font-size:.82rem; font-weight:700; color:#1a1a2e; }
.legend-pct { font-size:.68rem; color:#9ca3af; min-width:38px; text-align:right; }

/* ─── Email List ─── */
.email-list {
    background:#fff; border:1px solid #e5e7eb;
    border-radius:12px; overflow:hidden;
    box-shadow:0 1px 3px rgba(0,0,0,.04);
}
.date-group {
    font-size:.68rem; font-weight:700; color:#9ca3af;
    text-transform:uppercase; letter-spacing:.7px;
    padding:10px 18px 6px; background:#fafbfc;
    border-bottom:1px solid #f3f4f6;
}
.eml-row {
    display:grid; grid-template-columns:42px 1fr auto 16px;
    align-items:center; gap:12px;
    padding:13px 18px; border-bottom:1px solid #f3f4f6;
    cursor:pointer; transition:background .1s ease;
}
.eml-row:hover { background:#f8f9fb; }
.eml-row.selected { background:#eef2ff; border-left:3px solid #4f46e5; }
.eml-row.is-read .eml-sender, .eml-row.is-read .eml-subject { font-weight:400; color:#6b7280; }

/* ─── Avatar ─── */
.avatar {
    width:38px; height:38px; border-radius:50%;
    display:flex; align-items:center; justify-content:center;
    font-weight:700; font-size:.78rem; color:#fff; flex-shrink:0;
}
.av-red    { background:#ef4444; }
.av-blue   { background:#3b82f6; }
.av-green  { background:#22c55e; }
.av-purple { background:#8b5cf6; }
.av-orange { background:#f97316; }
.av-pink   { background:#ec4899; }
.av-teal   { background:#14b8a6; }
.av-indigo { background:#6366f1; }

.eml-meta { min-width:0; overflow:hidden; }
.eml-sender {
    font-size:.84rem; font-weight:600; color:#1a1a2e;
    white-space:nowrap; overflow:hidden; text-overflow:ellipsis;
}
.eml-subject {
    font-size:.82rem; font-weight:600; color:#1a1a2e;
    white-space:nowrap; overflow:hidden; text-overflow:ellipsis; margin-top:1px;
}
.eml-preview {
    font-size:.77rem; color:#9ca3af; font-weight:400;
    white-space:nowrap; overflow:hidden; text-overflow:ellipsis; margin-top:1px;
}
.eml-right {
    text-align:right; white-space:nowrap;
    display:flex; flex-direction:column; align-items:flex-end; gap:4px;
}
.eml-time { font-size:.68rem; color:#9ca3af; }
.eml-tag {
    display:inline-flex; padding:2px 8px; border-radius:4px;
    font-size:.6rem; font-weight:700; letter-spacing:.3px;
}
.tag-fraud   { background:#fef2f2; color:#dc2626; }
.tag-payment { background:#eff6ff; color:#2563eb; }
.tag-general { background:#f3f4f6; color:#6b7280; }

/* ─── Blue Unread Dot ─── */
.unread-dot {
    width:9px; height:9px; border-radius:50%; background:#3b82f6;
    flex-shrink:0; box-shadow:0 0 0 2px rgba(59,130,246,.25);
}
.read-dot { width:9px; height:9px; flex-shrink:0; }

/* ─── Priority Dot ─── */
.p-dot { width:7px; height:7px; border-radius:50%; display:inline-block; margin-right:5px; }
.pd-high   { background:#ef4444; }
.pd-medium { background:#f59e0b; }
.pd-low    { background:#22c55e; }

/* ─── Detail Panel ─── */
.detail-card {
    background:#fff; border:1px solid #e5e7eb;
    border-radius:12px; padding:24px 28px;
    box-shadow:0 1px 4px rgba(0,0,0,.04);
}
.detail-actions {
    display:flex; gap:14px; align-items:center;
    padding:10px 0; border-bottom:1px solid #e5e7eb; margin-bottom:18px;
}
.action-btn {
    display:inline-flex; align-items:center; gap:5px;
    font-size:.76rem; color:#6b7280; font-weight:500;
    cursor:pointer; padding:5px 10px; border-radius:6px;
    transition:all .1s ease; background:none; border:none;
}
.action-btn:hover { background:#f3f4f6; color:#1a1a2e; }
.action-icon { font-size:.92rem; }
.detail-from { display:flex; align-items:center; gap:14px; margin-bottom:18px; }
.detail-from-name { font-weight:700; color:#1a1a2e; font-size:.92rem; }
.detail-from-time { color:#9ca3af; font-size:.76rem; }
.detail-subject-line {
    font-size:1.2rem; font-weight:700; color:#1a1a2e;
    margin-bottom:18px; line-height:1.4;
}
.detail-body {
    color:#374151; font-size:.88rem; line-height:1.8;
    white-space:pre-wrap; padding:14px 0;
    border-top:1px solid #f3f4f6;
}

/* ─── Badges ─── */
.badge {
    display:inline-flex; align-items:center; gap:4px;
    padding:3px 10px; border-radius:14px;
    font-weight:600; font-size:.68rem; letter-spacing:.2px;
}
.b-high    { background:#fef2f2; color:#dc2626; }
.b-medium  { background:#fffbeb; color:#d97706; }
.b-low     { background:#f0fdf4; color:#16a34a; }
.b-fraud   { background:#fef2f2; color:#dc2626; }
.b-payment { background:#eff6ff; color:#2563eb; }
.b-general { background:#f3f4f6; color:#6b7280; }
.b-status  { background:#eef2ff; color:#4f46e5; }
.b-neg     { background:#fef2f2; color:#dc2626; }
.b-neu     { background:#f3f4f6; color:#6b7280; }
.b-pos     { background:#f0fdf4; color:#16a34a; }

/* ─── Insight Grid ─── */
.insight-grid { display:grid; grid-template-columns:repeat(4,1fr); gap:10px; margin:14px 0; }
.insight-box {
    background:#f8f9fb; border:1px solid #e5e7eb;
    border-radius:10px; padding:12px;
}
.insight-label {
    font-size:.58rem; font-weight:700; text-transform:uppercase;
    letter-spacing:.6px; color:#9ca3af; margin-bottom:5px;
}
.insight-value { font-size:.84rem; font-weight:600; color:#1a1a2e; }
.section-hdr {
    font-size:.72rem; font-weight:700; color:#4f46e5;
    text-transform:uppercase; letter-spacing:.7px;
    margin:18px 0 8px; padding-bottom:5px;
    border-bottom:2px solid #eef2ff; display:inline-block;
}

/* ─── Alert Bars ─── */
.alert-bar {
    display:flex; align-items:center; gap:10px;
    padding:11px 16px; border-radius:10px; margin-bottom:8px; font-size:.84rem;
}
.ab-red   { background:#fef2f2; border:1px solid #fecaca; color:#dc2626; }
.ab-amber { background:#fffbeb; border:1px solid #fde68a; color:#d97706; }
.ab-blue  { background:#eff6ff; border:1px solid #bfdbfe; color:#2563eb; }
.ab-green { background:#f0fdf4; border:1px solid #bbf7d0; color:#16a34a; }
.ab-icon  { font-size:1.15rem; }
.ab-text b { font-weight:700; }

/* ─── Queue Section ─── */
.queue-sec {
    background:#fff; border:1px solid #e5e7eb;
    border-radius:12px; padding:14px 16px;
    margin-bottom:10px; box-shadow:0 1px 3px rgba(0,0,0,.03);
}
.queue-hdr {
    display:flex; align-items:center; gap:8px;
    padding-bottom:8px; border-bottom:1px solid #f3f4f6; margin-bottom:8px;
}
.queue-title { font-size:.88rem; font-weight:700; color:#1a1a2e; }
.queue-cnt {
    margin-left:auto; font-size:.64rem; font-weight:700;
    padding:2px 9px; border-radius:10px;
}
.qc-r { background:#fef2f2; color:#dc2626; }
.qc-a { background:#fffbeb; color:#d97706; }
.qc-g { background:#f0fdf4; color:#16a34a; }

/* ─── Welcome ─── */
.welcome { text-align:center; padding:50px 20px; color:#9ca3af; }
.welcome-icon { font-size:2.8rem; margin-bottom:10px; display:block; }
.welcome-title { font-size:1.05rem; font-weight:700; color:#6b7280; margin-bottom:4px; }
.welcome-sub { font-size:.82rem; max-width:360px; margin:0 auto; line-height:1.6; }

/* ─── Fetch Page ─── */
.fetch-card {
    background:#fff; border:1px solid #e5e7eb;
    border-radius:12px; padding:22px 26px;
    box-shadow:0 1px 4px rgba(0,0,0,.04); margin-bottom:12px;
}

/* ─── Text Area / Inputs ─── */
.stTextArea textarea {
    background:#f8f9fb !important; border:1px solid #e5e7eb !important;
    border-radius:10px !important; color:#1a1a2e !important;
    font-family:'Inter',sans-serif !important;
    font-size:.86rem !important; line-height:1.7 !important;
}
.stTextArea textarea:focus {
    border-color:#4f46e5 !important;
    box-shadow:0 0 0 3px rgba(79,70,229,.08) !important;
}
.stTextInput input {
    background:#fff !important; border:1px solid #e5e7eb !important;
    border-radius:10px !important; font-size:.84rem !important;
    padding:10px 14px !important;
}
.stTextInput input:focus {
    border-color:#4f46e5 !important;
    box-shadow:0 0 0 3px rgba(79,70,229,.08) !important;
}

/* ─── Buttons ─── */
.stButton>button[kind="primary"] {
    background:#4f46e5 !important; border:none !important;
    border-radius:10px !important; font-weight:600 !important;
    padding:10px 22px !important; color:#fff !important;
    box-shadow:0 2px 8px rgba(79,70,229,.22) !important;
    transition:all .15s ease !important;
}
.stButton>button[kind="primary"]:hover {
    background:#4338ca !important;
    box-shadow:0 4px 14px rgba(79,70,229,.32) !important;
}
.stButton>button[kind="secondary"] {
    border-radius:10px !important; font-weight:500 !important;
    border-color:#e5e7eb !important; color:#6b7280 !important;
}
.stButton>button[kind="secondary"]:hover { background:#f3f4f6 !important; }

/* ─── Selectbox ─── */
.stSelectbox [data-baseweb="select"]>div {
    background:#f8f9fb !important; border-color:#e5e7eb !important;
    border-radius:8px !important; color:#1a1a2e !important;
}

/* ─── Metric ─── */
[data-testid="stMetric"] {
    background:#f8f9fb !important; border:1px solid #e5e7eb;
    border-radius:10px; padding:10px 8px;
}
[data-testid="stMetricLabel"]  { font-size:.58rem !important; color:#9ca3af !important; font-weight:700 !important; text-transform:uppercase !important; letter-spacing:.5px; }
[data-testid="stMetricValue"]  { font-weight:700 !important; color:#1a1a2e !important; }

/* ─── Scrollbar ─── */
::-webkit-scrollbar       { width:5px; }
::-webkit-scrollbar-track { background:transparent; }
::-webkit-scrollbar-thumb { background:#d1d5db; border-radius:3px; }

.stSpinner>div>div { border-top-color:#4f46e5 !important; }
.stAlert { border-radius:10px !important; }

/* ─── Tabs ─── */
.stTabs [data-baseweb="tab-list"] { gap:0; border-bottom:2px solid #e5e7eb; }
.stTabs [data-baseweb="tab"] {
    padding:10px 20px; font-weight:600; font-size:.82rem;
    color:#6b7280; border-bottom:2px solid transparent; margin-bottom:-2px;
}
.stTabs [aria-selected="true"] {
    color:#4f46e5 !important; border-bottom:2px solid #4f46e5 !important;
}
</style>
""",
    unsafe_allow_html=True,
)

# ═══════════════════════════════════════════════════════
#  AUTO-REFRESH
# ═══════════════════════════════════════════════════════
st_autorefresh(interval=30_000, limit=None, key="auto_refresh")

# ═══════════════════════════════════════════════════════
#  HELPERS
# ═══════════════════════════════════════════════════════
_AV_COLORS = [
    "av-red", "av-blue", "av-green", "av-purple",
    "av-orange", "av-pink", "av-teal", "av-indigo",
]
_PRI_ORDER = {"High": 0, "Medium": 1, "Low": 2}

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


def _icon(name: str, color: str = "#6b7280", size: int = 20) -> str:
    """Return an inline SVG icon as an HTML string.  Lucide-style strokes."""
    paths = _SVG_PATHS.get(name, _SVG_PATHS["info"])
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" '
        f'viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2" '
        f'stroke-linecap="round" stroke-linejoin="round" '
        f'style="vertical-align:middle;flex-shrink:0;display:inline-block;">'
        f'{paths}</svg>'
    )


def _initials(name: str) -> str:
    parts = name.strip().split()
    if len(parts) >= 2:
        return (parts[0][0] + parts[-1][0]).upper()
    return name[:2].upper() if name else "?"


def _av_color(name: str) -> str:
    return _AV_COLORS[hash(name) % len(_AV_COLORS)]


def _avatar(name: str) -> str:
    return f'<div class="avatar {_av_color(name)}">{_initials(name)}</div>'


def _pri_badge(p: str) -> str:
    c = {"High": "b-high", "Medium": "b-medium", "Low": "b-low"}.get(p, "b-low")
    ic = {"High": _icon("alert-triangle", "#dc2626", 14), "Medium": _icon("clock", "#d97706", 14), "Low": _icon("check-circle", "#16a34a", 14)}
    return f'<span class="badge {c}">{ic.get(p, _icon("info", "#6b7280", 14))} {p}</span>'


def _cat_badge(c: str) -> str:
    cls = {"Fraud": "b-fraud", "Payment Issue": "b-payment"}.get(c, "b-general")
    ic = {"Fraud": _icon("shield-alert", "#dc2626", 14), "Payment Issue": _icon("credit-card", "#2563eb", 14), "General": _icon("file-text", "#6b7280", 14)}
    return f'<span class="badge {cls}">{ic.get(c, _icon("file-text", "#6b7280", 14))} {c}</span>'


def _sent_badge(s: str) -> str:
    cls = {"Negative": "b-neg", "Neutral": "b-neu", "Positive": "b-pos", "Urgent": "b-neg"}.get(s, "b-neu")
    ic = {"Negative": _icon("frown", "#dc2626", 14), "Neutral": _icon("meh", "#6b7280", 14), "Positive": _icon("smile", "#16a34a", 14), "Urgent": _icon("alert-triangle", "#dc2626", 14)}
    return f'<span class="badge {cls}">{ic.get(s, _icon("help-circle", "#6b7280", 14))} {s or "Neutral"}</span>'


def _tag_html(cat: str) -> str:
    cls = {"Fraud": "tag-fraud", "Payment Issue": "tag-payment"}.get(cat, "tag-general")
    return f'<span class="eml-tag {cls}">{cat}</span>'


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
    # Support multi-word: all words must match
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
    st.markdown(
        '<div style="display:flex;align-items:center;gap:10px;padding:6px 0 2px;">'
        '<div class="avatar av-indigo" style="width:34px;height:34px;font-size:.72rem;">FT</div>'
        "<div>"
        '<div style="font-size:.72rem;color:#9ca3af !important;">Welcome</div>'
        '<div style="font-size:.88rem;font-weight:700;color:#1a1a2e !important;">Finance Triage</div>'
        "</div></div>",
        unsafe_allow_html=True,
    )

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
            clr = "#4f46e5" if is_active else "#6b7280"
            st.markdown(
                f'<div style="display:flex;align-items:center;justify-content:center;height:38px;">'
                f'{_icon(icon_name, clr, 18)}</div>',
                unsafe_allow_html=True,
            )
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
    st.markdown(
        '<div class="top-bar">'
        '<div class="top-logo"><div class="top-logo-icon">FT</div><span>Fetch Emails</span></div>'
        "</div>",
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div class="fetch-card">'
        '<div style="display:flex;gap:12px;align-items:flex-start;">'
        f'<span style="font-size:1.2rem;">{_icon("lightbulb", "#f59e0b", 22)}</span>'
        "<div>"
        '<div style="font-weight:700;color:#1a1a2e;margin-bottom:3px;font-size:.92rem;">How it works</div>'
        '<div style="color:#6b7280;font-size:.82rem;line-height:1.8;">'
        "1. Click <b>Fetch Emails</b> below<br/>"
        "2. Connects to your Gmail inbox via IMAP<br/>"
        "3. Fetches emails from the <b>last 2 days</b><br/>"
        "4. Emails are analysed by AI (Groq Llama 3.3)<br/>"
        "5. Tickets created and sorted by urgency — duplicates auto-skipped"
        "</div></div></div></div>",
        unsafe_allow_html=True,
    )
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
                f'<div class="alert-bar ab-red"><span class="ab-icon">{_icon("x-circle", "#dc2626", 18)}</span>'
                f'<div class="ab-text"><b>Rate Limit Hit</b> — Processed {fetched} email(s). '
                "Wait 1-2 min and retry.</div></div>",
                unsafe_allow_html=True,
            )
        if fetched > 0:
            parts = [f"{fetched} processed"]
            if skipped:
                parts.append(f"{skipped} duplicates skipped")
            if errs:
                parts.append(f"{errs} errors")
            st.markdown(
                f'<div class="alert-bar ab-green"><span class="ab-icon">{_icon("check-circle", "#16a34a", 18)}</span>'
                f'<div class="ab-text"><b>{result.get("message","Done!")}</b> — '
                f'{"  •  ".join(parts)}</div></div>',
                unsafe_allow_html=True,
            )
            for i, t in enumerate(result.get("tickets", [])):
                tc1, tc2, tc3, tc4 = st.columns([3, 1, 1, 1])
                with tc1:
                    st.markdown(f"**{t.get('subject','N/A')}**")
                    st.caption(t.get("sender", ""))
                with tc2:
                    st.markdown(_pri_badge(t.get("priority", "Medium")), unsafe_allow_html=True)
                with tc3:
                    st.markdown(_cat_badge(t.get("category", "General")), unsafe_allow_html=True)
                with tc4:
                    st.code(t.get("ticket_id", "")[:8])
                if i < len(result.get("tickets", [])) - 1:
                    st.divider()
        else:
            st.markdown(
                f'<div class="alert-bar ab-amber"><span class="ab-icon">{_icon("mail-open", "#d97706", 18)}</span>'
                '<div class="ab-text"><b>No new emails.</b> '
                'Try enabling "Include already-read emails".</div></div>',
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
    kp   = key_prefix  # unique per tab

    st.markdown('<div class="detail-card">', unsafe_allow_html=True)
    st.markdown(
        '<div class="detail-actions">'
        f'<span class="action-btn"><span class="action-icon">{_icon("reply", "#6b7280", 15)}</span> Reply</span>'
        f'<span class="action-btn"><span class="action-icon">{_icon("reply", "#6b7280", 15)}</span> Reply All</span>'
        f'<span class="action-btn"><span class="action-icon">{_icon("corner-up-right", "#6b7280", 15)}</span> Forward</span>'
        f'<span class="action-btn"><span class="action-icon">{_icon("trash-2", "#6b7280", 15)}</span> Delete</span>'
        "</div>",
        unsafe_allow_html=True,
    )
    st.markdown(f'<div class="detail-subject-line">{_sub}</div>', unsafe_allow_html=True)
    st.markdown(
        f'<div class="detail-from">{_avatar(_sdr)}<div>'
        f'<div class="detail-from-name">{_sdr}</div>'
        f'<div class="detail-from-time">{_tm}</div></div>'
        f'<div style="margin-left:auto;display:flex;gap:5px;flex-wrap:wrap;">'
        f'{_pri_badge(_p)} {_cat_badge(_c)} <span class="badge b-status">{_icon("pin", "#4f46e5", 13)} {_st}</span>'
        f"</div></div>",
        unsafe_allow_html=True,
    )
    st.markdown(f'<div class="detail-body">{_bd}</div></div>', unsafe_allow_html=True)

    st.markdown(f'<div class="section-hdr">{_icon("brain", "#4f46e5", 15)} AI Analysis</div>', unsafe_allow_html=True)
    st.markdown(
        f'<div class="insight-grid">'
        f'<div class="insight-box"><div class="insight-label">Category</div>{_cat_badge(_c)}</div>'
        f'<div class="insight-box"><div class="insight-label">Sentiment</div>{_sent_badge(ticket.get("sentiment","Neutral"))}</div>'
        f'<div class="insight-box"><div class="insight-label">Intent</div><div class="insight-value">{ticket.get("intent","N/A")}</div></div>'
        f'<div class="insight-box"><div class="insight-label">Amount</div><div class="insight-value">{ticket.get("amount") or "N/A"}</div></div>'
        f"</div>",
        unsafe_allow_html=True,
    )
    e1, e2, e3 = st.columns(3)
    e1.metric("Customer", ticket.get("customer_name") or "N/A")
    e2.metric("Transaction ID", ticket.get("transaction_id") or "N/A")
    e3.metric("Amount", ticket.get("amount") or "N/A")
    st.markdown(f"**{_icon('file-text', '#4f46e5', 15)} Summary:** {ticket.get('summary', 'N/A')}", unsafe_allow_html=True)

    st.markdown(f'<div class="section-hdr">{_icon("edit-3", "#4f46e5", 15)} Draft Response</div>', unsafe_allow_html=True)
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
    st.markdown(
        '<div class="top-bar">'
        '<div class="top-logo"><div class="top-logo-icon">FT</div><span>Finance Triage — Enterprise Analytics</span></div>'
        "</div>",
        unsafe_allow_html=True,
    )

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
    st.markdown(
        f'<div class="chart-title" style="margin-bottom:8px;">{_icon("alert-triangle", "#ef4444", 18)} KEY FINANCIAL RISKS</div>',
        unsafe_allow_html=True,
    )
    p1, p2, p3, p4 = st.columns(4)

    # Card 1: Total Disputed Value
    disputed_vol = metrics.get("total_disputed_volume", 0)
    with p1:
        st.markdown(
            f'<div class="a-card ac-red">'
            f'<div class="a-card-icon">{_icon("dollar-sign", "#ef4444", 26)}</div>'
            f'<div class="a-card-label">Total Disputed Value</div>'
            f'<div class="a-card-num">{_fmt_currency(disputed_vol)}</div>'
            f'<div class="a-card-sub">{metrics.get("open_tickets",0)} open tickets</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

    # Card 2: Active Fraud Alerts (count + value)
    fraud_open_ct = metrics.get("fraud_alerts_open", 0)
    fraud_open_val = metrics.get("fraud_exposure_open", 0)
    with p2:
        fraud_color_cls = "ac-red" if fraud_open_ct > 0 else "ac-green"
        st.markdown(
            f'<div class="a-card {fraud_color_cls}">'
            f'<div class="a-card-icon">{_icon("shield-alert", "#ef4444", 26)}</div>'
            f'<div class="a-card-label">Active Fraud Alerts</div>'
            f'<div class="a-card-num">{fraud_open_ct} Alert{"s" if fraud_open_ct != 1 else ""}</div>'
            f'<div class="a-card-sub">{_fmt_currency(fraud_open_val)} exposure</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

    # Card 3: SLA Breaches
    sla_ct = metrics.get("sla_breaches", 0)
    with p3:
        sla_cls = "ac-red" if sla_ct > 0 else "ac-green"
        sla_text_color = "color:#dc2626;font-weight:800;" if sla_ct > 0 else ""
        st.markdown(
            f'<div class="a-card {sla_cls}">'
            f'<div class="a-card-icon">{_icon("clock", "#f59e0b", 26)}</div>'
            f'<div class="a-card-label">SLA Breaches</div>'
            f'<div class="a-card-num" style="{sla_text_color}">{sla_ct}</div>'
            f'<div class="a-card-sub">High priority &gt; 4h open</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

    # Card 4: All-time Fraud Exposure
    fraud_total = metrics.get("fraud_exposure_total", 0)
    with p4:
        st.markdown(
            f'<div class="a-card ac-amber">'
            f'<div class="a-card-icon">{_icon("shield-check", "#f59e0b", 26)}</div>'
            f'<div class="a-card-label">Fraud Exposure (All-Time)</div>'
            f'<div class="a-card-num">{_fmt_currency(fraud_total)}</div>'
            f'<div class="a-card-sub">{metrics.get("fraud_alerts_open",0)} unresolved</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

    # ── SLA Breach Detail Table (if any) ──
    sla_detail = metrics.get("sla_breach_detail", [])
    if sla_detail:
        with st.expander(f"{len(sla_detail)} SLA Breach Detail(s)", expanded=False):
            for b in sla_detail:
                st.markdown(
                    f'<div class="alert-bar ab-red">'
                    f'<span class="ab-icon">{_icon("clock", "#dc2626", 18)}</span>'
                    f'<div class="ab-text">'
                    f'<b>{b.get("customer_name","Unknown")}</b> — '
                    f'{b.get("category","General")} — '
                    f'Open for <b>{b.get("hours_open",0):.1f}h</b> — '
                    f'Amount: {b.get("amount") or "N/A"}'
                    f'</div></div>',
                    unsafe_allow_html=True,
                )

    st.markdown("")

    # ════════════════════════════════════════════════════
    # ROW 2: OPERATIONAL HEALTH
    # ════════════════════════════════════════════════════
    st.markdown(
        f'<div class="chart-title" style="margin-bottom:8px;">{_icon("activity", "#4f46e5", 18)} OPERATIONAL HEALTH</div>',
        unsafe_allow_html=True,
    )
    op1, op2 = st.columns(2)

    # ── Chart 1: Incoming Volume by Hour (Plotly line chart) ──
    with op1:
        st.markdown('<div class="chart-card">', unsafe_allow_html=True)
        st.markdown(f'<div class="chart-title">{_icon("trending-up", "#4f46e5", 16)} Incoming Volume by Hour (Last 48h)</div>', unsafe_allow_html=True)
        vol_data = metrics.get("volume_by_hour", [])
        if vol_data:
            hours = [v["hour"] for v in vol_data]
            counts = [v["count"] for v in vol_data]
            # Show only time portion for cleaner labels
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
                xaxis=dict(
                    showgrid=False,
                    tickangle=-45,
                    tickfont=dict(size=9, color='#9ca3af'),
                    nticks=12,
                ),
                yaxis=dict(
                    showgrid=True,
                    gridcolor='#f3f4f6',
                    tickfont=dict(size=10, color='#9ca3af'),
                ),
                hoverlabel=dict(bgcolor='#1a1a2e', font_color='white', font_size=12),
            )
            st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})
        else:
            st.caption("No volume data in the last 48 hours.")
        st.markdown('</div>', unsafe_allow_html=True)

    # ── Chart 2: Top 5 Merchants / Issues (Plotly bar chart) ──
    with op2:
        st.markdown('<div class="chart-card">', unsafe_allow_html=True)
        st.markdown(f'<div class="chart-title">{_icon("building", "#4f46e5", 16)} Top 5 Merchants / Entities Mentioned</div>', unsafe_allow_html=True)
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
                xaxis=dict(
                    showgrid=True,
                    gridcolor='#f3f4f6',
                    tickfont=dict(size=10, color='#9ca3af'),
                ),
                yaxis=dict(
                    tickfont=dict(size=11, color='#1a1a2e', family='Inter'),
                ),
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
    st.markdown(
        f'<div class="chart-title" style="margin-bottom:8px;">{_icon("brain", "#4f46e5", 18)} AGENT & AI PERFORMANCE</div>',
        unsafe_allow_html=True,
    )

    # ── KPI cards row ──
    a1, a2, a3, a4 = st.columns(4)
    ai_rate = metrics.get("ai_success_rate", 0)
    avg_res = metrics.get("avg_resolution_h", 0)
    with a1:
        st.markdown(
            f'<div class="a-card ac-indigo">'
            f'<div class="a-card-icon">{_icon("brain", "#4f46e5", 26)}</div>'
            f'<div class="a-card-label">AI Draft Acceptance</div>'
            f'<div class="a-card-num">{ai_rate:.0f}%</div>'
            f'<div class="a-card-sub">{metrics.get("ai_drafts_used",0)} drafts sent as-is</div>'
            f'</div>',
            unsafe_allow_html=True,
        )
    with a2:
        st.markdown(
            f'<div class="a-card ac-blue">'
            f'<div class="a-card-icon">{_icon("timer", "#3b82f6", 26)}</div>'
            f'<div class="a-card-label">Avg Resolution Time</div>'
            f'<div class="a-card-num">{_fmt_hours(avg_res)}</div>'
            f'<div class="a-card-sub">{metrics.get("closed_tickets",0)} tickets resolved</div>'
            f'</div>',
            unsafe_allow_html=True,
        )
    with a3:
        st.markdown(
            f'<div class="a-card ac-green">'
            f'<div class="a-card-icon">{_icon("inbox", "#22c55e", 26)}</div>'
            f'<div class="a-card-label">Total Tickets</div>'
            f'<div class="a-card-num">{metrics.get("total_tickets",0)}</div>'
            f'<div class="a-card-sub">{metrics.get("open_tickets",0)} open / {metrics.get("closed_tickets",0)} closed</div>'
            f'</div>',
            unsafe_allow_html=True,
        )
    with a4:
        resolve_pct = (metrics.get("closed_tickets", 0) / metrics.get("total_tickets", 1) * 100) if metrics.get("total_tickets") else 0
        st.markdown(
            f'<div class="a-card ac-purple">'
            f'<div class="a-card-icon">{_icon("check-circle", "#8b5cf6", 26)}</div>'
            f'<div class="a-card-label">Resolution Rate</div>'
            f'<div class="a-card-num">{resolve_pct:.0f}%</div>'
            f'<div class="a-card-sub">{metrics.get("closed_tickets",0)} of {metrics.get("total_tickets",0)}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

    st.markdown("")

    # ── Category Performance Leaderboard ──
    cat_perf = metrics.get("category_performance", [])
    if cat_perf:
        st.markdown('<div class="chart-card">', unsafe_allow_html=True)
        st.markdown(f'<div class="chart-title">{_icon("trophy", "#f59e0b", 16)} Category Performance Leaderboard</div>', unsafe_allow_html=True)

        # Build a styled HTML table
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
        cat_icons = {"Fraud": _icon("shield-alert", "#dc2626", 15), "Payment Issue": _icon("credit-card", "#2563eb", 15), "General": _icon("file-text", "#6b7280", 15)}
        for cp in cat_perf:
            cat_name = cp.get("category", "")
            icon = cat_icons.get(cat_name, _icon("file-text", "#6b7280", 15))
            reopen_rate = cp.get("reopen_rate", 0)
            reopen_color = "#dc2626" if reopen_rate > 10 else ("#d97706" if reopen_rate > 5 else "#22c55e")
            avg_h = cp.get("avg_resolution_h", 0)
            table_html += (
                f'<tr style="border-bottom:1px solid #f3f4f6;">'
                f'<td style="padding:12px;font-weight:600;color:#1a1a2e;">{icon} {cat_name}</td>'
                f'<td style="padding:12px;font-weight:700;color:#1a1a2e;">{cp.get("total",0)}</td>'
                f'<td style="padding:12px;color:#22c55e;font-weight:600;">{cp.get("closed",0)}</td>'
                f'<td style="padding:12px;color:#6b7280;">{_fmt_hours(avg_h)}</td>'
                f'<td style="padding:12px;font-weight:700;color:{reopen_color};">{reopen_rate:.1f}%</td>'
                f'</tr>'
            )
        table_html += '</tbody></table>'
        st.markdown(table_html, unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)

    st.markdown("")

    # ── Bottom row: Priority Distribution + Status Overview ──
    st.markdown(
        f'<div class="chart-title" style="margin-bottom:8px;">{_icon("pie-chart", "#4f46e5", 18)} DISTRIBUTION OVERVIEW</div>',
        unsafe_allow_html=True,
    )
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
                labels=labels_p, values=vals_p,
                hole=0.55,
                marker=dict(colors=colors_p),
                textinfo='label+value',
                textfont=dict(size=11),
                hovertemplate='%{label}: %{value} tickets<extra></extra>',
            ))
            fig_p.update_layout(
                height=250, margin=dict(l=0, r=0, t=0, b=0),
                paper_bgcolor='rgba(0,0,0,0)',
                showlegend=False,
            )
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
                labels=labels_c, values=vals_c,
                hole=0.55,
                marker=dict(colors=colors_c),
                textinfo='label+value',
                textfont=dict(size=11),
                hovertemplate='%{label}: %{value} tickets<extra></extra>',
            ))
            fig_c.update_layout(
                height=250, margin=dict(l=0, r=0, t=0, b=0),
                paper_bgcolor='rgba(0,0,0,0)',
                showlegend=False,
            )
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
                labels=labels_s, values=vals_s,
                hole=0.55,
                marker=dict(colors=colors_s),
                textinfo='label+value',
                textfont=dict(size=11),
                hovertemplate='%{label}: %{value}<extra></extra>',
            ))
            fig_s.update_layout(
                height=250, margin=dict(l=0, r=0, t=0, b=0),
                paper_bgcolor='rgba(0,0,0,0)',
                showlegend=False,
            )
            st.plotly_chart(fig_s, width="stretch", config={"displayModeBar": False})
        else:
            st.caption("No tickets yet.")
        st.markdown('</div>', unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════
#  PAGE: INBOX  (with Search + Category Tabs + Blue Dot)
# ══════════════════════════════════════════════════════════
elif st.session_state.tab == "inbox":
    st.markdown(
        '<div class="top-bar">'
        '<div class="top-logo"><div class="top-logo-icon">FT</div><span>Inbox</span></div>'
        "</div>",
        unsafe_allow_html=True,
    )

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

    # Inject JS to auto-submit search input after 400ms debounce (live search)
    st.markdown(
        """
        <script>
        (function() {
            const doc = window.parent.document;
            const inp = doc.querySelector('input[aria-label="Search"]');
            if (!inp || inp.dataset.liveSearch) return;
            inp.dataset.liveSearch = '1';
            let timer = null;
            inp.addEventListener('input', function() {
                clearTimeout(timer);
                timer = setTimeout(function() {
                    // Simulate pressing Enter to trigger Streamlit rerun
                    inp.dispatchEvent(new KeyboardEvent('keydown',  {key:'Enter', code:'Enter', keyCode:13, which:13, bubbles:true}));
                    inp.dispatchEvent(new KeyboardEvent('keyup',    {key:'Enter', code:'Enter', keyCode:13, which:13, bubbles:true}));
                    inp.dispatchEvent(new KeyboardEvent('keypress', {key:'Enter', code:'Enter', keyCode:13, which:13, bubbles:true}));
                }, 400);
            });
        })();
        </script>
        """,
        unsafe_allow_html=True,
    )

    # ── Auto-mark selected ticket as read ──
    sel_id = st.session_state.sel
    if sel_id and sel_id not in st.session_state.read_ids:
        _api_mark_read(sel_id)
        st.session_state.read_ids.add(sel_id)

    # ── Apply search filter ──
    display_tickets = [t for t in tickets if _search_match(t, search_query)]

    if search_query:
        st.markdown(
            f'<div class="alert-bar ab-blue"><span class="ab-icon">{_icon("search", "#2563eb", 18)}</span>'
            f'<div class="ab-text">Found <b>{len(display_tickets)}</b> result(s) for "<b>{search_query}</b>"</div></div>',
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
        row_cls = "selected" if selected else ("is-read" if is_read else "")
        pd_cls = {"High": "pd-high", "Medium": "pd-medium", "Low": "pd-low"}.get(pri, "pd-low")
        sender_style = "" if not is_read else "font-weight:400;color:#6b7280;"
        subject_style = "font-weight:700;" if not is_read else "font-weight:400;color:#6b7280;"
        dot_html = '<div class="unread-dot"></div>' if not is_read else '<div class="read-dot"></div>'

        st.markdown(
            f'<div class="eml-row {row_cls}">'
            f'{_avatar(sender)}'
            f'<div class="eml-meta">'
            f'<div class="eml-sender" style="{sender_style}"><span class="p-dot {pd_cls}"></span>{sender}</div>'
            f'<div class="eml-subject" style="{subject_style}">{subject}</div>'
            f'<div class="eml-preview">{preview}</div></div>'
            f'<div class="eml-right">'
            f'<div class="eml-time">{ts}</div>'
            f'{_tag_html(cat)}</div>'
            f'{dot_html}'
            f'</div>',
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
            st.markdown(
                f'<div class="welcome"><div class="welcome-icon">{_icon("mail-open", "#9ca3af", 44)}</div>'
                '<div class="welcome-title">No tickets here</div>'
                '<div class="welcome-sub">Tickets matching this filter will appear here.</div></div>',
                unsafe_allow_html=True,
            )
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

    # Category splits for the categorised tab
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
    st.markdown(
        '<div class="top-bar">'
        '<div class="top-logo"><div class="top-logo-icon">FT</div><span>Priority Queue</span></div>'
        "</div>",
        unsafe_allow_html=True,
    )
    if st.session_state.sel:
        tkt = next((t for t in tickets if t.get("id") == st.session_state.sel), None)
        if tkt:
            _render_detail(tkt)
            st.stop()

    for icon, title, pri, qc in [
        (_icon("alert-triangle", "#ef4444", 18), "High Priority — Immediate", "High", "qc-r"),
        (_icon("clock", "#f59e0b", 18), "Medium Priority — Review Soon", "Medium", "qc-a"),
        (_icon("check-circle", "#22c55e", 18), "Low Priority — When Available", "Low", "qc-g"),
    ]:
        grp = [t for t in tickets if t.get("priority") == pri]
        st.markdown(
            f'<div class="queue-sec"><div class="queue-hdr">'
            f'<span style="font-size:1rem;">{icon}</span>'
            f'<span class="queue-title">{title}</span>'
            f'<span class="queue-cnt {qc}">{len(grp)}</span>'
            f"</div></div>",
            unsafe_allow_html=True,
        )
        if grp:
            for t in grp:
                sender = _extract_sender(t.get("email_body", ""), t.get("customer_name", ""))
                subject = _extract_subject(t.get("email_body", ""))
                c1, c2, c3 = st.columns([4, 1, 1])
                with c1:
                    st.markdown(f"{_avatar(sender)} **{sender}** — {subject}", unsafe_allow_html=True)
                    st.caption(t.get("summary", "")[:100])
                with c2:
                    st.markdown(_cat_badge(t.get("category", "General")), unsafe_allow_html=True)
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
    st.markdown(
        '<div class="top-bar">'
        '<div class="top-logo"><div class="top-logo-icon">FT</div><span>By Category</span></div>'
        "</div>",
        unsafe_allow_html=True,
    )
    if st.session_state.sel:
        tkt = next((t for t in tickets if t.get("id") == st.session_state.sel), None)
        if tkt:
            _render_detail(tkt)
            st.stop()

    for icon, title, cat, cc in [
        (_icon("shield-alert", "#dc2626", 18), "Fraud", "Fraud", "qc-r"),
        (_icon("credit-card", "#f59e0b", 18), "Payment Issues", "Payment Issue", "qc-a"),
        (_icon("file-text", "#22c55e", 18), "General Inquiries", "General", "qc-g"),
    ]:
        grp = [t for t in tickets if t.get("category") == cat]
        st.markdown(
            f'<div class="queue-sec"><div class="queue-hdr">'
            f'<span style="font-size:1rem;">{icon}</span>'
            f'<span class="queue-title">{title}</span>'
            f'<span class="queue-cnt {cc}">{len(grp)}</span>'
            f"</div></div>",
            unsafe_allow_html=True,
        )
        if grp:
            for t in grp:
                sender = _extract_sender(t.get("email_body", ""), t.get("customer_name", ""))
                subject = _extract_subject(t.get("email_body", ""))
                c1, c2, c3 = st.columns([4, 1, 1])
                with c1:
                    st.markdown(f"{_avatar(sender)} **{sender}** — {subject}", unsafe_allow_html=True)
                    st.caption(t.get("summary", "")[:100])
                with c2:
                    st.markdown(_pri_badge(t.get("priority", "Medium")), unsafe_allow_html=True)
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
    st.markdown(
        '<div class="top-bar">'
        '<div class="top-logo"><div class="top-logo-icon">FT</div><span>Alerts</span></div>'
        "</div>",
        unsafe_allow_html=True,
    )
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
            f'<div class="alert-bar ab-green"><span class="ab-icon">{_icon("check-circle", "#16a34a", 18)}</span>'
            "<div class=\"ab-text\"><b>All clear!</b> No alerts right now.</div></div>",
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            f'<div class="alert-bar ab-red"><span class="ab-icon">{_icon("bell", "#dc2626", 18)}</span>'
            f'<div class="ab-text"><b>{len(alert_tix)} Active Alert{"s" if len(alert_tix) > 1 else ""}</b> — '
            f"Emails needing immediate attention.</div></div>",
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
                f'<div class="queue-sec" style="border-left:3px solid #ef4444;">'
                f'<div style="display:flex;gap:14px;align-items:center;">'
                f'{_avatar(sender)}'
                f'<div style="flex:1;min-width:0;">'
                f'<div style="font-weight:700;color:#1a1a2e;font-size:.88rem;">{sender}</div>'
                f'<div style="color:#6b7280;font-size:.82rem;margin-top:1px;">{subject}</div>'
                f'<div style="color:#9ca3af;font-size:.76rem;margin-top:2px;">{t.get("summary","")[:100]}</div>'
                f'<div style="margin-top:6px;display:flex;gap:5px;flex-wrap:wrap;">'
                f'{_pri_badge(pri)} {_cat_badge(cat)} {_sent_badge(snt)}</div></div>'
                f'<div style="text-align:right;">'
                f'<div style="font-size:.68rem;color:#9ca3af;">{_fmt_time(t.get("created_at"))}</div>'
                f'<div style="font-size:.64rem;color:#dc2626;font-weight:600;margin-top:3px;">{"  •  ".join(reasons)}</div>'
                f"</div></div></div>",
                unsafe_allow_html=True,
            )
            if st.button("View Details →", key=f"al_{t['id']}", use_container_width=True):
                st.session_state.sel = t["id"]
                st.session_state.tab = "inbox"
                st.rerun()

