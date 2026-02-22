FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Create .streamlit/config.toml (the file lives at repo root which is outside
# the frontend/ build context, so we generate it inline)
RUN mkdir -p .streamlit && cat > .streamlit/config.toml <<'EOF'
[theme]
primaryColor = "#4f46e5"
backgroundColor = "#f8f9fb"
secondaryBackgroundColor = "#ffffff"
textColor = "#1a1a2e"
font = "sans serif"

[server]
headless = true
enableCORS = false
enableXsrfProtection = false

[browser]
gatherUsageStats = false
EOF

# Railway injects $PORT — override server.port at runtime
CMD sh -c "streamlit run app.py \
    --server.port=${PORT:-8501} \
    --server.address=0.0.0.0 \
    --server.headless=true \
    --server.enableCORS=false \
    --server.enableXsrfProtection=false \
    --browser.gatherUsageStats=false \
    --server.fileWatcherType=none"
