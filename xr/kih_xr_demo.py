#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
kih_xr_demo.py — Keyboard In My Hand, 장갑 없는 XR 시연 (vision-only) · 통합 앱
==========================================================================

KIH의 본질은 장갑이라는 폼팩터가 아니라 **입력 메커니즘**이다.

    마디 스윗스팟(손가락 마디 위 16개 위치) × 가획 연타(같은 위치 2·3연타 = ㄱ→ㅋ→ㄲ)
    × 두벌식 전이(왼손 자음 · 오른손 모음 · 순차 입력)

이 프로그램은 그 메커니즘을 **물리 스위치 없이** 손 추적(hand tracking)만으로 돌린다.

    웹캠 → MediaPipe Hand Landmarker(오픈소스, Apache-2.0)가 양손 21관절을 추정
        → 장갑의 택트 스위치 자리(첫째·둘째 마디)를 관절 좌표로 계산한 '가상 버튼' 16개
          (사용자별 스윗스팟 오프셋(t, s)으로 보정 — 캘리브레이션)
        → 같은 손 엄지 끝이 가상 버튼에 닿는 순간 = 탭 (TapDetector)
        → 펌웨어(firmware/keyboard_glove/keyboard_glove.ino)의 연타 상태머신을 그대로 이식한 MultiTapEngine이 자모 확정
           (연타 윈도우 · early commit · 최대 연타 즉시 확정 · 디바운스 — 로직 동일)
        → 두벌식 오토마타(HangulComposer)가 음절 조합 → 텍스트박스 (옵션: --hid 로 OS에 키 입력)

즉 "손 관절 좌표를 주는 장치라면 무엇이든" 같은 코드 경로로 KIH가 돈다는 것이 시연의 요지다:
웹캠(MediaPipe) · Apple Vision Pro(ARKit HandAnchor) · Quest(OpenXR XR_EXT_hand_tracking).
관절 색인 대응표는 JOINT_TABLE 참조 — 다른 기기로 옮길 때 바꿀 것은 landmark 공급부 하나다.

하나의 프로그램 = 로컬 웹 앱 (추가 의존성 없음: 표준 http.server + 브라우저)
--------------------------------------------------------------------------
    pip install mediapipe opencv-python pillow numpy        # (--hid 쓰려면 pynput 추가)
    python kih_xr_demo.py                                    # 서버 실행 + 브라우저 자동 오픈 (http://127.0.0.1:7890)
    python kih_xr_demo.py --camera 1 --width 1280 --height 720 --port 7890 --no-browser
    python kih_xr_demo.py --video clip.mp4 --loop            # 녹화본으로 UI 시연
    python kih_xr_demo.py --nogui                            # 브라우저 대신 OpenCV 창
    python kih_xr_demo.py --nogui --video clip.mp4 --record out.mp4 --no-window   # 헤드리스 처리
    python kih_xr_demo.py --selftest                         # 카메라 없이 로직 검증

브라우저 화면 = 실시간 vision 오버레이(MJPEG) + 캘리브레이션 마법사 + 파라미터 슬라이더 + 텍스트박스.
  캘리브레이션 4단계(프로필 JSON으로 저장 → 다음 실행 때 자동 로드):
    1) 손 확인   — 손바닥을 카메라로 향한 상태에서 좌우 라벨 자동 검증(틀리면 자동 반전)
    2) 스윗스팟  — 16개 버튼을 하나씩 엄지로 누른 채 1초 유지 → 각 마디 위 실제 접촉점(t, s)을 버튼 중심으로 채택
    3) 탭 반경   — 2)의 접촉 잔차 분포와 '엄지를 뗀 편안한 자세'의 거리 분포 사이에서 press/release 임계 결정
    4) 연타 윈도우 — ㄱ 빠른 2연타 ×5 와 '따로 두 번' ×5 의 간격 분포 오분류 최소 임계 (펌웨어 tap_calibration.py 와 같은 원리)

시연 요령
---------
  * 두 손바닥을 카메라 쪽으로(장갑 버튼이 손바닥 쪽에 있었던 것과 같은 전제). 첫째 마디 = 손끝 쪽 지골(DIP–TIP),
    둘째 마디 = 중간 지골(PIP–DIP). 같은 손 엄지로 톡톡.
    기능키(왼손 BS · 오른손 Space)는 검지 밑마디(손바닥 쪽 구간).
  * 연타 윈도우 기본 450ms(펌웨어 300; 30fps 카메라 지연 보상). 개인화 대상 파라미터라는 점은 장갑과 같다.
  * 손바닥 게이트: MediaPipe 좌우 라벨과 손바닥 기하가 어긋난 손(=손등이 보임)은 입력 차단 + 경고.

매핑은 experiments/mapping.json(정본 = PPT 슬라이드 12)을 읽고, 없으면 내장 사본을 쓴다.
"""
from __future__ import annotations

import argparse
import glob
import json
import math
import os
import platform
import queue
import sys
import threading
import time
import urllib.request
import webbrowser
from collections import deque
from dataclasses import dataclass
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Dict, List, Optional, Tuple

os.environ.setdefault("GLOG_minloglevel", "2")  # mediapipe C++ 로그 소음 억제 (import 전에 설정)

try:
    import numpy as np
except ImportError:  # --install / 안내 메시지는 numpy 없이도 떠야 한다
    np = None

__version__ = "0.2.0"
HERE = Path(__file__).resolve().parent
PROFILE_DIR = HERE / "profiles"
# 인수 없이 실행할 때(VS Code ▶) 쓸 카메라 번호. 이 맥: 0 = iPhone 연속성 카메라, 1 = 맥북 내장 캠.
# None 으로 두면 mac_builtin_camera_index() 폴백을 쓰는데, 그 함수는 AVFoundation 목록 순서 = OpenCV 색인
# 순서를 가정한다. 이 맥에서는 어긋나서(목록은 FaceTime 이 먼저지만 OpenCV 로는 1번) 0 = iPhone 을 내장 캠으로
# 잘못 고른다. 같은 이유로 --camera-name FaceTime 도 틀린 번호를 준다 → 번호를 명시하는 이 상수를 쓴다.
DEFAULT_CAMERA_INDEX: Optional[int] = 1

# ---------------------------------------------------------------------------
# 관절 색인 — MediaPipe 21 landmarks ↔ visionOS ↔ OpenXR (기기 이식 시 이 표만 바꾼다)
# ---------------------------------------------------------------------------
JOINT_TABLE = """
 idx | 부위                 | visionOS HandSkeleton.JointName                       | OpenXR XR_HAND_JOINT_*
-----+----------------------+-------------------------------------------------------+-------------------------------
  0  | 손목                 | .wrist                                                | WRIST
 1-4 | 엄지 CMC/MCP/IP/TIP  | .thumbKnuckle/.thumbIntermediateBase/.thumbIntermediateTip/.thumbTip | THUMB_METACARPAL/PROXIMAL/DISTAL/TIP
 5-8 | 검지 MCP/PIP/DIP/TIP | .indexFingerKnuckle/.indexFingerIntermediateBase/.indexFingerIntermediateTip/.indexFingerTip | INDEX_PROXIMAL/INTERMEDIATE/DISTAL/TIP
 9-12| 중지 (동일 패턴)     | .middleFinger*                                        | MIDDLE_*
