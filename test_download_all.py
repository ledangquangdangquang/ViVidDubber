"""Self-check for GET /api/jobs/download-all. Run: python test_download_all.py"""
import io
import tempfile
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from fastapi.testclient import TestClient

import app as app_module


def test_zip_is_built_on_disk_and_leaves_nothing_behind():
    with tempfile.TemporaryDirectory() as d:
        jobs_dir = Path(d)
        video = jobs_dir / "output_vi_dub.mp4"
        video.write_bytes(b"video-bytes" * 1000)
        job = SimpleNamespace(
            id="abcdef123456",
            status="done",
            files={"output_dubbed_video": str(video)},
            options={"original_stem": "clip", "dub": "true"},
        )
        real_temporary_file = tempfile.TemporaryFile
        with (
            mock.patch.object(app_module, "_JOBS_DIR", jobs_dir),
            mock.patch.dict(app_module.JOBS, {job.id: job}, clear=True),
            mock.patch.object(tempfile, "TemporaryFile", side_effect=real_temporary_file) as temp_file,
        ):
            # No `with TestClient`: lifespan would start the queue worker.
            response = TestClient(app_module.app).get("/api/jobs/download-all")

        assert temp_file.call_args.kwargs["dir"] == jobs_dir  # not /tmp, which can be RAM
        assert response.status_code == 200
        assert 'filename="vivid_dub_all.zip"' in response.headers["content-disposition"]
        assert int(response.headers["content-length"]) == len(response.content)
        with zipfile.ZipFile(io.BytesIO(response.content)) as zf:
            assert zf.namelist() == ["clip_vi_dub.mp4"]
            assert zf.read("clip_vi_dub.mp4") == video.read_bytes()
        assert list(jobs_dir.iterdir()) == [video]  # no zip left on disk


if __name__ == "__main__":
    test_zip_is_built_on_disk_and_leaves_nothing_behind()
    print("ok")
