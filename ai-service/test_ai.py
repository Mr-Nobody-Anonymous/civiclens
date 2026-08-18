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