13-16| 약지                 | .ringFinger*                                          | RING_*
17-20| 소지                 | .littleFinger*                                        | LITTLE_*
"""
WRIST, THUMB_TIP = 0, 4
FINGERS = ("index", "middle", "ring", "pinky")
FINGER_NO = {"index": 1, "middle": 2, "ring": 3, "pinky": 4}
FINGER_KO = {"index": "검지", "middle": "중지", "ring": "약지", "pinky": "소지"}
FINGER_JOINTS = {  # (MCP, PIP, DIP, TIP)
    "index": (5, 6, 7, 8), "middle": (9, 10, 11, 12), "ring": (13, 14, 15, 16), "pinky": (17, 18, 19, 20),
}
# 마디(row) → 지골 구간. 실물(PPT 슬라이드 12·13 사진) 기준: 첫째 마디 = 손끝 쪽(DIP–TIP), 둘째 = 중간(PIP–DIP)
ROW_SEGMENT = {"a": (2, 3), "b": (1, 2), "c": (0, 1)}   # c = 밑마디(MCP–PIP) — 기능키(L5/R5) 전용
ROW_KO = {"a": "첫째 마디", "b": "둘째 마디", "c": "밑마디"}
HAND_CONNECTIONS = [(0, 1), (1, 2), (2, 3), (3, 4), (0, 5), (5, 6), (6, 7), (7, 8), (5, 9), (9, 10), (10, 11),
                    (11, 12), (9, 13), (13, 14), (14, 15), (15, 16), (13, 17), (17, 18), (18, 19), (19, 20), (0, 17)]

MODEL_URL = ("https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/"
             "float16/1/hand_landmarker.task")

# ---------------------------------------------------------------------------
# 매핑 (experiments/mapping.json 사본 — 정본은 PPT 슬라이드 12, 팀 확정 2026-07-11)
# ---------------------------------------------------------------------------
MAPPING_FALLBACK = {
    "buttons": {
        "L1a": {"jamo": "ㄱ"}, "L1b": {"jamo": "ㅅ"}, "L2a": {"jamo": "ㄴ"}, "L2b": {"jamo": "ㅈ"},
        "L3a": {"jamo": "ㄷ"}, "L3b": {"jamo": "ㅇ"}, "L4": {"jamo": "ㅂ"}, "L5": {"jamo": "BACKSPACE"},
        "R1a": {"jamo": "ㅓ"}, "R1b": {"jamo": "ㅗ"}, "R2a": {"jamo": "ㅏ"}, "R2b": {"jamo": "ㅜ"},
        "R3a": {"jamo": "ㅐ"}, "R3b": {"jamo": "ㅣ"}, "R4": {"jamo": "ㅔ"}, "R5": {"jamo": "SPACE"},
    },
    "sequences": {
        "ㅋ": ["L1a", "L1a"], "ㄲ": ["L1a", "L1a", "L1a"], "ㅁ": ["L1b", "L1b"], "ㅆ": ["L1b", "L1b", "L1b"],
        "ㄹ": ["L2a", "L2a"], "ㅊ": ["L2b", "L2b"], "ㅉ": ["L2b", "L2b", "L2b"], "ㅌ": ["L3a", "L3a"],
        "ㄸ": ["L3a", "L3a", "L3a"], "ㅎ": ["L3b", "L3b"], "ㅍ": ["L4", "L4"], "ㅃ": ["L4", "L4", "L4"],
        "ㅕ": ["R1a", "R1a"], "ㅛ": ["R1b", "R1b"], "ㅑ": ["R2a", "R2a"], "ㅠ": ["R2b", "R2b"],
        "ㅒ": ["R3a", "R3a"], "ㅡ": ["R3b", "R3b"], "ㅖ": ["R4", "R4"], ".": ["R5", "R5"],
        "ENTER": ["R5", "R5", "R5"],
    },
}
SPECIAL_TOKENS = {"BACKSPACE", "SPACE", "ENTER"}
TOKEN_SHORT = {"BACKSPACE": "BS", "SPACE": "SP", "ENTER": "ENT"}  # 화면 표기 (한글 폰트에 없는 기호 회피)


def find_mapping_file(explicit: Optional[str]) -> Optional[Path]:
    cands = [Path(explicit)] if explicit else []
    cands += [HERE / "mapping.json", HERE.parent / "experiments" / "mapping.json",
              HERE.parent / "firmware" / "keyboard_glove_fixed" / "mapping.json",
              HERE.parent / "firmware" / "keyboard_glove" / "mapping.json"]
    for p in cands:
        if p.is_file():
            return p
    return None


def load_mapping(path: Optional[str] = None) -> Tuple[dict, str]:
    """(mapping, 출처 설명). 파일이 있으면 내장 사본과 대조해 다르면 경고."""
    p = find_mapping_file(path)
    if p is None:
        return MAPPING_FALLBACK, "내장 사본"
    with open(p, encoding="utf-8") as f:
        raw = json.load(f)
    m = {"buttons": {k: {"jamo": v["jamo"]} for k, v in raw["buttons"].items() if not k.startswith("_")},
         "sequences": {k: v for k, v in raw["sequences"].items() if not k.startswith("_")}}
    if m != MAPPING_FALLBACK:
        print(f"[warn] {p} 가 내장 사본과 다릅니다 — 파일 쪽을 씁니다. 내장 사본도 갱신할 것.", file=sys.stderr)
    return m, str(p)


def build_tap_table(mapping: dict) -> Dict[str, Dict[int, str]]:
    """버튼 → {탭수: 토큰}. 예: L1a → {1:'ㄱ', 2:'ㅋ', 3:'ㄲ'}"""
    table = {bid: {1: info["jamo"]} for bid, info in mapping["buttons"].items()}
    for token, seq in mapping["sequences"].items():
        if len(set(seq)) != 1:
            raise ValueError(f"연타 시퀀스는 같은 버튼 반복이어야 함: {token}={seq}")
        table[seq[0]][len(seq)] = token
    return table


def hand_layout(side: str) -> Dict[str, Tuple[str, str, float, float]]:
    """버튼 ID → (손가락, 마디, t, s) 기본 위치.
    검지~약지 = 첫째·둘째 마디 정중앙. 소지 = 첫째 마디.
    기능키(L5 BS / R5 Space) = **검지 밑마디**(손바닥 쪽 MCP–PIP 구간) — 엄지로 바로 누른다."""
    lay: Dict[str, Tuple[str, str, float, float]] = {}
    for finger in ("index", "middle", "ring"):
        n = FINGER_NO[finger]
        lay[f"{side}{n}a"] = (finger, "a", 0.5, 0.0)
        lay[f"{side}{n}b"] = (finger, "b", 0.5, 0.0)
    lay[f"{side}4"] = ("pinky", "a", 0.5, 0.0)
    lay[f"{side}5"] = ("index", "c", 0.5, 0.0)
    return lay


def button_location_ko(bid: str) -> str:
    side = "왼손" if bid[0] == "L" else "오른손"
    n = int(bid[1])
    if n == 4:
        return f"{side} 소지 첫째 마디"
    if n == 5:
        return f"{side} 검지 밑마디"
    finger = {1: "검지", 2: "중지", 3: "약지"}[n]
    return f"{side} {finger} {ROW_KO[bid[2]]}"


# ---------------------------------------------------------------------------
# 연타 엔진 — keyboard_glove_fixed.ino 의 handleSide()/flushExcept() 이식
# ---------------------------------------------------------------------------
@dataclass
class KeyEvent:
    token: str      # 'ㄱ' / 'ㅋ' / 'SPACE' / 'BACKSPACE' / 'ENTER' / '.'
    button: str
    taps: int
    t_ms: float


class MultiTapEngine:
    """펌웨어와 같은 규칙:
    - 같은 버튼을 tap_window 안에 다시 누르면 탭 수 +1 (파생 자모)
    - 윈도우 만료 시 대기분 확정; 최대 연타(자음 3·모음 2·기능키 1/3)에 닿으면 즉시 확정
    - early_commit: 다른 버튼이 눌리면 대기 중이던 버튼 즉시 확정(양손 통틀어; 펌웨어 flushExcept와 동일)
    - debounce: 같은 버튼 재눌림이 debounce_ms 이내면 무시
    """

    def __init__(self, tap_table: Dict[str, Dict[int, str]], tap_window_ms: float = 300.0,
                 early_commit: bool = True, debounce_ms: float = 30.0, window_mode: str = "first"):
        self.table = tap_table
        self.max_tap = {b: max(t) for b, t in tap_table.items()}
        self.window = float(tap_window_ms)
        self.early_commit = early_commit
        self.debounce = float(debounce_ms)
        # window_mode: 'first' = 펌웨어와 동일(첫 탭부터 윈도우) · 'last' = 마지막 탭부터 다시 잼(롤링).
        # 카메라(30fps)에선 탭 간격이 물리 스위치보다 길어 3연타가 첫 탭 기준 윈도우를 넘기기 쉬우므로 시연 기본값은 'last'.
        # tap_calibration.py 가 재는 것도 '탭 사이 간격'이라 롤링 기준과 일치한다.
        self.window_mode = window_mode
        self.count = {b: 0 for b in tap_table}
        self.first = {b: 0.0 for b in tap_table}
        self.last = {b: 0.0 for b in tap_table}
        self.last_edge = {b: -1e12 for b in tap_table}
        self._out: List[KeyEvent] = []

    def _emit(self, b: str, taps: int, t: float) -> None:
        taps = max(1, min(taps, self.max_tap[b]))
        tok = self.table[b].get(taps) or self.table[b][1]
        self._out.append(KeyEvent(tok, b, taps, t))

    def _flush_except(self, b: str, t: float) -> None:
        for o in self.count:
            if o != b and self.count[o]:
                self._emit(o, self.count[o], t)
                self.count[o] = 0

    def press(self, b: str, t: float) -> None:
        """버튼 b 눌림 에지 (t: ms)."""
        if b not in self.count:
            return
        if t - self.last_edge[b] <= self.debounce:
            return
        self.last_edge[b] = t
        if self.early_commit:
            self._flush_except(b, t)
        if self.count[b] == 0 or (t - self._ref(b) > self.window):
            if self.count[b]:
                self._emit(b, self.count[b], t)
            self.count[b] = 1
            self.first[b] = t
        else:
            self.count[b] += 1
        self.last[b] = t
        if self.count[b] >= self.max_tap[b]:
            self._emit(b, self.count[b], t)
            self.count[b] = 0

    def _ref(self, b: str) -> float:
        return self.last[b] if self.window_mode == "last" else self.first[b]

    def tick(self, t: float) -> None:
        """윈도우 만료 확인 — 펌웨어 loop()처럼 매 프레임 호출."""
        for b in self.count:
            if self.count[b] and (t - self._ref(b) > self.window):
                self._emit(b, self.count[b], t)
                self.count[b] = 0

    def flush_all(self, t: float) -> None:
        for b in self.count:
            if self.count[b]:
                self._emit(b, self.count[b], t)
                self.count[b] = 0

    def pending(self) -> Dict[str, Tuple[int, float]]:
        """{버튼: (탭 수, 윈도우 기준 시각)} — 표시용 호(arc)는 기준 시각부터 남은 시간을 그린다."""
        return {b: (c, self._ref(b)) for b, c in self.count.items() if c}

    def drain(self) -> List[KeyEvent]:
        out, self._out = self._out, []
        return out


# ---------------------------------------------------------------------------
# 한글 조합 오토마타 — experiments/tv_osk_test.py 의 HangulComposer 와 동일 규약
# ---------------------------------------------------------------------------
CHOSEONG = "ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ"
JUNGSEONG = "ㅏㅐㅑㅒㅓㅔㅕㅖㅗㅘㅙㅚㅛㅜㅝㅞㅟㅠㅡㅢㅣ"
JONGSEONG = " ㄱㄲㄳㄴㄵㄶㄷㄹㄺㄻㄼㄽㄾㄿㅀㅁㅂㅄㅅㅆㅇㅈㅊㅋㅌㅍㅎ"
COMPOUND = {
    "ㅘ": "ㅗㅏ", "ㅙ": "ㅗㅐ", "ㅚ": "ㅗㅣ", "ㅝ": "ㅜㅓ", "ㅞ": "ㅜㅔ", "ㅟ": "ㅜㅣ", "ㅢ": "ㅡㅣ",
    "ㄳ": "ㄱㅅ", "ㄵ": "ㄴㅈ", "ㄶ": "ㄴㅎ", "ㄺ": "ㄹㄱ", "ㄻ": "ㄹㅁ", "ㄼ": "ㄹㅂ", "ㄽ": "ㄹㅅ",
    "ㄾ": "ㄹㅌ", "ㄿ": "ㄹㅍ", "ㅀ": "ㄹㅎ", "ㅄ": "ㅂㅅ",
}
VOWEL_COMBINE = {v: k for k, v in COMPOUND.items() if k in JUNGSEONG}
JONG_COMBINE = {v: k for k, v in COMPOUND.items() if k in JONGSEONG}
JONG_SPLIT = {v: (k[0], k[1]) for k, v in JONG_COMBINE.items()}
VOWEL_REDUCE = {v: k[0] for k, v in VOWEL_COMBINE.items()}


class HangulComposer:
    """단순 두벌식 오토마타 (도깨비불·겹받침·겹모음 지원). 쌍자음/ㅒㅖ는 자모로 직접 들어온다."""

    def __init__(self):
        self.committed: List[str] = []
        self.cho = self.jung = self.jong = None

    def _render_current(self) -> str:
        if self.cho is not None and self.jung is not None:
            jong_i = JONGSEONG.index(self.jong) if self.jong else 0
            return chr(0xAC00 + CHOSEONG.index(self.cho) * 588 + JUNGSEONG.index(self.jung) * 28 + jong_i)
        return self.cho or self.jung or ""

    def text(self) -> str:
        return "".join(self.committed) + self._render_current()

    def _commit(self) -> None:
        cur = self._render_current()
        if cur:
            self.committed.append(cur)
        self.cho = self.jung = self.jong = None

    def input_jamo(self, j: str) -> None:
        if j in CHOSEONG:
            self._input_consonant(j)
        elif j in JUNGSEONG:
            self._input_vowel(j)
        else:
            self._commit()
            self.committed.append(j)

    def _input_consonant(self, c: str) -> None:
        if self.jung is None:
            if self.cho is None:
                self.cho = c
            else:
                self._commit()
                self.cho = c
        elif self.cho is None:
            self._commit()
            self.cho = c
        elif self.jong is None:
            if c in JONGSEONG:
                self.jong = c
            else:
                self._commit()
                self.cho = c
        else:
            comb = JONG_COMBINE.get(self.jong + c)
            if comb:
                self.jong = comb
            else:
                self._commit()
                self.cho = c

    def _input_vowel(self, v: str) -> None:
        if self.jong is not None:
            if self.jong in JONG_SPLIT:
                keep, move = JONG_SPLIT[self.jong]
            else:
                keep, move = None, self.jong
            self.jong = keep
            self._commit()
            self.cho, self.jung = move, v
        elif self.jung is None:
            self.jung = v
        else:
            comb = VOWEL_COMBINE.get(self.jung + v)
            if comb:
                self.jung = comb
            else:
                self._commit()
                self.jung = v

    def input_space(self) -> None:
        self._commit()
        self.committed.append(" ")

    def input_enter(self) -> None:
        self._commit()
        self.committed.append("\n")

    def backspace(self) -> None:
        if self.jong is not None:
            self.jong = JONG_SPLIT[self.jong][0] if self.jong in JONG_SPLIT else None
        elif self.jung is not None:
            self.jung = VOWEL_REDUCE.get(self.jung)
        elif self.cho is not None:
            self.cho = None
        elif self.committed:
            self.committed.pop()

    def clear(self) -> None:
        self.committed.clear()
        self.cho = self.jung = self.jong = None

    def feed(self, token: str) -> None:
        if token == "BACKSPACE":
            self.backspace()
        elif token == "SPACE":
            self.input_space()
        elif token == "ENTER":
            self.input_enter()
        else:
            self.input_jamo(token)


def decompose_text(text: str) -> List[str]:
    """문자열 → 두벌식 키스트로크 토큰 열 (겹모음·겹받침 분해, 쌍자음 단일)."""
    out: List[str] = []
    for ch in text:
        code = ord(ch)
        if 0xAC00 <= code <= 0xD7A3:
            code -= 0xAC00
            cho, jung, jong = code // 588, (code % 588) // 28, code % 28
            out.append(CHOSEONG[cho])
            jv = JUNGSEONG[jung]
            out.extend(COMPOUND.get(jv, jv))
            if jong:
                jc = JONGSEONG[jong]
                out.extend(COMPOUND.get(jc, jc))
        elif ch == " ":
            out.append("SPACE")
        elif ch == "\n":
            out.append("ENTER")
        elif ch in COMPOUND:
            out.extend(COMPOUND[ch])
        else:
            out.append(ch)
    return out


# 두벌식 QWERTY 키 (펌웨어 L_KEYS/R_KEYS 와 동일) — --hid 옵션용
DUBEOLSIK_KEY = {
    "ㄱ": "r", "ㄲ": "R", "ㄴ": "s", "ㄷ": "e", "ㄸ": "E", "ㄹ": "f", "ㅁ": "a", "ㅂ": "q", "ㅃ": "Q",
    "ㅅ": "t", "ㅆ": "T", "ㅇ": "d", "ㅈ": "w", "ㅉ": "W", "ㅊ": "c", "ㅋ": "z", "ㅌ": "x", "ㅍ": "v", "ㅎ": "g",
    "ㅏ": "k", "ㅐ": "o", "ㅑ": "i", "ㅒ": "O", "ㅓ": "j", "ㅔ": "p", "ㅕ": "u", "ㅖ": "P", "ㅗ": "h",
    "ㅛ": "y", "ㅜ": "n", "ㅠ": "b", "ㅡ": "m", "ㅣ": "l",
}


class HidOutput:
    """--hid: 확정 토큰을 OS 키 입력으로 보낸다(pynput). 장갑이 USB HID로 두벌식 키코드를 보내는 것과 같은 계층.
    OS 입력기가 한글 상태여야 한다."""

    def __init__(self):
        from pynput.keyboard import Controller, Key  # noqa: WPS433 (선택 의존성)
        self.kb, self.Key = Controller(), Key

    def send(self, token: str) -> None:
        if token == "BACKSPACE":
            self.kb.tap(self.Key.backspace)
        elif token == "SPACE":
            self.kb.tap(self.Key.space)
        elif token == "ENTER":
            self.kb.tap(self.Key.enter)
        elif token in DUBEOLSIK_KEY:
            self.kb.type(DUBEOLSIK_KEY[token])
        else:
            self.kb.type(token)


# ---------------------------------------------------------------------------
# 손 기하 — 관절 좌표 → 가상 버튼(zone), 스케일, 손바닥 방향, 스윗스팟 오프셋
# ---------------------------------------------------------------------------
ZoneOffsets = Dict[str, Tuple[float, float]]   # button → (t, s): 지골 구간 A→B 위 비율 t, 옆 방향 s (구간 길이 배수)
DEFAULT_OFFSET = (0.5, 0.0)


@dataclass
class Zone:
    button: str
    finger: str
    row: str
    center: np.ndarray  # (3,) 원본 프레임 픽셀 좌표 (x, y, z·W)


@dataclass
class HandObs:
    side: str                # 최종 판정 'L' / 'R'
    P: np.ndarray            # (21, 3) 원본 프레임 픽셀 좌표
    scale: float
    zones: List[Zone]
    thumb: np.ndarray        # (3,)
    model_label: str = "?"
    model_score: float = 0.0
    geom_label: str = "?"
    palm_ok: bool = True
    Pw: Optional[np.ndarray] = None      # (21, 3) world landmarks (m, 손 중심) — 깊이 방향 들어올림 감지용
    scale_w: float = 1.0
    zones_w: Optional[Dict[str, np.ndarray]] = None   # button → world 좌표 버튼 중심
    thumb_w: Optional[np.ndarray] = None


def world_landmarks_to_np(lms) -> np.ndarray:
    return np.array([[lm.x, lm.y, lm.z] for lm in lms], dtype=np.float32)


def make_zones_world(side: str, Pw: np.ndarray, offsets: Optional[ZoneOffsets] = None) -> Dict[str, np.ndarray]:
    """world 좌표 버튼 중심: 구간 A→B 위 비율 t 만 적용(옆 오프셋 s 는 3D 에서 정의가 모호하고, 3D 거리는 상대 변화(들어올림)에만 쓴다)."""
    out = {}
    for bid, (finger, row, t0, _s0) in hand_layout(side).items():
        t, _ = (offsets or {}).get(bid, (t0, _s0))
        A, B = segment_points(Pw, finger, row)
        out[bid] = (A + t * (B - A)).astype(np.float32)
    return out


def landmarks_to_np(lms, w: int, h: int) -> np.ndarray:
    return np.array([[lm.x * w, lm.y * h, lm.z * w] for lm in lms], dtype=np.float32)


def hand_scale(P: np.ndarray) -> float:
    """손 크기 기준 길이: (손목–중지 MCP)와 (검지 MCP–소지 MCP)의 평균. 탭 반경·속도를 이 값으로 정규화."""
    a = float(np.linalg.norm(P[9, :2] - P[0, :2]))
    b = float(np.linalg.norm(P[17, :2] - P[5, :2]))
    return max(1.0, 0.5 * (a + b))


def palm_winding(P: np.ndarray) -> float:
    """손목→검지MCP, 손목→소지MCP 2D 외적. 손바닥이 카메라를 향할 때 오른손 <0, 왼손 >0 (원본 프레임, y↓)."""
    u = P[5, :2] - P[0, :2]
    v = P[17, :2] - P[0, :2]
    return float(u[0] * v[1] - u[1] * v[0])


def button_finger_row(bid: str) -> Tuple[str, str]:
    finger, row, _, _ = hand_layout(bid[0])[bid]
    return finger, row


def segment_points(P: np.ndarray, finger: str, row: str) -> Tuple[np.ndarray, np.ndarray]:
    """마디(row)의 지골 구간 양 끝 관절 (A=손목 쪽, B=손끝 쪽)."""
    joints = FINGER_JOINTS[finger]
    i, j = ROW_SEGMENT[row]
    return P[joints[i]], P[joints[j]]


def _seg_frame(A: np.ndarray, B: np.ndarray):
    d = (B - A)[:2].astype(np.float64)
    L = max(1e-6, float(np.hypot(d[0], d[1])))
    e = d / L
    n = np.array([-e[1], e[0]])
    return L, e, n


def zone_center(A: np.ndarray, B: np.ndarray, t: float, s: float) -> np.ndarray:
    L, e, n = _seg_frame(A, B)
    c = A.astype(np.float64) + t * (B.astype(np.float64) - A.astype(np.float64))
    c[:2] += s * L * n
    return c.astype(np.float32)


def local_coords(A: np.ndarray, B: np.ndarray, pt: np.ndarray) -> Tuple[float, float]:
    """점 pt 를 구간 A→B 의 국소 좌표 (t, s)로. 회전·크기 불변 → 캘리브레이션 값이 손 자세와 무관하게 재사용된다."""
    L, e, n = _seg_frame(A, B)
    v = (pt[:2] - A[:2]).astype(np.float64)
    return float(np.dot(v, e) / L), float(np.dot(v, n) / L)


def make_zones(side: str, P: np.ndarray, offsets: Optional[ZoneOffsets] = None) -> List[Zone]:
    zones = []
    for bid, (finger, row, t0, s0) in hand_layout(side).items():
        t, s = (offsets or {}).get(bid, (t0, s0))
        A, B = segment_points(P, finger, row)
        zones.append(Zone(bid, finger, row, zone_center(A, B, t, s)))
    return zones


def make_hand_obs(P: np.ndarray, model_label: str, model_score: float, hand_mode: str,
                  offsets: Optional[ZoneOffsets] = None, Pw: Optional[np.ndarray] = None) -> HandObs:
    geom = "R" if palm_winding(P) < 0 else "L"
    model = "R" if model_label.lower().startswith("r") else "L"
    if hand_mode == "model-swap":
        model = "L" if model == "R" else "R"
    if hand_mode == "geom":
        side, palm_ok = geom, True
    else:
        side, palm_ok = model, (geom == model)
    obs = HandObs(side=side, P=P, scale=hand_scale(P), zones=make_zones(side, P, offsets),
                  thumb=P[THUMB_TIP].copy(), model_label=model_label, model_score=model_score,
                  geom_label=geom, palm_ok=palm_ok)
    if Pw is not None:
        obs.Pw = Pw
        obs.scale_w = max(1e-3, 0.5 * (float(np.linalg.norm(Pw[9] - Pw[0])) + float(np.linalg.norm(Pw[17] - Pw[5]))))
        obs.zones_w = make_zones_world(side, Pw, offsets)
        obs.thumb_w = Pw[THUMB_TIP].copy()
    return obs


def assign_sides(raw_hands: List[tuple], hand_mode: str, offsets: Optional[ZoneOffsets] = None) -> Dict[str, HandObs]:
    """검출된 손들 → {'L': obs, 'R': obs}. 같은 라벨이 둘이면 점수 낮은 쪽을 반대편으로 돌린다.
    raw_hands 원소 = (P, label, score) 또는 (P, label, score, Pw)."""
    obs_list = [make_hand_obs(h[0], h[1], h[2], hand_mode, offsets, h[3] if len(h) > 3 else None) for h in raw_hands]
    obs_list.sort(key=lambda o: -o.model_score)
    out: Dict[str, HandObs] = {}
    for o in obs_list:
        if o.side in out:
            other = "L" if o.side == "R" else "R"
            if other in out:
                continue
            o.side = other
            o.zones = make_zones(other, o.P, offsets)
            if o.Pw is not None:
                o.zones_w = make_zones_world(other, o.Pw, offsets)
            o.palm_ok = hand_mode == "geom"
        out[o.side] = o
    return out


# ---------------------------------------------------------------------------
# 탭 검출 — 엄지 끝이 가상 버튼에 '닿는' 순간을 눌림 에지로
# ---------------------------------------------------------------------------
@dataclass
class TapParams:
    press: float = 0.30       # 눌림 판정 반경 (손 스케일 배수)
    release: float = 0.45     # 절대 해제 반경 (히스테리시스)
    rebound: float = 0.15     # 상대 해제: 최저점에서 이만큼 멀어지면 떼었다고 본다 (같은 자리 연타용)
    dwell_ms: float = 30.0    # 반경 안에 이 시간 이상 머물러야 탭 (스쳐 지나감 배제; 30fps에서 2프레임)
    max_speed: float = 8.0    # 엄지 속도 상한 (스케일/초) — 빠른 스윕 중엔 탭 아님
    z_weight: float = 0.0     # 거리 계산에 z(상대 깊이) 반영 비율. 0=2D만. 0.3~0.5 시도 가능
    rebound3: float = 0.25    # 3D(world landmark) 상대 해제: 눌림 후 엄지–버튼 3D 거리가 최저점에서 이만큼 늘면 뗀 것 (카메라 축 방향 들어올림)
    use_depth: bool = True    # 3D 들어올림 감지 사용 (False = 2D 만)
    sticky: float = 1.3       # 연타 대기 중인 버튼은 탭 반경을 이 배수로 넓혀 옆 버튼으로 새는 것을 막는다


class TapDetector:
    """손 하나의 엄지–버튼 접촉 상태머신. update()는 이번 프레임에 발생한 눌림 에지(버튼 ID 목록)를 돌려준다."""

    def __init__(self, params: TapParams):
        self.p = params
        self.reset()

    def reset(self) -> None:
        self.pressed: Optional[str] = None
        self.cand: Optional[str] = None
        self.cand_since = 0.0
        self.d_min = 0.0
        self.rel_zone: Optional[str] = None
        self.d_max = 0.0
        self.prev_thumb: Optional[np.ndarray] = None
        self.prev_t = 0.0
        self.speed = 0.0
        self.nearest: Optional[str] = None
        self.nearest_d = float("inf")
        self.dists: Dict[str, float] = {}
        self.d3: Dict[str, float] = {}
        self.d3_min = 0.0
        self.d3_max = 0.0
        self.last_release = ""       # 디버그: 마지막 해제 원인 ('2d' / '3d' / 'abs')

    def _dist(self, thumb: np.ndarray, z: Zone, scale: float) -> float:
        d = thumb - z.center
        dz = d[2] * self.p.z_weight
        return float(math.sqrt(d[0] * d[0] + d[1] * d[1] + dz * dz)) / scale

    def update(self, obs: HandObs, t: float, enabled: bool = True, sticky: Optional[str] = None) -> List[str]:
        """sticky: 이 손에서 연타 대기 중인 버튼(엔진 pending). 그 버튼은 반경을 넓혀 우선 후보로 삼는다."""
        p = self.p
        thumb = obs.thumb
        if self.prev_thumb is not None and t > self.prev_t:
            dt = (t - self.prev_t) / 1000.0
            self.speed = float(np.linalg.norm((thumb - self.prev_thumb)[:2])) / obs.scale / dt
        self.prev_thumb, self.prev_t = thumb.copy(), t

        self.dists = {z.button: self._dist(thumb, z, obs.scale) for z in obs.zones}
        k, dk = min(self.dists.items(), key=lambda kv: kv[1])
        if sticky in self.dists and self.dists[sticky] < p.press * p.sticky:
            k, dk = sticky, self.dists[sticky]          # 연타 대기 버튼 우선
        self.nearest, self.nearest_d = k, dk
        use3 = p.use_depth and obs.zones_w is not None and obs.thumb_w is not None
        if use3:
            self.d3 = {b: float(np.linalg.norm(obs.thumb_w - c)) / obs.scale_w for b, c in obs.zones_w.items()}
        else:
            self.d3 = {}
        taps: List[str] = []

        if not enabled:
            self.pressed = self.cand = None
            self.rel_zone = None
            return taps

        if self.pressed is not None:
            dp = self.dists.get(self.pressed, float("inf"))
            self.d_min = min(self.d_min, dp)
            d3p = self.d3.get(self.pressed)
            if d3p is not None:
                self.d3_min = min(self.d3_min, d3p)
            released = ""
            if dp > p.release:
                released = "abs"
            elif (dp - self.d_min) >= p.rebound:
                released = "2d"
            elif d3p is not None and (d3p - self.d3_min) >= p.rebound3:
                released = "3d"                             # 카메라 축 방향으로 들어올림 → 2D 로는 안 보이는 뗌
            if released:
                self.rel_zone, self.d_max = self.pressed, dp
                self.d3_max = d3p if d3p is not None else 0.0
                self.last_release = released
                self.pressed = None
                self.cand = None
            return taps

        # 떼어진 상태: 같은 버튼 재눌림에는 '내려오는' 움직임(2D 또는 3D)을 요구 — 손떨림으로 인한 연타 오인 배제
        if self.rel_zone is not None:
            dr = self.dists.get(self.rel_zone, float("inf"))
            self.d_max = max(self.d_max, dr)
            d3r = self.d3.get(self.rel_zone)
            if d3r is not None:
                self.d3_max = max(self.d3_max, d3r)
            if k != self.rel_zone and dk < p.press:
                self.rel_zone = None
        inside = dk < p.press and self.speed < p.max_speed
        if inside and self.rel_zone == k:
            descended_2d = dk <= self.d_max - 0.6 * p.rebound
            d3k = self.d3.get(k)
            descended_3d = d3k is not None and d3k <= self.d3_max - 0.6 * p.rebound3
            if not (descended_2d or descended_3d):
                inside = False
        if inside:
            if self.cand != k:
                self.cand, self.cand_since = k, t
            elif t - self.cand_since >= p.dwell_ms:
                taps.append(k)
                self.pressed, self.d_min = k, dk
                self.d3_min = self.d3.get(k, 0.0)
                self.cand = None
                self.rel_zone = None
        else:
            self.cand = None
        return taps


# ---------------------------------------------------------------------------
# 안내 모드(--target): 목표 문장 → 다음에 탭할 버튼
# ---------------------------------------------------------------------------
class TargetGuide:
    def __init__(self, target: str, tap_table: Dict[str, Dict[int, str]]):
        self.target = target
        self.tokens = decompose_text(target)
        self.token_to_btn: Dict[str, Tuple[str, int]] = {}
        for b, tt in tap_table.items():
            for n, tok in tt.items():
                self.token_to_btn.setdefault(tok, (b, n))

    def next_step(self, typed_text: str) -> Tuple[int, Optional[Tuple[str, str, int]], bool]:
        """(맞은 토큰 수, (토큰, 버튼, 탭수) or None=완료, 오타 여부)"""
        typed = decompose_text(typed_text)
        n = 0
        while n < len(typed) and n < len(self.tokens) and typed[n] == self.tokens[n]:
            n += 1
        wrong = n < len(typed)
        if wrong:
            return n, ("BACKSPACE", "L5", 1), True
        if n >= len(self.tokens):
            return n, None, False
        tok = self.tokens[n]
        b, taps = self.token_to_btn.get(tok, ("?", 1))
        return n, (tok, b, taps), False


# ---------------------------------------------------------------------------
# 렌더링 (cv2 도형 + PIL 한글 텍스트)
# ---------------------------------------------------------------------------
FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf", "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
    "/usr/share/fonts/truetype/nanum/NanumBarunGothic.ttf", "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc", "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc",
    "/System/Library/Fonts/AppleSDGothicNeo.ttc", "/System/Library/Fonts/Supplemental/AppleGothic.ttf",
    "/Library/Fonts/NanumGothic.ttf", "C:/Windows/Fonts/malgunbd.ttf", "C:/Windows/Fonts/malgun.ttf",
    "C:/Windows/Fonts/NanumGothic.ttf",
]


def find_korean_font(explicit: Optional[str] = None) -> Optional[str]:
    if explicit:
        return explicit if os.path.isfile(explicit) else None
    for c in FONT_CANDIDATES:
        if os.path.isfile(c):
            return c
    return None


class Renderer:
    COL_SKEL = (200, 200, 200)
    COL_L = (255, 170, 60)     # BGR — 왼손(자음) 주황
    COL_R = (80, 200, 255)     # 오른손(모음) 노랑-하늘
    COL_PRESS = (60, 220, 60)
    COL_PEND = (0, 165, 255)
    COL_NEAR = (0, 255, 255)
    COL_GUIDE = (255, 80, 255)
    COL_CAL = (255, 0, 200)

    def __init__(self, width: int, height: int, font_path: Optional[str], mirror: bool = True):
        import cv2
        from PIL import Image, ImageDraw, ImageFont
        self.cv2, self.Image, self.ImageDraw = cv2, Image, ImageDraw
        self.W, self.H = width, height
        self.mirror = mirror
        self.font_ok = font_path is not None
        base = max(12, int(width / 40))
        self.sizes = {"zone": base, "small": max(12, int(base * 0.85)), "text": int(base * 2.2),
                      "mid": int(base * 1.25)}
        self.fonts = {}
        for k, s in self.sizes.items():
            try:
                self.fonts[k] = ImageFont.truetype(font_path, s) if font_path else ImageFont.load_default()
            except Exception:
                self.fonts[k] = ImageFont.load_default()

    def tx(self, pt) -> Tuple[int, int]:
        x, y = float(pt[0]), float(pt[1])
        if self.mirror:
            x = self.W - 1 - x
        return int(round(x)), int(round(y))

    def draw(self, frame, hands: Dict[str, HandObs], detectors: Dict[str, "TapDetector"], engine: MultiTapEngine,
             text_line: str, t_ms: float, status: str, warnings: List[str], events: List[str],
             guide_text: str = "", guide_btn: Optional[str] = None, calib: Optional[dict] = None,
             debug: bool = False, show_panel: bool = True) -> np.ndarray:
        cv2 = self.cv2
        disp = cv2.flip(frame, 1) if self.mirror else frame.copy()
        texts = []  # (x, y, text, fontkey, rgb, anchor)
        pending = engine.pending()
        cal_btn = calib.get("button") if calib else None

        for side, obs in hands.items():
            col = self.COL_L if side == "L" else self.COL_R
            pts = [self.tx(p) for p in obs.P]
            for a, b in HAND_CONNECTIONS:
                cv2.line(disp, pts[a], pts[b], self.COL_SKEL, 1, cv2.LINE_AA)
            for pt in pts:
                cv2.circle(disp, pt, 2, self.COL_SKEL, -1, cv2.LINE_AA)
            det = detectors[side]
            r_zone = max(6, int(obs.scale * 0.13))
            for z in obs.zones:
                c = self.tx(z.center)
                base_tok = engine.table[z.button][1]
                label = TOKEN_SHORT.get(base_tok, base_tok)
                fill = None
                ring, thick = col, 1
                if det.pressed == z.button:
                    fill, ring, thick = self.COL_PRESS, self.COL_PRESS, 2
                elif z.button in pending:
                    ring, thick = self.COL_PEND, 2
                elif det.nearest == z.button and det.nearest_d < det.p.release:
                    ring, thick = self.COL_NEAR, 2
                if guide_btn == z.button:
                    cv2.circle(disp, c, r_zone + 6, self.COL_GUIDE, 2, cv2.LINE_AA)
                if cal_btn == z.button:
                    cv2.circle(disp, c, r_zone + 8, self.COL_CAL, 3, cv2.LINE_AA)
                    prog = float(calib.get("progress", 0.0))
                    if prog > 0:
                        cv2.ellipse(disp, c, (r_zone + 12, r_zone + 12), -90, 0, int(360 * prog), self.COL_CAL, 3,
                                    cv2.LINE_AA)
                if fill is not None:
                    overlay = disp.copy()
                    cv2.circle(overlay, c, r_zone, fill, -1, cv2.LINE_AA)
                    cv2.addWeighted(overlay, 0.45, disp, 0.55, 0, disp)
                cv2.circle(disp, c, r_zone, ring, thick, cv2.LINE_AA)
                if z.button in pending:
                    cnt, first = pending[z.button]
                    remain = max(0.0, 1.0 - (t_ms - first) / engine.window)
                    cv2.ellipse(disp, c, (r_zone + 3, r_zone + 3), -90, 0, int(360 * remain), self.COL_PEND, 2,
                                cv2.LINE_AA)
                    cur = engine.table[z.button].get(cnt, base_tok)
                    nxt = engine.table[z.button].get(cnt + 1)
                    tag = f"{TOKEN_SHORT.get(cur, cur)}" + (f"→{TOKEN_SHORT.get(nxt, nxt)}" if nxt else "")
                    texts.append((c[0], c[1] - r_zone - 6, tag, "mid", (255, 200, 80), "mb"))
                texts.append((c[0], c[1], label, "zone", (255, 255, 255), "mm"))
            tp = self.tx(obs.thumb)
            cv2.circle(disp, tp, 5, (0, 0, 255), -1, cv2.LINE_AA)
            wp = self.tx(obs.P[WRIST])
            tag = ("왼손·자음" if side == "L" else "오른손·모음")
            if not obs.palm_ok:
                tag += " ✗손바닥"
            texts.append((wp[0], wp[1] + 12, tag, "small", (255, 255, 255), "mt"))
            if debug:
                d3s = f" d3={det.d3[det.nearest]:.2f}" if det.nearest in det.d3 else ""
                dbg = (f"{side} model={obs.model_label}:{obs.model_score:.2f} geom={obs.geom_label} "
                       f"near={det.nearest} d={det.nearest_d:.2f}{d3s} v={det.speed:.1f} "
                       f"press={det.pressed} cand={det.cand} rel={det.last_release}")
                texts.append((8, self.H - int(self.sizes["small"] * 2.6) - 8 - int(self.sizes["small"] * 1.3) * (2 if side == "R" else 1),
                              dbg, "small", (200, 255, 200), "la"))

        panel_h = 0
        if show_panel:
            panel_h = int(self.sizes["text"] * 2.4)
            ov = disp.copy()
            cv2.rectangle(ov, (0, 0), (self.W, panel_h), (20, 20, 20), -1)
            cv2.addWeighted(ov, 0.65, disp, 0.35, 0, disp)
            caret = "|" if int(t_ms / 500) % 2 == 0 else " "
            texts.append((12, 8, text_line + caret, "text", (255, 255, 255), "la"))
            texts.append((12, panel_h - self.sizes["small"] - 6, "  ".join(events[-10:]), "small", (180, 220, 255), "la"))
        if guide_text and not (calib and calib.get("active")):   # 캘리브레이션 상자와 겹치지 않게
            texts.append((self.W - 12, 8, guide_text, "mid", (255, 150, 255), "ra"))
        if calib and calib.get("active"):
            box_top = panel_h + 8
            ov = disp.copy()
            cv2.rectangle(ov, (0, box_top), (self.W, box_top + int(self.sizes["mid"] * 3.4)), (40, 0, 40), -1)
            cv2.addWeighted(ov, 0.6, disp, 0.4, 0, disp)
            texts.append((12, box_top + 4, f"캘리브레이션 {calib.get('step_idx', 0) + 1}/{calib.get('n_steps', 0)} · {calib.get('title', '')}",
                          "mid", (255, 180, 255), "la"))
            texts.append((12, box_top + 6 + int(self.sizes["mid"] * 1.3), calib.get("instruction", ""), "small",
                          (255, 255, 255), "la"))
            texts.append((12, box_top + 8 + int(self.sizes["mid"] * 2.3), calib.get("feedback", ""), "small",
                          (200, 255, 200), "la"))
            prog = float(calib.get("progress", 0.0))
            if prog > 0:
                cv2.rectangle(disp, (12, box_top + int(self.sizes["mid"] * 3.2)), (12 + int((self.W - 24) * prog),
                              box_top + int(self.sizes["mid"] * 3.35)), self.COL_CAL, -1)
        if show_panel:
            bar_h = int(self.sizes["small"] * 2.6)
            ov = disp.copy()
            cv2.rectangle(ov, (0, self.H - bar_h), (self.W, self.H), (20, 20, 20), -1)
            cv2.addWeighted(ov, 0.6, disp, 0.4, 0, disp)
            texts.append((8, self.H - bar_h + 4, "q 종료 · c 지우기 · [ ] 연타 윈도우 · - = 탭 반경 · h 좌우 라벨 · d 디버그 · s 스크린샷",
                          "small", (160, 160, 160), "la"))
            texts.append((8, self.H - self.sizes["small"] - 6, status, "small", (220, 220, 220), "la"))
        for i, wtxt in enumerate(warnings):
            texts.append((self.W // 2, self.H // 2 + 28 * i, wtxt, "mid", (80, 200, 255), "mm"))
        return self._draw_texts(disp, texts)

    def _draw_texts(self, disp, texts):
        cv2 = self.cv2
        img = self.Image.fromarray(cv2.cvtColor(disp, cv2.COLOR_BGR2RGB))
        d = self.ImageDraw.Draw(img)
        for x, y, s, fk, rgb, anchor in texts:
            if not s:
                continue
            font = self.fonts[fk]
            try:
                d.text((x, y), s, font=font, fill=rgb, anchor=anchor,
                       stroke_width=2 if fk in ("text", "mid", "zone") else 0, stroke_fill=(0, 0, 0))
            except (ValueError, TypeError):  # anchor 미지원 폰트(기본 비트맵) 폴백
                d.text((x, y), s, font=font, fill=rgb)
        return cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)


# ---------------------------------------------------------------------------
# 손 추적 소스 (MediaPipe Hand Landmarker, Tasks API)
# ---------------------------------------------------------------------------
def ensure_model(path: Optional[str]) -> str:
    p = Path(path) if path else HERE / "models" / "hand_landmarker.task"
    if p.is_file():
        return str(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    print(f"[info] hand_landmarker.task 다운로드 → {p}")
    urllib.request.urlretrieve(MODEL_URL, str(p))
    return str(p)


class HandTracker:
    def __init__(self, model_path: str, num_hands: int = 2, det_conf: float = 0.5, track_conf: float = 0.5):
        import mediapipe as mp
        from mediapipe.tasks.python import vision
        from mediapipe.tasks.python.core.base_options import BaseOptions
        self.mp, self.vision = mp, vision
        opts = vision.HandLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=model_path), running_mode=vision.RunningMode.VIDEO,
            num_hands=num_hands, min_hand_detection_confidence=det_conf, min_hand_presence_confidence=det_conf,
            min_tracking_confidence=track_conf)
        self.lm = vision.HandLandmarker.create_from_options(opts)
        self.last_ts = -1

    def detect(self, rgb: np.ndarray, ts_ms: int) -> List[Tuple[np.ndarray, str, float]]:
        ts_ms = max(int(ts_ms), self.last_ts + 1)   # VIDEO 모드는 단조 증가 타임스탬프 필수
        self.last_ts = ts_ms
        h, w = rgb.shape[:2]
        img = self.mp.Image(image_format=self.mp.ImageFormat.SRGB, data=np.ascontiguousarray(rgb))
        res = self.lm.detect_for_video(img, ts_ms)
        out = []
        world = list(getattr(res, "hand_world_landmarks", None) or [])
        for i, (lms, hd) in enumerate(zip(res.hand_landmarks, res.handedness)):
            lab, sc = (hd[0].category_name, float(hd[0].score)) if hd else ("?", 0.0)
            Pw = world_landmarks_to_np(world[i]) if i < len(world) and world[i] else None
            out.append((landmarks_to_np(lms, w, h), lab, sc, Pw))
        return out

    def close(self) -> None:
        self.lm.close()


# ---------------------------------------------------------------------------
# 프로필 (캘리브레이션 결과 JSON)
# ---------------------------------------------------------------------------
def profile_path(name: str) -> Path:
    safe = "".join(ch for ch in name.strip() if ch.isalnum() or ch in "-_가-힣") or "default"
    return PROFILE_DIR / f"{safe}.json"


def list_profiles() -> List[str]:
    return sorted(Path(p).stem for p in glob.glob(str(PROFILE_DIR / "*.json")))


def save_profile(name: str, data: dict) -> Path:
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    p = profile_path(name)
    data = dict(data)
    data["saved_at"] = datetime.now().isoformat(timespec="seconds")
    data["version"] = __version__
    with open(p, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    return p


def load_profile(name: str) -> Optional[dict]:
    p = profile_path(name)
    if not p.is_file():
        return None
    with open(p, encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# 캘리브레이션 — 임계값 결정 함수와 마법사 상태머신
# ---------------------------------------------------------------------------
def _pct(vals: List[float], q: float) -> float:
    return float(np.percentile(np.asarray(vals, dtype=np.float64), q))


def decide_threshold(touch: List[float], hover: List[float], lo: float = 0.15, hi: float = 0.50) -> Tuple[float, float]:
    """접촉 잔차(작음)와 비접촉 거리(큼) 분포 사이에서 press/release 결정. → (press, release)"""
    if not touch and not hover:
        return TapParams.press, TapParams.release
    t90 = _pct(touch, 90) if touch else 0.12
    h10 = _pct(hover, 10) if hover else 0.9
    press = 0.5 * (t90 + h10)
    press = max(press, t90 + 0.06)
    press = min(max(press, lo), hi)
    release = min(press + 0.15, max(press + 0.08, h10 - 0.03))
    return round(press, 3), round(release, 3)


def decide_window(multitap: List[float], separate: List[float], current: float,
                  lo: float = 200.0, hi: float = 900.0) -> Tuple[float, dict]:
    """연타 간격(짧음)과 별개 입력 간격(긺) 분포의 오분류 최소 임계값. tap_calibration.py 와 같은 원리.
    → (window_ms, 진단 dict)"""
    mt = sorted(multitap)
    sp = sorted(separate)
    info = {"n_multitap": len(mt), "n_separate": len(sp)}
    if mt:
        info["multitap"] = {"median": round(float(np.median(mt)), 1), "p90": round(_pct(mt, 90), 1), "max": round(max(mt), 1)}
    if sp:
        info["separate"] = {"median": round(float(np.median(sp)), 1), "p10": round(_pct(sp, 10), 1), "min": round(min(sp), 1)}
    if not mt and not sp:
        return current, info
    if mt and not sp:
        w = _pct(mt, 90) * 1.3 + 60
    elif sp and not mt:
        w = min(current, _pct(sp, 10) - 60)
    else:
        cands = sorted(set(mt + sp))
        best = None
        for i in range(len(cands) + 1):
            thr = (cands[i - 1] + cands[i]) / 2 if 0 < i < len(cands) else (cands[0] - 1 if i == 0 else cands[-1] + 1)
            err = sum(1 for g in mt if g > thr) + sum(1 for g in sp if g <= thr)
            if best is None or err < best[0]:
                best = (err, thr)
        err, thr = best
        info["errors"] = err
        # 오분류 0이면 두 분포 사이 빈 구간의 가운데로(여유 최대)
        if err == 0 and mt and sp:
            thr = 0.5 * (max(mt) + min(sp))
        w = thr
    w = float(min(max(w, lo), hi))
    info["window"] = round(w, 1)
    return round(w, 1), info


@dataclass
class CalStep:
    kind: str                 # 'hands' | 'zone' | 'hover' | 'multitap' | 'separate'
    title: str
    instruction: str
    button: str = ""
    duration_ms: float = 1000.0
    pairs_needed: int = 5


class CalibrationSession:
    """마법사 상태머신. Pipeline이 매 프레임 on_frame()을 부르고, UI는 view()로 상태를 읽고 next/skip/cancel을 호출한다.
    결과는 단계가 끝날 때마다 즉시 pipeline 에 적용된다(오프셋 → 임계 → 윈도우 순서라 뒤 단계가 앞 결과를 쓴다)."""

    PAIR_GAP_MAX = 1200.0   # ms — 이보다 긴 간격은 쌍 구분(쉼)으로 본다
    SETTLE_MS = 500.0       # 단계 시작 직후 이 시간은 표본을 받지 않는다 (엄지를 옮길 여유; 직전 위치 오염 방지)

    def __init__(self, pipeline: "Pipeline", which: str = "all"):
        self.pl = pipeline
        self.steps: List[CalStep] = []
        buttons = [b for b in pipeline.table if b[0] == "L"] + [b for b in pipeline.table if b[0] == "R"]
        if which in ("all", "hands"):
            self.steps.append(CalStep("hands", "손 확인", "두 손바닥을 카메라 쪽으로 펴고 2초간 유지하세요. 좌우 라벨을 자동 검증합니다.",
                                      duration_ms=2000))
        if which in ("all", "zones"):
            for b in buttons:
                tok = TOKEN_SHORT.get(pipeline.table[b][1], pipeline.table[b][1])
                self.steps.append(CalStep("zone", f"스윗스팟 {b} ({tok})",
                                          f"{button_location_ko(b)}를 엄지로 누른 채 가만히 1초 유지하세요.", button=b,
                                          duration_ms=1000))
        if which in ("all", "zones", "threshold"):
            self.steps.append(CalStep("hover", "탭 반경 — 비접촉 자세",
                                      "양손을 펴고 엄지를 뗀 '편안한 대기 자세'로 2초 유지하세요 (엄지가 마디에 닿지 않게).",
                                      duration_ms=2000))
        if which in ("all", "window"):
            self.steps.append(CalStep("multitap", "연타 윈도우 — 빠른 2연타",
                                      "왼손 검지 첫째 마디(ㄱ)를 '빠르게 두 번' 두드리세요 ×5회. 쌍 사이에는 1.5초 이상 쉬세요.",
                                      button="L1a", pairs_needed=5))
            self.steps.append(CalStep("separate", "연타 윈도우 — 따로 두 번",
                                      "같은 버튼(ㄱ)을 평소 타자 속도로 '따로 두 번'(국가의 ㄱ…ㄱ처럼) 두드리세요 ×5회. 쌍 사이 1.5초 이상.",
                                      button="L1a", pairs_needed=5))
        self.idx = 0
        self.active = bool(self.steps)
        self.finished = False
        self.summary: List[str] = []
        self.feedback = ""
        self.progress = 0.0
        self._reset_step_state()
        # 누적 결과
        self.offsets: ZoneOffsets = dict(pipeline.zone_offsets)
        self.touch_resid: List[float] = []
        self.hover_d: List[float] = []
        self.multitap_gaps: List[float] = []
        self.separate_gaps: List[float] = []
        self.hand_mismatch = {"L": 0, "R": 0}
        self.hand_seen = {"L": 0, "R": 0}
        self.result: dict = {}

    # -- 상태 ---------------------------------------------------------------
    def _reset_step_state(self) -> None:
        self.samples: List[Tuple[float, float]] = []
        self.sample_pts: List[np.ndarray] = []
        self.sample_scales: List[float] = []
        self.valid_ms = 0.0
        self.last_t: Optional[float] = None
        self.step_started: Optional[float] = None
        self.tap_times: List[float] = []
        self.gaps: List[float] = []
        self.progress = 0.0
        self.feedback = ""

    @property
    def step(self) -> Optional[CalStep]:
        return self.steps[self.idx] if self.active and self.idx < len(self.steps) else None

    def view(self) -> dict:
        st = self.step
        return {"active": self.active, "finished": self.finished, "step_idx": self.idx, "n_steps": len(self.steps),
                "kind": st.kind if st else "", "title": st.title if st else "", "instruction": st.instruction if st else "",
                "button": st.button if st else "", "feedback": self.feedback, "progress": round(self.progress, 3),
                "summary": self.summary, "result": self.result}

    # -- 제어 ---------------------------------------------------------------
    def next(self) -> None:
        if self.active:
            self._finish_step(skipped=False)

    def skip(self) -> None:
        if self.active:
            self._finish_step(skipped=True)

    def cancel(self) -> None:
        self.active = False
        self.finished = False
        self.summary.append("취소됨 (이미 적용된 단계는 유지)")

    def _advance(self) -> None:
        self.idx += 1
        self._reset_step_state()
        if self.idx >= len(self.steps):
            self.active = False
            self.finished = True
            self.result = {"zone_offsets": self.offsets, "press": self.pl.params.press, "release": self.pl.params.release,
                           "window": self.pl.engine.window, "hand_mode": self.pl.hand_mode,
                           "n_touch": len(self.touch_resid), "n_hover": len(self.hover_d),
                           "n_multitap": len(self.multitap_gaps), "n_separate": len(self.separate_gaps)}
            self.summary.append("완료 — 설정 탭에서 프로필을 저장하세요 (자동 저장됨: 현재 프로필)")
            self.pl.on_calibration_finished()

    # -- 프레임 처리 ----------------------------------------------------------
    def on_frame(self, hands: Dict[str, HandObs], taps: Dict[str, List[str]], t_ms: float,
                 detectors: Dict[str, "TapDetector"]) -> None:
        st = self.step
        if st is None:
            return
        if self.step_started is None:
            self.step_started = t_ms
        dt = 0.0 if self.last_t is None else max(0.0, min(200.0, t_ms - self.last_t))
        self.last_t = t_ms
        if st.kind == "hands":
            for side in ("L", "R"):
                if side in hands:
                    self.hand_seen[side] += 1
                    if hands[side].model_label != "?" and hands[side].geom_label != hands[side].side:
                        self.hand_mismatch[side] += 1
            self.valid_ms += dt if hands else 0.0
            self.progress = min(1.0, self.valid_ms / st.duration_ms)
            seen = "·".join(f"{s}:{'보임' if s in hands else '없음'}" for s in ("L", "R"))
            self.feedback = f"{seen} · 불일치 L {self.hand_mismatch['L']}/{self.hand_seen['L']} R {self.hand_mismatch['R']}/{self.hand_seen['R']}"
            if self.progress >= 1.0:
                self._finish_step(False)
        elif st.kind == "zone":
            side = st.button[0]
            obs = hands.get(side)
            if obs is None:
                self.feedback = f"{'왼손' if side == 'L' else '오른손'}이 보이지 않습니다"
                return
            finger, row = button_finger_row(st.button)
            A, B = segment_points(obs.P, finger, row)
            mid = 0.5 * (A + B)
            d = float(np.linalg.norm((obs.thumb - mid)[:2])) / obs.scale
            speed = detectors[side].speed
            near = detectors[side].nearest
            same_finger = near is not None and button_finger_row(near)[0] == finger
            settling = (t_ms - self.step_started) < self.SETTLE_MS
            ok = obs.palm_ok and (d < 0.35 or (d < 0.7 and same_finger)) and speed < 3.0 and not settling
            if ok:
                self.samples.append(local_coords(A, B, obs.thumb))
                self.sample_pts.append(obs.thumb[:2].copy())
                self.sample_scales.append(obs.scale)
                self.valid_ms += dt
            self.progress = min(1.0, self.valid_ms / st.duration_ms)
            why = ("" if ok else (" · 준비…" if settling else (" · 손바닥?" if not obs.palm_ok else
                   (" · 엄지를 버튼에" if not (d < 0.35 or (d < 0.7 and same_finger)) else " · 가만히"))))
            self.feedback = f"샘플 {len(self.samples)} · 거리 {d:.2f} · 속도 {speed:.1f}{why}"
            if self.progress >= 1.0 and len(self.samples) >= 8:
                self._finish_step(False)
        elif st.kind == "hover":
            n_ok = 0
            if (t_ms - self.step_started) < self.SETTLE_MS:
                self.feedback = "준비… 엄지를 떼세요"
                return
            for side, obs in hands.items():
                if obs.palm_ok:
                    det = detectors[side]
                    if det.nearest_d < float("inf"):
                        self.hover_d.append(det.nearest_d)
                        n_ok += 1
            if n_ok:
                self.valid_ms += dt
            self.progress = min(1.0, self.valid_ms / st.duration_ms)
            self.feedback = f"샘플 {len(self.hover_d)} · 현재 최근접 거리 " + " ".join(
                f"{s}:{detectors[s].nearest_d:.2f}" for s in hands)
            if self.progress >= 1.0:
                self._finish_step(False)
        elif st.kind in ("multitap", "separate"):
            side = st.button[0]
            for b in taps.get(side, []):
                if b == st.button:
                    if self.tap_times and (t_ms - self.tap_times[-1]) < self.PAIR_GAP_MAX:
                        gap = t_ms - self.tap_times[-1]
                        # 쌍 = 직전 탭이 '쌍의 첫 탭'일 때만 (탭 수 홀수 → 첫 탭)
                        if len(self.tap_times) % 2 == 1:
                            self.gaps.append(gap)
                    self.tap_times.append(t_ms)
            done = len(self.gaps)
            self.progress = min(1.0, done / st.pairs_needed)
            last = f" · 마지막 {self.gaps[-1]:.0f}ms" if self.gaps else ""
            self.feedback = f"쌍 {done}/{st.pairs_needed}{last} · 탭 {len(self.tap_times)}"
            if done >= st.pairs_needed:
                self._finish_step(False)

    def _finish_step(self, skipped: bool) -> None:
        st = self.step
        if st is None:
            return
        if st.kind == "hands" and not skipped:
            tot_seen = sum(self.hand_seen.values())
            tot_mis = sum(self.hand_mismatch.values())
            if tot_seen >= 10 and tot_mis > 0.6 * tot_seen and self.pl.hand_mode != "geom":
                self.pl.hand_mode = "model-swap" if self.pl.hand_mode == "model" else "model"
                self.summary.append(f"좌우 라벨 불일치 {tot_mis}/{tot_seen} → hand_mode={self.pl.hand_mode} 로 반전")
            else:
                self.summary.append(f"좌우 라벨 확인 (불일치 {tot_mis}/{tot_seen})")
        elif st.kind == "zone" and not skipped and len(self.samples) >= 3:
            ts = np.array(self.samples)
            t_med, s_med = float(np.median(ts[:, 0])), float(np.median(ts[:, 1]))
            t_med = min(max(t_med, -0.3), 1.3)
            s_med = min(max(s_med, -1.0), 1.0)
            self.offsets[st.button] = (round(t_med, 3), round(s_med, 3))
            pts = np.array(self.sample_pts)
            med_pt = np.median(pts, axis=0)
            resid = np.linalg.norm(pts - med_pt, axis=1) / np.array(self.sample_scales)
            self.touch_resid.extend(float(r) for r in resid)
            self.pl.set_zone_offsets(self.offsets)
            self.summary.append(f"{st.button}: t={t_med:.2f} s={s_med:+.2f} (n={len(self.samples)})")
        elif st.kind == "hover" and not skipped:
            press, release = decide_threshold(self.touch_resid, self.hover_d)
            self.pl.set_threshold(press, release)
            info = (f"접촉 잔차 p90={_pct(self.touch_resid, 90):.2f} " if self.touch_resid else "접촉 잔차 없음 ") + \
                   (f"비접촉 p10={_pct(self.hover_d, 10):.2f}" if self.hover_d else "비접촉 없음")
            self.summary.append(f"탭 반경 press={press:.2f} release={release:.2f} ({info})")
        elif st.kind == "multitap" and not skipped:
            self.multitap_gaps = list(self.gaps)
            self.summary.append(f"연타 간격 n={len(self.gaps)} " + (f"중앙값 {np.median(self.gaps):.0f}ms" if self.gaps else ""))
        elif st.kind == "separate" and not skipped:
            self.separate_gaps = list(self.gaps)
            w, info = decide_window(self.multitap_gaps, self.separate_gaps, self.pl.engine.window)
            self.pl.set_window(w)
            self.summary.append(f"연타 윈도우 {w:.0f}ms (별개 입력 간격 n={len(self.gaps)}, 오분류 {info.get('errors', '-')})")
        elif skipped:
            self.summary.append(f"{st.title}: 건너뜀")
        self._advance()


# ---------------------------------------------------------------------------
# 파이프라인 — 프레임 → 손 → 탭 → 연타 엔진 → 조합 (GUI/CLI 공용, 워커 스레드에서 실행)
# ---------------------------------------------------------------------------
class FrameBus:
    """워커가 만든 최신 JPEG + 스냅샷을 스트림/상태 핸들러에 전달 (최신 1장만 유지)."""

    def __init__(self):
        self.cond = threading.Condition()
        self.seq = 0
        self.jpeg: bytes = b""
        self.snapshot: dict = {}

    def publish(self, jpeg: bytes, snapshot: dict) -> None:
        with self.cond:
            self.seq += 1
            self.jpeg, self.snapshot = jpeg, snapshot
            self.cond.notify_all()

    def wait(self, last_seq: int, timeout: float = 1.0) -> Tuple[int, bytes]:
        with self.cond:
            if self.seq == last_seq:
                self.cond.wait(timeout)
            return self.seq, self.jpeg

    def latest(self) -> Tuple[int, bytes, dict]:
        with self.cond:
            return self.seq, self.jpeg, self.snapshot


class Pipeline:
    PARAM_KEYS = ("press", "release", "rebound", "dwell_ms", "max_speed", "z_weight", "rebound3", "sticky")

    def __init__(self, table: Dict[str, Dict[int, str]], mapping_src: str, params: TapParams, window: float = 450.0,
                 early_commit: bool = True, debounce: float = 30.0, hand_mode: str = "model", palm_gate: bool = True,
                 mirror: bool = True, debug: bool = False, font_path: Optional[str] = None, tracker=None,
                 display_width: int = 960, log_path: Optional[str] = None, profile_name: str = "default",
                 autosave: bool = True, verbose: bool = False, window_mode: str = "last"):
        self.table, self.mapping_src = table, mapping_src
        self.params = params
        self.engine = MultiTapEngine(table, tap_window_ms=window, early_commit=early_commit, debounce_ms=debounce,
                                     window_mode=window_mode)
        self.composer = HangulComposer()
        self.detectors = {"L": TapDetector(params), "R": TapDetector(params)}
        self.hand_mode, self.palm_gate, self.mirror, self.debug = hand_mode, palm_gate, mirror, debug
        self.font_path, self.tracker, self.display_width = font_path, tracker, display_width
        self.zone_offsets: ZoneOffsets = {}
        self.guide: Optional[TargetGuide] = None
        self.calib: Optional[CalibrationSession] = None
        self.last_calib_view: dict = {"active": False, "finished": False, "summary": []}
        self.events: deque = deque(maxlen=40)
        self.event_objs: deque = deque(maxlen=40)
        self.n_events = 0
        self.renderer: Optional[Renderer] = None
        self.recorder = None
        self.record_path = ""
        self.hid_out = None
        self.hid_error = ""
        self.profile_name, self.autosave, self.verbose = profile_name, autosave, verbose
        self.log_f = open(log_path, "a", encoding="utf-8") if log_path else None
        self.cmds: "queue.Queue[dict]" = queue.Queue()
        self.lock = threading.RLock()
        self._snap: dict = {}
        self._fps_hist: deque = deque(maxlen=30)
        self.hands: Dict[str, HandObs] = {}
        self.warnings: List[str] = []
        self.screenshot_req = False
        self.last_screenshot = ""
        self.camera_index: Optional[int] = None      # 현재 카메라 번호 (프로필에 저장 → 다음 실행 때 인수 없이도 같은 카메라)
        self.camera_request: Optional[int] = None    # UI 에서 요청한 전환 (캡처 루프가 처리)
        self.probe_request = False
        self.cameras: List[dict] = []                # 마지막 탐색 결과 [{index, ok, w, h, name}]
        self.camera_error = ""
        self.remember_camera = False
        self.show_panel = True   # cv2 창 모드용 프레임 내 텍스트 패널·키 도움말 (웹 앱에서는 끔)

    # -- 설정 변경 (캘리브레이션·UI 명령에서 호출; 워커 스레드) ---------------------
    def set_zone_offsets(self, offsets: ZoneOffsets) -> None:
        with self.lock:
            self.zone_offsets = {k: (float(v[0]), float(v[1])) for k, v in offsets.items()}

    def set_threshold(self, press: float, release: float) -> None:
        with self.lock:
            self.params.press = float(press)
            self.params.release = float(max(release, press + 0.05))

    def set_window(self, w: float) -> None:
        with self.lock:
            self.engine.window = float(min(max(w, 100.0), 900.0))

    def set_param(self, name: str, value: float) -> None:
        with self.lock:
            v = float(value)
            if name == "window":
                self.set_window(v)
            elif name == "release_margin":
                self.params.release = self.params.press + max(0.03, v)
            elif name == "press":
                margin = self.params.release - self.params.press
                self.params.press = min(max(v, 0.05), 0.8)
                self.params.release = self.params.press + max(0.03, margin)
            elif name in self.PARAM_KEYS:
                setattr(self.params, name, v)

    def export_profile(self) -> dict:
        with self.lock:
            return {"zone_offsets": {k: [v[0], v[1]] for k, v in self.zone_offsets.items()},
                    "params": {k: getattr(self.params, k) for k in self.PARAM_KEYS},
                    "window": self.engine.window, "hand_mode": self.hand_mode, "palm_gate": self.palm_gate,
                    "mirror": self.mirror, "mapping_src": self.mapping_src,
                    "use_depth": self.params.use_depth, "window_mode": self.engine.window_mode,
                    "camera": self.camera_index}

    def apply_profile(self, data: dict) -> None:
        with self.lock:
            zo = data.get("zone_offsets") or {}
            self.zone_offsets = {k: (float(v[0]), float(v[1])) for k, v in zo.items() if k in self.table}
            for k, v in (data.get("params") or {}).items():
                if k in self.PARAM_KEYS:
                    setattr(self.params, k, float(v))
            if "window" in data:
                self.engine.window = float(data["window"])
            if data.get("hand_mode") in ("model", "model-swap", "geom"):
                self.hand_mode = data["hand_mode"]
            if "palm_gate" in data:
                self.palm_gate = bool(data["palm_gate"])
            if "mirror" in data:
                self.mirror = bool(data["mirror"])
                if self.renderer:
                    self.renderer.mirror = self.mirror
            if "use_depth" in data:
                self.params.use_depth = bool(data["use_depth"])
            if data.get("window_mode") in ("first", "last"):
                self.engine.window_mode = data["window_mode"]
            if isinstance(data.get("camera"), int):
                self.camera_index = data["camera"]

    def on_calibration_finished(self) -> None:
        if self.autosave and self.profile_name:
            try:
                p = save_profile(self.profile_name, self.export_profile())
                self.events.append(f"[프로필 저장 {p.name}]")
            except OSError as e:
                self.events.append(f"[프로필 저장 실패 {e}]")

    def set_hid(self, on: bool) -> None:
        if on and self.hid_out is None:
            try:
                self.hid_out = HidOutput()
                self.hid_error = ""
            except Exception as e:  # noqa: BLE001
                self.hid_out, self.hid_error = None, f"pynput 사용 불가: {e}"
        elif not on:
            self.hid_out = None

    # -- 명령 큐 (UI/서버 스레드 → 워커) ------------------------------------------
    def post(self, cmd: dict) -> None:
        self.cmds.put(cmd)

    def _handle_cmds(self, t_ms: float) -> None:
        while True:
            try:
                c = self.cmds.get_nowait()
            except queue.Empty:
                return
            k = c.get("cmd")
            try:
                if k == "clear":
                    self.composer.clear()
                    self.events.clear()
                elif k == "backspace":
                    self.composer.backspace()
                elif k == "enter":
                    self.composer.input_enter()
                elif k == "space":
                    self.composer.input_space()
                elif k == "set_params":
                    for name, v in (c.get("params") or {}).items():
                        self.set_param(name, v)
                elif k == "set_hand_mode":
                    if c.get("mode") in ("model", "model-swap", "geom"):
                        self.hand_mode = c["mode"]
                elif k == "set_option":
                    name, v = c.get("name"), bool(c.get("value"))
                    if name == "palm_gate":
                        self.palm_gate = v
                    elif name == "mirror":
                        self.mirror = v
                        if self.renderer:
                            self.renderer.mirror = v
                    elif name == "debug":
                        self.debug = v
                    elif name == "hid":
                        self.set_hid(v)
                    elif name == "early_commit":
                        self.engine.early_commit = v
                    elif name == "use_depth":
                        self.params.use_depth = v
                    elif name == "rolling_window":
                        self.engine.window_mode = "last" if v else "first"
                elif k == "set_guide":
                    tgt = (c.get("target") or "").strip()
                    self.guide = TargetGuide(tgt, self.table) if tgt else None
                elif k == "calib_start":
                    self.engine.flush_all(t_ms)
                    self.calib = CalibrationSession(self, c.get("which", "all"))
                elif k == "calib_next" and self.calib:
                    self.calib.next()
                elif k == "calib_skip" and self.calib:
                    self.calib.skip()
                elif k == "calib_cancel" and self.calib:
                    self.calib.cancel()
                elif k == "profile_load":
                    data = load_profile(c.get("name") or self.profile_name)
                    if data:
                        self.apply_profile(data)
                        self.profile_name = c.get("name") or self.profile_name
                        self.events.append(f"[프로필 로드 {self.profile_name}]")
                    else:
                        self.events.append("[프로필 없음]")
                elif k == "profile_save":
                    self.profile_name = c.get("name") or self.profile_name
                    p = save_profile(self.profile_name, self.export_profile())
                    self.events.append(f"[프로필 저장 {p.name}]")
                elif k == "profile_reset":
                    self.zone_offsets = {}
                    self.params.press, self.params.release = TapParams.press, TapParams.release
                    self.params.rebound, self.params.dwell_ms = TapParams.rebound, TapParams.dwell_ms
                    self.params.max_speed, self.params.z_weight = TapParams.max_speed, TapParams.z_weight
                    self.params.rebound3, self.params.sticky, self.params.use_depth = TapParams.rebound3, TapParams.sticky, TapParams.use_depth
                    self.engine.window = 450.0
                    self.events.append("[기본값 복원]")
                elif k == "record_start":
                    self.record_path = c.get("path") or str(HERE / f"record_{datetime.now():%Y%m%d_%H%M%S}.mp4")
                    self.recorder = "pending"
                elif k == "record_stop":
                    if self.recorder not in (None, "pending"):
                        self.recorder.release()
                    self.recorder, self.record_path = None, ""
                elif k == "screenshot":
                    self.screenshot_req = True
                elif k == "set_camera":
                    self.camera_request = int(c.get("index", 0))
                elif k == "probe_cameras":
                    self.probe_request = True
            except Exception as e:  # noqa: BLE001 — 명령 하나가 루프를 죽이지 않게
                self.events.append(f"[명령 오류 {k}: {e}]")

    # -- 핵심 로직 (트래커 없이도 호출 가능 → 셀프테스트) ------------------------------
    def update(self, hands: Dict[str, HandObs], t_ms: float) -> Dict[str, List[str]]:
        taps: Dict[str, List[str]] = {}
        warnings: List[str] = []
        if not hands:
            warnings.append("손이 보이지 않습니다 — 두 손바닥을 카메라 쪽으로")
        for side in ("L", "R"):
            det = self.detectors[side]
            obs = hands.get(side)
            if obs is None:
                det.reset()
                continue
            enabled = obs.palm_ok or not self.palm_gate
            if not obs.palm_ok:
                warnings.append(f"{'왼손' if side == 'L' else '오른손'} 손바닥을 카메라 쪽으로 (라벨이 틀리면 좌우 반전)")
            sticky = next((b for b in self.engine.pending() if b[0] == side), None)
            taps[side] = det.update(obs, t_ms, enabled=enabled, sticky=sticky)
        if self.calib is not None and self.calib.active:
            self.calib.on_frame(hands, taps, t_ms, self.detectors)
        else:
            for side, lst in taps.items():
                for b in lst:
                    self.engine.press(b, t_ms)
        engine_events = []
        self.engine.tick(t_ms)
        for ev in self.engine.drain():
            self.composer.feed(ev.token)
            engine_events.append(ev)
            self.n_events += 1
            self.event_objs.append(ev)
            self.events.append(TOKEN_SHORT.get(ev.token, ev.token) + (f"×{ev.taps}" if ev.taps > 1 else ""))
            if self.hid_out:
                try:
                    self.hid_out.send(ev.token)
                except Exception as e:  # noqa: BLE001
                    self.hid_error = f"HID 전송 실패: {e}"
            if self.log_f:
                self.log_f.write(json.dumps({"t_ms": round(ev.t_ms, 1), "button": ev.button, "taps": ev.taps,
                                             "token": ev.token, "text": self.composer.text()}, ensure_ascii=False) + "\n")
            if self.verbose:
                print(f"{ev.t_ms:8.0f}ms {ev.button:>4}×{ev.taps} → {ev.token:<9} | {self.composer.text()}")
        if self.calib is not None:
            self.last_calib_view = self.calib.view()
        self.hands, self.warnings = hands, warnings
        return taps

    def guide_step(self):
        return self.guide.next_step(self.composer.text()) if self.guide else None

    @staticmethod
    def guide_text(step) -> str:
        if step is None:
            return ""
        n, st, wrong = step
        if st is None:
            return "✓ 완료"
        tok, b, taps = st
        tok_disp = {"SPACE": "띄어쓰기", "BACKSPACE": "지우기", "ENTER": "엔터"}.get(tok, tok)
        if wrong:
            return "오타 → 지우기(왼손 소지 둘째 마디)"
        return f"다음: {tok_disp} = {button_location_ko(b)}" + (f" {taps}연타" if taps > 1 else " 1탭")

    def process(self, frame_bgr: np.ndarray, t_ms: float) -> Tuple[np.ndarray, dict]:
        import cv2
        self._handle_cmds(t_ms)
        self._fps_hist.append(time.monotonic())
        H, W = frame_bgr.shape[:2]
        if self.renderer is None:
            self.renderer = Renderer(W, H, self.font_path, mirror=self.mirror)
        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        raw_hands = self.tracker.detect(rgb, int(t_ms)) if self.tracker else []
        with self.lock:
            hands = assign_sides(raw_hands, self.hand_mode, self.zone_offsets)
            self.update(hands, t_ms)
            fps = ((len(self._fps_hist) - 1) / max(1e-6, self._fps_hist[-1] - self._fps_hist[0])
                   if len(self._fps_hist) > 1 else 0.0)
            gs = self.guide_step()
            gtext = self.guide_text(gs)
            gbtn = gs[1][1] if gs and gs[1] else None
            status = (f"{fps:4.1f} fps · 연타 윈도우 {self.engine.window:.0f}ms · 탭 반경 {self.params.press:.2f}/"
                      f"{self.params.release:.2f} · hands={self.hand_mode} · dwell {self.params.dwell_ms:.0f}ms")
            calib_view = self.calib.view() if self.calib else None
            text = self.composer.text()
            disp = self.renderer.draw(frame_bgr, hands, self.detectors, self.engine, text.split("\n")[-1], t_ms,
                                      status, self.warnings, list(self.events), gtext, gbtn, calib_view, self.debug,
                                      show_panel=self.show_panel)
            if self.recorder == "pending":
                self.recorder = cv2.VideoWriter(self.record_path, cv2.VideoWriter_fourcc(*"mp4v"), 30.0, (W, H))
            if self.recorder is not None:
                self.recorder.write(disp)
            if self.screenshot_req:
                self.screenshot_req = False
                self.last_screenshot = str(HERE / f"screenshot_{datetime.now():%Y%m%d_%H%M%S}.png")
                cv2.imwrite(self.last_screenshot, disp)
                self.events.append("[스크린샷 저장]")
            snap = self._build_snapshot(hands, fps, t_ms, gs, gtext, calib_view, text)
            self._snap = snap
        return disp, snap

    def _build_snapshot(self, hands, fps, t_ms, gs, gtext, calib_view, text) -> dict:
        hinfo = {}
        for side in ("L", "R"):
            o = hands.get(side)
            det = self.detectors[side]
            hinfo[side] = None if o is None else {
                "model": o.model_label, "score": round(o.model_score, 2), "geom": o.geom_label, "palm_ok": o.palm_ok,
                "nearest": det.nearest, "d": round(det.nearest_d, 3) if det.nearest_d < float("inf") else None,
                "d3": round(det.d3[det.nearest], 3) if det.nearest in det.d3 else None,
                "speed": round(det.speed, 2), "pressed": det.pressed, "scale": round(o.scale, 1),
                "release": det.last_release}
        committed = "".join(self.composer.committed)
        composing = self.composer._render_current()
        return {"t_ms": round(t_ms, 1), "fps": round(fps, 1), "text": committed, "composing": composing,
                "n_events": self.n_events, "events": list(self.events), "hands": hinfo, "warnings": list(self.warnings),
                "pending": {b: c for b, (c, _) in self.engine.pending().items()},
                "params": {"window": self.engine.window, "press": self.params.press,
                           "release_margin": round(self.params.release - self.params.press, 3),
                           "dwell_ms": self.params.dwell_ms, "rebound": self.params.rebound,
                           "max_speed": self.params.max_speed, "z_weight": self.params.z_weight,
                           "rebound3": self.params.rebound3, "sticky": self.params.sticky},
                "hand_mode": self.hand_mode,
                "options": {"palm_gate": self.palm_gate, "mirror": self.mirror, "debug": self.debug,
                            "hid": self.hid_out is not None, "early_commit": self.engine.early_commit,
                            "use_depth": self.params.use_depth, "rolling_window": self.engine.window_mode == "last"},
                "hid_error": self.hid_error, "recording": self.record_path, "screenshot": self.last_screenshot,
                "guide": {"target": self.guide.target if self.guide else "", "text": gtext,
                          "done": bool(gs and gs[1] is None), "wrong": bool(gs and gs[2])},
                "camera": {"index": self.camera_index, "list": self.cameras, "error": self.camera_error},
                "calib": calib_view or self.last_calib_view, "profile": self.profile_name,
                "mapping_src": self.mapping_src, "zone_offsets": {k: list(v) for k, v in self.zone_offsets.items()},
                "n_offsets": len(self.zone_offsets)}

    def snapshot(self) -> dict:
        with self.lock:
            return dict(self._snap)

    def close(self) -> None:
        if self.recorder not in (None, "pending"):
            self.recorder.release()
        if self.log_f:
            self.log_f.close()
        if self.tracker:
            self.tracker.close()


# ---------------------------------------------------------------------------
# 로컬 웹 앱 — 표준 http.server: MJPEG 스트림 + JSON 상태/명령 + 단일 HTML 페이지
# ---------------------------------------------------------------------------
PAGE_HTML = r"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><title>Keyboard In My Hand — XR demo</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
:root{--bg:#0f1115;--panel:#181b22;--line:#2a2f3a;--fg:#e8eaf0;--mut:#9aa3b2;--acc:#ffb347;--acc2:#7fd1ff;--ok:#5ad46a;--bad:#ff6b6b;--cal:#ff5ad4}
*{box-sizing:border-box}html,body{margin:0;height:100%;background:var(--bg);color:var(--fg);font-family:"Apple SD Gothic Neo","Malgun Gothic","NanumGothic","Noto Sans CJK KR","Noto Sans KR",system-ui,sans-serif}
body{display:grid;grid-template-rows:auto 1fr auto;grid-template-columns:1fr 380px;grid-template-areas:"top top" "video side" "text side";gap:10px;padding:10px;height:100vh}
#top{grid-area:top;display:flex;flex-wrap:wrap;align-items:center;gap:10px 14px;padding:6px 10px;background:var(--panel);border:1px solid var(--line);border-radius:10px}
#top h1{font-size:16px;margin:0;font-weight:700;white-space:nowrap}#top .sub{color:var(--mut);font-size:12px}
.chip{display:inline-flex;align-items:center;gap:6px;white-space:nowrap;padding:3px 9px;border-radius:999px;border:1px solid var(--line);background:#12151b;font-size:12px;color:var(--mut)}
.chip b{color:var(--fg)}.chip.ok{border-color:var(--ok)}.chip.bad{border-color:var(--bad)}.chip.L{border-color:var(--acc)}.chip.R{border-color:var(--acc2)}
#video{grid-area:video;background:#000;border-radius:10px;overflow:hidden;position:relative;min-height:240px;display:flex;align-items:center;justify-content:center}
#video img{max-width:100%;max-height:100%;object-fit:contain}
#warn{position:absolute;left:50%;top:12px;transform:translateX(-50%);background:rgba(20,20,20,.75);color:var(--acc2);padding:6px 12px;border-radius:8px;font-size:14px;display:none}
#side{grid-area:side;background:var(--panel);border:1px solid var(--line);border-radius:10px;display:flex;flex-direction:column;min-height:0}
.tabs{display:flex;border-bottom:1px solid var(--line)}.tabs button{flex:1;background:none;border:0;color:var(--mut);padding:10px;font-size:14px;cursor:pointer;border-bottom:2px solid transparent}
.tabs button.on{color:var(--fg);border-bottom-color:var(--acc)}
.tab{display:none;padding:12px;overflow:auto;flex:1}.tab.on{display:block}
h3{font-size:13px;margin:14px 0 6px;color:var(--mut);letter-spacing:.04em;text-transform:uppercase}h3:first-child{margin-top:0}
.row{display:flex;align-items:center;gap:8px;margin:6px 0;flex-wrap:wrap}.row label{font-size:13px}
.slider{display:grid;grid-template-columns:86px 1fr 62px;align-items:center;gap:8px;margin:6px 0;font-size:13px}
.slider input{width:100%}.slider .val{text-align:right;color:var(--acc);font-variant-numeric:tabular-nums}
button.btn{background:#242936;color:var(--fg);border:1px solid var(--line);border-radius:8px;padding:7px 11px;font-size:13px;cursor:pointer;white-space:nowrap}
button.btn:hover{border-color:var(--acc)}button.btn.pri{background:var(--acc);color:#000;border-color:var(--acc);font-weight:700}
button.btn.cal{background:var(--cal);color:#000;border-color:var(--cal);font-weight:700}button.btn.sm{padding:5px 8px;font-size:12px}
input[type=text],select{background:#12151b;color:var(--fg);border:1px solid var(--line);border-radius:8px;padding:6px 8px;font-size:13px}
.card{border:1px solid var(--line);border-radius:10px;padding:10px;margin:8px 0;background:#12151b}
.card.cal{border-color:var(--cal)}.card .t{font-weight:700;margin-bottom:4px}.card .i{font-size:13px;line-height:1.45}.card .f{font-size:12px;color:var(--ok);margin-top:6px;min-height:16px}
.bar{height:8px;background:#242936;border-radius:4px;overflow:hidden;margin-top:8px}.bar i{display:block;height:100%;background:var(--cal);width:0%}
ul.sum{font-size:12px;color:var(--mut);padding-left:16px;margin:6px 0;max-height:150px;overflow:auto}
#text{grid-area:text;background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:10px;display:grid;grid-template-columns:1fr auto;gap:10px;align-items:stretch}
#textbox{min-height:96px;max-height:160px;overflow:auto;font-size:34px;line-height:1.35;padding:6px 10px;background:#0c0e12;border:1px solid var(--line);border-radius:8px;white-space:pre-wrap;word-break:break-all;user-select:text}
#textbox .comp{text-decoration:underline;text-decoration-color:var(--acc);text-underline-offset:6px}
#textbox .caret{display:inline-block;width:2px;height:1em;background:var(--fg);vertical-align:-0.15em;animation:blink 1s steps(2) infinite}@keyframes blink{50%{opacity:0}}
#events{font-size:13px;color:var(--mut);margin-top:6px;min-height:18px}#events span{display:inline-block;background:#242936;border-radius:6px;padding:1px 7px;margin-right:4px;color:var(--fg)}
.tbtns{display:flex;flex-direction:column;gap:6px;justify-content:center}
.mut{color:var(--mut);font-size:12px}.kbd{font-family:ui-monospace,monospace;background:#242936;padding:1px 5px;border-radius:4px;font-size:11px}
@media (max-width:1380px){#top .sub{display:none}}
@media (max-width:1000px){body{grid-template-columns:1fr;grid-template-areas:"top" "video" "text" "side";height:auto}}
</style></head><body>
<div id="top"><h1>Keyboard In My Hand <span class="sub">— XR(vision-only) demo · 장갑 없이 손 추적만으로 같은 메커니즘</span></h1>
 <span class="chip" id="c_fps"><b>–</b> fps</span><span class="chip L" id="c_L">왼손 <b>–</b></span><span class="chip R" id="c_R">오른손 <b>–</b></span>
 <span class="chip" id="c_win">윈도우 <b>–</b></span><span class="chip" id="c_press">반경 <b>–</b></span><span class="chip" id="c_prof">프로필 <b>–</b></span>
 <span style="flex:1"></span><select id="cam_sel" title="카메라" style="font-size:12px;padding:4px 6px"></select><button class="btn sm" onclick="send('probe_cameras')" title="카메라 목록 다시 찾기">재검색</button><button class="btn sm" onclick="send('screenshot')">스크린샷</button><button class="btn sm" id="b_rec" onclick="toggleRec()">● 녹화</button><button class="btn sm" onclick="if(confirm('종료할까요?'))send('quit')">종료</button></div>
<div id="video"><img id="stream" src="/stream" alt="camera"><div id="warn"></div></div>
<div id="side">
 <div class="tabs"><button class="on" data-tab="cal">캘리브레이션</button><button data-tab="set">설정</button><button data-tab="help">도움말</button></div>
 <div class="tab on" id="tab-cal">
  <h3>프로필</h3>
  <div class="row"><select id="prof_sel" style="flex:1"></select><input type="text" id="prof_name" placeholder="이름" style="width:90px"></div>
  <div class="row"><button class="btn sm" onclick="profLoad()">불러오기</button><button class="btn sm" onclick="profSave()">저장</button><button class="btn sm" onclick="send('profile_reset')">기본값</button><span class="mut" id="prof_info"></span></div>
  <h3>캘리브레이션</h3>
  <div class="row"><button class="btn cal" onclick="calStart('all')">전체 시작 (약 1분)</button></div>
  <div class="row"><button class="btn sm" onclick="calStart('hands')">손 확인</button><button class="btn sm" onclick="calStart('zones')">스윗스팟 16</button><button class="btn sm" onclick="calStart('threshold')">탭 반경</button><button class="btn sm" onclick="calStart('window')">연타 윈도우</button></div>
  <div class="card cal" id="cal_card" style="display:none"><div class="t" id="cal_t"></div><div class="i" id="cal_i"></div><div class="f" id="cal_f"></div><div class="bar"><i id="cal_bar"></i></div>
   <div class="row" style="margin-top:8px"><button class="btn pri sm" onclick="send('calib_next')">다음 ▶</button><button class="btn sm" onclick="send('calib_skip')">건너뛰기</button><button class="btn sm" onclick="send('calib_cancel')">취소 (Esc)</button></div></div>
  <div class="card" id="cal_done" style="display:none"><div class="t">결과</div><ul class="sum" id="cal_sum"></ul></div>
  <h3>안내 모드</h3>
  <div class="row"><input type="text" id="guide_in" placeholder="목표 문장 (예: 메카)" style="flex:1"><button class="btn sm" onclick="send('set_guide',{target:document.getElementById('guide_in').value})">적용</button><button class="btn sm" onclick="send('set_guide',{target:''})">해제</button></div>
  <div class="mut" id="guide_txt"></div>
 </div>
 <div class="tab" id="tab-set">
  <h3>파라미터</h3><div id="sliders"></div>
  <h3>좌우 판정</h3>
  <div class="row"><label><input type="radio" name="hm" value="model"> model</label><label><input type="radio" name="hm" value="model-swap"> model-swap</label><label><input type="radio" name="hm" value="geom"> geom</label></div>
  <div class="mut">model = MediaPipe 라벨 + 손바닥 게이트 · swap = 라벨 반전 · geom = 손바닥이 카메라를 향한다고 가정하고 기하만</div>
  <h3>옵션</h3>
  <div class="row"><label><input type="checkbox" id="o_palm_gate"> 손바닥 게이트</label><label><input type="checkbox" id="o_mirror"> 거울 표시</label><label><input type="checkbox" id="o_debug"> 디버그 HUD</label></div>
  <div class="row"><label><input type="checkbox" id="o_early_commit"> early commit</label><label><input type="checkbox" id="o_hid"> OS 키 전송(HID)</label><label><input type="checkbox" id="o_beep" checked> 탭 소리</label></div>
  <div class="row"><label><input type="checkbox" id="o_use_depth"> 3D 들어올림 감지</label><label><input type="checkbox" id="o_rolling_window"> 롤링 윈도우(마지막 탭 기준)</label></div>
  <div class="mut">3D 감지 = world landmark 로 카메라 쪽으로 드는 동작을 잡음(정면 각도에서 연타 누락 방지) · 롤링 = 3연타가 첫 탭 기준 윈도우를 넘겨 갈리는 것 방지(펌웨어는 첫 탭 기준)</div>
  <div class="mut" id="hid_err"></div>
 </div>
 <div class="tab" id="tab-help">
  <h3>사용법</h3>
  <div class="i" style="font-size:13px;line-height:1.5">두 손바닥을 카메라 쪽으로 향하고 같은 손 엄지로 손가락 마디를 톡톡 두드립니다.<br>
  왼손 = 자음, 오른손 = 모음. 첫째 마디(손끝 쪽) / 둘째 마디(중간). 같은 버튼 2·3연타 = 가획(ㄱ→ㅋ→ㄲ).<br>
  BS(왼손)·Space(오른손)는 <b>검지 밑마디</b>(손바닥 쪽 구간).<br><br>
  <b>키보드</b>: <span class="kbd">Backspace</span> 지우기 · <span class="kbd">Enter</span> 줄바꿈 · <span class="kbd">Space</span> 띄어쓰기 · <span class="kbd">Esc</span> 캘리브레이션 취소 · <span class="kbd">Ctrl+L</span> 전체 지우기<br><br>
  <b>캘리브레이션 순서</b>: 손 확인 → 스윗스팟 16(버튼마다 엄지로 누른 채 1초) → 비접촉 자세 2초 → ㄱ 빠른 2연타 ×5 → ㄱ 따로 두 번 ×5. 결과는 프로필 JSON에 저장되어 다음 실행 때 자동 적용됩니다.<br><br>
  <b>잘 안 잡힐 때</b>: 디버그 HUD로 최근접 버튼 거리(d, d3)를 보며 탭 반경을 조정. 2연타가 하나로 합쳐지면 리바운드/3D 리바운드를 낮추고, 헛탭이 많으면 체류(ms)를 올리세요.<br>
  <b>연타 요령</b>: 엄지를 2cm 정도 확실히 들었다 다시 닿기. 카메라를 정면이 아니라 약간 위/옆에서 손을 보게 두면(손바닥을 30° 정도 기울임) 드는 동작이 화면에서 더 잘 보입니다. HUD의 rel=2d/3d 가 어느 채널로 뗌을 잡았는지 보여줍니다.</div>
 </div>
</div>
<div id="text"><div><div id="textbox"></div><div id="events"></div></div>
 <div class="tbtns"><button class="btn" onclick="send('backspace')">⌫ 지우기</button><button class="btn" onclick="send('space')">␣ 띄어쓰기</button><button class="btn" onclick="send('enter')">⏎ 엔터</button><button class="btn" onclick="copyText()">복사</button><button class="btn" onclick="send('clear')">전체 지우기</button></div></div>
<script>
const SLIDERS=[{id:'window',l:'연타 윈도우',min:100,max:900,st:10,u:'ms'},{id:'press',l:'탭 반경',min:0.10,max:0.60,st:0.01,u:''},{id:'release_margin',l:'해제 여유',min:0.05,max:0.30,st:0.01,u:''},{id:'dwell_ms',l:'체류',min:0,max:150,st:5,u:'ms'},{id:'rebound',l:'리바운드',min:0.05,max:0.40,st:0.01,u:''},{id:'max_speed',l:'속도 상한',min:2,max:20,st:0.5,u:'/s'},{id:'rebound3',l:'3D 리바운드',min:0.10,max:0.60,st:0.01,u:''},{id:'sticky',l:'연타 고착',min:1.0,max:2.0,st:0.05,u:'×'},{id:'z_weight',l:'z 가중',min:0,max:1,st:0.05,u:''}];
let S=null,lastN=null,beepOn=true,dragging=null,sendT=null,pend={};
const $=id=>document.getElementById(id);
function fmt(v,st){return (st<1)?Number(v).toFixed(2):String(Math.round(v))}
(function(){const box=$('sliders');for(const s of SLIDERS){const d=document.createElement('div');d.className='slider';d.innerHTML=`<span>${s.l}</span><input type="range" id="sl_${s.id}" min="${s.min}" max="${s.max}" step="${s.st}"><span class="val" id="sv_${s.id}">–</span>`;box.appendChild(d);
 const inp=d.querySelector('input');inp.addEventListener('pointerdown',()=>dragging=s.id);inp.addEventListener('pointerup',()=>setTimeout(()=>dragging=null,150));
 inp.addEventListener('input',()=>{$('sv_'+s.id).textContent=fmt(inp.value,s.st)+s.u;pend[s.id]=parseFloat(inp.value);clearTimeout(sendT);sendT=setTimeout(()=>{send('set_params',{params:pend});pend={}},80)})}
 document.querySelectorAll('.tabs button').forEach(b=>b.onclick=()=>{document.querySelectorAll('.tabs button').forEach(x=>x.classList.remove('on'));document.querySelectorAll('.tab').forEach(x=>x.classList.remove('on'));b.classList.add('on');$('tab-'+b.dataset.tab).classList.add('on')});
 document.querySelectorAll('input[name=hm]').forEach(r=>r.onchange=()=>send('set_hand_mode',{mode:r.value}));
 for(const o of ['palm_gate','mirror','debug','early_commit','hid','use_depth','rolling_window']){$('o_'+o).onchange=e=>send('set_option',{name:o,value:e.target.checked})}
 $('o_beep').onchange=e=>beepOn=e.target.checked;
 $('cam_sel').onchange=e=>send('set_camera',{index:parseInt(e.target.value)});
 document.addEventListener('keydown',e=>{const t=e.target.tagName;if(t==='INPUT'||t==='SELECT'||t==='TEXTAREA')return;
  if(e.key==='Backspace'){send('backspace');e.preventDefault()}else if(e.key==='Enter'){send('enter');e.preventDefault()}else if(e.key===' '){send('space');e.preventDefault()}
  else if(e.key==='Escape'){send('calib_cancel')}else if(e.key.toLowerCase()==='l'&&e.ctrlKey){send('clear');e.preventDefault()}});
 document.addEventListener('pointerdown',()=>{if(!window._ac){try{window._ac=new (window.AudioContext||window.webkitAudioContext)()}catch(x){}}},{once:false});
})();
async function send(cmd,extra){try{await fetch('/cmd',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(Object.assign({cmd},extra||{}))})}catch(e){}}
function beep(f,dur){if(!beepOn||!window._ac)return;const ac=window._ac,o=ac.createOscillator(),g=ac.createGain();o.type='sine';o.frequency.value=f;g.gain.setValueAtTime(0.25,ac.currentTime);g.gain.exponentialRampToValueAtTime(0.001,ac.currentTime+dur);o.connect(g).connect(ac.destination);o.start();o.stop(ac.currentTime+dur)}
function calStart(w){send('calib_start',{which:w});document.querySelector('.tabs button[data-tab=cal]').click()}
function profLoad(){const n=$('prof_name').value||$('prof_sel').value;send('profile_load',{name:n})}
function profSave(){const n=$('prof_name').value||$('prof_sel').value||'default';send('profile_save',{name:n})}
let recOn=false;function toggleRec(){recOn=!recOn;send(recOn?'record_start':'record_stop')}
function copyText(){const t=(S?S.text+S.composing:'');navigator.clipboard&&navigator.clipboard.writeText(t)}
function esc(s){return String(s).replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]))}
function render(s){S=s;
 $('c_fps').innerHTML=`<b>${s.fps}</b> fps`;
 for(const side of ['L','R']){const h=s.hands[side],el=$('c_'+side);const name=side==='L'?'왼손':'오른손';
  if(!h){el.innerHTML=`${name} <b>–</b>`;el.className='chip '+side}else{el.innerHTML=`${name} <b>${h.palm_ok?'✓':'✗손바닥'}</b> <span class="mut">${h.nearest||''} ${h.d==null?'':h.d.toFixed(2)}</span>`;el.className='chip '+side+(h.palm_ok?' ok':' bad')}}
 $('c_win').innerHTML=`윈도우 <b>${Math.round(s.params.window)}</b>ms`;$('c_press').innerHTML=`반경 <b>${s.params.press.toFixed(2)}</b>`;
 $('c_prof').innerHTML=`프로필 <b>${esc(s.profile)}</b> <span class="mut">${s.n_offsets}/16</span>`;
 const w=$('warn');if(s.warnings.length){w.style.display='block';w.textContent=s.warnings.join(' · ')}else w.style.display='none';
 const tb=$('textbox');const html=esc(s.text)+(s.composing?`<span class="comp">${esc(s.composing)}</span>`:'')+'<span class="caret"></span>';if(tb.innerHTML!==html){tb.innerHTML=html;tb.scrollTop=tb.scrollHeight}
 $('events').innerHTML=s.events.slice(-12).map(e=>`<span>${esc(e)}</span>`).join('');
 if(lastN!==null&&s.n_events>lastN){const last=s.events[s.events.length-1]||'';beep(last.startsWith('BS')?520:1180,0.06)}lastN=s.n_events;
 for(const sl of SLIDERS){if(dragging===sl.id)continue;const inp=$('sl_'+sl.id);if(document.activeElement===inp)continue;const v=s.params[sl.id];inp.value=v;$('sv_'+sl.id).textContent=fmt(v,sl.st)+sl.u}
 document.querySelectorAll('input[name=hm]').forEach(r=>r.checked=(r.value===s.hand_mode));
 for(const o of ['palm_gate','mirror','debug','early_commit','hid','use_depth','rolling_window']){const el=$('o_'+o);if(document.activeElement!==el)el.checked=!!s.options[o]}
 $('hid_err').textContent=s.hid_error||'';
 $('b_rec').textContent=s.recording?'■ 녹화 중지':'● 녹화';recOn=!!s.recording;$('b_rec').style.color=s.recording?'var(--bad)':'';
 $('guide_txt').textContent=s.guide.target?(s.guide.text||''):'';
 const c=s.calib;const card=$('cal_card');if(c&&c.active){card.style.display='block';$('cal_t').textContent=`${c.step_idx+1}/${c.n_steps} · ${c.title}`;$('cal_i').textContent=c.instruction;$('cal_f').textContent=c.feedback||'';$('cal_bar').style.width=Math.round((c.progress||0)*100)+'%'}else card.style.display='none';
 const done=$('cal_done');if(c&&c.summary&&c.summary.length&&!c.active){done.style.display='block';$('cal_sum').innerHTML=c.summary.map(x=>`<li>${esc(x)}</li>`).join('')}else done.style.display='none';
 const cam=s.camera||{};const cs=$('cam_sel');if(document.activeElement!==cs){const lst=(cam.list&&cam.list.length)?cam.list:[0,1,2,3].map(i=>({index:i,ok:true,name:'',w:0,h:0}));
  const sig=JSON.stringify([lst,cam.index]);if(cs.dataset.sig!==sig){cs.dataset.sig=sig;cs.innerHTML=lst.map(c=>`<option value="${c.index}" ${c.ok?'':'disabled'}>카메라 ${c.index}${c.name?' · '+esc(c.name):''}${c.w?' ('+c.w+'×'+c.h+')':''}${c.ok?'':' ✗'}</option>`).join('');if(cam.index!=null)cs.value=String(cam.index)}}
 if(cam.error){$('warn').style.display='block';$('warn').textContent=cam.error}
 const sel=$('prof_sel');const opts=(s.profiles||[]);if(sel.dataset.sig!==opts.join('|')){sel.dataset.sig=opts.join('|');sel.innerHTML=opts.map(p=>`<option value="${esc(p)}">${esc(p)}</option>`).join('');sel.value=s.profile}
}
async function poll(){try{const r=await fetch('/state',{cache:'no-store'});render(await r.json());setTimeout(poll,100)}catch(e){setTimeout(poll,600)}}
poll();
</script></body></html>
"""


