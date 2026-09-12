from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess


class MediaToolError(RuntimeError):
    pass


def resolve_video_urls(url: str) -> list[tuple[str, str]]:
    """Expand a YouTube link into a list of (url, title) for each video (single video → [(url, title)])."""
    import yt_dlp

    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": True,
        "force_generic_extractor": False,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
    if info.get("_type") == "playlist":
        items = []
        for entry in info.get("entries") or []:
            if entry and entry.get("url"):
                items.append((entry["url"], entry.get("title") or "Untitled"))
        if not items:
            items = [(url, info.get("title") or "Untitled")]
        return items
    return [(url, info.get("title") or "Untitled")]


def download_video(url: str, job_dir: Path, preferred_height: int = 720) -> tuple[Path, str]:
    """Download a single YouTube video via yt-dlp. Returns (input_path, title)."""
    import yt_dlp

    ydl_opts = {
        "outtmpl": str(job_dir / "input.%(ext)s"),
        "format": f"bv*[height<={preferred_height}]+ba/b[height<={preferred_height}]/bv*+ba/b",
        "merge_output_format": "mp4",
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        title = (info.get("entries") or [info])[0].get("title") or "video"
    files = sorted(job_dir.glob("input.*"))
    if not files:
        raise MediaToolError(f"No video downloaded from {url}")
    return files[0], title


def require_tool(tool_name: str) -> None:
    if shutil.which(tool_name) is None:
        raise MediaToolError(f"Required binary '{tool_name}' was not found in PATH.")


def run_command(cmd: list[str], timeout: int | None = None) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if result.returncode != 0:
        raise MediaToolError(
            f"Command failed with exit code {result.returncode}:\n"
            f"Command: {' '.join(cmd)}\n"
            f"Stderr: {result.stderr.strip()}"
        )
    return result


def probe_media(video_path: Path) -> dict:
    require_tool("ffprobe")
    cmd = [
        "ffprobe",
        "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        "-show_streams",
        str(video_path),
    ]
    result = run_command(cmd)
    return json.loads(result.stdout)


def extract_audio(video_path: Path, output_audio_path: Path, sample_rate: int = 16000) -> Path:
    require_tool("ffmpeg")
    output_audio_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg",
        "-y",
        "-i", str(video_path),
        "-vn",
        "-ac", "1",
        "-ar", str(sample_rate),
        "-c:a", "pcm_s16le",
        str(output_audio_path),
    ]
    run_command(cmd)
    return output_audio_path


def mux_soft_subtitles(video_path: Path, srt_path: Path, output_path: Path) -> Path:
    require_tool("ffmpeg")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg",
        "-y",
        "-i", str(video_path),
        "-i", str(srt_path),
        "-c", "copy",
        "-c:s", "mov_text",
        "-metadata:s:s:0", "language=vie",
        "-metadata:s:s:0", "title=Tiếng Việt",
        str(output_path),
    ]
    run_command(cmd)
    return output_path


def burn_subtitles(video_path: Path, srt_path: Path, output_path: Path, font_size: int = 22) -> Path:
    require_tool("ffmpeg")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    font_size = max(8, min(72, font_size))
    escaped_srt = str(srt_path).replace("\\", "/").replace(":", "\\:").replace("'", "\\'")
    cmd = [
        "ffmpeg",
        "-y",
        "-i", str(video_path),
        "-vf", f"subtitles='{escaped_srt}':force_style='FontSize={font_size},Outline=1,Shadow=0,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000'",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
        "-c:a", "copy",
        str(output_path),
    ]
    run_command(cmd, timeout=600)
    return output_path
