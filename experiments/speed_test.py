#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""speed_test.py — 한글 타자 속도 실험 + 연타 판정 윈도우 캘리브레이션 GUI

서울대 창의설계축전 출품작 '장갑형 한글 키보드(Keyboard In My Hand)'의
성능 실험 도구. 장갑이 OS 레벨에서 키 입력을 보내므로, 프로그램은 일반
키보드 입력과 동일하게 취급한다.

실행    : python speed_test.py   (Python 3.8+, 표준 라이브러리만 사용)
단어 목록: 같은 폴더의 word_list_ko.txt (한 줄 1단어, '#' 주석 지원)
매핑    : 같은 폴더의 mapping.json (버튼 ↔ 자모 ↔ keysym 단일 출처)
펌웨어  : ../firmware/keyboard_glove/keyboard_glove.ino (자동 탐색)

저장    : 같은 폴더의 logs/ 아래
  1) <participant>_<session>_speed1min_<MMDD_HHMMSS>.jsonl
     — 시행(trial)당 1줄 JSON. 단어별 기록과 키 이벤트 원본 포함.
  2) speed_sessions.csv — 전체 시행 누적 요약(1행/시행, UTF-8 BOM).

────────────────────────────────────────────────────────────────────────
[모드 1] 속도 측정 (1분)
────────────────────────────────────────────────────────────────────────
랜덤 단어를 60초간 전사시키고 CPM/자모분/WPM/오류율을 계산한다.

[캐비앗 — 한글 IME와 키 이벤트]
tkinter는 한글 IME 조합(composition) 중의 키 이벤트를 플랫폼별로 다르게
전달한다(Windows는 확정 시점에 몰림, macOS는 일부 키 누락, Linux는 IME
설정에 따라 keysym이 다름). 따라서 events / n_key_events(타수)는 '참고
지표'로만 해석하고, 성능 지표(CPM, 자모/분, WPM, MSD 오류율)는 전부
Entry 위젯에 확정된 '완성된 입력 문자열' 기준으로 계산한다.

[지표 정의]
  - 음절 수      : 완성형 한글 음절(가~힣) 개수
  - 자모 수      : 음절을 자모로 분해한 개수(겹모음/겹받침 2자모, 쌍자음 1자모)
  - CPM(음절/분) : 음절 수 × 60 / 60초
  - 자모/분(jpm) : 자모 수 × 60 / 60초
  - WPM          : 자모/분 ÷ 5
  - 미수정 오류율: MSD ER = Σ MSD(목표 자모열, 입력 자모열)
                          / Σ max(len목표, len입력) × 100
                   (시간 종료 시 입력 중이던 미완성 단어는 분량 지표에는
                    포함, 오류율에서는 제외)

────────────────────────────────────────────────────────────────────────
[모드 2] 탭 간격 캘리브레이션 → 펌웨어(.ino) 설정값 자동 수정
────────────────────────────────────────────────────────────────────────
같은 버튼의 연속 눌림 사이 간격을
  (a) '의도적 연타'(한 자모를 만들기 위한 2·3회 탭)
  (b) '별개 입력'(서로 다른 자모인데 우연히 같은 버튼이 연속되는 경우)
로 라벨링해 수집하고, 두 분포를 가장 잘 가르는 임계값을 계산해
**펌웨어 소스(keyboard_glove.ino)의 TAP_WINDOW_DEFAULT 값을 직접 수정**한다.

전체 흐름(도구가 안내대로 진행):
  1) [측정 준비] 도구가 .ino의 RAW_TAP_MODE를 1로 바꾼다 → 사용자가 업로드.
     raw-tap 모드에서는 펌웨어가 연타를 합치지 않고 물리 탭을 그대로 보내므로
     PC에서 실제 탭 간격을 복원할 수 있다.
  2) [측정] 두 문장만 입력한다.
       1단계 'separate' : 같은 버튼의 '별개 입력' 경계가 많은 문장
       2단계 'multitap' : 된소리·거센소리가 많은 문장
     PC 입력 언어는 영문(ABC/ENG)으로 둔다. mapping.json의 keysym_hint로
     각 물리 탭을 목표 시퀀스에 사후 정렬하므로, 오타가 나도 문장을 끝까지
     입력하면 정확히 매칭된 구간의 간격만 유효 표본으로 추출된다.
  3) [적용] 라벨된 두 분포에서 오분류를 최소화하는 임계값을 구해
     .ino의 TAP_WINDOW_DEFAULT에 기록하고, RAW_TAP_MODE를 0으로 되돌리며,
     CAL_STAMP를 +1 한다 → 사용자가 다시 업로드하면 적용 완료.
     (CAL_STAMP가 바뀌면 펌웨어는 EEPROM에 저장된 옛 값 대신 소스 값을 쓴다.
      이 스탬프가 없으면 .ino 숫자만 고쳐도 보드가 옛 EEPROM 값을 계속 쓴다.)
  수정 전 .ino는 같은 폴더에 .ino.bak-<시각> 으로 백업된다.

저장 파일(logs/):
  - <participant>_<session>_tapcal_<시각>.jsonl        : 문장별 원본 이벤트
  - <participant>_<session>_tap_intervals_<시각>.csv   : 간격 1개당 1행
    (trial_type = multitap / separate / cross)
  - <participant>_<session>_tap_summary_<시각>.csv     : 세션 요약 + 임계값

