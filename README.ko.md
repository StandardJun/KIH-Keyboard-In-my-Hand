# KIH — Keyboard In my Hand

**장갑형 한글 키보드 — 어디서든, 어떤 자세로든, 보지 않고 한글을 입력한다.**

[English README](README.md)

팀 손보드(HandBoard) · 서울대학교 공과대학 기계공학부
🏆 **대상**, 메카트로닉스 경연대회 (서울대학교 기계공학부 / HD현대, 2025. 12)
제15회 공과대학 창의설계축전(2026) 출품작
<!-- TODO: 축전 결과 나오면 갱신 -->

<p align="center">
  <img src="docs/images/glove_photo.png" width="560" alt="KIH 프로토타입"/>
</p>

<!-- TODO: 데모 GIF — eyes-free 타이핑 원테이크 -->

양손 장갑의 손가락 마디에 택트 스위치 16개를 달고 같은 손 엄지로 눌러 한글을 입력한다.
기기는 **표준 USB HID 키보드**로 인식되어 두벌식 키코드를 그대로 보내므로, 드라이버도
전용 프로그램도 필요 없이 OS 기본 IME가 한글을 조합한다. 재료 원가는 **14,184원**.

## 실험 결과

**참가자 20명**을 대상으로 KIH와 TV식 커서 화면 키보드(스마트TV·XR에서 쓰는 그 방식)를
같은 참가자가 모두 사용하는 방식으로 비교했다. 조건별로 10분씩 훈련한 뒤 **1분 입력을 15회**
반복했고, 300개 단어 풀에서 무작위로 제시된 단어를 **기기를 보지 않은 채** 입력했다.
조건 순서는 참가자 간 균형 배치했다.

<p align="center">
  <img src="docs/images/results_learning_curve.png" width="900" alt="KIH와 TV OSK의 학습곡선·멱법칙 적합·오류율"/>
</p>

| | KIH (장갑) | TV 화면 키보드 |
|---|---|---|
| 속도, 1회 → 15회 | **2.3 → 10.6 WPM** (4.6배) | 5.6 → 7.5 WPM |
| 멱법칙 적합 | WPM = 1.55·n<sup>0.602</sup> (R² = 0.636) | WPM = 5.80·n<sup>0.079</sup> (R² = 0.142) |
| 오류율, 1회 → 15회 | **17.2% → 4.1%** (−76%) | 4.3% → 5.6% (수정률, 추세 없음) |

데이터가 말하는 세 가지:

1. **KIH는 계속 학습되지만 커서 키보드는 아니다.** 멱법칙 지수 0.602 대 0.079 —
   대조군은 첫 접촉부터 이미 포화 상태였다. 참가자들은 TV 커서 키보드를 이미 써 봤고,
   그 방식은 거기까지가 상한이다.
2. **속도와 정확도가 함께 좋아졌다.** 15회차에 속도는 4.6배가 되면서 미수정 오류는 76%
   줄었다 — 새 입력 방식에서 흔한 속도-정확도 트레이드오프가 나타나지 않았다.
3. **교차가 빠르다.** 약 9회차, 즉 9분 남짓 연습에서 대조군을 추월하고 15회차에도 곡선은
   여전히 상승 중이다. 적합식을 외삽하면 30회에 약 12 WPM, 50회에 약 16 WPM이다.

최종 10.6 WPM은 최신 hands/eyes-free 입력 기법(발목 제스처 11~13 WPM, CHI 2026)과 동급이고
상용 커서 선택 방식의 문헌값(~8 WPM)을 웃돈다. 그러면서 **시선과 자세를 모두 자유롭게** 둔다.

WPM은 국제 비교를 위한 표준 정의(자모/분 ÷ 5)를 따랐다.
매핑 효율(KSPC 1.27, 1탭 74.2%)은 [`analysis/RESULTS.md`](analysis/RESULTS.md)에 있다.

## 왜 만들었나

키보드는 한 세기 넘게 '책상 위 평면 배열'을 유지해 왔다. 이 형태는 입력 좌표계를 신체 외부의
고정면에 묶어 **자세와 시선을 동시에 구속한다**. 개별 기기의 성능이 아니라 이 구조적 전제가
문제다.

- **XR** — HMD를 쓰면 손과 키보드가 보이지 않아 숙련자조차 물리 키보드 속도가 약 36% 떨어진다.
  XR 입력 기법 176종을 분석한 리뷰는 텍스트 입력을 XR이 데스크톱·모바일에 미달하는 영역으로
  지목한다.
