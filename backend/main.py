from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
from pathlib import Path
import os, json

app = FastAPI(title="INF80057 Prototype Assistant", version="0.1.0")

# Allow your GitHub Pages site to call this API (tight CORS for prototype).
FRONTEND_ORIGINS = [
    "https://eringobraugh.github.io",
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=FRONTEND_ORIGINS,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Simple kill switch via env var; production will wire this to admin control.
KILLED = os.getenv("ASSISTANT_KILLED", "false").lower() == "true"

# -------- Data loading (local, read-only) --------
DATA_DIR = Path(__file__).parent / "data"
MOCK_PATH = DATA_DIR / "mock_dates.json"
DOCS_PATH = DATA_DIR / "seed_docs.json"

def _load_json(p: Path):
    with p.open("r", encoding="utf-8") as f:
        return json.load(f)

# Start even if data missing (deploy-first safety)
try:
    MOCK = _load_json(MOCK_PATH)
except Exception:
    MOCK = {"weeks": []}
try:
    DOCS = _load_json(DOCS_PATH)
except Exception:
    DOCS = []

# -------- Models (stable API contract) --------
class AnswerRequest(BaseModel):
    role: str
    question: str
    context_policy: Optional[str] = "authoritative_only"
    mode: Optional[str] = "tutor"

class AnswerResponse(BaseModel):
    answer: str
    citations: List[Dict[str, str]]
    socratic_prompts: List[str]
    refusal: bool

class NextRequest(BaseModel):
    role: str
    state: Dict[str, Any]

# -------- Endpoints --------
@app.get("/health")
def health():
    return {"ok": not KILLED, "service": "assistant-backend", "version": "0.1.0"}

@app.post("/answer", response_model=AnswerResponse)
def answer(req: AnswerRequest):
    if KILLED:
        raise HTTPException(status_code=503, detail="Assistant paused by staff")

    q = req.question.lower().strip()

    # Deterministic keyword path for the prototype
    keywords = ["task 1", "week 4", "proposal", "planning document", "due"]
    if any(k in q for k in keywords) and DOCS:
        doc = DOCS[0]
        sec = doc["sections"][0]
        return AnswerResponse(
            answer="Task 1 Part 1 is due in Week 4. It includes the Project Proposal and Planning Document.",
            citations=[{"title": doc["title"], "href": doc["href"], "loc": sec["loc"]}],
            socratic_prompts=["Which client constraints affect your scope before Week 4?"],
            refusal=False,
        )

    # Naive overlap fallback
    q_words = [w for w in q.replace("?", " ").split() if len(w) >= 4]
    for doc in DOCS:
        for sec in doc.get("sections", []):
            text = sec.get("text", "").lower()
            if any(w in text for w in q_words):
                return AnswerResponse(
                    answer=sec.get("text", "I can only answer from authorised files."),
                    citations=[{"title": doc["title"], "href": doc["href"], "loc": sec.get("loc", "")}],
                    socratic_prompts=["What evidence from the assessment guide supports your plan?"],
                    refusal=False,
                )

    # Refuse outside authorised sources
    return AnswerResponse(
        answer="I can’t answer that from the unit’s authorised files. Try the Assessment Guide v1.0, Section 1.",
        citations=[],
        socratic_prompts=[],
        refusal=True,
    )

@app.post("/next")
def nxt(req: NextRequest):
    if KILLED:
        raise HTTPException(status_code=503, detail="Assistant paused by staff")
    week = req.state.get("week")
    items = []
    for w in MOCK.get("weeks", []):
        if w.get("week") == week:
            items = w.get("milestones", [])
            break
    if not items:
        items = ["No milestones found for this week."]
    return {"checklist": items, "refs": [{"title": "mock_dates.json", "loc": f"week:{week}"}]}
