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



def test_cjk_cuts_at_fullwidth_marks():
    from pipeline.transcribe import _CJK_LIMITS
    segs = [_seg((0.0, 1.0, "它可以杀人"), (1.0, 1.2, "。"), (1.3, 2.0, "你知道吗"), (2.0, 2.1, "？"))]
    assert [c[2] for c in group_sentences(segs, **_CJK_LIMITS)] == ["它可以杀人。", "你知道吗？"]
    # No punctuation at all: the CJK cap still cuts long before the 300-char Latin cap.
    segs = [_seg(*[(i * 0.2, i * 0.2 + 0.2, "字") for i in range(250)])]
    assert max(len(c[2]) for c in group_sentences(segs, **_CJK_LIMITS)) <= 100


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


def test_cpu_drops_gpu_only_compute_type():
    # The UI's hidden field can still say int8_float16 when the device select says CPU -> ctranslate2 refuses it.
    assert FasterWhisperTranscriber(device="cpu", compute_type="int8_float16").compute_type == "int8"
    assert FasterWhisperTranscriber(device="cuda", compute_type="int8_float16").compute_type == "int8_float16"


if __name__ == "__main__":
    test_stray_first_word_reanchors_start()
    test_long_fragment_before_gap_untouched()
    test_cuda_oom_frees_vram_and_retries_on_gpu()
    test_cuda_oom_falls_back_to_cpu_when_nothing_to_free()
    test_cpu_drops_gpu_only_compute_type()
    test_cjk_cuts_at_fullwidth_marks()
    print("ok")
