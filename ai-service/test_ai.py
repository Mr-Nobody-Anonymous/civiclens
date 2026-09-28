import shutil
import pytest
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_pothole_classification():
    r = client.post("/analyze", json={
        "title": "Huge pothole on Bole Road",
        "description": "Deep dangerous pothole, cars swerving, accidents almost happened, main road, urgent",
    })
    d = r.json()
    assert d["category"] == "Roads & Transportation"
    assert d["issue_type"].lower() == "pothole"
    assert d["severity"] >= 4
    assert 0 < d["confidence"] <= 1


def test_amharic_keywords():
    r = client.post("/analyze", json={
        "title": "የመንገድ መብራት ችግር",
        "description": "የመንገድ መብራት ስለማይሰራ ሌሊት አደጋ አለ",
    })
    d = r.json()
    assert d["category"] == "Electricity"


def test_user_category_respected_when_text_ambiguous():
    r = client.post("/analyze", json={
        "title": "Problem here", "description": "Please fix this issue soon thank you",
        "user_category": "Water",
    })
    assert r.json()["category"] == "Water"


def test_severity_bounds():
    r = client.post("/analyze", json={"title": "small litter", "description": "one bottle on grass"})
    assert 1 <= r.json()["severity"] <= 5


def test_model_metadata_present():
    r = client.post("/analyze", json={"title": "pothole", "description": "deep pothole on road"})
    d = r.json()
    assert d["model_name"] and d["model_version"]
    assert d["urgency"] in ("low", "medium", "high", "critical")


def test_low_confidence_on_vague_text():
    r = client.post("/analyze", json={"title": "hmm", "description": "something somewhere maybe"})
    assert r.json()["confidence"] < 0.6


def test_ollama_analyzer_falls_back_when_offline(monkeypatch):
    """Ollama unreachable → graceful heuristic fallback, never a 500."""
    import main as m
    monkeypatch.setattr(m, "OLLAMA_URL", "http://127.0.0.1:1")
    analyzer = m.OllamaAnalyzer()
    out = analyzer.analyze(m.AnalyzeRequest(
        title="Broken water pipe", description="water pipe burst flooding the street"))
    assert out.category == "Water"
    assert "fallback" in out.reasoning.lower() or out.confidence > 0


def test_ollama_invalid_json_falls_back(monkeypatch):
    """Ollama returning garbage JSON → fallback, not a crash."""
    import main as m

    class FakeResp:
        status_code = 200
        def raise_for_status(self): pass
        def json(self): return {"response": "this is not json {{{"}

    monkeypatch.setattr(m.httpx, "post", lambda *a, **k: FakeResp())
    out = m.OllamaAnalyzer().analyze(m.AnalyzeRequest(
        title="Garbage pile", description="overflowing garbage in the market"))
    assert out.category == "Garbage & Sanitation"   # heuristic fallback result


def test_ollama_unknown_category_sanitized(monkeypatch):
    """Ollama inventing a category → clamped to heuristic result."""
    import main as m
    import json as _json

    class FakeResp:
        status_code = 200
        def raise_for_status(self): pass
        def json(self): return {"response": _json.dumps({
            "category": "Alien Invasions", "issue_type": "UFO", "severity": 99,
            "confidence": 5.0, "urgency": "high", "reasoning": "nonsense"})}

    monkeypatch.setattr(m.httpx, "post", lambda *a, **k: FakeResp())
    out = m.OllamaAnalyzer().analyze(m.AnalyzeRequest(
        title="Deep pothole", description="deep pothole on the main road"))
    assert out.category in m.CATEGORIES
    assert 1 <= out.severity <= 5
    assert 0 < out.confidence <= 0.99


# ---------------- Phase C: deep Amharic + language detection ----------------
AMHARIC_EVAL = [
    # (description, expected_category) — the Amharic accuracy dataset
    ("በቦሌ አካባቢ ያለው መንገድ በጣም ተበላሽቷል፤ ጉድጓድ አለ", "Roads & Transportation"),
    ("በሰፈራችን ውሃው ተቋርጧል፤ ብዙ ቀናት ሆኖታል", "Water"),
    ("ቆሻሻው ተከምሯል፤ ሽታው በጣም ከባድ ነው", "Garbage & Sanitation"),
    ("ኔትወርኩ ተቋርጧል፤ ስልክ መደወል አልተቻለም", "Telecom"),
    ("የመንገድ መብራት አይሰራም፤ ሌሊት አደገኛ ነው", "Electricity"),
    ("ትምህርት ቤቱ ክፍል ተበላሽቷል፤ ተማሪዎች ተጎድተዋል", "Education"),
]


