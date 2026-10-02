"""Minimal self-check for sentence grouping. Run: python test_transcribe.py"""
from types import SimpleNamespace as NS

from pipeline.transcribe import group_sentences


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


if __name__ == "__main__":
    test_stray_first_word_reanchors_start()
    test_long_fragment_before_gap_untouched()
    print("ok")
