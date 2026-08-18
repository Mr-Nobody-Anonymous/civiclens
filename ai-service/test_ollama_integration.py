"""OPTIONAL real-Ollama vision-pipeline integration test.

Runs ONLY when a local Ollama server is reachable and OLLAMA_MODEL is pulled:
    AI_MODEL=ollama OLLAMA_MODEL=llava:7b pytest test_ollama_integration.py -v

Covers: real video -> FFmpeg frames -> Ollama vision -> structured response ->
validation -> classification/severity/confidence suitable for routing.
Skipped automatically in environments without Ollama (e.g. CI sandboxes).
"""
import base64
import os
import subprocess
import tempfile

import httpx
import pytest

import main as m

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434")
MODEL = os.environ.get("OLLAMA_MODEL", "llava:7b")


def _ollama_ready():
    try:
        r = httpx.get(f"{OLLAMA_URL}/api/tags", timeout=2)
        return r.status_code == 200 and any(
            MODEL.split(":")[0] in t.get("name", "") for t in r.json().get("models", []))
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _ollama_ready(),
                                reason=f"Ollama with {MODEL} not available at {OLLAMA_URL}")


def _make_frames() -> list[str]:
    """Real video -> FFmpeg -> representative JPEG frames (the exact backend pipeline)."""
    with tempfile.TemporaryDirectory() as td:
        vid = os.path.join(td, "test.mp4")
        subprocess.run(["ffmpeg", "-y", "-f", "lavfi",
                        "-i", "testsrc=duration=2:size=320x240:rate=10",
                        "-c:v", "libx264", "-pix_fmt", "yuv420p", vid],
                       capture_output=True, timeout=60, check=True)
        frames = []
        for i in range(2):
            fp = os.path.join(td, f"f{i}.jpg")
            subprocess.run(["ffmpeg", "-y", "-ss", str(0.5 + i * 0.8), "-i", vid,
                            "-frames:v", "1", "-vf", "scale=512:-2", fp],
                           capture_output=True, timeout=30, check=True)
            with open(fp, "rb") as f:
                frames.append(base64.b64encode(f.read()).decode())
        return frames


def test_real_ollama_vision_pipeline():
    frames = _make_frames()
    analyzer = m.OllamaAnalyzer()
    out = analyzer.analyze(m.AnalyzeRequest(
        title="Deep pothole on Bole Road",
        description="A deep dangerous pothole on the main road, cars swerving to avoid it.",
        user_category="Roads & Transportation", city="Addis Ababa",
        frames_b64=frames))
    # structured, validated output regardless of what the model said
    assert out.category in m.CATEGORIES
    assert 1 <= out.severity <= 5
    assert 0 < out.confidence <= 0.99
    assert out.urgency in ("low", "medium", "high", "critical")
    assert out.model_name.startswith("ollama:")
    assert out.frames_analyzed >= 1


def test_real_ollama_timeout_falls_back(monkeypatch):
    """Even with a real server, a hard timeout must degrade gracefully."""
    real_post = httpx.post

    def slow_post(*a, **k):
        k["timeout"] = 0.001
        return real_post(*a, **k)

    monkeypatch.setattr(m.httpx, "post", slow_post)
    out = m.OllamaAnalyzer().analyze(m.AnalyzeRequest(
        title="Water pipe burst", description="water flooding the street from a broken pipe"))
    assert out.category == "Water"   # heuristic fallback
