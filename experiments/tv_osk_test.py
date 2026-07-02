#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tv_osk_test.py — 커서 선택형 화면 키보드(TV 리모컨식) 한글 전사 실험 GUI

서울대 창의설계축전 출품작 '장갑형 한글 키보드' 비교 실험(실험 D)의
대조군 도구. 스마트TV/VR에서 쓰는 '방향키로 커서를 옮겨 화면 키보드의
자모를 하나씩 선택'하는 입력 방식을 시뮬레이션한다. 참가자는 같은
문장 세트를 ①장갑 키보드 ②이 시뮬레이터로 입력해 속도·오류율을 비교한다.

실행    : python tv_osk_test.py          (Python 3.8+, 표준 라이브러리만 사용)
자가진단: python tv_osk_test.py --selftest   (GUI 없이 조합 오토마타/지표 테스트)
문장 목록: 같은 폴더의 phrase_set_ko.txt (한 줄 1문장, '#' 주석 지원,
          없으면 내장 10문장 사용)
저장    : 같은 폴더의 logs/ 아래
  1) <participant>_<session>_tvosk_<MMDD_HHMMSS>.jsonl
     — 제출 문장당 1줄 JSON. 파일은 [시작] 시점에 1개 만들어지고
       같은 세션의 여러 문장이 줄 단위로 append 된다.
  2) tvosk_sessions.csv — 전체 문장 누적 요약(1행/문장, speed_sessions.csv와
     같은 컨벤션). 엑셀에서 바로 열 수 있다(UTF-8 BOM은 최초 생성 시 1회만).

[조작 — TV 리모컨 방식]
  방향키 ←↑↓→ : 커서 이동 (격자 밖으로는 이동 안 됨, 누른 횟수는 모두 기록)
  Enter        : 현재 셀 선택 (자모 입력 / Shift 토글 / Space / 지우기 / 완료)
  Esc          : 현재 문장 즉시 제출(= 완료 셀과 동일)
  Shift 셀     : 다음 자모 1회를 쌍자음/이중모음으로 (ㄱ→ㄲ ㄷ→ㄸ ㅂ→ㅃ
                 ㅅ→ㅆ ㅈ→ㅉ ㅐ→ㅒ ㅔ→ㅖ). 다시 선택하면 해제.
  지우기 셀    : 자모 단위 백스페이스 (조합 중 음절은 자모부터 지움)

[한글 조합 — 단순 두벌식 오토마타]
  초성-중성-종성 규칙으로 음절을 조합한다.
  - 도깨비불: 종성 뒤에 모음이 오면 종성이 다음 음절 초성으로 이동
    (값+ㅣ→갑시, 국+ㄱ+ㅏ→국가)
  - 겹받침 조합: ㄳ ㄵ ㄶ ㄺ ㄻ ㄼ ㄽ ㄾ ㄿ ㅀ ㅄ (ㄱ+ㅅ→ㄳ 등)
  - 겹모음 조합: ㅘ ㅙ ㅚ ㅝ ㅞ ㅟ ㅢ (ㅗ+ㅏ→ㅘ 등)
  - 자음 연타(ㄱㄱ 등)는 자동으로 쌍자음이 되지 않음 — Shift 셀을 사용

[측정 규약]
  - 문장 타이머는 해당 문장에서의 '첫 키 입력'(방향키/Enter 모두 포함)부터
    '완료 선택 또는 Esc'까지.
  - 커서는 문장마다 좌상단(ㄱ)으로 리셋 — 문장 간 조건을 동일하게 유지.
  - n_moves: 방향키 누른 횟수(벽에 막혀 이동하지 못한 누름도 포함 — 사용자
    노력 기준). n_selects: Enter 누른 횟수(Shift/지우기/완료 선택 포함).
  - 세션은 15분 카운트다운(기본값, 시작 화면에서 변경 가능) 또는
    [세션 종료] 버튼으로 끝난다. 세션 종료 시 입력 중이던 미완성 문장은
    기록하지 않는다(불완전 시행). 키 입력이 전혀 없었던 문장의 제출(Esc)은
    '건너뛰기'로 간주해 기록하지 않는다.

[지표 정의 — speed_test.py와 동일 규약]
  - 음절 수       : 입력된 완성형 한글 음절(가~힣) 개수
  - 자모 수       : 자모 분해 개수(겹모음/겹받침 2자모, 쌍자음 1자모, 공백 제외)
  - CPM(음절/분)  : 음절 수 / 소요시간(분)
  - 자모/분(jpm)  : 자모 수 / 소요시간(분)
  - WPM           : 자모/분 ÷ 5
  - MSD 오류율    : MSD(목표 자모열, 입력 자모열) / max(len) × 100
  - moves_per_jamo: n_moves / 자모 수 (KSPC 유사 — 자모 1개당 커서 이동)
  - kspc_jamo     : (n_moves + n_selects) / 자모 수 (총 키 누름 기준 KSPC)
