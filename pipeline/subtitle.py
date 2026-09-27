from __future__ import annotations

from dataclasses import dataclass, replace
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


def split_for_display(blocks: list[SubtitleBlock], max_chars: int = 80, min_sec: float = 1.2) -> list[SubtitleBlock]:
    """Split long (already translated) blocks into evenly sized pieces, timing proportional to text length."""
    out: list[SubtitleBlock] = []
    for block in blocks:
        words = block.text.split()
        n = -(-len(block.text) // max_chars)  # ceil
        if n <= 1:
            out.append(replace(block, index=len(out) + 1))
            continue
        target = len(block.text) / n
        pieces: list[str] = []
        current = ""
        for word in words:
            if current and len(pieces) < n - 1 and len(current) + 1 + len(word) / 2 > target:
                pieces.append(current)
                current = word
            else:
                current = f"{current} {word}".strip()
        pieces.append(current)
        start, end = srt_time_to_seconds(block.start), srt_time_to_seconds(block.end)
        total = sum(len(p) for p in pieces)
        t = start
        for piece in pieces:
            t_next = t + (end - start) * len(piece) / total
            out.append(SubtitleBlock(len(out) + 1, seconds_to_srt_time(t), seconds_to_srt_time(t_next), piece))
            t = t_next
    # Let short blocks linger into the following silence so they stay readable.
    for cur, nxt in zip(out, out[1:] + [None]):
        start, end = srt_time_to_seconds(cur.start), srt_time_to_seconds(cur.end)
        if end - start < min_sec:
            limit = srt_time_to_seconds(nxt.start) if nxt else start + min_sec
            cur.end = seconds_to_srt_time(max(end, min(start + min_sec, limit)))
    return out


def write_srt(blocks: list[SubtitleBlock]) -> str:
    output_lines: list[str] = []
    for i, block in enumerate(blocks, start=1):
        output_lines.append(str(i))
        output_lines.append(f"{block.start} --> {block.end}")
        output_lines.append(wrap_subtitle_text(block.text))
        output_lines.append("")
    return "\n".join(output_lines)
