#!/usr/bin/env python3
"""Keyboard In My Hand — 실험 기록기 (표준 라이브러리만 사용, Windows/Mac/Linux 공용)

사용법:
  python logger.py --mode transcribe --participant P01 --session S1        # 실험 B/C: 문장 전사
  python logger.py --mode tap --participant P01 --session S1              # 실험 A: 버튼 도달시간
  python logger.py --mode tap --self-test                                 # 장비 없이 동작 확인

출력: logs/<participant>_<session>_<mode>_<시각>.jsonl (1줄 = 1시행)
자세 조건은 세션 ID에 표기: S1-desk / S1-sofa / S1-stand
"""
import argparse
import json
import random
import time
import tkinter as tk
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
LOG_DIR = HERE / "logs"

TAP_REPS = 15          # 실험 A: 버튼당 반복 횟수 (1블록)
TRANSCRIBE_MIN = 15    # 실험 B: 세션 길이(분) — 화면에 남은 시간 표시용


def load_phrases():
    path = HERE / "phrase_set_ko.txt"
    lines = [l.strip() for l in path.read_text(encoding="utf-8").splitlines()]
    return [l for l in lines if l and not l.startswith("#")]


def load_mapping():
    path = HERE / "mapping.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


class Recorder:
    def __init__(self, participant, session, mode):
        LOG_DIR.mkdir(exist_ok=True)
        stamp = datetime.now().strftime("%m%d_%H%M%S")
        self.path = LOG_DIR / f"{participant}_{session}_{mode}_{stamp}.jsonl"
        self.meta = {"participant": participant, "session": session, "mode": mode,
                     "started": datetime.now().isoformat(timespec="seconds")}

    def write(self, record):
        record = {**self.meta, **record}
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")


class TranscribeApp:
    """실험 B/C/E: 제시 문장 전사. 키 이벤트 타임스탬프 + 최종 문자열 기록.
    hide_input=True(실험 E 블라인드 조건): 입력 문자열을 ●로 가려 시각 피드백 차단."""

    def __init__(self, root, rec, hide_input=False):
        self.rec = rec
        self.phrases = load_phrases()
        random.shuffle(self.phrases)
        self.idx = 0
        self.events = []
        self.t_first_key = None
        self.session_t0 = time.perf_counter()

        root.title("전사 실험 — 문장을 입력하고 Enter")
        root.geometry("900x300")
        self.target_var = tk.StringVar()
        self.timer_var = tk.StringVar()
        tk.Label(root, textvariable=self.timer_var, font=("", 12), fg="gray").pack(pady=4)
        tk.Label(root, textvariable=self.target_var, font=("", 20), wraplength=860).pack(pady=14)
        self.entry = tk.Entry(root, font=("", 18), width=50,
                              show="●" if hide_input else "")
        self.entry.pack(pady=10)
        self.entry.focus_set()
        self.entry.bind("<Key>", self.on_key)
        self.entry.bind("<Return>", self.on_enter)
        tk.Label(root, text="틀려도 지우지 말고 계속 입력하세요. Enter = 다음 문장",
                 font=("", 11), fg="gray").pack()
        self.root = root
        self.show_phrase()
        self.tick()

    def tick(self):
        remain = TRANSCRIBE_MIN * 60 - (time.perf_counter() - self.session_t0)
        if remain <= 0:
            self.timer_var.set("세션 종료! 창을 닫아 주세요.")
            self.entry.configure(state="disabled")
            return
        self.timer_var.set(f"남은 시간 {int(remain // 60)}:{int(remain % 60):02d}")
        self.root.after(1000, self.tick)

    def show_phrase(self):
        self.target = self.phrases[self.idx % len(self.phrases)]
        self.idx += 1
        self.target_var.set(self.target)
        self.entry.delete(0, tk.END)
        self.events = []
        self.t_first_key = None
        self.t_shown = time.perf_counter()

    def on_key(self, e):
        t = time.perf_counter()
        if e.keysym == "Return":
            return
        if self.t_first_key is None:
            self.t_first_key = t
        self.events.append({"t": round(t - self.t_shown, 4), "keysym": e.keysym,
                            "char": e.char if e.char and e.char.isprintable() else ""})

    def on_enter(self, _):
        t_end = time.perf_counter()
        typed = self.entry.get().strip()
        if not typed:
            return
        self.rec.write({
            "target": self.target, "typed": typed,
            "duration_s": round(t_end - (self.t_first_key or self.t_shown), 4),
            "n_key_events": len(self.events), "events": self.events,
        })
        self.show_phrase()


