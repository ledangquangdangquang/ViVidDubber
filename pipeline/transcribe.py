from __future__ import annotations

import os
from pathlib import Path

from .subtitle import SubtitleBlock, seconds_to_srt_time, write_srt


class TranscriptionError(RuntimeError):
    pass


def group_sentences(segments, pause: float = 0.6, soft_chars: int = 150, seg_chars: int = 250, max_chars: int = 300) -> list[tuple[float, float, str]]:
    """Regroup Whisper words (across segments) into whole sentences so translation/TTS get full context.

    Cuts at . ? !; when Whisper skipped punctuation, falls back to a pause >= `pause` s (once the text
    is >= soft_chars), a segment end (once >= seg_chars), and finally a hard max_chars cap.
    """
    words = [(w, i == len(seg.words) - 1) for seg in segments for i, w in enumerate(seg.words or [])]
    chunks: list[tuple[float, float, str]] = []
    current: list = []
    for i, (w, seg_end) in enumerate(words):
        current.append(w)
        text = "".join(x.word for x in current).strip()
        gap = words[i + 1][0].start - w.end if i + 1 < len(words) else 0.0
        if (
            w.word.strip().endswith((".", "?", "!"))
            or (gap >= pause and len(text) >= soft_chars)
            or (seg_end and len(text) >= seg_chars)
            or len(text) >= max_chars
        ):
            chunks.append((current[0].start, current[-1].end, text))
            current = []
    if current:
        chunks.append((current[0].start, current[-1].end, "".join(x.word for x in current).strip()))
    return [c for c in chunks if c[2]]


class FasterWhisperTranscriber:
    def __init__(self, model_name: str = "small", device: str | None = None, compute_type: str | None = None):
        self.model_name = model_name
        self.device = device or os.environ.get("WHISPER_DEVICE", "cpu")
        self.compute_type = compute_type or os.environ.get("WHISPER_COMPUTE_TYPE", "int8")

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
            if self.device != "cpu" and any(m in str(exc).lower() for m in ("cuda", "cublas", "cudnn", "gpu")):
                self.device = "cpu"
                self.compute_type = "int8"
                return self._run_transcription(whisper_model, audio_path, kwargs)
            raise TranscriptionError(str(exc)) from exc
