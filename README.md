# KIH — Keyboard In my Hand

**A glove-type wearable Hangul keyboard — type Korean anywhere, in any posture, without looking.**

[한국어 README](README.ko.md)

Team 손보드 (HandBoard) · Department of Mechanical Engineering, Seoul National University
🏆 **Grand Prize**, Mechatronics Competition (SNU Dept. of Mechanical Engineering / HD Hyundai, Dec 2025)
Entry for the 15th SNU College of Engineering Creative Design Festival (창의설계축전, 2026)
<!-- TODO: update once the festival result is out -->

<p align="center">
  <img src="docs/images/glove_photo.png" width="560" alt="KIH prototype"/>
</p>

<!-- TODO: demo GIF — eyes-free typing, one take -->

16 tactile switches sit on the finger phalanxes of a pair of gloves and are pressed by the same
hand's thumb. The device enumerates as a **standard USB HID keyboard** sending Dubeolsik (두벌식)
keycodes — no driver, no companion app; the OS IME composes Hangul exactly as it would for a
desktop keyboard. Total bill of materials: **₩14,184**.

## Results

A within-subject study with **20 participants** compared KIH against a TV-style cursor on-screen
keyboard (the input method used on smart TVs and in XR). Each participant trained 10 minutes per
condition, then completed **15 one-minute trials**, typing words drawn at random from a 300-word
pool **without looking at the device**. Condition order was counterbalanced.

<p align="center">
  <img src="docs/images/results_learning_curve.png" width="900" alt="Learning curves, power-law fits and error rates for KIH vs TV OSK"/>
</p>

| | KIH (glove) | TV on-screen keyboard |
|---|---|---|
| Speed, trial 1 → 15 | **2.3 → 10.6 WPM** (4.6×) | 5.6 → 7.5 WPM |
| Power-law fit | WPM = 1.55·n<sup>0.602</sup> (R² = 0.636) | WPM = 5.80·n<sup>0.079</sup> (R² = 0.142) |
| Error rate, trial 1 → 15 | **17.2% → 4.1%** (−76%) | 4.3% → 5.6% (correction rate, no trend) |

Three things the data shows:

1. **KIH keeps learning; the cursor keyboard does not.** A power-law exponent of 0.602 against
   0.079 means the baseline was already saturated at first contact — participants had used TV
   cursor keyboards before, and that is as fast as the method gets.
2. **Speed and accuracy improved together.** No speed–accuracy trade-off appeared: by trial 15
   users were 4.6× faster *and* made 76% fewer uncorrected errors.
3. **The crossover is early.** KIH passes the baseline at around trial 9 — roughly nine minutes
   of practice — and the curve is still rising at trial 15. Extrapolating the fit gives ~12 WPM at
   30 trials and ~16 WPM at 50.

The final 10.6 WPM is on par with recent hands-/eyes-free text entry (ankle gestures 11–13 WPM,
CHI 2026) and above the ~8 WPM reported for commercial cursor-selection keyboards — while leaving
both the user's gaze and posture free.

WPM here follows the standard convention, computed as jamo-per-minute ÷ 5.
Mapping efficiency (KSPC 1.27, 74.2% single-tap) is in [`analysis/RESULTS.md`](analysis/RESULTS.md).

## Why

Keyboards have kept the "board on a desk" form factor for over a century. That form binds the
input coordinate frame to a surface outside the body, which constrains **posture and gaze at the
same time** — and that constraint, not any individual device's performance, is the actual problem.

- **XR** — with an HMD on, expert typists lose ~36% of their speed on a physical keyboard, and a
  review of 176 XR text-entry techniques names text input as the area where XR still falls short
  of desktop and mobile.
- **Accessibility** — Korean braille notetakers cost about ₩6,000,000, yet only ~13% of Korean
  visually-impaired people read braille. There is no low-cost, braille-free tactile input device
  for the rest.
- **Posture** — 45.5% twelve-month prevalence of neck pain among office workers, with prolonged
  sitting and forward neck flexion as significant risk factors.

So the project reframes the goal as **posture-free, eyes-free text entry** and puts the keyboard
on the hand instead of on the desk.

## How it works

<p align="center">
  <img src="docs/images/mapping_diagram.png" width="760" alt="16-button Hangul mapping"/>
</p>

