from __future__ import annotations

import os
from pathlib import Path

from .subtitle import SubtitleBlock, seconds_to_srt_time, write_srt


class TranscriptionError(RuntimeError):
    pass


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
                **kwargs,
            )
            blocks = [
                SubtitleBlock(
                    index=i,
                    start=seconds_to_srt_time(segment.start),
                    end=seconds_to_srt_time(segment.end),
                    text=segment.text.strip(),
                )
                for i, segment in enumerate(segments, 1)
                if segment.text.strip()
            ]
            return blocks, info.language
        except Exception as exc:
            if self.device != "cpu" and any(m in str(exc).lower() for m in ("cuda", "cublas", "cudnn", "gpu")):
                self.device = "cpu"
                self.compute_type = "int8"
                return self._run_transcription(whisper_model, audio_path, kwargs)
            raise TranscriptionError(str(exc)) from exc
