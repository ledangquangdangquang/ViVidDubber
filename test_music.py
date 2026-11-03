"""Self-check for background-music mixing in the dub mux (real ffmpeg, no TTS). Run: python test_music.py"""
import io
import subprocess
import tempfile
from pathlib import Path

from fastapi import HTTPException, UploadFile

import app
from pipeline.media import probe_media
from pipeline.tts import _mux_dub_audio


def _ffmpeg(*args: str) -> None:
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *args], check=True)


def _mean_db(path: Path) -> float:
    out = subprocess.run(
        ["ffmpeg", "-i", str(path), "-map", "0:a", "-af", "volumedetect", "-f", "null", "-"],
        capture_output=True, text=True, check=True,
    ).stderr
    return float(out.split("mean_volume:")[1].split("dB")[0])


def test_short_music_loops_under_whole_video():
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp)
        video, dub, music = d / "v.mp4", d / "dub.wav", d / "music.mp3"
        _ffmpeg("-f", "lavfi", "-i", "color=c=black:s=64x64:d=4", "-f", "lavfi", "-i", "sine=f=220:d=4",
                "-shortest", "-c:v", "libx264", "-c:a", "aac", str(video))
        _ffmpeg("-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo", "-t", "4", str(dub))  # silent voice track
        _ffmpeg("-f", "lavfi", "-i", "sine=f=440:d=1", str(music))  # 1 s track must loop to fill 4 s
        for bg_vol in (0.0, 0.5):
            plain, mixed = d / f"plain{bg_vol}.mp4", d / f"mixed{bg_vol}.mp4"
            _mux_dub_audio(video, dub, plain, 1.0, bg_vol)
            _mux_dub_audio(video, dub, mixed, 1.0, bg_vol, music_audio=music, music_volume=0.5)
            assert abs(float(probe_media(mixed)["format"]["duration"]) - 4) < 0.3
            # music tail: last second is only audible if the 1 s track looped
            tail = d / f"tail{bg_vol}.wav"
            _ffmpeg("-sseof", "-1", "-i", str(mixed), "-vn", str(tail))
            assert _mean_db(tail) > -40, _mean_db(tail)
            assert _mean_db(mixed) > _mean_db(plain)


def test_upload_must_be_audio():
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp)
        src = d / "src.mp3"
        _ffmpeg("-f", "lavfi", "-i", "sine=f=440:d=1", str(src))
        saved = app._save_music(UploadFile(io.BytesIO(src.read_bytes()), filename="Song.MP3"), d)
        assert saved.name == "music.mp3" and saved.exists()
        try:
            app._save_music(UploadFile(io.BytesIO(b"not audio"), filename="x.mp3"), d)
        except HTTPException as exc:
            assert exc.status_code == 400
        else:
            raise AssertionError("expected HTTPException")
        assert not (d / "music.mp3").exists()  # a bad upload doesn't leave junk behind


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
