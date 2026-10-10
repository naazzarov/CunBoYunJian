# 1.0.0-beta.1 — 9 October 2026

Group-testing release for one trusted shared workspace hosted on a Mac.

- Separate reviewer sessions and feedback; previous records migrate without losing their notes.
- Server-enforced session expiry and sign-out revocation; bounded failed-login attempts.
- Upload body limits before multipart parsing, simultaneous-upload limits, storage checks and an atomic queue cap.
- Atomic worker claims prevent duplicate queue messages from rerunning a finished job. Persistent queued jobs remain discoverable if an in-memory message is missed. Interrupted jobs recover and a dead processing worker is restarted.
- Cancel queued sessions; inspect real model connectivity, worker status and storage in the interface.
- Select a knowledge category plus general rules; each job preserves its scoped evidence snapshot.
- Overlapping transcript windows reduce missed moments at boundaries. Retrieval reserves space for relevant facts alongside editorial rules. Bounded card excerpts retain full versions in evidence snapshots.
- Mac group-test launcher starts the local services, backs up SQLite, prints a protected HTTPS link and prevents idle sleep while running. Double-click start/stop commands and a Chinese tester guide are included.

Validation: 40 automated checks and JavaScript syntax checks pass locally. A fresh Chinese audio-to-clip run used multilingual Whisper small and Qwen3 1.7B; HTTPS reviewer separation, video seeking and bundle downloads were also verified. See VALIDATION.md for scope and limits.

Shared workspace keys grant access to all group recordings and knowledge. Reviewer nicknames are labels, not independent verified accounts. The temporary link requires the Mac and launcher to stay online. Native phone packages, permanent cloud hosting and broad-category quality certification are outside this release.
