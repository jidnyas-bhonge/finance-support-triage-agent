# 🏦 Finance Support Triage Agent

An AI-powered system that fetches customer support emails, classifies them by priority and category, and drafts professional replies — all from a single Streamlit dashboard. Deploys as a **single service** on Streamlit Cloud.

![AI Powered](https://img.shields.io/badge/AI-Powered-blueviolet?style=flat-square)
![Llama 3.3 70B](https://img.shields.io/badge/Llama_3.3-70B-orange?style=flat-square)
![Streamlit](https://img.shields.io/badge/Streamlit-FF4B4B?style=flat-square&logo=streamlit&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-4169E1?style=flat-square&logo=postgresql&logoColor=white)

---

## ✨ Features

- **Auto-fetch emails** from Gmail via IMAP every 5 minutes (keeps the service alive)
- **AI analysis** — sentiment, intent, priority, category, entity extraction in a single LLM call
- **Multi-tier urgency classifier** — 3 tiers × 12 subcategories with two-pass priority resolution
- **Auto-generated draft replies** tailored to Fraud / Payment Issue / General categories
- **Approve & send** replies directly via Gmail SMTP from the dashboard
- **Enterprise analytics dashboard** — KPI cards, SLA breach tracking, volume charts, merchant analysis
- **Modern inbox** — search, read/unread tracking (blue dots), date grouping, tabbed categories
- **Priority queue, category view, and alerts page**
- **Duplicate detection** — skips already-processed emails automatically
- **Single-service deployment** — no separate backend needed

---

## 🛠️ Tech Stack

| Layer | Technology |
|-------|-----------|
| **AI Model** | Llama 3.3 70B Versatile (via [Groq](https://groq.com/)) |
| **Urgency Classifier** | Llama 3.1 8B Instant (via Groq native client) |
| **AI Framework** | [LangChain](https://langchain.com/) — structured output + prompt engineering |
| **App Framework** | [Streamlit](https://streamlit.io/) + streamlit-autorefresh |
| **Database** | [PostgreSQL](https://www.postgresql.org/) + SQLAlchemy ORM |
| **Email In** | Gmail IMAP (SSL, port 993) |
| **Email Out** | Gmail SMTP (TLS, port 587) |
| **Charts** | [Plotly](https://plotly.com/) |
| **Validation** | [Pydantic](https://docs.pydantic.dev/) |

---

## 📂 Project Structure

```
finance-support-triage-agent/
├── streamlit_app.py            # ★ Main app — single-service entry point
├── requirements.txt            # All dependencies
├── .streamlit/
│   ├── config.toml             # Theme + server config
│   └── secrets.toml.example    # Secrets template
├── frontend/
│   ├── templates.py            # HTML template builders + SVG icon system
│   └── static/
│       ├── styles.css          # All CSS styles
│       └── script.js           # Live search debounce JS
├── backend/                    # Reference backend (not used in deployment)
│   ├── main.py                 # FastAPI app (for local dev)
│   ├── agent.py                # AI agent module
│   ├── urgency_classifier.py   # Multi-tier urgency classifier
│   ├── models.py               # SQLAlchemy ORM models
│   ├── schemas.py              # Pydantic schemas
│   └── database.py             # DB engine & session
├── .env.example                # Environment variables template
├── .gitignore
└── README.md
```

---

## 🚀 Deploy to Streamlit Cloud

### 1. Push to GitHub

```bash
git init
git add .
git commit -m "Initial commit"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/finance-support-triage-agent.git
git push -u origin main
```

### 2. Set up PostgreSQL

Create a free PostgreSQL database on any provider:
- [Neon](https://neon.tech/) (recommended — free tier)
- [Supabase](https://supabase.com/)
- [Railway](https://railway.app/)
- [Aiven](https://aiven.io/)

Copy the connection string (e.g. `postgresql://user:pass@host:5432/dbname`).

### 3. Deploy on Streamlit Cloud

1. Go to [share.streamlit.io](https://share.streamlit.io) → **New app**
2. Configure:

   | Setting | Value |
   |---------|-------|
   | Repository | `your-username/finance-support-triage-agent` |
   | Branch | `main` |
   | Main file path | `streamlit_app.py` |

3. Go to **App Settings → Secrets** and paste:

   ```toml
   DATABASE_URL = "postgresql://user:password@host:5432/dbname"
   GROQ_API_KEY = "gsk_your_groq_api_key"
   EMAIL_USER = "yourname@gmail.com"
   EMAIL_PASSWORD = "abcd efgh ijkl mnop"
   ```

4. Click **Deploy!** — live in ~2 minutes.

### Keep-Alive Mechanism

The app uses `streamlit_autorefresh` with a **5-minute interval** that:
- Auto-refreshes the dashboard UI
- Triggers automatic email fetching from Gmail
- Prevents Streamlit Cloud from putting the app to sleep

---

## 🏠 Local Development

### 1. Install dependencies

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure environment

Copy `.env.example` to `.env` and fill in your values:

```bash
cp .env.example .env
```

### 3. Run

```bash
streamlit run streamlit_app.py
```

Open **http://localhost:8501** 🎉

---

## 🧠 How the AI Works

1. Email text → **LangChain prompt** → **Groq Llama 3.3 70B** → structured analysis + draft reply
2. Email text → **Groq Llama 3.1 8B** → urgency classification (3 tiers × 12 subcategories)
3. **Two-pass priority resolution**: agent priority vs. classifier urgency → highest wins
4. **SHA-256 caching** skips the LLM for duplicate emails
5. Output validated against **Pydantic schemas** — no regex parsing

### Urgency Classification Taxonomy

| Tier | SLA | Subcategories |
|------|-----|---------------|
| **High** | Immediate | Security Breach, Fraud Report, Critical Transaction Failure, Account Lockout, Billing Error |
| **Medium** | 24 hours | Dispute Initiation, Feature Malfunction, KYC Compliance |
| **Low** | 48 hours | General Inquiry, Statement Request, Feedback/Feature Request, Status Check |

---

## 📊 Dashboard Pages

| Page | Description |
|------|-------------|
| **Analytics** | KPI cards (disputed volume, fraud exposure, SLA breaches), volume-by-hour chart, top merchants, category performance leaderboard, distribution donuts |
| **Inbox** | Search, read/unread tracking, date grouping, tabbed by category (All/Fraud/Payments/General/Resolved) |
| **Priority Queue** | Tickets grouped by High/Medium/Low priority |
| **By Category** | Tickets grouped by Fraud/Payment Issue/General |
| **Alerts** | Fraud tickets + High priority + Urgent/Negative sentiment |

---

## 📄 License

MIT
