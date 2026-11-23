# Installation & Development Setup

## 1. Prerequisites

| Tool | Version | Notes |
|------|---------|-------|
| Python | 3.11 or newer (tested on 3.13) | Backend |
| Node.js | 20 or newer (tested on 22) | Frontend |
| Tesseract OCR | 4+ (optional) | Needed only for scanned PDFs |
| Git | any | |

Install Tesseract:

- **Ubuntu/Debian:** `sudo apt-get install tesseract-ocr`
- **macOS:** `brew install tesseract`
- **Windows:** install from https://github.com/UB-Mannheim/tesseract/wiki and add it to `PATH`

Without Tesseract the app still works. Scanned pages are reported as unreadable instead.

## 2. Backend

```bash
cd backend
```

```bash
python3 -m venv .venv
```

```bash
source .venv/bin/activate
```

On Windows, activate with `.venv\Scripts\activate` instead.

```bash
pip install -r requirements-dev.txt
```

```bash
cp .env.example .env
```

```bash
uvicorn app.main:app --reload --port 8000
```

- Health check: http://localhost:8000/api/health
- Swagger UI: http://localhost:8000/docs

Runtime data (SQLite database, uploads, generated PPTX) is written to `backend/storage/`, which is git-ignored
and cleaned automatically after `FILE_RETENTION_HOURS`.

### Environment variables

See [`backend/.env.example`](../backend/.env.example) for the full list. The most important ones:

| Variable | Default | Description |
|----------|---------|-------------|
| `AI_PROVIDER` | `mock` | `mock`, `claude` or `gemini` |
| `ANTHROPIC_API_KEY` | – | Claude API key (server-side only) |
| `CLAUDE_MODEL` | `claude-sonnet-5-5` | Claude model ID |
| `GEMINI_API_KEY` | – | Gemini API key (server-side only) |
| `GEMINI_MODEL` | `gemini-2.5-flash` | Gemini model ID |
| `AI_FALLBACK_TO_MOCK` | `true` | Use the offline engine if the provider fails |
| `MAX_UPLOAD_MB` | `25` | Upload size limit |
| `MAX_PAGES` | `300` | Page limit |
| `OCR_ENABLED` | `true` | Enable Tesseract OCR fallback |
| `FILE_RETENTION_HOURS` | `24` | Auto-delete uploads and outputs after this time |
| `CORS_ORIGINS` | `http://localhost:5173,...` | Allowed frontend origins |

### Securely configuring an API key

1. Create a key at https://console.anthropic.com/ (Claude) or https://aistudio.google.com/ (Gemini).
2. Put it in `backend/.env`: **never** in frontend code, never in `.env.example`, and never in a commit.
3. Set `AI_PROVIDER=claude` (or `gemini`) and restart the backend.
4. Check: `curl localhost:8000/api/providers` should show `"claude_key_present": true`. The key itself is never returned.

In production, set these as real environment variables (or your host's secret manager) instead of a `.env` file.

## 3. Frontend

```bash
cd frontend
```

```bash
npm install
```

```bash
cp .env.example .env
```

```bash
npm run dev
```

Open http://localhost:5173. In development, Vite proxies `/api` to `VITE_DEV_BACKEND_URL`
(default `http://127.0.0.1:8000`), so no CORS setup is needed.

For production, build static files and point them at the deployed API:

```bash
VITE_API_BASE_URL=https://api.example.com npm run build
```

Serve `frontend/dist/` with any static host, and add the site origin to the backend `CORS_ORIGINS`.

## 4. Running tests

```bash
cd backend && source .venv/bin/activate && pytest
```

```bash
cd frontend && npm run lint && npm run build
```

Browser end-to-end test (both servers running, `playwright` installed via `npm i -g playwright && npx playwright install chromium`):

```bash
node scripts/e2e_smoke.cjs backend/samples/photosynthesis.pdf docs/screenshots
```

Regenerate the sample PDFs:

```bash
cd backend && python scripts/make_sample_pdf.py
```

## 5. Production notes

- Run the API with multiple workers behind a reverse proxy: `uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 2`.
  Jobs run in a per-process thread pool. For heavy traffic, move `services/jobs.py` to a task queue (e.g. RQ or Celery).
- Put `STORAGE_DIR` on persistent disk, or switch `DATABASE_URL` to PostgreSQL.
- Serve over HTTPS and restrict `CORS_ORIGINS` to your domain.
