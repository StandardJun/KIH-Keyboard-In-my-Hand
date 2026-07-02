#!/usr/bin/env python3
"""연타 판정 윈도우 개인화 캘리브레이션 도구 (keyboard_glove_fixed 펌웨어 전용).

사용자가 파생 자모가 골고루 든 문장을 자연스러운 속도로 타이핑하면,
펌웨어가 시리얼로 보내주는 버튼 탭 타임스탬프에서 '연타 간격'과 '일반 타건 간격'의
분포를 분리해 최적 윈도우(ms)를 추천·설정·저장(EEPROM)한다.

필요: pip install pyserial
사용: python calibrate_window.py [--port COM3]   (포트 생략 시 자동 탐색)

절차:
 1) 도구 실행 → 글러브 연결 확인
 2) 메모장 등 아무 텍스트 창에 포커스를 두고, 안내 문장을 자연 속도로 2회 타이핑
 3) 5초간 입력이 없으면 자동 분석 → 추천 윈도우 확인 후 y 입력 → 저장 완료
"""
import argparse
import statistics as st
import sys
import time

try:
    import serial
    from serial.tools import list_ports
except ImportError:
    sys.exit("pyserial이 필요합니다: pip install pyserial")

SENTENCE = "가까운 카페에 다녀와서 따뜻한 차와 바쁜 친구의 짜장밥을 싸자"
IDLE_END_S = 5.0      # 이 시간 동안 입력 없으면 수집 종료
MIN_EVENTS = 40


def find_port():
    for p in list_ports.comports():
        desc = f"{p.description} {p.manufacturer or ''}".lower()
        if "leonardo" in desc or "arduino" in desc or (p.vid == 0x2341):
            return p.device
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port")
    args = ap.parse_args()
    port = args.port or find_port()
    if not port:
        sys.exit("글러브(Leonardo) 포트를 찾지 못했습니다. --port COM3 형식으로 지정하세요.")

    ser = serial.Serial(port, 115200, timeout=0.2)
    time.sleep(2)  # 보드 리셋 대기
    ser.reset_input_buffer()
    ser.write(b"?\n")
    time.sleep(0.3)
    print("현재 설정:", ser.read_all().decode(errors="ignore").strip() or "(응답 없음 — 수정판 펌웨어인지 확인)")

    print("\n== 캘리브레이션 ==")
    print("아래 문장을 메모장 등 다른 창에 포커스를 두고 자연스러운 속도로 2회 타이핑하세요.")
    print(f"\n  「{SENTENCE}」\n")
    print("(입력이 5초간 없으면 자동으로 분석합니다)\n")
    ser.write(b"C1\n")

    events = []  # (button_id, ms)
    last_rx = time.time()
    try:
        while True:
            line = ser.readline().decode(errors="ignore").strip()
            if line and " " in line and line[0] in "LR":
                bid, ms = line.split()
                events.append((bid, int(ms)))
                last_rx = time.time()
                print(f"\r탭 수집: {len(events)}", end="", flush=True)
            if events and (time.time() - last_rx > IDLE_END_S):
                break
    except KeyboardInterrupt:
        pass
    ser.write(b"C0\n")
    print(f"\n수집 완료: {len(events)}탭")
    if len(events) < MIN_EVENTS:
        sys.exit(f"탭 수가 너무 적습니다(<{MIN_EVENTS}). 문장을 2회 이상 입력해 주세요.")

    # 같은 버튼 연속 탭 간격만 추출
    gaps = [b_ms - a_ms for (a, a_ms), (b, b_ms) in zip(events, events[1:])
            if a == b and 0 < b_ms - a_ms < 1500]
    if len(gaps) < 8:
        sys.exit("같은 버튼 연속 탭 표본이 부족합니다. 문장을 그대로(격음·경음 포함) 다시 입력해 주세요.")

    # 정렬 후 가장 큰 상대 간극에서 '연타 vs 일반 반복' 클러스터 분리
    g = sorted(gaps)
    split = None
    best_ratio = 1.6  # 최소 분리 비율
    for i in range(len(g) - 1):
        if g[i] >= 60 and g[i + 1] / g[i] > best_ratio:
            best_ratio = g[i + 1] / g[i]
            split = (g[i] + g[i + 1]) / 2
    intra = [x for x in g if split is None or x < split]
    p50, p95 = st.median(intra), sorted(intra)[max(0, int(len(intra) * 0.95) - 1)]
    rec = int(min(600, max(120, (split if split else p95 * 1.25))))

    print(f"\n연타 간격: 중앙값 {p50:.0f}ms / 95백분위 {p95:.0f}ms / 표본 {len(intra)}개")
    if split:
        print(f"클러스터 분리점: {split:.0f}ms (연타 ↔ 일반 반복)")
    print(f"→ 추천 윈도우: {rec}ms  (현재 대비 단타 확정 지연 {rec}ms)")

    if input("\n이 값으로 설정·저장할까요? [y/N] ").strip().lower() == "y":
        ser.write(f"W{rec}\n".encode()); time.sleep(0.3)
        print(ser.read_all().decode(errors="ignore").strip())
        ser.write(b"S\n"); time.sleep(0.3)
        print(ser.read_all().decode(errors="ignore").strip())
        print("완료 — 전원을 다시 꽂아도 유지됩니다.")
    else:
        print("설정하지 않았습니다.")
    ser.close()


if __name__ == "__main__":
    main()
