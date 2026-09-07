# Agent Guide

Fork/extension of Supertone's Supertonic TTS repo. Local product: a Vietnamese video dubber — **input: foreign-language video (mostly English), output: Vietnamese-narrated video with Vietnamese subtitles**.

```text
video -> audio.wav -> original.srt -> vi.srt -> Edge-TTS voice-over -> burned/muxed MP4
```

Work in the local tooling (`vi-video-dubber/`, `tool/`) and leave the upstream example SDKs (`py/`, `nodejs/`, …) alone unless the user asks.

## Primary product: `vi-video-dubber/`

Self-contained `uv` project. Run:

```bash
cd vi-video-dubber && uv run python app.py     # UI: http://127.0.0.1:8787
```

- FastAPI app (`app.py`) serves `web.html` and the job queue API. Single daemon worker thread, one job at a time. Guard the worker with `_WORKER_STARTED` so tests (which share one process) don't double-start it.
- Pipeline modules in `pipeline/`: `media.py` (ffmpeg/ffprobe), `transcribe.py` (faster-whisper), `translate.py` (Google, Ollama, or EnViT5), `tts.py` (Edge-TTS dubbing, VieNeu-TTS offline), `subtitle.py` (SRT parse/write).
- **By design: no paid APIs, no Supertonic ONNX.** Dependencies are free: faster-whisper, edge-tts, veneu, transformers<5, deep-translator, Google's free `translate_a/single` endpoint.
- Job flow in `_run_job` (`app.py:349`): probe → extract 16 kHz mono WAV → transcribe → translate → mux soft subs (always) → dub (if `dub=true`) → burn (if `export_mode=burn`, burned from the dubbed video when dubbing is on).

### Providers & env vars

- **Whisper**: model `small` default (`whisper_model` form field); device/compute via `WHISPER_DEVICE` (default `cpu`), `WHISPER_COMPUTE_TYPE` (`int8`). Auto-falls back to cpu/int8 on CUDA errors. Model downloads from HF on first run.
- **Translate** (`translation_provider`): `google` (default, no key — free gtx endpoint, 20-line chunks joined with newlines, 3 retries + backoff, per-line rescue, untranslated lines are kept as original English and surfaced in job `translation_warnings`), `ollama` (default model `hf.co/tencent/Hy-MT2-7B-GGUF:Q4_K_M`, base `http://127.0.0.1:11434`; env `OLLAMA_MODEL`, `OLLAMA_BASE_URL`, `OLLAMA_TRANSLATE_BATCH_SIZE`), or `envit5` (offline Transformers: `VietAI/envit5-translation`, GPU if CUDA else CPU, lazy-loads a shared singleton pipeline; env `ENVIT5_MODEL`, `ENVIT5_BATCH_SIZE`). Google path needs internet. Ollama/EnViT5 are local. EnViT5 needs `transformers<5` (v5 removed the `translation` pipeline and broke the EnViT5 tokenizer) — pinned in `pyproject.toml`. On machines where the default `gcc` lacks the multiarch Python include dir, triton's JIT compile fails → `_lazy_load` sets `CC=/usr/bin/gcc` fallback.
- **TTS voice**: Edge-TTS (online, default) or VieNeu-TTS (offline). `tts_provider` form field selects engine; `tts_voice` selects voice. Edge-TTS default `vi-VN-HoaiMyNeural` (non-`vi-VN-*` voice with `F` in name → HoaiMy, else `vi-VN-NamMinhNeural`). VieNeu-TTS has 23 preset voices (Bắc/Trung/Nam), voice cloning, emotion cues (`[cười]`, `[thở dài]`, `[hắng giọng]`), 48 kHz, runs via ONNX Runtime (torch-free). (`tts.py:89`, `tts.py:156`)
- Dubbing alignment: clip >2× the subtitle slot is re-synthesized at 1.25× speed; clips still longer than the slot are time-stretched with chained `atempo`; output replaces original audio unless `background_volume > 0`.

### API & job artifacts