class DemoHandler(BaseHTTPRequestHandler):
    pipeline: "Pipeline" = None
    bus: FrameBus = None
    stop_event: threading.Event = None
    _profiles_cache: Tuple[float, List[str]] = (0.0, [])

    def log_message(self, *a):  # 콘솔 소음 억제
        pass

    def _send(self, code: int, ctype: str, body: bytes) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = self.path.split("?")[0]
        if path in ("/", "/index.html"):
            self._send(200, "text/html; charset=utf-8", PAGE_HTML.encode("utf-8"))
        elif path == "/state":
            snap = self.pipeline.snapshot()
            now = time.monotonic()
            if now - DemoHandler._profiles_cache[0] > 1.0:
                DemoHandler._profiles_cache = (now, list_profiles())
            snap["profiles"] = DemoHandler._profiles_cache[1]
            self._send(200, "application/json; charset=utf-8", json.dumps(snap, ensure_ascii=False).encode("utf-8"))
        elif path == "/snapshot.jpg":
            _, jpeg, _ = self.bus.latest()
            self._send(200, "image/jpeg", jpeg)
        elif path == "/stream":
            self.send_response(200)
            self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            seq = -1
            try:
                while not self.stop_event.is_set():
                    seq2, jpeg = self.bus.wait(seq, timeout=1.0)
                    if seq2 == seq or not jpeg:
                        continue
                    seq = seq2
                    self.wfile.write(b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: " +
                                     str(len(jpeg)).encode() + b"\r\n\r\n" + jpeg + b"\r\n")
                    self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError, OSError):
                return
        else:
            self._send(404, "text/plain", b"not found")

    def do_POST(self):
        if self.path.split("?")[0] != "/cmd":
            self._send(404, "text/plain", b"not found")
            return
        n = int(self.headers.get("Content-Length") or 0)
        try:
            body = json.loads(self.rfile.read(n).decode("utf-8") or "{}")
        except (ValueError, UnicodeDecodeError):
            self._send(400, "application/json", b'{"ok": false, "msg": "bad json"}')
            return
        cmd = body.get("cmd", "")
        if cmd == "quit":
            self.stop_event.set()
        else:
            self.pipeline.post(body)
        self._send(200, "application/json", b'{"ok": true}')


