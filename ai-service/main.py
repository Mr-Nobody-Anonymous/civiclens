"""CivicLens Ethiopia — Local AI Analysis Service (FastAPI).

Runs fully on-premise. Analyzes report text + extracted video frames /
images and returns a structured classification.

Model layer is pluggable (AI_MODEL env var):
  heuristic  — built-in multilingual (English + Amharic) keyword/signal
               classifier. Zero dependencies, always available. (default)
  ollama     — any local Ollama model (e.g. llava for vision, llama3.x for
               text). Set OLLAMA_URL / OLLAMA_MODEL. Falls back to the
               heuristic engine when the Ollama server is unreachable.

Swap in a better local model later by adding another Analyzer subclass —
the backend contract (POST /analyze) never changes.
"""
import json
import os
from typing import List, Optional

import httpx
from fastapi import FastAPI, Request
from pydantic import BaseModel

MODEL_KIND = os.environ.get("AI_MODEL", "heuristic")
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llava:7b")
SERVICE_VERSION = "1.2.0"

app = FastAPI(title="CivicLens Local AI Service", version=SERVICE_VERSION)

CATEGORIES = [
    "Roads & Transportation", "Garbage & Sanitation", "Water", "Electricity",
    "Telecom", "Education", "Public Buildings", "Safety", "Environment", "Other",
]


class AnalyzeRequest(BaseModel):
    title: str = ""
    description: str = ""
    comments: str = ""
    user_category: Optional[str] = None
    city: Optional[str] = None
    address: Optional[str] = None
    frames_b64: List[str] = []          # JPEG frames extracted from video
    images_b64: List[str] = []          # photo evidence
    video_meta: Optional[dict] = None


class AnalyzeResponse(BaseModel):
    category: str
    issue_type: str
    severity: int
    confidence: float
    urgency: str
    organization_type: str
    responsible_organization: str
    reasoning: str
    model_name: str
    model_version: str
    frames_analyzed: int = 0


