# ResumeAI — Resume Optimizer

AI-powered resume optimization SaaS. Users pay $7.99 to get:
- ATS compatibility score
- Keyword gap analysis
- Fully rewritten resume
- Tailored cover letter

## Stack
- **Backend**: FastAPI + Python
- **AI**: Claude Sonnet (Anthropic)
- **Payments**: Stripe Checkout
- **Frontend**: Vanilla HTML/CSS/JS (zero dependencies)

## Setup

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Set environment variables
cp .env.example .env
# Fill in ANTHROPIC_API_KEY, STRIPE_SECRET_KEY, BASE_URL

# 3. Run locally
uvicorn app:app --reload
# → http://localhost:8000
```

## Deploy (Railway — recommended)

1. Push this folder to a GitHub repo
2. Create a new Railway project → Deploy from GitHub
3. Add environment variables from `.env.example`
4. Railway auto-detects Python and runs `uvicorn app:app --host 0.0.0.0 --port $PORT`
5. Set `BASE_URL` to your Railway domain (e.g. `https://resumeai-production.up.railway.app`)

**Cost**: ~$5/month on Railway Starter plan.

## Economics

| Item | Cost |
|------|------|
| Hosting | ~$5/mo (Railway) |
| Claude per request | ~$0.04 (Sonnet) |
| Stripe fee | ~$0.52 (6.5% of $7.99) |
| **Net per sale** | **~$7.43** |

Break even at **1 sale/month**. At 30 sales/month = ~$220 profit.

## Notes

- Submissions are stored in memory — restart clears them. For production add Redis or a database.
- Use Stripe test keys (`sk_test_...`) during development.
