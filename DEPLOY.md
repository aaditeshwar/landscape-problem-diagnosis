# Production deployment (Apache)

Deploy the **Landscape Problem Diagnosis** stack on a Linux server with Apache as the public entry point. Apache serves the built React UI and reverse-proxies `/api/*` to the FastAPI backend (uvicorn).

## Architecture

```
Browser
   │
   ▼
Apache  :443 / :80
   ├── /              → frontend/dist/  (static SPA)
   ├── /api/*         → uvicorn :8000  (FastAPI)
   └── /static/*      → uvicorn :8000  (log dashboard, etc.)

uvicorn (runtime/)
   ├── MongoDB        diagnosis_db
   ├── Ollama         embeddings + optional local LLM
   └── Anthropic API  optional diagnosis LLM (LLM_PROVIDER=anthropic)
```

| Component | Role |
|-----------|------|
| `frontend/dist/` | React SPA (`/`, `/feedback`, `/signals`, `/revise-cards`) |
| `runtime/main.py` | FastAPI API under `/api/*` |
| MongoDB | MWS data, evidence cards, paper chunks, metadata |
| Ollama | **Required** for query embeddings (`nomic-embed-text`); also used for diagnosis when `LLM_PROVIDER=ollama` |
| `data/clusters.tif` | Optional local cluster raster; otherwise set `CLUSTER_COG_URL` |

---

## 1. Server prerequisites

Install on the host (Ubuntu/Debian examples):

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip git apache2 \
  libapache2-mod-proxy-html nodejs npm mongodb-org
```

Enable Apache proxy modules:

```bash
sudo a2enmod proxy proxy_http rewrite headers ssl
sudo systemctl reload apache2
```

Also install and run:

- **MongoDB** — listening on `localhost:27017` (or set `MONGO_URI`).
- **Ollama** — `curl -fsSL https://ollama.com/install.sh | sh`, then:
  ```bash
  ollama pull nomic-embed-text
  # If using local LLM instead of Anthropic:
  ollama pull qwen2.5:14b
  ollama pull llama3.1:8b
  ```