"""

import csv
import json
import random
import sys
import time
from collections import deque
from datetime import datetime
from pathlib import Path

try:
    import tkinter as tk
    from tkinter import font as tkfont
    from tkinter import messagebox
except ImportError:  # headless 환경에서도 조합/지표 함수는 테스트 가능하게
    tk = None

# ---------------------------------------------------------------------------
# 경로/상수
# ---------------------------------------------------------------------------
SCRIPT_DIR = Path(__file__).resolve().parent
PHRASE_FILE = SCRIPT_DIR / "phrase_set_ko.txt"
LOGS_DIR = SCRIPT_DIR / "logs"
CSV_PATH = LOGS_DIR / "tvosk_sessions.csv"

DEFAULT_SESSION_MIN = 15
CSV_HEADER = [
    "timestamp", "participant", "session", "trial", "target", "typed",
    "duration_s", "n_moves", "n_selects", "syllables", "jamo",
    "cpm_syl", "jpm", "wpm", "msd_error_pct", "moves_per_jamo", "kspc_jamo",
]

FALLBACK_PHRASES = [
    "오늘 날씨가 정말 좋다",
    "내일 아침에 일찍 일어나야 한다",
    "커피 한 잔 마시고 싶다",
    "버스가 아직 오지 않았다",
    "주말에 영화 보러 가자",
    "도서관에서 책을 세 권 빌렸다",
    "비가 와서 우산을 챙겨야 한다",
    "친구와 저녁을 먹기로 했다",
    "음악을 들으면서 산책을 했다",
    "시험 공부는 미리 시작하는 게 좋다",
]

# ---------------------------------------------------------------------------
# 한글 자모 테이블 (분해 스펙 — speed_test.py와 동일)
# ---------------------------------------------------------------------------
CHOSEONG = "ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ"          # 19
JUNGSEONG = "ㅏㅐㅑㅒㅓㅔㅕㅖㅗㅘㅙㅚㅛㅜㅝㅞㅟㅠㅡㅢㅣ"     # 21
JONGSEONG = " ㄱㄲㄳㄴㄵㄶㄷㄹㄺㄻㄼㄽㄾㄿㅀㅁㅂㅄㅅㅆㅇㅈㅊㅋㅌㅍㅎ"  # 28 (첫 칸=받침 없음)

# 겹모음/겹받침 분해표 (오류율 계산용. 쌍자음 ㄲㄸㅃㅆㅉ는 단일 자모)
COMPOUND = {
    "ㅘ": "ㅗㅏ", "ㅙ": "ㅗㅐ", "ㅚ": "ㅗㅣ", "ㅝ": "ㅜㅓ",
    "ㅞ": "ㅜㅔ", "ㅟ": "ㅜㅣ", "ㅢ": "ㅡㅣ",
    "ㄳ": "ㄱㅅ", "ㄵ": "ㄴㅈ", "ㄶ": "ㄴㅎ", "ㄺ": "ㄹㄱ",
    "ㄻ": "ㄹㅁ", "ㄼ": "ㄹㅂ", "ㄽ": "ㄹㅅ", "ㄾ": "ㄹㅌ",
    "ㄿ": "ㄹㅍ", "ㅀ": "ㄹㅎ", "ㅄ": "ㅂㅅ",
}

# 조합용 결합표 (입력 오토마타용 — 분해표의 역방향)
VOWEL_COMBINE = {"ㅗㅏ": "ㅘ", "ㅗㅐ": "ㅙ", "ㅗㅣ": "ㅚ", "ㅜㅓ": "ㅝ",
                 "ㅜㅔ": "ㅞ", "ㅜㅣ": "ㅟ", "ㅡㅣ": "ㅢ"}
JONG_COMBINE = {"ㄱㅅ": "ㄳ", "ㄴㅈ": "ㄵ", "ㄴㅎ": "ㄶ", "ㄹㄱ": "ㄺ",
                "ㄹㅁ": "ㄻ", "ㄹㅂ": "ㄼ", "ㄹㅅ": "ㄽ", "ㄹㅌ": "ㄾ",
                "ㄹㅍ": "ㄿ", "ㄹㅎ": "ㅀ", "ㅂㅅ": "ㅄ"}
JONG_SPLIT = {v: (k[0], k[1]) for k, v in JONG_COMBINE.items()}
VOWEL_REDUCE = {v: k[0] for k, v in VOWEL_COMBINE.items()}  # 백스페이스용

# 두벌식 Shift 규칙
SHIFT_MAP = {"ㄱ": "ㄲ", "ㄷ": "ㄸ", "ㅂ": "ㅃ", "ㅅ": "ㅆ", "ㅈ": "ㅉ",
             "ㅐ": "ㅒ", "ㅔ": "ㅖ"}

# 화면 키보드 격자 (행별 셀 목록: ("jamo", 자모) 또는 기능 셀)
GRID_ROWS = [
    [("jamo", c) for c in "ㄱㄴㄷㄹㅁㅂㅅㅇ"],
    [("jamo", c) for c in "ㅈㅊㅋㅌㅍㅎㅏㅑ"],
    [("jamo", c) for c in "ㅓㅕㅗㅛㅜㅠㅡㅣ"],
    [("jamo", "ㅐ"), ("jamo", "ㅔ"),
     ("shift", "Shift"), ("space", "Space"), ("bksp", "지우기"), ("done", "완료")],
]


# ---------------------------------------------------------------------------
# 한글 조합 오토마타 (GUI 없이 단독 테스트 가능)
# ---------------------------------------------------------------------------
class HangulComposer:
    """단순 두벌식 오토마타.

    자모(호환 자모 문자)를 하나씩 받아 초성-중성-종성 규칙으로 음절을
    조합한다. 도깨비불(종성→다음 초성 이동), 겹받침/겹모음 결합 지원.
    쌍자음/이중모음(ㅒㅖ)은 Shift가 적용된 자모가 직접 들어온다고 가정.
    """

    def __init__(self):
        self.committed = []          # 확정된 문자들
        self.cho = None              # 조합 중 초성 (호환 자모 문자)
        self.jung = None             # 조합 중 중성 (겹모음이면 ㅘ 등 결합형)
        self.jong = None             # 조합 중 종성 (겹받침이면 ㄳ 등 결합형)

    # -- 상태 조회 -----------------------------------------------------------
    def _render_current(self):
        if self.cho is not None and self.jung is not None:
            cho_i = CHOSEONG.index(self.cho)
            jung_i = JUNGSEONG.index(self.jung)
            jong_i = JONGSEONG.index(self.jong) if self.jong else 0
            return chr(0xAC00 + cho_i * 588 + jung_i * 28 + jong_i)
        if self.cho is not None:
            return self.cho
        if self.jung is not None:
            return self.jung
        return ""

    def text(self):
        return "".join(self.committed) + self._render_current()

    # -- 내부 ----------------------------------------------------------------
    def _commit(self):
        cur = self._render_current()
        if cur:
            self.committed.append(cur)
        self.cho = self.jung = self.jong = None

    # -- 입력 ----------------------------------------------------------------
    def input_jamo(self, j):
        if j in CHOSEONG:
            self._input_consonant(j)
        elif j in JUNGSEONG:
            self._input_vowel(j)
        else:  # 예상 밖 문자는 그대로 확정
            self._commit()
            self.committed.append(j)

    def _input_consonant(self, c):
        if self.jung is None:
            # (빈 상태) / (초성만) / — 초성 연타는 앞 자모를 확정하고 새로 시작
            if self.cho is None:
                self.cho = c
            else:
                self._commit()
                self.cho = c
        elif self.cho is None:
            # 단독 모음 조합 중 → 모음 확정 후 새 초성
            self._commit()
            self.cho = c
        elif self.jong is None:
            if c in JONGSEONG:            # 종성 가능 자음(ㄸㅃㅉ 제외)
                self.jong = c
            else:
                self._commit()
                self.cho = c
        else:
            comb = JONG_COMBINE.get(self.jong + c)
            if comb:
                self.jong = comb          # 겹받침 (ㄱ+ㅅ→ㄳ 등)
            else:
                self._commit()
                self.cho = c

    def _input_vowel(self, v):
        if self.jong is not None:
            # 도깨비불: 종성(또는 겹받침 뒷자음)이 다음 음절 초성으로 이동
            if self.jong in JONG_SPLIT:
                keep, move = JONG_SPLIT[self.jong]
            else:
                keep, move = None, self.jong
            self.jong = keep
            self._commit()
            self.cho, self.jung = move, v
        elif self.jung is None:
            self.jung = v                 # 초성 유무 무관 (단독 모음 허용)
        else:
            comb = VOWEL_COMBINE.get(self.jung + v)
            if comb:
                self.jung = comb          # 겹모음 (ㅗ+ㅏ→ㅘ 등)
            else:
                self._commit()            # 결합 불가 → 새 단독 모음
                self.jung = v

    def input_space(self):
        self._commit()
        self.committed.append(" ")

    def backspace(self):
        """자모 단위 백스페이스. 확정된 글자는 통째로 지움(일반 IME와 동일)."""
        if self.jong is not None:
            self.jong = JONG_SPLIT[self.jong][0] if self.jong in JONG_SPLIT else None
        elif self.jung is not None:
            self.jung = VOWEL_REDUCE.get(self.jung)  # 겹모음→첫 성분, 아니면 None
        elif self.cho is not None:
            self.cho = None
        elif self.committed:
            self.committed.pop()


# ---------------------------------------------------------------------------
# 자모 분해 / MSD / 지표 계산 (speed_test.py와 동일 규약)
# ---------------------------------------------------------------------------
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
    if ch in COMPOUND:  # 단독 입력된 겹모음/겹받침도 분해
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


def compute_sentence_metrics(target, typed, duration_s, n_moves, n_selects):
    """제출된 한 문장의 성능 지표 계산."""
    syllables = count_syllables(typed)
    jamo = len(decompose_text(typed))
    minutes = max(duration_s, 1e-6) / 60.0
    tj = decompose_text(target)
    yj = decompose_text(typed)
    den = max(len(tj), len(yj))
    msd_error_pct = (msd(tj, yj) / den * 100.0) if den else 0.0
    return {
        "syllables": syllables,
        "jamo": jamo,
        "cpm_syl": round(syllables / minutes, 2),
        "jpm": round(jamo / minutes, 2),
        "wpm": round(jamo / minutes / 5.0, 2),
        "msd_error_pct": round(msd_error_pct, 2),
        "moves_per_jamo": round(n_moves / jamo, 2) if jamo else 0.0,
        "kspc_jamo": round((n_moves + n_selects) / jamo, 2) if jamo else 0.0,
    }


def load_phrases():
    """phrase_set_ko.txt 로드(# 주석/빈 줄 무시). 없으면 내장 10문장."""
    if PHRASE_FILE.exists():
        phrases = []
        for line in PHRASE_FILE.read_text(encoding="utf-8").splitlines():
            s = line.strip()
            if not s or s.startswith("#"):
                continue
            phrases.append(s)
        if phrases:
            return phrases, True
    return list(FALLBACK_PHRASES), False


def sanitize_id(text):
    """파일명에 쓸 수 있게 ID 문자열 정리."""
    return "".join(ch for ch in text.strip() if ch.isalnum() or ch in "-_") or "X"


# ---------------------------------------------------------------------------
# GUI
# ---------------------------------------------------------------------------
BORDER_NORMAL = "#9e9e9e"
BORDER_CURSOR = "#d35400"
BG_CONS = "#e8eef7"      # 자음 셀
BG_VOWEL = "#fbf1e0"     # 모음 셀
BG_FUNC = "#e4e4e4"      # 기능 셀
BG_CURSOR = "#ffd54f"    # 커서 셀
BG_SHIFT_ON = "#aed6f1"  # Shift 래치 표시


class TvOskApp:
    def __init__(self, root):
        self.root = root
        root.title("TV 리모컨식 화면 키보드 전사 실험")
        root.geometry("900x680")
        root.minsize(760, 600)

        base = tkfont.nametofont("TkDefaultFont")
        family = base.actual("family")
        self.f_small = tkfont.Font(family=family, size=11)
        self.f_mid = tkfont.Font(family=family, size=14)
        self.f_timer = tkfont.Font(family=family, size=26, weight="bold")
        self.f_target = tkfont.Font(family=family, size=24, weight="bold")
        self.f_typed = tkfont.Font(family=family, size=22)
        self.f_key = tkfont.Font(family=family, size=18, weight="bold")
        self.f_title = tkfont.Font(family=family, size=30, weight="bold")

        self.pool, self.from_file = load_phrases()
        self.queue = deque()

        # 세션 상태
        self.participant = ""
        self.session = ""
        self.session_seconds = DEFAULT_SESSION_MIN * 60
        self.jsonl_path = None
        self.in_test = False
        self.session_t_end = None
        self.trial = 0               # 제출(기록)된 문장 수
        self.records = []

        # 문장(시행) 상태
        self.composer = HangulComposer()
        self.cursor = [0, 0]
        self.shift_on = False
        self.t0 = None
        self.started_iso = None
        self.n_moves = 0
        self.n_selects = 0
        self.current_target = ""

        self._build_start_frame()
        self._build_test_frame()
        self._build_result_frame()
        self._show(self.start_frame)

        root.bind("<Left>", lambda e: self._on_move(0, -1))
        root.bind("<Right>", lambda e: self._on_move(0, 1))
        root.bind("<Up>", lambda e: self._on_move(-1, 0))
        root.bind("<Down>", lambda e: self._on_move(1, 0))
        root.bind("<Return>", self._on_enter)
        root.bind("<KP_Enter>", self._on_enter)
        root.bind("<Escape>", lambda e: self._submit_sentence() if self.in_test else None)

    # -- 화면 전환 ------------------------------------------------------------
    def _show(self, frame):
        for f in (self.start_frame, self.test_frame, self.result_frame):
            f.pack_forget()
        frame.pack(fill="both", expand=True)

    # -- 시작 화면 ------------------------------------------------------------
    def _build_start_frame(self):
        f = self.start_frame = tk.Frame(self.root)
        tk.Label(f, text="화면 키보드 전사 실험 (TV 리모컨식)", font=self.f_title).pack(pady=(46, 4))
        tk.Label(f, text="장갑형 한글 키보드 · 창의설계축전 비교 실험 D 대조군",
                 font=self.f_small, fg="gray40").pack(pady=(0, 26))

        form = tk.Frame(f)
        form.pack()
        tk.Label(form, text="실험자 ID", font=self.f_mid).grid(row=0, column=0, sticky="e", padx=8, pady=6)
        self.ent_participant = tk.Entry(form, font=self.f_mid, width=12)
        self.ent_participant.insert(0, "P01")
        self.ent_participant.grid(row=0, column=1, sticky="w", padx=8, pady=6)

        tk.Label(form, text="세션 ID", font=self.f_mid).grid(row=1, column=0, sticky="e", padx=8, pady=6)
        self.ent_session = tk.Entry(form, font=self.f_mid, width=12)
        self.ent_session.insert(0, "S1")
        self.ent_session.grid(row=1, column=1, sticky="w", padx=8, pady=6)

        tk.Label(form, text="세션 길이(분)", font=self.f_mid).grid(row=2, column=0, sticky="e", padx=8, pady=6)
        self.ent_minutes = tk.Entry(form, font=self.f_mid, width=12)
        self.ent_minutes.insert(0, str(DEFAULT_SESSION_MIN))
        self.ent_minutes.grid(row=2, column=1, sticky="w", padx=8, pady=6)

        tk.Button(f, text="시  작", font=self.f_mid, width=16,
                  command=self._start_session).pack(pady=30)

        note = "문장 풀: %d개" % len(self.pool)
        if not self.from_file:
            note += "  (phrase_set_ko.txt 없음 — 내장 10문장 사용 중)"
        tk.Label(f, text=note, font=self.f_small, fg="gray40").pack()
        tk.Label(f, text="결과 저장 위치: %s" % LOGS_DIR,
                 font=self.f_small, fg="gray40").pack(pady=(2, 0))

    def _start_session(self):
        p = self.ent_participant.get().strip()
        s = self.ent_session.get().strip()
        if not p or not s:
            messagebox.showwarning("입력 필요", "실험자 ID와 세션 ID를 입력하세요.")
            return
        try:
            minutes = float(self.ent_minutes.get().strip() or DEFAULT_SESSION_MIN)
            if minutes <= 0:
                raise ValueError
        except ValueError:
            messagebox.showwarning("입력 필요", "세션 길이(분)는 양수로 입력하세요.")
            return
        self.participant = p
        self.session = s
        self.session_seconds = minutes * 60.0
        self.trial = 0
        self.records = []
        stamp = datetime.now().strftime("%m%d_%H%M%S")
        self.jsonl_path = LOGS_DIR / ("%s_%s_tvosk_%s.jsonl"
                                      % (sanitize_id(p), sanitize_id(s), stamp))
        self.queue.clear()
        self.in_test = True
        self.session_t_end = time.perf_counter() + self.session_seconds
        self._begin_sentence()
        self._show(self.test_frame)
        self.test_frame.focus_set()
        self._tick()

    # -- 실험 화면 ------------------------------------------------------------
    def _build_test_frame(self):
        f = self.test_frame = tk.Frame(self.root)

        top = tk.Frame(f)
        top.pack(fill="x", pady=(10, 0))
        self.lbl_status = tk.Label(top, font=self.f_small, fg="gray40")
        self.lbl_status.pack(side="left", padx=12)
        tk.Button(top, text="세션 종료", font=self.f_small,
                  command=self._end_session).pack(side="right", padx=12)
        self.lbl_timer = tk.Label(top, font=self.f_timer, fg="#1a5276")
        self.lbl_timer.pack(side="right", padx=12)

        tk.Label(f, text="목표 문장", font=self.f_small, fg="gray40").pack(pady=(16, 0))
        self.lbl_target = tk.Label(f, font=self.f_target, wraplength=820, justify="center")
        self.lbl_target.pack(pady=(2, 10))

        self.lbl_typed = tk.Label(f, font=self.f_typed, anchor="w", relief="sunken",
                                  bd=2, padx=10, pady=8, bg="white", width=44)
        self.lbl_typed.pack(pady=(0, 8), padx=24, fill="x")

        self.kb_frame = tk.Frame(f)
        self.kb_frame.pack(pady=(6, 4))
        self._build_keyboard(self.kb_frame)

        tk.Label(f, text="방향키 ←↑↓→ 커서 이동 · Enter 선택 · Shift 셀 = 쌍자음/ㅒㅖ · Esc = 문장 제출",
                 font=self.f_small, fg="gray40").pack(side="bottom", pady=10)

    def _build_keyboard(self, parent):
        self.cells = []
        for r, row_spec in enumerate(GRID_ROWS):
            row_cells = []
            for c, (kind, label) in enumerate(row_spec):
                outer = tk.Frame(parent, bg=BORDER_NORMAL)
                width = 4 if kind == "jamo" else 6
                lbl = tk.Label(outer, text=label, font=self.f_key, width=width,
                               height=1, bg=self._cell_bg(kind, label))
                lbl.pack(padx=3, pady=3)
                outer.grid(row=r, column=c, padx=3, pady=3)
                row_cells.append({"kind": kind, "char": label,
                                  "outer": outer, "lbl": lbl})
            self.cells.append(row_cells)
        self._paint_cursor()

    @staticmethod
    def _cell_bg(kind, label):
        if kind == "jamo":
            return BG_CONS if label in CHOSEONG else BG_VOWEL
        return BG_FUNC

    def _paint_cursor(self):
        cr, cc = self.cursor
        for r, row in enumerate(self.cells):
            for c, cell in enumerate(row):
                is_cur = (r == cr and c == cc)
                cell["outer"].config(bg=BORDER_CURSOR if is_cur else BORDER_NORMAL)
                if is_cur:
                    bg = BG_CURSOR
                elif cell["kind"] == "shift" and self.shift_on:
                    bg = BG_SHIFT_ON
                else:
                    bg = self._cell_bg(cell["kind"], cell["char"])
                cell["lbl"].config(bg=bg)
                # Shift 래치 중에는 시프트 가능한 자모를 시프트 형태로 표시
                if cell["kind"] == "jamo":
                    shown = SHIFT_MAP.get(cell["char"], cell["char"]) if self.shift_on else cell["char"]
                    cell["lbl"].config(text=shown)

    def _update_typed(self):
        self.lbl_typed.config(text=self.composer.text() + "▏")

    def _update_status(self):
        self.lbl_status.config(
            text="%s · %s · 문장 %d 제출 · 이번 문장 이동 %d / 선택 %d"
                 % (self.participant, self.session, self.trial,
                    self.n_moves, self.n_selects))

    def _ensure_queue(self, n=1):
        while len(self.queue) < n:
            batch = self.pool[:]
            random.shuffle(batch)
            if self.queue and len(batch) > 1 and batch[0] == self.queue[-1]:
                batch[0], batch[1] = batch[1], batch[0]
            self.queue.extend(batch)

    def _begin_sentence(self):
        self._ensure_queue(1)
        self.current_target = self.queue.popleft()
        self.composer = HangulComposer()
        self.cursor = [0, 0]           # 문장마다 좌상단(ㄱ)에서 시작
        self.shift_on = False
        self.t0 = None
        self.started_iso = None
        self.n_moves = 0
        self.n_selects = 0
        self.lbl_target.config(text=self.current_target)
        self._paint_cursor()
        self._update_typed()
        self._update_status()

    # -- 입력 핸들러 ----------------------------------------------------------
    def _arm_timer(self):
        if self.t0 is None:
            self.t0 = time.perf_counter()
            self.started_iso = datetime.now().isoformat(timespec="seconds")

    def _on_move(self, dr, dc):
        if not self.in_test:
            return
        self._arm_timer()
        self.n_moves += 1
        r, c = self.cursor
        if dr:
            nr = min(max(r + dr, 0), len(self.cells) - 1)
            nc = min(c, len(self.cells[nr]) - 1)
        else:
            nr = r
            nc = min(max(c + dc, 0), len(self.cells[r]) - 1)
        self.cursor = [nr, nc]
        self._paint_cursor()
        self._update_status()

    def _on_enter(self, _event=None):
        if not self.in_test:
            return
        self._arm_timer()
        self.n_selects += 1
        r, c = self.cursor
        cell = self.cells[r][c]
        kind = cell["kind"]
        if kind == "jamo":
            j = cell["char"]
            if self.shift_on:
                j = SHIFT_MAP.get(j, j)
                self.shift_on = False
                self._paint_cursor()
            self.composer.input_jamo(j)
        elif kind == "shift":
            self.shift_on = not self.shift_on
            self._paint_cursor()
        elif kind == "space":
            self.composer.input_space()
        elif kind == "bksp":
            self.composer.backspace()
        elif kind == "done":
            self._update_status()
            self._submit_sentence()
            return
        self._update_typed()
        self._update_status()

    # -- 문장 제출/저장 --------------------------------------------------------
    def _submit_sentence(self):
        if not self.in_test:
            return
        if self.t0 is None:
            # 키 입력이 전혀 없었던 제출(Esc) = 문장 건너뛰기, 기록 없음
            self._begin_sentence()
            return
        duration_s = round(time.perf_counter() - self.t0, 4)
        typed = self.composer.text()
        metrics = compute_sentence_metrics(self.current_target, typed,
                                           duration_s, self.n_moves, self.n_selects)
        self.trial += 1
        record = {
            "participant": self.participant,
            "session": self.session,
            "mode": "tvosk",
            "trial": self.trial,
            "started": self.started_iso,
            "target": self.current_target,
            "typed": typed,
            "duration_s": duration_s,
            "n_moves": self.n_moves,
            "n_selects": self.n_selects,
            "syllables": metrics["syllables"],
            "jamo": metrics["jamo"],
            "cpm_syl": metrics["cpm_syl"],
            "jpm": metrics["jpm"],
            "wpm": metrics["wpm"],
            "msd_error_pct": metrics["msd_error_pct"],
            "moves_per_jamo": metrics["moves_per_jamo"],
            "kspc_jamo": metrics["kspc_jamo"],
        }
        self.records.append(record)
        self._save_record(record)
        self._begin_sentence()

    def _save_record(self, record):
        try:
            LOGS_DIR.mkdir(parents=True, exist_ok=True)
            with self.jsonl_path.open("a", encoding="utf-8") as fp:
                fp.write(json.dumps(record, ensure_ascii=False) + "\n")
            if not CSV_PATH.exists():
                # 엑셀 호환을 위해 BOM은 파일 생성 시 1회만 기록
                with CSV_PATH.open("w", encoding="utf-8-sig", newline="") as fp:
                    csv.writer(fp).writerow(CSV_HEADER)
            with CSV_PATH.open("a", encoding="utf-8", newline="") as fp:
                csv.writer(fp).writerow([
                    record["started"], record["participant"], record["session"],
                    record["trial"], record["target"], record["typed"],
                    record["duration_s"], record["n_moves"], record["n_selects"],
                    record["syllables"], record["jamo"], record["cpm_syl"],
                    record["jpm"], record["wpm"], record["msd_error_pct"],
                    record["moves_per_jamo"], record["kspc_jamo"],
                ])
        except OSError as exc:
            messagebox.showerror("저장 실패", "결과 저장 중 오류가 발생했습니다:\n%s" % exc)

    # -- 세션 타이머/종료 -------------------------------------------------------
    def _tick(self):
        if not self.in_test:
            return
        remaining = self.session_t_end - time.perf_counter()
        if remaining <= 0:
            self._end_session()
            return
        m, s = divmod(int(remaining + 0.999), 60)
        self.lbl_timer.config(text="%d:%02d" % (m, s),
                              fg="#c0392b" if remaining < 60 else "#1a5276")
        self.root.after(200, self._tick)

    def _end_session(self):
        if not self.in_test:
            return
        self.in_test = False
        # 진행 중이던 미완성 문장은 기록하지 않음(불완전 시행)
        self._show_result()

    # -- 결과 화면 --------------------------------------------------------------
    def _build_result_frame(self):
        f = self.result_frame = tk.Frame(self.root)
        self.lbl_result_title = tk.Label(f, font=self.f_title)
        self.lbl_result_title.pack(pady=(40, 16))
        self.result_grid = tk.Frame(f)
        self.result_grid.pack(pady=4)
        self.lbl_saved = tk.Label(f, font=self.f_small, fg="gray40")
        self.lbl_saved.pack(pady=(16, 0))
        tk.Button(f, text="새 세션", font=self.f_mid, width=13,
                  command=lambda: self._show(self.start_frame)).pack(pady=24)

    def _show_result(self):
        self.lbl_result_title.config(
            text="%s · %s 세션 결과" % (self.participant, self.session))
        for child in self.result_grid.winfo_children():
            child.destroy()

        n = len(self.records)

        def mean(key):
            return round(sum(r[key] for r in self.records) / n, 2) if n else 0.0

        rows = [
            ("제출 문장 수", n),
            ("총 입력 시간 (s)", round(sum(r["duration_s"] for r in self.records), 1)),
            ("평균 CPM (음절/분)", mean("cpm_syl")),
            ("평균 자모/분", mean("jpm")),
            ("평균 WPM (자모/5)", mean("wpm")),
            ("평균 MSD 오류율 (%)", mean("msd_error_pct")),
            ("평균 이동/자모", mean("moves_per_jamo")),
            ("평균 KSPC(자모)", mean("kspc_jamo")),
        ]
        for i, (name, value) in enumerate(rows):
            tk.Label(self.result_grid, text=name, font=self.f_mid,
                     anchor="e", width=24).grid(row=i, column=0, padx=10, pady=2, sticky="e")
            tk.Label(self.result_grid, text=str(value), font=self.f_mid,
                     anchor="w", width=12, fg="#1a5276").grid(row=i, column=1, padx=10, pady=2, sticky="w")
        if n:
            self.lbl_saved.config(text="저장 완료:  %s  ·  %s"
                                       % (self.jsonl_path.name, CSV_PATH.name))
        else:
            self.lbl_saved.config(text="제출된 문장이 없어 저장된 기록이 없습니다.")
        self._show(self.result_frame)


# ---------------------------------------------------------------------------
# 자가진단 (--selftest): GUI 없이 오토마타/지표 검증
# ---------------------------------------------------------------------------
def _feed(seq):
    """seq: 자모 문자 나열 + 'SHIFT'/'SPACE'/'BKSP' 토큰. 최종 문자열 반환."""
    comp = HangulComposer()
    shift = False
    for item in seq:
        if item == "SHIFT":
            shift = not shift
        elif item == "SPACE":
            comp.input_space()
        elif item == "BKSP":
            comp.backspace()
        else:
            j = SHIFT_MAP.get(item, item) if shift else item
            shift = False
            comp.input_jamo(j)
    return comp.text()


def selftest():
    failures = []

    def check(name, got, want):
        ok = got == want
        print("  [%s] %s: got=%r want=%r" % ("OK" if ok else "FAIL", name, got, want))
        if not ok:
            failures.append(name)

    print("== 한글 조합 오토마타 ==")
    check("값 (ㄱㅏㅂㅅ, 겹받침 ㅄ)", _feed("ㄱㅏㅂㅅ"), "값")
    check("국가 (도깨비불 아님: 단순 종성 후 자음)", _feed("ㄱㅜㄱㄱㅏ"), "국가")
    check("와 (ㅗ+ㅏ 겹모음)", _feed("ㅇㅗㅏ"), "와")
    check("의 (ㅡ+ㅣ 겹모음)", _feed("ㅇㅡㅣ"), "의")
    check("많다 (겹받침 ㄶ + 새 음절)", _feed("ㅁㅏㄴㅎㄷㅏ"), "많다")
    check("떡볶이 (Shift 토글 ×2 경유)",
          _feed(["SHIFT", "ㄷ", "ㅓ", "ㄱ", "ㅂ", "ㅗ", "SHIFT", "ㄱ", "ㅇ", "ㅣ"]),
          "떡볶이")
    check("갑시 (도깨비불: ㅄ 뒷자음 이동)", _feed("ㄱㅏㅂㅅㅣ"), "갑시")
    check("삶 (겹받침 ㄻ)", _feed("ㅅㅏㄹㅁ"), "삶")
    check("않 (겹받침 ㄶ)", _feed("ㅇㅏㄴㅎ"), "않")
    check("쌀 (Shift ㅅ→ㅆ)", _feed(["SHIFT", "ㅅ", "ㅏ", "ㄹ"]), "쌀")
    check("얘 (Shift ㅐ→ㅒ)", _feed(["ㅇ", "SHIFT", "ㅐ"]), "얘")
    check("단독 겹모음 ㅘ (초성 없음)", _feed("ㅗㅏ"), "ㅘ")
    check("국 가 (Space)", _feed(["ㄱ", "ㅜ", "ㄱ", "SPACE", "ㄱ", "ㅏ"]), "국 가")
    check("자음 연타는 쌍자음 아님 (ㄱㄱ)", _feed("ㄱㄱ"), "ㄱㄱ")
    check("가+ㅗ (결합 불가 모음 → 분리)", _feed("ㄱㅏㅗ"), "가ㅗ")

    print("== 백스페이스 (자모 단위) ==")
    check("값→갑", _feed(["ㄱ", "ㅏ", "ㅂ", "ㅅ", "BKSP"]), "갑")
    check("와→오", _feed(["ㅇ", "ㅗ", "ㅏ", "BKSP"]), "오")
    check("많→만", _feed(["ㅁ", "ㅏ", "ㄴ", "ㅎ", "BKSP"]), "만")
    check("가→ㄱ", _feed(["ㄱ", "ㅏ", "BKSP"]), "ㄱ")
    check("확정 글자는 통째 삭제 (국+공백→빈 문자열)",
          _feed(["ㄱ", "ㅜ", "ㄱ", "SPACE", "BKSP", "BKSP"]), "")

    print("== 자모 분해 스펙 ==")
    check("값 분해", "".join(decompose_text("값")), "ㄱㅏㅂㅅ")
    check("많다 분해", "".join(decompose_text("많다")), "ㅁㅏㄴㅎㄷㅏ")
    check("의 분해", "".join(decompose_text("의")), "ㅇㅡㅣ")
    check("떡볶이 분해 (쌍자음 1자모)", "".join(decompose_text("떡볶이")), "ㄸㅓㄱㅂㅗㄲㅇㅣ")
    check("공백 무시", "".join(decompose_text("국 가")), "ㄱㅜㄱㄱㅏ")

    print("== MSD / 지표 ==")
    check("MSD 값vs갑 = 1", msd(decompose_text("값"), decompose_text("갑")), 1)
    m = compute_sentence_metrics("값", "갑", 10.0, 12, 4)
    check("오류율 값vs갑 = 25%", m["msd_error_pct"], 25.0)
    m = compute_sentence_metrics("국가", "국가", 30.0, 40, 5)
    check("국가/30s: 음절 2", m["syllables"], 2)
    check("국가/30s: 자모 5", m["jamo"], 5)
    check("국가/30s: CPM 4", m["cpm_syl"], 4.0)
    check("국가/30s: 자모/분 10", m["jpm"], 10.0)
    check("국가/30s: WPM 2", m["wpm"], 2.0)
    check("국가/30s: 오류율 0", m["msd_error_pct"], 0.0)
    check("국가/30s: 이동/자모 8", m["moves_per_jamo"], 8.0)
    check("국가/30s: KSPC 9", m["kspc_jamo"], 9.0)
    m = compute_sentence_metrics("오늘 날씨", "", 5.0, 3, 1)
    check("빈 입력: 오류율 100%", m["msd_error_pct"], 100.0)

    print()
    if failures:
        print("FAIL: %d개 실패 — %s" % (len(failures), ", ".join(failures)))
        return 1
    print("PASS: 모든 자가진단 통과")
    return 0


def main():
    if "--selftest" in sys.argv:
        sys.exit(selftest())
    if tk is None:
        print("tkinter를 불러올 수 없습니다. Python 표준 GUI(tkinter)가 포함된 "
              "배포판인지 확인하세요. (Ubuntu: sudo apt install python3-tk)")
        sys.exit(1)
    root = tk.Tk()
    TvOskApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
