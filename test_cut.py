"""Self-check: cutting a part out of a finished job's output videos (POST /api/jobs/{id}/cut). Run: python test_cut.py"""
import subprocess
import tempfile
from pathlib import Path

from fastapi import HTTPException

import app
from pipeline.media import mux_soft_subtitles, probe_media

SRT = "1\n00:00:01,000 --> 00:00:02,000\nmột\n\n2\n00:00:04,000 --> 00:00:05,000\nhai\n"


def _status_code(fn, *args, **kw) -> int:
    try:
        fn(*args, **kw)
    except HTTPException as exc:
        return exc.status_code
    raise AssertionError("expected HTTPException")


def test_cut_finished_outputs():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        app._JOBS_FILE = root / "jobs.json"
        job_dir = root / "cut"
        job_dir.mkdir()
        plain, soft = job_dir / "output_vi_burned.mp4", job_dir / "output_vi_soft.mp4"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=d=6:s=160x120:r=10", "-f", "lavfi",
                        "-i", "sine=d=6", "-pix_fmt", "yuv420p", str(plain)], check=True, stdin=subprocess.DEVNULL)
        (job_dir / "vi.srt").write_text(SRT, encoding="utf-8")
        mux_soft_subtitles(plain, job_dir / "vi.srt", soft)
        files = {"input": str(job_dir / "input.mp4"), "output_video": str(soft), "output_burned_video": str(plain)}
        app.JOBS["cut"] = app.JobState(id="cut", status="done", files=files, options={})

        assert _status_code(app.cut_outputs, "cut", start="", end="") == 400  # nothing to cut
        assert _status_code(app.cut_outputs, "cut", start="abc", end="") == 400
        assert _status_code(app.cut_outputs, "cut", start="5", end="2") == 400  # empty range
        assert _status_code(app.cut_outputs, "cut", start="0:10", end="") == 400  # starts after the end (6 s)
        assert _status_code(app.cut_outputs, "cut", start="0", end="10") == 400  # would remove the whole video
        app.JOBS["cut"].status = "paused"
        assert _status_code(app.cut_outputs, "cut", start="1", end="4") == 409  # finished jobs only
        app.JOBS["cut"].status = "done"

        app.cut_outputs("cut", start="1", end="0:04")
        assert app.JOBS["cut"].status == "queued"
        app._run_job("cut")
        job = app.JOBS["cut"]
        assert (job.status, job.step, job.options) == ("done", "Done", {"cut_start": "1", "cut_end": "0:04"})
        for path in (plain, soft):  # 1-4 s removed, the two sides joined
            assert abs(float(probe_media(path)["format"]["duration"]) - 3.0) < 0.3, path
        # Soft subs survive: the cue inside the removed part is gone, the later one moved 3 s earlier.
        subs = subprocess.run(["ffmpeg", "-v", "error", "-i", str(soft), "-map", "0:s:0", "-f", "srt", "-"],
                              capture_output=True, text=True, check=True, stdin=subprocess.DEVNULL).stdout
        assert "hai" in subs and "một" not in subs and "00:00:01," in subs, subs

        app.cut_outputs("cut", start="", end="1")  # drop the first second; times are those of the cut video
        app._run_job("cut")
        assert app.JOBS["cut"].options == {"cut_start": "", "cut_end": "1"}
        assert abs(float(probe_media(plain)["format"]["duration"]) - 2.0) < 0.3
        assert sorted(p.name for p in job_dir.iterdir()) == ["output_vi_burned.mp4", "output_vi_soft.mp4", "vi.srt"]


def test_cut_blocks():
    from pipeline.subtitle import SubtitleBlock as B, cut_blocks, seconds_to_srt_time as ts
    cues = [B(i, ts(a), ts(b), str(i)) for i, (a, b) in enumerate([(0, 2), (8, 12), (12, 18), (18, 22), (9, 25), (30, 31)], 1)]
    spans = lambda out: [(b.text, b.start[3:8], b.end[3:8]) for b in out]
    assert spans(cut_blocks(cues, 10, 20)) == [  # 12-18 lies inside the removed part
        ("1", "00:00", "00:02"), ("2", "00:08", "00:10"), ("4", "00:10", "00:12"), ("5", "00:09", "00:15"), ("6", "00:20", "00:21")]
    assert spans(cut_blocks(cues, 10, None)) == [("1", "00:00", "00:02"), ("2", "00:08", "00:10"), ("5", "00:09", "00:10")]
    assert spans(cut_blocks(cues, 0, 10))[:2] == [("2", "00:00", "00:02"), ("3", "00:02", "00:08")]


if __name__ == "__main__":
    test_cut_blocks()
    test_cut_finished_outputs()
    print("ok")
