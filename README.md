<h1 align="center">Vietnamese AI Video Dubber</h1>

<p align="center">Fully local, fully free Vietnamese video dubbing — Whisper transcription, AI translation, and Edge-TTS / VieNeu-TTS voice-over. No API keys, no cloud, $0.</p>

<p align="center">
English | <a href="README_vi.md">Tiếng Việt</a>
</p>

https://github.com/user-attachments/assets/81dc4e20-f8ca-4456-8f00-f3903fb61a25


Everything runs on your own machine (offline mode available with all-local models). Automatic subtitle translation and Vietnamese voice-over for foreign-language videos (mostly English).

```text
video -> audio -> original subtitles (Whisper) -> translate to Vietnamese -> voice-over (Edge-TTS / VieNeu-TTS) -> MP4 with Vietnamese subtitles
```

### Performance

Tested on the machine below (VieNeu-TTS voice-over), full pipeline: transcription, translation, voice-over, and MP4 muxing.

| Video | Processing time | Ratio | Speed vs. playback |
|---|---|---|---|
| 2 min 45 s | 2 min 19 s | 0.84× realtime | ~16 % faster than live |
| 1 min 00 s | 1 min 12 s | 1.20× realtime | ~20 % slower than live |
| 3 min 18 s | 4 min 16 s | 1.29× realtime | ~29 % slower than live |
| 41 min 10 s | 61 min 12 s | 1.49× realtime | ~49 % slower than live |

Ratio climbs with video length on this GPU — a 4 GB card starts trading VRAM headroom for throughput on longer runs. Short clips can even beat realtime.

**Test machine setup:**

| Component | Spec |
|---|---|
| GPU | NVIDIA GeForce RTX 3050 Laptop GPU (4 GB VRAM) |
| CPU | Intel Core i5-11400H (12 threads) |
| RAM | 16 GB |
| CUDA / driver | CUDA 12.6, driver 610.43.02 |
| PyTorch | 2.14.0+cu126 |
| Whisper device | `cuda` |
| Translation device | `cuda` |
| TTS engine | VieNeu-TTS (offline) |

Raw numbers (and every future dub job) are logged automatically to `jobs/stats.json` — a JSON array with one entry per finished dub, with video duration, processing time, and GPU config (`GET /api/stats` reads it back).

Cost: **$0** — no paid APIs or cloud services required.

## Features

- **Speech-to-Text**: Faster-Whisper transcription, runs offline for free.
- **Translation**: 3 options — Google Translate (free), HuggingFace Hy-MT2-1.8B (direct, 4-bit quantized for low VRAM), or EnViT5 offline (Transformers).
- **AI Voice-over (TTS)**: Edge-TTS (online, Microsoft Neural) or VieNeu-TTS (offline, 23 Vietnamese voices).
- **Video processing**: Automatic timeline alignment (atempo), burn subtitles or mux soft subs with FFmpeg.
- **No paid APIs, no heavy Supertonic ONNX.**

## Requirements

