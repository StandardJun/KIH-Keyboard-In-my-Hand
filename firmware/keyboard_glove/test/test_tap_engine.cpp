// 펌웨어 연타 엔진 호스트 테스트 — 보드 없이 keyboard_glove.ino의 로직을 그대로 돌린다.
//
// Arduino API(Keyboard/EEPROM/digitalRead/millis/Serial)를 스텁으로 갈아끼우고
// 스케치를 그대로 #include 한 뒤, 가상 시계로 탭 타이밍을 만들어 실제 출력 키를
// 검사한다. 로직을 따로 베껴 적지 않으므로 펌웨어와 테스트가 갈라지지 않는다.
//
// 빌드/실행:  g++ -std=c++17 -o test_tap_engine test_tap_engine.cpp && ./test_tap_engine
// EARLY_COMMIT 끈 동작도 검사: g++ -std=c++17 -Istub -DEARLY_COMMIT=0 ...

#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <string>
#include <vector>

// ── Arduino 스텁 ──────────────────────────────────────────────────────────
static unsigned long g_now = 0;              // 가상 시계(ms)
static bool g_pin_low[64] = {false};         // true = 눌림(INPUT_PULLUP에서 LOW)
static std::string g_out;                    // Keyboard.write 결과

unsigned long millis() { return g_now; }
void delay(unsigned long ms) { g_now += ms; }
int digitalRead(int pin) { return g_pin_low[pin] ? 0 : 1; }   // LOW=0, HIGH=1
void pinMode(int, int) {}
#define INPUT_PULLUP 2
#define LOW 0
#define HIGH 1
#define KEY_BACKSPACE '\b'
#define KEY_RETURN '\n'
#define F(x) (x)

struct KeyboardStub {
  void begin() {}
  void write(char c) { g_out.push_back(c); }
} Keyboard;

struct EepromStub {
  uint8_t cell[64] = {0};
  uint8_t read(int a) { return cell[a]; }
  void update(int a, uint8_t v) { cell[a] = v; }
} EEPROM;

struct SerialStub {
  void begin(long) {}
  int available() { return 0; }
  char read() { return 0; }
  void print(const char*) {} void print(char) {} void print(unsigned long) {}
  void print(int) {} void println(const char*) {} void println(unsigned long) {}
  void println(int) {}
} Serial;

#include "../keyboard_glove.ino"   // ← 검사 대상(로직 원본)

// ── 테스트 헬퍼 ───────────────────────────────────────────────────────────
static void run_for(unsigned long ms) {       // 시간 경과 + loop() 반복 실행
  for (unsigned long i = 0; i < ms; i++) { g_now += 1; loop(); }
}
static void tap(int pin, unsigned long hold_ms = 12) {
  g_pin_low[pin] = true;  run_for(hold_ms);
  g_pin_low[pin] = false; run_for(4);
}

static int g_fail = 0;
static void check(const char* name, const std::string& got, const std::string& want) {
  bool ok = (got == want);
  if (!ok) g_fail++;
  printf("%-52s %s   (got=\"%s\" want=\"%s\")\n", name, ok ? "OK" : "FAIL",
         got.c_str(), want.c_str());
}
static void check_num(const char* name, long got, long want) {
  bool ok = (got == want);
  if (!ok) g_fail++;
  printf("%-52s %s   (got=%ld want=%ld)\n", name, ok ? "OK" : "FAIL", got, want);
}

static void reset_engine() {          // 시행 간 상태 초기화
  g_out.clear();
  for (int i = 0; i < 8; i++) { L[i] = TapState(); R[i] = TapState(); }
  for (int i = 0; i < 64; i++) g_pin_low[i] = false;
  g_now += 2000;                      // 이전 시행의 윈도우가 확실히 만료되도록
  run_for(5);
}

// 버튼 → 핀
static const int P_L1a = L_PINS[0];   // ㄱ ㅋ ㄲ  (maxTap 3)
static const int P_L2a = L_PINS[2];   // ㄴ ㄹ     (maxTap 2)
static const int P_R3b = R_PINS[5];   // ㅣ ㅡ     (maxTap 2)
static const int P_R2a = R_PINS[2];   // ㅏ ㅑ
static const int P_R2b = R_PINS[3];   // ㅜ ㅠ

