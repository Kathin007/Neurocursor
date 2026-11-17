# NEUROCURSOR: Progress

Carry-forward context for new sessions. Updated after every milestone.

## Current state: M4 complete; vision wired into the UI. M5 SKIPPED by the user (simulation only for an assignment).

### UI wiring of the vision engine (after M4, user request)
- **Calibration > Vision tab**: Start/Stop camera (real MJPEG preview via `/api/vision/preview.mjpg`), **Calibrate** opens a full-screen 9-dot overlay that drives `POST /api/vision/calibrate` (start, capture x9 with settle time and automatic retry on 408, finish), then shows the **measured held-out error**, per-point errors and an honest verdict (good <5% of screen width, fair <12%, else poor with advice). Save profile / Recalibrate / Done. Esc cancels (calls cancel on the backend).
- **Live** (the old Vision Control Room, now real): camera panel, measured readouts, click log, tuning controls pushed to the running engine over the WebSocket (`set_vision_config`, debounced), Pause/Resume via REST, and **Open live stage**: full-screen stage with six tiles, the simulated cursor from `cursor_update`, the raw-gaze ring, a dwell progress ring, closed-eye state, click ripples, and an accepted click presses the tile under the cursor (hit-test in normalized coordinates).
- Data labels come from the backend's `status.source` (never hardcoded). Neural tab and Analytics remain DEMO_DATA.
- Shared state: one `useVisionSession` in App (status polled every 2 s), per-screen `useVisionTelemetry` (events folded into a snapshot, pushed to React at most every 50 ms). `useBackend` no longer stores events in React state (that would re-render the app ~60x/s) and fans events out to subscribers that may register before the socket exists.
- The old "EMERGENCY STOP" button on the vision screen was removed (it only changed local state). The backend safety stop has no REST route yet (contract decision, was planned for M5).
- **Verified:** 83 vitest tests (overlay flow, retries, Esc/cancel, live stage cursor/gaze/dwell/blink/tile-press, rejected clicks, controls over WS, no DEMO_DATA on real screens, label from backend). **End-to-end in headless Edge via DevTools** against the real backend service and real UI, with a SCRIPTED camera/face (labelled DEMO_DATA, the badge shows it): Start camera -> preview decoded in the browser (640x480) -> Calibrate (9 dots) -> result card -> Save profile (profile 1 shown) -> Live stage -> cursor appeared, tile C pressed twice (one DWELL, one BLINK), Esc closed it, zero console errors/warnings. The 0 px error in that run is the scripted perfect face, NOT an accuracy result.
- **NOT verified:** the same flow with a real face on your webcam (I cannot look at the dots for you), browser Fullscreen behaviour in a normal window (headless Edge only), and real accuracy. Your real CLI calibration earlier gave 930 px held-out error (poor); the UI will show the real number and say "poor" if so.

### M4 (EEG engine) summary

### M4 summary
- **Built (backend only; the frontend is unchanged and still DEMO_DATA until M5):** `eeg/` (acquisition, simulator, device_manager, preprocessing, artifact_detection, signal_quality, feature_extraction, ssvep_classifier, motor_imagery stub, pipeline, service, evaluation), `control/neural_commands.py`, `api/routes_eeg.py`, per-mode click floors in `SafetyManager`.
- **No EEG hardware exists here.** Nothing REAL_EEG was ever run. Every number below is on `SYNTHETIC_EEG` / `RECORDED_EEG` that I generated.
- **BrainFlow 5.24.0 works on Python 3.12.** Verified: its synthetic board (16 ch, 250 Hz) and its playback board (replays a file in real time; a 12 Hz tone written to a file came back at 12.1 Hz).
- **BrainFlow's synthetic board has no usable SSVEP ground truth:** channel k is a fixed sine at 5k Hz (5, 10, 15 ... Hz), which lands exactly on the Down (10 Hz) and Right (15 Hz) targets and cannot be changed. So ground truth comes from our own injectable `SSVEPSimulator` (`SYNTHETIC_EEG`), and a BrainFlow-native path comes from playback of a known-frequency file we generate (`RECORDED_EEG`).
- **Pipeline:** causal 5-40 Hz Butterworth + 50 Hz notch (mains frequency configurable) -> 2 s sliding windows every 0.25 s -> amplitude/flat/railed artifact check (bad channels excluded, window rejected if <3 good) -> CCA against sin/cos at f and 2f for each target (numpy QR/SVD; cross-checked against scikit-learn CCA in a test) -> reject if winner < `min_confidence` or margin < `min_margin` -> command only after N=3 consecutive agreeing accepted windows (movement targets repeat every N windows while attention is held; Select fires once until the streak breaks) -> `NeuralCommandMapper` -> `CommandRouter` -> shared `CursorEngine`.
- `confidence` is the winning CCA correlation, NOT a probability. Neural click floor = the classifier's `min_confidence` (per-mode floor in `SafetyManager`; the vision floor stays 0.6).

