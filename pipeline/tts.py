from __future__ import annotations

import concurrent.futures
import hashlib
import io
import math
import os
from pathlib import Path
import re
import subprocess
import time

import soundfile as sf

from . import MODEL_LOAD_LOCK
from .media import probe_media, require_tool, run_command
from .subtitle import SubtitleBlock, srt_time_to_seconds

SAMPLE_RATE = 44100
SLOW_RATIO_THRESHOLD = 2.0
SLOW_SPEED_BOOST = 1.25
DUB_PHASES: dict[str, float] = {}  # phase -> seconds of the last create_vietnamese_dub (logged to jobs/stats.json)


class DubbingError(RuntimeError):
    pass


def _generate_silent_wav_bytes(duration_sec: float = 0.5) -> bytes:
    import numpy as np
    num_samples = int(SAMPLE_RATE * max(0.1, duration_sec))
    silence = np.zeros((num_samples,), dtype=np.int16)
    with io.BytesIO() as buf:
        sf.write(buf, silence, SAMPLE_RATE, format="WAV", subtype="PCM_16")
        return buf.getvalue()


def _array_to_wav(audio, sample_rate: int) -> bytes:
    import numpy as np
    array = np.asarray(audio, dtype=np.float32)
    with io.BytesIO() as buf:
        sf.write(buf, array, sample_rate, format="WAV", subtype="PCM_16")
        return buf.getvalue()


