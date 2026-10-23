"""Self-check: subtitle review stop + edit/re-render API. Run: python test_subtitle_edit.py"""
import tempfile
from pathlib import Path

from fastapi import HTTPException

import app

VI = "1\n00:00:01,000 --> 00:00:02,000\nXin chào\n\n2\n00:00:03,000 --> 00:00:04,500\nTạm biệt\n"
EN = "1\n00:00:01,000 --> 00:00:02,000\nHello\n\n2\n00:00:03,000 --> 00:00:04,500\nGoodbye\n"


def _job(root: Path, job_id: str, status: str, **options) -> Path:
    job_dir = root / job_id
    job_dir.mkdir()
    (job_dir / "vi.srt").write_text(VI, encoding="utf-8")
    (job_dir / "original.srt").write_text(EN, encoding="utf-8")
    files = {"input": str(job_dir / "input.mp4"), "vi_srt": str(job_dir / "vi.srt"), "original_srt": str(job_dir / "original.srt")}
    app.JOBS[job_id] = app.JobState(id=job_id, status=status, files=files, options=dict(options))
    return job_dir


def _status_code(fn, *args, **kw) -> int:
    try:
        fn(*args, **kw)
    except HTTPException as exc:
        return exc.status_code
    raise AssertionError("expected HTTPException")


def test_review_edit_and_rerender():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        app._JOBS_FILE = root / "jobs.json"

        _job(root, "rev", "paused", review_pending="true")
        assert app.get_subtitles("rev")["blocks"] == [
            {"start": "00:00:01,000", "end": "00:00:02,000", "text": "Xin chào", "source": "Hello"},
            {"start": "00:00:03,000", "end": "00:00:04,500", "text": "Tạm biệt", "source": "Goodbye"},
        ]
        assert _status_code(app.save_subtitles, "rev", texts=["một"]) == 400  # line count must match
        assert _status_code(app.save_subtitles, "rev", texts=["một", "  "]) == 400  # empty cue
        app.save_subtitles("rev", texts=["Chào  bạn\n\nnhé", "Tạm biệt"])
        job = app.JOBS["rev"]
        assert (job.status, job.options) == ("queued", {"reviewed": "true"})
        assert "Chào bạn nhé" in (root / "rev" / "vi.srt").read_text(encoding="utf-8")
        assert "00:00:03,000 --> 00:00:04,500" in (root / "rev" / "vi.srt").read_text(encoding="utf-8")
        assert app.QUEUE_PENDING == ["rev"]
        assert _status_code(app.save_subtitles, "rev", texts=["a", "b"]) == 409  # queued: no edits under the worker

        done_dir = _job(root, "done", "done", reviewed="true")
        for name in ("input_vi_soft.mp4", "input_vi_dub.mp4", "input_vi_burned.mp4", "burned_video_only.mp4", "background.wav"):
            (done_dir / name).write_bytes(b"x")
        app.JOBS["done"].files.update(output_video=str(done_dir / "input_vi_soft.mp4"),
                                      output_dubbed_video=str(done_dir / "input_vi_dub.mp4"),
                                      output_burned_video=str(done_dir / "input_vi_burned.mp4"))
        app.save_subtitles("done", texts=["Xin chào", "Hẹn gặp lại"])
        assert sorted(p.name for p in done_dir.iterdir()) == ["background.wav", "original.srt", "vi.srt"]  # earlier steps stay
        assert set(app.JOBS["done"].files) == {"input", "vi_srt", "original_srt"}
        assert app.JOBS["done"].options["redub"] == "true" and app.JOBS["done"].status == "queued"

        _job(root, "later", "paused", review_pending="true")
        app.resume_job("later")  # [resume] keeps the translation as is
        assert app.JOBS["later"].options == {"reviewed": "true"} and app.JOBS["later"].status == "queued"

        _job(root, "nosrt", "done")
        (root / "nosrt" / "vi.srt").unlink()
        assert _status_code(app.get_subtitles, "nosrt") == 404
    app.JOBS.clear()
    app.QUEUE_PENDING.clear()


if __name__ == "__main__":
    test_review_edit_and_rerender()
    print("ok")
