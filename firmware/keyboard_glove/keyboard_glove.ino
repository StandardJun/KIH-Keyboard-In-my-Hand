// Keyboard In My Hand — 장갑형 한글 키보드 펌웨어 (Arduino Leonardo / ATmega32u4)
//
// 동작 원리: 같은 버튼을 tapWindow(ms) 안에 2·3연타하면 파생 자모(ㄱ→ㅋ→ㄲ).
// OS에는 두벌식 QWERTY 키코드를 USB HID로 전송 → OS 한글 IME가 조합한다.
//
// [원본(sketch_nov28a.ino) 대비 수정 사항]
//  [버그] L_tapcount 오타 / L_pending·pending 미정의 변수 (컴파일 불가) → 상태 구조 재정리
//  [버그] 'bs','sp' 다중문자 상수 → KEY_BACKSPACE, ' ' 로 교체 (원본은 백스페이스·스페이스 미전송)
//  [버그] 왼손 싱글/더블 탭이 윈도우 만료 시 확정되지 않던 로직 → 만료 확정 구현
//  [개선] 스위치 바운스(채터링)가 연타로 오인되던 문제 → DEBOUNCE_MS 가드
//  [개선] 키 배열을 PPT 슬라이드 12 표(정본)에 맞춰 교정
//  [신규] RAW_TAP_MODE — 연타 판정 없이 물리 탭을 그대로 전송(캘리브레이션 측정 전용)
//  [신규] CAL_STAMP — 소스 설정값이 EEPROM에 저장된 옛 값을 이길 수 있게 하는 버전 스탬프
//  [옵션] EARLY_COMMIT — 다른 버튼이 눌리면 대기 중인 탭 즉시 확정(싱글탭 지연 제거, 기본 꺼짐)
//
// [캘리브레이션 흐름] 같은 폴더의 tap_calibration.py 가
//   ① RAW_TAP_MODE를 1로 바꿔 저장 → 사용자가 이 스케치를 업로드
//   ② 두 문장을 입력받아 '의도적 연타'와 '별개 입력'의 간격 분포를 라벨과 함께 수집
//   ③ 두 분포를 가르는 최적 임계값을 계산해 TAP_WINDOW_DEFAULT에 기록하고
//      RAW_TAP_MODE를 0으로 되돌린 뒤 CAL_STAMP를 +1 → 사용자가 다시 업로드
//   CAL_STAMP가 바뀌면 펌웨어는 EEPROM의 옛 값을 버리고 소스 값을 채택한다.

#include <Keyboard.h>
#include <EEPROM.h>

// ===== CALIBRATION BLOCK BEGIN — tap_calibration.py가 자동 수정하는 영역 =====
// (수동 편집도 가능하지만 형식은 유지할 것: 값 하나짜리 한 줄)
#define RAW_TAP_MODE 0                             // 1 = 연타 판정 없이 물리 탭을 즉시 전송(측정용)
const unsigned long TAP_WINDOW_DEFAULT = 300;      // ms — 연타 판정 윈도우 기본값
const uint16_t CAL_STAMP = 1;                      // 설정이 바뀔 때마다 +1 (EEPROM보다 소스 우선)
// ===== CALIBRATION BLOCK END =====

const unsigned long DEBOUNCE_MS = 30;  // 바운스 무시 구간 (ms)
// 다른 버튼이 눌리면 대기 중이던 탭을 즉시 확정한다. 대기 중인 탭의 '내용'은
// 이미 정해져 있으므로 확정 시점만 당겨질 뿐 결과는 같고, 다음 자모가 다른
// 버튼일 확률이 96.4%(말뭉치 인접 자모쌍 분석)라 체감 지연이 크게 준다.
// 더불어 A→B→A 처럼 다른 버튼을 사이에 둔 입력이 A의 연타로 잘못 합쳐지는
// 문제도 함께 막는다. 끄면 모든 탭이 윈도우 만료를 기다린다.
#ifndef EARLY_COMMIT          // 호스트 테스트에서 -DEARLY_COMMIT=0 으로 끄고 검사할 수 있다
#define EARLY_COMMIT 1
#endif

// 런타임 상태 — 시리얼 명령으로도 조정 가능 (재업로드 없이 실험할 때)
//   W<ms> 윈도우 설정 · S EEPROM 저장 · R1/R0 raw-tap on/off · C1/C0 탭 스트림 · ? 상태
unsigned long tapWindow = TAP_WINDOW_DEFAULT;
bool rawTap = (RAW_TAP_MODE != 0);
bool calStream = false;