class TapApp:
    """실험 A: 목표 자모(버튼)를 표시하고 다음 keypress까지의 반응시간 기록."""

    def __init__(self, root, rec, mapping, self_test=False):
        self.rec = rec
        if mapping:
            # 매핑의 자모를 자극으로 사용, keysym_hint로 정오 판정
            self.stimuli = [(b["jamo"], bid, b.get("keysym_hint", ""))
                            for bid, b in mapping["buttons"].items()]
        else:
            # mapping.json 없이도 동작(자체 테스트): 두벌식 기본 자모 16개
            fallback = "ㄱㄴㄷㄹㅁㅂㅅㅇㅏㅓㅗㅜㅡㅣㅔㅐ"
            self.stimuli = [(j, f"B{i:02d}", "") for i, j in enumerate(fallback)]
        seq = self.stimuli * TAP_REPS
        random.shuffle(seq)
        # 같은 자극 연속 방지
        for i in range(1, len(seq)):
            if seq[i][0] == seq[i - 1][0]:
                for k in range(i + 1, len(seq)):
                    if seq[k][0] != seq[i - 1][0]:
                        seq[i], seq[k] = seq[k], seq[i]
                        break
        self.queue = seq
        self.pos = 0
        self.self_test = self_test

        root.title("버튼 도달시간 실험 — 표시된 자모의 버튼을 누르세요")
        root.geometry("600x340")
        self.progress_var = tk.StringVar()
        self.stim_var = tk.StringVar()
        tk.Label(root, textvariable=self.progress_var, font=("", 12), fg="gray").pack(pady=6)
        tk.Label(root, textvariable=self.stim_var, font=("", 96, "bold")).pack(pady=20)
        tk.Label(root, text="최대한 빠르고 정확하게. 잘못 눌러도 멈추지 말 것.",
                 font=("", 11), fg="gray").pack()
        root.bind("<Key>", self.on_key)
        self.root = root
        self.accept = False
        self.next_stim()

    def next_stim(self):
        if self.pos >= len(self.queue):
            self.stim_var.set("끝!")
            self.progress_var.set("블록 완료 — 창을 닫아 주세요.")
            self.accept = False
            return
        self.jamo, self.button_id, self.hint = self.queue[self.pos]
        self.stim_var.set(self.jamo)
        self.progress_var.set(f"{self.pos + 1} / {len(self.queue)}")
        self.t_shown = time.perf_counter()
        self.accept = True

    def on_key(self, e):
        if not self.accept:
            return
        t = time.perf_counter()
        self.accept = False
        pressed = e.char if e.char and e.char.isprintable() else e.keysym
        correct = None
        if self.hint:
            correct = (pressed == self.hint) or (e.keysym == self.hint) or (e.char == self.jamo)
        elif self.self_test:
            correct = True
        self.rec.write({
            "stim_jamo": self.jamo, "button_id": self.button_id,
            "rt_s": round(t - self.t_shown, 4), "pressed": pressed, "correct": correct,
        })
        self.pos += 1
        # 500ms 간격 후 다음 자극
        self.root.after(500, self.next_stim)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["transcribe", "tap"], required=True)
    ap.add_argument("--participant", default="TEST")
    ap.add_argument("--session", default="S0")
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--hide-input", action="store_true",
                    help="실험 E 블라인드 조건: 입력 문자열을 가림")
    args = ap.parse_args()

    rec = Recorder(args.participant, args.session, args.mode)
    root = tk.Tk()
    if args.mode == "transcribe":
        TranscribeApp(root, rec, hide_input=args.hide_input)
    else:
        TapApp(root, rec, load_mapping(), self_test=args.self_test)
    print(f"기록 파일: {rec.path}")
    root.mainloop()
    print(f"저장 완료: {rec.path}")


if __name__ == "__main__":
    main()
