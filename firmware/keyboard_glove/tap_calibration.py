#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tap_calibration.py — 연타 판정 윈도우 캘리브레이션 → 펌웨어(.ino) 설정값 자동 수정

장갑형 한글 키보드는 같은 버튼을 짧은 시간 안에 2·3회 누르면 파생 자모를
만든다(ㄱ→ㅋ→ㄲ). 이때 '얼마나 짧아야 연타로 볼 것인가'가 연타 판정 윈도우
(TAP_WINDOW)이고, 사람마다 손가락 속도가 다르므로 개인별로 정해야 한다.

이 도구는 같은 버튼의 연속 눌림 사이 간격을
  (a) '의도적 연타'  — 한 자모를 만들기 위한 2·3회 탭
  (b) '별개 입력'    — 서로 다른 자모인데 우연히 같은 버튼이 연속되는 경우
로 **라벨과 함께** 수집한 뒤, 두 분포를 가장 잘 가르는 임계값을 계산해
**펌웨어 소스(keyboard_glove.ino)의 TAP_WINDOW_DEFAULT를 직접 수정**한다.

위치: 이 스크립트는 keyboard_glove.ino 와 같은 폴더에 있다. 캘리브레이션은
      펌웨어 설정을 바꾸는 작업이므로 펌웨어와 함께 두고, 실험 도구(experiments/)와
      분리한다.
실행: python tap_calibration.py            (Python 3.8+, 표준 라이브러리만)
      python tap_calibration.py --selftest (GUI 없이 계산 로직·.ino 패치 검증)
필요: keyboard_glove.ino  — 같은 폴더에서 자동 탐색
      mapping.json       — 버튼↔자모↔keysym 단일 출처. 편의를 위해 이 폴더에도
                           사본을 둔다(같은 폴더가 1순위). 없으면 위쪽 폴더의
                           <dir>/mapping.json·<dir>/experiments/mapping.json 을
                           거슬러 찾고, 그래도 없으면 시작 화면의
                           [mapping.json 찾아보기]로 지정한다(경로는 기억됨).
                           ※ 사본과 experiments/ 원본의 내용이 달라지면 시작
                           화면에서 경고한다 — 매핑을 고치면 양쪽을 함께 갱신할 것.
저장: experiments/logs/ (실험 데이터를 한곳에 모은다. experiments/가 없으면 스크립트 옆)

────────────────────────────────────────────────────────────────────────
전체 흐름 (도구가 순서대로 안내한다)
────────────────────────────────────────────────────────────────────────
 1) [측정 준비] 도구가 .ino의 RAW_TAP_MODE를 1로 바꾼다 → Arduino IDE에서 업로드.
    raw-tap 모드에서는 펌웨어가 연타를 합치지 않고 물리 탭을 그대로 보내므로
    PC에서 실제 탭 간격을 복원할 수 있다.
 2) [측정] PC 입력 언어를 영문(ABC/ENG)으로 두고 문장 2개만 입력한다.
      1단계 'separate' : 같은 버튼의 '별개 입력' 경계가 많은 문장
      2단계 'multitap' : 된소리·거센소리가 많은 문장
    mapping.json의 keysym_hint로 각 물리 탭을 목표 시퀀스에 사후 정렬하므로,
    오타가 나도 문장을 끝까지 입력하면 정확히 매칭된 구간의 간격만 유효 표본이 된다.
 3) [적용] 오분류(연타가 분리됨 + 별개 입력이 합쳐짐)를 최소화하는 임계값을
    TAP_WINDOW_DEFAULT에 기록하고, RAW_TAP_MODE를 0으로 되돌리며 CAL_STAMP를
    +1 한다 → 다시 업로드하면 적용 완료.
    (CAL_STAMP가 바뀌어야 보드가 EEPROM의 옛 값 대신 소스 값을 쓴다. 이 장치가
     없으면 .ino 숫자만 고쳐도 보드는 계속 옛 값으로 동작한다.)
 수정 전 .ino는 같은 폴더에 .ino.bak-<시각> 으로 백업된다.

저장(logs/): 캘리브레이션은 '지금 기기에 넣을 값'을 정하는 1회성 작업이라 세션 구분이
없다. 누구의 값인지만 남긴다(실험 도구의 참가자 ID와 같은 값을 쓰면 대조가 쉽다).
  - <user>_tapcal_<시각>.jsonl        : 문장별 원본 이벤트
  - <user>_tap_intervals_<시각>.csv   : 간격 1개당 1행
    (trial_type = multitap / separate / cross)
  - <user>_tap_summary_<시각>.csv     : 측정 요약 + 권고 임계값

