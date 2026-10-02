"""Minimal self-check for sentence grouping. Run: python test_transcribe.py"""
from types import SimpleNamespace as NS

from pipeline.transcribe import FasterWhisperTranscriber, group_sentences


def _seg(*words):
    return NS(words=[NS(start=s, end=e, word=t) for s, e, t in words])


def test_stray_first_word_reanchors_start():
    # Real case (job d3e982ad9fa7, 23:05): Whisper put "This" 15 s before the rest of the sentence.
    segs = [_seg((1385.4, 1385.9, " This"), (1400.7, 1400.8, " is"), (1400.8, 1407.6, " a lot of money.")),
            _seg((1407.7, 1412.9, " But it is comparable."))]
    chunks = group_sentences(segs)
    assert chunks[0] == (1400.7, 1407.6, "This is a lot of money.")  # text kept whole, start moved
    assert chunks[1][0] == 1407.7


def test_long_fragment_before_gap_untouched():
    segs = [_seg((0.0, 2.0, " Here is a much longer lead-in"), (6.0, 7.0, " before the end."))]
    assert group_sentences(segs)[0][0] == 0.0



def _fake_whisper(fail_on_cuda: int):
    calls = []

    class FakeModel:
        def __init__(self, name, device, compute_type):
            calls.append(device)
            if device == "cuda" and len(calls) <= fail_on_cuda:
                raise RuntimeError("CUDA failed with error out of memory")

        def transcribe(self, *a, **k):
            return [_seg((0.0, 1.0, " Hi."))], NS(language="en")

    return FakeModel, calls


def test_cuda_oom_frees_vram_and_retries_on_gpu():
    model, calls = _fake_whisper(fail_on_cuda=1)
    freed = []
    t = FasterWhisperTranscriber(device="cuda", free_vram=lambda: freed.append(1) or True)
    blocks, _ = t._run_transcription(model, None, {})
    assert calls == ["cuda", "cuda"] and t.device == "cuda" and freed == [1] and blocks[0].text == "Hi."


def test_cuda_oom_falls_back_to_cpu_when_nothing_to_free():
    model, calls = _fake_whisper(fail_on_cuda=2)
    t = FasterWhisperTranscriber(device="cuda", free_vram=lambda: True)  # frees once, still OOM -> CPU
    t._run_transcription(model, None, {})
    assert calls == ["cuda", "cuda", "cpu"] and t.device == "cpu"
    model, calls = _fake_whisper(fail_on_cuda=1)
    t = FasterWhisperTranscriber(device="cuda", free_vram=lambda: False)
    t._run_transcription(model, None, {})
    assert calls == ["cuda", "cpu"]


if __name__ == "__main__":
    test_stray_first_word_reanchors_start()
    test_long_fragment_before_gap_untouched()
    test_cuda_oom_frees_vram_and_retries_on_gpu()
    test_cuda_oom_falls_back_to_cpu_when_nothing_to_free()
    print("ok")