# --------------------------------------------------------------------------
# Heuristic multilingual analyzer (English + Amharic keywords)
# --------------------------------------------------------------------------
KB = {
    "Roads & Transportation": {
        "org_type": "Roads/Public Works",
        "org": "City Roads Authority",
        "keywords": [
            "road", "pothole", "asphalt", "traffic", "sidewalk", "pavement", "bridge",
            "crossing", "highway", "street", "junction", "roundabout", "taxi", "bus stop",
            "መንገድ", "ጉድጓድ", "አስፋልት", "ትራፊክ", "ድልድይ", "እግረኛ", "ተበላሽቷል", "ተሰብሯል", "መንገዱ", "ኮብልስቶን", "መተላለፊያ", "መኪና", "አውቶቡስ", "ታክሲ",
        ],
        "issues": {
            "pothole": ["pothole", "hole", "ጉድጓድ", "crater"],
            "damaged sidewalk": ["sidewalk", "pavement", "እግረኛ"],
            "damaged bridge": ["bridge", "ድልድይ"],
            "traffic signal fault": ["traffic light", "signal", "የትራፊክ መብራት"],
            "road damage": [],
        },
        "danger": ["accident", "crash", "vehicle damage", "injur", "deep", "wide", "main road",
                   "school", "hospital", "collapse", "አደጋ"],
    },
    "Garbage & Sanitation": {
        "org_type": "Sanitation/Municipality",
        "org": "City Sanitation & Beautification",
        "keywords": ["garbage", "trash", "waste", "rubbish", "dump", "sewage", "smell", "sanitation",
                     "landfill", "litter", "ቆሻሻ", "ፍሳሽ", "ሽታ", "ቆሻሻው", "ተከምሯል", "ገንዳ", "ጽዳት", "መጣያ"],
        "issues": {
            "overflowing garbage": ["overflow", "pile", "heap", "የተከመረ"],
            "sewage overflow": ["sewage", "sewer", "ፍሳሽ"],
            "illegal dumping": ["dumping", "dump site"],
            "uncollected waste": [],
        },
        "danger": ["disease", "cholera", "children", "school", "market", "clinic", "weeks", "rats",
                   "በሽታ"],
    },
    "Water": {
        "org_type": "Water Utility",
        "org": "Water & Sewerage Authority",
        "keywords": ["water", "pipe", "leak", "burst", "tap", "supply", "shortage", "flood",
                     "drinking", "ውሃ", "ቧንቧ", "ፍሳሽ", "ጎርፍ", "ውሃው", "ተቋርጧል", "እየፈሰሰ", "ንጹህ ውሃ", "የመጠጥ ውሃ"],
        "issues": {
            "pipe burst": ["burst", "broken pipe", "የተሰበረ ቧንቧ"],
            "water leak": ["leak", "leaking", "ፍሳሽ"],
            "water shortage": ["shortage", "no water", "cut", "ውሃ የለም"],
            "flooding": ["flood", "ጎርፍ"],
            "water issue": [],
        },
        "danger": ["days", "week", "neighborhood", "contaminat", "drinking", "hospital", "main line",
                   "wast", "street flooded"],
    },
    "Electricity": {
        "org_type": "Electric Utility",
        "org": "Ethiopian Electric Utility",
        "keywords": ["electric", "power", "outage", "blackout", "streetlight", "street light", "street lights", "streetlights", "lights not working", "dark at night", "pole",
                     "wire", "cable", "transformer", "መብራት", "ኤሌክትሪክ", "ኃይል", "ገመድ", "የመንገድ መብራት", "አምፖል"],
        "issues": {
            "broken streetlight": ["streetlight", "street light", "lamp", "የመንገድ መብራት"],
            "fallen power line": ["fallen", "wire", "cable", "live wire", "የወደቀ ገመድ"],
            "power outage": ["outage", "blackout", "no power", "መብራት የለም"],
            "damaged transformer": ["transformer", "ትራንስፎርመር"],
            "electrical fault": [],
        },
        "danger": ["live", "exposed", "spark", "fire", "child", "touch", "fell", "electrocut", "እሳት"],
    },
    "Telecom": {
        "org_type": "Telecom",
        "org": "Ethio telecom",
        "keywords": ["network", "internet", "telecom", "mobile", "signal", "sim", "data", "call",
                     "fiber", "4g", "5g", "wifi", "ኔትወርክ", "ስልክ", "ኢንተርኔት", "ኔትወርኩ", "ሲም", "ዳታ", "ጥሪ", "ተቋርጧል"],
        "issues": {
            "network outage": ["no network", "no signal", "outage", "down", "ኔትወርክ የለም"],
            "damaged telecom cable": ["cable", "fiber", "ገመድ"],
            "poor connectivity": ["slow", "weak", "poor", "ደካማ"],
            "telecom service issue": [],
        },
        "danger": ["business", "bank", "hospital", "emergency", "school", "days", "entire", "area"],
    },
    "Education": {
        "org_type": "Education Bureau",
        "org": "City Education Bureau",
        "keywords": ["school", "classroom", "student", "teacher", "education", "desk", "library",
                     "ትምህርት", "ተማሪ", "ትምህርት ቤት", "መምህር"],
        "issues": {
            "damaged classroom": ["classroom", "roof", "wall", "ክፍል"],
            "lack of facilities": ["desk", "chair", "toilet", "latrine", "water"],
            "school infrastructure problem": [],
        },
        "danger": ["collapse", "injur", "children", "unsafe", "rain", "crack"],
    },
    "Public Buildings": {
        "org_type": "Municipality",
        "org": "City Administration",
        "keywords": ["building", "office", "clinic", "health center", "public", "government",
                     "collapse", "roof", "ህንፃ", "ቢሮ", "ጤና ጣቢያ"],
        "issues": {
            "unsafe structure": ["collapse", "crack", "unsafe", "ስንጥቅ"],
            "building maintenance": [],
        },
        "danger": ["collapse", "crack", "fall", "people inside", "crowd"],
    },
    "Safety": {
        "org_type": "Public Safety",
        "org": "City Administration",
        "keywords": ["danger", "unsafe", "crime", "manhole", "open manhole", "open hole", "uncovered hole", "fell in", "fence", "fire",
                     "አደጋ", "ደህንነት", "እሳት"],
        "issues": {
            "open manhole": ["manhole", "open hole", "ክፍት ጉድጓድ"],
            "fire hazard": ["fire", "እሳት"],
            "public safety hazard": [],
        },
        "danger": ["child", "fell", "night", "injur", "dead", "urgent"],
    },
    "Environment": {
        "org_type": "Environment Bureau",
        "org": "Environmental Protection Authority",
        "keywords": ["pollution", "tree", "river", "smoke", "chemical", "deforestation", "air",
                     "አካባቢ", "ብክለት", "ዛፍ", "ወንዝ"],
        "issues": {
            "river pollution": ["river", "ወንዝ"],
            "air pollution": ["smoke", "air", "ጭስ"],
            "tree cutting": ["tree", "cut", "ዛፍ"],
            "environmental issue": [],
        },
        "danger": ["chemical", "toxic", "health", "drinking", "factory"],
    },
    "Other": {
        "org_type": "Municipality",
        "org": "City Administration",
        "keywords": [],
        "issues": {"general issue": []},
        "danger": [],
    },
}

