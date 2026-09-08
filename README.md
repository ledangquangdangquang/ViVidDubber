# Vietnamese AI Video Dubber

Automatic subtitle translation and Vietnamese voice-over for foreign-language videos (mostly English).

```text
video -> audio -> original subtitles (Whisper) -> translate to Vietnamese -> voice-over (Edge-TTS / VieNeu-TTS) -> MP4 with Vietnamese subtitles
```

> Tiếng Việt: xem [README_vi.md](README_vi.md)

## Features

- **Speech-to-Text**: Faster-Whisper transcription, runs offline for free.
- **Translation**: 4 options — Google Translate (free), Ollama local LLM, HuggingFace Hy-MT2-1.8B (direct, no Ollama), or EnViT5 offline (Transformers).
- **AI Voice-over (TTS)**: Edge-TTS (online, Microsoft Neural) or VieNeu-TTS (offline, 23 Vietnamese voices).
- **Video processing**: Automatic timeline alignment (atempo), burn subtitles or mux soft subs with FFmpeg.
- **No paid APIs, no heavy Supertonic ONNX.**

## Requirements

| Component | Required | Notes |
|---|---|---|
| Python | ✔ | ≥ 3.10 |
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
git clone <repo-url> vi-video-dubber
cd vi-video-dubber
uv sync --frozen               # installs all dependencies (incl. VieNeu-TTS)
uv run python app.py           # start server
```

> Note: `uv sync --frozen` uses the pre-resolved lock file, avoiding `vieneu` resolution errors on some machines.

Open **http://127.0.0.1:8787** in your browser.

Upload a video, pick your options (translation provider, voice-over, burn subtitles) and run. Results land in `jobs/<job-id>/`.

## Translation models — which one?

Pick "Translation provider" in the web UI before creating a job:

| | Google Translate | Ollama (Hy-MT2-1.8B) | HuggingFace Hy-MT2-1.8B | EnViT5 |
|---|---|---|---|---|
| **API key** | None | None | None | None |
| **Internet while running** | Yes | No | No | No |
| **Setup** | None | Install Ollama + pull model | Automatic (first-run download) | Automatic (first-run download) |
| **Download size** | 0 | ~1.1 GB (via Ollama) | ~3.5 GB | ~2.1 GB |
| **Translation quality** | Good | Best (1.8B LLM) | Best (1.8B LLM) | OK (T5 base) |
| **Speed** | Fast (online) | Slowest (large LLM) | Slow (large LLM) | Fast (T5, GPU) |
| **Best for** | Always-online machines | Offline, highest quality | Offline, no Ollama install | Offline, speed matters |

### 1. Google Translate (default)

No setup — just internet. The fastest way to get started.

### 2. Ollama — local LLM

```bash
# 1. Install Ollama: https://ollama.com/download
# 2. Start and pull the English-Vietnamese translation model:
ollama serve &                        # or run the Ollama app
ollama pull hf.co/tencent/Hy-MT2-1.8B-GGUF:Q4_K_M
# 3. Restart the app, pick "Ollama local" in the UI
```

Environment variables (optional):

| Variable | Default | Description |
|---|---|---|
| `OLLAMA_MODEL` | `hf.co/tencent/Hy-MT2-1.8B-GGUF:Q4_K_M` | Model used for translation |
| `OLLAMA_BASE_URL` | `http://127.0.0.1:11434` | Ollama server address |
| `OLLAMA_TRANSLATE_BATCH_SIZE` | `20` | Lines translated per call |

### 3. HuggingFace Hy-MT2-1.8B — direct, no Ollama

Runs `tencent/Hy-MT2-1.8B` directly with Transformers (no Ollama server). Downloads the model automatically (~3.5 GB) on first use, then runs fully offline:

```bash
# Just pick "HuggingFace Hy-MT2-1.8B" in the UI; the model downloads on first run
```

Environment variables (optional):

| Variable | Default | Description |
|---|---|---|
| `HF_TRANSLATE_REPO` | `tencent/Hy-MT2-1.8B` | HuggingFace model repo |
| `HF_TRANSLATE_BATCH_SIZE` | `20` | Lines translated per call |
| `HF_TRANSLATE_DEVICE` | `auto` | `cpu` or `cuda` (falls back to GPU if available) |

> Note: a CUDA GPU makes loading/warming faster; CPU works but is slower (1.8B is a small LLM, fits 4 GB VRAM).

### 4. EnViT5 — offline Transformers

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

## API (integration)

- `POST /api/jobs` — create a job (multipart: `file` + form options)
- `GET /api/queue` — list jobs
- `GET /api/jobs/{id}` — job status
- `DELETE /api/jobs/{id}` — delete a job (running job → 409)
- `GET /api/jobs/{id}/download/{kind}` — download a result
- `GET /api/config` — config & Ollama reachability check

## FAQ

**Lines stay in English (not translated)?**
Each failed line shows up as a "Cảnh báo" (warning) in the job result. Common causes: Google rate-limit (slow network) or Ollama running out of context. Failed lines are retried individually; if they still fail, the original English is kept instead of a wrong translation.

**Want a better translation model?**
Switch `OLLAMA_MODEL` to a larger quant (e.g. Q6_K or full precision) — slower but higher quality.

**File too large?**
Limit is 2 GB per upload, max 50 jobs, and result files are auto-deleted after 6 hours.