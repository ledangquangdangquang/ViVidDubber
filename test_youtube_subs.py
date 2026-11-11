"""Minimal self-check for the YouTube-subtitles shortcut. Run: python test_youtube_subs.py"""
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace as NS

from app import _youtube_subtitles
from pipeline.media import download_video

SRT = "1\n00:00:01,000 --> 00:00:03,000\nHello there.\n\n2\n00:00:50,000 --> 00:00:55,000\nBye now.\n"


def test_partial_subtitles_are_ignored():
    with tempfile.TemporaryDirectory() as d:
        job_dir = Path(d)
        assert _youtube_subtitles(job_dir, "en", 60) == []  # video had none
        (job_dir / "yt_sub.en.srt").write_text(SRT, encoding="utf-8")
        assert [b.text for b in _youtube_subtitles(job_dir, "en", 60)] == ["Hello there.", "Bye now."]
        assert _youtube_subtitles(job_dir, "en", 600) == []  # captions stop at 0:55 of 10 min -> Whisper


def test_subtitle_error_retries_without_subtitles():
    class DownloadError(Exception):
        pass

    calls = []

    class FakeYDL:
        def __init__(self, opts):
            self.opts = opts

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def extract_info(self, url, download):
            calls.append(bool(self.opts.get("writesubtitles")))
            if self.opts.get("writesubtitles"):
                raise DownloadError("ERROR: Unable to download video subtitles for 'en': HTTP Error 429")
            Path(self.opts["outtmpl"]["default"].replace("%(ext)s", "mp4")).write_bytes(b"x")
            return {"title": "t", "channel": "c"}

    real = sys.modules.get("yt_dlp")
    sys.modules["yt_dlp"] = NS(YoutubeDL=FakeYDL, utils=NS(DownloadError=DownloadError))
    try:
        with tempfile.TemporaryDirectory() as d:
            path, title, channel = download_video("https://youtu.be/xxxxxxxxxxx", Path(d), sub_lang="en")
            assert (path.name, title, channel) == ("input.mp4", "t", "c")
        assert calls == [True, False]
    finally:
        if real is not None:
            sys.modules["yt_dlp"] = real
        else:
            del sys.modules["yt_dlp"]


if __name__ == "__main__":
    test_partial_subtitles_are_ignored()
    test_subtitle_error_retries_without_subtitles()
    print("ok")
