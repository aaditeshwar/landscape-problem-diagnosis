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
| `frontend/dist/` | React SPA (`/`, `/diagnose`, `/feedback`, `/review`, `/logs`, `/triaging`, `/dashboard`, …) |
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

# Cluster map (signal editor)
# The browser always loads /api/clusters/cog; the API proxies CLUSTER_COG_URL server-side.
# Use 127.0.0.1:10001 here — that is correct for the backend, not for the user's browser.
# CLUSTER_COG_URL=http://127.0.0.1:10001/clusters.tif
# CLUSTER_COG_VIEWER_URL=http://127.0.0.1:10001/raster.html
# Or place data/clusters.tif in the repo and omit CLUSTER_COG_URL.
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

# Spatial index for map — required on production (file is not in git).
# Without it the API falls back to MongoDB tehsil_boundaries (dissolved on the fly).
python scripts/build_spatial_index.py

# Variable dashboard (/dashboard) — precomputes CDF charts under data/triage_dashboard/
# Sections = case-study catalog + evidence-card sections (empty charts when no built cards).
python scripts/triage/build_variable_dashboard.py
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

Output: `frontend/dist/` (static assets).

- **Root deploy** (`https://host/`): default build uses `base: /` and API paths `/api/...`.
- **Subpath deploy** (`https://host/core-insights/`): `frontend/.env.production` sets `VITE_BASE_PATH=/core-insights/`. Assets, routes, and API calls are prefixed automatically. Rebuild after changing the path.

To use a different subpath, edit `VITE_BASE_PATH` in `frontend/.env.production` (must start and end with `/`).

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

### Subpath deployment (`/core-insights/`)

When the app is mounted under a path prefix (not the vhost root), use the production build (`VITE_BASE_PATH=/core-insights/` in `frontend/.env.production`) and Apache config like:

```apache
# Static SPA under /core-insights/
Alias /core-insights /opt/landscape-diagnosis/frontend/dist

<Directory /opt/landscape-diagnosis/frontend/dist>
    Options -Indexes +FollowSymLinks
    AllowOverride None
    Require all granted

    RewriteEngine On
    RewriteBase /core-insights/
    RewriteRule ^index\.html$ - [L]
    RewriteCond %{REQUEST_FILENAME} !-f
    RewriteCond %{REQUEST_FILENAME} !-d
    RewriteRule . /core-insights/index.html [L]
</Directory>

# API under the same prefix
ProxyPass        /core-insights/api http://127.0.0.1:8000/api retry=0 timeout=600
ProxyPassReverse /core-insights/api http://127.0.0.1:8000/api

# Optional: log dashboard
ProxyPass        /core-insights/static http://127.0.0.1:8000/static retry=0 timeout=60
ProxyPassReverse /core-insights/static http://127.0.0.1:8000/static
```

Open `http://your-host/core-insights/` (trailing slash optional; Apache usually redirects).

For a **root** vhost (`DocumentRoot` = `frontend/dist`), keep `VITE_BASE_PATH=/` (remove or comment out `frontend/.env.production`) and use the main virtual host example above with `/api` proxy paths.

---

## 7. Post-deploy checks

| Check | Command / URL |
|-------|----------------|
| API health | `curl https://your-domain.example/api/health` |
| Ingested tehsils | `https://your-domain.example/api/ingested-tehsils` |
| UI loads | Open `https://your-domain.example/` |
| SPA routes | `/`, `/diagnose`, `/feedback`, `/review`, `/logs`, `/triaging`, `/dashboard` refresh without 404 |
| Log dashboard | `https://your-domain.example/logs` (SPA) or `/api/logs/dashboard` |
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

## 10. Diagnosis logs and query evaluation on production

### Where logs live

Diagnosis run events are appended to **`logs/diagnosis.jsonl`** (path from `LOG_DIR` in `.env`, e.g. `/opt/landscape-diagnosis/logs/diagnosis.jsonl`). The API exposes them at `/api/logs/*`; the UI serves a public viewer at **`/logs`** (embeds `/api/logs/dashboard`).

`logs/diagnosis.log` and `logs/server.log` are plain-text service logs and are **not** pruned by the cleanup script below.

### Pruning logs locally

