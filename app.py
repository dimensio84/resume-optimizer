import os
import uuid
import json
import io

from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse
from pydantic import BaseModel
import anthropic
import stripe
import pdfplumber

app = FastAPI(title="ResumeAI")

# In-memory store — swap for Redis/Postgres in production
submissions: dict = {}

stripe.api_key = os.environ.get("STRIPE_SECRET_KEY", "")
claude = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))

BASE_URL = os.environ.get("BASE_URL", "http://localhost:8000")
PRICE_CENTS = int(os.environ.get("PRICE_CENTS", "799"))  # $7.99


# ── Models ─────────────────────────────────────────────────────────────────────

class CheckoutRequest(BaseModel):
    resume_text: str
    job_description: str


class AnalyzeRequest(BaseModel):
    session_id: str


# ── API routes ─────────────────────────────────────────────────────────────────

@app.post("/api/upload-resume")
async def upload_resume(file: UploadFile = File(...)):
    """Extract plain text from an uploaded PDF resume."""
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "Only PDF files are supported")

    content = await file.read()
    try:
        with pdfplumber.open(io.BytesIO(content)) as pdf:
            text = "\n".join(
                page.extract_text() or "" for page in pdf.pages
            ).strip()
        if not text:
            raise HTTPException(400, "Could not extract text from PDF — try pasting your resume instead")
        return {"text": text}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(400, f"Failed to parse PDF: {e}")


@app.post("/api/checkout")
async def create_checkout(req: CheckoutRequest):
    """Store submission data and create a Stripe Checkout session."""
    if not req.resume_text.strip():
        raise HTTPException(400, "Resume text is required")
    if not req.job_description.strip():
        raise HTTPException(400, "Job description is required")

    submission_id = str(uuid.uuid4())
    submissions[submission_id] = {
        "resume_text": req.resume_text,
        "job_description": req.job_description,
        "result": None,
    }

    try:
        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            line_items=[
                {
                    "price_data": {
                        "currency": "usd",
                        "product_data": {
                            "name": "AI Resume Optimizer",
                            "description": "ATS score · optimized resume · tailored cover letter",
                        },
                        "unit_amount": PRICE_CENTS,
                    },
                    "quantity": 1,
                }
            ],
            mode="payment",
            success_url=f"{BASE_URL}/?session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{BASE_URL}/",
            metadata={"submission_id": submission_id},
        )
    except stripe.error.StripeError as e:
        raise HTTPException(500, f"Stripe error: {e.user_message}")

    return {"url": session.url}


@app.post("/api/analyze")
async def analyze(req: AnalyzeRequest):
    """Verify payment then run Claude analysis. Results are cached per submission."""
    try:
        session = stripe.checkout.Session.retrieve(req.session_id)
    except stripe.error.InvalidRequestError:
        raise HTTPException(400, "Invalid session ID")

    if session.payment_status != "paid":
        raise HTTPException(402, "Payment not completed")

    submission_id = session.metadata.get("submission_id")
    if not submission_id or submission_id not in submissions:
        raise HTTPException(404, "Submission not found — it may have expired. Please start over.")

    sub = submissions[submission_id]

    # Return cached result on repeated calls (e.g., page refresh)
    if sub["result"]:
        return sub["result"]

    result = _run_claude_analysis(sub["resume_text"], sub["job_description"])
    sub["result"] = result
    return result


# ── Claude analysis ────────────────────────────────────────────────────────────

def _run_claude_analysis(resume_text: str, job_description: str) -> dict:
    prompt = f"""You are an expert resume coach and ATS (Applicant Tracking System) specialist.

Analyze the resume below against the job description and return a JSON object with EXACTLY this structure (no markdown, no extra keys):

{{
  "ats_score": <integer 0-100>,
  "score_explanation": "<2-3 sentence explanation of the score>",
  "missing_keywords": ["<keyword>", ...],
  "improvements": ["<specific actionable improvement>", ...],
  "optimized_resume": "<full rewritten resume in plain text>",
  "cover_letter": "<full tailored cover letter in plain text>"
}}

Rules:
- missing_keywords: up to 10 important terms/skills from the job description absent from the resume
- improvements: 5-8 specific, actionable bullet points (e.g. "Add 'Python' to Skills section")
- optimized_resume: complete rewrite preserving all true facts, improving wording and keyword density
- cover_letter: professional, 3-paragraph letter tailored to this specific role

RESUME:
{resume_text}

JOB DESCRIPTION:
{job_description}"""

    message = claude.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = message.content[0].text
    # Strip markdown code fences if present
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1]
        raw = raw.rsplit("```", 1)[0]

    start = raw.find("{")
    end = raw.rfind("}") + 1
    return json.loads(raw[start:end])


# ── Static files (must be last) ────────────────────────────────────────────────

app.mount("/", StaticFiles(directory="static", html=True), name="static")
