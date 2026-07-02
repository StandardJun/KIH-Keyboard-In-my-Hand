#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""speed_test.py — 한글 1분 랜덤 단어 타자 속도 실험 GUI

서울대 창의설계축전 출품작 '장갑형 한글 키보드' 성능 실험 도구.
장갑이 OS 레벨에서 키 입력을 보내므로, 프로그램은 일반 키보드 입력과
동일하게 취급한다.

실행    : python speed_test.py   (Python 3.8+, 표준 라이브러리만 사용)
단어 목록: 같은 폴더의 word_list_ko.txt (한 줄 1단어, '#' 주석 지원)
저장    : 같은 폴더의 logs/ 아래
  1) <participant>_<session>_speed1min_<MMDD_HHMMSS>.jsonl
     — 시행(trial)당 1줄 JSON. 단어별 기록과 키 이벤트 원본 포함.
     — 파일은 [시작] 시점에 1개 만들어지고, 같은 실험자·세션의
       여러 회차(trial)가 같은 파일에 줄 단위로 append 된다.
  2) speed_sessions.csv — 전체 시행 누적 요약(1행/시행). 엑셀에서 바로
     열어 회차별 추이를 볼 수 있다(UTF-8 BOM으로 생성).

[캐비앗 — 한글 IME와 키 이벤트]
tkinter는 한글 IME 조합(composition) 중의 키 이벤트를 플랫폼별로 다르게
전달한다.
  - Windows: 조합 확정 시점에 이벤트가 몰리거나 event.char가 비어 있을 수 있음
  - macOS  : 조합 중 일부 키가 <Key>로 안 잡히거나 keysym이 비어 올 수 있음
  - Linux  : IME(ibus/fcitx) 설정에 따라 keysym/char가 다르게 옴
따라서 events / n_key_events(타수)는 '참고 지표'로만 기록·해석할 것.
성능 지표(CPM, 자모/분, WPM, MSD 오류율)는 전부 Entry 위젯에 실제로
확정된 '완성된 입력 문자열' 기준으로 계산한다.

[지표 정의]
  - 음절 수      : 입력된 완성형 한글 음절(가~힣) 개수 (60초 내 전체 입력)
  - 자모 수      : 음절을 자모로 분해한 개수 (겹모음/겹받침은 2자모,
                   쌍자음 ㄲㄸㅃㅆㅉ는 1자모)
  - CPM(음절/분) : 음절 수 × 60 / 60초
  - 자모/분(jpm) : 자모 수 × 60 / 60초
  - WPM          : 자모/분 ÷ 5
  - 미수정 오류율: MSD ER = Σ MSD(목표 자모열, 입력 자모열)
                          / Σ max(len목표, len입력) × 100
                   (제출된 단어 쌍 기준. 시간 종료 시 입력 중이던
                    미완성 단어는 분량 지표에는 포함, 오류율에서는 제외)
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
CSV_HEADER = [
    "timestamp", "participant", "session", "posture", "trial",
    "words_completed", "key_events", "backspace", "syllables", "jamo",
    "cpm_syl", "jpm", "wpm", "msd_error_pct",
]

