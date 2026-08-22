# JSON → Table Converter

A lightweight web tool to convert JSON data into viewable tables with CSV export capability. Designed for internal team use with zero data storage.

![Python](https://img.shields.io/badge/Python-3.11+-blue)
![Flask](https://img.shields.io/badge/Flask-3.0-green)
![License](https://img.shields.io/badge/License-GPL--3.0-yellow)

## Features

- **Multiple Input Methods**
  - 📁 File upload (drag & drop supported)
  - 📋 Paste JSON directly
  - 🌐 Fetch from external APIs

- **Authentication Support** (for API fetching)
  - API Key (custom header)
  - Basic Authentication
  - Bearer Token
  - Query Parameter Token

- **Data Processing**
  - Handles nested JSON objects and JSON Lines
  - Displays nested data as expandable tables (with render caps, so a huge cell cannot freeze the tab)
  - Preview the first `PREVIEW_ROW_LIMIT` rows, then "Load next 500" / "Load all"
  - Filter rows, sort columns, hide columns
  - Export **all** rows to CSV, TSV, JSONL, Markdown or Excel

- **Privacy First**
  - No data storage - everything processed in-memory
  - No databases, no logs, no persistence
  - Session-based processing only

---

## Quick Start (Local Development)

### Prerequisites
- Python 3.11+
- pip

### Installation

```bash
# Clone or download the project
cd json-table-tool

# Create virtual environment (optional but recommended)
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Run the application
python app.py
```

Open your browser to `http://localhost:5000`

---

## Deployment to Render (Recommended)

[Render](https://render.com) offers a free tier perfect for internal tools. No credit card required for free tier.

### Why Render?
- ✅ Free tier available
- ✅ No data persistence on free tier (exactly what we need)
- ✅ Easy GitHub integration
- ✅ HTTPS included
- ✅ Simple deployment process

### Step-by-Step Deployment

#### 1. Prepare Your Repository

Push the code to a GitHub repository (can be private):

```bash
cd json-table-tool
git init
git add .
git commit -m "Initial commit"
git remote add origin https://github.com/YOUR_USERNAME/json-table-tool.git
git push -u origin main
```

#### 2. Create Render Account

1. Go to [render.com](https://render.com)
2. Sign up with GitHub (recommended for easy repo access)
3. Verify your email

#### 3. Deploy the Service

**Option A: Using render.yaml (Blueprint)**

1. In Render dashboard, click **"New +"** → **"Blueprint"**
2. Connect your GitHub repository
3. Render will auto-detect `render.yaml` and configure everything
4. Click **"Apply"**
5. Wait for deployment (2-3 minutes)

**Option B: Manual Setup**

1. In Render dashboard, click **"New +"** → **"Web Service"**
2. Connect your GitHub repository
3. Configure:
   - **Name**: `json-table-converter` (or your choice)
   - **Region**: Choose closest to your team
   - **Branch**: `main`
   - **Runtime**: `Python 3`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `gunicorn "app:create_app()" --bind 0.0.0.0:$PORT --workers "$WEB_CONCURRENCY" --timeout 60`
   - **Environment**: `SECRET_KEY` (click *Generate* — the app **refuses to start**
     under `APP_ENV=production` with the development default), `APP_ENV=production`,
     `WEB_CONCURRENCY=1`, `APP_REPLICAS=1`
     (see [Deployment topology](#deployment-topology-and-rate-limiting))
4. Select **Free** plan
5. Click **"Create Web Service"**

#### 4. Access Your App

After deployment completes:
- Your app will be available at: `https://json-table-converter.onrender.com`
- (The exact URL depends on your service name)

### Access Control for Internal Use

Since this is for internal team use, consider these options:

#### Option 1: Keep URL Private (Simplest)
- Don't share the URL publicly
- Free tier URLs are hard to guess
- Sufficient for most internal tools

#### Option 2: Add Basic Authentication
Add this to `app.py` before the routes:

```python
from functools import wraps
from flask import request, Response

def check_auth(username, password):
    return username == 'your_team' and password == 'your_secret_password'

def authenticate():
    return Response(
        'Authentication required', 401,
        {'WWW-Authenticate': 'Basic realm="Login Required"'}
    )

def requires_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.authorization
        if not auth or not check_auth(auth.username, auth.password):
            return authenticate()
        return f(*args, **kwargs)
    return decorated

# Then add @requires_auth decorator to routes:
@app.route('/')
@requires_auth
def index():
    ...
```

#### Option 3: IP Allowlisting (Paid Tier)
Render's paid tiers support IP allowlisting for stricter access control.

---

## Alternative Deployment Options

### Self-Hosted with Gunicorn (Recommended for Own Server)

Run directly on any Linux server with Python 3.11+:

```bash
# Clone and install
git clone https://github.com/YOUR_USERNAME/json-table-tool.git
cd json-table-tool
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Set production environment variables.
#
# SECRET_KEY must be a random value you generate, not a literal copied from this
# README. The startup gate rejects the dev default and an empty value, but it
# cannot tell a real secret from a memorable one someone pasted:
#
#   python -c "import secrets; print(secrets.token_urlsafe(48))"
#
# Every SECRET_KEY placeholder below means "the output of that command", kept
# out of the shell history and out of version control.
export SECRET_KEY="$(python -c 'import secrets; print(secrets.token_urlsafe(48))')"
export FLASK_DEBUG=0
export APP_ENV=production

# Deployment topology. memory:// rate-limit counters are process-local, so the
# effective limit is multiplied by workers x replicas. One worker and one
# instance is the default; see "Deployment topology and rate limiting" below
# before raising either.
export WEB_CONCURRENCY=1
export APP_REPLICAS=1

# Run with gunicorn. --workers comes from WEB_CONCURRENCY so the running count
# and the declared count cannot drift, and --timeout stays above
# API_FETCH_TIMEOUT (default 30s).
gunicorn "app:create_app()" --bind 0.0.0.0:8000 --workers "$WEB_CONCURRENCY" --timeout 60
```

#### Systemd Service (Auto-Start on Boot)

Create `/etc/systemd/system/json-table-tool.service`:

```ini
[Unit]
Description=JSON Table Converter
After=network.target

[Service]
User=www-data
Group=www-data
WorkingDirectory=/opt/json-table-tool
Environment="SECRET_KEY=<output of the token_urlsafe command above>"
Environment="FLASK_DEBUG=0"
Environment="APP_ENV=production"
Environment="WEB_CONCURRENCY=1"
Environment="APP_REPLICAS=1"
ExecStart=/opt/json-table-tool/venv/bin/gunicorn "app:create_app()" --bind 127.0.0.1:8000 --workers ${WEB_CONCURRENCY} --timeout 60
Restart=always

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable json-table-tool
sudo systemctl start json-table-tool
```

#### Nginx Reverse Proxy (HTTPS)

Pair with Nginx for TLS termination and static file serving:

```nginx
server {
    listen 443 ssl;
    server_name jsontable.yourcompany.com;

    ssl_certificate /etc/letsencrypt/live/jsontable.yourcompany.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/jsontable.yourcompany.com/privkey.pem;

    location /static/ {
        alias /opt/json-table-tool/static/;
        expires 1d;
    }

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

### Docker

```dockerfile
# Dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8000
ENV APP_ENV=production
ENV WEB_CONCURRENCY=1
ENV APP_REPLICAS=1
# --workers is derived from WEB_CONCURRENCY (shell form so it expands), and
# --timeout stays above API_FETCH_TIMEOUT.
CMD gunicorn "app:create_app()" --bind 0.0.0.0:8000 --workers "$WEB_CONCURRENCY" --timeout 60
```

```bash
docker build -t json-table-tool .
docker run -p 8000:8000 \
  -e SECRET_KEY="$(python -c 'import secrets; print(secrets.token_urlsafe(48))')" \
  json-table-tool
```

### Deployment topology and rate limiting

Flask-Limiter's default `memory://` storage keeps its counters **inside one
process**. The effective limit is therefore multiplied by `workers x replicas`,
not by workers alone: four workers on two instances enforce eight times the
configured limit.

The supported default is **one worker and one instance**. To run more:

1. Install the Redis client: `pip install -r requirements.txt -r requirements-redis.txt`
2. Set `RATELIMIT_STORAGE_URI=redis://...`
3. Raise `WEB_CONCURRENCY` (and `APP_REPLICAS`, mirroring `numInstances`)

Under `APP_ENV=production` the app refuses to start if `WEB_CONCURRENCY` or
`APP_REPLICAS` is undeclared, if a `--workers N` in the start command disagrees
with `WEB_CONCURRENCY`, or if either count exceeds one while storage is still
`memory://`. Outside production the same conditions log a warning instead.

**HTTPS is required on every deployment path.** API keys, bearer tokens and
basic-auth passwords are POSTed from the browser to this app; without TLS they
are exposed on the wire.

**Timeout invariant:** gunicorn's `--timeout` must stay above
`API_FETCH_TIMEOUT` (a factor of two is the documented margin). gunicorn's
default of 30s equals the default `API_FETCH_TIMEOUT`, so a slow API fetch
raced the worker kill and surfaced as a 502.

#### Docker Compose

```yaml
# docker-compose.yml
services:
  app:
    build: .
    ports:
      - "8000:8000"
    environment:
      # See the SECRET_KEY note above: generate this, do not copy a literal.
      - SECRET_KEY=${SECRET_KEY:?set SECRET_KEY in .env or the environment}
      - FLASK_DEBUG=0
      - APP_ENV=production
      - WEB_CONCURRENCY=1
      - APP_REPLICAS=1
      - RATE_LIMIT_PROCESS=30/minute
      - RATE_LIMIT_EXPORT=60/minute
    restart: unless-stopped
```

```bash
docker compose up -d
```

This compose file terminates **no TLS** — it publishes plain HTTP on 8000, which
is only appropriate behind something that does. Credentials for the API-fetch
feature are POSTed from the browser, so put this behind the Nginx/Let's Encrypt
front end from the section above (or your platform's load balancer) and do not
publish port 8000 to the internet directly. With TLS terminated upstream, also
set `TRUST_PROXY=1` so rate limiting and the `Secure` cookie flag see the real
client address and scheme.

### Railway.app

```bash
npm install -g @railway/cli
railway login
railway init
railway up
```

### Fly.io

```bash
curl -L https://fly.io/install.sh | sh
fly launch
fly deploy
```

### Environment Variables (All Deployment Methods)

Set these in production for any deployment method:

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `SECRET_KEY` | **Yes** | `dev-secret-key-...` | CSRF token signing key. Generate with `python -c "import secrets; print(secrets.token_hex(32))"` |
| `FLASK_DEBUG` | No | `0` | Set to `0` in production |
| `MAX_UPLOAD_SIZE` | No | `10485760` | Max request body in bytes (10 MB) |
| `PREVIEW_ROW_LIMIT` | No | `25` | Rows shown in preview table |
| `API_FETCH_TIMEOUT` | No | `30` | Seconds before API fetch times out |
| `API_FETCH_MAX_RESPONSE` | No | `10485760` | Max API response size in bytes |
| `RATE_LIMIT_PROCESS` | No | `30/minute` | Rate limit on /process endpoint |
| `RATE_LIMIT_EXPORT` | No | `60/minute` | Rate limit on export endpoints |
| `RATE_LIMIT_DEFAULT` | No | `120/minute` | Default rate limit for all routes |
| `APP_ENV` | **Yes** (prod) | unset | Set to `production`. The single canonical production signal: enables the SECRET_KEY fail-fast, the `Secure` session cookie and the rate-limit topology guard. No alias (`PRODUCTION=true`, …) is accepted |
| `WEB_CONCURRENCY` | **Yes** (prod) | `1` | Worker count, and the single source of truth for it — start commands pass `--workers "$WEB_CONCURRENCY"` |
| `APP_REPLICAS` | **Yes** (prod) | `1` | Instance count; must mirror `render.yaml`'s `numInstances` |
| `RATELIMIT_STORAGE_URI` | No | `memory://` | Counters are process-local. Required to be shared (`redis://…`) above 1 worker × 1 instance |
| `TRUST_PROXY` | No | `0` | `1` trusts `X-Forwarded-*` from exactly one hop. Enable only behind a proxy you control |
| `API_ALLOWED_PORTS` | No | `80,443,8443` | Ports the API-fetch feature may connect to. Empty disables the check |
| `API_DNS_TIMEOUT` | No | `3` | Seconds a **request** waits for DNS. Does not bound the lookup itself |
| `API_DNS_MAX_WORKERS` | No | `4` | Concurrent DNS lookups |
| `API_DNS_ADMISSION_TIMEOUT` | No | `1` | Seconds to wait for a DNS permit before rejecting |
| `FLATTEN_MAX_DEPTH` | No | `10` | Max recursion depth for flattening and extraction |
| `MAX_EXPORT_CELLS` | No | `250000` | Excel-only budget in cells (`rows × columns`). `0` disables it. CSV/TSV are streamed and uncapped |
| `STATIC_MAX_AGE` | No | `86400` | `Cache-Control` max-age for static assets (URLs are version-busted) |
| `GZIP_MIN_SIZE` | No | `1024` | Smallest response body worth compressing |
| `HEALTH_REVEAL_VERSION` | No | `1` | Set to `0` to omit `version` from the health endpoints |

`.env.example` lists every variable with its default and the reasoning behind it.

**HTTPS is required on every deployment path** — API keys, bearer tokens and
basic-auth passwords are POSTed from the browser to this app.

---

## Usage Guide

### 1. Upload JSON File
- Click "Upload File" tab
- Drag & drop a `.json` file or click to browse
- Click "Convert to Table"

### 2. Paste JSON
- Click "Paste JSON" tab
- Paste your JSON into the text area
- Click "Convert to Table"

### 3. Fetch from API
- Click "Fetch from API" tab
- Enter the API endpoint URL
- Select authentication method if needed:
  - **API Key**: Enter header name and key
  - **Basic Auth**: Enter username and password
  - **Bearer Token**: Enter your token
  - **Query Param**: Enter parameter name and value
- Click "Convert to Table"

### 4. Export Data
- After conversion, click **"Export"** to see format options:
  - **CSV** — Comma-separated values (generated instantly in your browser)
  - **TSV** — Tab-separated values (generated instantly in your browser)
  - **JSONL** — one JSON object per line, over the same flattened columns the
    table shows, with values unescaped (no formula prefixing applied)
  - **Markdown** — a Markdown table; `|`, `\` and line breaks are escaped so a
    value cannot break the table, but no formula prefixing is applied
  - **Excel** — `.xlsx` file via server-side generation
- All formats export ALL rows (not just the preview)
- Excel is greyed out when the dataset exceeds `MAX_EXPORT_CELLS`; CSV and TSV
  are streamed and have no such limit, so every dataset stays exportable

---

## JSON Format Support

### Supported Structures

```json
// Array of objects (ideal)
[
  {"id": 1, "name": "Alice"},
  {"id": 2, "name": "Bob"}
]

// Object with array property
{
  "data": [
    {"id": 1, "name": "Alice"},
    {"id": 2, "name": "Bob"}
  ]
}

// Nested objects
{
  "users": {
    "data": [
      {"id": 1, "profile": {"name": "Alice", "age": 30}}
    ]
  }
}
```

### Nested Data Display
- Nested objects display as inline tables
- Arrays of objects show expandable preview (first 5 items)
- Complex nested data is JSON-stringified in CSV export

---

## Security Notes

- **No data logging**: Server processes data in memory only
- **No database**: No persistence layer configured
- **CSRF protection**: All POST routes protected via Flask-WTF tokens
- **SSRF prevention**: API fetch validates DNS, blocks private/internal IPs
- **Rate limiting**: Configurable per-route rate limits (Flask-Limiter), per client IP
  behind a trusted proxy (`TRUST_PROXY=1`)
- **Security headers**: CSP (`script-src 'self'`, `object-src 'none'`, `base-uri 'self'`,
  `frame-ancestors 'none'`, `form-action 'self'`, `upgrade-insecure-requests`),
  HSTS on secure requests, `Permissions-Policy`, COOP/CORP, X-Frame-Options,
  X-Content-Type-Options, Referrer-Policy, and `Cache-Control: no-store` on data responses
- **Formula-injection defense**: values starting with `=`, `+`, `-`, `@`, tab, CR or LF
  are neutralized in CSV, TSV and Excel exports, so an untrusted value cannot become a
  live formula when the file is opened. JSONL and Markdown deliberately do *not*
  get that prefix: JSON carries types and nothing evaluates it, and a leading `=`
  is inert in Markdown, so prefixing there would corrupt values while protecting
  nothing. (Markdown still escapes `|`, `\` and line breaks — that is table
  structure, not formula defense. Anyone pasting a Markdown or JSONL export into
  a spreadsheet is back to unprotected input: export CSV, TSV or Excel for that.)
- **Startup gates**: with `APP_ENV=production`, the app refuses to start on the
  development `SECRET_KEY` or with a rate-limit topology it cannot enforce
- **HTTPS**: Render provides free SSL/TLS; use Nginx/Let's Encrypt for self-hosted.
  **Required on every deployment path** — credentials are POSTed from the browser
- **Stateless**: Each request is independent, no session state

---

## Troubleshooting

### "Invalid JSON" Error
- Validate your JSON at [jsonlint.com](https://jsonlint.com)
- Check for trailing commas
- Ensure proper quote usage

### API Fetch Fails
- Verify the API URL is correct
- Check authentication credentials
- Ensure the API returns JSON (not XML/HTML)
- API must be accessible from Render's servers

### Large Files
- Maximum upload size: 10MB
- For larger files, consider pagination or pre-processing

---

## Development

```bash
# One-time setup (creates ./venv and installs dev dependencies)
make install

# Run in debug mode
export FLASK_DEBUG=1
make run                 # or: python app.py

# Everything CI runs
make check               # lint + test + test-js + audit

# Individually
make test                # python -m pytest tests/ -v
make test-js             # Node assertions for static/js/app.js (no npm install needed)
make lint                # ruff check + ruff format --check
make format              # ruff format + ruff check --fix
make audit               # pip-audit -r requirements.txt
make coverage            # test suite with a coverage report
```

Copy `.env.example` to `.env` for a local configuration reference; every value
there is the built-in default.

**Performance notes.** `/process` returns the full flattened dataset so exports
need no server round trip and nothing is persisted — responses over
`GZIP_MIN_SIZE` are gzipped to keep that affordable. The preview rows are a
truncated *copy*, so exports keep full fidelity. Excel exports are bounded by
`MAX_EXPORT_CELLS`, measured rather than guessed
(`docs/export-budget-v1.2.md`); CSV and TSV stream and stay uncapped. The JSON
tree picker builds children only when a node is opened.

---

## License

GNU General Public License v3.0 — see [`LICENSE`](LICENSE) for the full text.

---

## Support

For issues or feature requests, create an issue in the repository or contact your team admin.