Use `scripts/maintenance/cleanup_diagnosis_logs.py` on a dev or staging machine before copying a small, curated set to production.

```bash
source .venv/bin/activate

# Preview: keep only events referenced by query-eval batches
python scripts/maintenance/cleanup_diagnosis_logs.py --only-query-eval --dry-run

# Apply (creates logs/diagnosis.jsonl.bak.<timestamp> first)
python scripts/maintenance/cleanup_diagnosis_logs.py --only-query-eval
```

Other modes:

| Flag | Effect |
|------|--------|
| `--all` | Delete every event (combine with `--keep-query-eval` to spare eval rows) |
| `--before YYYY-MM-DD` | Delete events with timestamp strictly before that UTC date |
| `--session-ids id1,id2` | Delete events for those `session_id` values |
| `--keep-query-eval` | Never delete rows referenced in `reports/query_eval/` |
| `--dry-run` | Print plan only |
| `--no-backup` | Skip writing a `.bak` copy |

When events are removed, the script **remaps `log_index`** inside `reports/query_eval/**` (manifest, responses, evaluations) so feedback links stay consistent with the compacted JSONL. Copy the **updated** batch folder together with the pruned `diagnosis.jsonl`.

### Copy query evaluation + logs to production

Query evaluation batches live under **`reports/query_eval/`** (gitignored). The `/review` app reads them from disk; feedback links load the corresponding row from **`diagnosis.jsonl`** via `log_index`. Both must be present on the server and must match after any cleanup/remap.

From your dev machine (adjust host and paths):

```bash
# Pruned diagnosis log
scp logs/diagnosis.jsonl user@production:/opt/landscape-diagnosis/logs/diagnosis.jsonl

# One eval batch (entire directory, including remapped manifest + responses)
scp -r reports/query_eval/query_eval__pilot_v2_20260625T131416Z \
  user@production:/opt/landscape-diagnosis/reports/query_eval/
```

On the production host:

```bash
sudo mkdir -p /opt/landscape-diagnosis/reports/query_eval
sudo chown www-data:www-data /opt/landscape-diagnosis/logs/diagnosis.jsonl
sudo chown -R www-data:www-data /opt/landscape-diagnosis/reports/query_eval/
```

No API restart is required — files are read on each request. Verify:

```bash
curl -s https://your-domain.example/api/logs/meta | head
curl -s https://your-domain.example/api/query-eval/batches
```

Open **`/review`** in the browser and confirm feedback links load.

**Feedback URLs:** manifests may still contain `http://localhost:5173/feedback?...` from a local eval run. On production, links should use your public base (e.g. `https://your-domain.example/core-insights/feedback?...`). Re-run `scripts/eval/run_query_eval.py` with the production frontend base, or edit `feedback_url` fields in the batch manifest after copy.

To generate a fresh batch on production instead of copying, run the eval scripts on the server (with Mongo and LLM configured) so sessions and logs are created in place.

---

## 11. Troubleshooting

| Symptom | Likely cause |
|---------|----------------|
| `502 Bad Gateway` on `/api/*` | uvicorn not running — `journalctl -u landscape-diagnosis -f` |
| Diagnosis hangs then 504 | Increase Apache `ProxyTimeout` / `Timeout`; check `OLLAMA_CHAT_TIMEOUT` |
| `Embedding/retrieval failed` | Ollama down or wrong `OLLAMA_URL`; run `ollama pull nomic-embed-text` |
| Empty map / no tehsils | Mongo empty — re-run ingest; check `MONGO_URI` / `MONGO_DB` |
| `/dashboard` empty | Run `python scripts/triage/build_variable_dashboard.py` (writes `data/triage_dashboard/`) |
| `/revise-cards` empty | Missing `reports/claude_review/results/` on server |
| `/review` empty or feedback 404 | Missing `reports/query_eval/<batch>/` or `logs/diagnosis.jsonl`; copy both (see §10) |
| `/logs` blank or `404` on subpath deploy | Log dashboard fetches API under `/api/logs/*`; on subpath installs use `/core-insights/api/logs/...` (see §11.1). Rebuild frontend and restart API after updating `dashboard.html`. |
| Cluster map blank | Set `CLUSTER_COG_URL` (e.g. `http://127.0.0.1:10001/clusters.tif`) or add `data/clusters.tif`; confirm COG server is up and `curl -I http://127.0.0.1:10001/clusters.tif` works on the host |
| Permission errors | Ensure `www-data` owns `logs/` and can read repo + `.env` |