URGENT_WORDS = ["urgent", "emergency", "danger", "now", "immediately", "life", "death", "accident",
                "injur", "child", "fire", "collapse", "አስቸኳይ", "አደጋ", "እሳት", "በጣም", "አደገኛ",
                "ህይወት", "ልጆች", "ተጎድቷል", "ወዲያውኑ", "ጉዳት"]
SCALE_WORDS = ["entire", "whole", "many", "hundreds", "thousands", "neighborhood", "kebele",
               "district", "everyone", "all", "days", "weeks", "months", "main", "busy", "school",
               "hospital", "market", "ሁሉም", "ብዙ", "ቀናት", "ሳምንታት", "ወራት", "ሰፈር", "ቀበሌ",
               "ክፍለ ከተማ", "ትምህርት ቤት", "ሆስፒታል", "ገበያ", "ዋና"]


ETHIOPIC = lambda t: sum(1 for ch in t if '\u1200' <= ch <= '\u137f')  # noqa: E731


# High-signal tokens that separate languages sharing a script:
#   Afaan Oromo — Latin script (vs English), distinctive orthography/function words
#   Tigrinya    — Ethiopic script (vs Amharic), distinctive function words/verbs
_OROMO_TOKENS = (
    "keessa", "keessatti", "jira", "jiru", "hin ", "kan ", "fi ", "irratti", "irraa",
    "waan", "akka", "kun", "sun", "ta'e", "ta'ee", "guddaa", "baay'ee", "daandii",
    "bishaan", "ibsaa", "balfa", "mana barumsaa", "cabee", "cite", "hojjetamuu",
    "gargaarsa", "rakkoo", "naannoo", "magaalaa", "dhaabbata", "waggaa", "torban",
)
_TIGRINYA_TOKENS = (
    "እዩ", "እያ", "ኣሎ", "ኣላ", "የለን", "ኣብ ", "እዚ", "እታ", "እቲ", "ኣይ", "ኮይኑ",
    "ተባላሽዩ", "ተቛሪጹ", "ጸገም", "ኣዝዩ", "ቀጻሊ", "ንሕና", "ናትና", "ሓደ", "ክልተ",
    "ዘሎ", "ዘላ", "እንተ", "ድማ", "ግን ", "ካብ ", "ናብ ", "ምስ ", "ጽቡቕ", "ሕማቕ",
)


def detect_language(text: str) -> str:
    """en / am / om / ti by script + distinctive-token analysis.

    Ethiopic-dominant: Tigrinya if Tigrinya-specific tokens dominate, else
    Amharic. Latin-dominant: Afaan Oromo if Oromo tokens found, else English.
    """
    eth = ETHIOPIC(text)
    latin = sum(1 for ch in text if ch.isascii() and ch.isalpha())
    low = text.lower()
    if eth > latin * 0.5 and eth > 3:
        ti_hits = sum(1 for t in _TIGRINYA_TOKENS if t in text)
        return "ti" if ti_hits >= 2 else "am"
    om_hits = sum(1 for t in _OROMO_TOKENS if t in low)
    return "om" if om_hits >= 2 else "en"


