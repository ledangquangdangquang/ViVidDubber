"""Minimal self-check for length-sorted translation batching. Run: python test_translate.py"""
from pipeline.subtitle import SubtitleBlock
from pipeline.translate import _translate_blocks


class FakeTranslator:
    def __init__(self, drop_batch: int | None = None):
        self.batches: list[list[str]] = []
        self.drop_batch = drop_batch  # return one line too few for this batch, to force the per-line fallback

    def _translate_texts(self, texts, source_lang, target_lang):
        self.batches.append(list(texts))
        out = ["" if t == "blank" else t.upper() for t in texts]
        return out[:-1] if len(self.batches) - 1 == self.drop_batch else out


def _blocks(*texts):
    return [SubtitleBlock(index=i + 1, start=f"00:00:0{i},000", end=f"00:00:0{i},900", text=t) for i, t in enumerate(texts)]


def test_sorted_batches_keep_original_order():
    blocks = _blocks("a much longer line here", "hi", "blank", "medium line", "yo")
    tr = FakeTranslator()
    out = _translate_blocks(tr, blocks, "en", "vi", batch_size=2)
    assert tr.batches == [["hi", "yo"], ["blank", "medium line"], ["a much longer line here"]]
    assert [b.text for b in out] == ["A MUCH LONGER LINE HERE", "HI", "blank", "MEDIUM LINE", "YO"]
    assert [(b.index, b.start, b.end) for b in out] == [(b.index, b.start, b.end) for b in blocks]
    assert tr.warnings == ["dòng 3 chưa dịch được, giữ bản gốc tiếng Anh"]


def test_count_mismatch_falls_back_per_line():
    blocks = _blocks("one", "three", "two2")
    tr = FakeTranslator(drop_batch=0)
    out = _translate_blocks(tr, blocks, "en", "vi", batch_size=3)
    assert tr.batches[1:] == [["one"], ["two2"], ["three"]]
    assert [b.text for b in out] == ["ONE", "THREE", "TWO2"]


if __name__ == "__main__":
    test_sorted_batches_keep_original_order()
    test_count_mismatch_falls_back_per_line()
    print("ok")
