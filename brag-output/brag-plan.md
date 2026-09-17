# Brag Plan: AI Video Dubber (ViVidDubber)

## What is this app?
A local, self-hosted workbench that takes a batch of English videos and turns each one into a Vietnamese-dubbed, subtitled MP4 — fully offline pipeline (Whisper → translate → Edge-TTS/VieNeu-TTS → FFmpeg burn), $0, no cloud, no API keys.

## The angle
This is a real dev tool with a genuinely rare claim in 2026: an entire AI pipeline (transcription, translation, TTS, voice cloning) running locally on a consumer GPU for zero dollars. The angle is a clean, confident software-product flex — show the batch queue actually chewing through videos one by one, then land the "$0 / no cloud" claim as the mic-drop. No irony needed; the absurdity of "free enterprise-grade dubbing pipeline on your own 4GB laptop GPU" is the joke, played straight.

## Hook (first 2-3 seconds)
Dark canvas. The wordmark **AI VIDEO DUBBER** sits small and centered, mauve accent glow. Under it, the panel-code style tag from the real UI, `N INPUT → N MP4`, snaps in. This is the product's own visual language (`panel-code` badges in the real UI) used as the opening beat — instantly reads as "batch tool," not generic AI-app landing copy.

## Key moments (the middle)
- **Multi-file drop**: cursor drags 3-4 video files onto the real drop-zone copy ("Chọn hoặc thả nhiều video"). Filenames stack, counter updates to "4 video · 1.2 GB", drop zone state flips to filled.
- **Queue chews through it**: 4 job rows appear in the real queue-list layout, each stepping through the real pipeline stage labels (Tách audio → Whisper → Dịch → Lồng tiếng → Burn) with a progress fill — one job visibly finishing while the next starts, proving "chạy lần lượt" (sequential queue), not parallel chaos.
- **Burned-in result**: the preview panel flips from the raw upload to the burned-in output — Vietnamese subtitle text baked onto the video frame — while the real stats line populates: "Tổng 4 job · 4 xong · TB 1m12s/job", then the real "⬇ Tải tất cả bản lồng tiếng (.zip)" button appears.

## Outro / punchline
Cut to black-mauve. Big type: **$0.** Then, smaller, stacked: "No cloud. No API keys. Your GPU." Wordmark returns, small, bottom-center, with the real footer line "LOCAL WORKBENCH · BATCH QUEUE" as the closing tag.

## User flow worth showing
1. Entry: drop multiple video files into the batch form.
2. Key action: queue processes them one at a time through the real pipeline stages (extract → transcribe → translate → dub → burn), visible as sequential progress on job cards.
3. Result: preview swaps to the burned-in Vietnamese-subtitled video; a "download all" zip appears once the whole batch is done.

## Tone
- Preset: `app-store`
- Creative direction: confident local-dev-tool flex — feature-card clean, but grounded entirely in the real dark workbench UI instead of invented mockups.
- Interpretation: title-case feature beats, present tense, no jokes forced — the pipeline doing real sequential work *is* the spectacle. Clean slide/wipe transitions (0.35-0.45s), no aggression, no chaos. Confidence comes from showing the batch queue actually working, not from hype copy.

## Format: landscape — 1920x1080
## Duration: 20s target

## Visual identity (from the project)
- Background: `#1e1e2e` (Catppuccin Mocha base), secondary panel `#181825` (mantle), card surface `#313244` (surface0)
- Accent: `#cba6f7` (mauve, primary accent) with `#89b4fa` (blue) and `#74c7ec` (sapphire) as secondary accents; success state `#a6e3a1`
- Text: `#cdd6f4` (ink) primary, `#a6adc8` (muted) for secondary/help copy
- Display font: "Space Grotesk" (headings/wordmark)
- Body font: "IBM Plex Sans"
- Strongest visual element: the real `panel-code` tag badges (e.g. `N INPUT → N MP4`, `QUEUE 4`) and the queue-list job cards with step-by-step progress — this IS the product's own design language, not a recreation.

## Share copy (draft)
Drop in 4 English videos, walk away, come back to 4 Vietnamese-dubbed, subtitled MP4s — fully local, $0, zero cloud calls.