AM_REASON = {
    "matched": "ለ'{cat}' {n} ምልክቶች ተገኝተዋል።",
    "danger": "{n} የአደጋ ምልክቶች በመግለጫው ውስጥ ተገኝተዋል።",
    "scale": "ቋንቋው ሰፊ አካባቢ ወይም ብዙ ሰዎች መጎዳታቸውን ያሳያል።",
    "urgent": "አስቸኳይነትን የሚያሳዩ ቃላት አሉ።",
    "media": "{n} የእይታ ማስረጃዎች ተያይዘዋል።",
    "disagree": "ማሳሰቢያ፡ ሪፖርተኩ '{user}' መርጧል፤ ጽሁፉ ግን ወደ '{cat}' ያመለክታል።",
}


# Afaan Oromo (om) + Tigrinya (ti) category keywords — supplementary layer
# merged with KB keywords at scoring time (v1.4).
OM_TI_KEYWORDS = {
    "Roads & Transportation": [
        # om
        "daandii", "boolla", "karaa", "cabee", "riqicha", "konkolaataa", "asfaaltii", "tiraafikaa",
        # ti
        "መንገዲ", "ጉድጓድ", "ጽርግያ", "ድልድል", "መኪና", "ኣስፋልት", "ትራፊክ", "ተሰይሩ",
    ],
    "Garbage & Sanitation": [
        "balfa", "kosii", "xurii", "dhoqqee", "foolii", "qulqullina",
        "ጓሓፍ", "ረሳሕ", "ጨና", "ጽሬት", "እኩብ ጓሓፍ",
    ],
    "Water": [
        "bishaan", "ujummoo", "dhangala'aa", "hanqina bishaanii", "lolaa", "bishaan dhugaatii",
        "ማይ", "ቡምባ", "ምፍሳስ", "ዕጥረት ማይ", "ውሕጅ", "ዝስተ ማይ", "ተቛሪጹ",
    ],
    "Electricity": [
        "ibsaa", "elektirikii", "humna", "shiboo", "tiraansfoormarii", "ibsaa daandii", "ifaa hin jiru",
        "መብራህቲ", "ኤሌክትሪክ", "ሓይሊ", "ገመድ", "ትራንስፎርመር", "መብራህቲ የለን", "ወዲቑ ገመድ",
    ],
    "Telecom": [
        "networkii", "intarneetii", "bilbilaa", "mallattoo", "moobayilii",
        "ኔትወርክ", "ኢንተርነት", "ተሌፎን", "ሲግናል", "ሞባይል",
    ],
    "Education": [
        "mana barumsaa", "barattoota", "barsiisaa", "daree", "kitaaba",
        "ቤት ትምህርቲ", "ተማሃሮ", "መምህር", "ክፍሊ", "መጽሓፍ",
    ],
    "Public Buildings": [
        "gamoo", "waajjira", "kilinika", "mootummaa", "hospitaala",
        "ህንጻ", "ቤት ጽሕፈት", "ክሊኒክ", "መንግስቲ", "ሆስፒታል",
    ],
    "Safety": [
        "balaa", "sodaachisaa", "boolla banaa", "ibidda", "hanna", "nageenya",
        "ሓደጋ", "ኣስጋኢ", "ክፉት ጉድጓድ", "ሓዊ", "ስርቂ", "ድሕንነት",
    ],
    "Environment": [
        "faalama", "muka", "laga", "aara", "keemikaala", "naannoo",
        "ብከላ", "ኦም", "ሩባ", "ትኪ", "ከሚካል", "ከባቢ",
    ],
    "Other": [],
}


