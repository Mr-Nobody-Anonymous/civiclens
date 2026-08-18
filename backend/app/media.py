"""Video/image processing pipeline built on FFmpeg.

- probe(): duration / dimensions metadata
- make_video_thumbnail(): representative poster frame
- extract_frames(): N evenly spaced frames for the local vision model
- transcode_if_needed(): hook for compressing oversized uploads
"""
import json
import os
import subprocess
import tempfile
from typing import List


def _run(cmd: List[str], timeout=120) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, timeout=timeout)


def ffmpeg_available() -> bool:
    try:
        return _run(["ffmpeg", "-version"], timeout=10).returncode == 0
    except Exception:
        return False


def probe(path: str) -> dict:
    try:
        p = _run(["ffprobe", "-v", "quiet", "-print_format", "json",
                  "-show_format", "-show_streams", path], timeout=30)
        data = json.loads(p.stdout or b"{}")
        fmt = data.get("format", {})
        vstream = next((s for s in data.get("streams", []) if s.get("codec_type") == "video"), {})
        return {
            "duration_s": float(fmt.get("duration") or 0) or None,
            "width": vstream.get("width"),
            "height": vstream.get("height"),
            "codec": vstream.get("codec_name"),
        }
    except Exception:
        return {}


def make_video_thumbnail(video_path: str, out_path: str, at_s: float = 1.0) -> bool:
    try:
        p = _run(["ffmpeg", "-y", "-ss", str(at_s), "-i", video_path,
                  "-frames:v", "1", "-vf", "scale=640:-2", "-q:v", "4", out_path])
        return p.returncode == 0 and os.path.exists(out_path)
    except Exception:
        return False


def make_image_thumbnail(image_path: str, out_path: str) -> bool:
    try:
        p = _run(["ffmpeg", "-y", "-i", image_path, "-vf", "scale=640:-2", "-q:v", "4", out_path])
        return p.returncode == 0 and os.path.exists(out_path)
    except Exception:
        return False


def extract_frames(video_path: str, n: int = 3) -> List[str]:
    """Extract n evenly spaced JPEG frames; returns temp file paths."""
    meta = probe(video_path)
    dur = meta.get("duration_s") or 3.0
    out = []
    tmpdir = tempfile.mkdtemp(prefix="cl_frames_")
    for i in range(n):
        ts = max(0.1, dur * (i + 0.5) / n)
        fp = os.path.join(tmpdir, f"frame_{i}.jpg")
        p = _run(["ffmpeg", "-y", "-ss", f"{ts:.2f}", "-i", video_path,
                  "-frames:v", "1", "-vf", "scale=512:-2", "-q:v", "5", fp])
        if p.returncode == 0 and os.path.exists(fp):
            out.append(fp)
    return out


def transcode_if_needed(video_path: str, max_mb: int = 60) -> str:
    """Compress very large videos to H.264 720p. Returns path of usable file."""
    try:
        if os.path.getsize(video_path) <= max_mb * 1024 * 1024:
            return video_path
        out = video_path + ".compressed.mp4"
        p = _run(["ffmpeg", "-y", "-i", video_path, "-vf", "scale=-2:720",
                  "-c:v", "libx264", "-preset", "veryfast", "-crf", "28",
                  "-c:a", "aac", "-b:a", "96k", out], timeout=600)
        return out if p.returncode == 0 and os.path.exists(out) else video_path
    except Exception:
        return video_path
