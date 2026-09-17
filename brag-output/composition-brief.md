# Hyperframes Composition Brief: AI Video Dubber (ViVidDubber)

## Objective
Create a short launch-style brag video for AI Video Dubber (ViVidDubber) — a local batch video-dubbing workbench.

## Output
- Composition directory: `brag-output/composition/`
- Rendered video: `brag-output/brag.mp4`
- Format: landscape — 1920x1080
- Duration: 20 seconds

## Source Material
- Project root: `/home/quang/work/ViVidDubber` (working directory is the `vi-video-dubber/` app root)
- Primary files read: `web.html` (full UI + inline styles/script), `tokens.css`, `AGENTS.md`, `README.md`
- Product name: AI Video Dubber (brand markup: `<span class="brand-name">AI VIDEO<span class="brand-suffix"> DUBBER</span></span>`)
- Tagline / strongest claim: "Fully local, fully free — no API keys, no paid services, no cloud dependencies." / Cost: **$0**. Real page H1: "Nhiều video. Một hàng đợi. Chạy lần lượt." (Many videos. One queue. Run one after another.)
- Key UI or visual moment to recreate: the real batch workbench — file-drop zone → queue-list job cards stepping through real pipeline stage labels → preview panel flipping to the burned-in Vietnamese-subtitled video → stats line + download-all zip button. This is the real DOM structure/copy from `web.html`, not an invented mockup.
- Copy that must appear verbatim (real UI strings, keep Vietnamese as-is — it's the authentic product language):
  - `AI VIDEO DUBBER` (brand wordmark)
  - `N INPUT → N MP4` (real panel-code badge style, seen next to "Thiết lập batch")
  - `Chọn hoặc thả nhiều video` (drop-zone label)
  - Pipeline stage sequence: `Tách audio` → `Whisper` → `Dịch` → `Lồng tiếng` → `Burn` (derived from the real job flow in `AGENTS.md`/`app.py`: probe → extract WAV → transcribe → translate → mux/dub → burn)
  - `Tổng 4 job · 4 xong · TB 1m12s/job` (styled after the real `queueStats` template in `web.html`'s script: `` `Tổng ${jobs.length} job · ${done.length} xong · Tổng thời gian xử lý ${...} · TB ${...}/job` ``)
  - `⬇ Tải tất cả bản lồng tiếng (.zip)` (real `downloadAllBtn` label)
  - `LOCAL WORKBENCH · BATCH QUEUE` (real footer meta line)
  - Outro line: `$0.` / `No cloud. No API keys. Your GPU.`

## Creative Direction
- Tone preset: `app-store`
- Creative direction: confident local-dev-tool flex — feature-card clean, grounded entirely in the real dark workbench UI instead of invented mockups.
- Interpretation: title-case feature beats, present tense, no forced jokes — the batch queue doing real sequential work is the spectacle. Clean slide/wipe transitions (0.35-0.45s), no aggression or chaos. Confidence comes from showing the queue actually working.
- Angle: This is a real dev tool with a rare claim: an entire local AI pipeline (transcription, translation, TTS, voice cloning) running on a consumer GPU for $0, no cloud. Show the batch queue actually chewing through videos one by one, then land "$0 / no cloud" as the mic-drop. No irony needed — the product's own restraint sells it.
- Hook: dark canvas, wordmark "AI VIDEO DUBBER" fades/slams in centered, small-to-medium scale, mauve accent on "DUBBER". The real panel-code badge style renders "N INPUT → N MP4" beneath it.
- Outro / punchline: cut to near-black. Big type "$0." holds, then smaller stacked "No cloud. No API keys. Your GPU." Wordmark returns small, bottom-center, with "LOCAL WORKBENCH · BATCH QUEUE" beneath as the final hold.
- Avoid:
  - Generic SaaS language ("streamline your workflow", etc.)
  - Abstract filler visuals, waveform/equalizer graphics, generic particle systems
  - Unrelated visual redesign — reuse the locked Catppuccin Mocha tokens exactly, don't invent new colors/fonts
  - Inventing UI structure not present in the real `web.html` (drop zone, queue-list job cards, panel-code badges, preview panel, stats line, download-all button are all real elements — recreate their real look, not a generic dashboard)

## Visual Identity
- Background: `#1e1e2e` (base), secondary panel `#181825` (mantle), card surface `#313244` (surface0)
- Text: `#cdd6f4` (ink) primary, `#a6adc8` (muted) secondary/help copy, `#bac2de` (ink-2) for subtext
- Accent: `#cba6f7` (mauve, primary), `#89b4fa` (blue, secondary), `#74c7ec` (sapphire, tertiary), `#a6e3a1` (success/green) for completed states
- Rule/border colors: `#45475a` (rule), `#6c7086` (rule-2)
- Display font: "Space Grotesk" (fallback "IBM Plex Sans", system-ui, sans-serif) — headings/wordmark
- Body font: "IBM Plex Sans" (fallback system-ui, sans-serif)
- Radii/spacing feel: soft card radius (~1rem), pill-shaped badges (999px) for tags like the panel-code and stage-label chips — matches the real `--radius-card`/`--radius-pill` tokens
- Visual references from the project: the `panel-code` badge treatment (monospace-ish uppercase tag, e.g. `N INPUT → N MP4`, `QUEUE 4`), the `output-card`/queue job-row card style (rounded card, label + small metadata line, progress fill), the `.screen`/preview panel with video frame and burned-in subtitle text overlay, the `foot-stmt` footer meta line style

## Storyboard
Use the storyboard in `brag-output/brag-plan.md` as the creative contract — full per-scene detail, audio-coupled ideas, and sequential/interaction notes live there.

Scene summary:
1. Hook — 3s — wordmark "AI VIDEO DUBBER" + "N INPUT → N MP4" panel-code badge
2. Multi-file drop — 4s — real drop-zone card, 3-4 files land one by one, counter increments to "4 video · 1.2 GB"
3. Pipeline in motion — 5s — real queue-list job cards, stage labels advance (Tách audio → Whisper → Dịch → Lồng tiếng → Burn) on job 1 while job 2 begins
4. Burned-in result — 4s — preview panel flips to burned-in Vietnamese-subtitled frame, stats line resolves, download-all button arrives
5. Outro / punchline — 4s — "$0." + "No cloud. No API keys. Your GPU." + wordmark + footer tag, final hold

## Audio
- Audio role: sparse professional accents over a clean, modern minimal-electronic bed
- Audio arc: bed starts low under the hook, holds steady through the drop and pipeline scenes with light rhythmic presence, gentle swell begins at the burned-in reveal, peaks into a single chime on "$0.", fades to silence by the last frame
- Music: `happy-beats-business-moves-vol-11-by-ende-dot-app.mp3` (warm, business-y, 1:28 — matches `app-store` restraint), copied to `brag-output/composition/assets/music/`
- Music treatment: start at low volume (~0.3) under scene 1, hold steady through scenes 2-3, gentle swell into scene 4→5, fade to silence over the final ~1s of scene 5
- Music cue guidance: bundled preset at `assets/music/cues/happy-beats-business-moves-vol-11-by-ende-dot-app.music-cues.json` (also `.md` summary copied alongside). Tempo ~114.84 BPM. Strong cues in the 0-20s window: 1.60s, 3.70s, 5.80s, 6.34s, 8.96s, 9.50s, 12.65s, 17.91s. Target the burned-in reveal (scene 4 start, ~12s planned) toward the 12.65s strong cue (~0.65s from the natural cut — nudge only if it doesn't hurt the scene 3 pipeline pacing), and the "$0." slam (scene 5 start, ~16s planned) may drift toward whichever strong cue lands closest once scene 3/4 timing is finalized. Use the full beat grid (1.60, 2.12, 2.65, 3.18, 3.70, 4.23, 4.75, 5.28, 5.80, 6.34, 6.86, 7.38, 7.91, 8.44, 8.96, 9.50, ...) for the scene-3 pipeline stage-label ticks — but hold each stage label to its readable floor (~0.6s+) rather than snapping every beat.
- Audio-reactive treatment: subtle — the mauve accent glow on the wordmark and panel-code/stage-label badges may breathe slightly with music RMS/bass. No waveform, equalizer, or particle visuals.
- Audio-coupled moments:
  - Scene 1 — panel-code badge snap-in — soft chime
  - Scene 2 — each file drop — soft thud/pop per file, counter tick synced to each increment
  - Scene 3 — each pipeline stage-label advance — one soft tick per stage
  - Scene 4 — video-frame swap to burned-in — soft whoosh; stats line resolving — gentle counter tick; download-all button arrival — soft pop
  - Scene 5 — "$0." landing — single clean chime, then music fades under the final hold
- SFX selection guidance: match the real gestures — file drops use soft "landing" sounds (`interface/drop_*`), stage-label ticks use light UI click/select sounds (`interface/select_008`, `ui/click*`), the burned-in reveal uses a medium soft-impact whoosh (`impact/impactSoft_medium_*`), the stats/download-all pop-ins use light click/drop sounds, and the "$0." punchline uses one resonant bell (`impact/impactBell_heavy_000` or `_003`) per the `app-store` outro convention. Keep SFX at 0.65-0.75 volume per `app-store` guidance; music at ~0.3, swelling toward but not exceeding ~0.4 at the outro.
- SFX analysis guidance: read `skills/brag/assets/sfx/sfx-analysis.md` (or the plugin-cache path `/home/quang/.claude/plugins/cache/brag/brag/0.2.2/skills/brag/assets/sfx/sfx-analysis.md`) before final selection; prefer low/medium HF-risk files since most moments here are polished/repeated (file drops, stage ticks), reserving any higher-risk file only for the single outro chime if needed.
- Exact SFX choice: Hyperframes should choose exact filenames, timestamps, density, and volume based on the implemented animation.
- Audio files: music already copied to `brag-output/composition/assets/music/` (plus its cue preset in `assets/music/cues/`). Copy any chosen SFX into `brag-output/composition/assets/sfx/...` mirroring the source subfolder structure before referencing them.

## Hyperframes Instructions
Load the composition-building Hyperframes domain skills — `hyperframes-core` (composition contract + `data-*` timing), `hyperframes-animation` (motion), `hyperframes-creative` (design spec, beats, audio-reactive), `hyperframes-keyframes` (seek-safe keyframes), and `hyperframes-cli` (lint/check/render). `/brag` is its own workflow: do not enter the `hyperframes` entry-point intent interview and do not route into its generic promo / launch-video workflow. Prefer native Hyperframes conventions over anything in `/brag`.

Requirements:
- Show at least one real UI, copy, or visual element from the source project (the drop zone, queue-list cards, preview panel, stats line, and download-all button are all real — recreate their real look and copy).
- Keep all text readable in the final render — respect the reading-time floors from `brag-plan.md` (short labels ~0.8s settled, sentences ~0.3s/word).
- Keep the video within 15-25 seconds (target 20s).
- Include the planned music/SFX layer — audio was not disabled.
- Treat `/brag` audio notes as guidance, not a fixed cue sheet. Choose SFX after the visual animation exists.
- Treat music cue metadata as optional timing hints. Ignore cues that hurt readability, scene pacing, or the product story.
- Major reveals may move toward nearby strong cues within about 0.15s. Smaller entrances may align to nearby beat points within about 0.10s. Use only 1-3 strong cue locks in this 20s video.
- Use SFX to support motion and interaction per the moment-type guidance above; keep restraint (`app-store` = consistent light layer, not a grab bag).
- Honor the planned music treatment: low start, steady hold, gentle swell into the outro, fade on the final hold.
- Wire at least one visual element to audio-reactive RMS/bass data (subtle glow/presence on the wordmark or badges) per the `hyperframes-creative` audio-reactive workflow; if extraction is unavailable, document it and skip rather than block the render.
- Use local assets for audio and any required runtime/media dependencies.
- Run `hyperframes check` before render — it is brag's single gate.
