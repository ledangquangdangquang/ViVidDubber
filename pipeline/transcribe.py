from __future__ import annotations

from collections.abc import Callable
import os
from pathlib import Path

from .subtitle import SubtitleBlock, seconds_to_srt_time, write_srt


class TranscriptionError(RuntimeError):
    pass


def group_sentences(
    segments, pause: float = 0.6, soft_chars: int = 150, seg_chars: int = 250, max_chars: int = 300,
    stray_gap: float = 3.0, stray_chars: int = 20,
) -> list[tuple[float, float, str]]:
    """Regroup Whisper words (across segments) into whole sentences so translation/TTS get full context.

    Cuts at . ? !; when Whisper skipped punctuation, falls back to a pause >= `pause` s (once the text
    is >= soft_chars), a segment end (once >= seg_chars), and finally a hard max_chars cap.
    Whisper sometimes drops a sentence's first word(s) seconds before the rest (over music/B-roll);
    a fragment < stray_chars followed by a gap >= stray_gap re-anchors the cue start after the gap,
    otherwise the sub shows early and the dub finishes long before the cue ends.
    """
    words = [(w, i == len(seg.words) - 1) for seg in segments for i, w in enumerate(seg.words or [])]
    chunks: list[tuple[float, float, str]] = []
    current: list = []
    start = 0.0
    for i, (w, seg_end) in enumerate(words):
        if not current:
            start = w.start
        current.append(w)
        text = "".join(x.word for x in current).strip()
        gap = words[i + 1][0].start - w.end if i + 1 < len(words) else 0.0
        if (
            w.word.strip().endswith((".", "?", "!"))
            or (gap >= pause and len(text) >= soft_chars)
            or (seg_end and len(text) >= seg_chars)
            or len(text) >= max_chars
        ):
            chunks.append((start, current[-1].end, text))
            current = []
        elif gap >= stray_gap and len(text) < stray_chars:
            start = words[i + 1][0].start
    if current:
        chunks.append((start, current[-1].end, "".join(x.word for x in current).strip()))
    return [c for c in chunks if c[2]]


class FasterWhisperTranscriber:
    def __init__(
        self, model_name: str = "small", device: str | None = None, compute_type: str | None = None,
        free_vram: Callable[[], bool] | None = None,
    ):
        self.model_name = model_name
        self.device = device or os.environ.get("WHISPER_DEVICE", "cpu")
        self.compute_type = compute_type or os.environ.get("WHISPER_COMPUTE_TYPE", "int8")
        # Called once on a CUDA error before falling back to CPU; returns True if it freed VRAM worth a GPU retry.
        self.free_vram = free_vram

    def transcribe_to_srt(
        self,
        audio_path: Path,
        srt_path: Path,
        source_lang: str = "en",
    ) -> list[SubtitleBlock]:
        try:
            from faster_whisper import WhisperModel
        except ImportError as exc:
            raise TranscriptionError("Missing faster-whisper. Install dependencies.") from exc

        blocks, _ = self._run_transcription(WhisperModel, audio_path, {"language": source_lang})
        srt_path.write_text(write_srt(blocks), encoding="utf-8")
        return blocks

    def _run_transcription(self, whisper_model, audio_path: Path, kwargs: dict) -> tuple[list[SubtitleBlock], str]:
        model = segments = None
        try:
            model = whisper_model(
                self.model_name,
                device=self.device,
                compute_type=self.compute_type,
            )
            beam_size = int(os.environ.get("WHISPER_BEAM_SIZE", "1"))
            segments, info = model.transcribe(
                str(audio_path),
                vad_filter=True,
                beam_size=beam_size,
                word_timestamps=True,
                # Conditioned on the previous window, one window that drops punctuation makes every later one drop
                # it too (91-min interview: none after 9:47 -> 354 run-on cues of ~207 chars). Independent windows
                # kept it all the way through (1,279 sentence marks) and ran a bit faster.
                condition_on_previous_text=False,
                **kwargs,
            )
            chunks = group_sentences(segments)
            blocks = [
                SubtitleBlock(
                    index=i,
                    start=seconds_to_srt_time(start),
                    end=seconds_to_srt_time(end),
                    text=text,
                )
                for i, (start, end, text) in enumerate(chunks, 1)
            ]
            return blocks, info.language
        except Exception as exc:
            if self.device == "cpu" or not any(m in str(exc).lower() for m in ("cuda", "cublas", "cudnn", "gpu")):
                raise TranscriptionError(str(exc)) from exc
            error = str(exc)
        # Retry outside the except block and after dropping our refs, or the failed model stays in VRAM.
        model = segments = None
        free_vram, self.free_vram = self.free_vram, None
        if free_vram is not None and free_vram():
            print(f"[Whisper Warning] {error[:160]}; freed VRAM, retrying on {self.device}")
        else:
            self.device = "cpu"
            self.compute_type = "int8"
        return self._run_transcription(whisper_model, audio_path, kwargs)