### 11.1 API down — `503 Service Unavailable` on `/api/*`

Apache returns **503** when the reverse proxy cannot reach uvicorn. The React shell may still load; API-backed pages show HTML error bodies instead of JSON.

**Confirm the service is crash-looping:**

```bash
sudo systemctl status landscape-diagnosis
sudo journalctl -u landscape-diagnosis -n 80 --no-pager
```

**Reproduce manually** (same paths as the unit file):

```bash
cd /path/to/landscape-problem-diagnosis
source .venv/bin/activate
cd runtime
python -m uvicorn main:app --host 127.0.0.1 --port 8000
```

In another shell: `curl -s http://127.0.0.1:8000/api/health` should return `{"status":"ok"}`.

| Log / symptom | Fix |
|---------------|-----|
| `ModuleNotFoundError: No module named 'main'` | Set `WorkingDirectory=.../runtime` in the systemd unit (`main:app` resolves only from `runtime/`). |
| `ServerSelectionTimeoutError` (Mongo) | Fix `MONGO_URI` in `.env`; from the host run a pymongo `ping` (see §2). Startup fails if Mongo is unreachable. |
| `Permission denied` on `logs/` | `mkdir -p logs && chown` to the service user (`www-data` or deploy user). |
| Import / package errors after `git pull` | `pip install -r runtime/requirements.txt` |
| Manual start works, systemd fails | Check `User=`, `EnvironmentFile=`, and file permissions on `.env` and the repo. |

**Example unit paths** (adjust to your install):

```ini
WorkingDirectory=/home/aseth/core-stack/landscape-problem-diagnosis/runtime
EnvironmentFile=/home/aseth/core-stack/landscape-problem-diagnosis/.env
ExecStart=/home/aseth/core-stack/landscape-problem-diagnosis/.venv/bin/python -m uvicorn main:app \
  --host 127.0.0.1 --port 8000 --proxy-headers
```

After fixes: `sudo systemctl daemon-reload && sudo systemctl restart landscape-diagnosis`.

**Apache vs API:** once `curl http://127.0.0.1:8000/api/health` works, test through Apache:

```bash
# Root deploy
curl -s http://localhost/api/health

# Subpath deploy (e.g. act4d.iitd.ac.in/core-insights/)
curl -s http://localhost/core-insights/api/health
```

If local `:8000` works but Apache still 503, the vhost `ProxyPass` prefix does not match the public URL.

### 11.2 `/logs` returns 404 on subpath deploy

The `/logs` page embeds `/api/logs/dashboard`. That HTML page calls `/api/logs/meta` and `/api/logs/events`. On a subpath install (`VITE_BASE_PATH=/core-insights/`), those requests must go to **`/core-insights/api/logs/...`**, not `/api/logs/...` (which Apache does not proxy).

The log dashboard script reads the API prefix from the `api_base` query parameter (set by the `/logs` React page), from `window.location.pathname`, or from `/static/logs/dashboard.html` mounts.

**Verify on the server:**

```bash
curl -s "http://localhost/core-insights/api/logs/meta" | head
curl -s "http://localhost/core-insights/api/logs/dashboard?api_base=/core-insights/api/logs" | head
```

Both should return JSON / HTML respectively. Then open `https://your-host/core-insights/logs`.

Ensure Apache proxies the prefixed API (see §6 subpath example):

```apache
ProxyPass        /core-insights/api http://127.0.0.1:8000/api retry=0 timeout=600
ProxyPassReverse /core-insights/api http://127.0.0.1:8000/api
```

Restart API after updating `runtime/static/logs/dashboard.html` (no frontend rebuild required for that file alone; restart uvicorn or touch the service).

---

API logs: `/opt/landscape-diagnosis/logs/` (see `LOG_DIR` in `.env`).

Service logs: `sudo journalctl -u landscape-diagnosis -f`

Apache logs: `/var/log/apache2/landscape-diagnosis-*.log`