[주의 — 측정 정확도]
이 모드의 결과는 OS IME 조합 결과가 아니라 raw QWERTY keydown 시간 자체다.
PC 입력 언어를 영문으로 두는 것이 가장 안정적이다. 더 엄밀하게는 펌웨어
시리얼 스트림(C1 명령)의 timestamp를 쓰면 OS 이벤트 지연까지 제거할 수 있다.
"""

import csv
import json
import random
import re
import shutil
import sys
import time
from collections import deque
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path

try:
    import tkinter as tk
    from tkinter import font as tkfont
    from tkinter import messagebox, ttk
except ImportError:  # headless 환경에서도 아래 계산 함수는 테스트 가능하게
    tk = None

# ---------------------------------------------------------------------------
# 경로/상수
# ---------------------------------------------------------------------------
SCRIPT_DIR = Path(__file__).resolve().parent
WORD_FILE = SCRIPT_DIR / "word_list_ko.txt"
LOGS_DIR = SCRIPT_DIR / "logs"
CSV_PATH = LOGS_DIR / "speed_sessions.csv"

TRIAL_SECONDS = 60.0
POSTURES = ("desk", "sofa", "stand")
MODES = ("속도 측정 (1분)", "탭 간격 캘리브레이션")
CSV_HEADER = [
    "timestamp", "participant", "session", "posture", "trial",
    "words_completed", "key_events", "backspace", "syllables", "jamo",
    "cpm_syl", "jpm", "wpm", "msd_error_pct",
]

# ---------------------------------------------------------------------------
# 펌웨어(.ino) 연동 — 캘리브레이션 결과를 소스 설정값에 직접 반영
# ---------------------------------------------------------------------------
# .ino의 'CALIBRATION BLOCK' 안에 있는 값 한 줄씩을 정규식으로 교체한다.
RE_RAW = re.compile(r"^(\s*#define\s+RAW_TAP_MODE\s+)(\d+)", re.M)
RE_WINDOW = re.compile(
    r"^(\s*const\s+unsigned\s+long\s+TAP_WINDOW_DEFAULT\s*=\s*)(\d+)(\s*;)", re.M)
RE_STAMP = re.compile(r"^(\s*const\s+uint16_t\s+CAL_STAMP\s*=\s*)(\d+)(\s*;)", re.M)

WINDOW_MIN, WINDOW_MAX = 100, 600   # 펌웨어가 허용하는 범위와 동일하게 유지할 것
WINDOW_ROUND = 5                    # 권고값 반올림 단위(ms)

# 탐색 순서: 스크립트 폴더 → 레포 표준 위치 → 상위 firmware 트리
INO_SEARCH_DIRS = (
    SCRIPT_DIR,
    SCRIPT_DIR / "firmware" / "keyboard_glove",
    SCRIPT_DIR.parent / "firmware" / "keyboard_glove",
    SCRIPT_DIR.parent / "firmware",
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
    # 마커가 없더라도 .ino 자체가 하나뿐이면 그것을 후보로 돌려준다(경고용).
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
        text = RE_WINDOW.sub(lambda m: "%s%d%s" % (m.group(1), w, m.group(3)), text, count=1)
    if raw_tap is not None:
        rv = 1 if raw_tap else 0
        text = RE_RAW.sub(lambda m: "%s%d" % (m.group(1), rv), text, count=1)
    if bump_stamp:
        text = RE_STAMP.sub(
            lambda m: "%s%d%s" % (m.group(1), (before["cal_stamp"] + 1) % 65536, m.group(3)),
            text, count=1)

    backup = path.with_suffix(path.suffix + ".bak-%s" % datetime.now().strftime("%m%d_%H%M%S"))
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
      - multitap 표본이 T 이상  → 연타가 분리됨(의도한 파생 자모가 안 나옴)
      - separate 표본이 T 미만  → 별개 입력이 잘못 합쳐짐(엉뚱한 자모)
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
    candidates = []
    for a, b in zip(pooled, pooled[1:]):
        if b > a:
            candidates.append(((a + b) / 2.0, b - a))
    candidates.append((pooled[0] - 1.0, 0.0))
    candidates.append((pooled[-1] + 1.0, 0.0))

    best = None  # (총오류, -여유, 임계값)
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


# 타이머 시작 전이라면 무시할 키(입력 내용에 기여하지 않는 키).
NON_STARTING_KEYS = {
    "Shift_L", "Shift_R", "Control_L", "Control_R", "Alt_L", "Alt_R",
    "Meta_L", "Meta_R", "Super_L", "Super_R", "Caps_Lock", "Num_Lock",
    "Hangul", "Hangul_Hanja", "Henkan", "Muhenkan", "Kanji",
    "space", "Return", "KP_Enter", "BackSpace", "Tab", "Escape",
}

# word_list_ko.txt가 없을 때 최소한 실행은 되도록 하는 예비 목록
FALLBACK_WORDS = [
    "사과", "학교", "컴퓨터", "도서관", "운동장", "아침", "바람", "생각",
    "친구", "가족", "시간", "하늘", "바다", "나무", "음악", "노래",
    "전화", "가방", "우산", "신발", "김치", "딸기", "떡볶이", "토끼",
    "읽다", "앉다", "먹다", "마시다", "달리다", "웃다",
]

# ---------------------------------------------------------------------------
# 탭 간격 캘리브레이션 — 두 문장만 사용
# ---------------------------------------------------------------------------
# 1단계: 서로 다른 자모인데 같은 버튼이 연속되는 경계를 의도적으로 포함.
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
    {
        "phase": "separate",
        "title": "1단계 · 별개 입력",
        "focus": "separate",
        "sentence": CALIB_SEPARATE_SENTENCE,
    },
    {
        "phase": "multitap",
        "title": "2단계 · 의도적 연타",
        "focus": "multitap",
        "sentence": CALIB_MULTITAP_SENTENCE,
    },
)

TAPCAL_CSV_HEADER = [
    "timestamp", "participant", "session", "phase", "trial_index",
    "trial_type", "use_for_calibration", "target", "gap_index", "interval_ms",
    "prev_jamo", "next_jamo", "prev_button", "next_button", "match",
]

TAPCAL_SUMMARY_HEADER = [
    "timestamp", "participant", "session",
    "n_multitap", "mean_multitap_ms", "median_multitap_ms", "sd_multitap_ms",
    "n_separate", "mean_separate_ms", "median_separate_ms", "sd_separate_ms",
    "mean_gap_ms", "midpoint_reference_ms",
    "recommended_window_ms", "err_split", "err_merged", "err_pct", "applied_to_ino",
]

# ---------------------------------------------------------------------------
# 한글 자모 분해 / MSD / 지표 계산 (GUI 없이 단독 테스트 가능)
# ---------------------------------------------------------------------------
CHOSEONG = "ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ"          # 19
JUNGSEONG = "ㅏㅐㅑㅒㅓㅔㅕㅖㅗㅘㅙㅚㅛㅜㅝㅞㅟㅠㅡㅢㅣ"     # 21
JONGSEONG = " ㄱㄲㄳㄴㄵㄶㄷㄹㄺㄻㄼㄽㄾㄿㅀㅁㅂㅄㅅㅆㅇㅈㅊㅋㅌㅍㅎ"  # 28

# 겹모음/겹받침 분해표 (쌍자음 ㄲㄸㅃㅆㅉ는 단일 자모로 취급)
COMPOUND = {
    "ㅘ": "ㅗㅏ", "ㅙ": "ㅗㅐ", "ㅚ": "ㅗㅣ", "ㅝ": "ㅜㅓ",
    "ㅞ": "ㅜㅔ", "ㅟ": "ㅜㅣ", "ㅢ": "ㅡㅣ",
    "ㄳ": "ㄱㅅ", "ㄵ": "ㄴㅈ", "ㄶ": "ㄴㅎ", "ㄺ": "ㄹㄱ",
    "ㄻ": "ㄹㅁ", "ㄼ": "ㄹㅂ", "ㄽ": "ㄹㅅ", "ㄾ": "ㄹㅌ",
    "ㄿ": "ㄹㅍ", "ㅀ": "ㄹㅎ", "ㅄ": "ㅂㅅ",
}


def decompose_char(ch):
    """한 글자를 자모 리스트로 분해한다. 한글 음절이 아니면 [ch] 그대로."""
    code = ord(ch)
    if 0xAC00 <= code <= 0xD7A3:
        code -= 0xAC00
        cho = CHOSEONG[code // 588]
        jung = JUNGSEONG[(code % 588) // 28]
        jong = JONGSEONG[code % 28]
        out = [cho]
        out.extend(COMPOUND.get(jung, jung))
        if jong != " ":
            out.extend(COMPOUND.get(jong, jong))
        return out
    if ch in COMPOUND:  # 단독 입력된 호환 자모(겹모음/겹받침)도 분해
        return list(COMPOUND[ch])
    return [ch]


def decompose_text(text):
    """문자열 전체를 자모 리스트로 분해한다. 공백은 무시."""
    jamo = []
    for ch in text:
        if ch == " ":
            continue
        jamo.extend(decompose_char(ch))
    return jamo


def msd(seq_a, seq_b):
    """두 시퀀스 간 Levenshtein(minimum string distance)."""
    la, lb = len(seq_a), len(seq_b)
    if la == 0:
        return lb
    if lb == 0:
        return la
    prev = list(range(lb + 1))
    for i in range(1, la + 1):
        cur = [i] + [0] * lb
        for j in range(1, lb + 1):
            cost = 0 if seq_a[i - 1] == seq_b[j - 1] else 1
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost)
        prev = cur
    return prev[lb]


def count_syllables(text):
    """완성형 한글 음절(가~힣) 개수."""
    return sum(1 for ch in text if 0xAC00 <= ord(ch) <= 0xD7A3)


def compute_metrics(words, duration_s=TRIAL_SECONDS):
    """'완성된 입력 문자열' 기준 성능 지표 계산.

    words: [{"target": str, "typed": str, ("partial": True)} ...]
    partial(종료 시 입력 중이던 단어)은 분량 지표에는 포함하되 오류율에서는 제외.
    """
    typed_all = "".join(w["typed"] for w in words)
    syllables = count_syllables(typed_all)
    jamo = len(decompose_text(typed_all))
    minutes = duration_s / 60.0 if duration_s > 0 else 1.0
    cpm_syl = syllables / minutes
    jpm = jamo / minutes
    wpm = jpm / 5.0

    submitted = [w for w in words if not w.get("partial")]
    num = den = 0
    for w in submitted:
        tj = decompose_text(w["target"])
        yj = decompose_text(w["typed"])
        num += msd(tj, yj)
        den += max(len(tj), len(yj))
    msd_error_pct = (num / den * 100.0) if den else 0.0

    return {
        "words_completed": len(submitted),
        "syllables": syllables,
        "jamo": jamo,
        "cpm_syl": round(cpm_syl, 2),
        "jpm": round(jpm, 2),
        "wpm": round(wpm, 2),
        "msd_error_pct": round(msd_error_pct, 2),
    }


def load_words():
    """word_list_ko.txt 로드(중복 제거, # 주석/빈 줄 무시). 없으면 예비 목록."""
    if WORD_FILE.exists():
        words, seen = [], set()
        for line in WORD_FILE.read_text(encoding="utf-8").splitlines():
            w = line.strip()
            if not w or w.startswith("#"):
                continue
            if w not in seen:
                seen.add(w)
                words.append(w)
        if words:
            return words, True
    return list(FALLBACK_WORDS), False


def sanitize_id(text):
    """파일명에 쓸 수 있게 ID 문자열 정리."""
    return "".join(ch for ch in text.strip() if ch.isalnum() or ch in "-_") or "X"


# ---------------------------------------------------------------------------
# mapping.json 로드 및 시행(trial) 생성
# ---------------------------------------------------------------------------
def load_mapping():
    """mapping.json을 읽어온다(logger.py·analyze.py와 동일한 단일 출처)."""
    path = SCRIPT_DIR / "mapping.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


MAPPING = load_mapping()
BUTTON_TO_KEYSYM = {}
if MAPPING:
    for _bid, _info in MAPPING.get("buttons", {}).items():
        _hint = str(_info.get("keysym_hint", "")).strip().lower()
        if _hint:
            BUTTON_TO_KEYSYM[_bid] = _hint


def _event_token(event):
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
                    "캘리브레이션 문장의 자모 %r 을 mapping.json으로 입력할 수 없습니다." % jamo)
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
            "mapping.json을 찾을 수 없습니다. speed_test.py와 같은 폴더에 두세요.")
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


