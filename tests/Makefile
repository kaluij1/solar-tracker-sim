CC     ?= gcc
CFLAGS  = -std=c11 -O2 -Wall -Wno-attributes -Wno-unused-function -U_FORTIFY_SOURCE -I.

closed_loop_test: closed_loop_test.c ../wokwi/sun-sensor-head.chip.c wokwi-api.h
	$(CC) $(CFLAGS) -include wokwi-api.h -Dprintf=chip_log -c ../wokwi/sun-sensor-head.chip.c -o chip.o
	$(CC) $(CFLAGS) -include wokwi-api.h -c closed_loop_test.c -o test.o
	$(CC) -o $@ test.o chip.o -lm

.PHONY: test clean
test: closed_loop_test
	./closed_loop_test

clean:
	rm -f closed_loop_test *.o