class HeuristicAnalyzer:
    name = "civiclens-heuristic"
    version = "1.4"          # 1.4: + Afaan Oromo & Tigrinya keywords/langdetect

    def analyze(self, req: AnalyzeRequest) -> AnalyzeResponse:
        text = " ".join(filter(None, [req.title, req.description, req.comments])).lower()
        scores = {}
        for cat, kb in KB.items():
            s = sum(2 if len(k) > 4 else 1 for k in kb["keywords"] if k in text)
            s += sum(2 if len(k) > 4 else 1
                     for k in OM_TI_KEYWORDS.get(cat, ()) if k.lower() in text)
            if req.user_category == cat:
                s += 3  # citizen's own pick is a strong signal, not absolute
            scores[cat] = s
        best_cat = max(scores, key=scores.get)
        best_score = scores[best_cat]
        if best_score <= (3 if req.user_category else 0):
            best_cat = req.user_category or "Other"

        kb = KB[best_cat]
        issue_type = next(
            (name for name, kws in kb["issues"].items() if any(k in text for k in kws)),
            list(kb["issues"].keys())[-1],
        )

        danger_hits = sum(1 for w in kb["danger"] if w in text)
        urgent_hits = sum(1 for w in URGENT_WORDS if w in text)
        scale_hits = sum(1 for w in SCALE_WORDS if w in text)
        severity = 2
        severity += min(2, danger_hits)
        severity += 1 if urgent_hits else 0
        severity += 1 if scale_hits >= 2 else 0
        severity = max(1, min(5, severity))

        media_n = len(req.frames_b64) + len(req.images_b64)
        confidence = 0.42 + min(0.3, best_score * 0.045) + min(0.12, media_n * 0.04)
        if req.user_category == best_cat:
            confidence += 0.08
        confidence = round(min(0.97, confidence), 2)

        urgency = {1: "low", 2: "low", 3: "medium", 4: "high", 5: "critical"}[severity]
        lang = detect_language(text)
        if lang == "am":   # explanations in the reporter's language
            reasons = [AM_REASON["matched"].format(cat=best_cat, n=best_score)]
            if danger_hits:
                reasons.append(AM_REASON["danger"].format(n=danger_hits))
            if scale_hits >= 2:
                reasons.append(AM_REASON["scale"])
            if urgent_hits:
                reasons.append(AM_REASON["urgent"])
            if media_n:
                reasons.append(AM_REASON["media"].format(n=media_n))
            if req.user_category and req.user_category != best_cat:
                reasons.append(AM_REASON["disagree"].format(user=req.user_category, cat=best_cat))
        else:
            reasons = [f"Matched {best_score} signal(s) for '{best_cat}'."]
            if danger_hits:
                reasons.append(f"{danger_hits} danger indicator(s) detected in the description.")
            if scale_hits >= 2:
                reasons.append("Language suggests a wide area or many people are affected.")
            if urgent_hits:
                reasons.append("Urgency wording present.")
            if media_n:
                reasons.append(f"{media_n} visual evidence item(s) attached (frames/photos).")
            if req.user_category and req.user_category != best_cat:
                reasons.append(f"Note: reporter selected '{req.user_category}' but text signals point to '{best_cat}'.")

        return AnalyzeResponse(
            category=best_cat, issue_type=issue_type.title(), severity=severity,
            confidence=confidence, urgency=urgency,
            organization_type=kb["org_type"], responsible_organization=kb["org"],
            reasoning=" ".join(reasons),
            model_name=self.name, model_version=self.version,
            frames_analyzed=media_n,
        )


