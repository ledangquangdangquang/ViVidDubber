from __future__ import annotations

import argparse
from contextlib import asynccontextmanager
from dataclasses import asdict, dataclass, field
from functools import lru_cache
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading
import time
import uuid
import zipfile

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, Response
from starlette.background import BackgroundTask

_DIR = Path(__file__).parent
_JOBS_DIR = _DIR / "jobs"
_JOBS_DIR.mkdir(parents=True, exist_ok=True)
_STATS_FILE = _JOBS_DIR / "stats.json"

MAX_UPLOAD_BYTES = 2 * 1024 * 1024 * 1024  # 2 GB
MAX_JOBS = 50
JOB_TTL_SECONDS = 3600 * 6  # 6 hours

from pipeline.media import burn_subtitles, download_video, extract_audio, mux_soft_subtitles, probe_media, resolve_video_urls
from pipeline.subtitle import parse_srt, write_srt
from pipeline.transcribe import FasterWhisperTranscriber
from pipeline.translate import EnViT5Translator, GoogleTranslator, HuggingFaceTranslator
from pipeline.tts import EdgeTTSEngine, VieNeuTTS, create_vietnamese_dub

PREVIEW_TEXT = "Xin chào, đây là bản nghe thử giọng đọc tiếng Việt."


@dataclass
class JobState:
    id: str
    status: str = "queued"
    step: str = "Waiting"
    progress: int = 0
    error: str | None = None
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    files: dict[str, str] = field(default_factory=dict)
    options: dict[str, str] = field(default_factory=dict)
    step_timings: dict[str, float] = field(default_factory=dict)
    translation_warnings: list[str] = field(default_factory=list)
    _current_step_start: float = field(default=0.0, repr=False)
    pause_requested: bool = field(default=False, repr=False)
    cancel_requested: bool = field(default=False, repr=False)
    paused_step: str = field(default="", repr=False)


JOBS: dict[str, JobState] = {}
JOBS_LOCK = threading.Lock()

QUEUE_PENDING: list[str] = []
QUEUE_RUNNING: str | None = None
QUEUE_LOCK = threading.Lock()
QUEUE_COND = threading.Condition(QUEUE_LOCK)

_WORKER_STARTED = False
_WORKER_LOCK = threading.Lock()


def _queue_worker() -> None:
    global QUEUE_RUNNING
    while True:
        with QUEUE_COND:
            while not QUEUE_PENDING:
                QUEUE_COND.wait()
            job_id = QUEUE_PENDING.pop(0)
            QUEUE_RUNNING = job_id
        try:
            _run_job(job_id)
        except Exception:
            import traceback
            traceback.print_exc()
        finally:
            with QUEUE_LOCK:
                QUEUE_RUNNING = None


@asynccontextmanager
async def _lifespan(_app):
    global _WORKER_STARTED
    with _WORKER_LOCK:
        if not _WORKER_STARTED:
            threading.Thread(target=_queue_worker, name="job-queue", daemon=True).start()
            _WORKER_STARTED = True
    yield


app = FastAPI(title="Vietnamese Video Dubber", lifespan=_lifespan)


def _enqueue_job(job_id: str) -> None:
    with QUEUE_LOCK:
        QUEUE_PENDING.append(job_id)
        QUEUE_COND.notify()


def _queue_position(job_id: str) -> int | None:
    with QUEUE_LOCK:
        if job_id == QUEUE_RUNNING:
            return 0
        if job_id in QUEUE_PENDING:
            return QUEUE_PENDING.index(job_id) + 1
    return None


def _cleanup_jobs() -> None:
    now = time.time()
    with JOBS_LOCK:
        expired = [
            jid for jid, j in JOBS.items()
            if j.status in {"done", "error"} and (now - j.updated_at) > JOB_TTL_SECONDS
        ]
    for jid in expired:
        _delete_job(jid)


def _delete_job(job_id: str) -> bool:
    job_dir = None
    with JOBS_LOCK:
        job = JOBS.pop(job_id, None)
    if job:
        job_dir = Path(job.files.get("input", "")).parent
    if job_dir and job_dir.is_dir():
        shutil.rmtree(job_dir, ignore_errors=True)
    return job is not None


