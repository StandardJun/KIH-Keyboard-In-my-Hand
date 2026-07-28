#!/usr/bin/env python3
"""RESULTS.md에 실린 수치를 원자료에서 다시 계산해 대조한다.

    python analysis/verify_results.py

문서의 숫자와 데이터가 어긋나면 종료 코드 1. 표준 라이브러리만 쓴다.
"""
import csv
import math
import sys
from collections import defaultdict
from pathlib import Path

CSV_PATH = Path(__file__).resolve().parent.parent / "experiments" / "logs" / "speed_vs_tv_all.csv"

# RESULTS.md가 주장하는 값. 문서를 고치면 여기도 함께 고쳐야 한다.
CLAIMS = {
    "KIH":    {"first": 2.3, "last": 10.6, "a": 1.55, "b": 0.602, "r2": 0.636,
               "err_col": "msd_error_pct", "err_first": 17.2, "err_last": 4.1},
    "TV_OSK": {"first": 5.6, "last": 7.5,  "a": 5.80, "b": 0.079, "r2": 0.142,
               "err_col": "correction_pct", "err_first": None, "err_last": None},
}
TOL = 0.05          # 표시 자릿수까지만 맞으면 통과
TRIALS = 15


def load(path=CSV_PATH):
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def power_law(points):
    """개별 시행 (n, wpm) 점들에 WPM = a·n^b 를 로그-로그 선형회귀로 적합."""
    xs = [math.log(n) for n, w in points]
    ys = [math.log(w) for n, w in points]
    k = len(xs)
    mx, my = sum(xs) / k, sum(ys) / k
    b = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sum((x - mx) ** 2 for x in xs)
    a = math.exp(my - b * mx)
    ss_res = sum((y - (math.log(a) + b * x)) ** 2 for x, y in zip(xs, ys))
    ss_tot = sum((y - my) ** 2 for y in ys)
    return a, b, 1 - ss_res / ss_tot


def mean_by_trial(rows, column):
    acc = defaultdict(list)
    for r in rows:
        raw = r[column].strip()
        if raw:
            acc[int(r["trial"])].append(float(raw))
    return {t: sum(v) / len(v) for t, v in acc.items()}


def main():
    if not CSV_PATH.exists():
        print(f"원자료를 찾을 수 없습니다: {CSV_PATH}")
        return 1

    rows = load()
    failures = []

    def check(label, got, want):
        if want is None:
            return
        ok = abs(got - want) <= TOL
        print(f"  {label:34} {got:8.3f}   문서 {want:7.3f}   {'OK' if ok else '불일치'}")
        if not ok:
            failures.append(f"{label}: 계산 {got:.3f} vs 문서 {want:.3f}")

    print(f"원자료: {CSV_PATH.name}  ({len(rows)}행)\n")

    for device, claim in CLAIMS.items():
        d = [r for r in rows if r["device"] == device]
        print(f"[{device}]  {len(d)}시행")

        wpm = mean_by_trial(d, "wpm")
        if sorted(wpm) != list(range(1, TRIALS + 1)):
            failures.append(f"{device}: 시행 번호가 1~{TRIALS}이 아님")
        check("1회차 평균 WPM", wpm[1], claim["first"])
        check(f"{TRIALS}회차 평균 WPM", wpm[TRIALS], claim["last"])

        pts = [(int(r["trial"]), float(r["wpm"])) for r in d if float(r["wpm"]) > 0]
        a, b, r2 = power_law(pts)
        check("멱법칙 계수 a", a, claim["a"])
        check("학습 지수 b", b, claim["b"])
        check("R^2", r2, claim["r2"])

        err = mean_by_trial(d, claim["err_col"])
        if err:
            check(f"1회차 {claim['err_col']}", err[1], claim["err_first"])
            check(f"{TRIALS}회차 {claim['err_col']}", err[TRIALS], claim["err_last"])
        print()

    if failures:
        print("불일치 %d건:" % len(failures))
        for f in failures:
            print("  -", f)
        return 1
    print("RESULTS.md의 모든 수치가 원자료에서 재현됩니다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