def start_server(pipeline: "Pipeline", bus: FrameBus, stop_event: threading.Event, host: str, port: int):
    DemoHandler.pipeline, DemoHandler.bus, DemoHandler.stop_event = pipeline, bus, stop_event
    for p in range(port, port + 20):
        try:
            srv = ThreadingHTTPServer((host, p), DemoHandler)
            break
        except OSError:
            continue
    else:
        raise SystemExit(f"[error] 포트 {port}~{port + 19} 모두 사용 중")
    srv.daemon_threads = True
    th = threading.Thread(target=srv.serve_forever, kwargs={"poll_interval": 0.2}, daemon=True)
    th.start()
    return srv, p


# ---------------------------------------------------------------------------
# 실행 — 캡처 루프(워커) + 웹 앱 / OpenCV 창
# ---------------------------------------------------------------------------
def camera_backend():
    import cv2
    sysname = platform.system()
    if sysname == "Windows":
        return cv2.CAP_DSHOW
    if sysname == "Darwin":
        return cv2.CAP_AVFOUNDATION   # macOS: 명시해야 TCC(카메라 권한) 요청이 확실히 일어난다
    return 0


MAC_CAMERA_HINT = """
  macOS 카메라 권한 체크리스트
   · 첫 VideoCapture 호출 때 "'Code'(또는 'Terminal')이(가) 카메라에 접근하려고 합니다" 팝업이 떠야 합니다.
     시스템 설정 → 개인정보 보호 및 보안 → 카메라 목록에는 '한 번이라도 요청한 앱'만 나타납니다.
   · 팝업이 안 뜨고 목록에도 없으면 (VS Code 통합 터미널이면 앱 = VS Code):
       tccutil reset Camera com.microsoft.VSCode      # Terminal.app 은 com.apple.Terminal
     실행 후 VS Code 를 완전히 종료(Cmd+Q)했다가 다시 열어 재실행.
   · 그래도 안 되면 Terminal.app 에서 같은 명령을 한 번 실행해 권한을 받으세요.
   · 열리는 카메라 번호 확인:  python kih_xr_demo.py --list-cameras   (iPhone 연속성 카메라가 0번을 차지하기도 함 → --camera 1)
   · 아이폰이 자꾸 잡히면: 아이폰 설정 → 일반 → AirPlay 및 연속성(또는 AirPlay 및 Handoff) → '연속성 카메라' 끄기.
     또는 pip install pyobjc-framework-AVFoundation 후  --camera-name FaceTime  으로 내장 카메라를 이름으로 지정.
"""