def _set_job(job_id: str, **updates) -> None:
    with JOBS_LOCK:
        job = JOBS[job_id]
        for key, value in updates.items():
            setattr(job, key, value)
        job.updated_at = time.time()


def _set_step(job_id: str, step: str, progress: int) -> None:
    now = time.time()
    with JOBS_LOCK:
        job = JOBS[job_id]
        if job._current_step_start > 0:
            elapsed = now - job._current_step_start
            job.step_timings[job.step] = round(elapsed, 1)
        job.step = step
        job.progress = progress
        job._current_step_start = now
        job.updated_at = now


def _add_file(job_id: str, kind: str, path: Path) -> None:
    with JOBS_LOCK:
        job = JOBS[job_id]
        job.files = {**job.files, kind: str(path)}
        job.updated_at = time.time()


def _begin_step(job_id: str, step: str, progress: int, done_path: Path | None = None) -> str | None:
    """Mark a step as starting. Returns None=run it, False=skip (already done), 'pause'=paused, 'cancel'=cancelled."""
    if done_path is not None and done_path.exists():
        return False
    _set_step(job_id, step, progress)
    with JOBS_LOCK:
        job = JOBS[job_id]
        if job.cancel_requested:
            return "cancel"
        if job.pause_requested:
            job.status = "paused"
            job.paused_step = step
            return "pause"
    return None


def _job_payload(job: JobState) -> dict:
    payload = asdict(job)
    payload.pop("_current_step_start", None)
    payload.pop("pause_requested", None)
    payload.pop("cancel_requested", None)
    payload.pop("paused_step", None)
    payload["downloads"] = {
        name: f"/api/jobs/{job.id}/download/{name}"
        for name, path in job.files.items()
        if Path(path).is_file()
    }
    if job.status == "queued":
        total_elapsed = 0.0
    elif job.status == "running":
        total_elapsed = time.time() - job.created_at
    else:
        total_elapsed = sum(job.step_timings.values())
    payload["total_elapsed"] = round(total_elapsed, 1)
    return payload


