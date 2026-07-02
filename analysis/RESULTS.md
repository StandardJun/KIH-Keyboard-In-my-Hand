# Analysis Results

## Mapping efficiency (corpus analysis, 2026-07)

Corpus: ~200,000 keystroke-level jamo from modern Korean prose (`mapping_analysis.py`).

| Metric | Value | Note |
|---|---|---|
| Theoretical KSPC (taps per jamo) | **1.269** | multi-tap mapping, PPT-final layout |
| KSPC of frequency-blind uniform layout | 1.727 | baseline |
| Reduction | **−26.5%** | achieved by base-jamo = 1 tap structure |
| Share of input completed in a single tap | **74.2%** | |
| Adjacent jamo pairs sharing a button | **3.60%** | only these pay the multi-tap timeout |
| Most frequent same-button pair | ㅡ+ㅣ (syllable '의') | ≈32% of all same-button pairs → early-commit / dedicated 'ㅢ' handling planned |

Key insight: the base letters of Hangul (기본자) largely coincide with the
highest-frequency jamo, so a layout that follows the 가획 (stroke-addition)
derivation principle — chosen for learnability — inherits frequency-optimal
variable-length coding almost for free.

## Pilot typing speed

3 participants, varied environments: **9–15 WPM** (jamo/5 convention) —
on par with recent hands-/eyes-free text entry techniques
(AnkleType eyes-free 11–13 WPM, HeadText 9.8 WPM, DuSK 10–13 WPM),
well above the thumb-to-phalanx predecessor FingerT9 (3.4–5.4 WPM).

Full learning-curve, device-comparison and eyes-free studies: see
[`experiments/PROTOCOL.md`](../experiments/PROTOCOL.md) (in Korean). Results will be added here.
