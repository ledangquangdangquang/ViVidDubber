"""Self-check: a failed TTS line is never cached (it would stay silent on every re-render).
Run: python test_dub_cache.py  (needs ffmpeg)"""
import io
import subprocess
import tempfile
from pathlib import Path

import numpy as np
import soundfile as sf

from pipeline import tts
from pipeline.subtitle import SubtitleBlock

BLOCKS = [SubtitleBlock(1, "00:00:00,000", "00:00:00,900", "một"),
          SubtitleBlock(2, "00:00:01,000", "00:00:01,900", "BAD"),
          SubtitleBlock(3, "00:00:02,000", "00:00:02,900", "ba")]


def _tone() -> bytes:
    buf = io.BytesIO()
    sf.write(buf, (0.2 * np.sin(np.arange(16000) / 5)).astype(np.float32), 24000, format="WAV", subtype="PCM_16")
    return buf.getvalue()


class FakeEdge:
    def __init__(self, default_voice="", **_kw):
        pass

    def synthesize(self, text, voice=None, speed=1.0):
        if "BAD" in text:
            raise tts.DubbingError("Edge-TTS failed after 3 tries: 403")
        return _tone(), 0.67, 0.0


class FakeVieNeu(FakeEdge):
    def synthesize_batch(self, texts, voice=None):
        return [None if "BAD" in t else _tone() for t in texts]


def _video(path: Path) -> None:
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc=size=160x120:rate=10:duration=3",
                    "-f", "lavfi", "-i", "sine=duration=3", "-shortest", "-c:v", "libx264", "-c:a", "aac", str(path)], check=True)


def _dub(work: Path, blocks, provider: str) -> set[str]:
    tts.create_vietnamese_dub(work / "in.mp4", blocks, work, work / "out.mp4", tts_provider=provider, tts_device="cuda")
    assert (work / "out.mp4").stat().st_size > 0
    return {p.name for p in (work / "tts_cache").iterdir()}


def test_failed_lines_are_not_cached():
    tts.EdgeTTSEngine, tts.VieNeuTTS = FakeEdge, FakeVieNeu
    for provider in ("edge", "vieneu"):  # per-line path, and the GPU batch path
        with tempfile.TemporaryDirectory() as d:
            work = Path(d)
            _video(work / "in.mp4")
            cached = _dub(work, BLOCKS, provider)
            assert cached == {tts._cache_key("vi-VN-HoaiMyNeural", 1.05, t) for t in ("một", "ba")}, (provider, cached)


def test_all_lines_failing_reports_the_cause():
    tts.EdgeTTSEngine = FakeEdge
    with tempfile.TemporaryDirectory() as d:
        work = Path(d)
        _video(work / "in.mp4")
        try:
            _dub(work, [BLOCKS[1]], "edge")
        except tts.DubbingError as exc:
            assert "403" in str(exc), exc
        else:
            raise AssertionError("expected DubbingError")
        assert not any((work / "tts_cache").iterdir())


if __name__ == "__main__":
    test_failed_lines_are_not_cached()
    test_all_lines_failing_reports_the_cause()
    print("ok")