- **접근성** — 점자정보단말기는 약 600만 원인데 국내 시각장애인 중 점자 해독 가능 비율은
  약 13%다. 나머지를 위한 저비용 비점자 촉각 입력기는 사실상 없다.
- **자세** — 사무직의 12개월 목 통증 유병률 45.5%, 장시간 좌식과 목 전방 굴곡이 유의한 위험 요인.

그래서 이 과제는 목표를 **자세 비구속·시선 비점유 입력(posture-free, eyes-free text entry)** 으로
재정의하고, 키보드를 책상이 아니라 손에 씌웠다.

## 어떻게 동작하나

<p align="center">
  <img src="docs/images/mapping_diagram.png" width="760" alt="16버튼 한글 매핑"/>
</p>

1. **마디는 신체에 내장된 키캡이다.** 사람은 시각 없이 촉각과 고유수용감각만으로 자기 손가락 위
   여러 버튼을 구별해 조작할 수 있다(DigitSpace, CHI '16). 16버튼(한 손 8개)은 그 가능성을
   해치지 않는 범위에서 버튼 수를 확장한 결과다. 버튼 위치는 eyes-free 배열 후보 3안을 두고
   **참가자 30명의 응답**과 HCI 문헌을 근거로 선정했다. 스위치가 손가락에 붙어 있어 책상이나
   별도 입력면이 필요 없고, 접점이 닫히는 전기 신호를 그대로 쓰기 때문에 추정할 동작이 없다 —
   카메라도, 인식도, 확률적 오류도 없다.

2. **연타 = 가획.** 기본 자모는 1탭, 파생 자모는 **같은 버튼을 다시** 누른다 — 2연타는 격음과
   y계 모음(ㄱ→ㅋ, ㅏ→ㅑ), 3연타는 경음(ㄱ→ㄲ). 훈민정음의 가획·병서 원리를 반복 횟수로 그대로
   옮긴 것이라, 외울 규칙은 "같은 계열은 같은 버튼을 반복해서 누른다" 하나뿐이다.

   <p align="center">
     <img src="docs/images/multitap_timeline.png" width="720" alt="연타 원리"/>
     <br/>
     <img src="docs/images/freq_vs_taps.png" width="760" alt="자모 빈도와 필요 탭 수"/>
   </p>

   한글의 기본자가 대체로 고빈도 자모와 일치하기 때문에, 이 구조를 따르는 것만으로 빈도 효율이
   함께 따라온다. 말뭉치 199,806자모 분석 결과 **KSPC 1.27**(빈도 무시 배치 대비 −26%),
   **전체 입력의 74.2%가 1탭**으로 처리된다.

3. **동시입력이 아니라 순차 입력.** 코드(동시입력) 키보드는 암기 부담 때문에 대중화에 이르지
   못했다. 좌자음-우모음은 두벌식 그대로라 기존 한글 사용자의 배열 지식이 그대로 전이되고,
   겹모음·겹받침도 두벌식처럼 순차 입력하면 OS IME가 조합한다.

4. **사용자별 캘리브레이션.** 연타 판정 윈도우(기본 300ms)는
   [`firmware/keyboard_glove/tap_calibration.py`](firmware/keyboard_glove/tap_calibration.py)로
   실측해 정한다. 펌웨어를 raw-tap 모드로 전환한 뒤 사용자가 문장 두 개를 입력하면, 관측된
   keydown을 `mapping.json`의 목표 시퀀스에 정렬해 모든 탭 간격을 *의도적 연타* 와
   *같은 버튼을 쓰는 별개 입력* 으로 라벨링한다. 그다음 오분류를 최소화하는 임계값을 골라
   **.ino의 `TAP_WINDOW_DEFAULT`를 직접 수정**하고 `CAL_STAMP`를 올려, 보드에 저장된 옛 EEPROM
   값이 새 값을 덮지 못하게 한다. 시리얼 포트도, 추가 패키지도 필요 없다.

## 저장소 구조

```
firmware/
  keyboard_glove/
    keyboard_glove.ino    Arduino Leonardo 펌웨어 (USB HID, 연타 엔진, raw-tap 측정 모드,
                          캘리브레이션 블록, CAL_STAMP + EEPROM)
    tap_calibration.py    사용자별 연타 윈도우 캘리브레이션 — .ino를 수정하므로 같은 폴더에 둠
    mapping.json          experiments/mapping.json의 사본(도구가 단독으로 돌도록).
                          둘을 함께 갱신할 것 — 내용이 달라지면 도구가 경고한다
    test/                 연타 엔진 호스트 테스트 — Arduino API를 스텁으로 갈아끼우고 스케치를
                          #include 해 가상 시계로 구동, 보드 없이 타이밍 로직 검증 (`make both`)
    legacy/               수업 당시 원본 스케치 (개발 히스토리)
  calibrate_window.py     선택 경로: 재업로드 없이 시리얼로 윈도우만 즉시 조정
experiments/
  PROTOCOL.md             실험 프로토콜 — 버튼 도달시간·매핑 비용, 학습곡선, 사용성·자세,
                          커서식 OSK 비교, eyes-free (MacKenzie 계열 표준 방법론)
  speed_test.py           1분 랜덤 단어 속도 실험 GUI (본 실험 도구)
  tv_remote_sprint.py     TV 리모컨식 커서 키보드 60초 스프린트 — 대조군
                          (같은 단어 풀·같은 WPM 정의)
  tv_osk_test.py          같은 입력 방식의 문장 전사 버전
  logger.py               전사·탭 기록 GUI
  analyze.py              지표·그림: CPM/WPM, MSD 오류율, 학습곡선,
                          매핑 비용 vs 무작위 배치 10,000개
  mapping.json            16버튼 ↔ 자모 매핑 (단일 출처)
analysis/
  mapping_analysis.py     말뭉치 → 자모 빈도, KSPC, 같은 버튼 연속쌍 비율
  RESULTS.md              정량 결과
docs/images/              사진·다이어그램·실험 그림
```

모든 Python 도구는 표준 라이브러리만 쓰고 GUI 없이 도는 `--selftest`를 갖고 있으며,
펌웨어는 하드웨어 없이 돌아가는 호스트 테스트를 함께 둔다.

## 하드웨어

<p align="center">
  <img src="docs/images/system_overview.png" width="820" alt="프로토타입과 신호 흐름"/>
</p>

| 품목 | 수량 | 단가 | 비고 |
|---|---|---|---|
| 택트 스위치 (6×6mm) | 16 | 134원 | 한 손당 검지~약지 마디당 2개, 소지 1개 + 기능키 1개 |
| Arduino Leonardo (ATmega32u4) | 1 | 8,500원 | USB HID 네이티브 지원 |
| 가죽 장갑 | 1쌍 | 1,000원 | |
| 배선재·열수축 튜브 | 1식 | 1,040원 | |
| 접착제·절연 테이프 | 1식 | 500원 | |
| **합계** | | **14,184원** | 15대 이상 생산 시 약 12,230원 (−13.8%) |

`firmware/keyboard_glove/keyboard_glove.ino`를 Arduino IDE에서 업로드한다(보드: Leonardo).
시리얼 115200 baud: `W<ms>` 윈도우 설정 · `S` EEPROM 저장 · `R1/R0` raw-tap 모드 ·
`C1/C0` 탭 스트림 · `?` 상태.

## 실행 방법

```bash
# Python 3.8+ / GUI는 tkinter(표준 라이브러리), 추가 설치 없음
python experiments/speed_test.py                    # 1분 속도 실험
python experiments/tv_remote_sprint.py              # TV 리모컨식 대조군, 60초 스프린트
python experiments/tv_osk_test.py                   # 대조군, 문장 전사 버전
python experiments/logger.py --mode transcribe --participant P01 --session S1
python firmware/keyboard_glove/tap_calibration.py   # 연타 윈도우 캘리브레이션 → .ino 수정
python experiments/analyze.py transcribe            # 그림 생성 (matplotlib 필요)

# 하드웨어 없이 검증
python experiments/speed_test.py --selftest
make -C firmware/keyboard_glove/test both
```

## 팀

**손보드(HandBoard)** — 서울대학교 공과대학 기계공학부

| | | |
|---|---|---|
| 김기준 | 하드웨어 | 장갑 장착 구조, 스위치 부착, 프로토타입 제작 |
| 이동원 | 유저 테스트·시장성 | 실험 설계, 데이터 분석, 원가·시장 분석 |
| 하홍준 | 소프트웨어 | 펌웨어, 연타 엔진, 캘리브레이션 도구 |

## 라이선스

[MIT](LICENSE) — 하드웨어 설계, 펌웨어, 실험 도구.