def _clean_tts_text(text: str) -> str:
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\[[^\]]*\]", "", text)
    text = re.sub(r"\([^)]*\)", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    if not re.search(r"[\w\d\u00C0-\u1EF9]", text, re.IGNORECASE):
        return ""
    return text


def _cache_key(voice: str, speed: float, text: str) -> str:
    """Keyed on the text itself, so an edited SRT line never reuses stale audio."""
    return f"{voice}_{speed}_{hashlib.sha1(text.encode()).hexdigest()[:12]}.wav"


def _build_atempo_filter(ratio: float) -> str:
    ratio = max(0.25, min(ratio, 4.0))
    filters = []
    remaining = ratio
    while remaining > 2.0:
        filters.append("atempo=2.0")
        remaining /= 2.0
    while remaining < 0.5:
        filters.append("atempo=0.5")
        remaining /= 0.5
    filters.append(f"atempo={remaining:.4f}")
    return ",".join(filters)


def _stretch_one_clip(clip_path: Path, target_ms: int) -> Path | None:
    clip_ms = sf.info(str(clip_path)).duration * 1000
    if clip_ms <= 0 or target_ms <= 0:
        return None

    ratio = clip_ms / target_ms
    if ratio <= 1.0:
        return None

    atempo = _build_atempo_filter(ratio)
    out_path = clip_path.with_name(f"{clip_path.stem}_stretched.wav")
    cmd = [
        "ffmpeg", "-y", "-i", str(clip_path),
        "-filter:a", atempo,
        "-vn", str(out_path), "-loglevel", "error",
    ]
    result = subprocess.run(cmd, capture_output=True, stdin=subprocess.DEVNULL, timeout=300)
    if result.returncode == 0 and out_path.exists():
        return out_path
    return None


class EdgeTTSEngine:
    def __init__(self, default_voice: str = "vi-VN-HoaiMyNeural"):
        self.default_voice = default_voice

    def synthesize(
        self,
        text: str,
        voice: str | None = None,
        speed: float = 1.0,
    ) -> tuple[bytes, float, float]:
        import edge_tts

        cleaned = _clean_tts_text(text)
        if not cleaned:
            wav_bytes = _generate_silent_wav_bytes(0.5)
            return wav_bytes, 0.5, 0.0

        selected_voice = voice or self.default_voice
        if not selected_voice.startswith("vi-VN-"):
            selected_voice = "vi-VN-HoaiMyNeural" if "F" in selected_voice.upper() else "vi-VN-NamMinhNeural"

        rate_int = int(round((speed - 1.0) * 100))
        rate_str = f"{rate_int:+d}%"

        start_t = time.time()
        last_err = None

        for attempt in range(3):
            try:
                comm = edge_tts.Communicate(cleaned, selected_voice, rate=rate_str, receive_timeout=120)
                mp3_data = b""
                for chunk in comm.stream_sync():
                    if chunk["type"] == "audio":
                        mp3_data += chunk["data"]

                if not mp3_data:
                    raise DubbingError("Edge-TTS returned empty audio.")

                p = subprocess.run(
                    ["ffmpeg", "-y", "-i", "pipe:0", "-ar", "44100", "-ac", "1", "-f", "wav", "pipe:1"],
                    input=mp3_data,
                    capture_output=True,
                )
                if p.returncode != 0 or not p.stdout:
                    err_msg = p.stderr.decode("utf-8", errors="ignore")
                    raise DubbingError(f"FFmpeg audio conversion failed: {err_msg}")

                wav_bytes = p.stdout
                with io.BytesIO(wav_bytes) as f:
                    dur = sf.info(f).duration

                latency = time.time() - start_t
                return wav_bytes, dur, latency
            except Exception as exc:
                last_err = exc
                time.sleep(0.4 * (attempt + 1))

        print(f"[EdgeTTSEngine Warning] Failed to synthesize '{cleaned[:35]}…' ({last_err}); using silence.")
        wav_bytes = _generate_silent_wav_bytes(0.5)
        return wav_bytes, 0.5, 0.0


class VieNeuTTS:
    """Fully offline Vietnamese TTS via VieNeu-TTS v3 Turbo (ONNX)."""
    _instance = None
    _lock = __import__("threading").Lock()

    _device = None
    _ref_voices: dict[str, dict] = {}  # ref_audio path -> encoded voice; numpy on CPU, survives model reloads

    def __init__(self, default_voice: str = "Minh Quân", ref_audio: str | None = None, device: str | None = None):
        self.default_voice = default_voice
        self.ref_audio = ref_audio
        self.device = device
        self._ref_voice = None

    def _lazy(self):
        device = self.device or os.environ.get("VIENEU_DEVICE", "cpu")
        with self._lock:
            if self._instance is None or type(self)._device != device:
                try:
                    import importlib
                    vieneu_mod = importlib.import_module('vieneu')
                    Vieneu = vieneu_mod.Vieneu
                except ImportError as exc:
                    raise DubbingError("VieNeu-TTS needs 'vieneu'. Install with: uv add vieneu") from exc
                os.environ.setdefault("CC", "/usr/bin/gcc")
                with MODEL_LOAD_LOCK:
                    v = Vieneu(device=device)
                v.list_preset_voices()
                type(self)._instance = v
                type(self)._device = device
            # vieneu re-denoises + re-encodes ref_audio on CPU (~2.4s) on every infer(); encode once.
            if self.ref_audio and self._ref_voice is None:
                if self.ref_audio not in self._ref_voices:
                    emb, codes = self._instance.encode_reference(self.ref_audio)
                    self._ref_voices[self.ref_audio] = {"speaker_emb": emb, "codes": codes}
                self._ref_voice = self._ref_voices[self.ref_audio]
        return self._instance

    def import_backend(self) -> None:
        """Call on the main thread before preload() runs in a background thread: importing transformers from
        two threads at once (vieneu's torch engine + the HF translator) leaves it half-initialised and the
        loser fails with "cannot import name 'PretrainedConfig'". The ONNX/CPU engine doesn't use transformers."""
        if (self.device or os.environ.get("VIENEU_DEVICE", "cpu")) != "cpu":
            import vieneu._v3_turbo_engine.inference_v3_turbo  # noqa: F401

    def preload(self) -> None:
        """Load the model, encode the clone ref and warm up the kernels (~13s on an RTX 3050), so a caller
        can overlap it with other work. Not thread-safe against a concurrent synthesize: join first."""
        self.synthesize_batch(["Xin chào."])

    def synthesize(
        self,
        text: str,
        voice: str | None = None,
        speed: float = 1.0,
    ) -> tuple[bytes, float, float]:
        v = self._lazy()
        cleaned = _clean_tts_text(text)
        if not cleaned:
            return _generate_silent_wav_bytes(0.5), 0.5, 0.0

        selected_voice = voice or self.default_voice
        start_t = time.time()
        try:
            if self._ref_voice:
                audio = v.infer(cleaned, voice=self._ref_voice)
            else:
                audio = v.infer(cleaned, voice=selected_voice)
        except Exception as exc:
            print(f"[VieNeu Warning] Failed to synthesize '{cleaned[:35]}…' ({exc}); using silence.")
            return _generate_silent_wav_bytes(0.5), 0.5, 0.0

        wav_bytes = _array_to_wav(audio, 48000)
        with io.BytesIO(wav_bytes) as f:
            dur = sf.info(f).duration
        return wav_bytes, dur, time.time() - start_t

    def synthesize_batch(self, texts: list[str], voice: str | None = None) -> list[bytes]:
        """All lines in one call: on GPU vieneu shares each forward step across lines (~3-4x faster than per-line infer)."""
        v = self._lazy()
        try:
            audios = v.infer_batch(
                [_clean_tts_text(t) for t in texts], voice=self._ref_voice or voice or self.default_voice
            )
        except Exception as exc:
            print(f"[VieNeu Warning] Batch synthesis failed ({exc}); falling back to one line at a time.")
            return [self.synthesize(t, voice=voice)[0] for t in texts]
        return [_array_to_wav(a, 48000) if len(a) else _generate_silent_wav_bytes(0.5) for a in audios]


def create_vietnamese_dub(
    video_path: Path,
    blocks: list[SubtitleBlock],
    work_dir: Path,
    output_path: Path,
    voice: str = "vi-VN-HoaiMyNeural",
    speed: float = 1.05,
    background_volume: float = 0.0,
    voice_volume: float = 1.0,
    tts_provider: str = "edge",
    ref_audio: str | None = None,
    tts_device: str | None = None,
) -> Path:
    if not blocks:
        raise DubbingError("No subtitle blocks available for dubbing.")

    clips_dir = work_dir / "dub_clips"
    clips_dir.mkdir(parents=True, exist_ok=True)
    cache_dir = work_dir / "tts_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    dub_audio = work_dir / "dub_vi.wav"

    if tts_provider == "vieneu":
        engine = VieNeuTTS(default_voice=voice or "Minh Quân", ref_audio=ref_audio, device=tts_device)
    else:
        engine = EdgeTTSEngine(default_voice=voice)
    clip_paths: list[tuple[Path, int, float]] = []
    workers = max(1, min(8, int(os.environ.get("TTS_PARALLEL", "4"))))

    def _render(task: tuple[SubtitleBlock, str, int, float]) -> tuple[Path, int, float] | None:
        block, text, start_ms, slot_sec = task
        clip_path = clips_dir / f"{block.index:05d}.wav"
        cached_path = cache_dir / _cache_key(voice, speed, text)
        try:
            if cached_path.exists() and cached_path.stat().st_size > 0:
                clip_path.write_bytes(cached_path.read_bytes())
            else:
                wav_bytes, duration, _latency = engine.synthesize(text, voice=voice, speed=speed)
                clip_path.write_bytes(wav_bytes)
                cached_path.write_bytes(wav_bytes)
            return clip_path, start_ms, slot_sec
        except Exception as exc:
            print(f"[Dubbing Warning] Skipped block {block.index}: {exc}")
            return None

    DUB_PHASES.clear()
    phase_t = time.time()

    def _phase(name: str) -> None:
        nonlocal phase_t
        now = time.time()
        DUB_PHASES[name] = round(now - phase_t, 1)
        phase_t = now

    # Pass 1: generate TTS with cache
    tasks: list[tuple[SubtitleBlock, str, int, float]] = []
    for block in blocks:
        text = _clean_tts_text(block.text)
        if not text:
            continue
        start_ms = int(round(srt_time_to_seconds(block.start) * 1000))
        slot_sec = max(0.25, srt_time_to_seconds(block.end) - srt_time_to_seconds(block.start))
        tasks.append((block, text, start_ms, slot_sec))

    if isinstance(engine, VieNeuTTS) and tts_device == "cuda":  # on CPU/ONNX infer_batch is sequential; threads win there
        # Fill the cache in one batched call; _render below then just copies cached clips.
        todo = {}
        for _block, text, _start_ms, _slot in tasks:
            cached_path = cache_dir / _cache_key(voice, speed, text)
            if not (cached_path.exists() and cached_path.stat().st_size > 0):
                todo[cached_path] = text
        if todo:
            for cached_path, wav_bytes in zip(todo, engine.synthesize_batch(list(todo.values()), voice=voice)):
                cached_path.write_bytes(wav_bytes)

    if workers > 1:
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
            for result in pool.map(_render, tasks):
                if result:
                    clip_paths.append(result)
    else:
        for task in tasks:
            result = _render(task)
            if result:
                clip_paths.append(result)

    if not clip_paths:
        raise DubbingError("No TTS clips were generated.")
    _phase("synth_sec")

    # Pass 2: Regen slow cues (> 2x slot duration)
    def _regen(item: tuple[Path, int, float]) -> None:
        clip_path, _start_ms, slot_sec = item

        clip_dur = sf.info(str(clip_path)).duration
        if clip_dur <= 0 or slot_sec <= 0:
            return

        if (clip_dur / slot_sec) > SLOW_RATIO_THRESHOLD and speed * SLOW_SPEED_BOOST < 2.0:
            block_index = int(clip_path.stem)
            block = next((b for b in blocks if b.index == block_index), None)
            if not block:
                return
            text = _clean_tts_text(block.text)
            if not text:
                return
            cached_path = cache_dir / _cache_key(voice, speed, text)
            marker = cached_path.with_name(cached_path.name + ".fast")
            if marker.exists():
                return

            try:
                fast_speed = min(2.0, speed * SLOW_SPEED_BOOST)
                wav_bytes, _duration, _latency = engine.synthesize(text, voice=voice, speed=fast_speed)
                clip_path.write_bytes(wav_bytes)
                cached_path.write_bytes(wav_bytes)
                marker.touch()
            except Exception as exc:
                print(f"[Dubbing Warning] Regen failed for block {block_index}: {exc}")

    if tts_provider == "vieneu":
        pass  # VieNeu ignores `speed`, so a "faster" regen would just re-roll the same clip; stretch-fit handles it
    elif workers > 1:
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
            for _ in pool.map(_regen, clip_paths):
                pass
    else:
        for item in clip_paths:
            _regen(item)

    # Stretch fit
    def _fit(item: tuple[Path, int, float]) -> tuple[Path, int]:
        clip_path, start_ms, slot_sec = item
        return _stretch_one_clip(clip_path, int(round(slot_sec * 1000))) or clip_path, start_ms

    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        final_clips: list[tuple[Path, int]] = list(pool.map(_fit, clip_paths))

    _phase("fit_sec")
    media = probe_media(video_path)
    total_duration = float(media["format"]["duration"])
    _mix_delayed_clips(final_clips, dub_audio, total_duration)

    _phase("mix_sec")
    for clip_path, _ in final_clips:
        if "_stretched" in clip_path.name:
            try:
                clip_path.unlink()
            except OSError:
                pass

    if background_volume > 0:
        _mux_mixed_audio(video_path, dub_audio, output_path, background_volume, voice_volume)
    else:
        _mux_replace_audio(video_path, dub_audio, output_path, voice_volume)
    _phase("mux_sec")
    return output_path


def _mix_delayed_clips(
    clips: list[tuple[Path, int]],
    output_path: Path,
    duration: float,
    chunk_seconds: float = 300.0,
) -> None:
    require_tool("ffmpeg")
    chunk_dir = output_path.parent / "dub_chunks"
    chunk_dir.mkdir(parents=True, exist_ok=True)
    clip_info = [
        (path, start_ms / 1000.0, start_ms / 1000.0 + float(sf.info(path).duration))
        for path, start_ms in clips
    ]
    chunk_paths: list[Path] = []

    for chunk_index in range(math.ceil(duration / chunk_seconds)):
        chunk_start = chunk_index * chunk_seconds
        chunk_end = min(duration, chunk_start + chunk_seconds)
        chunk_duration = chunk_end - chunk_start
        active = [item for item in clip_info if item[1] < chunk_end and item[2] > chunk_start]
        chunk_path = chunk_dir / f"chunk_{chunk_index:05d}.wav"

        if active:
            _render_audio_chunk(active, chunk_path, chunk_start, chunk_duration)
        else:
            run_command(
                [
                    "ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
                    "-t", f"{chunk_duration:.6f}", "-c:a", "pcm_s16le", str(chunk_path),
                ]
            )
        chunk_paths.append(chunk_path)

    concat_list = chunk_dir / "concat.txt"
    concat_list.write_text(
        "".join(f"file '{path.name}'\n" for path in chunk_paths),
        encoding="utf-8",
    )
    run_command(
        [
            "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_list),
            "-c:a", "copy", str(output_path),
        ]
    )
    concat_list.unlink(missing_ok=True)
    for p in chunk_paths:
        p.unlink(missing_ok=True)
    chunk_dir.rmdir()


def _render_audio_chunk(
    clips: list[tuple[Path, float, float]],
    output_path: Path,
    chunk_start: float,
    chunk_duration: float,
) -> None:
    args = ["ffmpeg", "-y"]
    for clip_path, _start, _end in clips:
        args.extend(["-i", str(clip_path)])

    filter_parts = []
    labels = []
    chunk_end = chunk_start + chunk_duration
    for index, (_path, clip_start, clip_end) in enumerate(clips):
        trim_start = max(0.0, chunk_start - clip_start)
        trim_end = min(clip_end, chunk_end) - clip_start
        delay_ms = max(0, int(round((clip_start - chunk_start) * 1000)))
        label = f"a{index}"
        labels.append(f"[{label}]")
        filter_parts.append(
            f"[{index}:a]atrim=start={trim_start:.6f}:end={trim_end:.6f},"
            f"asetpts=PTS-STARTPTS,adelay={delay_ms}:all=1[{label}]"
        )

    filter_parts.append(
        "".join(labels)
        + f"amix=inputs={len(clips)}:duration=longest:dropout_transition=0:normalize=0,"
        + f"apad,atrim=0:{chunk_duration:.6f},alimiter=limit=0.95[dub]"
    )
    args.extend(
        [
            "-filter_complex", ";".join(filter_parts), "-map", "[dub]",
            "-ar", "44100", "-ac", "2", "-c:a", "pcm_s16le", str(output_path),
        ]
    )
    run_command(args)


def _mux_replace_audio(video_path: Path, audio_path: Path, output_path: Path, voice_volume: float) -> None:
    require_tool("ffmpeg")
    voice_volume = max(0.1, min(3.0, voice_volume))
    run_command(
        [
            "ffmpeg", "-y", "-i", str(video_path), "-i", str(audio_path),
            "-map", "0:v:0", "-map", "1:a:0", "-map", "0:s?",
            "-filter:a", f"volume={voice_volume:.3f},alimiter=limit=0.95",
            "-c:v", "copy", "-c:s", "copy",
            "-c:a", "aac", "-aac_coder", "fast",  # default twoloop coder: ~4x slower, no audible gain for speech
            "-shortest", str(output_path),
        ]
    )


def _mux_mixed_audio(
    video_path: Path,
    audio_path: Path,
    output_path: Path,
    background_volume: float,
    voice_volume: float,
) -> None:
    require_tool("ffmpeg")
    bg_vol = max(0.0, min(1.0, background_volume))
    vc_vol = max(0.1, min(3.0, voice_volume))
    filter_spec = (
        f"[0:a]volume={bg_vol:.3f}[bg];"
        f"[1:a]volume={vc_vol:.3f}[vc];"
        f"[bg][vc]amix=inputs=2:duration=first:dropout_transition=0,alimiter=limit=0.95[aout]"
    )
    run_command(
        [
            "ffmpeg", "-y", "-i", str(video_path), "-i", str(audio_path),
            "-filter_complex", filter_spec,
            "-map", "0:v:0", "-map", "[aout]", "-map", "0:s?",
            "-c:v", "copy", "-c:s", "copy",
            "-c:a", "aac", "-aac_coder", "fast",  # default twoloop coder: ~4x slower, no audible gain for speech
            "-shortest", str(output_path),
        ]
    )
