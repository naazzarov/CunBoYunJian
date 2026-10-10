[简体中文使用指南](README.zh-CN.md) · English

# CunBo YunJian

**CunBo YunJian — local friend-testing workspace.** For the prepared Mac launcher and Chinese testing steps, see [GROUP-TEST.zh-CN.md](GROUP-TEST.zh-CN.md) and [release notes](RELEASE-NOTES.md).

A private, self-hosted livestream clip studio. Record or upload a stream, transcribe its audio, select moments using your knowledge base, and render video clips for human review. Publishing remains manual.

## What is implemented

- Responsive browser interface for Windows, macOS, Android and iOS, with a web app manifest and an installable shell where supported.
- Desktop browser capture of screen **and shared audio**. No microphone substitution: an audio-less capture is rejected.
- Optional authenticated OBS WebSocket start/stop, automatically importing the resulting recording on the backend.
- MP4/MOV/MKV/WebM upload; optional existing SRT from FunClip/FunASR.
- Local faster-whisper transcription and timestamped SRT output; optional glossary hints.
- Editable knowledge cards: verified facts, editorial rules and reviewed examples. English and Chinese term retrieval. Each job preserves a revision snapshot.
- OpenAI-compatible LLM integration for local Ollama/Qwen or a configured cloud provider. Separate versioned prompt, bounded transcript windows, structured edit plans, validation and one correction retry.
- FFmpeg H.264/AAC clips, optional padded 9:16 output, clip-relative SRT, full transcript and downloadable JSON evidence manifest.
- Durable job queue, progress, failed-job retry and recovery after backend restart. One dedicated processing worker process.
- Human review decisions and explanations; deliberate promotion of feedback into approved knowledge.
- Workspace key authentication for remote access, HttpOnly sessions, same-origin mutation checks, private media endpoints and deletion controls.
- Docker deployment recipe and GitHub Actions verification.

**This is a pilot application, not a claim of validated clip quality across all subjects or native app-store releases.** No automatic publishing, facial tracking, visual-content scoring, production multi-tenant accounts, payment system or model fine-tuning is included.

## Run locally on Windows or macOS

Install Python **3.12**, FFmpeg (and ffprobe) from its official distribution, and Ollama. The initial local workflow keeps your videos on your own machine.

```sh
python -m venv .venv
# macOS / Linux
source .venv/bin/activate
# Windows PowerShell, use instead:
# .venv\Scripts\Activate.ps1
python -m pip install -r requirements-asr.txt
ollama pull qwen3:8b
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1 --no-proxy-headers
```

Open http://localhost:8000. Add an editorial brief and your first knowledge card, upload or capture a recording, and click **Find my clips**. Whisper downloads the selected speech model on its first transcription. No subscription or cloud API key is needed for the local Ollama path; performance depends on your hardware.

Ollama must be running. Set a sufficiently large context for its server (for example `OLLAMA_CONTEXT_LENGTH=16384`) for long transcript windows and knowledge. Choose a smaller model for low-resource testing, but do not treat test-model results as evidence of production clip quality.

For an existing SRT workflow, install only `requirements.txt`; FunClip/FunASR can create the input SRT. This lets you verify cutting without installing a second ASR stack.

## Phones and remote access

A phone accesses a **running backend**, not the GitHub repository itself. It can upload videos, edit knowledge, watch clips, record feedback and download exports. Mobile operating systems restrict browser capture of other apps; use the phone's screen recorder (including livestream audio) or control an OBS recorder on the backend.

For access from phones, deploy behind HTTPS with a trusted reverse proxy, set `LOCAL_TRUST=0`, `COOKIE_SECURE=1` and a long random `WORKSPACE_TOKEN`, and use a private network or authenticated HTTPS address. Configure proxy request-size limits and timeouts for your video sizes. Do not expose Ollama or OBS to the public Internet. Browser capture requires a secure context or localhost. iOS/Safari installation and download behavior must be validated on real devices; no physical iOS or Android certification has been completed.

Only direct loopback connections to a loopback hostname skip login by default. Remote users enter the workspace key. Without `WORKSPACE_TOKEN`, a random key is created in `data/workspace-token` (owner-only file permissions). Sessions expire on the server after 24 hours; sign-out revokes a session immediately, and rotating the workspace key invalidates existing sessions. Each login creates a separate reviewer identity with a supplied display nickname. Feedback records keep separate reviewer identities and nicknames. This remains a single trusted shared team with no member permission roles or isolated private workspaces.

