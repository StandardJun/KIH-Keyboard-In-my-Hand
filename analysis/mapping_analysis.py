#!/usr/bin/env python3
"""Corpus analysis for the Keyboard-In-My-Hand Hangul mapping.

Computes, from any Korean text corpus:
  1. Jamo frequency table (keystroke-level: compound vowels/finals decomposed,
     double consonants kept single — Dubeolsik convention)
  2. Theoretical KSPC (keystrokes per jamo) of the multi-tap mapping,
     vs. a uniform (frequency-blind) assignment
  3. Same-button consecutive-jamo rate — the fraction of adjacent jamo pairs
     that share a button and therefore pay the multi-tap timeout penalty

Usage:
  python mapping_analysis.py --corpus ./my_corpus_dir [--mapping ../experiments/mapping.json]

The corpus dir may contain .txt/.md files; only Hangul syllables are used.
"""
import argparse
import json
from collections import Counter
from pathlib import Path

CHO = "ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ"
JUNG = "ㅏㅐㅑㅒㅓㅔㅕㅖㅗㅘㅙㅚㅛㅜㅝㅞㅟㅠㅡㅢㅣ"
JONG = " ㄱㄲㄳㄴㄵㄶㄷㄹㄺㄻㄼㄽㄾㄿㅀㅁㅂㅄㅅㅆㅇㅈㅊㅋㅌㅍㅎ"
SPLIT_VOWEL = {"ㅘ": "ㅗㅏ", "ㅙ": "ㅗㅐ", "ㅚ": "ㅗㅣ", "ㅝ": "ㅜㅓ",
               "ㅞ": "ㅜㅔ", "ㅟ": "ㅜㅣ", "ㅢ": "ㅡㅣ"}
SPLIT_FINAL = {"ㄳ": "ㄱㅅ", "ㄵ": "ㄴㅈ", "ㄶ": "ㄴㅎ", "ㄺ": "ㄹㄱ", "ㄻ": "ㄹㅁ",
               "ㄼ": "ㄹㅂ", "ㄽ": "ㄹㅅ", "ㄾ": "ㄹㅌ", "ㄿ": "ㄹㅍ", "ㅀ": "ㄹㅎ", "ㅄ": "ㅂㅅ"}


def to_jamo_words(text):
    """Split text into words (eojeol) of keystroke-level jamo."""
    words, cur = [], []
    for ch in text:
        code = ord(ch) - 0xAC00
        if 0 <= code < 11172:
            cur.append(CHO[code // 588])
            cur.extend(SPLIT_VOWEL.get(JUNG[(code % 588) // 28], JUNG[(code % 588) // 28]))
            jong = JONG[code % 28]
            if jong != " ":
                cur.extend(SPLIT_FINAL.get(jong, jong))
        else:
            if cur:
                words.append(cur)
                cur = []
    if cur:
        words.append(cur)
    return words


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", required=True, help="directory of .txt/.md Korean files")
    ap.add_argument("--mapping", default=str(Path(__file__).parent.parent / "experiments" / "mapping.json"))
    ap.add_argument("--out", default=str(Path(__file__).parent / "jamo_freq_corpus.json"))
    args = ap.parse_args()

    corpus = ""
    files = [p for p in Path(args.corpus).rglob("*") if p.suffix in (".txt", ".md")]
    for p in files:
        try:
            corpus += p.read_text(encoding="utf-8")
        except Exception:
            pass

    words = to_jamo_words(corpus)
    stream = [j for w in words for j in w]
    freq = Counter(stream)
    total = sum(freq.values())
    print(f"corpus: {len(files)} files, {total:,} jamo, {len(words):,} words")

    m = json.loads(Path(args.mapping).read_text(encoding="utf-8"))
    btn_of, taps_of = {}, {}
    for bid, info in m["buttons"].items():
        if len(info["jamo"]) == 1:
            btn_of[info["jamo"]] = bid
            taps_of[info["jamo"]] = 1
    for j, seq in m["sequences"].items():
        if not j.startswith("_") and len(j) == 1 and ord(j) > 0x3130:
            btn_of[j] = seq[0]
            taps_of[j] = len(seq)

    covered = sum(c for j, c in freq.items() if j in taps_of)
    kspc = sum(c * taps_of[j] for j, c in freq.items() if j in taps_of) / covered
    one_tap = sum(c for j, c in freq.items() if j in taps_of and taps_of[j] == 1) / covered
    uniform = sum(taps_of.values()) / len(taps_of)
    print(f"coverage {covered / total * 100:.2f}% | KSPC {kspc:.3f} "
          f"(uniform {uniform:.3f}, -{(1 - kspc / uniform) * 100:.1f}%) | 1-tap {one_tap * 100:.1f}%")

    pairs = same = 0
    same_pairs = Counter()
    for w in words:
        for a, b in zip(w, w[1:]):
            if a in btn_of and b in btn_of:
                pairs += 1
                if btn_of[a] == btn_of[b]:
                    same += 1
                    same_pairs[a + b] += 1
    print(f"same-button adjacent pairs: {same:,}/{pairs:,} = {same / pairs * 100:.2f}%")
    print("top pairs:", same_pairs.most_common(8))

    Path(args.out).write_text(json.dumps({
        "_source": f"{len(files)} files, {total} jamo",
        "kspc": round(kspc, 4), "kspc_uniform": round(uniform, 4),
        "one_tap_ratio": round(one_tap, 4),
        "same_button_pair_ratio": round(same / pairs, 4),
        "frequencies_pct": {j: round(c / total * 100, 4) for j, c in freq.most_common()
                            if j in taps_of},
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"saved: {args.out}")


if __name__ == "__main__":
    main()
