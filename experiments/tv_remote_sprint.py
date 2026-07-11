#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tv_remote_sprint.py — TV 리모컨식 화면 키보드로 60초 한글 단어 스프린트

실험 D(기기 간 비교)의 대조군. 스마트TV·VR에서 흔한 '커서를 한 칸씩 옮겨
선택하는' 입력 방식을 그대로 구현해, 장갑형 키보드(speed_test.py)와
**완전히 같은 과제·같은 지표**로 비교한다.

  장갑        : python speed_test.py        (60초 랜덤 단어, 물리 16버튼)
  대조군(이것) : python tv_remote_sprint.py  (60초 랜덤 단어, 방향키+선택)

두 도구가 같은 word_list_ko.txt, 같은 60초, 같은 WPM 정의를 쓰므로 결과를
그대로 나란히 놓을 수 있다. (문장 전사 방식의 대조군은 tv_osk_test.py)

조작: ← → ↑ ↓ 이동 · Enter 선택 · Backspace 지우기 · 단어가 정확히 완성되면
      자동으로 다음 단어. **첫 조작(방향키 이동 또는 선택)부터** 60초 카운트다운
      — 커서 이동도 이 방식의 입력 비용이므로 측정 시간에 포함한다.
실행: python tv_remote_sprint.py            (Python 3.8+, 표준 라이브러리만)
      python tv_remote_sprint.py --selftest (GUI 없이 조합 엔진·지표 검증)

저장(logs/):
  1) <participant>_<session>_tvsprint_<MMDD_HHMMSS>.jsonl — 시행당 1줄
     (단어별 소요시간·선택수·이동수 로그 포함)
  2) tvsprint_sessions.csv — 전체 시행 누적 요약(1행/시행, UTF-8 BOM)

[지표 — speed_test.py와 동일 정의]
  - 음절 수 / 자모 수 : 입력 확정된 문자열 기준(겹모음·겹받침 2자모, 쌍자음 1자모)
  - CPM(음절/분)      : 음절 수 × 60 / 60초
  - 자모/분(jpm)      : 자모 수 × 60 / 60초
  - WPM               : 자모/분 ÷ 5     ← 두 기기 비교의 기준 지표
  - 이동/선택         : 커서 이동 횟수, 키 선택 횟수 (이 방식 고유의 조작 비용)
  - 선택당 이동       : moves / presses — 커서 방식의 구조적 오버헤드
  - 교정률(%)         : (선택 수 − 자모 수) / 자모 수 × 100
                        이 방식은 단어가 정확히 맞아야 넘어가므로 오타가 결과
                        문자열에 남지 않는다. 대신 '틀려서 더 누른 만큼'을
                        교정 비용으로 본다(speed_test.py의 MSD 오류율에 대응).

