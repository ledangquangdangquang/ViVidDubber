"""Self-check: jobs.json survives a restart, and cleanup waits for the queue. Run: python test_jobs_persist.py"""
import tempfile
import time
from pathlib import Path

import app


def _job(root: Path, job_id: str, **kw) -> app.JobState:
    (root / job_id).mkdir()
    return app.JobState(id=job_id, files={"input": str(root / job_id / "input.mp4")}, **kw)


def test_restart_and_cleanup():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        app._JOBS_FILE = root / "jobs.json"
        jobs = [
            _job(root, "queued", status="queued", created_at=1),
            _job(root, "running", status="running", created_at=2, current_output=str(root / "running" / "audio.wav")),
            _job(root, "done", status="done", created_at=3),
            _job(root, "paused", status="paused", created_at=4),
            _job(root, "pausing", status="running", pause_requested=True, created_at=5),
            _job(root, "cancelling", status="running", cancel_requested=True, created_at=6),
        ]
        app.JOBS.update({j.id: j for j in jobs})
        (root / "running" / "audio.wav").write_bytes(b"half")  # power cut mid-step
        app._save_jobs()

        app.JOBS.clear()  # simulate a restart
        app._load_jobs()
        assert app.QUEUE_PENDING == ["running", "queued"]  # the interrupted job resumes first
        assert {j: app.JOBS[j].status for j in app.JOBS} == {
            "queued": "queued", "running": "queued", "done": "done", "paused": "paused", "pausing": "paused",
        }
        assert not (root / "cancelling").exists()
        assert not (root / "running" / "audio.wav").exists()  # partial output dropped, the step reruns

        app.JOBS["done"].updated_at = time.time() - app.JOB_TTL_SECONDS - 1
        app._cleanup_jobs()
        assert "done" in app.JOBS  # queue still busy: keep finished outputs
        app.QUEUE_PENDING.clear()
        app._cleanup_jobs()
        assert "done" not in app.JOBS and not (root / "done").exists()
        app.JOBS.clear()


def test_video_statuses():
    with tempfile.TemporaryDirectory() as d:
        app._DONE_VIDEOS_FILE = Path(d) / "done_videos.txt"
        assert app._youtube_id("https://www.youtube.com/shorts/P11ykXwx4-k") == "P11ykXwx4-k"
        assert app._youtube_id("https://youtu.be/Nbwv5wHQoj0?t=3") == "Nbwv5wHQoj0"
        app.JOBS["q"] = app.JobState(id="q", options={"video_url": "https://www.youtube.com/watch?v=AAAAAAAAAAA"})
        app.JOBS["e"] = app.JobState(id="e", status="error", options={"video_url": "https://www.youtube.com/watch?v=BBBBBBBBBBB"})
        app._mark_video_done("https://www.youtube.com/watch?v=CCCCCCCCCCC")
        assert app._video_statuses() == {"AAAAAAAAAAA": "queued", "CCCCCCCCCCC": "done"}  # a failed job may be retried
        app.JOBS.clear()


def test_queue_wait_not_timed():
    with tempfile.TemporaryDirectory() as d:
        app._JOBS_FILE = Path(d) / "jobs.json"
        app.JOBS["w"] = app.JobState(id="w", _current_step_start=time.time() - 3600)  # an hour in the queue
        app._set_step("w", "Extracting audio", 15)
        assert "Waiting" not in app.JOBS["w"].step_timings
        app.JOBS.clear()


def test_clear_done():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        app._JOBS_FILE = root / "jobs.json"
        app.JOBS.update({j.id: j for j in [_job(root, "d", status="done"), _job(root, "e", status="error")]})
        assert app.clear_done() == {"ok": True, "deleted": 1}
        assert list(app.JOBS) == ["e"] and not (root / "d").exists() and (root / "e").exists()
        app.JOBS.clear()


if __name__ == "__main__":
    test_queue_wait_not_timed()
    test_clear_done()
    test_restart_and_cleanup()
    test_video_statuses()
    print("ok")