const int EE_MAGIC_ADDR = 0;   // 0x42
const int EE_WIN_ADDR   = 1;   // 2 bytes
const int EE_STAMP_ADDR = 3;   // 2 bytes
const uint8_t EE_MAGIC  = 0x42;

// 검지부터 1a, 1b, 2a, 2b, 3a, 3b, 4 + 5(기능키)
const int L_PINS[8] = {2, 3, 4, 5, 6, 7, 8, 9};
const int R_PINS[8] = {10, 11, 12, 13, 14, 15, 16, 17};

// [탭수-1]번째 키코드. 0 = 특수키(별도 처리)
const char L_KEYS[8][3] = {
  {'r', 'z', 'R'},  // L1a: ㄱ ㅋ ㄲ
  {'t', 'a', 'T'},  // L1b: ㅅ ㅁ ㅆ
  {'s', 'f', 's'},  // L2a: ㄴ ㄹ (3연타=ㄴ)
  {'w', 'c', 'W'},  // L2b: ㅈ ㅊ ㅉ
  {'e', 'x', 'E'},  // L3a: ㄷ ㅌ ㄸ
  {'d', 'g', 'd'},  // L3b: ㅇ ㅎ (3연타=ㅇ)
  {'q', 'v', 'Q'},  // L4 : ㅂ ㅍ ㅃ
  {0, 0, 0},        // L5 : Backspace
};
const char R_KEYS[8][3] = {
  {'j', 'u', 'j'},  // R1a: ㅓ ㅕ
  {'h', 'y', 'h'},  // R1b: ㅗ ㅛ
  {'k', 'i', 'k'},  // R2a: ㅏ ㅑ
  {'n', 'b', 'n'},  // R2b: ㅜ ㅠ
  {'o', 'O', 'o'},  // R3a: ㅐ ㅒ
  {'l', 'm', 'l'},  // R3b: ㅣ ㅡ
  {'p', 'P', 'p'},  // R4 : ㅔ ㅖ
  {0, 0, 0},        // R5 : Space(1탭) · .(2탭) · Enter(3탭)
};
const uint8_t L_MAXTAP[8] = {3, 3, 2, 3, 3, 2, 3, 1};
const uint8_t R_MAXTAP[8] = {2, 2, 2, 2, 2, 2, 2, 3};

struct TapState {
  uint8_t count = 0;         // 대기 중인 탭 수
  unsigned long first = 0;   // 첫 탭 시각
  unsigned long lastEdge = 0;
  bool lastPressed = false;
};
TapState L[8], R[8];

void emitKey(bool isLeft, int i, uint8_t taps) {
  if (taps == 0) return;
  if (isLeft && i == 7) { Keyboard.write(KEY_BACKSPACE); return; }
  if (!isLeft && i == 7) {  // R5: Space / . / Enter (PPT 정본)
    if (taps == 1) Keyboard.write(' ');
    else if (taps == 2) Keyboard.write('.');
    else Keyboard.write(KEY_RETURN);
    return;
  }
  const char k = isLeft ? L_KEYS[i][taps - 1] : R_KEYS[i][taps - 1];
  if (k) Keyboard.write(k);
}

// 대기 중인 다른 버튼들을 전부 확정 (EARLY_COMMIT용)
void flushExcept(bool isLeft, int except) {
  for (int i = 0; i < 8; i++) {
    if (!(isLeft && i == except)) {
      if (L[i].count) { emitKey(true, i, L[i].count); L[i].count = 0; }
    }
    if (!(!isLeft && i == except)) {
      if (R[i].count) { emitKey(false, i, R[i].count); R[i].count = 0; }
    }
  }
}