- `POST /api/jobs` (multipart `file` + form options), `GET /api/queue`, `GET /api/jobs/{id}`, `DELETE /api/jobs/{id}` (running job → 409), `GET /api/jobs/{id}/download/{kind}`, `GET /api/config` (Ollama reachability).
- Limits: 2 GB upload, 50 jobs, finished jobs auto-deleted after 6 h TTL.
- Per-job dir `vi-video-dubber/jobs/<id>/`: `input*`, `audio.wav`, `original.srt`, `vi.srt`, `<stem>_vi_soft.mp4`, `<stem>_vi_dub.mp4`, `<stem>_vi_burned.mp4`. Download filenames are renamed to `<original_stem>_…`.

### Subtitle handling rules

- Preserve SRT indexes and timestamps; translate text only. `write_srt` re-numbers blocks and wraps at 42 chars / 2 lines.
- Burn-in uses the `subtitles` filter (`FontSize=22`); escape the SRT path for the filter (`media.py:81`). Windows path escaping matters.
- Slow/risky TTS text is stripped of `<…>`, `[…]`, `(…)` before synthesis; empty text becomes 0.5 s silence.

## Legacy stack: `tool/`

Two older tools, still present and documented in `README.md` + `tool/WEBSOCKET_API.md`:

- `tool/ws_tts_server.py` — WebSocket TTS server on `ws://127.0.0.1:8765`, UI `tool/tts_web.html` (uses Supertonic ONNX in `assets/`).
- `tool/video_pipeline_server.py` — earlier localizer UI `tool/video_localizer_web.html` (Cerebras via `CEREBRAS_API_KEY` or Ollama + Supertonic TTS dubbing). Docker support: `docker compose up --build -d`.

Tests for the old stack live in `tool/test_pipeline.py` (pytest); **pytest is not installed in either venv by default** — install it into `py/.venv` before running. `vi-video-dubber/` has no tests.

## Editing conventions

- Validate JavaScript in any edited standalone HTML (both `tts_web.html` and `vi-video-dubber/web.html`):

```bash
node - <<'NODE'
const fs = require('fs');
const html = fs.readFileSync(process.argv[1], 'utf8');
const scripts = [...html.matchAll(/<script(?:\s[^>]*)?>([\s\S]*?)<\/script>/gi)]
  .map(m => m[1]).filter(s => s.trim());
for (const script of scripts) new Function(script);
console.log('ok');
NODE
```

- Prefer `rg` for searching; use edit/patch tools for edits. Respect existing user changes; don't revert unrelated work.
- Keep docs (`README.md`, `AGENTS.md`) in sync when user-facing workflows change.
- The user may write in Vietnamese; this guide stays in English.
- When the user says "ghep lai vao video", clarify soft subtitles vs burned-in vs full voice-over if the distinction matters.

## ADHD Communication Mode

Apply to every response in this repo:

1. **Lead with the next action** — first line is a command, file path, or one doable step. No context first.
2. **Number multi-step tasks.** Each step = one bounded action. No "and then" twice in one step.
3. **End with one concrete next action.** Under two minutes. Even "open the file" counts.
4. **Suppress tangents.** Finish the first issue before offering a second as a separate question.
5. **Restate state every turn.** "Step 3 of 5 done: X. Next: Y."
6. **Give specific time estimates.** "About 15 min if tests exist. An afternoon if not."
7. **Make completed work visible.** Show what now works, in concrete terms.
8. **Matter-of-fact tone for errors.** State cause and fix. No "Uh oh."
9. **Cap lists at 5 items.** Split into "do now" vs "later" if needed.
10. **No preamble, no recap, no closing pleasantries.** Start with the answer. End when done.

### When to break the rules

- User asks to "explain" or "walk me through" → explain fully, add headers for skimming.
- Destructive action ahead (`rm -rf`, force push, schema migration) → confirm first.
- Debug spiral (3+ turns of "still broken") → stop iterating, name the wrong assumption, ask one diagnostic question.
- Real ambiguity → one short clarifying question beats guessing and rewriting.