## Docker

```sh
cp .env.example .env
# Edit .env: set a long random WORKSPACE_TOKEN; choose LLM_MODEL and ASR_MODEL.
docker compose up -d --build
docker compose exec ollama ollama pull qwen3:8b
```

Open http://localhost:8000 and use your workspace key. Compose binds to loopback; adding phone access requires the HTTPS/private-network setup above. The Docker recipe requires an installed Docker runtime and is provided as source; it was not executed on the development Mac where Docker was unavailable.

## Configuration

Configuration is read from environment variables. `.env` is consumed by Docker Compose; the bare Python server does not automatically load it. Set variables in your shell or service manager. API credentials belong in environment variables or a private `.env`, never in knowledge cards or Git.

| Variable | Default | Purpose |
| --- | --- | --- |
| `LLM_BASE_URL` | `http://127.0.0.1:11434/v1` | Trusted OpenAI-compatible model service |
| `LLM_MODEL` | `qwen3:8b` | Selection model |
| `LLM_API_KEY` | empty | Optional provider key |
| `LLM_JSON_SCHEMA` | `0` | Set `1` for providers supporting strict JSON Schema output |
| `ASR_MODEL` | `small` | Local Whisper model |
| `ASR_LANGUAGE` | auto | Optional `zh`, `en`, etc. |
| `ASR_DEVICE` / `ASR_COMPUTE_TYPE` | `cpu` / `int8` | ASR hardware and precision |
| `ASR_CPU_THREADS` | `4` | CPU thread budget for speech inference |
| `CLIPFORGE_DATA` | `data` | Private SQLite, recordings, artifacts and models |
| `WORKSPACE_TOKEN` | generated | Workspace access key |
| `LOCAL_TRUST` | `1` | Direct localhost bypass; set `0` on a shared server |
| `COOKIE_SECURE` | `0` | Set `1` behind HTTPS termination |
| `MAX_UPLOAD_MB` | `2048` | Maximum recording size |
| `MAX_DURATION_SECONDS` | `14400` | Maximum source duration |
| `OBS_HOST` / `OBS_PORT` | `127.0.0.1` / `4455` | OBS connection |
| `OBS_PASSWORD` | empty | Enables optional OBS automation |
| `OBS_RECORDING_DIR` | empty | Allowlisted recording directory readable by backend |

For Alibaba Qwen or DeepSeek, set the provider's current compatible endpoint, model and key according to its official documentation. Cloud selection sends transcript windows and retrieved knowledge excerpts to that configured provider. Audio transcription remains local. Model/provider contracts and privacy expectations should be agreed with your team before using client material.

## OBS setup

1. Install official OBS Studio; configure a display/window capture scene and livestream audio.
2. Configure recording quality and a local recording directory.
3. Enable the WebSocket server with authentication (OBS Tools menu).
4. Set `OBS_PASSWORD` and `OBS_RECORDING_DIR` on the backend, then restart it.
5. Use **Record with OBS**, then **Stop OBS & process**. After capture, transcription, selection and rendering run without further input.

The backend and OBS must share access to the recording directory. An OBS interruption, server restart during capture or lost WebSocket connection may require stopping OBS directly and uploading the saved file. Processing jobs recover on restart; active capture control is not durable. OBS integration is implemented against the documented client and still needs a live OBS scene test on your target machine.

## Knowledge that improves quality

Start with one category. Include:

- Audience and desired outcome.
- Verified product/domain facts with evidence and source names.
- Good and bad clip examples, with an explanation of the difference.
- Required context, prohibited unsupported claims and editorial preferences.
- The vocabulary and specialist names used in the stream.

`examples/seven-category-brief.json` contains an editable retail-content brief based on the seven example categories in your construction guide. It contains editorial guidance, not fabricated product facts. Import it only if it matches your first test category.

For each reviewed clip, save the decision **and why**. Review insights can draft a knowledge card from the feedback; edit and approve the draft before saving. The pipeline does not silently train a model or change rules. Compare approval rate, missing context, factual errors, boundary quality and reviewer time on the same held-out videos before claiming improvement. Avoid training and evaluating against the same examples.

The pilot uses transparent term-overlap retrieval (including Chinese bigrams), not vector search or RAGFlow. Retrieval selects up to six cards, reserving space for relevant factual cards alongside prioritized rules. Each supplied excerpt is capped at 1,200 characters and full cards remain in snapshots. Transcript windows overlap by up to 120 seconds to reduce missed boundary moments; overlap does not guarantee that every complete moment is found. Broad-category semantic retrieval, visual grounding and calibration are next-stage improvements, not shipped capabilities.