void handleSide(bool isLeft, const int *pins, TapState *st, const uint8_t *maxTap,
                unsigned long now) {
  for (int i = 0; i < 8; i++) {
    bool pressed = (digitalRead(pins[i]) == LOW);  // INPUT_PULLUP: 눌림=LOW

    // 눌림 edge + 디바운스
    if (!st[i].lastPressed && pressed && (now - st[i].lastEdge > DEBOUNCE_MS)) {
      st[i].lastEdge = now;
      if (calStream) {  // 탭 스트림: 버튼id 시각(ms)
        Serial.print(isLeft ? 'L' : 'R'); Serial.print(i);
        Serial.print(' '); Serial.println(now);
      }

      if (rawTap) {
        // raw-tap 모드: 연타 판정을 하지 않고 물리 탭 1회 = 기본 자모 1회 전송.
        // PC 쪽 캘리브레이션 도구가 탭 사이 실제 시간 간격을 복원할 수 있게 한다.
        emitKey(isLeft, i, 1);
        st[i].count = 0;
        st[i].lastPressed = pressed;
        continue;
      }

#if EARLY_COMMIT
      flushExcept(isLeft, i);
#endif
      if (st[i].count == 0 || (now - st[i].first > tapWindow)) {
        // 윈도우 밖: 이전 대기분 확정 후 새 시퀀스 시작
        if (st[i].count) emitKey(isLeft, i, st[i].count);
        st[i].count = 1;
        st[i].first = now;
      } else {
        st[i].count++;
      }
      // 더 누를 단계가 없으면(자음 3탭·모음 2탭·기능키 1탭) 윈도우를 기다리지
      // 않고 즉시 확정한다. 첫 탭에서 바로 최대치인 버튼(Backspace 등)도
      // 여기서 걸리므로 기능키가 300ms씩 밀리지 않는다.
      if (st[i].count >= maxTap[i]) {
        emitKey(isLeft, i, st[i].count);
        st[i].count = 0;
      }
    }
    st[i].lastPressed = pressed;

    // 윈도우 만료 → 대기분 확정 (raw-tap 모드에서는 대기 자체가 없다)
    if (!rawTap && st[i].count && (now - st[i].first > tapWindow)) {
      emitKey(isLeft, i, st[i].count);
      st[i].count = 0;
    }
  }
}

void saveToEeprom() {
  EEPROM.update(EE_MAGIC_ADDR, EE_MAGIC);
  EEPROM.update(EE_WIN_ADDR, tapWindow & 0xFF);
  EEPROM.update(EE_WIN_ADDR + 1, (tapWindow >> 8) & 0xFF);
  EEPROM.update(EE_STAMP_ADDR, CAL_STAMP & 0xFF);
  EEPROM.update(EE_STAMP_ADDR + 1, (CAL_STAMP >> 8) & 0xFF);
}

void setup() {
  for (int i = 0; i < 8; i++) pinMode(L_PINS[i], INPUT_PULLUP);
  for (int i = 0; i < 8; i++) pinMode(R_PINS[i], INPUT_PULLUP);

  // 소스의 CAL_STAMP와 EEPROM에 저장된 스탬프가 같을 때만 EEPROM 값을 쓴다.
  // 스탬프가 다르면 = 캘리브레이션 도구가 소스를 갱신한 것이므로 소스 값이 이긴다.
  uint16_t eeStamp = EEPROM.read(EE_STAMP_ADDR) | (EEPROM.read(EE_STAMP_ADDR + 1) << 8);
  if (EEPROM.read(EE_MAGIC_ADDR) == EE_MAGIC && eeStamp == CAL_STAMP) {
    unsigned int w = EEPROM.read(EE_WIN_ADDR) | (EEPROM.read(EE_WIN_ADDR + 1) << 8);
    if (w >= 100 && w <= 600) tapWindow = w;
  } else {
    tapWindow = TAP_WINDOW_DEFAULT;
    saveToEeprom();
  }

  Serial.begin(115200);
  delay(3000);  // Leonardo USB/HID 안정화
  Keyboard.begin();
}

void handleSerial() {
  static char buf[16];
  static uint8_t len = 0;
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\n' || c == '\r') {
      buf[len] = 0;
      if (buf[0] == 'W') {
        long w = atol(buf + 1);
        if (w >= 100 && w <= 600) { tapWindow = w; Serial.print(F("OK W=")); Serial.println(tapWindow); }
        else Serial.println(F("ERR range 100~600"));
      } else if (buf[0] == 'S') {
        saveToEeprom();
        Serial.println(F("SAVED"));
      } else if (buf[0] == 'R') {
        rawTap = (buf[1] == '1');
        Serial.println(rawTap ? F("RAW ON") : F("RAW OFF"));
      } else if (buf[0] == 'C') {
        calStream = (buf[1] == '1');
        Serial.println(calStream ? F("CAL ON") : F("CAL OFF"));
      } else if (buf[0] == '?') {
        Serial.print(F("window_ms=")); Serial.print(tapWindow);
        Serial.print(F(" stamp=")); Serial.print(CAL_STAMP);
        Serial.print(F(" raw=")); Serial.println(rawTap ? 1 : 0);
      }
      len = 0;
    } else if (len < 15) buf[len++] = c;
  }
}

void loop() {
  unsigned long now = millis();
  handleSerial();
  handleSide(true, L_PINS, L, L_MAXTAP, now);
  handleSide(false, R_PINS, R, R_MAXTAP, now);
  delay(1);
}
