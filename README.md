# NEUROCURSOR

*Beyond Touch. Beyond Input.*

Desktop app with two independent input modes feeding one cursor engine:

- **VISION**: webcam gaze control (computer vision, **not** a BCI).
- **NEURAL**: EEG SSVEP control (the only mode that is BCI).

Status: **M4 EEG engine + vision wired into the UI** (M5 skipped by choice: simulation only) (backend SSVEP pipeline on synthetic/recorded EEG, plus the M3 webcam vision pipeline; the UI still shows DEMO_DATA until M5). M1 to M4 run in the browser with the Python backend; Rust/Tauri is only needed from M5. See [docs/PROGRESS.md](docs/PROGRESS.md) for what works, what is untested and what remains.

## Prerequisites

| Tool | Used for | Version tested |
|---|---|---|
| Python 3.12 (3.11 preferred; 3.13 not yet verified against MediaPipe/BrainFlow) | backend | 3.12.8 |
| Node + npm | frontend | Node 26.13.0, npm 11.20.0 |
| Rust + MSVC Build Tools + WebView2 | Tauri shell (M5) | **not installed on the dev machine; Tauri is untested** |

## Setup (Windows PowerShell; run from the repo root)

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
cd frontend; npm install; cd ..

# One-time: MediaPipe Face Landmarker model (about 4 MB, from Google's model bucket; git-ignored).
# The app never downloads anything at runtime.
New-Item -ItemType Directory -Force backend\vision\models | Out-Null
Invoke-WebRequest "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task" -OutFile backend\vision\models\face_landmarker.task
```

`mediapipe` requires the contrib build of OpenCV (`opencv-contrib-python`). Do not also install `opencv-python`: both provide `cv2` and clobber each other.

## Run: one command per layer

| Layer | Command | Result |
|---|---|---|
| Backend | `.\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000` | REST + `/ws/telemetry` on :8000 |
| Frontend | `cd frontend; npm run dev` | http://localhost:5173 (proxies `/api` and `/ws` to :8000) |
| Desktop | `cd frontend; npm run tauri dev` | **Requires Rust + MSVC; untested** |

Start the backend first, then the frontend, then open http://localhost:5173. Screens can be opened directly: `#/welcome`, `#/calibration`, `#/vision`, `#/neural`, `#/analytics`. Anything badged **DEMO_DATA** is a scripted placeholder; readiness checks on the Start screen are measured live.

## Using the UI (simulation only)

Run the backend and the frontend (above), open http://localhost:5173, then:

1. **Calibration** -> **Start camera** (turns on your webcam; the first start takes up to ~20 s).
2. **Calibrate**: the screen goes full-size and shows 9 dots. Look at each with your eyes only, head still. You get the **real measured held-out error** and a verdict; **Save profile** (or **Recalibrate**).
3. **Live** -> **Open live stage**: a full-screen stage with six tiles. A **simulated** cursor follows your gaze; **hold still** (dwell ring) or **blink once** to press the tile under it. Esc exits.

The cursor is always simulated and never touches your real mouse. The Neural tab and Analytics still show DEMO_DATA.

## Vision engine from the command line (M3)

```powershell
.\.venv\Scripts\python.exe -m backend.vision.cli probe       # opens the webcam ~3 s: measured fps, detection rate, EAR, timings. Saves nothing.
.\.venv\Scripts\python.exe -m backend.vision.cli calibrate   # full-screen 9-point calibration, prints held-out error, saves a profile
.\.venv\Scripts\python.exe -m backend.vision.cli live        # gaze -> SimulatedCursor with dwell/blink clicks (Esc quits)
```

Through the API: `POST /api/vision/start`, then `POST /api/vision/calibrate` with `step` = `start`, `capture` (per `point_index`), `finish`, `save`;
`GET /api/vision/preview.mjpg` for the preview; telemetry arrives on `/ws/telemetry`. The cursor is **always simulated**: nothing in the API can
select the real OS cursor. Starting vision turns the camera on (the camera LED will light); stopping releases it.

## EEG engine without a headset (M4)

No headset is needed or assumed. Sources, each labelled in code and in every telemetry event:

| `kind` for `POST /api/eeg/connect` | Label | What it is |
|---|---|---|
| `injected_synthetic` (default) | `SYNTHETIC_EEG` | Our simulator with a settable ground-truth SSVEP target (WebSocket `{"type":"set_synthetic_target","hz":12}`) |
| `brainflow_synthetic` | `SYNTHETIC_EEG` | BrainFlow's own board: fixed tones at 5k Hz per channel, no SSVEP ground truth |
| `playback` (`file`) | `RECORDED_EEG` | BrainFlow playback of a BrainFlow-format file |
| `brainflow_real` (`board_id`, `serial_port`) | `REAL_EEG` | A real headset. **Never tested here.** |

Flow: `connect` -> `start` (optional body: targets, window, thresholds) -> telemetry (`eeg_update`, `classification_update`, `interaction_event`) -> `stop` -> `disconnect`.
Starting EEG makes NEURAL the active control mode; the cursor stays simulated.

```powershell
.\.venv\Scripts\python.exe -m backend.eeg.evaluation   # measures offline accuracy and online control on the simulator (about 1 min)
```

## Test

```powershell
.\.venv\Scripts\python.exe -m pytest -q     # backend (repo root)
cd frontend; npm test                       # vitest + React Testing Library
cd frontend; npm run typecheck; npm run lint; npm run build
```

## Layout

```
backend/    FastAPI app: api/ vision/ eeg/ control/ db/
frontend/   Vite + React + TypeScript (strict); src-tauri/ holds the Tauri scaffold
tests/      pytest suites (frontend tests sit beside the code as *.test.ts[x])
docs/       PROGRESS.md (carry-forward context)
```

## Contracts defined so far

- Data-source labels (`backend/api/schemas.py`, mirrored in `frontend/src/lib/telemetry.ts`): `REAL_WEBCAM`, `REAL_EEG`, `SYNTHETIC_EEG`, `RECORDED_EEG`, `DEMO_DATA`.
- Telemetry envelope: `{type, timestamp (ms since epoch), source, payload}`. Camera frames are rejected by a validator and never travel over this socket.
- WebSocket client messages: `{"type":"ping","id":N}` is answered with a `system_log` event whose payload is `{message:"pong", ping_id:N, server_timestamp}`.
- `GET /api/system/status` reports each subsystem honestly (`NOT_IMPLEMENTED` until built).