## Audio direction
- Role: sparse professional accents over a clean, modern minimal-electronic bed
- Music: low-key confident tech-product bed (soft pulsing synth, no vocals), mood matches `app-store` restraint
- Music treatment: starts under the hook at low volume, holds steady through the queue/pipeline scenes, gentle swell into the outro's "$0" beat, quick fade on the final hold
- Music cue guidance: to be detected at composition time (no bundled preset chosen yet); target one strong cue at the burned-subtitle reveal (~scene 4 start) and one at the "$0" slam (scene 5 start); beat-grid window for the 5-stage pipeline ticks in scene 3 (space stage-label reveals evenly, not tighter than ~0.6s apart)
- Audio-reactive treatment: subtle — the mauve accent glow on the wordmark/panel-code tags may breathe slightly with the music, nothing waveform-y
- SFX posture: moderate, motion-matched — file-drop thud, per-stage tick/chime as each pipeline label advances, soft whoosh on the burned-in reveal, single clean chime on "$0"
- Audio-coupled moments: pipeline stage labels ticking in scene 3 (each stage = one tick sound), stats line populating in scene 4 (soft counter tick), download-all button arrival (soft pop)
- Restraint rule: no music vocals, no glitch/chaos SFX, no waveform visualizers — this is a clean product flex, not a hype reel

## Storyboard

### Scene 1 — Hook — 3s
Dark `#1e1e2e` canvas. Wordmark "AI VIDEO DUBBER" (Space Grotesk, mauve accent on "DUBBER" suffix per real brand markup) fades/slams in centered, small-to-medium scale. Below it, the real panel-code badge style renders "N INPUT → N MP4".
Sequential/interaction: none
Audio intent: quiet confident opener, no punchline yet — just presence
Audio-coupled idea: soft chime as the panel-code badge snaps in
Music: bed starts low under this scene
Transition mood: clean slide → Scene 2

### Scene 2 — Multi-file drop — 4s
The real drop-zone card ("Chọn hoặc thả nhiều video") is shown. A cursor drags in 3-4 video thumbnails one after another; each drop increments the file counter and total size ("4 video · 1.2 GB"), drop-zone border flips to its filled/accent state.
Sequential/interaction: yes — files arrive one by one, counter increments with each, drop-zone state changes on the last one
Audio intent: tactile, satisfying — each file lands with weight
Audio-coupled idea: soft thud/pop per file drop, counter tick synced to each increment
Music: bed continues, light rhythmic presence
Transition mood: clean wipe → Scene 3

### Scene 3 — Pipeline in motion — 5s
Cut to the real queue-list layout: 4 job rows/cards stacked, each labeled with a stage from the real pipeline (Tách audio → Whisper → Dịch → Lồng tiếng → Burn). Job 1's progress bar fills and its stage label advances through the sequence while Job 2 sits queued below; as Job 1 nears completion, Job 2's row begins animating too — demonstrating the sequential (not parallel) queue.
Sequential/interaction: yes — stage labels advance one at a time on Job 1 (hold each stage label to a readable floor, spaced no tighter than ~0.6s), Job 2 activates near the end of the scene
Audio intent: mechanical, steady, "it's working" — a sense of real processing
Audio-coupled idea: one soft tick per stage-label advance
Music: bed holds steady, slight rhythmic pulse under the ticks
Transition mood: soft wipe → Scene 4

### Scene 4 — Burned-in result — 4s
The real preview panel: video frame swaps from the raw upload to the burned-in output, Vietnamese subtitle text visible baked onto the frame. Below it, the real queue-stats line populates: "Tổng 4 job · 4 xong · TB 1m12s/job", followed by the real download-all button ("⬇ Tải tất cả bản lồng tiếng (.zip)") sliding/popping in.
Sequential/interaction: yes — stats line text settles first, then the download-all button arrives right after (each gets its own readable beat)
Audio intent: payoff — the "there it is" moment
Audio-coupled idea: soft whoosh on the video-frame swap, gentle counter-tick as the stats line resolves, soft pop on the download-all button
Music: gentle swell begins, leading into the outro
Transition mood: clean crossfade → Scene 5

### Scene 5 — Outro / punchline — 4s
Cut to a near-black `#181825` canvas. Big Space Grotesk type: **$0.** holds, then smaller stacked line beneath: "No cloud. No API keys. Your GPU." Wordmark returns small, bottom-center, with the real footer tag "LOCAL WORKBENCH · BATCH QUEUE" beneath it as the final hold.
Sequential/interaction: yes — "$0." slams in first and holds, then the supporting line arrives underneath, then the wordmark/footer tag settles last
Audio intent: confident final beat, then quiet
Audio-coupled idea: single clean chime timed to "$0." landing; music fades under the final hold
Music: swell peaks on "$0.", fades to silence by the last frame
Transition mood: hard hold (end)

**Music mood for this video:** clean minimal-electronic, confident and unhurried (app-store restraint)
**Audio summary:** A quiet, steady tech-product bed underscores real UI motion (file drops, pipeline ticks, stat reveals) with sparse motion-matched SFX, swelling once into a single chime on the "$0." punchline before fading to silence.
