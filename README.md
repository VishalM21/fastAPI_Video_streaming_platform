# StreamVault 🎬
> A private, self-hosted video library — FastAPI + S3 + Jinja2, no JS frameworks.

---

## Project Layout

```
streamvault/
├── main.py            # FastAPI app, all routes
├── models.py          # SQLAlchemy ORM model (Video)
├── database.py        # Async engine + session factory
├── s3_service.py      # All Boto3 / S3 operations
├── config.py          # Pydantic settings (reads .env)
├── requirements.txt
├── .env.example       # Copy to .env and fill in
├── static/
│   └── css/
│       └── style.css  # Dark "StreamVault" theme
└── templates/
    ├── layout.html    # Base template (navbar, footer)
    ├── index.html     # Gallery view
    ├── video_player.html
    └── upload.html
```

---

## Quick-start (local)

### 1. Prerequisites

| Tool | Version |
|------|---------|
| Python | 3.11+ |
| pip | latest |
| AWS account | — |

### 2. Clone / unzip and enter the directory

```bash
cd streamvault
```

### 3. Create and activate a virtual environment

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
```

### 4. Install dependencies

```bash
pip install -r requirements.txt
# pydantic-settings is needed for config.py — install separately if missing:
pip install pydantic-settings
```

### 5. Configure environment variables

```bash
cp .env.example .env
```

Open `.env` and fill in **at minimum**:

```env
AWS_ACCESS_KEY_ID=AKIA...
AWS_SECRET_ACCESS_KEY=...
AWS_REGION=us-east-1
S3_BUCKET_NAME=my-streamvault-bucket
```

The default database is SQLite (`streamvault.db` — created automatically).
Switch to PostgreSQL by changing `DATABASE_URL` (see `.env.example`).

### 6. S3 Bucket setup

1. Create a private S3 bucket (block all public access ✓).
2. Attach an IAM policy to your credentials that allows:
   ```json
   {
     "Effect": "Allow",
     "Action": ["s3:PutObject","s3:GetObject","s3:DeleteObject"],
     "Resource": "arn:aws:s3:::YOUR-BUCKET-NAME/*"
   }
   ```
3. That's it — **no bucket policy needed** (access is via presigned URLs only).

### 7. Run the server

```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

Open **http://localhost:8000** in your browser.

---

## Bundling into a ZIP for deployment

Run this from **outside** the `streamvault/` folder:

```bash
zip -r streamvault.zip streamvault/ \
  --exclude "streamvault/.venv/*" \
  --exclude "streamvault/__pycache__/*" \
  --exclude "streamvault/*.pyc" \
  --exclude "streamvault/*.db" \
  --exclude "streamvault/.env"
```

**On Windows (PowerShell):**
```powershell
Compress-Archive -Path streamvault -DestinationPath streamvault.zip
```

Then on the target machine:
```bash
unzip streamvault.zip
cd streamvault
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt pydantic-settings
cp .env.example .env   # edit with real credentials
uvicorn main:app --host 0.0.0.0 --port 8000
```

---

## Architecture notes

| Concern | Decision | Why |
|---------|----------|-----|
| Upload storage | AWS S3 (private) | Scalable, durable, cheap |
| DB write timing | `BackgroundTasks` after S3 upload | Response is sent fast; DB write is async |
| Video delivery | S3 Presigned URLs | Zero server bandwidth; browser streams directly from S3 |
| Auth/sessions | None (add FastAPI-Users for prod) | Out of scope for this template |
| JS framework | **None** — vanilla JS snippets only | Per constraint; Jinja2 server-renders everything |

### Data flow

```
Browser ──POST /upload──► FastAPI
                          │  1. Validate file
                          │  2. Upload to S3 (boto3.upload_fileobj)
                          │  3. Add BackgroundTask → write DB row
                          └──► 303 Redirect to /video/{id}

Browser ──GET /video/{id}──► FastAPI
                             │  1. Fetch Video from DB
                             │  2. boto3.generate_presigned_url(s3_key)
                             └──► Render video_player.html
                                  <video src="PRESIGNED_URL">

Browser ──► S3 (direct, no proxy) ──► video bytes
```

---

## Production checklist

- [ ] Set `DATABASE_URL` to PostgreSQL
- [ ] Put the app behind **nginx** or an ALB
- [ ] Enable HTTPS (Let's Encrypt / ACM)
- [ ] Add authentication (FastAPI-Users, Auth0, etc.)
- [ ] Set `PRESIGNED_URL_EXPIRY` to a sensible value (e.g. 3600 s)
- [ ] Enable S3 server-side encryption (SSE-S3 or SSE-KMS)
- [ ] Configure CORS on the bucket if embedding cross-origin
- [ ] Run with `uvicorn main:app --workers 4` or use Gunicorn