[주의 — 측정 정확도]
결과는 OS IME 조합 결과가 아니라 raw QWERTY keydown 시간 자체다. PC 입력 언어를
영문으로 두는 것이 가장 안정적이다. 더 엄밀하게는 펌웨어 시리얼 스트림(C1 명령)의
timestamp를 쓰면 OS 이벤트 지연까지 제거할 수 있다.
"""

import csv
import json
import re
import shutil
import sys
import time
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path

try:
    import tkinter as tk
    from tkinter import font as tkfont
    from tkinter import filedialog, messagebox
except ImportError:  # headless 환경에서도 selftest는 돌도록
    tk = None

# ---------------------------------------------------------------------------
# 경로/상수
# ---------------------------------------------------------------------------
SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent.parent          # firmware/keyboard_glove/ 기준
EXPERIMENTS_DIR = REPO_ROOT / "experiments"


CONFIG_PATH = SCRIPT_DIR / "tap_calibration.config.json"


def _saved_mapping_path():
    """이전에 사용자가 직접 지정한 mapping.json 경로(있으면)."""
    try:
        cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        p = Path(cfg.get("mapping_path", ""))
        return p if p.is_file() else None
    except (OSError, ValueError):
        return None


def find_mapping_candidates():
    """찾을 수 있는 mapping.json을 모두 반환한다(가까운 순).

    스크립트를 레포 밖(예: Arduino 스케치 폴더)에 복사해 써도 동작하도록,
    고정된 상대 경로에 의존하지 않고 위쪽 폴더까지 거슬러 올라가며 찾는다.
    같은 폴더의 파일이 항상 1순위다.
    """
    seen, found = set(), []
    for base in [SCRIPT_DIR, *SCRIPT_DIR.parents[:5]]:
        for cand in (base / "mapping.json", base / "experiments" / "mapping.json"):
            try:
                key = cand.resolve()
            except OSError:
                continue
            if key in seen:
                continue
            seen.add(key)
            if cand.is_file():
                found.append(cand)
    return found


def find_conflicting_mappings(chosen, candidates):
    """chosen과 내용이 다른 다른 위치의 mapping.json 목록.

    같은 매핑 파일이 여러 곳에 복사돼 있을 때, 한쪽만 고쳐서 서로 어긋나면
    측정 문장이 실제 기기와 다르게 만들어진다. 그 상태를 조용히 넘기지 않고
    시작 화면에서 경고하기 위한 함수다.
    """
    if chosen is None:
        return []
    try:
        base = Path(chosen).read_bytes()
    except OSError:
        return []
    out = []
    for cand in candidates:
        if Path(cand).resolve() == Path(chosen).resolve():
            continue
        try:
            if cand.read_bytes() != base:
                out.append(cand)
        except OSError:
            continue
    return out


def _resolve_mapping_path():
    """사용할 mapping.json 하나를 고른다(없으면 None — GUI에서 직접 지정 가능)."""
    saved = _saved_mapping_path()
    if saved:
        return saved
    cands = find_mapping_candidates()
    return cands[0] if cands else None


def _resolve_logs_dir():
    """세션 로그는 다른 실험 데이터와 같은 곳(experiments/logs)에 모은다."""
    return (EXPERIMENTS_DIR / "logs") if EXPERIMENTS_DIR.is_dir() else (SCRIPT_DIR / "logs")


MAPPING_PATH = _resolve_mapping_path()
MAPPING_CONFLICTS = find_conflicting_mappings(MAPPING_PATH, find_mapping_candidates())
LOGS_DIR = _resolve_logs_dir()

# ---------------------------------------------------------------------------
# 펌웨어(.ino) 연동
# ---------------------------------------------------------------------------
# .ino의 'CALIBRATION BLOCK' 안에 있는 값 한 줄씩을 정규식으로 교체한다.
RE_RAW = re.compile(r"^(\s*#define\s+RAW_TAP_MODE\s+)(\d+)", re.M)
RE_WINDOW = re.compile(
    r"^(\s*const\s+unsigned\s+long\s+TAP_WINDOW_DEFAULT\s*=\s*)(\d+)(\s*;)", re.M)
RE_STAMP = re.compile(r"^(\s*const\s+uint16_t\s+CAL_STAMP\s*=\s*)(\d+)(\s*;)", re.M)

WINDOW_MIN, WINDOW_MAX = 100, 600   # 펌웨어가 허용하는 범위와 동일하게 유지할 것
WINDOW_ROUND = 5                    # 권고값 반올림 단위(ms)

# 탐색 순서: 같은 폴더(정상) → 상위 firmware 트리 → 레포 표준 위치
INO_SEARCH_DIRS = (
    SCRIPT_DIR,
    SCRIPT_DIR.parent,
    REPO_ROOT / "firmware" / "keyboard_glove",
)


def find_ino_file():
    """캘리브레이션 블록을 가진 .ino를 찾는다. 없으면 None."""
    seen = []
    for d in INO_SEARCH_DIRS:
        if not d.is_dir():
            continue
        for path in sorted(d.glob("*.ino")):
            seen.append(path)
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            if RE_WINDOW.search(text) and RE_RAW.search(text):
                return path
    # 마커가 없더라도 .ino가 하나뿐이면 후보로 돌려준다(경고용).
    return seen[0] if len(seen) == 1 else None


def read_ino_settings(path):
    """.ino에서 현재 설정을 읽는다. -> dict 또는 None"""
    if not path or not Path(path).exists():
        return None
    text = Path(path).read_text(encoding="utf-8", errors="ignore")
    m_win, m_raw, m_stamp = (RE_WINDOW.search(text), RE_RAW.search(text),
                             RE_STAMP.search(text))
    if not (m_win and m_raw and m_stamp):
        return None
    return {
        "path": Path(path),
        "tap_window": int(m_win.group(2)),
        "raw_tap": int(m_raw.group(2)),
        "cal_stamp": int(m_stamp.group(2)),
    }


def patch_ino(path, tap_window=None, raw_tap=None, bump_stamp=True):
    """.ino 설정값을 수정한다(백업 후 덮어쓰기).

    tap_window : 새 연타 판정 윈도우(ms). None이면 유지.
    raw_tap    : 0/1. None이면 유지.
    bump_stamp : CAL_STAMP +1 — 보드의 EEPROM 옛 값 대신 소스 값을 쓰게 한다.
    반환: {"backup": Path, "before": dict, "after": dict}
    """
    path = Path(path)
    text = path.read_text(encoding="utf-8")
    before = read_ino_settings(path)
    if before is None:
        raise ValueError("이 .ino에는 캘리브레이션 설정 블록이 없습니다: %s" % path)

    if tap_window is not None:
        w = int(round(tap_window))
        if not (WINDOW_MIN <= w <= WINDOW_MAX):
            raise ValueError("윈도우 값은 %d~%d ms 범위여야 합니다(입력: %d)."
                             % (WINDOW_MIN, WINDOW_MAX, w))
        text = RE_WINDOW.sub(lambda m: "%s%d%s" % (m.group(1), w, m.group(3)),
                             text, count=1)
    if raw_tap is not None:
        rv = 1 if raw_tap else 0
        text = RE_RAW.sub(lambda m: "%s%d" % (m.group(1), rv), text, count=1)
    if bump_stamp:
        text = RE_STAMP.sub(
            lambda m: "%s%d%s" % (m.group(1), (before["cal_stamp"] + 1) % 65536,
                                  m.group(3)), text, count=1)

    backup = path.with_suffix(path.suffix + ".bak-%s"
                              % datetime.now().strftime("%m%d_%H%M%S"))
    shutil.copy2(path, backup)
    path.write_text(text, encoding="utf-8")
    return {"backup": backup, "before": before, "after": read_ino_settings(path)}


# ---------------------------------------------------------------------------
# 임계값 결정 — 라벨된 두 분포에서 오분류 최소화
# ---------------------------------------------------------------------------
def _stats(vals):
    if not vals:
        return {"n": 0, "mean": None, "median": None, "sd": None}
    vals = sorted(float(v) for v in vals)
    n = len(vals)
    mean = sum(vals) / n
    median = vals[n // 2] if n % 2 else (vals[n // 2 - 1] + vals[n // 2]) / 2.0
    var = sum((v - mean) ** 2 for v in vals) / n if n > 1 else 0.0
    return {"n": n, "mean": mean, "median": median, "sd": var ** 0.5}


def _errors_at(threshold, multitap, separate):
    """임계값 T에서의 오분류 수.

    T 미만 = 연타로 판정(합쳐짐), T 이상 = 별개 입력으로 판정.
      - multitap 표본이 T 이상 → 연타가 분리됨(의도한 파생 자모가 안 나옴)
      - separate 표본이 T 미만 → 별개 입력이 잘못 합쳐짐(엉뚱한 자모)
    """
    split = sum(1 for v in multitap if v >= threshold)
    merged = sum(1 for v in separate if v < threshold)
    return split, merged


def decide_threshold(multitap, separate):
    """라벨된 간격 분포에서 권고 연타 윈도우(ms)를 계산한다.

    1) 후보 임계값 = 두 분포를 합친 표본들 사이의 중점
    2) 총 오분류(연타 분리 + 오병합)를 최소화하는 값 선택
    3) 동점이면 두 표본 사이 '틈'이 가장 넓은 구간의 중점(안전 여유 최대)
    4) 펌웨어 허용 범위로 클램프하고 WINDOW_ROUND 단위로 반올림
    반환: dict — 권고값·오류 수·참고 통계. 표본이 없으면 None.
    """
    mt = [float(v) for v in multitap]
    sp = [float(v) for v in separate]
    if not mt or not sp:
        return None

    pooled = sorted(mt + sp)
    candidates = [((a + b) / 2.0, b - a) for a, b in zip(pooled, pooled[1:]) if b > a]
    candidates.append((pooled[0] - 1.0, 0.0))
    candidates.append((pooled[-1] + 1.0, 0.0))

    best = None  # ((총오류, -여유), 임계값, split, merged, gap)
    for t, gap in candidates:
        split, merged = _errors_at(t, mt, sp)
        key = (split + merged, -gap)
        if best is None or key < best[0]:
            best = (key, t, split, merged, gap)
    _, t_opt, split, merged, gap = best

    rec = min(WINDOW_MAX, max(WINDOW_MIN, t_opt))
    rec = int(round(rec / WINDOW_ROUND) * WINDOW_ROUND)
    r_split, r_merged = _errors_at(rec, mt, sp)

    mt_s, sp_s = _stats(mt), _stats(sp)
    return {
        "recommended_ms": rec,
        "optimal_raw_ms": round(t_opt, 2),
        "clamped": abs(rec - t_opt) > WINDOW_ROUND,
        "margin_ms": round(gap, 2),
        "err_split": r_split,          # 연타가 분리될 표본 수
        "err_merged": r_merged,        # 별개 입력이 합쳐질 표본 수
        "err_total": r_split + r_merged,
        "err_pct": round((r_split + r_merged) / (len(mt) + len(sp)) * 100.0, 2),
        "multitap": mt_s,
        "separate": sp_s,
        "separable": (mt_s["mean"] is not None and sp_s["mean"] is not None
                      and sp_s["mean"] > mt_s["mean"]),
    }


# ---------------------------------------------------------------------------
# 한글 자모 분해 (목표 문장 → 자모열)
# ---------------------------------------------------------------------------
CHOSEONG = "ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ"
JUNGSEONG = "ㅏㅐㅑㅒㅓㅔㅕㅖㅗㅘㅙㅚㅛㅜㅝㅞㅟㅠㅡㅢㅣ"
JONGSEONG = " ㄱㄲㄳㄴㄵㄶㄷㄹㄺㄻㄼㄽㄾㄿㅀㅁㅂㅄㅅㅆㅇㅈㅊㅋㅌㅍㅎ"
COMPOUND = {
    "ㅘ": "ㅗㅏ", "ㅙ": "ㅗㅐ", "ㅚ": "ㅗㅣ", "ㅝ": "ㅜㅓ",
    "ㅞ": "ㅜㅔ", "ㅟ": "ㅜㅣ", "ㅢ": "ㅡㅣ",
    "ㄳ": "ㄱㅅ", "ㄵ": "ㄴㅈ", "ㄶ": "ㄴㅎ", "ㄺ": "ㄹㄱ",
    "ㄻ": "ㄹㅁ", "ㄼ": "ㄹㅂ", "ㄽ": "ㄹㅅ", "ㄾ": "ㄹㅌ",
    "ㄿ": "ㄹㅍ", "ㅀ": "ㄹㅎ", "ㅄ": "ㅂㅅ",
}


def decompose_char(ch):
    """한 글자를 자모 리스트로 분해한다(겹모음·겹받침은 2자모, 쌍자음은 1자모)."""
    code = ord(ch)
    if 0xAC00 <= code <= 0xD7A3:
        code -= 0xAC00
        out = [CHOSEONG[code // 588]]
        jung = JUNGSEONG[(code % 588) // 28]
        out.extend(COMPOUND.get(jung, jung))
        jong = JONGSEONG[code % 28]
        if jong != " ":
            out.extend(COMPOUND.get(jong, jong))
        return out
    if ch in COMPOUND:
        return list(COMPOUND[ch])
    return [ch]


# ---------------------------------------------------------------------------
# 캘리브레이션 문장 — 두 개만 사용
# ---------------------------------------------------------------------------
# 1단계: 서로 다른 자모인데 같은 버튼이 연속되는 경계를 의도적으로 포함.
# (온난 ㄴ→ㄴ, 국가 ㄱ→ㄱ, 옷소매 ㅅ→ㅅ, 걷다가 ㄷ→ㄷ, 낮잠 ㅈ→ㅈ,
#  상어 ㅇ→ㅇ, 밥벌이 ㅂ→ㅂ)
CALIB_SEPARATE_SENTENCE = (
    "온난한 국가에서 옷소매를 걷다가 낮잠을 자고 "
    "상어를 찍으며 밥벌이를 한다"
)
# 2단계: 된소리(ㄲㄸㅃㅆㅉ)와 거센소리(ㅋㅌㅍㅊ)를 모두 포함.
CALIB_MULTITAP_SENTENCE = (
    "까치 토끼 코끼리가 펄쩍 뛰고 아빠는 빵을 "
    "쓱쓱 찢어 먹었다"
)

CALIBRATION_PHASES = (
    {"phase": "separate", "title": "1단계 · 별개 입력", "focus": "separate",
     "sentence": CALIB_SEPARATE_SENTENCE},
    {"phase": "multitap", "title": "2단계 · 의도적 연타", "focus": "multitap",
     "sentence": CALIB_MULTITAP_SENTENCE},
)

TAPCAL_CSV_HEADER = [
    "timestamp", "user", "phase", "trial_index",
    "trial_type", "use_for_calibration", "target", "gap_index", "interval_ms",
    "prev_jamo", "next_jamo", "prev_button", "next_button", "match",
]
TAPCAL_SUMMARY_HEADER = [
    "timestamp", "user",
    "n_multitap", "mean_multitap_ms", "median_multitap_ms", "sd_multitap_ms",
    "n_separate", "mean_separate_ms", "median_separate_ms", "sd_separate_ms",
    "mean_gap_ms", "midpoint_reference_ms",
    "recommended_window_ms", "err_split", "err_merged", "err_pct", "applied_to_ino",
]

# 측정에서 제외할 기능키/수식키
IGNORED_KEYS = {
    "Tab", "Escape", "Shift_L", "Shift_R", "Control_L", "Control_R",
    "Alt_L", "Alt_R", "Meta_L", "Meta_R", "Super_L", "Super_R",
    "Caps_Lock", "Num_Lock", "Hangul", "Hangul_Hanja",
    "Henkan", "Muhenkan", "Kanji",
}


# ---------------------------------------------------------------------------
# mapping.json 로드 및 시행(trial) 생성
# ---------------------------------------------------------------------------
def load_mapping():
    """mapping.json을 읽어온다(logger.py·analyze.py와 동일한 단일 출처)."""
    if MAPPING_PATH is None:
        return None
    return json.loads(MAPPING_PATH.read_text(encoding="utf-8"))


MAPPING = None
BUTTON_TO_KEYSYM = {}


def apply_mapping(mapping):
    """전역 매핑과 keysym 색인을 갱신한다."""
    global MAPPING, BUTTON_TO_KEYSYM
    MAPPING = mapping
    BUTTON_TO_KEYSYM = {}
    if mapping:
        for bid, info in mapping.get("buttons", {}).items():
            hint = str(info.get("keysym_hint", "")).strip().lower()
            if hint:
                BUTTON_TO_KEYSYM[bid] = hint
    return MAPPING


def set_mapping_path(path):
    """사용자가 고른 mapping.json을 적용하고 다음 실행을 위해 기억한다."""
    global MAPPING_PATH
    path = Path(path)
    mapping = json.loads(path.read_text(encoding="utf-8"))
    if not mapping.get("buttons"):
        raise ValueError("이 파일에는 buttons 항목이 없습니다: %s" % path)
    MAPPING_PATH = path
    apply_mapping(mapping)
    try:
        CONFIG_PATH.write_text(json.dumps({"mapping_path": str(path)},
                                          ensure_ascii=False, indent=1),
                               encoding="utf-8")
    except OSError:
        pass   # 기억에 실패해도 이번 실행에는 지장 없다
    return MAPPING


apply_mapping(load_mapping())


def event_token(event):
    """GUI key event -> 비교용 영문 token."""
    if event.char and event.char.isprintable() and not event.char.isspace():
        return event.char.lower()
    return str(event.keysym or "").lower()


def align_observed_to_plan(events, tap_plan):
    """실제 raw keydown과 목표 raw-tap plan을 느슨하게 정렬한다.

    오타가 있어도 문장 전체를 폐기하지 않고, 정확히 일치하는 키들만 사후에
    대응시켜 주변의 유효 interval을 살리기 위한 함수다.
    반환: (alignment {expected_index: observed_index}, edit_distance_like)
    """
    expected = [BUTTON_TO_KEYSYM.get(x["button"], "").lower() for x in tap_plan]
    observed = [str(x.get("token", "")).lower() for x in events]

    sm = SequenceMatcher(a=expected, b=observed, autojunk=False)
    alignment = {}
    matched = 0
    for block in sm.get_matching_blocks():
        for k in range(block.size):
            alignment[block.a + k] = block.b + k
            matched += 1
    return alignment, max(len(expected), len(observed)) - matched


def build_char_to_button_sequence(mapping):
    """한 자모 -> raw-tap 버튼 시퀀스(기본 자모 1탭, 파생 자모 2·3탭)."""
    seq_of = {}
    for bid, info in mapping.get("buttons", {}).items():
        jamo = info.get("jamo", "")
        if len(jamo) == 1:
            seq_of[jamo] = [bid]
    for result_char, seq in mapping.get("sequences", {}).items():
        if result_char.startswith("_") or len(result_char) != 1:
            continue
        if seq and all(b in mapping.get("buttons", {}) for b in seq):
            seq_of[result_char] = list(seq)
    return seq_of


def build_calibration_plan(sentence, mapping):
    """목표 문장을 raw 물리 탭 시퀀스로 펼치고 각 간격의 정답 라벨을 만든다.

    gap label 규칙
      - 같은 자모(unit) 내부의 연속 탭: multitap
      - 서로 다른 자모 사이, 공백 없이 이어지고 버튼도 같음: separate
      - 버튼이 다르거나 단어 사이 공백을 건너뜀: cross
    공백 키 자체는 측정에서 제외하되, 공백을 사이에 둔 두 자모를 '별개 입력'
    표본으로 잘못 세지 않도록 segment를 구분한다.
    """
    seq_of = build_char_to_button_sequence(mapping)
    tap_plan = []
    unit_idx = segment_idx = 0

    for ch in sentence:
        if ch.isspace():
            segment_idx += 1
            continue
        for jamo in decompose_char(ch):
            seq = seq_of.get(jamo)
            if seq is None:
                if not ("ㄱ" <= jamo <= "ㅣ"):
                    segment_idx += 1   # 구두점 등은 경계로 보고 제외
                    continue
                raise ValueError(
                    "캘리브레이션 문장의 자모 %r 을 mapping.json으로 입력할 수 없습니다."
                    % jamo)
            for tap_idx, button in enumerate(seq):
                tap_plan.append({
                    "button": button, "jamo": jamo, "unit_idx": unit_idx,
                    "segment_idx": segment_idx, "tap_idx": tap_idx,
                    "tap_count": len(seq),
                })
            unit_idx += 1

    if len(tap_plan) < 2:
        raise ValueError("캘리브레이션 문장을 raw 탭 시퀀스로 만들 수 없습니다.")

    gap_labels = []
    for i in range(1, len(tap_plan)):
        prev, cur = tap_plan[i - 1], tap_plan[i]
        if prev["unit_idx"] == cur["unit_idx"]:
            trial_type = "multitap"
        elif (prev["segment_idx"] == cur["segment_idx"]
              and prev["button"] == cur["button"]):
            trial_type = "separate"
        else:
            trial_type = "cross"
        gap_labels.append({
            "trial_type": trial_type,
            "prev_jamo": prev["jamo"], "next_jamo": cur["jamo"],
            "prev_button": prev["button"], "next_button": cur["button"],
        })
    return tap_plan, gap_labels


def build_calibration_trials():
    """두 단계, 두 문장으로만 구성된 캘리브레이션 시행 목록."""
    if not MAPPING:
        raise RuntimeError(
            "mapping.json을 찾을 수 없습니다.\n"
            "시작 화면의 [mapping.json 찾아보기] 버튼으로 직접 지정하거나,\n"
            "이 스크립트와 같은 폴더(또는 상위의 experiments/)에 두세요.")
    trials = []
    for spec in CALIBRATION_PHASES:
        tap_plan, gap_labels = build_calibration_plan(spec["sentence"], MAPPING)
        n_focus = sum(1 for g in gap_labels if g["trial_type"] == spec["focus"])
        if n_focus == 0:
            raise ValueError("%s 문장에서 %s 표본을 찾지 못했습니다."
                             % (spec["title"], spec["focus"]))
        trials.append({**spec, "tap_plan": tap_plan,
                       "gap_labels": gap_labels, "n_focus": n_focus})
    return trials


def extract_valid_gaps(events, tap_plan, gap_labels):
    """관측 이벤트에서 유효 간격만 뽑는다.

    두 목표 탭이 모두 정확히 매칭되고, 실제 관측에서도 바로 연속인 경우만
    유효 표본으로 인정한다(중간에 오타가 끼면 그 간격은 버린다).
    반환: (gaps_ms, labels, alignment, edit_distance)
    """
    alignment, edit_distance = align_observed_to_plan(events, tap_plan)
    gaps, labels = [], []
    for gap_idx, lab in enumerate(gap_labels, start=1):
        prev_exp, next_exp = gap_idx - 1, gap_idx
        if prev_exp not in alignment or next_exp not in alignment:
            continue
        prev_obs, next_obs = alignment[prev_exp], alignment[next_exp]
        if next_obs != prev_obs + 1:
            continue
        gaps.append(round(events[next_obs]["t_ms"] - events[prev_obs]["t_ms"], 2))
        labels.append({**lab, "expected_gap_index": gap_idx})
    return gaps, labels, alignment, edit_distance


def sanitize_id(text):
    """파일명에 쓸 수 있게 ID 문자열 정리."""
    return "".join(ch for ch in text.strip() if ch.isalnum() or ch in "-_") or "X"


# ---------------------------------------------------------------------------
# GUI
# ---------------------------------------------------------------------------
class TapCalibrationApp:
    def __init__(self, root):
        self.root = root
        root.title("연타 판정 윈도우 캘리브레이션 — Keyboard In My Hand")
        root.geometry("860x620")
        root.minsize(720, 560)

        base = tkfont.nametofont("TkDefaultFont")
        fam = base.actual("family")
        self.f_small = tkfont.Font(family=fam, size=11)
        self.f_mid = tkfont.Font(family=fam, size=14)
        self.f_entry = tkfont.Font(family=fam, size=22)
        self.f_title = tkfont.Font(family=fam, size=28, weight="bold")
        self.f_target = tkfont.Font(family=fam, size=24, weight="bold")

        self.user = ""
        self.ino_path = find_ino_file()
        self.ino = read_ino_settings(self.ino_path) if self.ino_path else None

        self.trials = []
        self.index = 0
        self.rows = []
        self.cur = None
        self.t0 = None
        self.events = []
        self.accept = False
        self.decision = None
        self.jsonl_path = self.csv_path = self.summary_path = None

        self._build_start()
        self._build_interstitial()
        self._build_measure()
        self._build_result()
        self._show(self.start_frame)

    def _show(self, frame):
        for f in (self.start_frame, self.inter_frame, self.measure_frame,
                  self.result_frame):
            f.pack_forget()
        frame.pack(fill="both", expand=True)

    # -- 시작 화면 --------------------------------------------------------
    def _build_start(self):
        f = self.start_frame = tk.Frame(self.root)
        tk.Label(f, text="연타 판정 윈도우 캘리브레이션", font=self.f_title).pack(pady=(38, 4))
        tk.Label(f, text="같은 버튼을 다시 누를 때 '연타'로 볼 시간 한계를 개인별로 실측합니다",
                 font=self.f_small, fg="gray40").pack(pady=(0, 22))

        form = tk.Frame(f)
        form.pack()
        # 캘리브레이션은 '기기에 지금 설정할 값'을 정하는 1회성 작업이라 세션 구분이
        # 없다. 다만 누구의 값인지는 남겨야 실험 데이터와 대조할 수 있으므로
        # 사용자 이름/ID 한 칸만 받는다(실험 도구의 참가자 ID와 같은 값을 쓰면 좋다).
        tk.Label(form, text="사용자 ID", font=self.f_mid).grid(row=0, column=0, sticky="e", padx=8, pady=6)
        self.ent_user = tk.Entry(form, font=self.f_mid, width=14)
        self.ent_user.insert(0, "P01")
        self.ent_user.grid(row=0, column=1, sticky="w", padx=8, pady=6)
        tk.Label(form, text="(실험 참가자 ID와 같은 값을 쓰면 실험 결과와 대조하기 쉽습니다)",
                 font=self.f_small, fg="gray45").grid(row=1, column=0, columnspan=2, pady=(2, 0))

        tk.Button(f, text="시  작", font=self.f_mid, width=16,
                  command=self._start).pack(pady=(20, 12))

        fw = tk.LabelFrame(f, text=" 펌웨어(.ino) ", font=self.f_small, fg="gray30")
        fw.pack(fill="x", padx=44, pady=(4, 6))
        self.lbl_fw = tk.Label(fw, font=self.f_small, fg="gray30", justify="left")
        self.lbl_fw.pack(anchor="w", padx=10, pady=(6, 4))
        row = tk.Frame(fw)
        row.pack(anchor="w", padx=10, pady=(0, 8))
        tk.Button(row, text="raw-tap 모드로 전환", font=self.f_small,
                  command=lambda: self._set_raw_mode(True)).pack(side="left", padx=(0, 6))
        tk.Button(row, text="일반 모드로 복귀", font=self.f_small,
                  command=lambda: self._set_raw_mode(False)).pack(side="left", padx=6)
        tk.Button(row, text="새로고침", font=self.f_small,
                  command=self._refresh_fw).pack(side="left", padx=6)
        self._refresh_fw()
        mp = tk.Frame(f)
        mp.pack(pady=(6, 0))
        self.lbl_mapping = tk.Label(mp, font=self.f_small, justify="left")
        self.lbl_mapping.pack(side="left")
        tk.Button(mp, text="mapping.json 찾아보기", font=self.f_small,
                  command=self._pick_mapping).pack(side="left", padx=8)
        self._refresh_mapping_label()
        tk.Label(f, text="결과 저장 위치: %s" % LOGS_DIR,
                 font=self.f_small, fg="gray40").pack(pady=(2, 0))

    def _refresh_mapping_label(self):
        if MAPPING and MAPPING_CONFLICTS:
            self.lbl_mapping.config(
                text=("매핑: %s\n※ 내용이 다른 mapping.json이 %d곳에 더 있습니다 — "
                      "복사본이 어긋나면 측정 문장이 실기기와 달라집니다:\n   %s"
                      % (MAPPING_PATH, len(MAPPING_CONFLICTS),
                         "\n   ".join(str(x) for x in MAPPING_CONFLICTS))),
                fg="#b9770e", justify="left")
        elif MAPPING:
            self.lbl_mapping.config(text="매핑: %s" % MAPPING_PATH, fg="gray40")
        else:
            self.lbl_mapping.config(
                text="매핑: 찾지 못함 — mapping.json을 지정하세요", fg="#c0392b")

    def _pick_mapping(self):
        """mapping.json을 직접 고른다(선택한 경로는 다음 실행을 위해 기억된다)."""
        path = filedialog.askopenfilename(
            title="mapping.json 선택",
            filetypes=[("mapping.json", "mapping.json"),
                       ("JSON 파일", "*.json"), ("모든 파일", "*.*")],
            initialdir=str(EXPERIMENTS_DIR if EXPERIMENTS_DIR.is_dir() else SCRIPT_DIR))
        if not path:
            return
        try:
            set_mapping_path(path)
        except (OSError, ValueError) as exc:
            messagebox.showerror("mapping.json을 읽을 수 없습니다", str(exc))
            return
        self._refresh_mapping_label()
        messagebox.showinfo("매핑 적용", "이 경로를 기억했습니다:\n%s" % MAPPING_PATH)

    def _refresh_fw(self):
        self.ino_path = find_ino_file()
        self.ino = read_ino_settings(self.ino_path) if self.ino_path else None
        if not self.ino:
            self.lbl_fw.config(
                text=("펌웨어 .ino를 찾지 못했습니다 — 결과를 자동 반영할 수 없습니다.\n"
                      "keyboard_glove.ino를 이 폴더나 ../firmware/keyboard_glove/ 에 두세요."),
                fg="#c0392b")
            return
        self.lbl_fw.config(
            text=("파일: %s\n연타 윈도우 %d ms  ·  raw-tap %s  ·  CAL_STAMP %d"
                  % (self.ino["path"], self.ino["tap_window"],
                     "ON (측정용)" if self.ino["raw_tap"] else "OFF (일반 사용)",
                     self.ino["cal_stamp"])),
            fg="#c0392b" if self.ino["raw_tap"] else "gray30")

    def _set_raw_mode(self, on):
        if not self.ino:
            messagebox.showwarning("펌웨어 없음", ".ino 파일을 찾지 못했습니다.")
            return
        if self.ino["raw_tap"] == (1 if on else 0):
            messagebox.showinfo("변경 없음", "이미 %s 상태입니다."
                                % ("raw-tap 모드" if on else "일반 모드"))
            return
        try:
            res = patch_ino(self.ino["path"], raw_tap=on)
        except (OSError, ValueError) as exc:
            messagebox.showerror("펌웨어 수정 실패", str(exc))
            return
        self._refresh_fw()
        messagebox.showinfo(
            "펌웨어 수정 완료",
            "RAW_TAP_MODE = %d 로 변경했습니다.\n\n"
            "Arduino IDE에서 이 스케치를 보드에 업로드해야 실제로 적용됩니다.\n\n"
            "백업: %s" % (1 if on else 0, res["backup"].name))

    def _start(self):
        u = self.ent_user.get().strip()
        if not u:
            messagebox.showwarning("입력 필요", "사용자 ID를 입력하세요.")
            return
        self.user = u
        stem = sanitize_id(u)
        stamp = datetime.now().strftime("%m%d_%H%M%S")
        self.jsonl_path = LOGS_DIR / ("%s_tapcal_%s.jsonl" % (stem, stamp))
        self.csv_path = LOGS_DIR / ("%s_tap_intervals_%s.csv" % (stem, stamp))
        self.summary_path = LOGS_DIR / ("%s_tap_summary_%s.csv" % (stem, stamp))

        if not MAPPING:
            messagebox.showwarning(
                "mapping.json 필요",
                "버튼↔자모 매핑이 있어야 측정 문장을 만들 수 있습니다.\n\n"
                "아래 [mapping.json 찾아보기] 버튼으로 파일을 지정하세요.\n"
                "(보통 레포의 experiments/mapping.json 입니다)")
            return
        try:
            self.trials = build_calibration_trials()
        except (RuntimeError, ValueError) as exc:
            messagebox.showerror("캘리브레이션을 시작할 수 없습니다", str(exc))
            return
        self.rows = []
        self.index = 0
        self.decision = None

        if self.ino and not self.ino["raw_tap"]:
            self._interstitial(
                title="먼저 raw-tap 모드로 전환",
                body=("측정하려면 펌웨어가 연타를 합치지 않고 물리 탭을 그대로 보내야 합니다.\n\n"
                      "아래 버튼을 누르면 .ino의 RAW_TAP_MODE를 1로 바꿔 저장합니다.\n"
                      "그다음 Arduino IDE에서 보드에 업로드한 뒤 계속 진행하세요.\n\n"
                      "현재: 윈도우 %d ms · raw-tap OFF" % self.ino["tap_window"]),
                action=self._raw_then_intro, button="RAW_TAP_MODE = 1 로 저장")
            return
        self._intro()

    def _raw_then_intro(self):
        self._set_raw_mode(True)
        self._intro()

    def _intro(self):
        fw_line = ""
        if self.ino:
            fw_line = ("\n\n현재 펌웨어: 윈도우 %d ms · raw-tap %s"
                       % (self.ino["tap_window"], "ON" if self.ino["raw_tap"] else "OFF"))
            if not self.ino["raw_tap"]:
                fw_line += "\n※ raw-tap이 OFF입니다 — 측정값이 왜곡될 수 있습니다."
        self._interstitial(
            title="측정 안내",
            body=("두 문장만 입력합니다.\n\n"
                  "1) 장갑을 raw-tap 모드로 업로드한 상태여야 합니다.\n"
                  "2) PC 입력 언어를 영문(ABC/ENG)으로 바꾸세요.\n"
                  "3) 평소 리듬으로 문장을 끝까지 입력하고 Enter를 누르세요.\n"
                  "   오타가 나도 멈추지 말고 계속 입력하면 됩니다." + fw_line),
            action=self._begin_trial)

    # -- 안내 화면 --------------------------------------------------------
    def _build_interstitial(self):
        f = self.inter_frame = tk.Frame(self.root)
        self.lbl_inter_title = tk.Label(f, font=self.f_title)
        self.lbl_inter_title.pack(pady=(46, 14))
        self.lbl_inter_body = tk.Label(f, font=self.f_mid, justify="center", wraplength=720)
        self.lbl_inter_body.pack(pady=(0, 26))
        self.btn_inter = tk.Button(f, text="계  속", font=self.f_mid, width=18)
        self.btn_inter.pack()

    def _interstitial(self, title, body, action, button="계  속"):
        self.lbl_inter_title.config(text=title)
        self.lbl_inter_body.config(text=body)
        self.btn_inter.config(command=action, text=button)
        self._show(self.inter_frame)

    # -- 측정 화면 --------------------------------------------------------
    def _build_measure(self):
        f = self.measure_frame = tk.Frame(self.root)
        top = tk.Frame(f)
        top.pack(fill="x", pady=(10, 0))
        self.lbl_status = tk.Label(top, font=self.f_small, fg="gray40")
        self.lbl_status.pack(side="left", padx=12)
        tk.Button(top, text="중단", font=self.f_small,
                  command=lambda: self._show(self.start_frame)).pack(side="right", padx=12)

        self.lbl_instr = tk.Label(f, font=self.f_mid, fg="gray30",
                                  justify="center", wraplength=720)
        self.lbl_instr.pack(pady=(20, 8))
        self.lbl_target = tk.Label(f, font=self.f_target, justify="center", wraplength=740)
        self.lbl_target.pack(padx=24, pady=(8, 16))
        self.lbl_progress = tk.Label(f, font=self.f_mid, fg="#1a5276")
        self.lbl_progress.pack(pady=(4, 8))
        self.ent_input = tk.Entry(f, font=self.f_entry, justify="center", width=18)
        self.ent_input.pack(pady=(0, 10), ipady=6)
        self.ent_input.bind("<Key>", self._on_key)
        self.lbl_feedback = tk.Label(f, font=self.f_small, fg="gray40")
        self.lbl_feedback.pack(pady=(0, 8))
        tk.Label(f, text="장갑 raw-tap 모드 · PC 영문 입력 · 띄어쓰기는 측정에서 제외 · 끝까지 입력 후 Enter",
                 font=self.f_small, fg="gray40").pack(side="bottom", pady=14)

    def _begin_trial(self):
        if self.index >= len(self.trials):
            self._finish()
            return
        self.cur = self.trials[self.index]
        self.t0 = None
        self.events = []
        self.accept = True

        self.lbl_status.config(text="%s · %d/2 · %s"
                               % (self.user, self.index + 1, self.cur["title"]))
        self.lbl_instr.config(text=(
            "평소 타이핑 리듬으로 아래 문장을 입력하세요.\n"
            + ("같은 버튼이 '서로 다른 자모' 때문에 연속되는 구간을 측정합니다."
               if self.cur["phase"] == "separate"
               else "된소리·거센소리를 만드는 2·3회 의도적 연타 간격을 측정합니다.")))
        self.lbl_target.config(text=self.cur["sentence"])
        self.lbl_feedback.config(
            text="입력 문자열은 저장하지 않고 raw keydown 시간만 측정합니다.", fg="gray40")
        self._update_progress()
        self.ent_input.config(state="normal")
        self.ent_input.delete(0, tk.END)
        self._show(self.measure_frame)
        self.ent_input.focus_set()

    def _update_progress(self):
        if not self.cur:
            return
        self.lbl_progress.config(
            text="수집된 raw keydown: %d회    ·    이 단계의 핵심 간격 후보 %d개"
            % (len(self.events), self.cur["n_focus"]))

    def _on_key(self, event):
        """raw keydown timestamp를 기록하면서 실제 입력도 Entry에 표시한다."""
        if not self.accept or self.cur is None:
            return "break"

        if event.keysym in ("Return", "KP_Enter"):
            if len(self.events) < 2:
                self.lbl_feedback.config(
                    text="측정된 키 입력이 너무 적습니다. 문장을 입력한 뒤 Enter를 누르세요.",
                    fg="#c0392b")
                return "break"
            self.accept = False
            self.lbl_feedback.config(text="입력 완료. 목표 시퀀스와 사후 정렬 중입니다.",
                                     fg="#1a5276")
            self.root.after(100, self._submit)
            return "break"

        # Space/Backspace는 타이밍 표본에서 제외하되 Entry 기본 동작은 허용
        if event.keysym in ("space", "BackSpace"):
            return None
        if event.keysym in IGNORED_KEYS:
            return "break"

        now = time.perf_counter()
        if self.t0 is None:
            self.t0 = now
        self.events.append({
            "t_ms": round((now - self.t0) * 1000.0, 2),
            "keysym": event.keysym, "char": event.char, "token": event_token(event),
        })
        self._update_progress()
        return None   # break하지 않아야 Entry에 실제 문자가 보인다

    def _submit(self):
        if self.cur is None:
            return
        trial = self.cur
        gaps, labels, alignment, edit_distance = extract_valid_gaps(
            self.events, trial["tap_plan"], trial["gap_labels"])
        n_matched = len(alignment)
        match_ratio = n_matched / len(trial["tap_plan"]) if trial["tap_plan"] else 0.0

        record = {
            "user": self.user,
            "phase": trial["phase"], "trial_index": self.index + 1,
            "target_sentence": trial["sentence"], "focus": trial["focus"],
            "match": match_ratio >= 0.90, "match_ratio": round(match_ratio, 4),
            "alignment_edit_distance": edit_distance,
            "n_expected_taps": len(trial["tap_plan"]),
            "n_observed_taps": len(self.events), "n_matched_taps": n_matched,
            "n_valid_focus_gaps": sum(1 for x in labels
                                      if x["trial_type"] == trial["focus"]),
            "visible_raw_input": self.ent_input.get(),
            "firmware_raw_tap": self.ino["raw_tap"] if self.ino else None,
            "events": self.events, "gaps_ms": gaps, "gap_labels": labels,
            "started": datetime.now().isoformat(timespec="seconds"),
        }
        self._save_trial(record)

        self.index += 1
        if self.index < len(self.trials):
            nxt = self.trials[self.index]
            self._interstitial(
                title=nxt["title"],
                body=("장갑 raw-tap 모드와 PC 영문 입력을 그대로 유지하세요.\n\n"
                      "이번에는 된소리·거센소리가 많은 문장 1개를 입력합니다.\n"
                      "끝까지 입력한 뒤 Enter를 누르세요."),
                action=self._begin_trial)
        else:
            self._finish()

    # -- 저장 -------------------------------------------------------------
    def _save_trial(self, record):
        try:
            self.rows.extend(save_trial_record(record, self.jsonl_path, self.csv_path,
                                               logs_dir=LOGS_DIR))
        except OSError as exc:
            messagebox.showerror("저장 실패", "결과 저장 중 오류가 발생했습니다:\n%s" % exc)

    # -- 결과 화면 --------------------------------------------------------
    def _build_result(self):
        f = self.result_frame = tk.Frame(self.root)
        tk.Label(f, text="캘리브레이션 완료", font=self.f_title).pack(pady=(30, 10))
        self.lbl_reco = tk.Label(f, font=self.f_mid, fg="#1a5276",
                                 justify="center", wraplength=740)
        self.lbl_reco.pack(pady=(0, 8))
        self.lbl_summary = tk.Label(f, font=self.f_small, justify="center", wraplength=760)
        self.lbl_summary.pack(pady=6)
        self.btn_apply = tk.Button(f, text="이 값을 펌웨어에 적용 (.ino 수정)",
                                   font=self.f_mid, width=30, command=self._apply)
        self.btn_apply.pack(pady=(10, 6))
        self.lbl_saved = tk.Label(f, font=self.f_small, fg="gray40",
                                  justify="center", wraplength=760)
        self.lbl_saved.pack(pady=(6, 0))
        tk.Button(f, text="처음으로", font=self.f_mid, width=16,
                  command=lambda: self._show(self.start_frame)).pack(pady=18)

    def _finish(self):
        # 라벨은 목표 시퀀스에서 도출된 정답이므로, 두 문장에서 나온 같은 라벨의
        # 표본을 모두 사용한다(표본이 많을수록 임계값 추정이 안정적).
        mt_vals, sp_vals = collect_labeled_intervals(self.rows)
        mt, sp = _stats(mt_vals), _stats(sp_vals)
        self.decision = decide_threshold(mt_vals, sp_vals)
        d = self.decision

        def fmt(st):
            if st["n"] == 0:
                return "n=0"
            return ("n=%d · 평균 %.1f ms · 중앙값 %.1f ms · SD %.1f ms"
                    % (st["n"], st["mean"], st["median"], st["sd"]))

        if d is None:
            self.lbl_reco.config(text="표본이 부족해 임계값을 계산하지 못했습니다.", fg="#c0392b")
            self.btn_apply.config(state="disabled")
        elif not d["separable"]:
            self.lbl_reco.config(
                text=("두 분포가 분리되지 않았습니다(연타 평균 ≥ 별개 입력 평균).\n"
                      "raw-tap 모드가 켜져 있었는지 확인하고 다시 측정하세요."),
                fg="#c0392b")
            self.btn_apply.config(state="disabled")
        else:
            self.lbl_reco.config(
                text=("권고 연타 판정 윈도우:  %d ms\n"
                      "이 값에서 오분류 %d개 / %d개 (%.1f%%) — 연타 분리 %d · 오병합 %d"
                      % (d["recommended_ms"], d["err_total"], mt["n"] + sp["n"],
                         d["err_pct"], d["err_split"], d["err_merged"])),
                fg="#1a5276")
            self.btn_apply.config(state="normal")

        extra = ""
        if d and d["separable"]:
            extra = ("\n두 분포 사이 여유 %.0f ms · 이론 최적 %.0f ms"
                     % (d["margin_ms"], d["optimal_raw_ms"]))
            if d["clamped"]:
                extra += "  (펌웨어 허용 범위 %d~%d ms로 조정됨)" % (WINDOW_MIN, WINDOW_MAX)
        self.lbl_summary.config(
            text=("의도적 연타(multitap): %s\n별개 입력(separate): %s%s"
                  % (fmt(mt), fmt(sp), extra)))

        self._write_summary(mt, sp, applied=False)
        self.lbl_saved.config(
            text=("저장: %s · %s\n원본 로그: %s"
                  % (self.csv_path.name, self.summary_path.name, self.jsonl_path.name)))
        self._show(self.result_frame)

    def _write_summary(self, mt, sp, applied):
        try:
            write_summary_row(self.summary_path, self.user, mt, sp, self.decision, applied)
        except OSError as exc:
            messagebox.showerror("요약 저장 실패", "요약 CSV 저장 중 오류가 발생했습니다:\n%s" % exc)

    def _apply(self):
        """권고 임계값을 .ino에 기록하고 raw-tap 모드를 되돌린다."""
        d = self.decision
        if not d:
            return
        if not self.ino:
            messagebox.showwarning(
                "펌웨어 없음",
                ".ino 파일을 찾지 못했습니다.\n\n권고값 %d ms 를 직접 "
                "TAP_WINDOW_DEFAULT 에 입력하세요." % d["recommended_ms"])
            return
        try:
            res = patch_ino(self.ino["path"], tap_window=d["recommended_ms"], raw_tap=False)
        except (OSError, ValueError) as exc:
            messagebox.showerror("펌웨어 수정 실패", str(exc))
            return

        self._refresh_fw()
        mt_vals, sp_vals = collect_labeled_intervals(self.rows)
        self._write_summary(_stats(mt_vals), _stats(sp_vals), applied=True)
        self.btn_apply.config(state="disabled", text="적용 완료 — 보드에 업로드하세요")
        messagebox.showinfo(
            "펌웨어 수정 완료",
            "TAP_WINDOW_DEFAULT: %d → %d ms\nRAW_TAP_MODE: 1 → 0\nCAL_STAMP: %d → %d\n\n"
            "Arduino IDE에서 이 스케치를 보드에 업로드하면 적용됩니다.\n"
            "(CAL_STAMP가 바뀌었으므로 보드에 저장돼 있던 옛 값 대신 이 값이 쓰입니다.)\n\n"
            "백업: %s"
            % (res["before"]["tap_window"], res["after"]["tap_window"],
               res["before"]["cal_stamp"], res["after"]["cal_stamp"], res["backup"].name))


# ---------------------------------------------------------------------------
# 저장 (GUI 없이도 검증할 수 있게 분리)
# ---------------------------------------------------------------------------
COL_TRIAL_TYPE = TAPCAL_CSV_HEADER.index("trial_type")
COL_INTERVAL = TAPCAL_CSV_HEADER.index("interval_ms")


def save_trial_record(record, jsonl_path, csv_path, logs_dir=LOGS_DIR):
    """시행 1건을 JSONL에 append하고 간격 CSV에 행들을 추가한다. -> 추가된 행 목록"""
    logs_dir.mkdir(parents=True, exist_ok=True)
    with Path(jsonl_path).open("a", encoding="utf-8") as fp:
        fp.write(json.dumps(record, ensure_ascii=False) + "\n")

    gaps, labels = record["gaps_ms"], record["gap_labels"]
    if len(gaps) != len(labels):
        return []
    rows = []
    for i, (interval, lab) in enumerate(zip(gaps, labels), start=1):
        rows.append([
            record["started"], record["user"],
            record["phase"], record["trial_index"], lab["trial_type"],
            lab["trial_type"] == record["focus"], record["target_sentence"],
            i, interval, lab["prev_jamo"], lab["next_jamo"],
            lab["prev_button"], lab["next_button"], record["match"],
        ])

    csv_path = Path(csv_path)
    new_file = not csv_path.exists()
    with csv_path.open("a", encoding="utf-8-sig" if new_file else "utf-8",
                       newline="") as fp:
        w = csv.writer(fp)
        if new_file:
            w.writerow(TAPCAL_CSV_HEADER)
        w.writerows(rows)
    return rows


def collect_labeled_intervals(rows):
    """간격 행 목록 -> (multitap 간격들, separate 간격들)"""
    mt = [r[COL_INTERVAL] for r in rows if r[COL_TRIAL_TYPE] == "multitap"]
    sp = [r[COL_INTERVAL] for r in rows if r[COL_TRIAL_TYPE] == "separate"]
    return mt, sp


def write_summary_row(summary_path, user, mt, sp, decision, applied):
    """세션 요약 1행을 기록한다."""
    midpoint = ((mt["mean"] + sp["mean"]) / 2.0
                if mt["mean"] is not None and sp["mean"] is not None else None)
    mean_gap = (sp["mean"] - mt["mean"]
                if mt["mean"] is not None and sp["mean"] is not None else None)
    summary_path = Path(summary_path)
    new_file = not summary_path.exists()
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    with summary_path.open("a", encoding="utf-8-sig" if new_file else "utf-8",
                           newline="") as fp:
        w = csv.writer(fp)
        if new_file:
            w.writerow(TAPCAL_SUMMARY_HEADER)
        w.writerow([
            datetime.now().isoformat(timespec="seconds"), user,
            mt["n"], *(("" if mt[k] is None else round(mt[k], 2))
                       for k in ("mean", "median", "sd")),
            sp["n"], *(("" if sp[k] is None else round(sp[k], 2))
                       for k in ("mean", "median", "sd")),
            "" if mean_gap is None else round(mean_gap, 2),
            "" if midpoint is None else round(midpoint, 2),
            "" if decision is None else decision["recommended_ms"],
            "" if decision is None else decision["err_split"],
            "" if decision is None else decision["err_merged"],
            "" if decision is None else decision["err_pct"],
            applied,
        ])
    return summary_path


# ---------------------------------------------------------------------------
# self-test (GUI 없이 계산 로직 검증)
# ---------------------------------------------------------------------------
def _selftest():
    ok = True

    def check(name, got, want):
        nonlocal ok
        good = got == want
        ok = ok and good
        print("%-40s %s   (got=%r)" % (name, "OK" if good else "FAIL", got))

    check("분해 학교", decompose_char("학") + decompose_char("교"),
          ["ㅎ", "ㅏ", "ㄱ", "ㄱ", "ㅛ"])
    check("분해 닭(겹받침)", decompose_char("닭"), ["ㄷ", "ㅏ", "ㄹ", "ㄱ"])
    check("분해 의(겹모음)", decompose_char("의"), ["ㅇ", "ㅡ", "ㅣ"])
    check("분해 떡(쌍자음 1자모)", decompose_char("떡"), ["ㄸ", "ㅓ", "ㄱ"])

    # 임계값: 연타 80~140, 별개 260~400 → 그 사이
    d = decide_threshold([80, 95, 110, 130, 140], [260, 300, 330, 400])
    check("임계값 분리 가능", d["separable"], True)
    check("임계값 오분류 0", d["err_total"], 0)
    print("%-40s %s" % ("임계값 권고(140~260 사이)",
                        "OK" if 140 < d["recommended_ms"] < 260 else "FAIL"))
    ok = ok and (140 < d["recommended_ms"] < 260)
    d2 = decide_threshold([100, 150, 300], [200, 320, 400])
    check("임계값 겹침 시 최소 오분류", d2["err_total"], 1)
    check("임계값 겹침 시 오병합 0", d2["err_merged"], 0)
    check("임계값 상한 클램프", decide_threshold([700, 800], [900, 1000])["recommended_ms"],
          WINDOW_MAX)
    check("임계값 표본 없음", decide_threshold([], [100, 200]), None)

    # 캘리브레이션 계획: mapping.json이 있으면 두 문장이 실제로 만들어지는지
    if MAPPING:
        trials = build_calibration_trials()
        check("시행 2개", len(trials), 2)
        sep = next(t for t in trials if t["phase"] == "separate")
        mul = next(t for t in trials if t["phase"] == "multitap")
        print("%-40s %s   (separate=%d, multitap=%d)"
              % ("두 단계 핵심 표본 존재",
                 "OK" if sep["n_focus"] >= 5 and mul["n_focus"] >= 8 else "FAIL",
                 sep["n_focus"], mul["n_focus"]))
        ok = ok and sep["n_focus"] >= 5 and mul["n_focus"] >= 8
        # 정렬: 계획대로 정확히 친 경우 모든 유효 간격이 복원되는지
        plan, labels = mul["tap_plan"], mul["gap_labels"]
        events = [{"t_ms": i * 100.0, "token": BUTTON_TO_KEYSYM[x["button"]]}
                  for i, x in enumerate(plan)]
        gaps, labs, align, ed = extract_valid_gaps(events, plan, labels)
        check("완전 일치 시 간격 수", len(gaps), len(labels))
        check("완전 일치 시 edit distance", ed, 0)
        check("간격 값 100ms", set(gaps), {100.0})
        # 중간에 오타 1개가 껴도 나머지가 살아남는지
        noisy = events[:5] + [{"t_ms": 450.0, "token": "@"}] + [
            {"t_ms": e["t_ms"] + 100.0, "token": e["token"]} for e in events[5:]]
        g2, l2, a2, ed2 = extract_valid_gaps(noisy, plan, labels)
        print("%-40s %s   (%d/%d 유효)"
              % ("오타 1개 삽입 시 대부분 생존",
                 "OK" if len(g2) >= len(labels) - 3 else "FAIL", len(g2), len(labels)))
        ok = ok and len(g2) >= len(labels) - 3
    else:
        print("%-40s SKIP  (mapping.json 없음)" % "캘리브레이션 계획")

    # .ino 패치 왕복
    import tempfile
    sample = ("#define RAW_TAP_MODE 0\n"
              "const unsigned long TAP_WINDOW_DEFAULT = 300;      // ms\n"
              "const uint16_t CAL_STAMP = 1;\n")
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        p = td / "x.ino"
        p.write_text(sample, encoding="utf-8")
        check("ino 읽기 window", read_ino_settings(p)["tap_window"], 300)
        res = patch_ino(p, tap_window=185, raw_tap=True)
        s1 = read_ino_settings(p)
        check("ino 패치 window", s1["tap_window"], 185)
        check("ino 패치 raw", s1["raw_tap"], 1)
        check("ino 스탬프 +1", s1["cal_stamp"], 2)
        check("ino 백업 존재", res["backup"].exists(), True)
        check("ino 주석 보존", "// ms" in p.read_text(encoding="utf-8"), True)
        try:
            patch_ino(p, tap_window=50)
            check("ino 범위 밖 거부", False, True)
        except ValueError:
            check("ino 범위 밖 거부", True, True)

        # 저장 경로: CSV 헤더/행, 요약, 라벨 수집
        rec = {
            "user": "P01", "phase": "multitap", "trial_index": 1, "target_sentence": "까치", "focus": "multitap",
            "match": True, "started": "2026-07-12T10:00:00",
            "gaps_ms": [95.0, 320.0],
            "gap_labels": [
                {"trial_type": "multitap", "prev_jamo": "ㄱ", "next_jamo": "ㅋ",
                 "prev_button": "L1a", "next_button": "L1a"},
                {"trial_type": "separate", "prev_jamo": "ㄱ", "next_jamo": "ㄱ",
                 "prev_button": "L1a", "next_button": "L1a"},
            ],
        }
        rows = save_trial_record(rec, td / "t.jsonl", td / "i.csv", logs_dir=td)
        check("CSV 행 2개", len(rows), 2)
        written = list(csv.reader((td / "i.csv").open(encoding="utf-8-sig")))
        check("CSV 헤더", written[0], TAPCAL_CSV_HEADER)
        check("CSV 데이터 행", len(written), 3)
        mt_vals, sp_vals = collect_labeled_intervals(rows)
        check("라벨 수집 multitap", mt_vals, [95.0])
        check("라벨 수집 separate", sp_vals, [320.0])
        dd = decide_threshold(mt_vals, sp_vals)
        write_summary_row(td / "s.csv", "P01", _stats(mt_vals), _stats(sp_vals),
                          dd, applied=True)
        srows = list(csv.reader((td / "s.csv").open(encoding="utf-8-sig")))
        check("요약 헤더", srows[0], TAPCAL_SUMMARY_HEADER)
        check("요약 권고값 기록",
              srows[1][TAPCAL_SUMMARY_HEADER.index("recommended_window_ms")],
              str(dd["recommended_ms"]))
        check("요약 열 수 일치", len(srows[1]), len(TAPCAL_SUMMARY_HEADER))

    print("\n결과:", "ALL OK" if ok else "FAILURES ABOVE")
    return 0 if ok else 1


def main():
    if "--selftest" in sys.argv:
        sys.exit(_selftest())
    if tk is None:
        print("tkinter를 불러올 수 없습니다. (Ubuntu: sudo apt install python3-tk)")
        sys.exit(1)
    root = tk.Tk()
    TapCalibrationApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
