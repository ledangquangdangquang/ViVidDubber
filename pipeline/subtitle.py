from __future__ import annotations

from dataclasses import dataclass
import re


@dataclass
class SubtitleBlock:
    index: int
    start: str
    end: str
    text: str


def srt_time_to_seconds(srt_time: str) -> float:
    match = re.match(r"^(\d{2}):(\d{2}):(\d{2})[,.](\d{3})$", srt_time.strip())
    if not match:
        raise ValueError(f"Invalid SRT timestamp: {srt_time}")
    hours, minutes, seconds, millis = map(int, match.groups())
    return hours * 3600 + minutes * 60 + seconds + millis / 1000.0


def seconds_to_srt_time(seconds: float) -> str:
    if seconds < 0:
        seconds = 0.0
    total_ms = int(round(seconds * 1000))
    hours = total_ms // 3600000
    total_ms %= 3600000
    minutes = total_ms // 60000
    total_ms %= 60000
    secs = total_ms // 1000
    millis = total_ms % 1000
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def parse_srt(srt_text: str) -> list[SubtitleBlock]:
    blocks: list[SubtitleBlock] = []
    raw_blocks = re.split(r"\n\s*\n", srt_text.strip())
    for raw in raw_blocks:
        lines = [line.strip() for line in raw.splitlines() if line.strip()]
        if len(lines) < 2:
            continue
        try:
            index = int(lines[0])
            time_line_idx = 1
        except ValueError:
            index = len(blocks) + 1
            time_line_idx = 0

        if time_line_idx >= len(lines):
            continue

        time_match = re.match(
            r"(\d{2}:\d{2}:\d{2}[,. ]\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2}[,. ]\d{3})",
            lines[time_line_idx],
        )
        if not time_match:
            continue

        start = time_match.group(1).replace(".", ",").replace(" ", "")
        end = time_match.group(2).replace(".", ",").replace(" ", "")
        text = " ".join(lines[time_line_idx + 1:])
        text = re.sub(r"\s+", " ", text).strip()
        if text:
            blocks.append(SubtitleBlock(index=index, start=start, end=end, text=text))
    return blocks


def wrap_subtitle_text(text: str, max_chars_per_line: int = 42, max_lines: int = 2) -> str:
    words = text.split()
    if not words:
        return ""
    lines: list[str] = []
    current_line = words[0]
    for word in words[1:]:
        if len(current_line) + 1 + len(word) <= max_chars_per_line:
            current_line += f" {word}"
        else:
            lines.append(current_line)
            current_line = word
    lines.append(current_line)

    if len(lines) > max_lines:
        merged = " ".join(lines)
        mid = len(merged) // 2
        split_idx = merged.rfind(" ", 0, mid + 10)
        if split_idx == -1:
            split_idx = merged.find(" ", mid)
        if split_idx != -1:
            return f"{merged[:split_idx].strip()}\n{merged[split_idx+1:].strip()}"
    return "\n".join(lines[:max_lines])


def write_srt(blocks: list[SubtitleBlock]) -> str:
    output_lines: list[str] = []
    for i, block in enumerate(blocks, start=1):
        output_lines.append(str(i))
        output_lines.append(f"{block.start} --> {block.end}")
        output_lines.append(wrap_subtitle_text(block.text))
        output_lines.append("")
    return "\n".join(output_lines)