1. **Phalanxes are built-in keycaps.** People can distinguish and operate multiple buttons on
   their own fingers using touch and proprioception alone, without looking (DigitSpace, CHI '16).
   16 buttons (8 per hand) expand on that capacity without exceeding it. Positions were chosen
   from three eyes-free layout candidates using responses from **30 participants** plus the HCI
   literature. Because the switches ride on the fingers, no desk or input surface is needed, and
   because a switch closes an electrical contact, there is no gesture to estimate — no camera, no
   recognition, no probabilistic error.

2. **Multi-tap = stroke addition (가획).** Base jamo are one tap; derived jamo come from tapping
   the *same* button again — two taps for aspirates and y-vowels (ㄱ→ㅋ, ㅏ→ㅑ), three for tense
   consonants (ㄱ→ㄲ). This is the 가획·병서 principle of Hunminjeongeum mapped onto repetition
   count, so the only rule to memorize is "same family, same button, press again."

   <p align="center">
     <img src="docs/images/multitap_timeline.png" width="720" alt="Multi-tap principle"/>
     <br/>
     <img src="docs/images/freq_vs_taps.png" width="760" alt="Jamo frequency vs. required taps"/>
   </p>

   Hangul's base letters largely coincide with its highest-frequency jamo, so following the
   derivation principle also buys frequency efficiency for free: on a 199,806-jamo corpus the
   layout scores **KSPC 1.27** (−26% vs. a frequency-blind layout) with **74.2% of input
   completed in a single tap**.

3. **Sequential, never chorded.** Chorded keyboards never reached general adoption because of the
   memorization barrier. Left-consonant / right-vowel follows Dubeolsik, so existing Korean
   typists carry their layout knowledge over; compound vowels and final clusters are typed
   sequentially and composed by the OS IME, exactly as on a desktop keyboard.

4. **Per-user calibration.** The multi-tap window (default 300 ms) is measured per user by
   [`firmware/keyboard_glove/tap_calibration.py`](firmware/keyboard_glove/tap_calibration.py):
   the firmware is flipped into a raw-tap mode, the user types two sentences, and every inter-tap
   interval is labelled *intentional multi-tap* vs *separate keystroke that reuses the button* by
   aligning observed keydowns against the target sequence from `mapping.json`. The tool picks the
   threshold that minimises misclassification and **rewrites `TAP_WINDOW_DEFAULT` in the .ino
   directly** — bumping a `CAL_STAMP` so the board's stored EEPROM value cannot shadow the newly
   calibrated one. No serial port, no extra packages.

## Repository structure

```
firmware/
  keyboard_glove/
    keyboard_glove.ino    Arduino Leonardo firmware (USB HID, multi-tap engine, raw-tap
                          measurement mode, calibration block, CAL_STAMP + EEPROM)
    tap_calibration.py    per-user multi-tap window calibration — lives next to the sketch
                          because it edits it
    mapping.json          copy of experiments/mapping.json so the calibration tool works
                          standalone; keep both in sync (the tool warns if they diverge)
    test/                 host-side test of the multi-tap engine — stubs the Arduino API,
                          #includes the sketch and drives it on a virtual clock, so the
                          timing logic is verified without a board (`make both`)
    legacy/               original course-project sketch (development history)
  calibrate_window.py     optional serial route: tune the window live without re-flashing
experiments/
  PROTOCOL.md             experiment protocol (Korean): button reach-time & mapping cost,
                          learning curve, usability/posture, cursor-OSK comparison,
                          eyes-free — standard text-entry methodology (MacKenzie et al.)
  speed_test.py           1-minute random-word speed test GUI (the main study tool)
  tv_remote_sprint.py     TV-remote cursor keyboard, 60-second word sprint — the matched
                          baseline (same word pool, same WPM definition)
  tv_osk_test.py          same input method, sentence-transcription variant
  logger.py               transcription/tapping logger GUI
  analyze.py              metrics & figures: CPM/WPM, MSD error rate, learning curve,
                          mapping cost vs. 10,000 random layouts
  mapping.json            16-button ↔ jamo mapping (single source of truth)
  logs/
    speed_vs_tv_all.csv   raw per-trial records for the study — 20 participants × 2
                          conditions × 15 trials (600 rows), participants pseudonymous
    README.md             data dictionary; why the two conditions carry different columns
analysis/
  mapping_analysis.py     corpus → jamo frequency, KSPC, same-button bigram rate
  verify_results.py       recomputes every figure in RESULTS.md from the raw data and
                          exits non-zero on any mismatch
  STUDY_DESIGN.md         study design, metric definitions and limitations
  COST_MARKET.md          bill of materials, scale economics and recommended price
  RESULTS.md              quantitative results
docs/
  BUILD.md                build guide: parts, button placement, assembly, bring-up
  images/                 photos, diagrams and the study figure
```

Every Python tool is standard-library only and ships with a `--selftest` that runs without a GUI;
the firmware has a host-side test suite that needs no hardware. The study's raw data is in the
repository, so the numbers below can be recomputed with `python analysis/verify_results.py`.

## Hardware

<p align="center">
  <img src="docs/images/system_overview.png" width="820" alt="Prototype and signal flow"/>
</p>

| Part | Qty | Unit | Note |
|---|---|---|---|
| Tactile switch (6×6 mm) | 16 | ₩134 | 2 per finger (index–ring), 1 pinky + 1 function key, per hand |
| Arduino Leonardo (ATmega32u4) | 1 | ₩8,500 | native USB HID |
| Leather gloves | 1 pair | ₩1,000 | |
| Wiring, heat-shrink | 1 set | ₩1,040 | |
| Adhesive, insulating tape | 1 set | ₩500 | |
| **Total** | | **₩14,184** | ~₩12,230 at 15+ units (−13.8%) |

Flash `firmware/keyboard_glove/keyboard_glove.ino` (Arduino IDE, board: Leonardo).
Serial at 115200 baud: `W<ms>` set tap window · `S` save to EEPROM · `R1/R0` raw-tap mode ·
`C1/C0` tap stream · `?` status.

## Running the tools

```bash
# Python 3.8+; GUIs use tkinter (stdlib), no pip packages
python experiments/speed_test.py                    # 1-min speed test
python experiments/tv_remote_sprint.py              # TV-remote baseline, 60s word sprint
python experiments/tv_osk_test.py                   # baseline, sentence-transcription variant
python experiments/logger.py --mode transcribe --participant P01 --session S1
python firmware/keyboard_glove/tap_calibration.py   # tap-window calibration → patches the .ino
python experiments/analyze.py transcribe            # figures (needs matplotlib)

# verification, no hardware required
python experiments/speed_test.py --selftest
make -C firmware/keyboard_glove/test both
```

## Team

**손보드 (HandBoard)** — Department of Mechanical Engineering, Seoul National University

| | | |
|---|---|---|
| Kijun Kim (김기준) | Hardware | glove integration, switch mounting, prototype build |
| Dongwon Lee (이동원) | User studies & market | study design, data analysis, cost/market analysis |
| Hongjun Ha (하홍준) | Software | firmware, multi-tap engine, calibration tooling |

## License

[MIT](LICENSE) — hardware design, firmware and experiment tools.