def _safe_suffix(filename: str) -> str:
    suffix = Path(filename).suffix.lower()
    return suffix if suffix in {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v"} else ".mp4"


MAX_CLONE_REF_BYTES = 25 * 1024 * 1024  # 25 MB, ref clips are a few seconds
_VOICES_DIR = _DIR / "voices"
_VOICES_DIR.mkdir(parents=True, exist_ok=True)
_CLONED_VOICES_INDEX = _VOICES_DIR / "cloned_voices.json"


def _load_cloned_voices() -> dict[str, str]:
    if not _CLONED_VOICES_INDEX.exists():
        return {}
    try:
        return json.loads(_CLONED_VOICES_INDEX.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_cloned_voices_index(index: dict[str, str]) -> None:
    _CLONED_VOICES_INDEX.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")


def _resolve_clone_ref_path(name: str) -> str | None:
    filename = _load_cloned_voices().get(name)
    if not filename:
        return None
    path = _VOICES_DIR / filename
    return str(path) if path.exists() else None


MAX_CLONE_REF_SECONDS = 8  # longer clips don't clone better, just slow things down


def _save_clone_ref(upload: UploadFile, dest_dir: Path) -> Path:
    """Save an uploaded voice-clone reference clip as WAV; caller must unlink it when done.

    VieNeu reads ref clips with libsndfile, which can't decode .m4a/AAC — always
    transcode through ffmpeg so any input format the browser gives us works, and
    cut it down to MAX_CLONE_REF_SECONDS in the same pass.
    """
    dest_dir.mkdir(parents=True, exist_ok=True)
    stem = uuid.uuid4().hex[:12]
    raw_suffix = Path(upload.filename or "").suffix or ".bin"
    raw_path = dest_dir / f"{stem}_raw{raw_suffix}"
    data = upload.file.read(MAX_CLONE_REF_BYTES + 1)
    if len(data) > MAX_CLONE_REF_BYTES:
        raise HTTPException(status_code=413, detail="File giọng mẫu quá lớn (tối đa 25 MB).")
    raw_path.write_bytes(data)

    wav_path = dest_dir / f"{stem}.wav"
    result = subprocess.run(
        ["ffmpeg", "-y", "-i", str(raw_path), "-t", str(MAX_CLONE_REF_SECONDS),
         "-ar", "24000", "-ac", "1", str(wav_path)],
        capture_output=True,
    )
    raw_path.unlink(missing_ok=True)
    if result.returncode != 0 or not wav_path.exists():
        raise HTTPException(status_code=400, detail="Không đọc được file giọng mẫu. Thử file WAV/MP3 khác.")
    return wav_path


@app.get("/", response_class=HTMLResponse)
def index():
    return (_DIR / "web.html").read_text(encoding="utf-8")


@app.get("/tokens.css")
def design_tokens():
    return FileResponse(_DIR / "tokens.css", media_type="text/css")


@app.get("/favicon.ico")
def favicon():
    return FileResponse(_DIR / "assets" / "favicon.svg", media_type="image/svg+xml")


@app.get("/favicon.svg")
def favicon_svg():
    return FileResponse(_DIR / "assets" / "favicon.svg", media_type="image/svg+xml")


@app.get("/favicon-badge.svg")
def favicon_badge_svg():
    return FileResponse(_DIR / "assets" / "favicon-badge.svg", media_type="image/svg+xml")


@app.get("/api/config")
def config():
    return {"ok": True, "translation_providers": ["google", "huggingface", "envit5"]}


@app.get("/api/stats")
def stats():
    """Video duration vs. dub/total completion time, one row per finished dub job, per GPU config."""
    return _read_stats_file(_STATS_FILE)


@app.get("/api/clone-voices")
def list_clone_voices():
    return {"voices": sorted(_load_cloned_voices().keys())}


@app.post("/api/clone-voices")
def save_clone_voice(name: str = Form(...), file: UploadFile = File(...)):
    name = name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Cần đặt tên cho giọng.")
    wav_path = _save_clone_ref(file, _VOICES_DIR)
    index = _load_cloned_voices()
    old_filename = index.get(name)
    index[name] = wav_path.name
    _save_cloned_voices_index(index)
    if old_filename and old_filename != wav_path.name:
        (_VOICES_DIR / old_filename).unlink(missing_ok=True)
    return {"voices": sorted(index.keys())}


@app.delete("/api/clone-voices/{name}")
def delete_clone_voice(name: str):
    index = _load_cloned_voices()
    filename = index.pop(name, None)
    if filename is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy giọng.")
    _save_cloned_voices_index(index)
    (_VOICES_DIR / filename).unlink(missing_ok=True)
    return {"voices": sorted(index.keys())}


@lru_cache(maxsize=32)
def _synthesize_preview(tts_provider: str, tts_voice: str, ref_audio: str | None = None) -> bytes:
    engine = VieNeuTTS(default_voice=tts_voice, ref_audio=ref_audio) if tts_provider == "vieneu" else EdgeTTSEngine(default_voice=tts_voice)
    wav_bytes, _duration, _latency = engine.synthesize(PREVIEW_TEXT, voice=tts_voice)
    return wav_bytes


@app.post("/api/preview-voice")
def preview_voice(
    tts_provider: str = Form("edge"),
    tts_voice: str = Form("vi-VN-HoaiMyNeural"),
    clone_ref_audio: UploadFile = File(None),
    clone_voice_name: str = Form(""),
):
    ref_path = None
    cleanup_ref = False
    try:
        if clone_ref_audio is not None and clone_ref_audio.filename:
            ref_path = _save_clone_ref(clone_ref_audio, _JOBS_DIR / "preview_ref")
            cleanup_ref = True
        elif clone_voice_name.strip():
            saved = _resolve_clone_ref_path(clone_voice_name.strip())
            if saved is None:
                raise HTTPException(status_code=404, detail="Không tìm thấy giọng đã lưu.")
            ref_path = Path(saved)
        wav_bytes = _synthesize_preview(tts_provider, tts_voice, ref_audio=str(ref_path) if ref_path else None)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Không tạo được giọng thử: {exc}")
    finally:
        if ref_path and cleanup_ref:
            ref_path.unlink(missing_ok=True)
    return Response(content=wav_bytes, media_type="audio/wav")


@app.post("/api/resolve")
async def resolve_url(video_url: str = Form("")):
    url = video_url.strip()
    if not url:
        raise HTTPException(status_code=400, detail="No URL provided.")
    try:
        items = resolve_video_urls(url)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Failed to resolve URL: {exc}")
    return {"videos": [{"url": u, "title": t} for u, t in items]}


@app.post("/api/jobs")
async def create_job(
    file: UploadFile = File(None),
    video_url: str = Form(""),
    target_lang: str = Form("vi"),
    whisper_model: str = Form("medium"),
    whisper_device: str = Form("cuda"),
    whisper_compute_type: str = Form(""),
    export_mode: str = Form("burn"),
    subtitle_font_size: int = Form(15),
    translate: str = Form("true"),
    translation_provider: str = Form("huggingface"),
    translate_device: str = Form("cuda"),
    dub: str = Form("true"),
    tts_voice: str = Form("Thanh Bình"),
    tts_provider: str = Form("vieneu"),
    tts_device: str = Form("cuda"),
    background_volume: float = Form(0.5),
    voice_volume: float = Form(2.0),
    clone_ref_audio: UploadFile = File(None),
    clone_voice_name: str = Form(""),
):
    if export_mode not in {"soft", "burn"}:
        raise HTTPException(status_code=400, detail="Unsupported subtitle export mode.")
    if translation_provider not in {"google", "envit5", "huggingface"}:
        raise HTTPException(status_code=400, detail="Unsupported translation provider.")
    if not file and not video_url.strip():
        raise HTTPException(status_code=400, detail="Provide a video file or a YouTube URL.")

    _cleanup_jobs()

    job_id = uuid.uuid4().hex[:12]
    job_dir = _JOBS_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    video_url = video_url.strip()
    source_title = None
    if video_url:
        input_path = job_dir / "input.mp4"
    else:
        if file is None:
            raise HTTPException(status_code=400, detail="Provide a video file or a YouTube URL.")
        content_length = file.size
        if content_length and content_length > MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=413, detail="File too large.")
        input_path = job_dir / f"input{_safe_suffix(file.filename or '')}"
        uploaded = 0
        with input_path.open("wb") as out:
            while True:
                chunk = file.file.read(1024 * 1024)
                if not chunk:
                    break
                uploaded += len(chunk)
                if uploaded > MAX_UPLOAD_BYTES:
                    input_path.unlink(missing_ok=True)
                    shutil.rmtree(job_dir, ignore_errors=True)
                    raise HTTPException(status_code=413, detail="File too large.")
                out.write(chunk)
        source_title = Path(file.filename or "input").stem

    ref_audio_path = ""
    if clone_ref_audio is not None and clone_ref_audio.filename:
        ref_audio_path = str(_save_clone_ref(clone_ref_audio, job_dir))
        tts_provider = "vieneu"  # cloning is a VieNeu-only feature
    elif clone_voice_name.strip():
        saved = _resolve_clone_ref_path(clone_voice_name.strip())
        if saved is None:
            raise HTTPException(status_code=404, detail="Không tìm thấy giọng đã lưu.")
        ref_audio_path = saved
        tts_provider = "vieneu"

    state = JobState(
        id=job_id,
        files={"input": str(input_path)},
        _current_step_start=time.time(),
        options={
            "target_lang": target_lang,
            "whisper_model": whisper_model,
            "whisper_device": whisper_device,
            "whisper_compute_type": whisper_compute_type,
            "export_mode": export_mode,
            "subtitle_font_size": str(subtitle_font_size),
            "translate": translate,
            "translation_provider": translation_provider,
            "translate_device": translate_device,
            "dub": dub,
            "tts_voice": tts_voice,
            "tts_provider": tts_provider,
            "tts_device": tts_device,
            "tts_ref_audio": ref_audio_path,
            "background_volume": str(background_volume),
            "voice_volume": str(voice_volume),
            "video_url": video_url,
            "original_stem": source_title,
        },
    )
    with JOBS_LOCK:
        JOBS[job_id] = state

    _enqueue_job(job_id)
    return _job_payload(state)


@app.get("/api/jobs/download-all")
def download_all():
    """Zip the dub+Vietnamese-sub output (burned > soft) of every finished job."""
    with JOBS_LOCK:
        jobs = list(JOBS.values())

    entries: list[tuple[str, str, Path]] = []
    for job in jobs:
        if job.status != "done":
            continue
        raw_path = job.files.get("output_burned_video") or job.files.get("output_dubbed_video")
        if not raw_path or not Path(raw_path).is_file():
            continue
        stem = job.options.get("original_stem", Path(raw_path).stem)
        entries.append((job.id, stem, Path(raw_path)))

    if not entries:
        raise HTTPException(status_code=404, detail="Chưa có video nào lồng tiếng xong để nén.")

    tmp = tempfile.NamedTemporaryFile(suffix=".zip", delete=False)
    tmp.close()
    used_names: set[str] = set()
    with zipfile.ZipFile(tmp.name, "w", zipfile.ZIP_STORED) as zf:
        for job_id, stem, path in entries:
            name = f"{stem}_vi_dub{path.suffix}"
            if name in used_names:
                name = f"{stem}_vi_dub_{job_id[:8]}{path.suffix}"
            used_names.add(name)
            zf.write(path, arcname=name)

    return FileResponse(
        tmp.name,
        filename="vivid_dub_all.zip",
        media_type="application/zip",
        background=BackgroundTask(os.unlink, tmp.name),
    )


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str):
    with JOBS_LOCK:
        job = JOBS.get(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        return _job_payload(job)


@app.get("/api/queue")
def get_queue():
    with JOBS_LOCK:
        payloads = {jid: _job_payload(j) for jid, j in JOBS.items()}

    for jid, payload in payloads.items():
        payload["queue_position"] = _queue_position(jid)

    with QUEUE_LOCK:
        running = QUEUE_RUNNING
        pending = list(QUEUE_PENDING)

    order = []
    if running and running in payloads:
        order.append(running)
    order += [jid for jid in pending if jid in payloads and jid not in order]
    remaining = [jid for jid in payloads if jid not in order]
    remaining.sort(key=lambda jid: payloads[jid]["created_at"], reverse=True)
    order += remaining
    return {"jobs": [payloads[jid] for jid in order], "running": running}


def _job_status(job_id: str) -> str | None:
    with JOBS_LOCK:
        job = JOBS.get(job_id)
        return job.status if job else None


@app.post("/api/jobs/{job_id}/pause")
def pause_job(job_id: str):
    status = _job_status(job_id)
    if status is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if status == "paused":
        return {"ok": True, "status": "paused"}
    with QUEUE_LOCK:
        if job_id in QUEUE_PENDING:
            QUEUE_PENDING.remove(job_id)
    with JOBS_LOCK:
        job = JOBS[job_id]
        if job.status == "running":
            job.pause_requested = True
            job.updated_at = time.time()
            return {"ok": True, "status": "running"}
        job.status = "paused"
        job.step = "Paused"
        job.updated_at = time.time()
    return {"ok": True, "status": "paused"}


@app.post("/api/jobs/{job_id}/resume")
def resume_job(job_id: str):
    with JOBS_LOCK:
        job = JOBS.get(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        if job.status == "paused":
            job.status = "queued"
            job.pause_requested = False
            job.step = "Waiting"
            job.updated_at = time.time()
    if job.status == "queued":
        _enqueue_job(job_id)
    return {"ok": True, "status": job.status}


@app.post("/api/jobs/{job_id}/cancel")
def cancel_job(job_id: str):
    status = _job_status(job_id)
    if status is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if status == "running":
        with JOBS_LOCK:
            JOBS[job_id].cancel_requested = True
            JOBS[job_id].updated_at = time.time()
        return {"ok": True, "status": "cancelling"}
    with QUEUE_LOCK:
        if job_id in QUEUE_PENDING:
            QUEUE_PENDING.remove(job_id)
    if _delete_job(job_id):
        return {"ok": True, "status": "cancelled"}
    raise HTTPException(status_code=404, detail="Job not found")


@app.get("/api/jobs/{job_id}/download/{kind}")
def download(job_id: str, kind: str):
    with JOBS_LOCK:
        job = JOBS.get(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        path = Path(job.files.get(kind, ""))

    if not path.is_file():
        raise HTTPException(status_code=404, detail="File not ready")

    original_stem = job.options.get("original_stem", path.stem)
    download_names = {
        "output_burned_video": f"{original_stem}_vi_burned.mp4",
        "output_dubbed_video": f"{original_stem}_vi_dub.mp4",
        "output_video": f"{original_stem}_vi_soft.mp4",
        "vi_srt": f"{original_stem}_vi.srt",
        "original_srt": f"{original_stem}_original.srt",
        "audio": f"{original_stem}_audio.wav",
        "input": path.name,
    }
    return FileResponse(path, filename=download_names.get(kind, path.name))


def _run_job(job_id: str) -> None:
    with JOBS_LOCK:
        job = JOBS[job_id]
        input_path = Path(job.files["input"])
        opts = dict(job.options)

    job_dir = input_path.parent
    audio_path = job_dir / "audio.wav"
    original_srt = job_dir / "original.srt"
    vi_srt = job_dir / "vi.srt"
    input_stem = input_path.stem
    output_video = job_dir / f"{input_stem}_vi_soft.mp4"
    output_dubbed_video = job_dir / f"{input_stem}_vi_dub.mp4"
    output_burned_video = job_dir / f"{input_stem}_vi_burned.mp4"

    try:
        with JOBS_LOCK:
            JOBS[job_id].status = "running"
            JOBS[job_id].pause_requested = False

        video_url = opts.get("video_url", "")
        if video_url:
            state = _begin_step(job_id, "Downloading video from YouTube", 10, input_path if input_path.exists() else None)
            if state is None:
                input_path, source_title = download_video(video_url, job_dir)
                _add_file(job_id, "input", input_path)
                _set_job(job_id, options={**opts, "original_stem": source_title})
            elif state in ("pause", "cancel"):
                return _finish_control(job_id, state)

        state = _begin_step(job_id, "Extracting audio", 15, audio_path)
        if state is None:
            extract_audio(input_path, audio_path)
            _add_file(job_id, "audio", audio_path)
        elif state in ("pause", "cancel"):
            return _finish_control(job_id, state)

        state = _begin_step(job_id, "Transcribing audio to SRT", 35, original_srt)
        if state is None:
            transcriber = FasterWhisperTranscriber(
                model_name=opts["whisper_model"],
                device=opts.get("whisper_device"),
                compute_type=opts.get("whisper_compute_type") or None,
            )
            original_blocks = transcriber.transcribe_to_srt(audio_path, original_srt)
            _add_file(job_id, "original_srt", original_srt)
        elif state in ("pause", "cancel"):
            return _finish_control(job_id, state)
        else:
            original_blocks = parse_srt(original_srt.read_text(encoding="utf-8"))

        subtitle_for_export = original_srt
        if opts.get("translate", "true") == "true" and original_blocks:
            state = _begin_step(job_id, "Translating subtitles to Vietnamese", 65, vi_srt if vi_srt.exists() else None)
            if state is None:
                provider = opts.get("translation_provider", "google")
                if provider == "envit5":
                    translator = EnViT5Translator(device=opts.get("translate_device", "cpu"))
                elif provider == "huggingface":
                    translator = HuggingFaceTranslator(device=opts.get("translate_device", "cpu"))
                else:
                    translator = GoogleTranslator()
                vi_blocks = translator.translate_blocks(
                    original_blocks, source_lang="en", target_lang=opts["target_lang"]
                )
                if translator.warnings:
                    _set_job(job_id, translation_warnings=list(translator.warnings))
                vi_srt.write_text(write_srt(vi_blocks), encoding="utf-8")
                subtitle_for_export = vi_srt
                _add_file(job_id, "vi_srt", vi_srt)
            elif state in ("pause", "cancel"):
                return _finish_control(job_id, state)
            else:
                subtitle_for_export = vi_srt

        state = _begin_step(job_id, "Muxing soft subtitles", 80, output_video)
        if state is None:
            mux_soft_subtitles(input_path, subtitle_for_export, output_video)
            _add_file(job_id, "output_video", output_video)
        elif state in ("pause", "cancel"):
            return _finish_control(job_id, state)

        if opts.get("dub", "false") == "true" and subtitle_for_export.exists():
            tts_label = "VieNeu-TTS" if opts.get("tts_provider", "edge") == "vieneu" else "Edge-TTS"
            state = _begin_step(job_id, f"Generating Vietnamese voice-over ({tts_label})", 90, output_dubbed_video)
            if state is None:
                dub_blocks = parse_srt(subtitle_for_export.read_text(encoding="utf-8"))
                bg_vol = float(opts.get("background_volume", "0.15"))
                vc_vol = float(opts.get("voice_volume", "1.0"))
                create_vietnamese_dub(
                    output_video, dub_blocks, job_dir, output_dubbed_video,
                    voice=opts.get("tts_voice", "vi-VN-HoaiMyNeural"),
                    background_volume=bg_vol, voice_volume=vc_vol,
                    tts_provider=opts.get("tts_provider", "edge"),
                    ref_audio=opts.get("tts_ref_audio") or None,
                    tts_device=opts.get("tts_device", "cpu"),
                )
                _add_file(job_id, "output_dubbed_video", output_dubbed_video)
            elif state in ("pause", "cancel"):
                return _finish_control(job_id, state)

        if opts.get("export_mode") == "burn":
            state = _begin_step(job_id, "Burning subtitles into video", 96, output_burned_video)
            if state is None:
                burn_source = output_dubbed_video if opts.get("dub", "false") == "true" else input_path
                burn_subtitles(
                    burn_source,
                    subtitle_for_export,
                    output_burned_video,
                    font_size=int(opts.get("subtitle_font_size", 22)),
                )
                _add_file(job_id, "output_burned_video", output_burned_video)
            elif state in ("pause", "cancel"):
                return _finish_control(job_id, state)

        if opts.get("dub", "false") == "true":
            _log_dub_stats(job_id, input_path)

        _set_step(job_id, "Done", 100)
        _set_job(job_id, status="done")
    except Exception as exc:
        _set_job(job_id, status="error", step="Failed", error=str(exc))


def _finish_control(job_id: str, state: str) -> None:
    if state == "cancel":
        _delete_job(job_id)
    # paused: leave job in JOBS with status=paused for later resume


def _gpu_name() -> str:
    try:
        import torch
        if torch.cuda.is_available():
            return torch.cuda.get_device_name(0)
    except Exception:
        pass
    return "cpu"


def _log_dub_stats(job_id: str, input_path: Path) -> None:
    """Append video duration vs. total dub time for this GPU config to jobs/stats.json."""
    try:
        video_duration = float(probe_media(input_path)["format"]["duration"])
    except Exception:
        video_duration = None
    with JOBS_LOCK:
        job = JOBS[job_id]
        dub_elapsed = next(
            (v for k, v in job.step_timings.items() if k.startswith("Generating Vietnamese voice-over")), None
        )
        row = {
            "job_id": job_id,
            "timestamp": round(time.time(), 1),
            "video_duration_sec": video_duration,
            "dub_elapsed_sec": dub_elapsed,
            "total_elapsed_sec": round(sum(job.step_timings.values()), 1),
            "gpu": _gpu_name(),
            "whisper_device": job.options.get("whisper_device"),
            "translate_device": job.options.get("translate_device"),
            "tts_provider": job.options.get("tts_provider", "edge"),
            "tts_device": job.options.get("tts_device"),
        }
        rows = _read_stats_file(_STATS_FILE)
        rows.append(row)
        _STATS_FILE.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")


def _read_stats_file(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8787)
    args = parser.parse_args()

    import uvicorn
    print(f"Vietnamese Video Dubber: http://{args.host}:{args.port}")
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