[주의] 원본 웹 프로토타입(etc-files/tv-remote-word-sprint.html)은 60초 동안
완료한 '단어 수'를 그대로 WPM으로 표시했다. 그 값은 텍스트 입력 연구의 표준
WPM(1 word = 5 characters)이 아니므로 기기 간 비교에 쓸 수 없다. 이 파일은
표준 정의로 WPM을 계산하고, 완료 단어 수는 별도 지표로 함께 보고한다.
"""

import csv
import json
import random
import sys
import time
from datetime import datetime
from pathlib import Path

try:
    import tkinter as tk
    from tkinter import font as tkfont
    from tkinter import messagebox, ttk
except ImportError:  # headless에서도 selftest는 돌도록
    tk = None

# ---------------------------------------------------------------------------
# 경로/상수
# ---------------------------------------------------------------------------
SCRIPT_DIR = Path(__file__).resolve().parent
WORD_FILE = SCRIPT_DIR / "word_list_ko.txt"
LOGS_DIR = SCRIPT_DIR / "logs"
CSV_PATH = LOGS_DIR / "tvsprint_sessions.csv"

TRIAL_SECONDS = 60.0
POSTURES = ("desk", "sofa", "stand")
WORD_SYLLABLE_RANGE = (2, 3)   # 원본 웹 프로토타입과 동일하게 2~3음절 단어만 사용

CSV_HEADER = [
    "timestamp", "participant", "session", "posture", "trial",
    "words_completed", "skips", "presses", "moves", "backspaces",
    "syllables", "jamo", "cpm_syl", "jpm", "wpm",
    "moves_per_press", "correction_pct",
]

# ---------------------------------------------------------------------------
# 한글 조합 엔진 (원본 웹 프로토타입의 오토마타를 그대로 이식)
# ---------------------------------------------------------------------------
CHO = list("ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ")
JUNG = list("ㅏㅐㅑㅒㅓㅔㅕㅖㅗㅘㅙㅚㅛㅜㅝㅞㅟㅠㅡㅢㅣ")
JONG = ["", "ㄱ", "ㄲ", "ㄳ", "ㄴ", "ㄵ", "ㄶ", "ㄷ", "ㄹ", "ㄺ", "ㄻ", "ㄼ",
        "ㄽ", "ㄾ", "ㄿ", "ㅀ", "ㅁ", "ㅂ", "ㅄ", "ㅅ", "ㅆ", "ㅇ", "ㅈ", "ㅊ",
        "ㅋ", "ㅌ", "ㅍ", "ㅎ"]

VCOMB = {"ㅗㅏ": "ㅘ", "ㅗㅐ": "ㅙ", "ㅗㅣ": "ㅚ", "ㅜㅓ": "ㅝ",
         "ㅜㅔ": "ㅞ", "ㅜㅣ": "ㅟ", "ㅡㅣ": "ㅢ"}
JCOMB = {"ㄱㅅ": "ㄳ", "ㄴㅈ": "ㄵ", "ㄴㅎ": "ㄶ", "ㄹㄱ": "ㄺ", "ㄹㅁ": "ㄻ",
         "ㄹㅂ": "ㄼ", "ㄹㅅ": "ㄽ", "ㄹㅌ": "ㄾ", "ㄹㅍ": "ㄿ", "ㄹㅎ": "ㅀ",
         "ㅂㅅ": "ㅄ", "ㄱㄱ": "ㄲ", "ㅅㅅ": "ㅆ"}
DCOMB = {"ㄱㄱ": "ㄲ", "ㄷㄷ": "ㄸ", "ㅂㅂ": "ㅃ", "ㅅㅅ": "ㅆ", "ㅈㅈ": "ㅉ"}
JSPLIT = {"ㄳ": ("ㄱ", "ㅅ"), "ㄵ": ("ㄴ", "ㅈ"), "ㄶ": ("ㄴ", "ㅎ"),
          "ㄺ": ("ㄹ", "ㄱ"), "ㄻ": ("ㄹ", "ㅁ"), "ㄼ": ("ㄹ", "ㅂ"),
          "ㄽ": ("ㄹ", "ㅅ"), "ㄾ": ("ㄹ", "ㅌ"), "ㄿ": ("ㄹ", "ㅍ"),
          "ㅀ": ("ㄹ", "ㅎ"), "ㅄ": ("ㅂ", "ㅅ"), "ㄲ": ("ㄱ", "ㄱ"),
          "ㅆ": ("ㅅ", "ㅅ")}
VSPLIT = {"ㅘ": "ㅗ", "ㅙ": "ㅗ", "ㅚ": "ㅗ", "ㅝ": "ㅜ", "ㅞ": "ㅜ",
          "ㅟ": "ㅜ", "ㅢ": "ㅡ"}


class HangulComposer:
    """두벌식 조합 오토마타. committed(확정) + 조합 중 글자 1개를 유지한다."""

    def __init__(self):
        self.reset()

    def reset(self):
        self.committed = ""
        self.cho = -1
        self.jung = -1
        self.jong = 0

    def _reset_cur(self):
        self.cho = self.jung = -1
        self.jong = 0

    def current(self):
        """조합 중인 글자(없으면 빈 문자열)."""
        if self.cho >= 0 and self.jung >= 0:
            return chr(0xAC00 + self.cho * 588 + self.jung * 28 + self.jong)
        if self.cho >= 0:
            return CHO[self.cho]
        if self.jung >= 0:
            return JUNG[self.jung]
        return ""

    def text(self):
        return self.committed + self.current()

    def _commit(self):
        c = self.current()
        if c:
            self.committed += c
        self._reset_cur()

    def input_jamo(self, ch):
        """자모 1개 입력."""
        if ch in JUNG:                       # 모음
            vi = JUNG.index(ch)
            if self.jung < 0:
                self.jung = vi
                return
            if self.jong == 0:
                comb = VCOMB.get(JUNG[self.jung] + ch)
                if comb:
                    self.jung = JUNG.index(comb)
                else:
                    self._commit()
                    self.jung = vi
                return
            # 받침이 있는데 모음이 오면: 받침을 다음 글자 초성으로 넘긴다(도깨비불)
            jc = JONG[self.jong]
            sp = JSPLIT.get(jc)
            if sp and sp[1] in CHO:
                self.jong = JONG.index(sp[0])
                self._commit()
                self.cho = CHO.index(sp[1])
            else:
                self.jong = 0
                self._commit()
                self.cho = CHO.index(jc)
            self.jung = vi
        else:                                # 자음
            ci = CHO.index(ch) if ch in CHO else -1
            if self.cho < 0 and self.jung < 0:
                self.cho = ci
                return
            if self.cho >= 0 and self.jung < 0:
                d = DCOMB.get(CHO[self.cho] + ch)   # 같은 자음 2번 → 쌍자음
                if d:
                    self.cho = CHO.index(d)
                else:
                    self._commit()
                    self.cho = ci
                return
            if self.jung >= 0 and self.cho < 0:
                self._commit()
                self.cho = ci
                return
            if self.jong == 0:
                ji = JONG.index(ch) if ch in JONG else 0
                if ji > 0:
                    self.jong = ji
                else:
                    self._commit()
                    self.cho = ci
                return
            comb = JCOMB.get(JONG[self.jong] + ch)
            if comb:
                self.jong = JONG.index(comb)
            else:
                self._commit()
                self.cho = ci

    def backspace(self):
        """자모 단위 삭제(조합 중이면 마지막 자모, 아니면 확정 글자 1개)."""
        if self.jong > 0:
            sp = JSPLIT.get(JONG[self.jong])
            self.jong = JONG.index(sp[0]) if sp else 0
        elif self.jung >= 0:
            v = VSPLIT.get(JUNG[self.jung])
            if v:
                self.jung = JUNG.index(v)
            elif self.cho >= 0:
                self.jung = -1
            else:
                self._reset_cur()
        elif self.cho >= 0:
            self._reset_cur()
        else:
            self.committed = self.committed[:-1]

    def space(self):
        self._commit()
        self.committed += " "


# ---------------------------------------------------------------------------
# 지표 계산 (speed_test.py와 동일 정의 — 두 기기 비교를 위해 반드시 일치)
# ---------------------------------------------------------------------------
COMPOUND = {
    "ㅘ": "ㅗㅏ", "ㅙ": "ㅗㅐ", "ㅚ": "ㅗㅣ", "ㅝ": "ㅜㅓ",
    "ㅞ": "ㅜㅔ", "ㅟ": "ㅜㅣ", "ㅢ": "ㅡㅣ",
    "ㄳ": "ㄱㅅ", "ㄵ": "ㄴㅈ", "ㄶ": "ㄴㅎ", "ㄺ": "ㄹㄱ",
    "ㄻ": "ㄹㅁ", "ㄼ": "ㄹㅂ", "ㄽ": "ㄹㅅ", "ㄾ": "ㄹㅌ",
    "ㄿ": "ㄹㅍ", "ㅀ": "ㄹㅎ", "ㅄ": "ㅂㅅ",
}


def decompose_char(ch):
    code = ord(ch)
    if 0xAC00 <= code <= 0xD7A3:
        code -= 0xAC00
        out = [CHO[code // 588]]
        jung = JUNG[(code % 588) // 28]
        out.extend(COMPOUND.get(jung, jung))
        jong = JONG[code % 28]
        if jong:
            out.extend(COMPOUND.get(jong, jong))
        return out
    if ch in COMPOUND:
        return list(COMPOUND[ch])
    return [ch]


def decompose_text(text):
    jamo = []
    for ch in text:
        if ch == " ":
            continue
        jamo.extend(decompose_char(ch))
    return jamo


def count_syllables(text):
    return sum(1 for ch in text if 0xAC00 <= ord(ch) <= 0xD7A3)


def compute_metrics(typed_all, presses, moves, duration_s=TRIAL_SECONDS):
    """입력 확정 문자열 + 조작 횟수 → 지표."""
    syllables = count_syllables(typed_all)
    jamo = len(decompose_text(typed_all))
    minutes = duration_s / 60.0 if duration_s > 0 else 1.0
    jpm = jamo / minutes
    # 이 방식은 자모 1개 = 선택 1회가 최소 비용. 그 초과분이 교정(오선택) 비용.
    correction = ((presses - jamo) / jamo * 100.0) if jamo else 0.0
    return {
        "syllables": syllables,
        "jamo": jamo,
        "cpm_syl": round(syllables / minutes, 2),
        "jpm": round(jpm, 2),
        "wpm": round(jpm / 5.0, 2),
        "moves_per_press": round(moves / presses, 2) if presses else 0.0,
        "correction_pct": round(correction, 2),
    }


# ---------------------------------------------------------------------------
# 단어 목록
# ---------------------------------------------------------------------------
FALLBACK_WORDS = [
    "사과", "나무", "바다", "하늘", "노래", "학교", "친구", "시간", "마음", "소리",
    "거울", "지구", "안경", "우유", "김치", "라면", "버스", "병원", "극장", "신발",
    "고양이", "강아지", "무지개", "바나나", "어린이", "할머니", "지우개", "세탁기",
    "비행기", "자전거", "운동장", "목소리", "전화기", "소방차", "냉장고", "도서관",
]


def load_words():
    """word_list_ko.txt에서 2~3음절 순수 한글 단어만 사용(장갑 실험과 동일 풀)."""
    lo, hi = WORD_SYLLABLE_RANGE
    if WORD_FILE.exists():
        words, seen = [], set()
        for line in WORD_FILE.read_text(encoding="utf-8").splitlines():
            w = line.strip()
            if not w or w.startswith("#") or w in seen:
                continue
            if all(0xAC00 <= ord(c) <= 0xD7A3 for c in w) and lo <= len(w) <= hi:
                seen.add(w)
                words.append(w)
        if len(words) >= 10:
            return words, True
    return list(FALLBACK_WORDS), False


def sanitize_id(text):
    return "".join(ch for ch in text.strip() if ch.isalnum() or ch in "-_") or "X"


# ---------------------------------------------------------------------------
# 저장 (GUI 없이도 검증할 수 있게 분리)
# ---------------------------------------------------------------------------
# CSV 열 이름 -> record의 키 (record는 'timestamp' 대신 'started'를 쓴다)
CSV_FIELD_OF = dict(zip(CSV_HEADER, CSV_HEADER))
CSV_FIELD_OF["timestamp"] = "started"


def save_record(record, jsonl_path, csv_path=CSV_PATH, logs_dir=LOGS_DIR):
    """시행 1건을 JSONL에 append하고 누적 CSV에 요약 1행을 추가한다."""
    logs_dir.mkdir(parents=True, exist_ok=True)
    with Path(jsonl_path).open("a", encoding="utf-8") as fp:
        fp.write(json.dumps(record, ensure_ascii=False) + "\n")
    csv_path = Path(csv_path)
    new_file = not csv_path.exists()
    if new_file:   # 엑셀 호환 BOM은 생성 시 1회만
        with csv_path.open("w", encoding="utf-8-sig", newline="") as fp:
            csv.writer(fp).writerow(CSV_HEADER)
    with csv_path.open("a", encoding="utf-8", newline="") as fp:
        csv.writer(fp).writerow([record[CSV_FIELD_OF[col]] for col in CSV_HEADER])
    return csv_path


# ---------------------------------------------------------------------------
# 화면 키보드 레이아웃 (원본 웹 프로토타입과 동일 — 스마트TV 자판 관행)
# ---------------------------------------------------------------------------
LAYOUT = [
    ["ㄱ", "ㄴ", "ㄷ", "ㄹ", "ㅁ", "ㅂ", "ㅅ"],
    ["ㅇ", "ㅈ", "ㅊ", "ㅋ", "ㅌ", "ㅍ", "ㅎ"],
    ["ㅏ", "ㅑ", "ㅓ", "ㅕ", "ㅗ", "ㅛ", "ㅜ"],
    ["ㅠ", "ㅡ", "ㅣ", "ㅐ", "ㅔ", "ㅒ", "ㅖ"],
    ["SPACE", "BACK", "SKIP"],
]
KEY_LABEL = {"SPACE": "스페이스", "BACK": "지우기", "SKIP": "건너뛰기"}


def move_cursor(pos, dr, dc):
    """방향 이동(가로 순환, 세로는 열 위치를 비율로 사상). -> 새 (r, c)"""
    r, c = pos
    if dc:
        c = (c + dc) % len(LAYOUT[r])
    if dr:
        old_len = len(LAYOUT[r])
        r = (r + dr) % len(LAYOUT)
        ratio = c / (old_len - 1) if old_len > 1 else 0.0
        c = min(round(ratio * (len(LAYOUT[r]) - 1)), len(LAYOUT[r]) - 1)
    return r, c


# ---------------------------------------------------------------------------
# GUI
# ---------------------------------------------------------------------------
BG = "#ffffff"        # 배경
PANEL = "#f1f3f4"     # 자모 키 · 제시 단어 패널
PANEL2 = "#e4e7ea"    # 기능 키
INK = "#202124"       # 본문 글자
DIM = "#5f6368"       # 보조 글자
HINT = "#9aa0a6"      # 안내 문구
LINE = "#dadce0"      # 테두리
OK = "#1a73e8"        # 강조(파랑)
GOOD = "#188038"      # 정답
BAD = "#d93025"       # 오답
RED = "#d93025"       # 타이머 경고
FOCUS_BG = "#1a73e8"  # 커서가 놓인 키
FOCUS_FG = "#ffffff"


class TvSprintApp:
    def __init__(self, root):
        self.root = root
        root.title("리모컨 한글 단어 스프린트 — 실험 D 대조군")
        root.geometry("900x760")
        root.minsize(760, 680)
        root.configure(bg=BG)

        base = tkfont.nametofont("TkDefaultFont")
        fam = base.actual("family")
        self.f_small = tkfont.Font(family=fam, size=10)
        self.f_mid = tkfont.Font(family=fam, size=13)
        self.f_key = tkfont.Font(family=fam, size=16)
        self.f_fn = tkfont.Font(family=fam, size=10)
        self.f_word = tkfont.Font(family=fam, size=34, weight="bold")
        self.f_typed = tkfont.Font(family=fam, size=22)
        self.f_timer = tkfont.Font(family=fam, size=28, weight="bold")
        self.f_big = tkfont.Font(family=fam, size=40, weight="bold")

        self.pool, self.from_file = load_words()

        # 세션 상태
        self.participant = self.session = ""
        self.posture = POSTURES[0]
        self.trial = 1
        self.jsonl_path = None

        # 시행 상태
        self.comp = HangulComposer()
        self.pos = (0, 0)
        self.reset_trial_state()

        self._build_start()
        self._build_test()
        self._build_result()
        self._show(self.start_frame)
        root.bind("<Key>", self._on_key)

    def reset_trial_state(self):
        self.t0 = None
        self.running = False
        self.finished = True
        self.presses = self.moves = self.skips = self.backspaces = 0
        self.words_done = 0
        self.typed_all = ""
        self.word_log = []
        self.cur_word = ""
        self.word_t0 = None
        self.word_presses = self.word_moves = 0
        self.started_iso = None

    # -- 공통 -------------------------------------------------------------
    def _show(self, frame):
        for f in (self.start_frame, self.test_frame, self.result_frame):
            f.pack_forget()
        frame.pack(fill="both", expand=True)
        self.active = frame

    def _lbl(self, parent, text="", font=None, fg=INK, bg=BG, **kw):
        return tk.Label(parent, text=text, font=font or self.f_mid,
                        fg=fg, bg=bg, **kw)

    # -- 시작 화면 --------------------------------------------------------
    def _build_start(self):
        f = self.start_frame = tk.Frame(self.root, bg=BG)
        self._lbl(f, "리모컨 한글 단어 스프린트", self.f_timer).pack(pady=(56, 4))
        self._lbl(f, "실험 D 대조군 — 스마트TV·VR식 커서 선택 입력 (60초)",
                  self.f_small, DIM).pack(pady=(0, 26))

        form = tk.Frame(f, bg=BG)
        form.pack()
        rows = [("실험자 ID", "P01"), ("세션 ID", "S1")]
        self.entries = {}
        for i, (label, default) in enumerate(rows):
            self._lbl(form, label, self.f_mid).grid(row=i, column=0, sticky="e", padx=8, pady=6)
            e = tk.Entry(form, font=self.f_mid, width=12, bg="#ffffff", fg=INK,
                         insertbackground=INK, relief="solid", borderwidth=1,
                         highlightthickness=0)
            e.insert(0, default)
            e.grid(row=i, column=1, sticky="w", padx=8, pady=6)
            self.entries[label] = e
        self._lbl(form, "자세 조건", self.f_mid).grid(row=2, column=0, sticky="e", padx=8, pady=6)
        self.cmb_posture = ttk.Combobox(form, values=list(POSTURES), state="readonly",
                                        width=10, font=self.f_mid)
        self.cmb_posture.set(POSTURES[0])
        self.cmb_posture.grid(row=2, column=1, sticky="w", padx=8, pady=6)

        tk.Button(f, text="시작  (Enter)", font=self.f_mid, width=18, relief="flat",
                  bg=OK, fg="#ffffff", activebackground="#1765cc",
                  activeforeground="#ffffff",
                  command=self._start_session).pack(pady=30)
        note = "단어 풀: %d개 (2~3음절)" % len(self.pool)
        if not self.from_file:
            note += "  ·  word_list_ko.txt 없음 — 내장 목록 사용"
        self._lbl(f, note, self.f_small, DIM).pack()
        self._lbl(f, "← → ↑ ↓ 이동 · Enter 선택 · Backspace 지우기 · 단어 완성 시 자동으로 다음\n"
                     "첫 방향키 이동 또는 선택과 동시에 60초가 시작됩니다",
                  self.f_small, HINT).pack(pady=(8, 0))
        self._lbl(f, "저장 위치: %s" % LOGS_DIR, self.f_small, HINT).pack(pady=(6, 0))

    def _start_session(self):
        p = self.entries["실험자 ID"].get().strip()
        s = self.entries["세션 ID"].get().strip()
        if not p or not s:
            messagebox.showwarning("입력 필요", "실험자 ID와 세션 ID를 입력하세요.")
            return
        self.participant, self.session = p, s
        self.posture = self.cmb_posture.get() or POSTURES[0]
        self.trial = 1
        self.jsonl_path = LOGS_DIR / ("%s_%s_tvsprint_%s.jsonl"
                                      % (sanitize_id(p), sanitize_id(s),
                                         datetime.now().strftime("%m%d_%H%M%S")))
        self._begin_trial()

    # -- 실험 화면 --------------------------------------------------------
    def _build_test(self):
        f = self.test_frame = tk.Frame(self.root, bg=BG)
        top = tk.Frame(f, bg=BG)
        top.pack(fill="x", padx=26, pady=(16, 0))
        self.lbl_status = self._lbl(top, "", self.f_small, DIM)
        self.lbl_status.pack(side="left")
        self.lbl_timer = self._lbl(top, "60.0", self.f_timer)
        self.lbl_timer.pack(side="right")

        hud = tk.Frame(f, bg=BG)
        hud.pack(fill="x", padx=26, pady=(6, 0))
        self.hud_vars = {}
        for key, label in (("words", "완료 단어"), ("presses", "선택"),
                           ("moves", "이동"), ("skips", "건너뜀")):
            box = tk.Frame(hud, bg=BG)
            box.pack(side="left", padx=(0, 20))
            self._lbl(box, label, self.f_small, DIM).pack(side="left")
            v = self._lbl(box, " 0", self.f_small, OK)
            v.pack(side="left")
            self.hud_vars[key] = v

        self.lbl_word = self._lbl(f, "", self.f_word, INK, PANEL, height=2)
        self.lbl_word.pack(fill="x", padx=26, pady=(14, 0))
        self.lbl_typed = self._lbl(f, "", self.f_typed, OK, BG, height=2)
        self.lbl_typed.pack(pady=(6, 4))

        kb = tk.Frame(f, bg=BG)
        kb.pack(pady=(4, 0))
        self.key_widgets = []
        for r, row in enumerate(LAYOUT):
            rowf = tk.Frame(kb, bg=BG)
            rowf.pack(pady=3)
            widgets = []
            for c, key in enumerate(row):
                is_fn = key in KEY_LABEL
                w = tk.Label(rowf, text=KEY_LABEL.get(key, key),
                             font=self.f_fn if is_fn else self.f_key,
                             fg=DIM if is_fn else INK, bg=PANEL2 if is_fn else PANEL,
                             width=13 if is_fn else 4, pady=7,
                             relief="solid", borderwidth=1,
                             highlightbackground=LINE)
                w.pack(side="left", padx=3)
                w.bind("<Button-1>", lambda e, rr=r, cc=c: self._click_key(rr, cc))
                widgets.append(w)
            self.key_widgets.append(widgets)

        self._lbl(f, "← → ↑ ↓ 이동 · Enter 선택 · Backspace 지우기 · 단어가 맞으면 자동으로 다음 (첫 조작부터 60초)",
                  self.f_small, HINT).pack(pady=(14, 0))
        tk.Button(f, text="중단", font=self.f_small, relief="flat", bg=PANEL2, fg=DIM,
                  command=self._abort).pack(pady=10)

    def _begin_trial(self):
        self.reset_trial_state()
        self.running = True
        self.finished = False
        self.pos = (0, 0)
        self.lbl_status.config(text="%s · %s · %s · trial %d"
                               % (self.participant, self.session, self.posture, self.trial))
        self.lbl_timer.config(text="%.1f" % TRIAL_SECONDS, fg=INK)
        for v in self.hud_vars.values():
            v.config(text=" 0")
        self._next_word()
        self._render_focus()
        self._show(self.test_frame)

    def _abort(self):
        self.running = False
        self.finished = True
        self._show(self.start_frame)

    def _next_word(self):
        w = self.cur_word
        while w == self.cur_word and len(self.pool) > 1:
            w = random.choice(self.pool)
        self.cur_word = w
        self.comp.reset()
        self.word_t0 = time.perf_counter()
        self.word_presses = self.word_moves = 0
        self._render()

    def _render(self):
        typed = self.comp.text()
        # 목표 단어: 맞은 글자 초록 / 틀린 글자 빨강 / 미입력 회색 — tk Label은
        # 부분 색상이 안 되므로 상태를 기호로 표시한다.
        marks = []
        for i, ch in enumerate(self.cur_word):
            if i >= len(typed):
                marks.append(ch)
            elif typed[i] == ch:
                marks.append(ch)
            else:
                marks.append("(%s)" % ch)   # 틀린 위치 표시
        wrong = any(i < len(typed) and typed[i] != ch
                    for i, ch in enumerate(self.cur_word))
        self.lbl_word.config(text="  ".join(marks), fg=BAD if wrong else INK)
        self.lbl_typed.config(text=typed or "…", fg=GOOD if typed == self.cur_word else OK)

    def _render_focus(self):
        for r, row in enumerate(self.key_widgets):
            for c, w in enumerate(row):
                focused = (r, c) == self.pos
                is_fn = LAYOUT[r][c] in KEY_LABEL
                w.config(bg=FOCUS_BG if focused else (PANEL2 if is_fn else PANEL),
                         fg=FOCUS_FG if focused else (DIM if is_fn else INK))

    def _click_key(self, r, c):
        if not self.running:
            return
        self.pos = (r, c)
        self._render_focus()
        self._select()

    def _on_key(self, event):
        if self.active is self.start_frame:
            if event.keysym in ("Return", "KP_Enter"):
                self._start_session()
            return
        if self.active is self.result_frame:
            return
        if not self.running or self.finished:
            return
        deltas = {"Left": (0, -1), "Right": (0, 1), "Up": (-1, 0), "Down": (1, 0)}
        if event.keysym in deltas:
            self._start_timer_if_needed()        # 이동도 조작 → 여기서 타이머 시작
            self.pos = move_cursor(self.pos, *deltas[event.keysym])
            self.moves += 1
            self.word_moves += 1
            self.hud_vars["moves"].config(text=" %d" % self.moves)
            self._render_focus()
        elif event.keysym in ("Return", "KP_Enter"):
            self._select()
        elif event.keysym == "BackSpace":
            # 물리 백스페이스도 허용(원본 프로토타입과 동일). 선택 1회로 계상.
            self._apply_key("BACK")

    def _select(self):
        self._apply_key(LAYOUT[self.pos[0]][self.pos[1]])

    def _start_timer_if_needed(self):
        """첫 조작(커서 이동 또는 키 선택)에 타이머를 시작한다.

        커서 이동 자체가 이 입력 방식의 비용이므로, 이동부터 시간을 잰다.
        (원본 웹 프로토타입은 첫 선택부터 쟀다 — 이동 비용이 누락되어
         장갑과의 비교가 대조군에 유리하게 왜곡된다.)
        """
        if self.t0 is not None:
            return
        now = time.perf_counter()
        self.t0 = now
        self.word_t0 = now
        self.started_iso = datetime.now().isoformat(timespec="seconds")
        self.root.after(50, self._tick)

    def _apply_key(self, key):
        if not self.running or self.finished:
            return
        self._start_timer_if_needed()

        self.presses += 1
        self.word_presses += 1
        self.hud_vars["presses"].config(text=" %d" % self.presses)

        if key == "SPACE":
            self.comp.space()
        elif key == "BACK":
            self.comp.backspace()
            self.backspaces += 1
        elif key == "SKIP":
            self._finish_word("건너뜀")
            self.skips += 1
            self.hud_vars["skips"].config(text=" %d" % self.skips)
            self._next_word()
            return
        else:
            self.comp.input_jamo(key)

        self._render()
        if self.comp.text() == self.cur_word:    # 정확히 완성 → 자동 진행
            self._finish_word("완료")
            self.words_done += 1
            self.hud_vars["words"].config(text=" %d" % self.words_done)
            self._next_word()

    def _finish_word(self, result):
        typed = self.comp.text()
        self.typed_all += typed
        self.word_log.append({
            "word": self.cur_word, "typed": typed, "result": result,
            "time_s": round(time.perf_counter() - (self.word_t0 or time.perf_counter()), 3),
            "presses": self.word_presses, "moves": self.word_moves,
        })

    def _tick(self):
        if not self.running or self.t0 is None:
            return
        remain = TRIAL_SECONDS - (time.perf_counter() - self.t0)
        if remain <= 0:
            self._end_trial()
            return
        self.lbl_timer.config(text="%.1f" % remain, fg=RED if remain <= 10 else INK)
        self.root.after(50, self._tick)

    # -- 종료/저장 --------------------------------------------------------
    def _end_trial(self):
        self.running = False
        self.finished = True
        self.lbl_timer.config(text="0.0", fg=RED)
        partial = self.comp.text()
        if partial:                              # 종료 시 입력 중이던 단어
            self._finish_word("미완료")

        m = compute_metrics(self.typed_all, self.presses, self.moves, TRIAL_SECONDS)
        record = {
            "participant": self.participant, "session": self.session,
            "posture": self.posture, "mode": "tvsprint", "trial": self.trial,
            "started": self.started_iso or datetime.now().isoformat(timespec="seconds"),
            "duration_s": int(TRIAL_SECONDS),
            "words_completed": self.words_done, "skips": self.skips,
            "presses": self.presses, "moves": self.moves,
            "backspaces": self.backspaces, **m,
            "words": self.word_log,
        }
        self._show_result(record, self._save(record))

    def _save(self, record):
        try:
            save_record(record, self.jsonl_path)
            return "저장 완료:  %s  ·  %s" % (self.jsonl_path.name, CSV_PATH.name)
        except OSError as exc:
            messagebox.showerror("저장 실패", "결과 저장 중 오류가 발생했습니다:\n%s" % exc)
            return "저장 실패: %s" % exc

    # -- 결과 화면 --------------------------------------------------------
    def _build_result(self):
        f = self.result_frame = tk.Frame(self.root, bg=BG)
        self.lbl_res_title = self._lbl(f, "결과", self.f_timer)
        self.lbl_res_title.pack(pady=(40, 6))
        self.lbl_wpm = self._lbl(f, "", self.f_big, OK)
        self.lbl_wpm.pack(pady=(0, 4))
        self.lbl_wpm_note = self._lbl(f, "WPM = 자모/분 ÷ 5 (장갑 실험과 동일 정의)",
                                      self.f_small, DIM)
        self.lbl_wpm_note.pack(pady=(0, 16))
        self.res_grid = tk.Frame(f, bg=BG)
        self.res_grid.pack()
        self.lbl_saved = self._lbl(f, "", self.f_small, DIM)
        self.lbl_saved.pack(pady=(16, 0))
        btns = tk.Frame(f, bg=BG)
        btns.pack(pady=22)
        tk.Button(btns, text="다음 회차", font=self.f_mid, width=13, relief="flat",
                  bg=OK, fg="#ffffff", activebackground="#1765cc",
                  activeforeground="#ffffff",
                  command=self._next_trial).pack(side="left", padx=8)
        tk.Button(btns, text="실험자 변경", font=self.f_mid, width=13, relief="flat",
                  bg=PANEL2, fg=INK,
                  command=lambda: self._show(self.start_frame)).pack(side="left", padx=8)

    def _show_result(self, rec, save_msg):
        self.lbl_res_title.config(text="%s · %s · trial %d 결과"
                                  % (rec["participant"], rec["session"], rec["trial"]))
        self.lbl_wpm.config(text="%.1f WPM" % rec["wpm"])
        for child in self.res_grid.winfo_children():
            child.destroy()
        rows = [
            ("완료 단어 수", rec["words_completed"]),
            ("건너뜀", rec["skips"]),
            ("음절 수 / 자모 수", "%d / %d" % (rec["syllables"], rec["jamo"])),
            ("CPM (음절/분)", rec["cpm_syl"]),
            ("자모/분", rec["jpm"]),
            ("선택 횟수", rec["presses"]),
            ("커서 이동 횟수", rec["moves"]),
            ("선택당 이동", rec["moves_per_press"]),
            ("교정률 (%)", rec["correction_pct"]),
        ]
        for i, (name, value) in enumerate(rows):
            self._lbl(self.res_grid, name, self.f_mid, DIM, BG,
                      anchor="e", width=20).grid(row=i, column=0, padx=10, pady=2, sticky="e")
            self._lbl(self.res_grid, str(value), self.f_mid, INK, BG,
                      anchor="w", width=12).grid(row=i, column=1, padx=10, pady=2, sticky="w")
        self.lbl_saved.config(text=save_msg)
        self._show(self.result_frame)

    def _next_trial(self):
        self.trial += 1
        self._begin_trial()


# ---------------------------------------------------------------------------
# self-test
# ---------------------------------------------------------------------------
def _selftest():
    ok = True

    def check(name, got, want):
        nonlocal ok
        good = got == want
        ok = ok and good
        print("%-40s %s   (got=%r)" % (name, "OK" if good else "FAIL", got))

    def compose(keys):
        c = HangulComposer()
        for k in keys:
            c.input_jamo(k)
        return c.text()

    check("조합 사과", compose("ㅅㅏㄱㅗㅏ"), "사과")
    check("조합 값(겹받침)", compose("ㄱㅏㅂㅅ"), "값")
    check("조합 국가(도깨비불 없음)", compose("ㄱㅜㄱㄱㅏ"), "국가")
    check("조합 의(겹모음)", compose("ㅇㅡㅣ"), "의")
    check("조합 많다", compose("ㅁㅏㄴㅎㄷㅏ"), "많다")
    check("조합 떡(쌍자음 2연타)", compose("ㄷㄷㅓㄱ"), "떡")
    check("조합 갑시(도깨비불)", compose("ㄱㅏㅂㅅㅣ"), "갑시")
    check("조합 쌀", compose("ㅅㅅㅏㄹ"), "쌀")

    c = HangulComposer()
    for k in "ㄱㅏㅂㅅ":
        c.input_jamo(k)
    c.backspace()
    check("백스페이스 값→갑", c.text(), "갑")
    c = HangulComposer()
    for k in "ㅇㅗㅏ":
        c.input_jamo(k)
    c.backspace()
    check("백스페이스 와→오", c.text(), "오")

    check("분해 학교", decompose_text("학교"), ["ㅎ", "ㅏ", "ㄱ", "ㄱ", "ㅛ"])
    check("분해 떡볶이(쌍자음 1자모)", decompose_text("떡볶이"),
          ["ㄸ", "ㅓ", "ㄱ", "ㅂ", "ㅗ", "ㄲ", "ㅇ", "ㅣ"])

    # 지표: 60초에 '사과'(자모 5) → jpm 5, WPM 1.0
    m = compute_metrics("사과", presses=5, moves=12, duration_s=60.0)
    check("지표 자모", m["jamo"], 5)
    check("지표 CPM", m["cpm_syl"], 2.0)
    check("지표 WPM", m["wpm"], 1.0)
    check("지표 선택당 이동", m["moves_per_press"], 2.4)
    check("지표 교정률 0(최소 선택)", m["correction_pct"], 0.0)
    m2 = compute_metrics("사과", presses=7, moves=12, duration_s=60.0)
    check("지표 교정률 40(2회 초과)", m2["correction_pct"], 40.0)

    # 커서 이동: 가로 순환 / 세로 비율 사상
    check("이동 오른쪽 순환", move_cursor((0, 6), 0, 1), (0, 0))
    check("이동 왼쪽 순환", move_cursor((0, 0), 0, -1), (0, 6))
    check("이동 아래(7열→3열 사상)", move_cursor((3, 6), 1, 0), (4, 2))
    check("이동 위 순환", move_cursor((0, 0), -1, 0), (4, 0))

    words, _ = load_words()
    lo, hi = WORD_SYLLABLE_RANGE
    check("단어 풀 음절 범위", all(lo <= len(w) <= hi for w in words), True)
    check("단어 풀 크기 ≥10", len(words) >= 10, True)

    # 저장 경로: CSV 열 ↔ record 키 매핑이 실제로 맞는지 (GUI 없이 검증)
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        rec = {
            "participant": "P01", "session": "S1", "posture": "desk",
            "mode": "tvsprint", "trial": 1, "started": "2026-07-12T10:00:00",
            "duration_s": 60, "words_completed": 7, "skips": 1, "presses": 61,
            "moves": 140, "backspaces": 3,
            **compute_metrics("사과나무바다", presses=61, moves=140),
            "words": [],
        }
        save_record(rec, td / "t.jsonl", csv_path=td / "c.csv", logs_dir=td)
        save_record(rec, td / "t.jsonl", csv_path=td / "c.csv", logs_dir=td)
        rows = list(csv.reader((td / "c.csv").open(encoding="utf-8-sig")))
        check("CSV 헤더 1회", rows[0], CSV_HEADER)
        check("CSV 행 2개 누적", len(rows), 3)
        check("CSV timestamp=started", rows[1][0], "2026-07-12T10:00:00")
        check("CSV wpm 열 값", float(rows[1][CSV_HEADER.index("wpm")]), rec["wpm"])
        check("JSONL 2줄", len((td / "t.jsonl").read_text(encoding="utf-8").strip().splitlines()), 2)

    print("\n결과:", "ALL OK" if ok else "FAILURES ABOVE")
    return 0 if ok else 1


def main():
    if "--selftest" in sys.argv:
        sys.exit(_selftest())
    if tk is None:
        print("tkinter를 불러올 수 없습니다. (Ubuntu: sudo apt install python3-tk)")
        sys.exit(1)
    root = tk.Tk()
    TvSprintApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
