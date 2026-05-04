# Video streaming platform 🎬

---

## Project Layout

```
fastAPI_Video_streaming_platform/
├── main.py            
├── models.py          
├── database.py        
├── s3_service.py      
├── config.py          
├── requirements.txt
├── .env.example       
├── static/
│   └── css/
│       └── style.css  
└── templates/
    ├── layout.html    
    ├── index.html    
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
