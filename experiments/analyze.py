#!/usr/bin/env python3
"""Keyboard In My Hand — 실험 로그 분석기.

사용법:
  python analyze.py transcribe   # 실험 B/C: 학습곡선(CPM·오류율) 그래프
  python analyze.py tap          # 실험 A: 버튼 RT 매트릭스 + 매핑 최적성
  python analyze.py sus scores.csv  # SUS 채점 (행=응답자, 열=문항1~10)

입력: logs/*.jsonl (logger.py 산출물), mapping.json, jamo_freq.json
출력: figures/*.png (보고서 삽입용, 300dpi) + 콘솔 요약
"""
import json
import math
import random
import statistics as st
import sys
from collections import defaultdict
from pathlib import Path

import matplotlib
import matplotlib.pyplot as plt
from matplotlib import font_manager

HERE = Path(__file__).resolve().parent
LOG_DIR = HERE / "logs"
FIG_DIR = HERE / "figures"

# ---- 스타일: 보고서(흑백 인쇄 가능성)용 — 단일 색조, 절제된 그리드 ----
ACCENT = "#2f5f8f"
matplotlib.rcParams.update({
    "figure.dpi": 110, "savefig.dpi": 300, "font.size": 11,
    "axes.spines.top": False, "axes.spines.right": False,
    "axes.grid": True, "grid.alpha": 0.25, "grid.linewidth": 0.6,
})
for name in ("Malgun Gothic", "NanumGothic", "AppleGothic", "Noto Sans CJK KR"):
    if any(name.lower() in f.name.lower() for f in font_manager.fontManager.ttflist):
        matplotlib.rcParams["font.family"] = name
        break
matplotlib.rcParams["axes.unicode_minus"] = False

# ---- 한글 자모 분해 (두벌식 키스트로크 단위) ----
CHO = "ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ"
JUNG = "ㅏㅐㅑㅒㅓㅔㅕㅖㅗㅘㅙㅚㅛㅜㅝㅞㅟㅠㅡㅢㅣ"
JONG = " ㄱㄲㄳㄴㄵㄶㄷㄹㄺㄻㄼㄽㄾㄿㅀㅁㅂㅄㅅㅆㅇㅈㅊㅋㅌㅍㅎ"
SPLIT_VOWEL = {"ㅘ": "ㅗㅏ", "ㅙ": "ㅗㅐ", "ㅚ": "ㅗㅣ", "ㅝ": "ㅜㅓ",
               "ㅞ": "ㅜㅔ", "ㅟ": "ㅜㅣ", "ㅢ": "ㅡㅣ"}
SPLIT_FINAL = {"ㄳ": "ㄱㅅ", "ㄵ": "ㄴㅈ", "ㄶ": "ㄴㅎ", "ㄺ": "ㄹㄱ", "ㄻ": "ㄹㅁ",
               "ㄼ": "ㄹㅂ", "ㄽ": "ㄹㅅ", "ㄾ": "ㄹㅌ", "ㄿ": "ㄹㅍ", "ㅀ": "ㄹㅎ", "ㅄ": "ㅂㅅ"}


def to_jamo(text):
    """음절 → 키스트로크 단위 자모열. 쌍자음은 단일, 겹모음·겹받침은 분해."""
    out = []
    for ch in text:
        code = ord(ch) - 0xAC00
        if 0 <= code < 11172:
            cho, jung, jong = CHO[code // 588], JUNG[(code % 588) // 28], JONG[code % 28]
            out.append(cho)
            out.extend(SPLIT_VOWEL.get(jung, jung))
            if jong != " ":
                out.extend(SPLIT_FINAL.get(jong, jong))
        elif ch != " ":
            out.append(ch)
    return out


def msd(a, b):
    """최소 문자열 거리 (Levenshtein)."""
    m, n = len(a), len(b)
    prev = list(range(n + 1))
    for i in range(1, m + 1):
        cur = [i] + [0] * n
        for j in range(1, n + 1):
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (a[i - 1] != b[j - 1]))
        prev = cur
    return prev[n]


def load_logs(mode):
    trials = []
    for p in sorted(LOG_DIR.glob(f"*_{mode}_*.jsonl")):
        for line in p.read_text(encoding="utf-8").splitlines():
            if line.strip():
                trials.append(json.loads(line))
    if not trials:
        sys.exit(f"logs/ 에 {mode} 로그가 없습니다.")
    return trials


