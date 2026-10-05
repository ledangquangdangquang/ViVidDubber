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
- Pipeline modules in `pipeline/`: `media.py` (ffmpeg/ffprobe), `transcribe.py` (faster-whisper), `translate.py` (Google or EnViT5), `tts.py` (Edge-TTS dubbing, VieNeu-TTS offline), `subtitle.py` (SRT parse/write).
- **By design: no paid APIs, no Supertonic ONNX.** Dependencies are free: faster-whisper, edge-tts, veneu, transformers<5, deep-translator, Google's free `translate_a/single` endpoint.
- Job flow in `_run_job` (`app.py:349`): probe → cut to `trim_start`/`trim_end` (optional form fields, ffmpeg time syntax; `trim_video` re-encodes to `trimmed.mp4` for a frame-exact cut, and every later step uses it) → extract 16 kHz mono WAV → transcribe → translate → mux soft subs (always) → dub (if `dub=true`) → burn (if `export_mode=burn`). With dub+burn, the picture is burned from the input (`-an`, `burned_video_only.mp4`) in a background thread that runs alongside TTS; the burn step then joins it and stream-copies the dub audio in (`replace_audio`).

### Providers & env vars

- **Whisper**: model `small` default (`whisper_model` form field); device/compute via `WHISPER_DEVICE` (default `cpu`), `WHISPER_COMPUTE_TYPE` (`int8`). The UI sends `whisper_compute_type=int8_float16` (hidden input in `web.html`): `medium` needs ~1.2 GB vs ~2.1 GB at `float16`, same speed, ~97% identical words, and it fits next to the resident translator on 4 GB. On a CUDA error it first calls `free_vram` (`_free_translators` in `app.py`: drops the resident HF/EnViT5 model, ~1.2 GB) and retries on GPU once, then falls back to cpu/int8 — on 4 GB, Whisper `medium` `float16` doesn't fit next to the resident translator, and the CPU fallback (~114s vs ~20s) costs far more than reloading the translator (~11s). Model downloads from HF on first run. `condition_on_previous_text=False`: with it on, once a 30s window drops punctuation every later window does too (randomly; one 91-min run lost it from 9:47 on), and sentence grouping then falls back to ~300-char cues.
- **Source language** (`source_lang` form field: `en` default, `zh`, `ja`; UI select "Ngôn ngữ trong video"): passed to Whisper `language` and the translator. For zh/ja, Whisper gets a punctuation prompt via `hotwords` (`_PUNCTUATION_PROMPTS` in `transcribe.py`) — without it zh/ja come out with no punctuation at all (and zh in Traditional), so every cue hits the char cap; `initial_prompt` would only cover the first 30s window since `condition_on_previous_text=False`. `group_sentences` also cuts at `。？！` and uses `_CJK_LIMITS` (~1/3 of the Latin char caps). EnViT5 is English-only: the API rejects it for zh/ja and the UI disables it.
- **Translate** (`translation_provider`): `google` (default, no key — free gtx endpoint, 20-line chunks joined with newlines, 3 retries + backoff, per-line rescue, untranslated lines are kept as original English and surfaced in job `translation_warnings`), `huggingface` (direct Transformers load of `tencent/Hy-MT2-1.8B`, GPU if CUDA else CPU, lazy-loads a shared singleton; **default 4-bit quantized via bitsandbytes** to cut VRAM ~3.4GB→~1.2GB — `HF_TRANSLATE_QUANT=4bit`|`none`, falls back to FP16 on CPU or if missing; env `HF_TRANSLATE_REPO`, `HF_TRANSLATE_BATCH_SIZE`, `HF_TRANSLATE_DEVICE`, `HF_TRANSLATE_QUANT`), or `envit5` (offline Transformers: `VietAI/envit5-translation`, GPU if CUDA else CPU, lazy-loads a shared singleton pipeline; env `ENVIT5_MODEL`, `ENVIT5_BATCH_SIZE`). Google path needs internet. HuggingFace/EnViT5 are local. The HF/EnViT5 model is a class-level singleton keyed by `(repo, device[, quant])` — assign via `cls`, not `self` (assigning `self._model` once made every job reload it, ~11s). `_translate_blocks` batches lines sorted by length and writes results back in file order (50 lines: 16.3s → 11.0s; `test_translate.py`). Don't preload the translator alongside Whisper: on 4 GB the 4-bit load's transient VRAM peak pushed Whisper `medium` into its CPU fallback (118s vs ~20s), costing far more than the ~11s load it hid (only the first job after a server start pays it). EnViT5 needs `transformers<5` (v5 removed the `translation` pipeline and broke the EnViT5 tokenizer) — pinned in `pyproject.toml`. On machines where the default `gcc` lacks the multiarch Python include dir, triton's JIT compile fails → `_lazy_load` sets `CC=/usr/bin/gcc` fallback.
- **TTS voice**: Edge-TTS (online, default) or VieNeu-TTS (offline). `tts_provider` form field selects engine; `tts_voice` selects voice. Edge-TTS default `vi-VN-HoaiMyNeural` (non-`vi-VN-*` voice with `F` in name → HoaiMy, else `vi-VN-NamMinhNeural`). VieNeu-TTS has 23 preset voices (Bắc/Trung/Nam), voice cloning, emotion cues (`[cười]`, `[thở dài]`, `[hắng giọng]`), 48 kHz, device comes from the `tts_device` form field (UI default `cuda`; env `VIENEU_DEVICE` is the fallback, default `cpu`). `cuda` → PyTorch backend on GPU; `cpu` → torch-free ONNX backend. Swapping device reloads the singleton. Even on `cuda`, vieneu's speaker encoder and denoiser are hardcoded to CPU ONNX (`onnxruntime-gpu` doesn't change that), so clone `ref_audio` is encoded **once** in `VieNeuTTS._lazy` and passed to `infer` as a `voice` dict — passing `ref_audio=` per call re-denoises/re-encodes on CPU every block (~2.4s each). On `cuda`, `create_vietnamese_dub` synthesizes all uncached lines in one `VieNeuTTS.synthesize_batch` → vieneu `infer_batch` call (lines share forward steps: 53 lines 89s → ~22s on an RTX 3050 4GB, peak ~720MB); on CPU/ONNX it keeps the per-line thread pool. VieNeu ignores `speed`, so the slow-cue regen pass is skipped for it. Model load + ref encode + kernel warm-up is ~13s and `_free_gpu` drops the model before every Whisper run, so `_run_job` calls `VieNeuTTS.preload()` in a background thread right after transcription (overlapping translation) and joins it before the dub step (call `import_backend()` on the main thread first: importing `transformers` from that thread while the HF translator imports it raises `cannot import name 'PretrainedConfig'`; and every model construction holds `pipeline.MODEL_LOAD_LOCK`, because `from_pretrained`'s `init_empty_weights()` patches `nn.Module.register_parameter` process-wide, so a model built in another thread meanwhile gets empty meta tensors); encoded clone refs are cached per path in `VieNeuTTS._ref_voices` across reloads. `batch_size` 16/32/64 made no difference (~27s for 50 lines), the batch itself is GPU-bound. (`tts.py` `VieNeuTTS`)
- Dubbing alignment: clip >2× the subtitle slot is re-synthesized at 1.25× speed; clips still longer than the slot are time-stretched with chained `atempo`; output replaces original audio unless `background_volume > 0`.

### API & job artifacts

- `POST /api/jobs` (multipart `file` + form options), `GET /api/queue`, `GET /api/jobs/{id}`, `POST /api/jobs/{id}/pause`, `POST /api/jobs/{id}/resume`, `POST /api/jobs/{id}/cancel`, `GET /api/jobs/{id}/download/{kind}`, `GET /api/config` (translation providers), `GET /api/stats` (dub-benchmark rows, see below), `POST /api/preview-voice` (form `tts_provider`+`tts_voice` → short WAV sample via the `listen` button next to the voice select in `web.html`; synthesized with the same `EdgeTTSEngine`/`VieNeuTTS` classes as a real job, `lru_cache`d per voice). Voice `<select>` lists are built from the `VOICES` table in `web.html` (male group before female).
- **Dub benchmarking**: on every job that finishes with `dub=true`, `_log_dub_stats` (`app.py`) appends one row to the JSON array in `jobs/stats.json` — `video_duration_sec` (via `probe_media`), `dub_elapsed_sec` / `total_elapsed_sec` (from `job.step_timings`), and the GPU config (`gpu` via `torch.cuda.get_device_name(0)`, plus `whisper_device` (requested) / `whisper_device_used` (actual, differs when Whisper fell back to CPU on OOM) / `translate_device`/`translation_provider`/`tts_provider`). Read it back via `GET /api/stats`. Lets you compare video length vs. completion time across GPU configs.
- Limits: 2 GB upload (file mode), 50 jobs, finished jobs auto-deleted after 6 h TTL.
- Two input modes via `POST /api/jobs`: `file` (multipart) or `video_url` (a single YouTube video). `POST /api/resolve` flattens a link into per-video `{url,title}` entries (`extract_flat`, no download); the UI lists them with checkboxes for selection and submits one `POST /api/jobs` per chosen video (downloads run sequentially). The actual yt-dlp download happens **inside `_run_job`** (step "Downloading video from YouTube", 720p preferred, title becomes the download stem), so `create_job` returns instantly. `_run_job` treats the downloaded file identically to an upload.
- Per-job dir `vi-video-dubber/jobs/<id>/`: `input*`, `audio.wav`, `original.srt`, `vi.srt`, `<stem>_vi_soft.mp4`, `<stem>_vi_dub.mp4`, `<stem>_vi_burned.mp4`. Download filenames are renamed to `<original_stem>_…`.

### Subtitle handling rules

- Preserve SRT indexes and timestamps; translate text only. `write_srt` re-numbers blocks and wraps at 42 chars / 2 lines.
- Burn-in uses the `subtitles` filter; form field `flip=true` (UI switch, default off) prepends `hflip` so the picture is mirrored but the subtitles stay readable — burn mode only, soft output is never flipped. `cover_bottom` (0–0.4 of the height, UI slider "Làm mờ phụ đề gốc", default 0 = off) gblurs that bottom band before our subs are drawn, to hide the source's own hardsubs (common in zh/ja videos); also burn only. `show_source=true` draws "Cre: <name>" top-left with `drawtext` (text read from `source_credit.txt`, `expansion=none`, so channel names need no escaping); name = `source_credit` form field, else the YouTube channel (`download_video` returns it, stored as `source_channel` in job options). `/api/resolve` returns `channel` per video so the UI pre-fills the field (left empty for mixed-channel playlists).
- Burn-in uses the `subtitles` filter; escape the SRT path for the filter (`burn_subtitles` in `media.py`). Windows path escaping matters.
- Burn encoder: `h264_nvenc` (`-cq 27`, ~2x faster than x264 on an RTX 3050, same SSIM) when a test encode opens it, else `libx264 veryfast crf18`; `BURN_ENCODER=libx264` forces CPU. The Nix ffmpeg can't see host NVIDIA libs, so `_driver_lib_env` symlinks `libcuda`/`libnvidia-encode`/`libnvcuvid` into `$TMPDIR/vivid-nvenc-libs` and puts only that on `LD_LIBRARY_PATH` (the whole system lib dir clashes with Nix glibc).
- Slow/risky TTS text is stripped of `<…>`, `[…]`, `(…)` before synthesis; empty text becomes 0.5 s silence.

## Legacy stack: `tool/`

Two older tools, still present and documented in `README.md` + `tool/WEBSOCKET_API.md`:

- `tool/ws_tts_server.py` — WebSocket TTS server on `ws://127.0.0.1:8765`, UI `tool/tts_web.html` (uses Supertonic ONNX in `assets/`).
- `tool/video_pipeline_server.py` — earlier localizer UI `tool/video_localizer_web.html` (Cerebras via `CEREBRAS_API_KEY` or Ollama + Supertonic TTS dubbing). Docker support: `docker compose up --build -d`.

Tests for the old stack live in `tool/test_pipeline.py` (pytest); **pytest is not installed in either venv by default** — install it into `py/.venv` before running. `vi-video-dubber/` has no tests.

## UI changes: use the Hallmark skill

`web.html` already carries a locked design system: `tokens.css` (custom "Terminal" theme: phosphor green on
near-black, JetBrains Mono everywhere, OKLCH tokens; a light variant under `:root[data-theme="light"]`,
toggled by the sun/moon button, first visit follows the OS, choice kept in `localStorage`) plus a
`/* Hallmark · genre: ... macrostructure: Workbench · theme: ... */` stamp at the top of its `<style>`
block. Any request to change, fix, or redesign the UI must go through the **`hallmark`** skill
(`.claude/skills/hallmark`) — invoke it via the Skill tool rather than hand-rolling CSS.

- For small additions/fixes to existing markup, treat it as `hallmark redesign` on `./web.html`
  (single-page flow) — preserve the existing IA, tokens, and stamp; don't invent new colors/fonts.
- Reference existing tokens (`var(--color-*)`, `var(--space-*)`, `var(--radius-*)`, ...) from
  `tokens.css`. No inline `style="..."` — add a real CSS rule.
- Don't swap the theme or macrostructure without the user asking for a redesign. Layout is queue-first:
  N8 prompt bar (`> vividdubber queue`) + `[+ thêm video]` (key `N`), queue list + sticky preview, a
  vim-style status line, and all job options in a native `<dialog id="addDialog">` side sheet (closes
  itself once every job is queued). Terminal voice: `# section` titles, `[x]`/`[ ]` checkboxes,
  bracketed status tags, `█░` text progress bar, outputs listed by file name. No SVG icons, no emoji.
- UI copy is bilingual (EN default, VI) via the `I18N` table in `web.html`'s script: static markup uses
  `data-i18n="key"` / `data-i18n-attr="attr:key;…"`, JS uses `t('key', {vars})`. Any new user-facing string
  needs a key in **both** `en` and `vi`. Server-sent text (job `error`, `translation_warnings`) is not translated.
- Update the stamp comment and `.hallmark/log.json` (if present) when a change actually alters the
  structural fingerprint, not for routine bug fixes.

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