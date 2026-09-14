"""Minimal self-check for jobs/stats.json round-trip. Run: python test_stats.py"""
import json
import tempfile
from pathlib import Path

from app import _read_stats_file


def test_read_stats_file():
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "stats.json"

        assert _read_stats_file(path) == []  # missing file -> empty, not an error

        rows = [
            {"job_id": "a", "video_duration_sec": 60.0, "total_elapsed_sec": 12.3, "gpu": "cpu"},
            {"job_id": "b", "video_duration_sec": 120.0, "total_elapsed_sec": 24.1, "gpu": "NVIDIA RTX 4090"},
        ]
        path.write_text(json.dumps(rows), encoding="utf-8")

        assert _read_stats_file(path) == rows


if __name__ == "__main__":
    test_read_stats_file()
    print("ok")