def _cv2_quiet():
    """OpenCV 내부 로그(없는 카메라 탐색 시 FFMPEG 오류 등) 억제. 구버전이면 무시."""
    try:
        import cv2
        cv2.utils.logging.setLogLevel(cv2.utils.logging.LOG_LEVEL_SILENT)
    except Exception:  # noqa: BLE001
        pass


def mac_camera_names() -> Tuple[List[str], str]:
    """macOS 카메라 장치 이름 목록. (이름들, 출처). PyObjC(AVFoundation)가 있으면 OpenCV와 같은 열거 순서로,
    없으면 system_profiler(순서가 OpenCV 색인과 다를 수 있음)."""
    if platform.system() != "Darwin":
        return [], ""
    try:
        import AVFoundation as AVF  # pyobjc-framework-AVFoundation (선택 설치)
        names = []
        try:
            types = [AVF.AVCaptureDeviceTypeBuiltInWideAngleCamera, AVF.AVCaptureDeviceTypeExternalUnknown]
            sess = AVF.AVCaptureDeviceDiscoverySession.discoverySessionWithDeviceTypes_mediaType_position_(
                types, AVF.AVMediaTypeVideo, AVF.AVCaptureDevicePositionUnspecified)
            names = [str(d.localizedName()) for d in sess.devices()]
        except Exception:  # noqa: BLE001 — 구버전 API 폴백
            names = [str(d.localizedName()) for d in AVF.AVCaptureDevice.devicesWithMediaType_(AVF.AVMediaTypeVideo)]
        if names:
            return names, "AVFoundation(OpenCV와 같은 순서)"
    except Exception:  # noqa: BLE001
        pass
    try:
        import subprocess
        out = subprocess.run(["system_profiler", "SPCameraDataType", "-json"], capture_output=True, text=True, timeout=15).stdout
        items = json.loads(out).get("SPCameraDataType", [])
        names = [str(it.get("_name", "?")) for it in items]
        return names, "system_profiler(순서는 OpenCV 색인과 다를 수 있음)"
    except Exception:  # noqa: BLE001
        return [], ""


