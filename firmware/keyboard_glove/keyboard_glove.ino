// Keyboard In My Hand — 수정판 펌웨어 (원본: sketch_nov28a.ino)
// 원본 대비 수정 사항:
//  [버그] L_tapcount 오타(컴파일 에러) → L 상태 배열로 통일
//  [버그] L_pending / pending 미정의 변수(컴파일 에러) → 상태 구조 재정리
//  [버그] 'bs', 'sp' 다중문자 상수 → KEY_BACKSPACE / ' ' 로 교체 (원본은 백스페이스·스페이스가 실제로 전송되지 않음)
//  [버그] 왼손 싱글/더블 탭이 윈도우 만료 시 확정되지 않던 로직 → 만료 확정 구현
//  [개선] 스위치 바운스(채터링)가 연타로 오인되던 문제 → DEBOUNCE_MS 가드 추가
//  [옵션] EARLY_COMMIT: 다른 버튼이 눌리면 대기 중인 탭을 즉시 확정 → 싱글탭 300ms 지연 대부분 제거 (기본 꺼짐, 실험 후 채택 판단)
//
// 동작 원리(원본 설계 유지): 같은 버튼을 300ms 안에 2·3연타하면 파생 자모(ㄱ→ㅋ→ㄲ).
// OS에는 두벌식 QWERTY 키코드를 USB HID로 전송 → OS 한글 IME가 조합.

#include <Keyboard.h>
#include <EEPROM.h>

// 연타 판정 윈도우: 기본 300ms, 시리얼 명령으로 사용자별 조정 가능 (EEPROM 저장)
//   W<ms>  윈도우 설정 (예: W250)      S  현재 값 EEPROM 저장
//   C1/C0  캘리브레이션 스트림 on/off   ?  현재 상태 출력
// 캘리브레이션: tools/calibrate_window.py 로 문장 1회 입력 → 개인 연타 분포 측정 → 자동 설정
unsigned long tapWindow = 300;
const unsigned long DEBOUNCE_MS = 30;  // 바운스 무시 구간 (ms)
#define EARLY_COMMIT 0                 // 1로 바꾸면 다른 버튼 입력 시 즉시 확정
const int EE_MAGIC_ADDR = 0, EE_WIN_ADDR = 1;
bool calStream = false;

// 검지부터 1a, 1b, 2a, 2b, 3a, 3b, 4 + 5(기능키)
const int L_PINS[8] = {2, 3, 4, 5, 6, 7, 8, 9};
const int R_PINS[8] = {10, 11, 12, 13, 14, 15, 16, 17};

// [탭수-1]번째 키코드. 0 = 특수키(별도 처리)
// ※ 키 배열은 PPT 슬라이드 12 표(정본) 기준으로 교정됨 — 원본 .ino는 수정 전 구버전
//   (원본과 차이: ㅅ버튼 2연타=ㅁ(원본 ㅎ), ㅇ버튼 2연타=ㅎ(원본 ㅁ), 모음 마디 짝 ㅗ/ㅜ/ㅣ 재배치)
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
  {0, 0, 0},        // R5 : Space(1탭) . (2탭) Enter(3탭)
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
      if (calStream) {  // 캘리브레이션: 버튼id 시각(ms) 스트림
        Serial.print(isLeft ? 'L' : 'R'); Serial.print(i);
        Serial.print(' '); Serial.println(now);
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
        if (st[i].count >= maxTap[i]) {  // 최대 연타 도달 → 즉시 확정
          emitKey(isLeft, i, st[i].count);
          st[i].count = 0;
        }
      }
    }
    st[i].lastPressed = pressed;

    // 윈도우 만료 → 대기분 확정
    if (st[i].count && (now - st[i].first > tapWindow)) {
      emitKey(isLeft, i, st[i].count);
      st[i].count = 0;
    }
  }
}

void setup() {
  for (int i = 0; i < 8; i++) pinMode(L_PINS[i], INPUT_PULLUP);
  for (int i = 0; i < 8; i++) pinMode(R_PINS[i], INPUT_PULLUP);
  // EEPROM에서 사용자 캘리브레이션 값 복원
  if (EEPROM.read(EE_MAGIC_ADDR) == 0x42) {
    unsigned int w = EEPROM.read(EE_WIN_ADDR) | (EEPROM.read(EE_WIN_ADDR + 1) << 8);
    if (w >= 100 && w <= 600) tapWindow = w;
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
        EEPROM.update(EE_MAGIC_ADDR, 0x42);
        EEPROM.update(EE_WIN_ADDR, tapWindow & 0xFF);
        EEPROM.update(EE_WIN_ADDR + 1, (tapWindow >> 8) & 0xFF);
        Serial.println(F("SAVED"));
      } else if (buf[0] == 'C') {
        calStream = (buf[1] == '1');
        Serial.println(calStream ? F("CAL ON") : F("CAL OFF"));
      } else if (buf[0] == '?') {
        Serial.print(F("window_ms=")); Serial.println(tapWindow);
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
