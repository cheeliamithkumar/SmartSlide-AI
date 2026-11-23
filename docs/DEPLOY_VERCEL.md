# Deploying to Vercel

The repository deploys as **one Vercel project** that serves both parts behind a single URL:

| Part | How it runs on Vercel |
|------|-----------------------|
| React frontend | Built with `npm run build` in `frontend/`, served as static files (`frontend/dist`) |
| FastAPI backend | Python serverless function `api/index.py`, reached at `/api/*` |

Configuration lives in `vercel.json`, `requirements.txt` (root, includes `backend/requirements.txt`),
`.python-version` and `.vercelignore`.

## Serverless mode

On Vercel (detected via the `VERCEL` environment variable) the backend switches to serverless mode:

- conversion jobs run **inside** the `POST /api/jobs` request (no background threads);
- extracted PDF text is stored **in the database**, so any function instance can continue the work;
- PPTX files are rendered on demand into `/tmp` when downloaded;
- runtime files go to `/tmp/smartslide`.

## Required: a Postgres database

Function instances do not share disk, so a shared database is required for reliable operation.

1. Vercel dashboard → your project → **Storage** → **Create Database** → **Neon (Postgres)** → free plan.
2. Connect it to the project (all environments). Vercel injects `DATABASE_URL` / `POSTGRES_URL` automatically.
3. Redeploy (Deployments → ⋯ → Redeploy).

`GET /api/health` reports `"persistent_database": true` once it is connected.

## Large uploads: Vercel Blob

Vercel functions accept request bodies of at most ~4.5 MB. To allow larger PDFs, connect a
**private Blob store** (Storage → Create → Blob → Private → connect to the project). Vercel adds
`BLOB_READ_WRITE_TOKEN`, and the app switches to direct uploads automatically:

1. the browser asks `POST /api/documents/upload-token` for a short-lived token, restricted to one
   path, PDF content and `MAX_UPLOAD_MB`;
2. it uploads the file straight to private Blob storage (no size limit from the function);
3. `POST /api/documents/from-blob` downloads it once, **deletes it**, and processes it.

Only URLs from your own store's `uploads/` folder are accepted.

## Recommended environment variables

| Variable | Value | Why |
|----------|-------|-----|
| `MAX_UPLOAD_MB` | `25` with Blob, otherwise `4` | Without Blob, Vercel limits request bodies to 4.5 MB |
| `AI_PROVIDER` | `mock`, `claude` or `gemini` | AI engine |
| `ANTHROPIC_API_KEY` / `GEMINI_API_KEY` | your key | Only if using that provider. Mark as *Sensitive* |

## Limitations on Vercel

- Without a Blob store, uploads are limited to ~4 MB (platform request limit).
- Tesseract OCR is not available in Vercel functions, so scanned pages are reported as unreadable.
  Self-host (see INSTALLATION.md) for OCR.
- Each conversion must finish within the function time limit (300 s); fine for demo mode and typical documents.
