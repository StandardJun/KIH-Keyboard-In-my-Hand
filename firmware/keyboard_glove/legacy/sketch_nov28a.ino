#include <Keyboard.h>

// 왼손 : L, 오른손 : R
// 검지부터 1a, 1b, 2a, 2b, 3a, 3b, 4 + 5
// ex) 왼손 검지 1번 : L1a

const unsigned long DOUBLE_WINDOW = 300; // 더블탭 시간 300ms

const int L_PINS[8] = {2, 3, 4, 5, 6, 7, 8, 9}; // 순서대로 L1a, L1b, L2a, L2b, L3a, L3b, L4, L5
const int R_PINS[8] = {10, 11, 12, 13, 14, 15, 16, 17}; // 순서대로 R1a, R1b, R2a, R2b, R3a(A0), R3b(A1), R4(A2), R5(A3)

// 키 할당
const char L_SINGLE[8] = {'r', 't', 's', 'w', 'e', 'd', 'q', 'bs'}; // ㄱ ㅅ ㄴ ㅈ ㄷ ㅇ ㅂ backspace
const char L_DOUBLE[8] = {'z', 'g', 'f', 'c', 'x', 'a', 'v', 'bs'}; // ㅋ ㅎ ㄹ ㅊ ㅌ ㅁ ㅍ backspace
const char L_TRIPLE[8] = {'R', 'T', 's', 'W', 'E', 'd', 'Q', 'bs'}; // ㄲ ㅆ ㄴ ㅉ ㄸ ㅇ ㅃ backspace

const char R_SINGLE[8] = {'j','l', 'k', 'h', 'o', 'n', 'p', 'sp'}; // ㅓ ㅣ ㅏ ㅗ ㅐ ㅜ ㅔ space
const char R_DOUBLE[8] = {'u', 'm', 'i', 'y', 'O', 'b', 'P', 'sp'}; // ㅕ ㅡ ㅑ ㅛ ㅒ ㅠ ㅖ space

bool L_lastPressedHigh[8] = {false, false, false, false, false, false, false, false};
bool R_lastPressedHigh[8] = {false, false, false, false, false, false, false, false};
unsigned long L_tapCount[8] = {0, 0, 0, 0, 0, 0, 0, 0};
bool R_pending[8] = {false, false, false, false, false, false, false, false};
unsigned long L_firstTime[8] = {0, 0, 0, 0, 0, 0, 0, 0};
unsigned long R_firstTime[8] = {0, 0, 0, 0, 0, 0, 0, 0};



void setup() {
  for (int i = 0; i < 8; i++) pinMode(L_PINS[i], INPUT_PULLUP);
  for (int i = 0; i < 8; i++) pinMode(R_PINS[i], INPUT_PULLUP);

  delay(3000);        // Leonardo USB/HID 안정화
  Keyboard.begin();
}

void loop() {
  unsigned long now = millis();

  // 1) 눌림 edge 감지 + 더블탭 처리
  for (int i = 0; i < 8; i++) {
    // INPUT_PULLUP에서는 눌림이 LOW지만, 우리가 "눌림=HIGH"로 해석
    bool L_pressedHigh = (digitalRead(L_PINS[i]) == LOW);
    bool R_pressedHigh = (digitalRead(R_PINS[i]) == LOW);

    // "LOW->HIGH"에 해당하는 눌림 순간(edge): false -> true
    if (!L_lastPressedHigh[i] && L_pressedHigh) {
      if (L_tapCount[i] == 0) {
        L_tapCount[i] = 1;
        L_firstTime[i] = now;
      } else {
        if (now - L_firstTime[i] <= DOUBLE_WINDOW) {
          L_tapcount[i]++;

          if (L_tapCount[i] >= 3) {
            Keyboard.write(L_TRIPLE[i]);
            L_tapCount[i] = 0;
          }
        } else {
          if (L_tapCount[i] == 1) Keyboard.write(L_SINGLE[i]);
          else if (L_tapCount[i] == 2) Keyboard.write(L_DOUBLE[i]);

          L_tapCount[i] = 1;
          L_firstTime[i] = now;
        }
      }
    }

    if (!R_lastPressedHigh[i] && R_pressedHigh) {
      if (!R_pending[i]) {
        R_pending[i] = true;
        R_firstTime[i] = now;
      } else {
        if (now - R_firstTime[i] <= DOUBLE_WINDOW) {
          Keyboard.write(R_DOUBLE[i]);
          R_pending[i] = false;
        } else {
          Keyboard.write(R_SINGLE[i]);
          R_pending[i] = true;
          R_firstTime[i] = now;
        }
      }
    }

    L_lastPressedHigh[i] = L_pressedHigh;
    R_lastPressedHigh[i] = R_pressedHigh;
  }

  // 2) 더블탭 시간 만료 → 싱글 확정 출력
  for (int i = 0; i < 8; i++) {
    if (L_pending[i] && (now - L_firstTime[i] > DOUBLE_WINDOW)) {
      Keyboard.write(L_SINGLE[i]);
      pending[i] = false;
    }
    if (R_pending[i] && (now - R_firstTime[i] > DOUBLE_WINDOW)) {
      Keyboard.write(R_SINGLE[i]);
      pending[i] = false;
    }
  }

  delay(1);
}
