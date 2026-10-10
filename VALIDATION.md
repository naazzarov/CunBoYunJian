# Verification update · 2026-10-10

- 48 automated tests pass. Duration-valid range IDs eliminate the need for a small model to calculate clip lengths; tests verify unknown/short ranges are rejected and absolute source boundaries are preserved. Eligibility does not guarantee semantic quality or force the model to select a clip.
- Official FunClip v2.1.0 with FunASR 1.4.0 now runs in the isolated Python 3.10 environment. seaco-Paraformer / FSMN VAD / CT-Transformer v2.0.4 and CAM++ v2.0.2 loaded. The public Chinese sample yields the expected sentence, timed SRT and anonymous speaker 0; hotword input is exercised. This single-speaker sample does not certify real multi-speaker separation or proper-name accuracy.
- ASR wording and model explanations still need human correction. This verifies the pipeline, not the editorial quality of every clip. Live selection uses the explicitly displayed Qwen3 1.7B fallback.
- Qwen3 8B official weights are downloaded. Normal Ollama inference fails Metal initialization here. CPU runner tests load but time out on short answers, including an isolated mmap/no-repack run with a 2048-token context. 8B is not accepted as a usable default on this Mac.
- OBS 32.2.2 official Apple Silicon installer checksum matches the GitHub release digest; disk-image mounting is unavailable in the execution environment. Installation and real screen/audio/WebSocket acceptance remain pending. No paid calls were made.

Previous verification below is historical and describes the configurations used on those dates.

# CunBo YunJian validation

## Branded workflow update — 9 October 2026

- 46 automated tests pass locally. New tests cover correction retries for short candidates, original-preserving SRT reprocessing, access-controlled source playback, silence timeline mapping and protection of subtitle-covered speech.
- Actual auto-editor 31.7.2 v3 export was verified against its official Release digest. A generated 16-second audio/video fixture with 10 seconds of silence exported a 6.458-second cleaned recording; audio/video durations match within 0.001 seconds. Short fades are applied at cuts. This is a generated integration fixture, not a client recording.
- MoviePy 1.0.3 with ImageMagick rendered Chinese hard subtitles, inspected in a decoded video frame. A fresh live job reused the official public Chinese sample's SRT, selected a 4.8-second interval, exported a 4.833-second portrait video with hard subtitles, and saved keyword and selection diagnostics. Its measured end-to-end processing time was 12.661 seconds, using the existing local Qwen3 1.7B model.
- Chinese and English controls, the six-section knowledge template and the 390px phone layout were checked in the actual browser. Page width equals viewport width at 390px. Native iOS/Android devices have not been certified by this browser-width check.
- Python 3.10.22, FunASR 1.4.0, torch 2.8.0, ModelScope 1.40.1 and the official FunClip v2.1.0 VideoClipper import successfully; pip check reports no broken requirements. Speech-model weights and exact-toolchain end-to-end acceptance remain pending available storage. Qwen3 8B weights downloaded successfully; this does not establish its viability on the 8 GB Mac.
- A real recheck of the user's existing 68-second transcript proposed six sub-15-second candidates, then returned no candidates after the correction prompt. This confirms the retry path, not improved transcription or editorial quality. The original task was preserved.
- OBS recording, manual Jianying final export and phase-two RAG/vision/draft components are not represented as completed. See environment_version_log.md and FIRST-PHASE-STATUS.zh-CN.md.

# Earlier pilot validation — 8 October 2026

## Friend-testing release — 9 October 2026

- 40 automated checks pass on Python 3.12; both browser JavaScript files pass syntax checks. New checks cover independent reviewer records, expiry/revocation, feedback migration, atomic job claims, queued cancellation, queue capacity, streamed upload limits, category snapshots, retrieval balance and subtitle-window boundaries.
- The running Mac release uses multilingual faster-whisper **small** on CPU and **Qwen3 1.7B** with structured JSON selection. A fresh run of the official FunASR public Chinese sample completed without supplied subtitles. It transcribed “欢迎大家来体验达摩院推出的语音识别模型”, selected 0.56–5.36 seconds, and exported H.264/AAC at 720×1280. The exported SRT spans 0–4.80 seconds; the encoded file duration is 4.833 seconds.
- A second fresh run selected the 初测 knowledge category. Its saved evidence snapshot contains only the three 初测 cards, excluding the historical English demo category. Speech/selection model names and the effective prompt are saved in the manifest.
- Two authenticated clients through the live HTTPS tunnel saved distinct reviewer records on the same clip. HTTP Range playback returned 206 and the export bundle downloaded successfully. Chinese login, model/worker readiness, category controls and the completed clip were inspected in the actual browser; the 390px layout has no horizontal overflow and no browser console errors were observed.
- The first group test is hosted on this Mac through a temporary HTTPS tunnel. Local model files, access keys, recordings and machine-specific paths are excluded from Git. A Chinese guide and start/stop launchers are included in the release.