# 타이머 시작 전이라면 무시할 키(입력 내용에 기여하지 않는 키).
# 스페이스/엔터/백스페이스로 타이머가 실수로 시작되는 것을 막는다.
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
# 한글 자모 분해 / MSD / 지표 계산 (GUI 없이 단독 테스트 가능)
# ---------------------------------------------------------------------------
CHOSEONG = "ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ"          # 19
JUNGSEONG = "ㅏㅐㅑㅒㅓㅔㅕㅖㅗㅘㅙㅚㅛㅜㅝㅞㅟㅠㅡㅢㅣ"     # 21
JONGSEONG = " ㄱㄲㄳㄴㄵㄶㄷㄹㄺㄻㄼㄽㄾㄿㅀㅁㅂㅄㅅㅆㅇㅈㅊㅋㅌㅍㅎ"  # 28 (첫 칸=받침 없음)

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
    - partial(시간 종료 시 입력 중이던 단어)은 음절/자모/CPM/WPM 분량에는
      포함하되, MSD 오류율에서는 제외한다(미완성 단어를 오타로 볼 수 없음).
    """
    typed_all = "".join(w["typed"] for w in words)
    syllables = count_syllables(typed_all)
    jamo = len(decompose_text(typed_all))
    minutes = duration_s / 60.0 if duration_s > 0 else 1.0
    cpm_syl = syllables / minutes
    jpm = jamo / minutes
    wpm = jpm / 5.0

    submitted = [w for w in words if not w.get("partial")]
    num = 0
    den = 0
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
# GUI
# ---------------------------------------------------------------------------
class SpeedTestApp:
    def __init__(self, root):
        self.root = root
        root.title("한글 타자 속도 실험 — 1분 랜덤 단어")
        root.geometry("800x580")
        root.minsize(660, 500)

        base = tkfont.nametofont("TkDefaultFont")
        family = base.actual("family")
        self.f_small = tkfont.Font(family=family, size=11)
        self.f_mid = tkfont.Font(family=family, size=14)
        self.f_entry = tkfont.Font(family=family, size=22)
        self.f_timer = tkfont.Font(family=family, size=32, weight="bold")
        self.f_target = tkfont.Font(family=family, size=46, weight="bold")

        self.pool, self.from_file = load_words()
        self.queue = deque()

        # 세션 상태
        self.participant = ""
        self.session = ""
        self.posture = POSTURES[0]
        self.trial = 1
        self.jsonl_path = None

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
        self._show(self.start_frame)

    # -- 화면 전환 ----------------------------------------------------------
    def _show(self, frame):
        for f in (self.start_frame, self.test_frame, self.result_frame):
            f.pack_forget()
        frame.pack(fill="both", expand=True)

    # -- 시작 화면 ----------------------------------------------------------
    def _build_start_frame(self):
        f = self.start_frame = tk.Frame(self.root)
        tk.Label(f, text="한글 타자 속도 실험 (1분)", font=self.f_timer).pack(pady=(46, 4))
        tk.Label(f, text="장갑형 한글 키보드 · 창의설계축전 성능 실험",
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

        tk.Label(form, text="자세 조건", font=self.f_mid).grid(row=2, column=0, sticky="e", padx=8, pady=6)
        self.cmb_posture = ttk.Combobox(form, values=list(POSTURES), state="readonly",
                                        width=10, font=self.f_mid)
        self.cmb_posture.set(POSTURES[0])
        self.cmb_posture.grid(row=2, column=1, sticky="w", padx=8, pady=6)

        tk.Button(f, text="시  작", font=self.f_mid, width=16,
                  command=self._start_session).pack(pady=30)

        note = "단어 풀: %d개" % len(self.pool)
        if not self.from_file:
            note += "  (word_list_ko.txt 없음 — 내장 예비 목록 사용 중)"
        tk.Label(f, text=note, font=self.f_small, fg="gray40").pack()
        tk.Label(f, text="결과 저장 위치: %s" % LOGS_DIR,
                 font=self.f_small, fg="gray40").pack(pady=(2, 0))

    def _start_session(self):
        p = self.ent_participant.get().strip()
        s = self.ent_session.get().strip()
        if not p or not s:
            messagebox.showwarning("입력 필요", "실험자 ID와 세션 ID를 입력하세요.")
            return
        self.participant = p
        self.session = s
        self.posture = self.cmb_posture.get() or POSTURES[0]
        self.trial = 1
        stamp = datetime.now().strftime("%m%d_%H%M%S")
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
        # 시행 상태 초기화
        self.t0 = None
        self.trial_over = False
        self.events = []
        self.words = []
        self.n_backspace = 0
        self.started_iso = None
        self.word_t_start = 0.0
        self.queue.clear()          # 매 회차 새로 섞기
        self._update_word_labels()

        self.lbl_status.config(text="%s · %s · %s · trial %d"
                               % (self.participant, self.session, self.posture, self.trial))
        self.lbl_timer.config(text="%.1f" % TRIAL_SECONDS)
        self.entry.config(state="normal")
        self.entry.delete(0, tk.END)
        self._show(self.test_frame)
        self.entry.focus_set()

    def _abort_trial(self):
        """저장 없이 시작 화면으로."""
        self.trial_over = True
        self._show(self.start_frame)

    def _on_key(self, event):
        if self.trial_over:
            return "break"
        now = time.perf_counter()
        if self.t0 is None:
            if event.keysym in NON_STARTING_KEYS:
                return None  # 타이머 시작 전 보조 키는 무시
            self.t0 = now
            self.started_iso = datetime.now().isoformat(timespec="seconds")
            self.word_t_start = 0.0
            self.root.after(50, self._tick)
        t = now - self.t0
        self.events.append({"t": round(t, 4), "keysym": event.keysym, "char": event.char})
        if event.keysym == "BackSpace":
            self.n_backspace += 1
        if event.keysym in ("Return", "KP_Enter", "space"):
            # IME 확정이 위젯에 반영된 뒤 읽도록 after_idle로 지연 제출
            self.root.after_idle(self._submit_word)
            if event.keysym != "space":
                return "break"
        return None

    def _submit_word(self):
        if self.trial_over or self.t0 is None:
            return
        text = self.entry.get().strip()
        self.entry.delete(0, tk.END)
        if not text:
            return  # 빈 제출(연속 스페이스 등)은 무시
        t_end = round(time.perf_counter() - self.t0, 4)
        self.words.append({
            "target": self.current_target,
            "typed": text,
            "t_start": round(self.word_t_start, 4),
            "t_end": t_end,
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
        if partial:  # 종료 시점에 입력 중이던 미완성 단어
            self.words.append({
                "target": self.current_target,
                "typed": partial,
                "t_start": round(self.word_t_start, 4),
                "t_end": round(TRIAL_SECONDS, 4),
                "partial": True,
            })
        self.entry.config(state="disabled")

        metrics = compute_metrics(self.words, TRIAL_SECONDS)
        record = {
            "participant": self.participant,
            "session": self.session,
            "posture": self.posture,
            "mode": "speed1min",
            "trial": self.trial,
            "started": self.started_iso or datetime.now().isoformat(timespec="seconds"),
            "duration_s": int(TRIAL_SECONDS),
            "words": self.words,
            "n_key_events": len(self.events),
            "n_backspace": self.n_backspace,
            "words_completed": metrics["words_completed"],
            "syllables": metrics["syllables"],
            "jamo": metrics["jamo"],
            "cpm_syl": metrics["cpm_syl"],
            "jpm": metrics["jpm"],
            "wpm": metrics["wpm"],
            "msd_error_pct": metrics["msd_error_pct"],
            "events": self.events,
        }
        save_msg = self._save_record(record)
        self._show_result(record, save_msg)

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


def main():
    if tk is None:
        print("tkinter를 불러올 수 없습니다. Python 표준 GUI(tkinter)가 포함된 "
              "배포판인지 확인하세요. (Ubuntu: sudo apt install python3-tk)")
        sys.exit(1)
    root = tk.Tk()
    SpeedTestApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