### M4 measurements (SIMULATOR ONLY; run `python -m backend.eeg.evaluation`)
Simulator defaults: SSVEP 3 uV (+ 2nd harmonic), noise ~10 uV/channel, alpha 1 uV at 10 Hz, 50 Hz mains 1 uV, 250 Hz, 8 channels (occipital-weighted). **These are my assumptions, not properties of real EEG.**
- **Offline classification accuracy (single windows, 100 trials per target, argmax before rejection):** 1 s window 80.8%, **2 s 98.4%**, 3 s 100%. With rejection at the 2 s defaults: 53.6% of windows accepted, 100% correct among those, noise-only false-accept 0.5%.
- **Window-length matters for the threshold:** at 1 s the noise-only false-accept rate is 45% with the 2 s thresholds, so thresholds are window-specific.
- **Alpha confound (offline accuracy at 0 / 1 / 2 / 4 uV of 10 Hz alpha):** 99.5% / 98.5% / 86.5% / **20% (chance)**. The first simulator I wrote had 4 uV alpha and scored chance; the classifier was fine, the scenario was swamped. 10 Hz is a real alpha frequency, so the Down target is the weak point on real people.
- **Online control (full pipeline, 3 consecutive windows, 6 s of attention per target, 10 seeds pooled = 80 segments, 6.7 min of rest):** segment success **67.5%** (54/80; per-session range 12.5% to 100%), median time to first correct command **3.25 s** (p90 4.9 s), 0 wrong-target commands, 7 false activations at rest = 1.05/min **of which all 7 were carry-over** (fired within about 2.5 s after the attended target ended, while the 2 s window still held it) and **0 spurious** in 6.7 min. Pipeline step cost median about 4.5 ms.
- **Reading these honestly:** the winning-correlation median at 3 uV (~0.66) sits at the 0.65 threshold, so about half the windows pass; consecutive windows overlap 87.5%, so passes come in streaks and a session's success depends heavily on its noise realisation (hence the 12.5% to 100% spread). Thresholds were set from the simulator's noise-only distribution (null p99 about 0.63) and MUST be re-tuned on real recordings. I did not tune them to flatter the success rate.
- Offline and online numbers are separate by design and must not be merged.

### M4 decisions / additions beyond the written API contract (need approval)
1. `POST /api/eeg/connect` takes a body (`kind` + parameters). `POST /api/eeg/start` takes an optional config body.
2. WebSocket client message `{"type":"set_synthetic_target","hz":...}` to move the simulator's ground truth (valid only for `injected_synthetic`).
3. Starting EEG sets NEURAL as the active control mode; starting vision sets VISION. One mode drives the cursor at a time; the other's commands are rejected ("mode not active").
4. Still no REST route for emergency stop or OS-cursor opt-in (M5, needs contract approval).
- Filter: causal streaming filter for live use; zero-phase only in offline evaluation.
- No raw EEG is stored (test asserts nothing is written to disk). `eeg_update` carries only a ~150 ms filtered preview per channel.
- Device silence for 3 s (configurable) -> state ERROR, control paused, `device_status` error event.
- MNE-Python was not used (offline analysis only; nothing needed it yet). LSL not added (no device needs it).
- Dependency added: `brainflow==5.24.0`.

### M4 untested / not done
- **Everything on real EEG.** No REAL_EEG device, no real recording, no human data: real SSVEP accuracy, real artifact behaviour, real alpha/line-noise levels and the thresholds are all unknown. `brainflow_real` is unexercised code.
- Display-refresh validation of SSVEP frequencies stays in the UI (real, M2). The backend does not check stimulus frames; it only checks that harmonics stay inside the pass-band and targets differ by 0.5 Hz.
- Real stimulus-presentation timing (the UI flicker driving real EEG) is untested end to end.
- Motor imagery: documented stub, `NOT_IMPLEMENTED`, never claimed.
- Frontend not wired to EEG telemetry (M5).