def resolve_camera_index(name_substr: str) -> int:
    """--camera-name: 장치 이름 부분 문자열(대소문자 무시)로 OpenCV 색인을 찾는다 (macOS: PyObjC 필요)."""
    names, src = mac_camera_names()
    if not names or "AVFoundation" not in src:
        raise SystemExit("[error] --camera-name 은 macOS + PyObjC 가 필요합니다: pip install pyobjc-framework-AVFoundation\n"
                         "        대신 python kih_xr_demo.py --list-cameras 로 번호를 확인해 --camera N 을 쓰세요."
                         + (f"\n        (system_profiler 카메라: {', '.join(names)})" if names else ""))
    key = name_substr.lower()
    for i, n in enumerate(names):
        if key in n.lower():
            print(f"[info] 카메라 '{n}' → --camera {i}")
            return i
    raise SystemExit(f"[error] '{name_substr}' 를 포함하는 카메라가 없습니다. 목록: {names}")


def list_cameras(max_index: int = 6) -> int:
    import cv2
    _cv2_quiet()
    be = camera_backend()
    found = 0
    names, src = mac_camera_names()
    if names:
        print(f"  장치 이름 [{src}]: " + " · ".join(f"[{i}] {n}" for i, n in enumerate(names)))
    for i in range(max_index):
        cap = cv2.VideoCapture(i, be) if be else cv2.VideoCapture(i)
        ok = cap.isOpened()
        if ok:
            ok, frame = cap.read()
        if ok:
            found += 1
            print(f"  camera {i}: OK {frame.shape[1]}x{frame.shape[0]}")
        else:
            print(f"  camera {i}: 열리지 않음")
        cap.release()
    if found == 0 and platform.system() == "Darwin":
        print(MAC_CAMERA_HINT)
    return 0 if found else 1


def mac_builtin_camera_index() -> Optional[int]:
    """macOS: 장치 이름으로 내장 카메라 번호 추정 (PyObjC 있을 때만). 아이폰 연속성 카메라가 0번을 차지하는 문제 회피."""
    names, src = mac_camera_names()
    if not names or "AVFoundation" not in src:
        return None
    for i, n in enumerate(names):
        low = n.lower()
        if "facetime" in low or "built-in" in low or "내장" in low:
            return i
    return None


def resolve_initial_camera(args, pl: "Pipeline", quiet: bool = False) -> Optional[int]:
    """우선순위: --camera-name > --camera N > 프로필에 저장된 카메라 > DEFAULT_CAMERA_INDEX
    > macOS 내장 카메라 이름 매칭 > 0."""
    if args.video:
        return None
    if getattr(args, "camera_name", None):
        idx, why = resolve_camera_index(args.camera_name), "--camera-name"
    elif args.camera is not None:
        idx, why = args.camera, "--camera"
    elif pl.camera_index is not None:
        idx, why = pl.camera_index, f"프로필 '{pl.profile_name}'"
    elif DEFAULT_CAMERA_INDEX is not None:
        idx, why = DEFAULT_CAMERA_INDEX, f"기본값 DEFAULT_CAMERA_INDEX={DEFAULT_CAMERA_INDEX}"
    else:
        b = mac_builtin_camera_index()
        idx, why = (b, "내장 카메라 이름 매칭") if b is not None else (0, "기본값")
    args.camera = idx
    pl.remember_camera = why.startswith("--camera") and pl.camera_index != idx   # 열기 성공 후 remember_camera_if_requested()
    pl.camera_index = idx
    if not quiet:
        print(f"[info] 카메라 {idx} ({why})")
    return idx


def remember_camera_if_requested(pl: "Pipeline") -> None:
    """명시적 --camera/--camera-name 으로 연 카메라를 프로필에 기억 → 다음엔 인수 없이(VS Code ▶) 실행해도 같은 카메라."""
    if getattr(pl, "remember_camera", False) and pl.autosave and pl.profile_name:
        pl.remember_camera = False
        try:
            save_profile(pl.profile_name, pl.export_profile())
            print(f"[info] 카메라 {pl.camera_index} 을(를) 프로필 '{pl.profile_name}' 에 기억했습니다 (다음엔 인수 없이 실행해도 이 카메라)")
        except OSError as e:
            print(f"[warn] 프로필 저장 실패: {e}", file=sys.stderr)


def open_camera(index: int, args):
    import cv2
    _cv2_quiet()
    be = camera_backend()
    cap = cv2.VideoCapture(index, be) if be else cv2.VideoCapture(index)
    if cap.isOpened():
        if args.width:
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, args.width)
        if args.height:
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, args.height)
    return cap


def probe_cameras(args, skip: Optional[int] = None, max_index: int = 5) -> List[dict]:
    """번호별 열림 여부·해상도 (+ macOS 장치 이름). 현재 쓰는 카메라(skip)는 열지 않고 'ok' 로 둔다."""
    names, src = mac_camera_names()
    out = []
    for i in range(max_index):
        name = names[i] if ("AVFoundation" in src and i < len(names)) else ""
        if i == skip:
            out.append({"index": i, "ok": True, "w": 0, "h": 0, "name": name, "current": True})
            continue
        cap = open_camera(i, args)
        ok = cap.isOpened()
        w = h = 0
        if ok:
            ok, frame = cap.read()
            if ok:
                h, w = frame.shape[:2]
        cap.release()
        out.append({"index": i, "ok": bool(ok), "w": w, "h": h, "name": name, "current": False})
    return out


def open_capture(args):
    import cv2
    _cv2_quiet()
    if args.video:
        cap = cv2.VideoCapture(args.video)
    else:
        if args.camera is None:
            args.camera = 0
        cap = open_camera(args.camera, args)
    if not cap.isOpened():
        msg = (f"[error] 입력을 열 수 없습니다: {'video ' + args.video if args.video else 'camera ' + str(args.camera)}"
               " (--camera 1, --video 파일, 다른 앱이 카메라를 쓰는지 확인)")
        if not args.video and platform.system() == "Darwin":
            msg += MAC_CAMERA_HINT
        raise SystemExit(msg)
    return cap


def build_pipeline(args, with_tracker: bool = True) -> "Pipeline":
    mapping, src = load_mapping(args.mapping)
    table = build_tap_table(mapping)
    params = TapParams(press=args.press, release=args.release, rebound=args.rebound, dwell_ms=args.dwell_ms,
                       max_speed=args.max_speed, z_weight=args.z_weight, rebound3=args.rebound3,
                       use_depth=(args.depth == "world"))
    font = find_korean_font(args.font)
    if font is None:
        print("[warn] 한글 폰트를 찾지 못했습니다 — --font 로 지정하세요 (오버레이 한글이 □로 보입니다)", file=sys.stderr)
    tracker = HandTracker(ensure_model(args.model), det_conf=args.det_conf, track_conf=args.track_conf) if with_tracker else None
    pl = Pipeline(table, src, params, window=args.window, early_commit=not args.no_early_commit, debounce=args.debounce,
                  hand_mode=args.hand_mode, palm_gate=not args.no_palm_gate, mirror=not args.no_mirror, debug=args.debug,
                  font_path=font, tracker=tracker, display_width=args.display_width, log_path=args.log,
                  profile_name=args.profile, autosave=not args.no_autosave, verbose=args.verbose,
                  window_mode=args.window_mode)
    if args.target:
        pl.guide = TargetGuide(args.target, table)
    if args.hid:
        pl.set_hid(True)
        print("[info] --hid: " + (pl.hid_error or "확정 자모를 OS 키 입력으로 전송합니다 (OS 입력기를 한글로 두세요)"))
    data = load_profile(args.profile)
    if data:
        pl.apply_profile(data)
        print(f"[info] 프로필 로드: {profile_path(args.profile)} (스윗스팟 {len(pl.zone_offsets)}/16, press {pl.params.press:.2f}, window {pl.engine.window:.0f}ms)")
    print(f"[info] mapping={src} · window={pl.engine.window:.0f}ms({pl.engine.window_mode}) · early_commit={pl.engine.early_commit}"
          f" · depth={'world' if pl.params.use_depth else 'none'} · hand_mode={pl.hand_mode}")
    return pl


def capture_loop(args, pl: "Pipeline", on_frame, stop_event: threading.Event, cap=None) -> int:
    """카메라/영상 → pipeline.process → on_frame(disp, snap). 영상 파일은 실시간 속도로 재생(--loop 반복).
    cap 을 미리 열어 넘기면(메인 스레드) 열기 실패 안내가 스레드 안에서 삼켜지지 않는다."""
    import cv2
    if cap is None:
        cap = open_capture(args)
    fps_src = cap.get(cv2.CAP_PROP_FPS) or 30.0
    if not (1.0 <= fps_src <= 240.0):
        fps_src = 30.0
    t0 = time.monotonic()
    n = 0
    try:
        while not stop_event.is_set():
            if not args.video and pl.camera_request is not None:
                req, pl.camera_request = pl.camera_request, None
                if req != pl.camera_index:
                    new_cap = open_camera(req, args)
                    if new_cap.isOpened():
                        cap.release()
                        cap = new_cap
                        pl.camera_index = req
                        pl.camera_error = ""
                        pl.events.append(f"[카메라 {req}]")
                        for d in pl.detectors.values():
                            d.reset()
                        if pl.autosave and pl.profile_name:
                            try:
                                save_profile(pl.profile_name, pl.export_profile())
                            except OSError:
                                pass
                    else:
                        new_cap.release()
                        pl.camera_error = f"카메라 {req} 를 열 수 없습니다"
                        pl.events.append(f"[카메라 {req} 실패]")
            if not args.video and pl.probe_request:
                pl.probe_request = False
                pl.cameras = probe_cameras(args, skip=pl.camera_index)
            ok, frame = cap.read()
            if not ok:
                if args.video and args.loop:
                    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    continue
                break
            n += 1
            if args.video:
                t_ms = (time.monotonic() - t0) * 1000.0
                target = n / fps_src
                lag = target - (time.monotonic() - t0)
                if lag > 0:
                    time.sleep(min(lag, 0.1))
            else:
                t_ms = (time.monotonic() - t0) * 1000.0
            disp, snap = pl.process(frame, t_ms)
            if on_frame(disp, snap) is False:
                break
            if args.max_frames and n >= args.max_frames:
                break
    finally:
        cap.release()
    return n