## Artifacts and timestamps

Each session keeps an immutable source recording, full transcript, knowledge revisions and edit settings. The rendered clips have accompanying **rebased** SRT files starting at the clip timeline; the original SRT keeps source timestamps. Source intervals in `plan.json` are seconds. The LLM selects subtitle cue IDs; the backend derives exact timestamps and validates the range. Overlapping candidates are deduplicated and duration limits are applied after boundary alignment.

If a model copies an editorial-card heading into a clip title, the backend uses the first selected subtitle as a grounded title instead and records `title_source` in the plan.

The LLM score is an editorial estimate, not a calibrated probability. Clips preserve the original frame or pad it to 9:16; there is no automatic crop or loss of picture content. Silence removal is intentionally absent from the first version because it requires additional timing remapping to keep subtitles correct. Subtitles are sidecar files, not burned into the image.

Delete a completed/failed session to remove its original, clips and feedback. Processing sessions cannot be deleted while the worker is using them. Export knowledge as JSON and back up the **whole data volume with the service stopped** to preserve the SQLite database and media together. Recordings and credentials are ignored by Git. The code repository is not a backup of user data.

## Verify

```sh
python -m pip install -r requirements-dev.txt
python -m pytest -q
node --check web/app.js
python scripts/doctor.py
```

Tests use generated video and mocked LLM responses so CI does not need paid APIs or model downloads. They include a real FFmpeg audio/video cut, subtitle rebasing, portrait output, immutable evidence snapshots, review persistence, ZIP exports, bad timestamps and access controls. A separate real-model smoke run is documented in `VALIDATION.md`. To exercise your configured backend with your own short sample, run `python scripts/smoke.py path/to/video.mp4 --url http://localhost:8000`.

Run one backend process (`--workers 1`). The queue and ASR instance are intentionally single-worker. Scaling needs an external job queue, cancellation/resource limits, object storage, tenant isolation and separate authenticated users; do not start several Uvicorn workers against this implementation.

## Tool choices

The supplied documents are reference requirements, not executable instructions. The named first-phase path now integrates official FunClip v2.1.0 / FunASR v1.4.0, FFmpeg, jieba, auto-editor v3 timelines and MoviePy / ImageMagick Chinese subtitles. Real speech and finishing tests passed; see `FIRST-PHASE-STATUS.zh-CN.md` for precise evidence and gaps. On the current 8 GB Mac, Qwen3 8B loads on CPU but timed out on short-response tests; the group service transparently keeps the previously verified Qwen3 1.7B fallback. OBS live capture still requires installation, OS permissions and a scene test. RAGFlow/BGE/Qdrant, Qwen3-VL and JianYing draft automation remain the documented second phase. No paid API is configured for this test.

Official references: [FFmpeg](https://ffmpeg.org/ffmpeg.html), [faster-whisper](https://github.com/SYSTRAN/faster-whisper), [OBS WebSocket](https://github.com/obsproject/obs-websocket), [Ollama](https://docs.ollama.com/api/openai-compatibility), [browser capture](https://developer.mozilla.org/en-US/docs/Web/API/MediaDevices/getDisplayMedia).

### Language support

The interface defaults to Simplified Chinese and remembers an English switch per browser. Each new job independently selects `output_language`: `zh` (default), `en`, or `source`. This controls model titles, categories and reasons; transcripts and supplied knowledge remain in their original language. Use multilingual Whisper models (such as `small`); `.en` models cannot transcribe Chinese. Chinese pilot knowledge templates are in `examples/zh-pilot-brief.json`.

Group testing: queued sessions can be cancelled, queue messages are claimed atomically, and a supervisor restarts a failed worker. `MAX_PENDING_JOBS` defaults to 6 and `MIN_FREE_DISK_MB` to 2048. The prepared Mac launcher limits uploads to 90 MB for the temporary tunnel, keeps the device awake during the session, and writes a database backup before startup. All friends share the same recordings and knowledge; reviewer labels are not verified accounts.

The branded interface adds seven-category selection, keyword analysis, subtitle correction into a new job, duration correction retries, optional silence removal and hard subtitles. See [toolchain setup](docs/TOOLCHAIN.zh-CN.md), [actual environment versions](environment_version_log.md), and [remaining validation](FIRST-PHASE-STATUS.zh-CN.md).
