# 보드 없이 펌웨어 연타 엔진을 검사한다.
#   make        기본 설정(EARLY_COMMIT=1) 검사
#   make both   EARLY_COMMIT 켠/끈 동작을 모두 검사
CXXFLAGS = -std=c++17 -Istub -Wall

test: test_tap_engine
	./test_tap_engine

test_tap_engine: test_tap_engine.cpp ../keyboard_glove.ino
	$(CXX) $(CXXFLAGS) -o $@ $<

both: test
	$(CXX) $(CXXFLAGS) -DEARLY_COMMIT=0 -o test_tap_engine_noearly test_tap_engine.cpp
	./test_tap_engine_noearly

clean:
	rm -f test_tap_engine test_tap_engine_noearly t0 t1
.PHONY: test both clean