def run_gui(args) -> int:
    import cv2
    pl = build_pipeline(args)
    pl.show_panel = False
    resolve_initial_camera(args, pl)
    cap = open_capture(args)          # 메인 스레드에서 먼저 연다 — 권한/장치 오류 안내가 바로 보이도록
    remember_camera_if_requested(pl)
    bus = FrameBus()
    stop_event = threading.Event()
    srv, port = start_server(pl, bus, stop_event, args.host, args.port)
    url = f"http://{'127.0.0.1' if args.host in ('127.0.0.1', '0.0.0.0', '') else args.host}:{port}/"
    webview_mod = None
    if args.ui in ("auto", "native"):
        try:
            import webview as webview_mod  # pywebview — macOS 는 WKWebView 네이티브 창
        except Exception as e:  # noqa: BLE001
            webview_mod = None
            if args.ui == "native":
                print(f"[warn] pywebview 를 불러올 수 없어 브라우저로 엽니다 ({e}). 설치: pip install pywebview", file=sys.stderr)
    print(f"[info] 웹 앱: {url}   ({'네이티브 창' if webview_mod else '브라우저'} · Ctrl+C 또는 화면의 '종료' 버튼으로 끝냄)")
    if webview_mod is None and not args.no_browser:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    q = [int(cv2.IMWRITE_JPEG_QUALITY), args.jpeg_quality]
    dw = args.display_width

    def on_frame(disp, snap):
        if dw and disp.shape[1] > dw:
            h = int(disp.shape[0] * dw / disp.shape[1])
            disp = cv2.resize(disp, (dw, h), interpolation=cv2.INTER_AREA)
        ok, buf = cv2.imencode(".jpg", disp, q)
        if ok:
            bus.publish(buf.tobytes(), snap)
        return not stop_event.is_set()

    def worker():
        try:
            capture_loop(args, pl, on_frame, stop_event, cap=cap)
        except SystemExit as e:   # 스레드 안의 SystemExit 은 조용히 사라지므로 직접 출력
            print(e, file=sys.stderr)
        except Exception as e:  # noqa: BLE001
            print(f"[error] 캡처 루프 종료: {e}", file=sys.stderr)
        finally:
            stop_event.set()

    th = threading.Thread(target=worker, daemon=True)
    th.start()
    try:
        if webview_mod is not None:
            win = webview_mod.create_window("Keyboard In My Hand — XR demo", url, width=1420, height=920,
                                            min_size=(960, 640), text_select=True)
            evs = getattr(win, "events", win)
            try:
                evs.closed += lambda *a: stop_event.set()
            except Exception:  # noqa: BLE001 — 구버전 API 차이는 무시 (창 닫힘 → start() 반환으로도 종료됨)
                pass

            def _close_on_stop():   # 화면의 '종료' 버튼(quit) → 창도 닫는다
                stop_event.wait()
                try:
                    win.destroy()
                except Exception:  # noqa: BLE001
                    pass

            threading.Thread(target=_close_on_stop, daemon=True).start()
            webview_mod.start()          # 메인 스레드 블로킹 — 창이 닫히면 반환
            stop_event.set()
        else:
            while not stop_event.is_set():
                time.sleep(0.2)
    except KeyboardInterrupt:
        stop_event.set()
    srv.shutdown()
    th.join(timeout=3.0)
    pl.close()
    print(f"[done] 최종 텍스트: {pl.composer.text()!r}")
    return 0


def run_cli(args) -> int:
    """--nogui: OpenCV 창 (브라우저 없이) / --no-window: 헤드리스 처리."""
    import cv2
    pl = build_pipeline(args)
    resolve_initial_camera(args, pl)
    cap = open_capture(args)
    remember_camera_if_requested(pl)
    writer = [None]
    stop_event = threading.Event()

    def on_frame(disp, snap):
        if args.record:
            if writer[0] is None:
                writer[0] = cv2.VideoWriter(args.record, cv2.VideoWriter_fourcc(*"mp4v"), 30.0, (disp.shape[1], disp.shape[0]))
            writer[0].write(disp)
        if args.no_window:
            return True
        cv2.imshow("Keyboard In My Hand — XR (vision-only) demo", disp)
        key = cv2.waitKey(1) & 0xFF
        if key in (27, ord("q")):
            return False
        keymap = {ord("c"): {"cmd": "clear"}, 8: {"cmd": "backspace"}, 127: {"cmd": "backspace"},
                  ord("d"): {"cmd": "set_option", "name": "debug", "value": not pl.debug},
                  ord("m"): {"cmd": "set_option", "name": "mirror", "value": not pl.mirror},
                  ord("s"): {"cmd": "screenshot"}, ord("k"): {"cmd": "calib_start", "which": "all"},
                  ord("n"): {"cmd": "calib_next"}, ord("x"): {"cmd": "calib_skip"}, 27: {"cmd": "calib_cancel"},
                  ord("["): {"cmd": "set_params", "params": {"window": pl.engine.window - 25}},
                  ord("]"): {"cmd": "set_params", "params": {"window": pl.engine.window + 25}},
                  ord("-"): {"cmd": "set_params", "params": {"press": pl.params.press - 0.02}},
                  ord("="): {"cmd": "set_params", "params": {"press": pl.params.press + 0.02}},
                  ord("h"): {"cmd": "set_hand_mode", "mode": {"model": "model-swap", "model-swap": "geom", "geom": "model"}[pl.hand_mode]}}
        if key in keymap:
            pl.post(keymap[key])
        return True

    try:
        n = capture_loop(args, pl, on_frame, stop_event, cap=cap)
    finally:
        if writer[0] is not None:
            writer[0].release()
        pl.close()
        if not args.no_window:
            cv2.destroyAllWindows()
    print(f"[done] {n} frames · 최종 텍스트: {pl.composer.text()!r}")
    return 0


# ---------------------------------------------------------------------------
# 셀프테스트 (카메라·mediapipe·브라우저 없이 로직 검증)
# ---------------------------------------------------------------------------
def _synthetic_left_hand() -> np.ndarray:
    """손바닥이 카메라를 향한 왼손(원본 프레임 좌표, 손가락 위, 엄지 왼쪽)."""
    P = np.zeros((21, 3), dtype=np.float32)
    P[0] = (300, 420, 0)
    P[1], P[2], P[3], P[4] = (235, 395, 0), (195, 355, 0), (168, 315, 0), (150, 280, 0)
    mcps = {"index": (250, 300), "middle": (290, 290), "ring": (330, 295), "pinky": (370, 312)}
    for f, (x, y) in mcps.items():
        m, p_, d, t = FINGER_JOINTS[f]
        P[m] = (x, y, 0)
        P[p_] = (x - 4, y - 45, 0)
        P[d] = (x - 7, y - 80, 0)
        P[t] = (x - 9, y - 110, 0)
    return P


def _mirror_hand(P: np.ndarray, width: float = 640.0) -> np.ndarray:
    Q = P.copy()
    Q[:, 0] = width - Q[:, 0]
    return Q


def _test_pipeline() -> "Pipeline":
    table = build_tap_table(MAPPING_FALLBACK)
    return Pipeline(table, "test", TapParams(), window=450.0, tracker=None, autosave=False, profile_name="")


def selftest() -> int:
    passed = failed = 0

    def check(name: str, cond: bool, info: str = "") -> None:
        nonlocal passed, failed
        if cond:
            passed += 1
        else:
            failed += 1
            print(f"  FAIL {name} {info}")

    table = build_tap_table(MAPPING_FALLBACK)
    fw_max = {"L1a": 3, "L1b": 3, "L2a": 2, "L2b": 3, "L3a": 3, "L3b": 2, "L4": 3, "L5": 1,
              "R1a": 2, "R1b": 2, "R2a": 2, "R2b": 2, "R3a": 2, "R3b": 2, "R4": 2, "R5": 3}
    check("maxtap", {b: max(t) for b, t in table.items()} == fw_max)
    check("table L1a", table["L1a"] == {1: "ㄱ", 2: "ㅋ", 3: "ㄲ"})
    check("table R5", table["R5"] == {1: "SPACE", 2: ".", 3: "ENTER"})
    check("file mapping == fallback", load_mapping(None)[0] == MAPPING_FALLBACK)

    def run_engine(presses, window=300, early=True, tick_to=None):
        e = MultiTapEngine(table, window, early)
        for b, t in presses:
            e.tick(t)
            e.press(b, t)
        e.tick(tick_to if tick_to is not None else presses[-1][1] + window + 1)
        return [(ev.token, ev.taps) for ev in e.drain()]

    check("single commit on expiry", run_engine([("L1a", 0)]) == [("ㄱ", 1)])
    check("double", run_engine([("L1a", 0), ("L1a", 150)]) == [("ㅋ", 2)])
    check("triple immediate", run_engine([("L1a", 0), ("L1a", 100), ("L1a", 200)], tick_to=201) == [("ㄲ", 3)])
    check("vowel 2-tap immediate", run_engine([("R2a", 0), ("R2a", 100)], tick_to=101) == [("ㅑ", 2)])
    check("backspace immediate", run_engine([("L5", 0)], tick_to=1) == [("BACKSPACE", 1)])
    check("R5 space/./enter", run_engine([("R5", 0)]) == [("SPACE", 1)] and
          run_engine([("R5", 0), ("R5", 100)]) == [(".", 2)] and
          run_engine([("R5", 0), ("R5", 100), ("R5", 200)], tick_to=201) == [("ENTER", 3)])
    check("early commit", run_engine([("L1a", 0), ("R2a", 100)], tick_to=101) == [("ㄱ", 1)])
    check("A-B-A not merged", run_engine([("L1a", 0), ("R2a", 100), ("L1a", 200)]) == [("ㄱ", 1), ("ㅏ", 1), ("ㄱ", 1)])
    check("no early commit waits", run_engine([("L1a", 0), ("R2a", 100)], early=False, tick_to=101) == [])
    check("debounce", run_engine([("L1a", 0), ("L1a", 20)]) == [("ㄱ", 1)])
    check("window expiry restarts", run_engine([("L1a", 0), ("L1a", 400)]) == [("ㄱ", 1), ("ㄱ", 1)])
    check("ㄴ 2-tap = ㄹ", run_engine([("L2a", 0), ("L2a", 100)], tick_to=101) == [("ㄹ", 2)])

    def run_mode(presses, window, mode):
        e = MultiTapEngine(table, window, True, window_mode=mode)
        for b, t in presses:
            e.tick(t)
            e.press(b, t)
        e.tick(presses[-1][1] + window + 1)
        return [(ev.token, ev.taps) for ev in e.drain()]

    trip = [("L1a", 0), ("L1a", 300), ("L1a", 600)]
    check("first-mode triple splits (펌웨어)", run_mode(trip, 450, "first") == [("ㅋ", 2), ("ㄱ", 1)], str(run_mode(trip, 450, "first")))
    check("rolling triple merges", run_mode(trip, 450, "last") == [("ㄲ", 3)], str(run_mode(trip, 450, "last")))
    check("rolling expiry", run_mode([("L1a", 0), ("L1a", 300), ("L1a", 800)], 450, "last") == [("ㅋ", 2), ("ㄱ", 1)])

    def compose(tokens):
        c = HangulComposer()
        for t in tokens:
            c.feed(t)
        return c.text()

    check("메카", compose(list("ㅁㅔㅋㅏ")) == "메카")
    check("국가 dokkaebi", compose(list("ㄱㅜㄱㄱㅏ")) == "국가")
    check("값", compose(list("ㄱㅏㅂㅅ")) == "값")
    check("의", compose(list("ㅇㅡㅣ")) == "의")
    check("space/enter", compose(list("ㄴㅏ") + ["SPACE"] + list("ㄱㅏ")) == "나 가")
    check("backspace jamo", compose(list("ㄱㅏㅂ") + ["BACKSPACE"]) == "가")
    check("backspace committed", compose(list("ㄱㅏ") + ["SPACE", "BACKSPACE"]) == "가")
    check("decompose", decompose_text("값 의") == ["ㄱ", "ㅏ", "ㅂ", "ㅅ", "SPACE", "ㅇ", "ㅡ", "ㅣ"])
    check("hid keys cover jamo", all(tok in DUBEOLSIK_KEY for tt in table.values() for tok in tt.values()
                                     if tok not in SPECIAL_TOKENS and tok != "."))

    # 기하: 좌우 판정·zone·버튼 ID·오프셋
    PL = _synthetic_left_hand()
    PR = _mirror_hand(PL)
    check("geom left", palm_winding(PL) > 0)
    check("geom right", palm_winding(PR) < 0)
    hands = assign_sides([(PL, "Left", 0.9), (PR, "Right", 0.9)], "model")
    check("assign L/R", set(hands) == {"L", "R"} and hands["L"].palm_ok and hands["R"].palm_ok)
    hands_bad = assign_sides([(PL, "Right", 0.9)], "model")
    check("palm gate on mismatch", "R" in hands_bad and not hands_bad["R"].palm_ok)
    hands_geom = assign_sides([(PL, "Right", 0.9)], "geom")
    check("geom mode overrides", "L" in hands_geom and hands_geom["L"].palm_ok)
    zl = {z.button for z in hands["L"].zones}
    check("zone ids", zl == {"L1a", "L1b", "L2a", "L2b", "L3a", "L3b", "L4", "L5"})
    za = next(z for z in hands["L"].zones if z.button == "L1a")
    zb = next(z for z in hands["L"].zones if z.button == "L1b")
    check("row a nearer fingertip", za.center[1] < zb.center[1])
    check("button loc ko", button_location_ko("L1b") == "왼손 검지 둘째 마디" and button_location_ko("R5") == "오른손 검지 밑마디")
    A, B = segment_points(PL, "index", "a")
    pt = zone_center(A, B, 0.7, -0.25)
    t_, s_ = local_coords(A, B, pt)
    check("local coords round trip", abs(t_ - 0.7) < 1e-4 and abs(s_ + 0.25) < 1e-4, f"{t_},{s_}")
    zo = make_zones("L", PL, {"L1a": (0.7, -0.25)})
    check("offset applied", np.allclose(next(z.center for z in zo if z.button == "L1a")[:2], pt[:2], atol=1e-3))
    check("button_finger_row", button_finger_row("L4") == ("pinky", "a") and button_finger_row("R3b") == ("ring", "b")
          and button_finger_row("L5") == ("index", "c") and button_finger_row("R5") == ("index", "c"))
    # 기능키 = 검지 밑마디(MCP–PIP 정중앙)
    zsL = {z.button: z.center for z in make_zones("L", PL)}
    midC = 0.5 * (PL[5] + PL[6])
    check("L5 at index base segment", np.allclose(zsL["L5"][:2], midC[:2], atol=1e-3), str(zsL["L5"]))
    check("L5 below L1b (손바닥 쪽)", zsL["L5"][1] > zsL["L1b"][1] > zsL["L1a"][1])
    zsR = {z.button: z.center for z in make_zones("R", PR)}
    midCR = 0.5 * (PR[5] + PR[6])
    check("R5 at index base (mirror)", np.allclose(zsR["R5"][:2], midCR[:2], atol=1e-3), str(zsR["R5"]))

    # 탭 검출기
    params = TapParams()

    def tap_sequence(frames, side="L"):
        det = TapDetector(params)
        P = PL if side == "L" else PR
        taps = []
        for i, (pos, dt) in enumerate(frames):
            Q = P.copy()
            Q[THUMB_TIP, :2] = pos
            obs = make_hand_obs(Q, "Left" if side == "L" else "Right", 0.9, "geom")
            for b in det.update(obs, i * dt):
                taps.append((b, i))
        return taps

    obsL = make_hand_obs(PL, "Left", 0.9, "geom")
    cz = {z.button: z.center[:2] for z in obsL.zones}
    s = obsL.scale
    far = np.array([120.0, 300.0])
    approach = [(far, 33), (cz["L1b"] + (0.9 * s, 0), 33), (cz["L1b"] + (0.4 * s, 0), 33)]
    hold = [(cz["L1b"] + (0.05 * s, 0), 33)] * 4
    lift_small = [(cz["L1b"] + (0.22 * s, 0), 33)] * 2
    leave = [(cz["L1b"] + (0.9 * s, 0), 33), (far, 33)]
    t1 = tap_sequence(approach + hold + leave)
    check("single tap", [b for b, _ in t1] == ["L1b"], str(t1))
    t2 = tap_sequence(approach + hold + lift_small + hold + leave)
    check("double tap with small lift", [b for b, _ in t2] == ["L1b", "L1b"], str(t2))
    t3 = tap_sequence(approach + hold + [(cz["L1b"] + (0.06 * s, 0.03 * s), 33)] * 6 + leave)
    check("jitter no extra tap", [b for b, _ in t3] == ["L1b"], str(t3))
    sweep = [(far, 33), (cz["L2b"] + (0.1 * s, 0), 33), (cz["L1b"] + (0.1 * s, 0), 33), (far, 33)]
    check("fast sweep no tap", tap_sequence(sweep) == [], str(tap_sequence(sweep)))

    # 3D 들어올림: 2D 위치는 그대로, world z 만 카메라 쪽으로 4cm → 3D 리바운드로 뗌 → 재접촉 = 2번째 탭
    PLw = ((PL - PL[0]) / 1000.0).astype(np.float32)          # m 단위 합성 world 좌표 (z=0 평면)
    obs_w = make_hand_obs(PL, "Left", 0.9, "geom", None, PLw)
    cw = obs_w.zones_w["L1b"]

    def seq3d(lift_z, use_depth=True):
        prm = TapParams(use_depth=use_depth)
        det = TapDetector(prm)
        frames = [(far, 0.0)] * 2 + [(cz["L1b"], 0.0)] * 4 + [(cz["L1b"], lift_z)] * 2 + [(cz["L1b"], 0.0)] * 4 + [(far, 0.0)] * 2
        taps = []
        for i, (pos, zlift) in enumerate(frames):
            Q = PL.copy()
            Q[THUMB_TIP, :2] = pos
            Qw = PLw.copy()
            Qw[THUMB_TIP] = cw + np.array([0, 0, zlift], dtype=np.float32) if np.allclose(pos, cz["L1b"]) else Qw[THUMB_TIP]
            o = make_hand_obs(Q, "Left", 0.9, "geom", None, Qw)
            taps += det.update(o, i * 33.0)
        return taps

    check("3D lift → double tap", seq3d(-0.04) == ["L1b", "L1b"], str(seq3d(-0.04)))
    check("3D small jitter → single", seq3d(-0.01) == ["L1b"], str(seq3d(-0.01)))
    check("2D-only misses depth lift", seq3d(-0.04, use_depth=False) == ["L1b"], str(seq3d(-0.04, use_depth=False)))

    # sticky: 연타 대기 중인 L1a 가 있으면 L1b 쪽으로 살짝 치우친 접촉도 L1a 로
    mid_pt = cz["L1a"] + 0.55 * (cz["L1b"] - cz["L1a"])

    def seq_sticky(sticky):
        det = TapDetector(TapParams())
        taps = []
        for i, pos in enumerate([far, far, mid_pt, mid_pt, mid_pt, far]):
            Q = PL.copy()
            Q[THUMB_TIP, :2] = pos
            taps += det.update(make_hand_obs(Q, "Left", 0.9, "geom"), i * 33.0, sticky=sticky)
        return taps

    check("sticky pending zone", seq_sticky("L1a") == ["L1a"] and seq_sticky(None) == ["L1b"], f"{seq_sticky('L1a')} {seq_sticky(None)}")

    # 종단: Pipeline.update 로 '메카' — ㅁ(L1b×2) ㅔ(R4) ㅋ(L1a×2) ㅏ(R2a)
    pl = _test_pipeline()
    obsR = make_hand_obs(PR, "Right", 0.9, "geom")
    czR = {z.button: z.center[:2] for z in obsR.zones}
    farR = np.array([520.0, 300.0])
    script = []
    for btn, n in [("L1b", 2), ("R4", 1), ("L1a", 2), ("R2a", 1)]:
        side = btn[0]
        c = cz[btn] if side == "L" else czR[btn]
        f = far if side == "L" else farR
        script += [(side, f)] * 3
        for _ in range(n):
            script += [(side, c + (0.05 * s, 0))] * 3 + [(side, c + (0.25 * s, 0))] * 2
        script += [(side, f)] * 3
    t = 0.0
    for side, pos in script:
        Q = (PL if side == "L" else PR).copy()
        Q[THUMB_TIP, :2] = pos
        obs = make_hand_obs(Q, "Left" if side == "L" else "Right", 0.9, "geom")
        pl.update({side: obs}, t)
        t += 33.0
    pl.update({}, t + 1000)
    check("end-to-end 메카 (pipeline)", pl.composer.text() == "메카", repr(pl.composer.text()))
    check("events/snapshot", pl.n_events == 4 and pl.events[-1] == "ㅏ" and pl.events[0] == "ㅁ×2", str(list(pl.events)))
    pl.post({"cmd": "backspace"})
    pl.post({"cmd": "set_params", "params": {"window": 380, "press": 0.35, "release_margin": 0.2}})
    pl.post({"cmd": "set_hand_mode", "mode": "geom"})
    pl._handle_cmds(t)
    check("cmd backspace", pl.composer.text() == "메ㅋ", repr(pl.composer.text()))
    check("cmd params", pl.engine.window == 380 and abs(pl.params.press - 0.35) < 1e-9 and abs(pl.params.release - 0.55) < 1e-9 and pl.hand_mode == "geom")
    prof = pl.export_profile()
    pl2 = _test_pipeline()
    pl2.apply_profile(json.loads(json.dumps(prof)))
    check("profile round trip", pl2.engine.window == 380 and abs(pl2.params.press - 0.35) < 1e-9 and pl2.hand_mode == "geom")
    # 카메라 기억/우선순위
    pl.camera_index = 1
    pl3 = _test_pipeline()
    pl3.apply_profile(json.loads(json.dumps(pl.export_profile())))
    check("profile camera", pl3.camera_index == 1)

    class _A:  # argparse 흉내
        video = None
        camera = None
        camera_name = None

    a = _A()
    check("camera: profile wins over default", resolve_initial_camera(a, pl3, quiet=True) == 1 and a.camera == 1)
    a2 = _A()
    a2.camera = 2
    check("camera: --camera wins over profile", resolve_initial_camera(a2, pl3, quiet=True) == 2 and pl3.camera_index == 2)
    a3 = _A()
    pl4 = _test_pipeline()
    idx = resolve_initial_camera(a3, pl4, quiet=True)
    expected = DEFAULT_CAMERA_INDEX if DEFAULT_CAMERA_INDEX is not None else 0
    check("camera: default = DEFAULT_CAMERA_INDEX", idx == expected or platform.system() == "Darwin", str(idx))
    pl3.post({"cmd": "set_camera", "index": 3})
    pl3.post({"cmd": "probe_cameras"})
    pl3._handle_cmds(0.0)
    check("cmd set_camera/probe", pl3.camera_request == 3 and pl3.probe_request is True)
    snap = pl3._build_snapshot({}, 0.0, 0.0, None, "", None, "")
    check("snapshot camera", snap["camera"]["index"] == 2 and "list" in snap["camera"])
    guide = TargetGuide("메카", table)
    check("guide next", guide.next_step("메")[1] == ("ㅋ", "L1a", 2) and guide.next_step("메카")[1] is None
          and guide.next_step("멬")[1] == ("ㅏ", "R2a", 1) and guide.next_step("매")[2] is True)

    # 캘리브레이션 결정 함수
    p_, r_ = decide_threshold([0.05, 0.08, 0.1, 0.12], [0.7, 0.8, 0.9, 1.1])
    check("decide_threshold", 0.15 <= p_ <= 0.5 and r_ > p_ and p_ >= 0.12 + 0.06 - 1e-9, f"{p_},{r_}")
    w_, info = decide_window([150, 180, 200, 220, 170], [450, 500, 600, 520, 480], 450)
    check("decide_window separable", 220 < w_ < 450 and info.get("errors") == 0, f"{w_} {info}")
    w2, _ = decide_window([150, 200, 300, 420], [350, 400, 500, 600], 450)
    check("decide_window overlap", 200 <= w2 <= 900, str(w2))
    w3, _ = decide_window([150, 200], [], 450)
    check("decide_window multitap only", 200 <= w3 <= 900 and w3 > 200, str(w3))

    # 캘리브레이션 세션 (합성 손)
    pl = _test_pipeline()
    pl.hand_mode = "model"
    pl.calib = CalibrationSession(pl, "all")
    n_steps = len(pl.calib.steps)
    check("calib steps", n_steps == 1 + 16 + 1 + 2 and pl.calib.steps[1].button == "L1a", str(n_steps))
    # 1) 손 확인: 라벨이 기하와 반대인 손 → 반전
    t = 0.0
    for _ in range(70):
        hands = assign_sides([(PL, "Right", 0.9), (PR, "Left", 0.9)], pl.hand_mode, pl.zone_offsets)
        pl.update(hands, t)
        t += 33.0
    check("calib hands → swap", pl.hand_mode == "model-swap" and pl.calib.idx == 1, f"{pl.hand_mode} idx={pl.calib.idx}")
    # 2) 스윗스팟 L1a: 엄지를 (t=0.6, s=0.2) 위치에 유지
    A, B = segment_points(PL, "index", "a")
    target_pt = zone_center(A, B, 0.6, 0.2)
    for _ in range(60):
        Q = PL.copy()
        Q[THUMB_TIP] = target_pt
        hands = assign_sides([(Q, "Right", 0.9)], pl.hand_mode, pl.zone_offsets)   # model-swap → 'L'
        pl.update(hands, t)
        t += 33.0
    off = pl.zone_offsets.get("L1a")
    check("calib zone offset", off is not None and abs(off[0] - 0.6) < 0.02 and abs(off[1] - 0.2) < 0.02 and pl.calib.idx == 2, str(off))
    for _ in range(15):   # 나머지 zone 단계 건너뛰기
        pl.calib.skip()
    check("calib at hover", pl.calib.step is not None and pl.calib.step.kind == "hover", str(pl.calib.step))
    # 3) 비접촉: 엄지 멀리
    for _ in range(90):
        Q = PL.copy()
        Q[THUMB_TIP, :2] = far
        hands = assign_sides([(Q, "Right", 0.9)], pl.hand_mode, pl.zone_offsets)
        pl.update(hands, t)
        t += 33.0
    check("calib threshold applied", pl.calib.step is not None and pl.calib.step.kind == "multitap" and 0.15 <= pl.params.press <= 0.5
          and pl.params.release > pl.params.press, f"{pl.calib.step} {pl.params.press} {pl.params.release}")
    # 4) 연타/별개 간격: 탭 이벤트를 직접 주입
    def inject(times):
        nonlocal t
        for tm in times:
            pl.calib.on_frame({}, {"L": ["L1a"]}, tm, pl.detectors)
        t = times[-1] + 100
    base = t
    inject([base + i * 2000 + g for i in range(5) for g in (0, 190)])
    check("calib multitap collected", pl.calib.step is not None and pl.calib.step.kind == "separate" and len(pl.calib.multitap_gaps) == 5,
          f"{pl.calib.step} {pl.calib.multitap_gaps}")
    base = t
    inject([base + i * 2500 + g for i in range(5) for g in (0, 520)])
    check("calib window decided", pl.calib.finished and 190 < pl.engine.window < 520, f"{pl.calib.finished} {pl.engine.window}")
    check("calib summary", any("연타 윈도우" in x for x in pl.calib.summary) and pl.calib.view()["active"] is False)
    # 취소 경로
    pl.calib = CalibrationSession(pl, "window")
    pl.calib.cancel()
    check("calib cancel", not pl.calib.active and not pl.calib.finished)
    # HTML/서버 정적 점검
    check("page html", "<title>Keyboard In My Hand" in PAGE_HTML and "/stream" in PAGE_HTML and "calib_start" in PAGE_HTML)
    print(f"selftest: {passed}/{passed + failed} passed")
    return 0 if failed == 0 else 1


