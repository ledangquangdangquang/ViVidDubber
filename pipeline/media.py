from __future__ import annotations

from functools import lru_cache
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import threading
import urllib.parse
import urllib.request


class MediaToolError(RuntimeError):
    pass


def _channel(info: dict) -> str:
    return info.get("channel") or info.get("uploader") or ""


def _ydl_common_opts() -> dict:
    """Without a JS runtime yt-dlp can't solve YouTube's challenges and falls back to clients that get
    "Sign in to confirm you're not a bot"; the solver script ships in yt-dlp-ejs, deno or node runs it.
    Cookies (YTDLP_COOKIES=cookies.txt, YTDLP_COOKIES_FROM_BROWSER=firefox|chrome|...) are the extra lever."""
    opts = {"js_runtimes": {"deno": {}, "node": {}}}
    if browser := os.environ.get("YTDLP_COOKIES_FROM_BROWSER"):
        opts["cookiesfrombrowser"] = (browser,)
    if path := os.environ.get("YTDLP_COOKIES"):
        opts["cookiefile"] = path
    return opts


YT_ID_RE = re.compile(r"(?:[?&]v=|/shorts/|/live/|youtu\.be/)([\w-]{11})")


def resolve_video_urls(url: str) -> list[tuple[str, str, str]]:
    """Expand a YouTube link into (url, title, channel) per video (single video → one item)."""
    if YT_ID_RE.search(url) and "list=" not in url:
        # oEmbed: title + channel without a full yt-dlp extraction, which hits the bot check when the IP is throttled.
        query = urllib.parse.urlencode({"url": url, "format": "json"})
        with urllib.request.urlopen(f"https://www.youtube.com/oembed?{query}", timeout=15) as resp:
            data = json.load(resp)
        return [(url, data.get("title") or "Untitled", data.get("author_name") or "")]
    import yt_dlp

    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": True,
        "force_generic_extractor": False,
        **_ydl_common_opts(),
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
    if info.get("_type") == "playlist":
        items = []

        def walk(playlist: dict) -> None:
            for entry in playlist.get("entries") or []:
                if not entry:
                    continue
                if entry.get("_type") == "playlist":  # a bare channel link nests its tabs (Videos, Live, Shorts)
                    walk(entry)
                elif entry.get("url"):
                    items.append((entry["url"], entry.get("title") or "Untitled", _channel(entry) or _channel(info)))

        walk(info)
        if not items:
            items = [(url, info.get("title") or "Untitled", _channel(info))]
        return items
    return [(url, info.get("title") or "Untitled", _channel(info))]


def download_video(url: str, job_dir: Path, preferred_height: int = 720) -> tuple[Path, str, str]:
    """Download a single YouTube video via yt-dlp. Returns (input_path, title, channel)."""
    import yt_dlp

    ydl_opts = {
        "outtmpl": str(job_dir / "input.%(ext)s"),
        # Prefer H.264: soft-sub outputs stream-copy the video, and many players show AV1/VP9 as black.
        "format": (
            f"bv*[height<={preferred_height}][vcodec^=avc1]+ba[ext=m4a]/"
            f"bv*[height<={preferred_height}]+ba/b[height<={preferred_height}]/bv*+ba/b"
        ),
        "merge_output_format": "mp4",
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        # A pause before each download: a back-to-back channel batch is what trips the bot check.
        "sleep_interval": 5,
        "max_sleep_interval": 15,
        **_ydl_common_opts(),
    }
    for attempt in range(3):
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
            break
        except yt_dlp.utils.DownloadError as exc:
            # YouTube now and then answers 403 for a stream URL; a fresh extraction gets a working one.
            if "403" not in str(exc) or attempt == 2:
                raise
    video = (info.get("entries") or [info])[0]
    title = video.get("title") or "video"
    files = sorted(job_dir.glob("input.*"))
    if not files:
        raise MediaToolError(f"No video downloaded from {url}")
    return files[0], title, _channel(video)


def require_tool(tool_name: str) -> None:
    if shutil.which(tool_name) is None:
        raise MediaToolError(f"Required binary '{tool_name}' was not found in PATH.")


def run_command(cmd: list[str], timeout: int | None = 1800, env: dict | None = None) -> subprocess.CompletedProcess[str]:
    # stdin=DEVNULL: an inherited terminal stdin lets ffmpeg get stopped by SIGTTIN mid-run (silent hang);
    # the default timeout turns any other hang into a job error instead of a job stuck forever.
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, stdin=subprocess.DEVNULL, env=env)
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


def extract_audio(video_path: Path, output_audio_path: Path, sample_rate: int = 16000, channels: int = 1) -> Path:
    require_tool("ffmpeg")
    output_audio_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg",
        "-y",
        "-i", str(video_path),
        "-vn",
        "-ac", str(channels),
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


_NVENC_ARGS = ["-c:v", "h264_nvenc", "-preset", "p4", "-rc", "vbr", "-cq", "27", "-b:v", "0"]
_X264_ARGS = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "18"]
_NVIDIA_LIBS = ("libcuda.so.1", "libnvidia-encode.so.1", "libnvcuvid.so.1")
_DRIVER_DIRS = ("/run/opengl-driver/lib", "/usr/lib/x86_64-linux-gnu", "/lib/x86_64-linux-gnu", "/usr/lib64")