# ================= 실험 B/C: 전사 분석 =================
def analyze_transcribe():
    trials = load_logs("transcribe")
    by_ps = defaultdict(list)  # (participant, session) -> trials
    for t in trials:
        by_ps[(t["participant"], t["session"])].append(t)

    rows = []
    for (p, s), ts in sorted(by_ps.items()):
        syl = sum(len(t["typed"].replace(" ", "")) for t in ts)
        jam = sum(len(to_jamo(t["typed"])) for t in ts)
        dur_min = sum(t["duration_s"] for t in ts) / 60
        errs = [msd(to_jamo(t["target"]), to_jamo(t["typed"])) /
                max(len(to_jamo(t["target"])), len(to_jamo(t["typed"])), 1) for t in ts]
        rows.append({"participant": p, "session": s, "n": len(ts),
                     "cpm_syl": syl / dur_min if dur_min else 0,
                     "jpm": jam / dur_min if dur_min else 0,
                     "err": st.mean(errs) * 100})
        print(f"{p} {s}: 문장 {len(ts)}개, {syl / dur_min:5.1f} 음절/분, "
              f"{jam / dur_min:5.1f} 자모/분, 오류율 {st.mean(errs) * 100:4.1f}%")

    FIG_DIR.mkdir(exist_ok=True)
    # 학습곡선: 참가자별 라인 + 평균, 세션 번호는 ID의 숫자에서 추출
    fig, axes = plt.subplots(1, 2, figsize=(10, 4))
    parts = sorted({r["participant"] for r in rows})
    for p in parts:
        rs = [r for r in rows if r["participant"] == p]
        xs = list(range(1, len(rs) + 1))
        axes[0].plot(xs, [r["cpm_syl"] for r in rs], marker="o", ms=5, lw=2,
                     alpha=0.85, label=p)
        axes[1].plot(xs, [r["err"] for r in rs], marker="o", ms=5, lw=2, alpha=0.85)
    axes[0].set(xlabel="세션", ylabel="입력 속도 (음절/분)", title="학습곡선 — 속도")
    axes[1].set(xlabel="세션", ylabel="오류율 (%)", title="학습곡선 — 오류율")
    for ax in axes:
        ax.xaxis.set_major_locator(matplotlib.ticker.MaxNLocator(integer=True))
    axes[0].legend(fontsize=9, frameon=False)

    # power law 피팅 (전체 평균, 세션 2개 이상일 때)
    max_s = max(len([r for r in rows if r["participant"] == p]) for p in parts)
    if max_s >= 3:
        mean_by_session = []
        for i in range(max_s):
            vals = [rs[i]["cpm_syl"] for p in parts
                    for rs in [[r for r in rows if r["participant"] == p]] if len(rs) > i]
            mean_by_session.append(st.mean(vals))
        lx = [math.log(i + 1) for i in range(max_s)]
        ly = [math.log(v) for v in mean_by_session]
        n = len(lx)
        b = (n * sum(x * y for x, y in zip(lx, ly)) - sum(lx) * sum(ly)) / \
            (n * sum(x * x for x in lx) - sum(lx) ** 2)
        a = math.exp((sum(ly) - b * sum(lx)) / n)
        xs = [1 + i * 0.1 for i in range(int((max_s - 1) / 0.1) + 1)]
        axes[0].plot(xs, [a * x ** b for x in xs], "--", color="gray", lw=1.5,
                     label=f"power law: {a:.1f}·n^{b:.2f}")
        axes[0].legend(fontsize=9, frameon=False)
        print(f"\npower law of practice: CPM = {a:.1f} × 세션^{b:.2f}")
    fig.tight_layout()
    fig.savefig(FIG_DIR / "learning_curve.png", bbox_inches="tight")
    print(f"저장: {FIG_DIR / 'learning_curve.png'}")