| Component | Required | Notes |
|---|---|---|
| Python | ✔ | ≥ 3.10, < 3.14 |
| [uv](https://docs.astral.sh/uv/) | ✔ | Package + virtualenv management |
| [ffmpeg](https://ffmpeg.org/) | ✔ | Video/audio processing |
| NVIDIA GPU (CUDA) | ✖ | Recommended — speeds up Whisper & EnViT5; CPU works but slower |
| Internet | Setup only | Needed for install and first-time model download; Google Translate needs a connection every time |

Platform install:

```bash
# Ubuntu/Debian
sudo apt update && sudo apt install -y ffmpeg git
curl -LsSf https://astral.sh/uv/install.sh | sh

# macOS (Homebrew)
brew install ffmpeg git
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows: get ffmpeg at https://ffmpeg.org/download.html
# then uv:  powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
```

## Install & run

```bash
git clone https://github.com/ledangquangdangquang/ViVidDubber
cd ViVidDubber
uv sync --frozen               # installs all dependencies (incl. VieNeu-TTS)
uv run python app.py           # start server
```

> Note: `uv sync --frozen` uses the pre-resolved lock file, avoiding `vieneu` resolution errors on some machines.

Open **http://127.0.0.1:8787** in your browser.

Upload a video, pick your options (translation provider, voice-over, burn subtitles) and run. Results land in `jobs/<job-id>/`.

## Where do downloaded models go?

Whisper, HuggingFace Hy-MT2-1.8B, EnViT5, and VieNeu-TTS all download automatically on first use via Hugging Face Hub, into the standard shared cache:

- Linux/macOS: `~/.cache/huggingface/hub/`
- Windows: `%USERPROFILE%\.cache\huggingface\hub\`

Each model gets its own `models--<org>--<name>/` folder there, e.g. `models--Systran--faster-whisper-small`, `models--VietAI--envit5-translation`, `models--tencent--Hy-MT2-1.8B`, `models--pnnbao-ump--VieNeu-TTS-v3-Turbo`. Nothing downloads until you pick that engine/provider in the UI and run a job. Override the location (all models at once) with the `HF_HOME` env var before running `uv run python app.py`.

## Translation models — which one?

Pick "Translation provider" in the web UI before creating a job:

| | Google Translate | HuggingFace Hy-MT2-1.8B | EnViT5 |
|---|---|---|---|
| **API key** | None | None | None |
| **Internet while running** | Yes | No | No |
| **Setup** | None | Automatic (first-run download) | Automatic (first-run download) |
| **Download size** | 0 | ~3.5 GB | ~2.1 GB |
| **Translation quality** | Good | Best (1.8B LLM) | OK (T5 base) |
| **Speed** | Fast (online) | Slow (large LLM) | Fast (T5, GPU) |
| **Best for** | Always-online machines | Offline, highest quality | Offline, speed matters |

### 1. Google Translate (default)

No setup — just internet. The fastest way to get started.

### 2. HuggingFace Hy-MT2-1.8B — direct

Runs `tencent/Hy-MT2-1.8B` directly with Transformers. By default it loads **4-bit quantized** (bitsandbytes), cutting VRAM from ~3.4 GB to ~1.2 GB with no noticeable quality loss. Downloads the model automatically (~3.5 GB) on first use, then runs fully offline. Previously this model required installing a separate Ollama server; that dependency is removed now — just pick "HuggingFace Hy-MT2-1.8B" in the UI. The model downloads on first run:

```bash
# Just pick "HuggingFace Hy-MT2-1.8B" in the UI; the model downloads on first run
```

Environment variables (optional):

| Variable | Default | Description |
|---|---|---|
| `HF_TRANSLATE_REPO` | `tencent/Hy-MT2-1.8B` | HuggingFace model repo |
| `HF_TRANSLATE_BATCH_SIZE` | `20` | Lines translated per call |
| `HF_TRANSLATE_DEVICE` | `auto` | `cpu` or `cuda` (falls back to GPU if available) |
| `HF_TRANSLATE_QUANT` | `4bit` | `4bit` (bitsandbytes, low VRAM) or `none` (FP16) |

> Note: a CUDA GPU makes loading/warming faster; CPU works but is slower (1.8B is a small LLM, fits 4 GB VRAM).

### 3. EnViT5 — offline Transformers

Fully offline with `VietAI/envit5-translation`. Downloads the model automatically (~2.1 GB) on first use — runs on GPU if CUDA is available, falls back to CPU. Nothing extra to install:

```bash
# Just pick "EnViT5 (offline GPU)" in the UI; the model downloads on first run
```

Environment variables (optional):

| Variable | Default | Description |
|---|---|---|
| `ENVIT5_MODEL` | `VietAI/envit5-translation` | HuggingFace model name |
| `ENVIT5_BATCH_SIZE` | `20` | Lines translated per call |

> GPU note: if `uv run python app.py` reports a triton CUDA compile error, set `CC=/usr/bin/gcc` before running. The code sets this fallback automatically when using EnViT5.

## Whisper config (speech recognition)

Defaults to CPU + int8 (no GPU needed). For GPU:

```bash
WHISPER_DEVICE=cuda WHISPER_COMPUTE_TYPE=float16 uv run python app.py
```

| Variable | Default | Description |
|---|---|---|
| `WHISPER_DEVICE` | `cpu` | `cpu` or `cuda` |
| `WHISPER_COMPUTE_TYPE` | `int8` | `int8`/`float16`/`float32` |
| `WHISPER_BEAM_SIZE` | `1` | Beam search — higher = more accurate, slower |

Default Whisper model is `small` (selectable in the UI). First run downloads it from HuggingFace.

## TTS config (voice-over)

Pick "Engine lồng tiếng" (voice-over engine) in the web UI before creating a job:

| | Edge-TTS | VieNeu-TTS |
|---|---|---|
| **Status** | Online (Microsoft) | **Offline** |
| **Voices** | 2 (Hoai My, Nam Minh) | **23** (North/Central/South dialects) |
| **Audio** | 44.1 kHz | **48 kHz** |
| **Voice cloning** | ❌ | ✅ (3–8s clip) |
| **Emotion cues** | ❌ | ✅ `[cười]` `[thở dài]` `[hắng giọng]` |
| **Setup** | None | Automatic via `uv sync` |
| **Model size** | 0 | ~900 MB (first-run download) |
| **Best for** | Always-online machines | Offline, many voices, voice cloning |

### 1. Edge-TTS (default)

Free Microsoft Edge-TTS, needs internet. Default voice: `vi-VN-HoaiMyNeural` (female) — changeable in the UI; `vi-VN-NamMinhNeural` (male) is available too.

### 2. VieNeu-TTS (offline)

Fully offline with VieNeu-TTS v3 Turbo (48 kHz, 23 voices). Downloads the model automatically (~900 MB) on first use.

```bash
# Just pick "VieNeu-TTS (offline)" in the UI; the model downloads on first run
```

Environment variables (optional):

| Variable | Default | Description |
|---|---|---|
| (none) | — | the `vieneu` package autoloads its model from HuggingFace |

> Note: the model downloads from HuggingFace on first run (~900 MB). After that it runs fully offline.

> Note: voice cloning (`ref_audio`) increases processing time vs. preset voices — avoid it for long videos.

## API (integration)

- `POST /api/jobs` — create a job (multipart `file` + form options, or `video_url` a single YouTube video)
- `POST /api/resolve` — expand a YouTube link into per-video URLs (playlist → each video)
- `GET /api/queue` — list jobs
- `GET /api/jobs/{id}` — job status
- `DELETE /api/jobs/{id}` — delete a job (running job → 409)
- `GET /api/jobs/{id}/download/{kind}` — download a result
- `GET /api/config` — config & translation provider list

## FAQ

**Lines stay in English (not translated)?**
Each failed line shows up as a "Cảnh báo" (warning) in the job result. Common cause: Google rate-limit (slow network). Failed lines are retried individually; if they still fail, the original English is kept instead of a wrong translation.

**Want a better translation model?**
Switch `HF_TRANSLATE_REPO` to a larger Hy-MT2 (e.g. `tencent/Hy-MT2-7B`) — slower but higher quality.

**File too large?**
Limit is 2 GB per upload, max 50 jobs, and result files are auto-deleted after 6 hours.
