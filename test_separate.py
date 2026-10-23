"""Self-check for chunked vocal removal (fake separator, no model download). Run: python test_separate.py"""
import tempfile
from pathlib import Path

import numpy as np
import soundfile as sf

from pipeline import separate


class FakeSeparator:
    calls = 0

    def separate_tensor(self, wav, sr):
        FakeSeparator.calls += 1
        return wav, {"vocals": wav * 0.5}


def _input(path: Path, frames: int, rate: int = 100) -> np.ndarray:
    t = np.arange(frames) / rate
    audio = np.stack([np.sin(t), np.cos(t)], axis=1).astype(np.float32) * 0.8
    sf.write(str(path), audio, rate, "PCM_16")
    return sf.read(str(path), dtype="float32")[0]


def test_chunks_stitch_back_to_mix_minus_vocals():
    separate._make_separator = lambda device: FakeSeparator()
    FakeSeparator.calls = 0
    with tempfile.TemporaryDirectory() as tmp:
        src, out = Path(tmp) / "in.wav", Path(tmp) / "bg.wav"
        audio = _input(src, 1050)  # 10.5 s at 100 Hz: chunks of 3 s + 0.5 s padding, last one partial
        assert separate.separate_background(src, out, "cpu", chunk_sec=3, pad_sec=0.5) == "cpu"
        bg, rate = sf.read(str(out), dtype="float32")
        assert rate == 100 and bg.shape == audio.shape
        assert np.abs(bg - audio * 0.5).max() < 1e-3  # seams included
        assert FakeSeparator.calls == 4


def test_cuda_error_frees_vram_then_falls_back_to_cpu():
    devices, freed = [], []

    def factory(device):
        devices.append(device)
        if device == "cuda":
            raise RuntimeError("CUDA out of memory. Tried to allocate 1.00 GiB")
        return FakeSeparator()

    separate._make_separator = factory
    with tempfile.TemporaryDirectory() as tmp:
        src, out = Path(tmp) / "in.wav", Path(tmp) / "bg.wav"
        _input(src, 300)
        used = separate.separate_background(src, out, "cuda", free_vram=lambda: freed.append(1) or True)
    assert used == "cpu" and devices == ["cuda", "cuda", "cpu"] and freed == [1]


def test_other_errors_are_not_retried():
    separate._make_separator = lambda device: (_ for _ in ()).throw(ValueError("bad file"))
    try:
        separate.separate_background(Path("x.wav"), Path("y.wav"), "cuda")
    except separate.SeparationError as exc:
        assert "bad file" in str(exc)
    else:
        raise AssertionError("expected SeparationError")


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