### M3 real-user calibration result (user-run on their laptop, 2026-11-10)
`python -m backend.vision.cli calibrate` on a 1920x1200 screen, 209 samples over 9 points: **held-out (leave-one-point-out) error mean 930 px, worst 1788 px; training error 556 px; linear model, alpha 10.** Per point: 1788, 458, 1375, 1008, 187, 908, 1227, 482, 940 px. That is **poor**: the cursor is not usable for pointing at this accuracy. Even the training error is large, so the 5 features do not separate the 9 gaze points on this person/setup.
- Not yet diagnosed. Candidate causes (UNVERIFIED): small iris-ratio dynamic range at 640x480; head movement during capture; eyes not yet settled on the dot; the generic head-pose model; iris landmark noise. The per-point feature spread would show which, and the raw samples are not stored by design.
- `live`: dwell and blink clicks did fire on a real face; blink clicks with quality 0.36 and 0.44 were correctly rejected by the 0.6 floor; accepted ones had 0.72-0.85. This shows the click logic works on real data, NOT that the cursor lands where the user looks.
- Ctrl+C in `live`/`calibrate` printed a traceback; now handled ("interrupted", exit 130). Esc only works when the OpenCV window has focus.

### M3 summary
- **Built (backend only; the frontend is unchanged and still DEMO_DATA until M5):** `vision/` (camera, face_landmarks, head_pose, gaze_estimation, blink_detection, calibration, gaze_smoothing, pipeline, service, config, cli), `control/` (safety_manager, cursor_engine incl. SimulatedCursor/OSCursor, click_engine, dwell_controller, smoothing, command_router), `db/` (SQLite calibration profiles), `api/routes_vision.py`.
- **Real hardware verified (this laptop, Integrated Camera = index 0, 640x480):** capture about 27-29 fps; MediaPipe found a face in 90/90 and 273/273 frames; the backend labelled it `REAL_WEBCAM`; the MJPEG preview returned real JPEG data; the camera was released on stop (restart succeeded).
- **Not verifiable by me:** gaze accuracy on a real person. That needs a human looking at 9 dots. Run `python -m backend.vision.cli calibrate`; its held-out error is the first real accuracy number. No accuracy is claimed.

### M3 decisions
- **Features (5):** iris-relative-to-eye-corner ratios (h, v; both eyes averaged in image direction) + head-pose yaw/pitch/roll (solvePnP on 6 landmarks, scipy Rotation). Iris position alone is not used.
- **Calibration:** ridge regression, degree 1 or 2, alpha grid; chosen by **leave-one-point-out held-out error** (the reported number). Per-point outliers dropped by MAD. Profiles are stored as JSON parameters in SQLite (no pickle, no images).
  - Finding: with 9 points and 5 features, degree-2 (20 terms) badly overfits under leave-one-point-out (about 500+ px on synthetic nonlinear data), so linear is normally chosen. Corner points need extrapolation, so held-out error is deliberately pessimistic.
