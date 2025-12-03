# JSON → Table Converter

A lightweight web tool to convert JSON data into viewable tables with CSV export capability. Designed for internal team use with zero data storage.

![Python](https://img.shields.io/badge/Python-3.11+-blue)
![Flask](https://img.shields.io/badge/Flask-3.0-green)
![License](https://img.shields.io/badge/License-MIT-yellow)

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
  - Handles nested JSON objects
  - Displays nested data as expandable tables
  - Preview first 25 rows
  - Export ALL rows to CSV

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
   - **Start Command**: `gunicorn app:app --bind 0.0.0.0:$PORT`
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

### Railway.app

```bash
# Install Railway CLI
npm install -g @railway/cli

# Login and deploy
railway login
railway init
railway up
```

### Fly.io

```bash
# Install flyctl
curl -L https://fly.io/install.sh | sh

# Deploy
fly launch
fly deploy
```

### Docker (Self-Hosted)

```dockerfile
# Dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 5000
CMD ["gunicorn", "app:app", "--bind", "0.0.0.0:5000"]
```

```bash
docker build -t json-table-tool .
docker run -p 5000:5000 json-table-tool
```

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

### 4. Export to CSV
- After conversion, click "Export CSV"
- Downloads ALL rows (not just the preview)

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
- **HTTPS**: Render provides free SSL/TLS
- **Session isolation**: Each request is independent
- **Stateless**: Server doesn't maintain session state

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
# Run in debug mode
export FLASK_DEBUG=1
python app.py

# Run tests (if added)
python -m pytest tests/
```

---

## License

MIT License - Feel free to modify and use internally.

---

## Support

For issues or feature requests, create an issue in the repository or contact your team admin.