def test_amharic_eval_dataset():
    """Amharic accuracy evaluation: >= 5/6 categories must classify correctly."""
    correct = 0
    for desc, expected in AMHARIC_EVAL:
        r = client.post("/analyze", json={"title": desc[:30], "description": desc})
        if r.json()["category"] == expected:
            correct += 1
    assert correct >= 5, f"Amharic eval below threshold: {correct}/{len(AMHARIC_EVAL)}"


def test_amharic_reasoning_in_amharic():
    r = client.post("/analyze", json={
        "title": "መንገዱ ተበላሽቷል",
        "description": "በቦሌ ያለው መንገድ ጉድጓድ አለው፤ አስቸኳይ ነው፤ መኪናዎች ተጎድተዋል።"})
    reasoning = r.json()["reasoning"]
    assert any('\u1200' <= ch <= '\u137f' for ch in reasoning), "reasoning must be in Amharic"


def test_mixed_language_understanding():
    """Amharic/English mixed text still classifies via combined keywords."""
    r = client.post("/analyze", json={
        "title": "Network problem in Bole",
        "description": "ኔትወርኩ down ነው since Monday, no internet, ስልክ አይሰራም"})
    assert r.json()["category"] == "Telecom"


def test_language_detection():
    from main import detect_language
    assert detect_language("መንገዱ በጣም ተበላሽቷል") == "am"
    assert detect_language("the road is very damaged") == "en"
    assert detect_language("road ተበላሽቷል በጣም ጉድጓድ አለው") == "am"   # Ethiopic-dominant


def test_amharic_severity_signals():
    low = client.post("/analyze", json={"title": "ቆሻሻ", "description": "ትንሽ ቆሻሻ አለ"}).json()
    high = client.post("/analyze", json={
        "title": "አደጋ", "description":
        "የወደቀ ገመድ አለ፤ በጣም አደገኛ ነው፤ ልጆች ይጫወታሉ፤ አስቸኳይ እርዳታ ያስፈልጋል፤ ሁሉም ሰፈር ተጎድቷል"}).json()
    assert high["severity"] > low["severity"]


# ---------------- Phase C: voice transcription endpoint ----------------
def test_transcribe_rejects_empty_and_garbage():
    r = client.post("/transcribe", content=b"xx")
    assert "error" in r.json()
    r = client.post("/transcribe", content=b"not-really-audio" * 100)
    assert "error" in r.json()


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not installed on this system")
def test_transcribe_real_audio():
    """Real WAV through the full pipeline: ffmpeg -> whisper -> draft.
    Uses a synthesized sine tone; whisper returns empty/no-speech -> graceful,
    OR on models that hallucinate, a draft. Both paths must not 500."""
    import subprocess, tempfile, os
    with tempfile.TemporaryDirectory() as td:
        wav = os.path.join(td, "t.wav")
        subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i",
                        "sine=frequency=440:duration=2", "-ar", "16000", wav],
                       capture_output=True, timeout=60, check=True)
        audio = open(wav, "rb").read()
    r = client.post("/transcribe", content=audio)
    assert r.status_code == 200
    data = r.json()
    # either clean no-speech error or a transcript with a reviewed draft
    assert "error" in data or ("text" in data and "draft" in data and "note" in data)


# ---------------- Afaan Oromo + Tigrinya (v1.4) ----------------

def test_language_detection_oromo_tigrinya():
    from main import detect_language
    assert detect_language("Daandii keessa boolla guddaa jira, konkolaataan darbuu hin danda'u") == "om"
    assert detect_language("ኣብ መንገዲ ዓቢ ጉድጓድ ኣሎ እዩ፣ መኪና ክሓልፍ ኣይክእልን") == "ti"
    # Amharic must NOT be mistaken for Tigrinya
    assert detect_language("መንገዱ ላይ ትልቅ ጉድጓድ አለ፤ መኪናዎች ተጎድተዋል") == "am"
    # English must NOT be mistaken for Oromo
    assert detect_language("The main road has a dangerous pothole near the market") == "en"


def test_classification_oromo():
    r = client.post("/analyze", json={
        "title": "Boolla daandii irratti",
        "description": "Daandii keessa boolla guddaa jira, konkolaataan miidhamaa jiru, balaa guddaa dha",
    })
    assert r.status_code == 200
    data = r.json()
    assert data["category"] == "Roads & Transportation"
    assert 1 <= data["severity"] <= 5


def test_classification_tigrinya():
    r = client.post("/analyze", json={
        "title": "ጸገም ማይ",
        "description": "ማይ የለን ካብ ሰሉስ ጀሚሩ እዩ፣ ቡምባ ተሰይሩ ምፍሳስ ኣሎ፣ ዓቢ ጸገም እዩ",
    })
    assert r.status_code == 200
    data = r.json()
    assert data["category"] == "Water"
    assert 1 <= data["severity"] <= 5