def _driver_lib_env() -> dict | None:
    """Env that lets a Nix-built ffmpeg see the host NVIDIA driver. Adding the whole system lib dir to
    LD_LIBRARY_PATH clashes with Nix's glibc, so only the three driver libs get symlinked into a shim dir."""
    lib_dir = next((d for d in _DRIVER_DIRS if all(Path(d, n).exists() for n in _NVIDIA_LIBS)), None)
    if lib_dir is None:
        return None
    shim = Path(tempfile.gettempdir()) / "vivid-nvenc-libs"
    try:
        shim.mkdir(exist_ok=True)
        for name in _NVIDIA_LIBS:
            link = shim / name
            link.unlink(missing_ok=True)
            link.symlink_to(Path(lib_dir, name))
    except OSError:
        return None
    return {**os.environ, "LD_LIBRARY_PATH": os.pathsep.join(filter(None, [str(shim), os.environ.get("LD_LIBRARY_PATH")]))}


@lru_cache(maxsize=1)
def _video_encoder() -> tuple[list[str], dict | None]:
    """(codec args, env) for burn-in: NVENC when a test encode actually opens it (~2x faster than x264
    on an RTX 3050, CPU stays free for TTS), else libx264. Override with BURN_ENCODER=libx264."""
    if shutil.which("ffmpeg") and os.environ.get("BURN_ENCODER", "nvenc") == "nvenc":
        probe = ["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=s=256x256:d=0.1", *_NVENC_ARGS, "-f", "null", "-"]
        for env in (None, _driver_lib_env()):
            try:
                if subprocess.run(probe, env=env, capture_output=True, timeout=30, stdin=subprocess.DEVNULL).returncode == 0:
                    return _NVENC_ARGS, env
            except (OSError, subprocess.TimeoutExpired):
                pass
    return _X264_ARGS, None


def _filter_path(path: Path) -> str:
    """A file path quoted for an ffmpeg filter option (Windows backslashes, ':' and "'" escaped)."""
    return "'" + str(path).replace("\\", "/").replace(":", "\\:").replace("'", "\\'") + "'"


def burn_subtitles(video_path: Path, srt_path: Path | None, output_path: Path, font_size: int = 22, keep_audio: bool = True, flip: bool = False,
                   cover: float = 0.0, credit: str = "") -> Path:
    """Burn subtitles / flip / blur / credit into the picture. `srt_path=None` skips the subtitles
    filter so a flip-only or credit-only job needs no SRT and no transcription."""
    require_tool("ffmpeg")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    font_size = max(8, min(72, font_size))
    credit_file = output_path.parent / "source_credit.txt"
    if credit:
        # Read from a file with expansion off: channel names carry ':', quotes and '%' that drawtext would parse.
        credit_file.write_text(credit, encoding="utf-8")
    codec_args, env = _video_encoder()
    # Write to a unique temp name: a resumed job may burn the same output while a background burn is still running.
    part = output_path.with_name(f"{output_path.stem}.{os.getpid()}-{threading.get_ident()}.part{output_path.suffix}")
    # hflip first so the subs stay readable; `cover` blurs the bottom band (the source's own hardsubs) under ours.
    vf = ("hflip," if flip else "")
    if cover > 0:
        vf += f"split[v][b];[b]crop=iw:ih*{cover:.2f}:0:ih*{1 - cover:.2f},gblur=sigma=40[bl];[v][bl]overlay=0:H-h,"
    if srt_path is not None:
        vf += f"subtitles={_filter_path(srt_path)}:force_style='FontSize={font_size},Outline=1,Shadow=0,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000',"
    if credit:
        vf += (f"drawtext=textfile={_filter_path(credit_file)}:expansion=none:font=Sans:fontsize=h*0.035:fontcolor=white"
               ":borderw=2:bordercolor=black:x=w*0.025:y=h*0.035")
    vf = vf.strip(",")
    cmd = [
        "ffmpeg",
        "-y",
        "-i", str(video_path),
        *([ "-vf", vf] if vf else []),
        *codec_args,
        *(["-c:a", "copy"] if keep_audio else ["-an"]),
        str(part),
    ]
    try:
        run_command(cmd, timeout=7200, env=env)
        part.replace(output_path)
    finally:
        part.unlink(missing_ok=True)
    return output_path


def trim_video(video_path: Path, output_path: Path, start: str = "", end: str = "") -> Path:
    """Cut [start, end] out of `video_path` (ffmpeg time syntax, e.g. "90" or "1:30"; empty = from start / to end).
    Re-encodes so the cut is frame-exact: a stream copy would start at the previous keyframe."""
    require_tool("ffmpeg")
    codec_args, env = _video_encoder()
    run_command([
        "ffmpeg", "-y",
        *(["-ss", start] if start else []), *(["-to", end] if end else []),
        "-i", str(video_path), *codec_args, "-c:a", "aac", "-b:a", "192k", str(output_path),
    ], timeout=7200, env=env)
    return output_path


def replace_audio(video_path: Path, audio_source: Path, output_path: Path) -> Path:
    """Video stream of `video_path` + audio (and soft subs) of `audio_source`, all stream-copied."""
    require_tool("ffmpeg")
    run_command([
        "ffmpeg", "-y", "-i", str(video_path), "-i", str(audio_source),
        "-map", "0:v:0", "-map", "1:a?", "-map", "1:s?", "-c", "copy", str(output_path),  # no -shortest: see tts.py
    ])
    return output_path
