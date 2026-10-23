"""Vocal removal with Demucs (htdemucs): the dub keeps the original music/effects instead of the whole
original track turned down, which still let the source voice through."""
from __future__ import annotations

import gc
from pathlib import Path
from typing import Callable

import numpy as np
import soundfile as sf

from . import MODEL_LOAD_LOCK

# htdemucs returns 4 float32 stems per call: a 91-min video in one call is ~7 GB of RAM, a 10-min chunk ~1 GB.
CHUNK_SEC = 600
PAD_SEC = 5  # extra context on each side of a chunk, cut off again, so the seams carry no edge artifacts


class SeparationError(RuntimeError):
    pass


def _make_separator(device: str):
    from demucs.api import Separator

    with MODEL_LOAD_LOCK:  # from_pretrained-style loads elsewhere patch nn.Module process-wide
        return Separator(model="htdemucs", device=device)


def separate_background(
    audio_path: Path,
    output_path: Path,
    device: str = "cpu",
    free_vram: Callable[[], bool] | None = None,
    chunk_sec: float = CHUNK_SEC,
    pad_sec: float = PAD_SEC,
) -> str:
    """Write `audio_path` minus its vocals to `output_path`. The input must be 44.1 kHz stereo (htdemucs's own
    format). Returns the device actually used: on a CUDA error, `free_vram` gets one chance to make room for a
    GPU retry, then it falls back to CPU (same policy as FasterWhisperTranscriber)."""
    while True:
        try:
            _separate(audio_path, output_path, device, chunk_sec, pad_sec)
            return device
        except Exception as exc:
            if device == "cpu" or not any(m in str(exc).lower() for m in ("cuda", "cublas", "cudnn", "gpu")):
                raise SeparationError(str(exc)) from exc
            error = str(exc)
        if free_vram is not None and free_vram():
            print(f"[Demucs Warning] {error[:160]}; freed VRAM, retrying on {device}")
        else:
            print(f"[Demucs Warning] {error[:160]}; falling back to CPU")
            device = "cpu"
        free_vram = None


def _separate(audio_path: Path, output_path: Path, device: str, chunk_sec: float, pad_sec: float) -> None:
    import torch

    separator = _make_separator(device)
    try:
        if device == "cuda":
            torch.cuda.reset_peak_memory_stats()
        info = sf.info(str(audio_path))
        rate, total = info.samplerate, info.frames
        chunk, pad = int(chunk_sec * rate), int(pad_sec * rate)
        with sf.SoundFile(str(audio_path)) as src, \
                sf.SoundFile(str(output_path), "w", rate, info.channels, "PCM_16") as dst:
            for start in range(0, total, chunk):
                lo, hi = max(0, start - pad), min(total, start + chunk + pad)
                src.seek(lo)
                mix = src.read(hi - lo, dtype="float32", always_2d=True)  # (frames, channels)
                wav, stems = separator.separate_tensor(torch.from_numpy(np.ascontiguousarray(mix.T)), rate)
                # Mix minus vocals, not the sum of the other stems: keeps the background at its original level.
                background = (wav - stems["vocals"]).cpu().numpy().T
                keep = background[start - lo:start - lo + min(chunk, total - start)]
                dst.write(np.clip(keep, -1.0, 1.0))  # mix - vocals can overshoot the PCM_16 range
        if device == "cuda":
            print(f"[Demucs] peak VRAM {torch.cuda.max_memory_allocated() / 2**20:.0f} MiB")
    finally:
        del separator
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
