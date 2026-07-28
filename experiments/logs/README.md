# 실험 원자료

`speed_vs_tv_all.csv` — 학습곡선 실험(실험 D)의 시행별 기록. 1행 = 1시행.

참가자 20명 × 조건 2개 × 시행 15회 = **600행**. 파일럿 2명을 2026-07-11에,
본실험을 2026-07-21 ~ 07-26에 실시했다. 설계는 [`analysis/STUDY_DESIGN.md`](../../analysis/STUDY_DESIGN.md),
결과 해석은 [`analysis/RESULTS.md`](../../analysis/RESULTS.md)에 있다.

참가자는 `P1`~`P20` 가명이며 실명·연락처·인구통계는 수집·기록하지 않았다.

## 조건

| `device` | 내용 |
|---|---|
| `KIH` | 장갑형 키보드. `experiments/speed_test.py`로 측정 |
| `TV_OSK` | 대조군. 방향키로 커서를 옮겨 선택하는 화면 키보드. `experiments/tv_remote_sprint.py`로 측정 |

**두 조건은 컬럼이 다르다.** 입력 방식이 달라 셀 수 있는 것이 다르기 때문이다.
`KIH` 행에서는 `TV_OSK` 전용 컬럼이 비어 있고 그 반대도 같다.

## 컬럼

### 공통

| 컬럼 | 의미 |
|---|---|
| `timestamp` | 시행 시작 시각 (ISO 8601) |
| `participant` | 참가자 가명 `P1`~`P20` |
| `device` | `KIH` / `TV_OSK` |
| `session` | 세션 ID (본 실험은 전부 `S1`) |
| `posture` | 자세 조건 (본 실험은 전부 `desk`) |
| `trial` | 해당 조건에서 몇 번째 시행인지 `1`~`15` |
| `words_completed` | 60초 안에 제출한 단어 수 |
| `syllables` | 입력한 음절 수 |
| `jamo` | 입력한 자모 수 |
| `cpm_syl` | 분당 음절 수 |
| `jpm` | 분당 자모 수 |
| `wpm` | `jpm / 5`. 국제 비교용 표준 정의 |

### `KIH` 전용

| 컬럼 | 의미 |
|---|---|
| `key_events` | 키 이벤트 총 수 |
| `backspace` | 백스페이스 누른 횟수 |
| `msd_error_pct` | 미수정 오류율. `MSD(목표 자모열, 입력 자모열) / max(길이) × 100` |

### `TV_OSK` 전용

| 컬럼 | 의미 |
|---|---|
| `presses` | 선택(확인) 키를 누른 횟수 |
| `moves` | 커서 이동(방향키) 횟수 |
| `moves_per_press` | `moves / presses`. 자모 하나당 커서 이동 비용 |
| `backspaces` | 백스페이스 횟수 |
| `skips` | 건너뛴 단어 수 |
| `correction_pct` | 수정률. `(presses − jamo) / jamo × 100` |

## 정확도 지표가 조건별로 다른 이유

`TV_OSK`는 단어가 정확히 맞아야 다음으로 넘어가는 구조라 **오타가 결과 문자열에 남지 않는다.**
그래서 `msd_error_pct`를 계산할 수 없고, 대신 "틀려서 더 누른 만큼"을 `correction_pct`로 환산했다.

두 값은 정의가 달라 **직접 대소 비교를 하지 않는다.** 각 조건 안에서의 추세만 본다.

## 재현

```bash
python analysis/verify_results.py
```

`RESULTS.md`에 실린 수치를 이 CSV에서 다시 계산해 대조한다. 하나라도 어긋나면 종료 코드 1.