class OllamaAnalyzer:
    """Local LLM/VLM via Ollama. Vision frames are passed when the model supports them."""
    name = f"ollama:{OLLAMA_MODEL}"
    version = "1"

    PROMPT = """You are an AI classifier for an Ethiopian civic issue reporting platform.
Analyze the citizen report (and images if given) and reply ONLY with JSON:
{"category": one of %s,
 "issue_type": short phrase, "severity": 1-5 (1 minor,5 critical, consider danger to people,
 number affected, service impact, extent, urgency), "confidence": 0-1,
 "urgency": "low|medium|high|critical", "reasoning": one or two sentences}
Report title: %s
Description: %s
Extra comments: %s
Reporter-selected category (may be wrong): %s
City: %s"""

    def analyze(self, req: AnalyzeRequest) -> AnalyzeResponse:
        fallback = HeuristicAnalyzer().analyze(req)
        try:
            images = (req.frames_b64 + req.images_b64)[:4]
            payload = {
                "model": OLLAMA_MODEL,
                "prompt": self.PROMPT % (json.dumps(CATEGORIES), req.title, req.description,
                                         req.comments, req.user_category, req.city),
                "stream": False, "format": "json",
            }
            if images:
                payload["images"] = images
            r = httpx.post(f"{OLLAMA_URL}/api/generate", json=payload, timeout=180)
            r.raise_for_status()
            out = json.loads(r.json().get("response", "{}"))
            cat = out.get("category") if out.get("category") in CATEGORIES else fallback.category
            kb = KB[cat]
            sev = int(out.get("severity", fallback.severity))
            return AnalyzeResponse(
                category=cat,
                issue_type=str(out.get("issue_type", fallback.issue_type))[:100],
                severity=max(1, min(5, sev)),
                confidence=round(max(0.05, min(0.99, float(out.get("confidence", 0.6)))), 2),
                urgency=out.get("urgency", fallback.urgency),
                organization_type=kb["org_type"], responsible_organization=kb["org"],
                reasoning=str(out.get("reasoning", ""))[:1000] or fallback.reasoning,
                model_name=self.name, model_version=self.version,
                frames_analyzed=len(images),
            )
        except Exception:
            # graceful degradation to the built-in engine
            fallback.reasoning += " (Ollama model unavailable — heuristic fallback used.)"
            return fallback


def get_analyzer():
    if MODEL_KIND == "ollama":
        return OllamaAnalyzer()
    return HeuristicAnalyzer()


# ---------------------------------------------------------------------------
# Voice reporting: speech-to-text (faster-whisper, local, multilingual incl. am)
# Model size via WHISPER_MODEL (tiny for low-RAM dev; small/medium for prod).
# ---------------------------------------------------------------------------
WHISPER_MODEL = os.environ.get("WHISPER_MODEL", "tiny")
_whisper = None


def get_whisper():
    global _whisper
    if _whisper is None:
        from faster_whisper import WhisperModel
        _whisper = WhisperModel(WHISPER_MODEL, device="cpu", compute_type="int8")
    return _whisper


@app.post("/transcribe")
async def transcribe(request: Request):
    """Body: raw audio bytes (webm/ogg/wav/mp3). Returns transcription +
    detected language + a structured draft report (category/severity extracted
    from the transcript through the normal analyzer). The citizen ALWAYS
    reviews/corrects before submitting."""
    import subprocess, tempfile, os as _os
    audio = await request.body()
    if len(audio) < 100:
        return {"error": "empty audio"}
    if len(audio) > 15 * 1024 * 1024:
        return {"error": "audio too large (max 15MB)"}
    with tempfile.TemporaryDirectory() as td:
        src = _os.path.join(td, "in.audio")
        wav = _os.path.join(td, "in.wav")
        open(src, "wb").write(audio)
        try:
            p = subprocess.run(["ffmpeg", "-y", "-i", src, "-ar", "16000", "-ac", "1", wav],
                               capture_output=True, timeout=120)
        except FileNotFoundError:
            return {"error": "ffmpeg not available on host"}
        if p.returncode != 0 or not _os.path.exists(wav):
            return {"error": "could not decode audio"}
        try:
            segments, info = get_whisper().transcribe(wav, vad_filter=True)
            text = " ".join(seg.text.strip() for seg in segments).strip()
        except Exception as e:
            return {"error": f"transcription failed: {type(e).__name__}"}
    if not text:
        return {"error": "no speech detected"}
    lang = info.language if info.language in ("am", "en", "om", "ti") else detect_language(text)
    draft = get_analyzer().analyze(AnalyzeRequest(title="", description=text))
    return {
        "text": text, "language": lang,
        "language_probability": round(getattr(info, "language_probability", 0) or 0, 2),
        "draft": {
            "category": draft.category, "issue_type": draft.issue_type,
            "severity": draft.severity, "confidence": draft.confidence,
        },
        "note": "AI-generated draft — the citizen must review and correct before submitting.",
    }


@app.get("/health")
def health():
    a = get_analyzer()
    return {"status": "ok", "model": a.name, "version": a.version, "service": SERVICE_VERSION}


@app.post("/analyze", response_model=AnalyzeResponse)
def analyze(req: AnalyzeRequest):
    return get_analyzer().analyze(req)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8090")))
