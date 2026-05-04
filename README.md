# Butcher Law Office — Document Execution Engine

Practice automation system for Butcher Law Office LLC, Eugene OR.

## What's in here

| File | Purpose |
|---|---|
| `motion_library.html` | Document Execution Engine — 65 docs, open in Chrome |
| `webhook_server.py` | Flask webhook server — runs on Railway |
| `requirements.txt` | Python dependencies |
| `Procfile` | Railway/Heroku start command |
| `railway.toml` | Railway deployment config |
| `.env.example` | Environment variable template |

## Document Execution Engine (motion_library.html)

65 documents across 9 categories:
- 10 Fee Agreements (Dropbox Sign + LawPay integrated)
- 19 Letters (Email/Fax/Mail delivery)
- 6 Time & Deadlines motions
- 14 Case Management motions
- 4 Automatic Stay motions
- 4 Discharge motions
- 2 State documents
- 2 Service documents
- 4 LBF forms (101C, 101D, 1305, Exhibit D-2)

**Login password:** Butcher2026

### Integrations
- **Dropbox Sign** — e-signatures on fee agreements
- **LawPay** — payment requests (Operating + Trust/IOLTA accounts)
- **Resend** — email delivery from tom@butcherlawoffice.com
- **RedFax** — fax delivery via email-to-fax
- **Lob** — physical mail (First Class, Certified, Certified+RR)

### Sign → Pay flow
When a VA sends an agreement for signature with an amount entered:
1. Agreement sent to client via Dropbox Sign
2. Payment intent registered with Railway server
3. Once all parties sign → Railway fires LawPay payment request automatically
4. Client receives payment email with "Pay Now" button

## Webhook Server (webhook_server.py)

Flask app handling:
- `/webhook/dropbox-sign` — receives Dropbox Sign events, triggers LawPay on full signing
- `/webhook/register-payment` — registers pending payment intent from the browser app
- `/webhook/*` — document generation routes for all 65 docs

## Deployment (Railway)

1. Push this repo to GitHub
2. Go to railway.app → New Project → Deploy from GitHub repo
3. Add environment variables from `.env.example`
4. Railway auto-deploys on every push

## Local development

```bash
pip install -r requirements.txt
cp .env.example .env
python webhook_server.py
```

## Attorney info

Tomas K. Butcher, OSB #082807  
Butcher Law Office LLC  
116 Hwy 99 N #101, Eugene, OR 97402  
(541) 762-1967 | tom@butcherlawoffice.com