These are integration and browser-layout results for a short public sample. They do not certify long/noisy livestream editorial quality, physical phone behavior or sustained concurrent capacity. This is a shared-workspace beta for trusted friends, with manual review and publishing. Model explanations and knowledge references still need human checking.

## Verified

- **25 automated checks pass locally.** They cover SRT round trips and rebasing, invalid/out-of-range timings, subtitle-ID resolution, overlapping clips, English/Chinese knowledge retrieval, knowledge revisions and atomic imports, access controls, LLM correction retries and unknown references, safe handling of copied rule titles, media input restrictions, real FFmpeg rendering, delayed audio tracks, evidence snapshots, review persistence, exports and deletion.
- **GitHub Actions runs the same test suite and JavaScript syntax check on Linux/Python 3.12.** See the repository Actions tab for the exact commit and final status; no paid models are used in CI.
- **A real speech → knowledge → model selection → video render run succeeded.** Input was the public `jfk.flac` test fixture from the official faster-whisper repository, placed over generated test imagery. No client recording was used. The source was 12.208 seconds; the selected clip was 0–11 seconds, rendered as H.264/AAC at 720×1280 with rebased SRT. Both sides of the spoken comparison were included.
- Speech engine: faster-whisper 1.2.1, PyAV 16.0.1, tiny.en on CPU. Selection: real Qwen3 0.6B Q4_K_M, with strict JSON Schema output enabled. These small models verify integration, not production editorial quality.
- On this restricted development Mac, Ollama's default Metal path could not allocate GPU buffers. The real-model run used its installed llama.cpp runner with CPU-only flags through the compatible HTTP API. No cloud API was used.
- The model chose subtitle cue IDs. The backend derived exact intervals, checked durations/overlaps and validated knowledge references. A copied editorial-card title was replaced with an actual selected subtitle and marked `title_source: transcript` in the manifest.
- The browser interface was inspected at phone width (390 pixels; no horizontal overflow) and desktop width (1440 pixels). Knowledge creation, production status, video review controls and artifact links were inspected in the actual interface.

## What these results do not establish

This is a working pilot, not a finished cross-category production service. A 12-second speech sample does not establish selection quality, transcription accuracy on noisy Chinese livestreams, multi-hour performance, concurrent-user capacity or improvement from accumulated review data. Model scores are not calibrated probabilities.

Native Windows/macOS applications and Android/iOS app-store packages are not included. The interface is a responsive web app. Real-device phone testing, live OBS scenes, browser audio capture across operating systems and the Docker deployment recipe still require verification on their target environments. A publicly reachable phone service requires a running backend and HTTPS deployment; a private GitHub repository alone does not host video processing.

The knowledge base contains an editable demo editorial rule, not your product facts. Replace it with your initial category's verified content before judging results. Reviewer decisions are recorded, but knowledge changes require explicit approval through the interface; there is no silent model training.

## Next acceptance gate

1. Provide representative recordings and aligned reference subtitles where available.
2. Supply a narrow initial knowledge set and have reviewers label useful and unsuitable moments independently.
3. Choose a stronger local model on suitable hardware or a configured cloud Qwen/DeepSeek service.
4. Measure transcription error, boundary completeness, factual grounding, approval rate and reviewer time against held-out recordings.
5. Verify OBS capture/recovery, full-session processing and the target phones before exposing an HTTPS pilot to the team.

Public test-audio source: https://github.com/SYSTRAN/faster-whisper/blob/master/tests/data/jfk.flac

## Chinese localization verification — 8 October 2026

- 27 automated checks pass locally, including output-language validation, unchanged Chinese transcript/knowledge delivery to the LLM, and output-language policy in exported job manifests.
- The actual browser was checked in Chinese and English. Switching retains unsaved review decisions and notes. Chinese layouts were checked at 390px and 1440px; user cards and historical plan text remain unchanged.
- The running local pilot now loads multilingual Whisper tiny instead of tiny.en. A 5.547-second public Chinese sample completed speech → SRT → Qwen selection → H.264/AAC export in an isolated test workspace. The clip covered 0.56–5.16 seconds and included Chinese metadata. The tiny speech model misrecognized proper names in this sample, and selection reused that incorrect text. This proves pipeline connectivity, not adequate recognition accuracy; use the default multilingual small model or a stronger speech engine and review representative recordings before judging quality.
- The public sample is referenced by the [official FunASR HTTP example](https://github.com/modelscope/FunASR/blob/main/runtime/python/http/README.md). Test media and model downloads are not committed to the repository.