- **Smoothing:** `P(t)=a*P_new+(1-a)*P_prev`, a adaptive to speed. First version measured raw frame-to-frame jump, so jitter looked like movement and defeated the smoothing (caught by a test). Now uses a low-passed velocity vector (One-Euro style); default speed_ref 1.5 screens/s.
- **Blink click:** EAR threshold with hysteresis, min 60 ms, max 400 ms, refractory 500 ms; fires once on reopening. Closures over max are "prolonged" and never click. Click confidence is taken from the last open-eye frame (quality is 0 while the eye is closed).
- **Gaze quality** (the `confidence` on clicks) is a heuristic 0-1 score (eye openness x head-turn), NOT a calibrated probability.
- **Safety enforced in code:** states ACTIVE/PAUSED/STOPPED (stop needs explicit rearm, which lands paused); non-finite or >25% off-screen estimates rejected, other overshoot clamped to [0.01, 0.99] (never the corner, where the PyAutoGUI failsafe lives); click confidence floor 0.6; duplicate-click lockout 600 ms; camera loss pauses control.
- **OSCursor** cannot be constructed without a session-scoped opt-in token; pyautogui is imported lazily only then; FAILSAFE is forced True. **No API route can select it in M3.**
- Fake camera / scripted detector in tests are labelled `DEMO_DATA`, never `REAL_WEBCAM`.
- Mode gating: `CommandRouter` only accepts commands from the active mode.
- Model file `face_landmarker.task` (3,758,596 bytes, sha256 `64184E229B263107BC2B804C6625DB1341FF2BB731874B0BCC2FE6544E0BC9FF`) fetched once from `storage.googleapis.com/mediapipe-models/...`; git-ignored.
- Deps added (all in stack): opencv-contrib-python 5.0.0.93 (mediapipe's requirement; `opencv-python` removed to avoid a `cv2` clash), mediapipe 1.2.2, numpy 2.5.4, scipy 1.18.1, scikit-learn 1.9.1, pyautogui 0.9.54 (+ its small deps).

### M3 additions that go beyond the written API contract (need approval; flagged in the report)
1. `GET /api/vision/preview.mjpg`: the "separate MJPEG endpoint" (path not specified in the brief).
2. `POST /api/vision/calibrate` takes a `step` body (`start|capture|finish|save|cancel|load`), and `POST /api/vision/start` an optional body.
3. WebSocket client message `{"type":"set_vision_config","config":{...}}` for live tuning (the REST list has no settings route). Replies via a `system_log` event.
4. No REST route yet for emergency stop or OS-cursor opt-in (safety logic exists and is tested; the routes need contract approval and arrive in M5).

### M3 measurements (real, this machine; see report for commands)
- Capture 27-29 fps. Service-reported tracking fps 27.1, capture-to-publish latency median 34.7 ms / p95 41.2 ms, processing median 34.5 ms (gaze_update `proc_ms`).
- Landmark detection alone measured 15 ms (first probe), 19 ms, 30-31 ms (later runs): it varies run to run on this laptop with no explanation yet. Worker-thread vs main-thread timing was inconclusive. Systematic profiling is M6.
- First `start` took 21 s (DirectShow open about 5 s + MediaPipe import/model load); a restart took 2.3 s. The UI must show a "starting" state.
- Process CPU for the standalone loop was about 73-115% of one core. The service-level CPU was not measured (my attempt measured the venv launcher stub; discard it).
- This user's open-eye EAR median was 0.24-0.28 against the default blink threshold 0.2: thin margin, per-user tuning needed.

### M3 untested / not done
- Gaze accuracy on a real person, and the `calibrate` / `live` CLI modes (need a human at the screen; written, never run).
- Real blink and dwell clicking on a real face (tested only with scripted landmarks that have known ground truth).
- The IR camera (index 1) is not accessible through DirectShow; not used.
- Frontend is not wired to any of this (M5). Emergency-stop route, global hotkey, recording opt-in, session recording (M5).
- OSCursor was never run against the real mouse (forbidden without your go-ahead); tested only against a fake pyautogui.

**Scope decision (user, after M1):** Rust and Tauri are not needed for M1 to M4. Those milestones run in the browser (React/Vite on Node) plus the Python backend. Tauri packaging is M5, and Rust and MSVC are only needed then.

### Environment (inspected 2026-11-10)
- Windows 11 Home 10.0.26300. Display refresh reported by Windows: 59 Hz (Intel Arc).
- Python: 3.13.13 (default), 3.12.8, 3.10 installed. **3.11 absent.** Project venv uses **3.12.8** (`.venv`).
- Node v26.13.0, npm 11.20.0. TypeScript 7.x (`baseUrl` removed, so `paths` only), Vite 8, Vitest 5, React 19.
- Rust/cargo and MSVC Build Tools are missing. WebView2 is present. Not needed until M5.
- Webcam: Windows enumerates `Integrated Camera` and `Integrated IR Camera`. Opening a device is untested (needs OpenCV, M3).

### Decisions (M1)
- Python 3.12 instead of 3.11 (closest available).
- Event timestamps are epoch milliseconds (float) everywhere.
- Round-trip check: client `{"type":"ping","id"}`, answered by a `system_log` event with `message:"pong"`. The contract's event list was not changed.
- `TelemetryEvent.source` is `DataSource | null`. A validator rejects bytes and `data:image` in payloads.
- Slow WebSocket consumers: per-client bounded queue (64) drops the oldest event; publishing never blocks.
- Backend tests use a live uvicorn thread plus `websockets` and `urllib` (no `httpx`).
- CORS is off. The browser uses the Vite proxy; M5 must add CORS or another transport for the Tauri origin.
- Vite dev port fixed at 5173.

### Decisions (M2)
- **Stack additions installed:** `tailwindcss` + `@tailwindcss/vite` (v4), `motion`, `recharts`, `three`, `@react-three/fiber`, `shadcn` (CLI) with generated `button`, `slider`, `switch`, `tabs`.
- **shadcn side effects (dependencies the shadcn CLI added, not individually chosen):** `@base-ui/react` (primitives for this shadcn style), `class-variance-authority`, `lucide-react`, `tw-animate-css`, `@fontsource-variable/geist` (self-hosted font, no cloud), and `cn` (a published class-merge library; this shadcn version imports it as `from "cn"` in the generated components and in `src/lib/utils.ts`).
- No router. Navigation is state plus a hash deep-link (`#/welcome|calibration|vision|neural|analytics`).
- **Folders:** `src/design/` shared design system (Panel, Readout, Meter, StatusDot, EmptyState, SourceBadge, Controls, DemoFace); `src/screens/<screen>/`; `src/demo/` the only place DEMO_DATA is generated; `src/lib/` real logic.
- **Real vs demo.** Real, measured in the browser: backend REST status, WebSocket state and ping RTT, camera device count (enumerate only; the camera is never opened), camera permission state, WebGL availability, display refresh rate (from `requestAnimationFrame`), SSVEP frame-compatibility and harmonic-overlap validation. DEMO_DATA: gaze/cursor/blink/dwell, face preview, calibration error, EEG waveform/spectrum/quality/decisions/history, confusion matrix, all Analytics rows.
- Every demo panel carries a `DEMO_DATA` badge (`data-source="DEMO_DATA"`, amber). Tests assert each demo screen has one.
- Analytics aggregation (`lib/analytics.ts`) is pure and returns `null` with no sessions, so the UI shows an empty state instead of zeros. M5 reuses it over SQLite events. Offline EEG accuracy and online success rate are separate fields and never merged. CSV rows carry a `data_source` column and the file name says DEMO_DATA.
- The browser never opens the camera. The backend owns it (M3) and serves video on a separate MJPEG endpoint.
- Stimulus flicker is **off by default** with a photosensitivity warning and is disabled under `prefers-reduced-motion`.
- Welcome background: React Three Fiber network (lazy-loaded chunk). It starts static if WebGL is missing or reduced motion is requested, and drops to a static CSS background if the measured frame rate is below 45 fps.
- Default Select frequency is 6.67 Hz (9 frames at 60 Hz, no 2nd-harmonic collision with the other four). It is configurable.

### What works (evidence in the M2 report)
- All five screens render from `npm run dev` (headless Edge screenshots, no console errors).
- Vitest: 8 files, 56 tests. `tsc -b`, `vite build`, pytest unchanged from M1 and passing.

### Untested / not done
- **60 fps on the target laptop is not measured.** Only the fallback logic exists. Headless Edge cannot judge frame rate.
- **Real-GPU rendering of the WebGL background** was seen only in headless Edge software rendering.
- Browser console in an interactive session was not inspected (headless run only). It showed Vite/React INFO lines and one third-party warning: `THREE.Clock: This module has been deprecated` (from three@0.187 with @react-three/fiber 9.8.2).
- Headless Edge reported a ~30 Hz refresh rate, so frame-compatibility warnings seen in screenshots reflect that, not this laptop's display. The validation follows the measured rate by design.
- Camera enumeration/permission showed "pending"/"prompt" in headless runs; behaviour on a real session is unobserved.
- Emergency stop, pause/resume, sliders and switches change local UI state only. No backend wiring, no global hotkey (M3/M5).
- Tauri shell (files only, never compiled). Webcam access, display-refresh use in the backend, all vision/EEG/cursor/db code (M3 to M5).
- OSCursor opt-in test: nothing to test until M3.
- Lint: 2 upstream shadcn warnings (`only-export-components` in `button.tsx`, `tabs.tsx`) left as generated.

### Known limitations
- Main JS chunk is about 883 kB (Recharts, Motion, base-ui); the three.js chunk is about 918 kB and loads only when WebGL is available. No code-splitting beyond that.
- Calibration "Save profile" is a no-op (demo). Profiles persist to SQLite in M3.
- Incident: while running a command in M2 I accidentally deleted `frontend/src/lib/telemetry.test.ts`. It was restored verbatim from the earlier version and the test count confirmed (8 files).
- `frontend/README.md` is still the Vite template text; Tauri icons are placeholders.

### Remaining milestones
M3 Vision engine, M4 EEG engine, M5 Integration (+Tauri packaging, needs Rust + MSVC), M6 Validation.