- **Node.js 20+** — for building the frontend (use [NodeSource](https://github.com/nodesource/distributions) or `nvm` if the distro package is too old).

---

## 2. Install the application

```bash
sudo mkdir -p /opt/landscape-diagnosis
sudo chown "$USER":"$USER" /opt/landscape-diagnosis
cd /opt/landscape-diagnosis

git clone <your-repo-url> .
# or rsync/scp from your dev machine
```

### Python virtualenv

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -r runtime/requirements.txt
pip install -r scripts/requirements.txt   # needed for ingest / card reload scripts
```

### Environment file

```bash
cp .env.example .env
nano .env
```

Minimum production settings:

```env
MONGO_URI=mongodb://127.0.0.1:27017/?directConnection=true
MONGO_DB=diagnosis_db

# Diagnosis: anthropic (recommended on a CPU-only app server) or ollama
LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-...

# Embeddings always use Ollama (same host or remote GPU box)
OLLAMA_URL=http://127.0.0.1:11434
OLLAMA_EMBED_MODEL=nomic-embed-text

# If Ollama runs on another machine:
# OLLAMA_URL=http://<gpu-host>:11434

# CORS not required when UI and API share the same Apache host; keep for direct API access if needed
CORS_ORIGINS=https://your-domain.example

LOG_DIR=/opt/landscape-diagnosis/logs
LOG_LEVEL=INFO

# CoRE Stack geometry fetch (ingest only)
CORE_STACK_API_KEY=...

# Cluster map (signal editor) — use local file or remote COG
# If data/clusters.tif exists, /api/clusters/cog is served automatically
# CLUSTER_COG_URL=https://...
# CLUSTER_COG_VIEWER_URL=https://...
```

Create the log directory:

```bash
mkdir -p logs
```

---

## 3. Load data (one-time / after updates)

Run from the repo root with the venv activated.

```bash
# Framework, variable registry, pathway queries
python scripts/load_metadata_to_mongo.py

# Ingest tehsil Excel + geometries (repeat per tehsil or use batch)
python scripts/ingest_excel.py \
  --excel data/raw_excel/Darwha_data.xlsx \
  --state Maharashtra --district Yavatmal --tehsil Darwha

# Evidence cards → Mongo (after raw JSON is present)
python scripts/reload_evidence_cards.py

# Optional: spatial index for map performance
python scripts/build_spatial_index.py
```

Verify Mongo before going live:

```bash
curl -s http://127.0.0.1:8000/api/health          # after starting API (step 4)
curl -s http://127.0.0.1:8000/api/ingested-tehsils
```

---

## 4. Build the frontend

```bash
cd frontend
npm ci
npm run build
cd ..
```

Output: `frontend/dist/` (static assets). The app calls `/api/...` on the same host, so no `VITE_*` API base URL is required.

---

## 5. Run the API with systemd

Create `/etc/systemd/system/landscape-diagnosis.service`:

```ini
[Unit]
Description=Landscape Problem Diagnosis API
After=network.target mongod.service

[Service]
Type=simple
User=www-data
Group=www-data
WorkingDirectory=/opt/landscape-diagnosis/runtime
EnvironmentFile=/opt/landscape-diagnosis/.env
ExecStart=/opt/landscape-diagnosis/.venv/bin/python -m uvicorn main:app \
  --host 127.0.0.1 --port 8000 --proxy-headers
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Ensure `www-data` can read the repo, `.env`, `data/`, `metadata/`, and write `logs/`:

```bash
sudo chown -R www-data:www-data /opt/landscape-diagnosis/logs
sudo chmod -R o+rX /opt/landscape-diagnosis
sudo systemctl daemon-reload
sudo systemctl enable --now landscape-diagnosis
sudo systemctl status landscape-diagnosis
```

Test locally:

```bash
curl http://127.0.0.1:8000/api/health
```

---

## 6. Apache virtual host

Example site: `/etc/apache2/sites-available/landscape-diagnosis.conf`

```apache
<VirtualHost *:80>
    ServerName your-domain.example
    DocumentRoot /opt/landscape-diagnosis/frontend/dist

    # Diagnosis queries can run several minutes (Ollama / Claude)
    ProxyTimeout 600
    Timeout 600

    # API → uvicorn
    ProxyPreserveHost On
    ProxyPass        /api http://127.0.0.1:8000/api retry=0 timeout=600
    ProxyPassReverse /api http://127.0.0.1:8000/api

    # FastAPI static (log dashboard at /static/logs/dashboard.html)
    ProxyPass        /static http://127.0.0.1:8000/static retry=0 timeout=60
    ProxyPassReverse /static http://127.0.0.1:8000/static

    # React Router — serve index.html for client-side routes
    <Directory /opt/landscape-diagnosis/frontend/dist>
        Options -Indexes +FollowSymLinks
        AllowOverride None
        Require all granted

        RewriteEngine On
        RewriteBase /
        RewriteRule ^index\.html$ - [L]
        RewriteCond %{REQUEST_FILENAME} !-f
        RewriteCond %{REQUEST_FILENAME} !-d
        RewriteRule . /index.html [L]
    </Directory>

    ErrorLog ${APACHE_LOG_DIR}/landscape-diagnosis-error.log
    CustomLog ${APACHE_LOG_DIR}/landscape-diagnosis-access.log combined
</VirtualHost>
```

Enable the site and reload:

```bash
sudo a2ensite landscape-diagnosis
sudo apache2ctl configtest
sudo systemctl reload apache2
```

### HTTPS

Use Certbot or your existing TLS termination:

```bash
sudo certbot --apache -d your-domain.example
```

After TLS is enabled, set `CORS_ORIGINS=https://your-domain.example` if you use it.

### Subpath deployment

The frontend assumes it is served from `/` (routes and `/api` paths are absolute). Prefer a dedicated subdomain (e.g. `diagnosis.example.org`) rather than mounting under `/some/path/` unless you add a Vite `base` and router `basename`.

---

## 7. Post-deploy checks

| Check | Command / URL |
|-------|----------------|
| API health | `curl https://your-domain.example/api/health` |
| Ingested tehsils | `https://your-domain.example/api/ingested-tehsils` |
| UI loads | Open `https://your-domain.example/` |
| SPA routes | `/feedback`, `/signals`, `/revise-cards` refresh without 404 |
| Log dashboard | `https://your-domain.example/static/logs/dashboard.html` |
| Ollama reachability | From app server: `curl $OLLAMA_URL/api/tags` |

Run a diagnosis smoke test (optional):

```bash
source .venv/bin/activate
python scripts/test/smoke_test_diagnosis.py
```

---

## 8. Redeploying updates

```bash
cd /opt/landscape-diagnosis
git pull   # or sync files

source .venv/bin/activate
pip install -r runtime/requirements.txt

# If evidence cards changed
python scripts/reload_evidence_cards.py

cd frontend && npm ci && npm run build && cd ..

sudo systemctl restart landscape-diagnosis
sudo systemctl reload apache2
```

---

## 9. Optional: `/revise-cards` review workflow

The review UI reads from `reports/claude_review/` and `metadata/claude_review_decisions.json` on the server filesystem. Copy or generate those directories on the production host if reviewers use `/revise-cards` in production. Card edits still propagate via:

```bash
python scripts/review/apply_user_card_edits.py
python scripts/reload_evidence_cards.py --prefix <card_id>
```

This workflow is typically run on a staging machine, not public production.

---

## 10. Troubleshooting

| Symptom | Likely cause |
|---------|----------------|
| `502 Bad Gateway` on `/api/*` | uvicorn not running — `journalctl -u landscape-diagnosis -f` |
| Diagnosis hangs then 504 | Increase Apache `ProxyTimeout` / `Timeout`; check `OLLAMA_CHAT_TIMEOUT` |
| `Embedding/retrieval failed` | Ollama down or wrong `OLLAMA_URL`; run `ollama pull nomic-embed-text` |
| Empty map / no tehsils | Mongo empty — re-run ingest; check `MONGO_URI` / `MONGO_DB` |
| `/revise-cards` empty | Missing `reports/claude_review/results/` on server |
| Cluster map blank | Add `data/clusters.tif` or set `CLUSTER_COG_URL` in `.env` |
| Permission errors | Ensure `www-data` owns `logs/` and can read repo + `.env` |

API logs: `/opt/landscape-diagnosis/logs/` (see `LOG_DIR` in `.env`).

Service logs: `sudo journalctl -u landscape-diagnosis -f`

Apache logs: `/var/log/apache2/landscape-diagnosis-*.log`
