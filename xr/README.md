# KIH-XR — the same keyboard, no glove

KIH's core is not the glove; it is the **input mechanism**:

> phalanx sweet spots (16 positions on the fingers) × stroke-addition multi-tap (same spot 2–3× = ㄱ→ㅋ→ㄲ)
> × Dubeolsik transfer (left hand consonants, right hand vowels, sequential input)

This demo runs that mechanism with **no physical switches at all** — only camera-based hand tracking.
It is the step from a glove prototype toward XR, where headsets already track both hands.

```
webcam ─► MediaPipe Hand Landmarker (21 joints per hand, Apache-2.0)
       ─► 16 virtual buttons placed on the phalanxes, from joint coordinates
          (per-user sweet-spot offsets from calibration)
       ─► thumb tip touches a virtual button = tap         (TapDetector: press/release hysteresis, 3-D lift-off)
       ─► MultiTapEngine — the firmware's multi-tap state machine, ported line for line
          (tap window, early commit, max-tap instant commit, debounce)
       ─► Dubeolsik automaton composes syllables ─► text box (optionally sent to the OS as key presses)
```

Anything that provides hand-joint coordinates could drive the same code path — a webcam via MediaPipe,
Apple Vision Pro (ARKit `HandAnchor`) or Quest (OpenXR `XR_EXT_hand_tracking`). The joint-index
correspondence table is in the script (`JOINT_TABLE`); porting to another device means replacing only
the landmark source. So far the demo has been run on webcams only.

## What it does

- **Live overlay** — hand skeleton, the 16 virtual buttons and tap feedback, streamed to a local web app.
- **Calibration wizard** (4 steps, saved per user to `profiles/<name>.json` and auto-loaded):
  1. hand check — verifies left/right labels with palms facing the camera
  2. sweet spots — hold the thumb on each of the 16 buttons for 1 s; the actual contact point on each
     phalanx becomes that button's centre
  3. tap radius — press/release thresholds chosen between the contact and relaxed-hand distance distributions
  4. tap window — fast double-taps vs. deliberate separate taps, threshold that minimises misclassification
     (same principle as the glove's [`tap_calibration.py`](../firmware/keyboard_glove/tap_calibration.py))
- **Text box** with the composing syllable underlined and a tap sound; parameter sliders for live tuning.
- **Palm gate** — if a hand shows its back (model label and palm geometry disagree), input from it is blocked.

Button placement follows the glove: first row = distal phalanx (DIP–TIP), second row = middle phalanx
(PIP–DIP), function keys (left Backspace, right Space) on the proximal phalanx of the index finger.
The mapping is read from [`experiments/mapping.json`](../experiments/mapping.json), the same file the
firmware tools use.

## Running

```bash
python -m venv .venv && source .venv/bin/activate
python kih_xr_demo.py --install          # = pip install -r requirements.txt
python kih_xr_demo.py                    # web app at http://127.0.0.1:7890 (native window if pywebview is present)

python kih_xr_demo.py --list-cameras     # pick a camera: --camera N
python kih_xr_demo.py --video clip.mp4 --loop   # run on a recording instead of a camera
python kih_xr_demo.py --hid              # send committed jamo to the OS as key presses (needs pynput)
python kih_xr_demo.py --selftest         # logic self-test, no camera needed
```

The hand model (`hand_landmarker.task`, ~7.5 MB) is downloaded to `models/` on first run.
The UI and inline comments are in Korean.

**Platform notes.** Tested on Linux x86_64 (mediapipe 1.0.1) and macOS Apple Silicon.
On macOS, mediapipe ≥ 0.10.30 aborts at start-up while initialising Metal, so `requirements.txt` pins
**Python 3.12 + mediapipe 0.10.21** there. If an iPhone is nearby, Continuity Camera may take camera 0 —
use `--list-cameras` / `--camera`.

## Differences from the glove

| | Glove | XR (vision) |
|---|---|---|
| Tap detection | switch contact (deterministic) | thumb–phalanx distance with hysteresis |
| Default tap window | 300 ms | 450 ms — compensates ~30 fps camera latency |
| Window timing | from first tap | rolling, from the last tap (`--window-mode first` = firmware behaviour) |
| Tactile feedback | switch click | none (visual + audio only) |

Tap thresholds depend on camera, distance and lighting — run the calibration wizard before typing.
The typing-speed results in the main README were measured on the glove, not on this demo.