def install_deps() -> int:
    """--install: 실행 중인 파이썬에 requirements.txt 를 설치한다. pip 모듈이 없으면 ensurepip 으로 먼저 만든다."""
    import subprocess
    py = sys.executable
    req = HERE / "requirements.txt"
    if not req.is_file():
        print(f"[error] {req} 가 없습니다", file=sys.stderr)
        return 2
    if platform.system() == "Darwin" and sys.version_info >= (3, 13):
        print(f"[error] macOS 에서는 Python 3.12 가 필요합니다 (현재 {sys.version.split()[0]}: mediapipe 0.10.21 휠이 cp312 까지만 있고, "
              "그 이후 macOS 빌드는 크래시)." + MAC_MEDIAPIPE_HINT.format(ver="1.0.x"), file=sys.stderr)
        return 2
    if subprocess.call([py, "-m", "pip", "--version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) != 0:
        print("[info] pip 모듈이 없어 ensurepip 으로 설치합니다…")
        if subprocess.call([py, "-m", "ensurepip", "--upgrade"]) != 0:
            print("[error] ensurepip 실패 — 가상환경을 만들어 다시 시도하세요: "
                  f"\"{py}\" -m venv .venv && source .venv/bin/activate && python kih_xr_demo.py --install", file=sys.stderr)
            return 2
    cmd = [py, "-m", "pip", "install", "-r", str(req)]
    print("[info] 실행:", " ".join(f'"{c}"' if " " in c else c for c in cmd))
    rc = subprocess.call(cmd)
    if rc != 0:
        print("[warn] 설치 실패. 'externally-managed-environment' 오류라면 가상환경으로: "
              f"\"{py}\" -m venv .venv && source .venv/bin/activate && python kih_xr_demo.py --install", file=sys.stderr)
        return rc
    print(f"[done] 설치 완료 — 이제 실행: \"{py}\" {Path(__file__).name}")
    return 0


MAC_MEDIAPIPE_HINT = """
  macOS 에서 mediapipe {ver} 는 CPU 그래프인데도 Metal(GPU) 헬퍼를 초기화하다
  'graph_service.h Check failed: service_ Service is unavailable' 로 프로세스가 abort 됩니다 (0.10.30+ / 1.0.x 의 py3-none 빌드).
  검증된 조합: Python 3.12 + mediapipe==0.10.21 (cp312 universal2 휠)
      brew install python@3.12
      /opt/homebrew/opt/python@3.12/bin/python3.12 -m venv .venv && source .venv/bin/activate
      python kih_xr_demo.py --install        # requirements.txt 가 macOS 에서는 mediapipe==0.10.21 을 고른다
  (새 버전에서 고쳐졌는지 시험하려면 --allow-new-mediapipe)
"""


def _version_tuple(v: str) -> Tuple[int, ...]:
    out = []
    for part in v.split(".")[:3]:
        digits = "".join(ch for ch in part if ch.isdigit())
        out.append(int(digits) if digits else 0)
    return tuple(out)


def check_mediapipe_platform(allow_new: bool = False) -> None:
    if platform.system() != "Darwin" or allow_new:
        return
    try:
        import mediapipe as mp
        ver = getattr(mp, "__version__", "0")
    except ImportError:
        return
    if _version_tuple(ver) >= (0, 10, 30):
        print(f"[error] macOS + mediapipe {ver}: 알려진 크래시 조합입니다." + MAC_MEDIAPIPE_HINT.format(ver=ver), file=sys.stderr)
        sys.exit(2)


def maybe_reexec_into_venv(argv: List[str]) -> None:
    """실행한 파이썬에 의존성이 없는데 스크립트 옆에 .venv 가 있으면, 그 파이썬으로 자신을 다시 실행한다.
    VS Code ▶ 버튼이 Homebrew/시스템 파이썬을 골라도 venv 로 돌게 하기 위함. KIH_NO_REEXEC=1 로 끌 수 있다."""
    import importlib.util
    if os.environ.get("KIH_NO_REEXEC") or os.environ.get("KIH_REEXEC"):
        return
    missing = [m for m in ("cv2", "mediapipe", "numpy") if importlib.util.find_spec(m) is None]
    if not missing:
        return
    here = Path(__file__).resolve().parent
    cands = [here / ".venv" / "bin" / "python", here / ".venv" / "Scripts" / "python.exe",
             here / "venv" / "bin" / "python", here / "venv" / "Scripts" / "python.exe"]
    # 주의: venv 의 python 은 기반 인터프리터의 심링크라 바이너리 경로로 비교하면 같아 보인다 → sys.prefix(환경 디렉터리)로 비교
    my_prefix = Path(sys.prefix).resolve()
    for vp in cands:
        if vp.is_file() and vp.parent.parent.resolve() != my_prefix:
            print(f"[info] 현재 파이썬({sys.executable})에 {', '.join(missing)} 없음 → {vp} 로 다시 실행합니다")
            os.environ["KIH_REEXEC"] = "1"
            try:
                os.execv(str(vp), [str(vp), str(Path(__file__).resolve())] + list(argv))
            except OSError as e:
                print(f"[warn] 재실행 실패: {e}", file=sys.stderr)
            return


def check_deps() -> None:
    """cv2/mediapipe/PIL 이 없으면 트레이스백 대신 설치 명령을 안내한다 (실행 중인 인터프리터 기준)."""
    missing = []
    for mod, pkg in (("numpy", "numpy"), ("cv2", "opencv-python"), ("mediapipe", "mediapipe"), ("PIL", "pillow")):
        try:
            __import__(mod)
        except ImportError:
            missing.append(pkg)
    if not missing:
        return
    py = sys.executable
    req = HERE / "requirements.txt"
    print(f"[error] 필요한 패키지가 없습니다: {', '.join(missing)}\n"
          f"        실행 중인 파이썬: {py}\n"
          f"        설치:  \"{py}\" {Path(__file__).name} --install     (= \"{py}\" -m pip install -r \"{req}\")\n"
          f"        (pip이 externally-managed 오류를 내면 가상환경: \"{py}\" -m venv .venv && source .venv/bin/activate "
          f"&& pip install -r requirements.txt)\n"
          f"        VS Code ▶ 버튼이 다른 파이썬을 쓰면: ⌘⇧P → 'Python: Select Interpreter' → .venv 선택 "
          f"(스크립트 옆에 .venv 가 있으면 자동으로 그쪽으로 재실행됩니다)\n"
          f"        macOS: 첫 실행 때 터미널 앱의 카메라 접근 허용이 필요합니다 (시스템 설정 → 개인정보 보호 → 카메라).",
          file=sys.stderr)
    sys.exit(2)


def main(argv=None) -> int:
    try:
        sys.stdout.reconfigure(line_buffering=True)
    except Exception:  # noqa: BLE001
        pass
    maybe_reexec_into_venv(list(sys.argv[1:] if argv is None else argv))
    ap = argparse.ArgumentParser(description="Keyboard In My Hand — 장갑 없는 XR(vision) 시연 (웹 앱 / OpenCV 창)",
                                 formatter_class=argparse.RawDescriptionHelpFormatter, epilog=JOINT_TABLE)
    ap.add_argument("--camera", type=int, default=None,
                    help=f"웹캠 번호 (생략 시: 프로필에 기억된 카메라 → 기본값 {DEFAULT_CAMERA_INDEX})")
    ap.add_argument("--camera-name", help="장치 이름으로 카메라 선택 (macOS, PyObjC 필요; 예: FaceTime)")
    ap.add_argument("--video", help="카메라 대신 동영상 파일")
    ap.add_argument("--loop", action="store_true", help="--video 반복 재생")
    ap.add_argument("--width", type=int, default=1280)
    ap.add_argument("--height", type=int, default=720)
    ap.add_argument("--display-width", type=int, default=960, help="브라우저 스트림 가로 픽셀 (기본 960)")
    ap.add_argument("--jpeg-quality", type=int, default=80)
    ap.add_argument("--host", default="127.0.0.1", help="웹 앱 바인드 주소 (다른 기기에서 보려면 0.0.0.0)")
    ap.add_argument("--port", type=int, default=7890)
    ap.add_argument("--no-browser", action="store_true", help="브라우저 자동 열기 끄기")
    ap.add_argument("--ui", choices=["auto", "native", "browser"], default="auto",
                    help="auto=pywebview 있으면 네이티브 창, 없으면 브라우저 · native · browser")
    ap.add_argument("--nogui", action="store_true", help="웹 앱 대신 OpenCV 창")
    ap.add_argument("--no-window", action="store_true", help="창 없이 처리 (--nogui 와 함께; --record/--log 용)")
    ap.add_argument("--model", help="hand_landmarker.task 경로 (없으면 자동 다운로드)")
    ap.add_argument("--mapping", help="mapping.json 경로 (기본: experiments/mapping.json → 내장 사본)")
    ap.add_argument("--profile", default="default", help="캘리브레이션 프로필 이름 (profiles/<이름>.json)")
    ap.add_argument("--no-autosave", action="store_true", help="캘리브레이션 완료 시 프로필 자동 저장 끄기")
    ap.add_argument("--window", type=float, default=450.0, help="연타 윈도우 ms (펌웨어 기본 300; 카메라는 450 권장)")
    ap.add_argument("--no-early-commit", action="store_true", help="다른 버튼 눌림 시 즉시 확정 끄기")
    ap.add_argument("--debounce", type=float, default=30.0, help="디바운스 ms (펌웨어 30)")
    ap.add_argument("--press", type=float, default=TapParams.press, help="탭 판정 반경 (손 스케일 배수)")
    ap.add_argument("--release", type=float, default=TapParams.release, help="해제 반경")
    ap.add_argument("--rebound", type=float, default=TapParams.rebound, help="같은 자리 연타 인식용 상대 해제 거리")
    ap.add_argument("--dwell-ms", type=float, default=TapParams.dwell_ms, help="탭 확정까지 체류 시간 ms")
    ap.add_argument("--max-speed", type=float, default=TapParams.max_speed, help="엄지 속도 상한 (스케일/초)")
    ap.add_argument("--z-weight", type=float, default=TapParams.z_weight, help="거리 계산의 z 가중 (0=2D)")
    ap.add_argument("--rebound3", type=float, default=TapParams.rebound3, help="3D(world) 들어올림 해제 거리 (손 스케일 배수)")
    ap.add_argument("--depth", choices=["world", "none"], default="world", help="들어올림 감지에 3D world landmark 사용(world) / 2D만(none)")
    ap.add_argument("--window-mode", choices=["last", "first"], default="last",
                    help="연타 윈도우 기준: last=마지막 탭부터(롤링, 시연 기본) · first=첫 탭부터(펌웨어 동일)")
    ap.add_argument("--hand-mode", choices=["model", "model-swap", "geom"], default="model",
                    help="좌우 판정: model=MediaPipe 라벨(+손바닥 게이트) · model-swap=라벨 반전 · geom=기하만")
    ap.add_argument("--no-palm-gate", action="store_true", help="손바닥 방향 게이트 끄기")
    ap.add_argument("--det-conf", type=float, default=0.5)
    ap.add_argument("--track-conf", type=float, default=0.5)
    ap.add_argument("--target", help="안내 모드: 입력할 목표 문장 (예: '메카')")
    ap.add_argument("--hid", action="store_true", help="확정 자모를 OS 키 입력으로 전송 (pynput)")
    ap.add_argument("--record", help="(--nogui) 렌더링 결과를 mp4로 저장")
    ap.add_argument("--log", help="확정 이벤트 JSONL 로그 경로")
    ap.add_argument("--no-mirror", action="store_true", help="거울 표시 끄기")
    ap.add_argument("--max-frames", type=int, default=0, help="N 프레임 후 종료 (테스트용)")
    ap.add_argument("--font", help="한글 TTF/TTC 경로")
    ap.add_argument("--debug", action="store_true", help="디버그 HUD 켜고 시작")
    ap.add_argument("--verbose", action="store_true", help="확정 이벤트를 터미널에도 출력")
    ap.add_argument("--selftest", action="store_true", help="로직 셀프테스트 후 종료")
    ap.add_argument("--install", action="store_true", help="이 파이썬에 requirements.txt 설치 (pip 없으면 ensurepip)")
    ap.add_argument("--list-cameras", action="store_true", help="열리는 카메라 번호 확인 후 종료")
    ap.add_argument("--allow-new-mediapipe", action="store_true", help="macOS 에서 mediapipe 0.10.30+/1.0.x 차단 해제 (크래시 시험용)")
    args = ap.parse_args(argv)
    if args.install:
        return install_deps()
    if np is None:
        check_deps()
    if args.selftest:
        return selftest()
    check_deps()
    check_mediapipe_platform(args.allow_new_mediapipe)
    if args.list_cameras:
        return list_cameras()
    if args.nogui or args.no_window:
        return run_cli(args)
    return run_gui(args)


if __name__ == "__main__":
    sys.exit(main())