# ---------------------------------------------------------------------------
# GUI
# ---------------------------------------------------------------------------
class SpeedTestApp:
    def __init__(self, root):
        self.root = root
        root.title("한글 타자 속도 실험 / 탭 간격 캘리브레이션")
        root.geometry("860x640")
        root.minsize(700, 560)

        base = tkfont.nametofont("TkDefaultFont")
        family = base.actual("family")
        self.f_small = tkfont.Font(family=family, size=11)
        self.f_mid = tkfont.Font(family=family, size=14)
        self.f_entry = tkfont.Font(family=family, size=22)
        self.f_timer = tkfont.Font(family=family, size=32, weight="bold")
        self.f_target = tkfont.Font(family=family, size=46, weight="bold")
        self.f_calib_target = tkfont.Font(family=family, size=24, weight="bold")

        self.pool, self.from_file = load_words()
        self.queue = deque()

        # 세션 상태
        self.mode = "speed"
        self.participant = self.session = ""
        self.posture = POSTURES[0]
        self.trial = 1
        self.jsonl_path = None

        # 펌웨어 연동 상태
        self.ino_path = find_ino_file()
        self.ino = read_ino_settings(self.ino_path) if self.ino_path else None

        # 캘리브레이션 상태
        self.calib_trials = []
        self.calib_index = 0
        self.calib_rows = []
        self.cur_calib_trial = None
        self.calib_t0 = None
        self.calib_events = []
        self.calib_accept = False
        self.calib_decision = None
        self.tapcal_csv_path = self.tapcal_summary_path = None

        # 시행 상태
        self.t0 = None
        self.trial_over = True
        self.events = []
        self.words = []
        self.n_backspace = 0
        self.started_iso = None
        self.word_t_start = 0.0
        self.current_target = ""

        self._build_start_frame()
        self._build_test_frame()
        self._build_result_frame()
        self._build_calib_frame()
        self._build_calib_interstitial_frame()
        self._build_calib_result_frame()
        self._show(self.start_frame)

    # -- 화면 전환 ----------------------------------------------------------
    def _show(self, frame):
        for f in (self.start_frame, self.test_frame, self.result_frame,
                  self.calib_frame, self.calib_inter_frame, self.calib_result_frame):
            f.pack_forget()
        frame.pack(fill="both", expand=True)

    # -- 시작 화면 ----------------------------------------------------------
    def _build_start_frame(self):
        f = self.start_frame = tk.Frame(self.root)
        tk.Label(f, text="한글 타자 속도 실험", font=self.f_timer).pack(pady=(34, 4))
        tk.Label(f, text="장갑형 한글 키보드 · 창의설계축전 성능 실험",
                 font=self.f_small, fg="gray40").pack(pady=(0, 20))

        form = tk.Frame(f)
        form.pack()
        tk.Label(form, text="실험자 ID", font=self.f_mid).grid(row=0, column=0, sticky="e", padx=8, pady=5)
        self.ent_participant = tk.Entry(form, font=self.f_mid, width=12)
        self.ent_participant.insert(0, "P01")
        self.ent_participant.grid(row=0, column=1, sticky="w", padx=8, pady=5)

        tk.Label(form, text="세션 ID", font=self.f_mid).grid(row=1, column=0, sticky="e", padx=8, pady=5)
        self.ent_session = tk.Entry(form, font=self.f_mid, width=12)
        self.ent_session.insert(0, "S1")
        self.ent_session.grid(row=1, column=1, sticky="w", padx=8, pady=5)

        tk.Label(form, text="자세 조건", font=self.f_mid).grid(row=2, column=0, sticky="e", padx=8, pady=5)
        self.cmb_posture = ttk.Combobox(form, values=list(POSTURES), state="readonly",
                                        width=10, font=self.f_mid)
        self.cmb_posture.set(POSTURES[0])
        self.cmb_posture.grid(row=2, column=1, sticky="w", padx=8, pady=5)

        tk.Label(form, text="테스트 모드", font=self.f_mid).grid(row=3, column=0, sticky="e", padx=8, pady=5)
        self.cmb_mode = ttk.Combobox(form, values=list(MODES), state="readonly",
                                     width=18, font=self.f_mid)
        self.cmb_mode.set(MODES[0])
        self.cmb_mode.grid(row=3, column=1, sticky="w", padx=8, pady=5)

        tk.Button(f, text="시  작", font=self.f_mid, width=16,
                  command=self._start_session).pack(pady=(22, 10))

        # 펌웨어 상태 패널
        fw = tk.LabelFrame(f, text=" 펌웨어(.ino) ", font=self.f_small, fg="gray30")
        fw.pack(fill="x", padx=40, pady=(4, 6))
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

        note = "단어 풀: %d개" % len(self.pool)
        if not self.from_file:
            note += "  (word_list_ko.txt 없음 — 내장 예비 목록 사용 중)"
        tk.Label(f, text=note, font=self.f_small, fg="gray40").pack()
        tk.Label(f, text="결과 저장 위치: %s" % LOGS_DIR,
                 font=self.f_small, fg="gray40").pack(pady=(2, 0))

    def _refresh_fw(self):
        self.ino_path = find_ino_file()
        self.ino = read_ino_settings(self.ino_path) if self.ino_path else None
        if not self.ino:
            self.lbl_fw.config(
                text=("펌웨어 .ino를 찾지 못했습니다 — 캘리브레이션 결과를 자동 반영할 수 없습니다.\n"
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

    def _start_session(self):
        p = self.ent_participant.get().strip()
        s = self.ent_session.get().strip()
        if not p or not s:
            messagebox.showwarning("입력 필요", "실험자 ID와 세션 ID를 입력하세요.")
            return
        self.participant, self.session = p, s
        self.posture = self.cmb_posture.get() or POSTURES[0]
        stamp = datetime.now().strftime("%m%d_%H%M%S")

        if (self.cmb_mode.get() or MODES[0]) == MODES[1]:
            self.mode = "calib"
            stem = "%s_%s" % (sanitize_id(p), sanitize_id(s))
            self.jsonl_path = LOGS_DIR / ("%s_tapcal_%s.jsonl" % (stem, stamp))
            self.tapcal_csv_path = LOGS_DIR / ("%s_tap_intervals_%s.csv" % (stem, stamp))
            self.tapcal_summary_path = LOGS_DIR / ("%s_tap_summary_%s.csv" % (stem, stamp))
            self._start_calibration()
        else:
            self.mode = "speed"
            self.trial = 1
            self.jsonl_path = LOGS_DIR / ("%s_%s_speed1min_%s.jsonl"
                                          % (sanitize_id(p), sanitize_id(s), stamp))
            self._begin_trial()

    # -- 실험 화면 ----------------------------------------------------------
    def _build_test_frame(self):
        f = self.test_frame = tk.Frame(self.root)
        top = tk.Frame(f)
        top.pack(fill="x", pady=(10, 0))
        self.lbl_status = tk.Label(top, font=self.f_small, fg="gray40")
        self.lbl_status.pack(side="left", padx=12)
        tk.Button(top, text="중단", font=self.f_small,
                  command=self._abort_trial).pack(side="right", padx=12)

        self.lbl_timer = tk.Label(f, font=self.f_timer, fg="#c0392b")
        self.lbl_timer.pack(pady=(14, 4))
        self.lbl_target = tk.Label(f, font=self.f_target)
        self.lbl_target.pack(pady=(26, 14))
        self.entry = tk.Entry(f, font=self.f_entry, justify="center", width=16)
        self.entry.pack(pady=(0, 12), ipady=6)
        self.entry.bind("<Key>", self._on_key)
        self.lbl_preview = tk.Label(f, font=self.f_mid, fg="gray50")
        self.lbl_preview.pack()
        tk.Label(f, text="첫 키 입력과 동시에 60초 시작 · 단어 입력 후 스페이스 또는 엔터 (틀려도 다음 단어로)",
                 font=self.f_small, fg="gray40").pack(side="bottom", pady=14)

    def _ensure_queue(self, n=3):
        while len(self.queue) < n:
            batch = self.pool[:]
            random.shuffle(batch)
            if self.queue and len(batch) > 1 and batch[0] == self.queue[-1]:
                batch[0], batch[1] = batch[1], batch[0]
            self.queue.extend(batch)

    def _update_word_labels(self):
        self._ensure_queue(3)
        self.current_target = self.queue[0]
        self.lbl_target.config(text=self.current_target)
        self.lbl_preview.config(text="다음:  %s   ·   %s" % (self.queue[1], self.queue[2]))

    def _begin_trial(self):
        self.t0 = None
        self.trial_over = False
        self.events = []
        self.words = []
        self.n_backspace = 0
        self.started_iso = None
        self.word_t_start = 0.0
        self.queue.clear()
        self._update_word_labels()

        self.lbl_status.config(text="%s · %s · %s · trial %d"
                               % (self.participant, self.session, self.posture, self.trial))
        self.lbl_timer.config(text="%.1f" % TRIAL_SECONDS)
        self.entry.config(state="normal")
        self.entry.delete(0, tk.END)
        self._show(self.test_frame)
        self.entry.focus_set()

    def _abort_trial(self):
        self.trial_over = True
        self._show(self.start_frame)

    def _on_key(self, event):
        if self.trial_over:
            return "break"
        now = time.perf_counter()
        if self.t0 is None:
            if event.keysym in NON_STARTING_KEYS:
                return None
            self.t0 = now
            self.started_iso = datetime.now().isoformat(timespec="seconds")
            self.word_t_start = 0.0
            self.root.after(50, self._tick)
        t = now - self.t0
        self.events.append({"t": round(t, 4), "keysym": event.keysym, "char": event.char})
        if event.keysym == "BackSpace":
            self.n_backspace += 1
        if event.keysym in ("Return", "KP_Enter", "space"):
            self.root.after_idle(self._submit_word)   # IME 확정 반영 후 읽기
            if event.keysym != "space":
                return "break"
        return None

    def _submit_word(self):
        if self.trial_over or self.t0 is None:
            return
        text = self.entry.get().strip()
        self.entry.delete(0, tk.END)
        if not text:
            return
        t_end = round(time.perf_counter() - self.t0, 4)
        self.words.append({
            "target": self.current_target, "typed": text,
            "t_start": round(self.word_t_start, 4), "t_end": t_end,
        })
        self.word_t_start = t_end
        self.queue.popleft()
        self._update_word_labels()

    def _tick(self):
        if self.trial_over or self.t0 is None:
            return
        remaining = TRIAL_SECONDS - (time.perf_counter() - self.t0)
        if remaining <= 0:
            self._end_trial()
        else:
            self.lbl_timer.config(text="%.1f" % remaining)
            self.root.after(50, self._tick)

    # -- 시행 종료/저장 ------------------------------------------------------
    def _end_trial(self):
        self.trial_over = True
        self.lbl_timer.config(text="0.0")
        partial = self.entry.get().strip()
        if partial:
            self.words.append({
                "target": self.current_target, "typed": partial,
                "t_start": round(self.word_t_start, 4),
                "t_end": round(TRIAL_SECONDS, 4), "partial": True,
            })
        self.entry.config(state="disabled")

        metrics = compute_metrics(self.words, TRIAL_SECONDS)
        record = {
            "participant": self.participant, "session": self.session,
            "posture": self.posture, "mode": "speed1min", "trial": self.trial,
            "started": self.started_iso or datetime.now().isoformat(timespec="seconds"),
            "duration_s": int(TRIAL_SECONDS), "words": self.words,
            "n_key_events": len(self.events), "n_backspace": self.n_backspace,
            "tap_window_ms": self.ino["tap_window"] if self.ino else None,
            **metrics, "events": self.events,
        }
        self._show_result(record, self._save_record(record))

    def _save_record(self, record):
        try:
            LOGS_DIR.mkdir(parents=True, exist_ok=True)
            with self.jsonl_path.open("a", encoding="utf-8") as fp:
                fp.write(json.dumps(record, ensure_ascii=False) + "\n")
            if not CSV_PATH.exists():
                with CSV_PATH.open("w", encoding="utf-8-sig", newline="") as fp:
                    csv.writer(fp).writerow(CSV_HEADER)
            with CSV_PATH.open("a", encoding="utf-8", newline="") as fp:
                csv.writer(fp).writerow([
                    record["started"], record["participant"], record["session"],
                    record["posture"], record["trial"], record["words_completed"],
                    record["n_key_events"], record["n_backspace"],
                    record["syllables"], record["jamo"], record["cpm_syl"],
                    record["jpm"], record["wpm"], record["msd_error_pct"],
                ])
            return "저장 완료:  %s  ·  %s" % (self.jsonl_path.name, CSV_PATH.name)
        except OSError as exc:
            messagebox.showerror("저장 실패", "결과 저장 중 오류가 발생했습니다:\n%s" % exc)
            return "저장 실패: %s" % exc

    # -- 결과 화면 ----------------------------------------------------------
    def _build_result_frame(self):
        f = self.result_frame = tk.Frame(self.root)
        self.lbl_result_title = tk.Label(f, font=self.f_timer)
        self.lbl_result_title.pack(pady=(34, 14))
        self.result_grid = tk.Frame(f)
        self.result_grid.pack(pady=4)
        self.lbl_saved = tk.Label(f, font=self.f_small, fg="gray40")
        self.lbl_saved.pack(pady=(14, 0))
        btns = tk.Frame(f)
        btns.pack(pady=22)
        tk.Button(btns, text="다음 회차", font=self.f_mid, width=13,
                  command=self._next_trial).pack(side="left", padx=10)
        tk.Button(btns, text="실험자 변경", font=self.f_mid, width=13,
                  command=lambda: self._show(self.start_frame)).pack(side="left", padx=10)

    def _show_result(self, record, save_msg):
        self.lbl_result_title.config(
            text="%s · %s · trial %d 결과"
                 % (record["participant"], record["session"], record["trial"]))
        for child in self.result_grid.winfo_children():
            child.destroy()
        rows = [
            ("완성 단어 수", record["words_completed"]),
            ("총 키 이벤트 수 (타수, 참고)", record["n_key_events"]),
            ("음절 수", record["syllables"]),
            ("자모 수", record["jamo"]),
            ("CPM (음절/분)", record["cpm_syl"]),
            ("자모/분", record["jpm"]),
            ("WPM (자모수/5)", record["wpm"]),
            ("미수정 오류율 MSD (%)", record["msd_error_pct"]),
            ("백스페이스 횟수", record["n_backspace"]),
        ]
        for i, (name, value) in enumerate(rows):
            tk.Label(self.result_grid, text=name, font=self.f_mid,
                     anchor="e", width=24).grid(row=i, column=0, padx=10, pady=2, sticky="e")
            tk.Label(self.result_grid, text=str(value), font=self.f_mid,
                     anchor="w", width=12, fg="#1a5276").grid(row=i, column=1, padx=10, pady=2, sticky="w")
        self.lbl_saved.config(text=save_msg)
        self._show(self.result_frame)

    def _next_trial(self):
        self.trial += 1
        self._begin_trial()

    # =========================================================================
    # 탭 간격 캘리브레이션
    # =========================================================================
    def _build_calib_interstitial_frame(self):
        f = self.calib_inter_frame = tk.Frame(self.root)
        self.lbl_inter_title = tk.Label(f, font=self.f_timer)
        self.lbl_inter_title.pack(pady=(46, 14))
        self.lbl_inter_body = tk.Label(f, font=self.f_mid, justify="center", wraplength=720)
        self.lbl_inter_body.pack(pady=(0, 26))
        self.btn_inter_next = tk.Button(f, text="계  속", font=self.f_mid, width=16)
        self.btn_inter_next.pack()

    def _show_calib_interstitial(self, title, body, next_action, button="계  속"):
        self.lbl_inter_title.config(text=title)
        self.lbl_inter_body.config(text=body)
        self.btn_inter_next.config(command=next_action, text=button)
        self._show(self.calib_inter_frame)

    def _build_calib_frame(self):
        f = self.calib_frame = tk.Frame(self.root)
        top = tk.Frame(f)
        top.pack(fill="x", pady=(10, 0))
        self.lbl_calib_status = tk.Label(top, font=self.f_small, fg="gray40")
        self.lbl_calib_status.pack(side="left", padx=12)
        tk.Button(top, text="중단", font=self.f_small,
                  command=lambda: self._show(self.start_frame)).pack(side="right", padx=12)

        self.lbl_calib_instr = tk.Label(f, font=self.f_mid, fg="gray30",
                                        justify="center", wraplength=720)
        self.lbl_calib_instr.pack(pady=(20, 8))
        self.lbl_calib_target = tk.Label(f, font=self.f_calib_target,
                                         justify="center", wraplength=740)
        self.lbl_calib_target.pack(padx=24, pady=(8, 16))
        self.lbl_calib_progress = tk.Label(f, font=self.f_mid, fg="#1a5276")
        self.lbl_calib_progress.pack(pady=(4, 8))
        self.ent_calib = tk.Entry(f, font=self.f_entry, justify="center", width=18)
        self.ent_calib.pack(pady=(0, 10), ipady=6)
        self.ent_calib.bind("<Key>", self._on_calib_key)
        self.lbl_calib_feedback = tk.Label(f, font=self.f_small, fg="gray40")
        self.lbl_calib_feedback.pack(pady=(0, 8))
        tk.Label(f, text="장갑 raw-tap 모드 · PC 영문 입력 · 띄어쓰기는 측정에서 제외 · 끝까지 입력 후 Enter",
                 font=self.f_small, fg="gray40").pack(side="bottom", pady=14)

    def _build_calib_result_frame(self):
        f = self.calib_result_frame = tk.Frame(self.root)
        tk.Label(f, text="캘리브레이션 완료", font=self.f_timer).pack(pady=(30, 10))
        self.lbl_calib_reco = tk.Label(f, font=self.f_mid, fg="#1a5276",
                                       justify="center", wraplength=740)
        self.lbl_calib_reco.pack(pady=(0, 8))
        self.lbl_calib_summary = tk.Label(f, font=self.f_small, justify="center", wraplength=760)
        self.lbl_calib_summary.pack(pady=6)
        self.btn_apply = tk.Button(f, text="이 값을 펌웨어에 적용 (.ino 수정)",
                                   font=self.f_mid, width=30, command=self._apply_to_ino)
        self.btn_apply.pack(pady=(10, 6))
        self.lbl_calib_saved = tk.Label(f, font=self.f_small, fg="gray40",
                                        justify="center", wraplength=760)
        self.lbl_calib_saved.pack(pady=(6, 0))
        tk.Button(f, text="처음으로", font=self.f_mid, width=16,
                  command=lambda: self._show(self.start_frame)).pack(pady=18)

    # -- 흐름 제어 ------------------------------------------------------------
    def _start_calibration(self):
        try:
            self.calib_trials = build_calibration_trials()
        except (RuntimeError, ValueError) as exc:
            messagebox.showerror("캘리브레이션을 시작할 수 없습니다", str(exc))
            self._show(self.start_frame)
            return

        self.calib_rows = []
        self.calib_index = 0
        self.calib_decision = None

        if self.ino and not self.ino["raw_tap"]:
            self._show_calib_interstitial(
                title="먼저 raw-tap 모드로 전환",
                body=("측정하려면 펌웨어가 연타를 합치지 않고 물리 탭을 그대로 보내야 합니다.\n\n"
                      "아래 버튼을 누르면 .ino의 RAW_TAP_MODE를 1로 바꿔 저장합니다.\n"
                      "그다음 Arduino IDE에서 보드에 업로드한 뒤 계속 진행하세요.\n\n"
                      "현재: 윈도우 %d ms · raw-tap OFF" % self.ino["tap_window"]),
                next_action=self._raw_mode_then_continue,
                button="RAW_TAP_MODE = 1 로 저장")
            return
        self._calib_intro()

    def _raw_mode_then_continue(self):
        self._set_raw_mode(True)
        self._calib_intro()

    def _calib_intro(self):
        fw_line = ""
        if self.ino:
            fw_line = ("\n\n현재 펌웨어: 윈도우 %d ms · raw-tap %s"
                       % (self.ino["tap_window"], "ON" if self.ino["raw_tap"] else "OFF"))
            if not self.ino["raw_tap"]:
                fw_line += "\n※ raw-tap이 OFF입니다 — 측정값이 왜곡될 수 있습니다."
        self._show_calib_interstitial(
            title="탭 간격 캘리브레이션",
            body=("두 문장만 입력합니다.\n\n"
                  "1) 장갑을 raw-tap 모드로 업로드한 상태여야 합니다.\n"
                  "2) PC 입력 언어를 영문(ABC/ENG)으로 바꾸세요.\n"
                  "3) 평소 리듬으로 문장을 끝까지 입력하고 Enter를 누르세요.\n"
                  "   오타가 나도 멈추지 말고 계속 입력하면 됩니다." + fw_line),
            next_action=self._begin_calib_trial)

    def _begin_calib_trial(self):
        if self.calib_index >= len(self.calib_trials):
            self._finish_calibration()
            return

        self.cur_calib_trial = self.calib_trials[self.calib_index]
        self.calib_t0 = None
        self.calib_events = []
        self.calib_accept = True
        trial = self.cur_calib_trial

        self.lbl_calib_status.config(
            text="%s · %s · %d/2 · %s"
            % (self.participant, self.session, self.calib_index + 1, trial["title"]))
        self.lbl_calib_instr.config(text=(
            "평소 타이핑 리듬으로 아래 문장을 입력하세요.\n"
            + ("같은 버튼이 '서로 다른 자모' 때문에 연속되는 구간을 측정합니다."
               if trial["phase"] == "separate"
               else "된소리·거센소리를 만드는 2·3회 의도적 연타 간격을 측정합니다.")))
        self.lbl_calib_target.config(text=trial["sentence"])
        self.lbl_calib_feedback.config(
            text="입력 문자열은 저장하지 않고 raw keydown 시간만 측정합니다.", fg="gray40")
        self._update_calib_progress()

        self.ent_calib.config(state="normal")
        self.ent_calib.delete(0, tk.END)
        self._show(self.calib_frame)
        self.ent_calib.focus_set()

    def _update_calib_progress(self):
        if not self.cur_calib_trial:
            return
        self.lbl_calib_progress.config(
            text="수집된 raw keydown: %d회    ·    이 단계의 핵심 간격 후보 %d개"
            % (len(self.calib_events), self.cur_calib_trial["n_focus"]))

    # -- 키 입력 ---------------------------------------------------------------
    def _on_calib_key(self, event):
        """raw keydown timestamp를 기록하면서 실제 입력도 Entry에 표시한다."""
        if not self.calib_accept or self.cur_calib_trial is None:
            return "break"

        if event.keysym in ("Return", "KP_Enter"):
            if len(self.calib_events) < 2:
                self.lbl_calib_feedback.config(
                    text="측정된 키 입력이 너무 적습니다. 문장을 입력한 뒤 Enter를 누르세요.",
                    fg="#c0392b")
                return "break"
            self.calib_accept = False
            self.lbl_calib_feedback.config(
                text="입력 완료. 목표 시퀀스와 사후 정렬 중입니다.", fg="#1a5276")
            self.root.after(100, self._submit_calib_trial)
            return "break"

        # Space/Backspace는 타이밍 표본에서 제외하되 Entry 기본 동작은 허용
        if event.keysym in ("space", "BackSpace"):
            return None
        if event.keysym in (
            "Tab", "Escape", "Shift_L", "Shift_R", "Control_L", "Control_R",
            "Alt_L", "Alt_R", "Meta_L", "Meta_R", "Super_L", "Super_R",
            "Caps_Lock", "Num_Lock", "Hangul", "Hangul_Hanja",
            "Henkan", "Muhenkan", "Kanji",
        ):
            return "break"

        now = time.perf_counter()
        if self.calib_t0 is None:
            self.calib_t0 = now
        self.calib_events.append({
            "t_ms": round((now - self.calib_t0) * 1000.0, 2),
            "keysym": event.keysym, "char": event.char, "token": _event_token(event),
        })
        self._update_calib_progress()
        return None   # break하지 않아야 Entry에 실제 문자가 보인다

    def _submit_calib_trial(self):
        if self.cur_calib_trial is None:
            return
        trial = self.cur_calib_trial
        plan, labels = trial["tap_plan"], trial["gap_labels"]
        alignment, edit_distance = align_observed_to_plan(self.calib_events, plan)

        # 두 목표 탭이 모두 매칭되고 실제 관측에서도 바로 연속일 때만 유효 표본
        valid_gaps, valid_labels = [], []
        for gap_idx, lab in enumerate(labels, start=1):
            prev_exp, next_exp = gap_idx - 1, gap_idx
            if prev_exp not in alignment or next_exp not in alignment:
                continue
            prev_obs, next_obs = alignment[prev_exp], alignment[next_exp]
            if next_obs != prev_obs + 1:
                continue
            valid_gaps.append(round(
                self.calib_events[next_obs]["t_ms"] - self.calib_events[prev_obs]["t_ms"], 2))
            valid_labels.append({**lab, "expected_gap_index": gap_idx})

        n_matched = len(alignment)
        match_ratio = n_matched / len(plan) if plan else 0.0
        record = {
            "participant": self.participant, "session": self.session,
            "phase": trial["phase"], "trial_index": self.calib_index + 1,
            "target_sentence": trial["sentence"], "focus": trial["focus"],
            "match": match_ratio >= 0.90, "match_ratio": round(match_ratio, 4),
            "alignment_edit_distance": edit_distance,
            "n_expected_taps": len(plan), "n_observed_taps": len(self.calib_events),
            "n_matched_taps": n_matched,
            "n_valid_focus_gaps": sum(1 for x in valid_labels
                                      if x["trial_type"] == trial["focus"]),
            "visible_raw_input": self.ent_calib.get(),
            "firmware_raw_tap": self.ino["raw_tap"] if self.ino else None,
            "events": self.calib_events, "gaps_ms": valid_gaps,
            "gap_labels": valid_labels,
            "started": datetime.now().isoformat(timespec="seconds"),
        }
        self._save_calib_record(record)

        self.calib_index += 1
        if self.calib_index < len(self.calib_trials):
            nxt = self.calib_trials[self.calib_index]
            self._show_calib_interstitial(
                title=nxt["title"],
                body=("장갑 raw-tap 모드와 PC 영문 입력을 그대로 유지하세요.\n\n"
                      "이번에는 된소리·거센소리가 많은 문장 1개를 입력합니다.\n"
                      "끝까지 입력한 뒤 Enter를 누르세요."),
                next_action=self._begin_calib_trial)
        else:
            self._finish_calibration()

    # -- 저장 ------------------------------------------------------------------
    def _save_calib_record(self, record):
        try:
            LOGS_DIR.mkdir(parents=True, exist_ok=True)
            with self.jsonl_path.open("a", encoding="utf-8") as fp:
                fp.write(json.dumps(record, ensure_ascii=False) + "\n")

            new_file = not self.tapcal_csv_path.exists()
            with self.tapcal_csv_path.open(
                    "a", encoding="utf-8-sig" if new_file else "utf-8", newline="") as fp:
                w = csv.writer(fp)
                if new_file:
                    w.writerow(TAPCAL_CSV_HEADER)
                labels, gaps = record["gap_labels"], record["gaps_ms"]
                if len(labels) != len(gaps):
                    return
                for i, (interval, lab) in enumerate(zip(gaps, labels), start=1):
                    row = [
                        record["started"], record["participant"], record["session"],
                        record["phase"], record["trial_index"], lab["trial_type"],
                        lab["trial_type"] == record["focus"], record["target_sentence"],
                        i, interval, lab["prev_jamo"], lab["next_jamo"],
                        lab["prev_button"], lab["next_button"], record["match"],
                    ]
                    w.writerow(row)
                    self.calib_rows.append(row)
        except OSError as exc:
            messagebox.showerror("저장 실패", "결과 저장 중 오류가 발생했습니다:\n%s" % exc)

    # -- 종료/요약 -------------------------------------------------------------
    def _finish_calibration(self):
        # 라벨은 목표 시퀀스에서 도출된 정답이므로, 두 문장에서 나온 같은 라벨의
        # 표본을 모두 사용한다(표본 수가 많을수록 임계값 추정이 안정적).
        # trial_type=5, interval_ms=9
        multitap_vals = [r[9] for r in self.calib_rows if r[5] == "multitap"]
        separate_vals = [r[9] for r in self.calib_rows if r[5] == "separate"]
        mt, sp = _stats(multitap_vals), _stats(separate_vals)
        self.calib_decision = decide_threshold(multitap_vals, separate_vals)

        def fmt(st):
            if st["n"] == 0:
                return "n=0"
            return ("n=%d · 평균 %.1f ms · 중앙값 %.1f ms · SD %.1f ms"
                    % (st["n"], st["mean"], st["median"], st["sd"]))

        d = self.calib_decision
        if d is None:
            self.lbl_calib_reco.config(
                text="표본이 부족해 임계값을 계산하지 못했습니다.", fg="#c0392b")
            self.btn_apply.config(state="disabled")
        elif not d["separable"]:
            self.lbl_calib_reco.config(
                text=("두 분포가 분리되지 않았습니다(연타 평균 ≥ 별개 입력 평균).\n"
                      "raw-tap 모드가 켜져 있었는지 확인하고 다시 측정하세요."),
                fg="#c0392b")
            self.btn_apply.config(state="disabled")
        else:
            self.lbl_calib_reco.config(
                text=("권고 연타 판정 윈도우:  %d ms\n"
                      "이 값에서 오분류 %d개 / %d개 (%.1f%%) — 연타 분리 %d · 오병합 %d"
                      % (d["recommended_ms"], d["err_total"],
                         mt["n"] + sp["n"], d["err_pct"],
                         d["err_split"], d["err_merged"])), fg="#1a5276")
            self.btn_apply.config(state="normal")

        extra = ""
        if d and d["separable"]:
            extra = ("\n두 분포 사이 여유 %.0f ms · 이론 최적 %.0f ms"
                     % (d["margin_ms"], d["optimal_raw_ms"]))
            if d["clamped"]:
                extra += "  (펌웨어 허용 범위 %d~%d ms로 조정됨)" % (WINDOW_MIN, WINDOW_MAX)
        self.lbl_calib_summary.config(
            text=("의도적 연타(multitap): %s\n별개 입력(separate): %s%s"
                  % (fmt(mt), fmt(sp), extra)))

        self._write_calib_summary(mt, sp, applied=False)
        self.lbl_calib_saved.config(
            text=("저장: %s · %s\n원본 로그: %s"
                  % (self.tapcal_csv_path.name, self.tapcal_summary_path.name,
                     self.jsonl_path.name)))
        self._show(self.calib_result_frame)

    def _write_calib_summary(self, mt, sp, applied):
        d = self.calib_decision
        midpoint = ((mt["mean"] + sp["mean"]) / 2.0
                    if mt["mean"] is not None and sp["mean"] is not None else None)
        mean_gap = (sp["mean"] - mt["mean"]
                    if mt["mean"] is not None and sp["mean"] is not None else None)
        try:
            new_file = not self.tapcal_summary_path.exists()
            with self.tapcal_summary_path.open(
                    "a", encoding="utf-8-sig" if new_file else "utf-8", newline="") as fp:
                w = csv.writer(fp)
                if new_file:
                    w.writerow(TAPCAL_SUMMARY_HEADER)
                w.writerow([
                    datetime.now().isoformat(timespec="seconds"),
                    self.participant, self.session,
                    mt["n"], *(("" if mt[k] is None else round(mt[k], 2))
                               for k in ("mean", "median", "sd")),
                    sp["n"], *(("" if sp[k] is None else round(sp[k], 2))
                               for k in ("mean", "median", "sd")),
                    "" if mean_gap is None else round(mean_gap, 2),
                    "" if midpoint is None else round(midpoint, 2),
                    "" if d is None else d["recommended_ms"],
                    "" if d is None else d["err_split"],
                    "" if d is None else d["err_merged"],
                    "" if d is None else d["err_pct"],
                    applied,
                ])
        except OSError as exc:
            messagebox.showerror("요약 저장 실패", "요약 CSV 저장 중 오류가 발생했습니다:\n%s" % exc)

    def _apply_to_ino(self):
        """권고 임계값을 .ino에 기록하고 raw-tap 모드를 되돌린다."""
        d = self.calib_decision
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
        self._write_calib_summary(_stats([r[9] for r in self.calib_rows if r[5] == "multitap"]),
                                  _stats([r[9] for r in self.calib_rows if r[5] == "separate"]),
                                  applied=True)
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
# self-test (GUI 없이 계산 로직 검증)
# ---------------------------------------------------------------------------
def _selftest():
    ok = True

    def check(name, got, want):
        nonlocal ok
        good = got == want
        ok = ok and good
        print("%-38s %s   (got=%r)" % (name, "OK" if good else "FAIL", got))

    check("decompose 학교", decompose_text("학교"), ["ㅎ", "ㅏ", "ㄱ", "ㄱ", "ㅛ"])
    check("decompose 닭(겹받침)", decompose_text("닭"), ["ㄷ", "ㅏ", "ㄹ", "ㄱ"])
    check("decompose 의(겹모음)", decompose_text("의"), ["ㅇ", "ㅡ", "ㅣ"])
    check("decompose 떡(쌍자음 1자모)", decompose_text("떡"), ["ㄸ", "ㅓ", "ㄱ"])
    check("msd 동일", msd(list("abc"), list("abc")), 0)
    check("msd 치환 1", msd(list("사과"), list("샤과")), 1)
    m = compute_metrics([{"target": "사과", "typed": "사과"}], 60.0)
    check("metrics 음절", m["syllables"], 2)
    check("metrics 자모", m["jamo"], 5)
    check("metrics CPM", m["cpm_syl"], 2.0)
    check("metrics WPM", m["wpm"], 1.0)
    check("metrics 오류율 0", m["msd_error_pct"], 0.0)

    # 임계값 결정: 연타 80~140, 별개 260~400 → 그 사이 어딘가
    d = decide_threshold([80, 95, 110, 130, 140], [260, 300, 330, 400])
    check("threshold 분리 가능", d["separable"], True)
    check("threshold 오분류 0", d["err_total"], 0)
    print("%-38s %s" % ("threshold 권고값(140~260 사이)",
                        "OK" if 140 < d["recommended_ms"] < 260 else "FAIL"))
    ok = ok and (140 < d["recommended_ms"] < 260)
    # 겹치는 분포: 최소 오분류를 찾는지 (T≈175에서 연타 300 하나만 분리 → 1)
    d2 = decide_threshold([100, 150, 300], [200, 320, 400])
    check("threshold 겹침 시 최소 오분류", d2["err_total"], 1)
    check("threshold 겹침 시 오병합 0", d2["err_merged"], 0)
    # 클램프: 두 분포가 모두 매우 크면 상한으로
    d3 = decide_threshold([700, 800], [900, 1000])
    check("threshold 상한 클램프", d3["recommended_ms"], WINDOW_MAX)

    # .ino 패치 왕복 테스트
    import tempfile
    sample = ("#define RAW_TAP_MODE 0\n"
              "const unsigned long TAP_WINDOW_DEFAULT = 300;      // ms\n"
              "const uint16_t CAL_STAMP = 1;\n")
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "x.ino"
        p.write_text(sample, encoding="utf-8")
        s0 = read_ino_settings(p)
        check("ino 읽기 window", s0["tap_window"], 300)
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

    print("\n결과:", "ALL OK" if ok else "FAILURES ABOVE")
    return 0 if ok else 1


def main():
    if "--selftest" in sys.argv:
        sys.exit(_selftest())
    if tk is None:
        print("tkinter를 불러올 수 없습니다. Python 표준 GUI(tkinter)가 포함된 "
              "배포판인지 확인하세요. (Ubuntu: sudo apt install python3-tk)")
        sys.exit(1)
    root = tk.Tk()
    SpeedTestApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