# ================= 실험 A: 탭 분석 + 매핑 최적성 =================
def analyze_tap():
    trials = load_logs("tap")
    mapping = json.loads((HERE / "mapping.json").read_text(encoding="utf-8"))
    freq_raw = json.loads((HERE / "jamo_freq.json").read_text(encoding="utf-8"))
    freq = {**freq_raw["consonants"], **freq_raw["vowels"]}
    total = sum(freq.values())
    freq = {j: v / total for j, v in freq.items()}

    # 버튼별 RT (오답 시행 제외, 3SD 이상치 제거)
    rts = defaultdict(list)
    n_err = defaultdict(int)
    for t in trials:
        if t.get("correct") is False:
            n_err[t["button_id"]] += 1
        else:
            rts[t["button_id"]].append(t["rt_s"])
    rt_mean = {}
    for b, v in rts.items():
        if len(v) >= 3:
            mu, sd = st.mean(v), st.pstdev(v)
            v = [x for x in v if abs(x - mu) <= 3 * sd] or v
        rt_mean[b] = st.mean(v)
        err = n_err[b] / (n_err[b] + len(v)) * 100 if (n_err[b] + len(v)) else 0
        print(f"{b}: RT {rt_mean[b]:.3f}s (n={len(v)}), 오답 {err:.0f}%")

    # 자모 → 버튼 시퀀스
    seq_of = {}
    for bid, info in mapping["buttons"].items():
        seq_of[info["jamo"]] = [bid]
    for jamo, seq in mapping.get("sequences", {}).items():
        if not jamo.startswith("_"):
            seq_of[jamo] = seq

    # 버튼별 사용 가중치 w(b) = Σ freq(자모) × (시퀀스 내 등장 횟수)
    w = defaultdict(float)
    covered = 0.0
    for jamo, f in freq.items():
        if jamo in seq_of:
            covered += f
            for b in seq_of[jamo]:
                w[b] += f
    print(f"\n빈도 커버리지: {covered * 100:.1f}% (매핑에 없는 자모는 제외됨)")

    buttons = [b for b in rt_mean if b in w or True]
    w_vec = [w.get(b, 0.0) for b in buttons]
    rt_vec = [rt_mean[b] for b in buttons]

    cost_now = sum(wi * ri for wi, ri in zip(w_vec, rt_vec))
    # 최적: 가중치 내림차순 ↔ RT 오름차순 (재배열 부등식 — 버튼별 분리 가능 비용이라 정확해)
    cost_opt = sum(wi * ri for wi, ri in
                   zip(sorted(w_vec, reverse=True), sorted(rt_vec)))
    rnd = []
    rt_shuffled = rt_vec[:]
    for _ in range(10000):
        random.shuffle(rt_shuffled)
        rnd.append(sum(wi * ri for wi, ri in zip(w_vec, rt_shuffled)))
    rnd_mu, rnd_sd = st.mean(rnd), st.pstdev(rnd)
    pct = sum(r < cost_now for r in rnd) / len(rnd) * 100

    print(f"\n=== 매핑 최적성 ===")
    print(f"현재 매핑 기대 비용   : {cost_now * 1000:.1f} ms/자모")
    print(f"이론 최적 비용        : {cost_opt * 1000:.1f} ms/자모  "
          f"(현재는 최적 대비 {cost_now / cost_opt * 100:.1f}%)")
    print(f"랜덤 매핑 분포        : {rnd_mu * 1000:.1f} ± {rnd_sd * 1000:.1f} ms/자모")
    print(f"현재 매핑보다 나쁜 랜덤 비율: {100 - pct:.1f}%  "
          f"(랜덤 대비 {(rnd_mu - cost_now) / rnd_mu * 100:.1f}% 효율적)")

    FIG_DIR.mkdir(exist_ok=True)
    fig, axes = plt.subplots(1, 2, figsize=(11, 4))
    # (1) 랜덤 분포 히스토그램 + 현재/최적 표시 (단일 색조)
    axes[0].hist([r * 1000 for r in rnd], bins=40, color=ACCENT, alpha=0.55,
                 edgecolor="white", linewidth=0.4)
    axes[0].axvline(cost_now * 1000, color="#222", lw=1.6, label="현재 매핑")
    axes[0].axvline(cost_opt * 1000, color="#222", lw=1.6, ls="--", label="이론 최적")
    axes[0].legend(fontsize=9, frameon=False, loc="upper right")
    axes[0].set(xlabel="기대 입력 비용 (ms/자모)", ylabel="랜덤 매핑 개수",
                title="매핑 비용: 현재 vs 랜덤 10,000개 vs 최적")
    # (2) 버튼 RT vs 사용 가중치 산점 — 음의 상관이면 '고빈도→빠른 버튼' 입증
    axes[1].scatter([x * 1000 for x in rt_vec], [x * 100 for x in w_vec],
                    s=60, color=ACCENT)
    for b, x, y in zip(buttons, rt_vec, w_vec):
        axes[1].annotate(b, (x * 1000, y * 100), textcoords="offset points",
                         xytext=(5, 3), fontsize=8, color="#555")
    axes[1].set(xlabel="버튼 평균 도달시간 (ms)", ylabel="자모 빈도 가중치 (%)",
                title="고빈도 자모일수록 빠른 버튼에 배치되었는가")
    if len(rt_vec) > 2:
        mx, my = st.mean(rt_vec), st.mean(w_vec)
        r = sum((a - mx) * (b - my) for a, b in zip(rt_vec, w_vec)) / max(
            math.sqrt(sum((a - mx) ** 2 for a in rt_vec) *
                      sum((b - my) ** 2 for b in w_vec)), 1e-12)
        axes[1].text(0.97, 0.95, f"Pearson r = {r:.2f}", transform=axes[1].transAxes,
                     ha="right", va="top", fontsize=10)
        print(f"버튼 RT ↔ 빈도 가중치 상관: r = {r:.2f} (음수일수록 설계 의도 입증)")
    fig.tight_layout()
    fig.savefig(FIG_DIR / "mapping_optimality.png", bbox_inches="tight")
    print(f"저장: {FIG_DIR / 'mapping_optimality.png'}")


# ================= SUS 채점 =================
def analyze_sus(csv_path):
    import csv
    rows = list(csv.reader(open(csv_path, encoding="utf-8")))
    scores = []
    for row in rows:
        vals = [int(x) for x in row if x.strip()]
        if len(vals) != 10:
            continue
        s = sum((v - 1) if i % 2 == 0 else (5 - v) for i, v in enumerate(vals))
        scores.append(s * 2.5)
    print(f"SUS 평균 {st.mean(scores):.1f} (n={len(scores)}, "
          f"개별: {[f'{s:.0f}' for s in scores]})")
    print("참고: 68점이 업계 평균, 80.3 이상이면 상위 10% (A등급)")


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    if mode == "transcribe":
        analyze_transcribe()
    elif mode == "tap":
        analyze_tap()
    elif mode == "sus":
        analyze_sus(sys.argv[2])
    else:
        sys.exit(__doc__)