int main() {
  setup();
  printf("연타 윈도우 %lu ms · 디바운스 %lu ms · EARLY_COMMIT %d\n\n",
         tapWindow, DEBOUNCE_MS, EARLY_COMMIT);

  // 1) 최대 연타 도달 시 '추가 대기 없이' 즉시 확정되는가 (핵심 요구사항)
  reset_engine();
  tap(P_L1a); tap(P_L1a); tap(P_L1a);          // ㄱ×3 = ㄲ
  check("자음 3탭 ㄲ — 윈도우 만료 전 즉시 확정", g_out, "R");
  unsigned long t_commit = g_now;
  run_for(tapWindow + 50);
  check("자음 3탭 — 이후 추가 출력 없음", g_out, "R");
  (void)t_commit;

  reset_engine();
  tap(P_R3b); tap(P_R3b);                       // ㅣ×2 = ㅡ
  check("모음 2탭 ㅡ — 즉시 확정", g_out, "m");

  reset_engine();
  tap(P_L2a); tap(P_L2a);                       // ㄴ×2 = ㄹ (자음이지만 2단계)
  check("2단계 자음 ㄹ — 즉시 확정", g_out, "f");

  // 2) 'ㅢ' = ㅡ(2탭) + ㅣ(1탭) — 같은 버튼 3연타
  reset_engine();
  tap(P_R3b); tap(P_R3b); tap(P_R3b);
  check("ㅢ 3탭 직후 — ㅡ만 확정(ㅣ는 대기)", g_out, "m");
  run_for(tapWindow + 30);
  check("ㅢ 3탭 — 윈도우 만료 후 ㅡㅣ 완성", g_out, "ml");

  // 3) 대기 중이던 마지막 탭이 '다른 버튼'으로 즉시 확정되는가 (EARLY_COMMIT)
  reset_engine();
  tap(P_R3b); tap(P_R3b); tap(P_R3b);           // ㅡ 확정 + ㅣ 대기
  tap(P_R2a);                                   // 다른 버튼(ㅏ)
#if EARLY_COMMIT
  check("ㅢ 뒤 다른 버튼 — ㅣ 즉시 확정(ㅏ는 대기)", g_out, "ml");
#else
  check("ㅢ 뒤 다른 버튼 — 둘 다 대기", g_out, "m");
#endif
  run_for(tapWindow + 30);
  check("ㅢ + ㅏ 최종 결과", g_out, "mlk");

  // 4) 단일 탭은 윈도우가 만료돼야 확정 (연타 판정에 필요한 대기)
  reset_engine();
  tap(P_L1a);
  check("ㄱ 1탭 — 윈도우 내에는 미확정", g_out, "");
  run_for(tapWindow + 30);
  check("ㄱ 1탭 — 만료 후 확정", g_out, "r");

  // 5) 같은 버튼의 '별개 입력'(국가의 ㄱㄱ)은 윈도우 밖이면 따로 확정
  reset_engine();
  tap(P_L1a);
  run_for(tapWindow + 30);
  tap(P_L1a);
  run_for(tapWindow + 30);
  check("ㄱ+간격+ㄱ — 두 번 다 ㄱ", g_out, "rr");

  // 6) 디바운스: 너무 빠른 재접점(채터링)은 탭으로 세지 않는다
  reset_engine();
  g_pin_low[P_L1a] = true;  run_for(6);
  g_pin_low[P_L1a] = false; run_for(6);         // 12ms 후 재접점 → 무시되어야 함
  g_pin_low[P_L1a] = true;  run_for(6);
  g_pin_low[P_L1a] = false; run_for(6);
  run_for(tapWindow + 30);
  check("채터링(12ms 간격) — 1탭으로 처리", g_out, "r");

  // 7) 기능키: R5 3탭 = Enter 즉시 확정 / L5 = Backspace 1탭 즉시
  reset_engine();
  tap(R_PINS[7]); tap(R_PINS[7]); tap(R_PINS[7]);
  check("R5 3탭 — Enter 즉시", g_out, "\n");
  reset_engine();
  tap(L_PINS[7]);
  check("L5 — Backspace 즉시(maxTap 1)", g_out, "\b");

  // 8) 윈도우를 넘긴 2탭은 연타가 아니라 두 글자
  reset_engine();
  tap(P_R2b);
  run_for(tapWindow + 30);
  tap(P_R2b);
  run_for(tapWindow + 30);
  check("ㅜ+간격+ㅜ — ㅠ 아님", g_out, "nn");

  // 9) 다른 버튼을 사이에 둔 같은 버튼 입력이 연타로 잘못 합쳐지지 않는가
  //    (ㄱ ㅏ ㄱ 을 빠르게: EARLY_COMMIT이 없으면 두 ㄱ이 ㅋ으로 합쳐진다)
  reset_engine();
  tap(P_L1a); tap(P_R2a); tap(P_L1a);
  run_for(tapWindow + 30);
#if EARLY_COMMIT
  check("ㄱ+ㅏ+ㄱ 빠르게 — 각각 확정", g_out, "rkr");
#else
  check("ㄱ+ㅏ+ㄱ 빠르게 — ㅋ으로 잘못 합쳐짐(알려진 결함)", g_out, "zk");
#endif

  printf("\n%s (실패 %d건)\n", g_fail ? "FAILURES ABOVE" : "ALL OK", g_fail);
  return g_fail ? 1 : 0;
}
