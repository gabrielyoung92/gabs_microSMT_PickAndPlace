CC ?= cc
ARM_CC ?= arm-none-eabi-gcc
PYTHON ?= python3
WARNINGS := -Wall -Wextra -Werror -Wpedantic -Wconversion -Wshadow
CORE := firmware/feeder/feed_cycle.c
HEADER := firmware/feeder/feed_cycle.h
INCLUDES := -Ifirmware/feeder -Ifirmware/bridge

.PHONY: check test arm-check
check: test

test: build/test_feed_cycle build/test_bus build/test_wifi
	# LeakSanitizer cannot run under the task runner's ptrace; this core has no heap.
	ASAN_OPTIONS=detect_leaks=0 ./build/test_feed_cycle
	ASAN_OPTIONS=detect_leaks=0 ./build/test_bus
	ASAN_OPTIONS=detect_leaks=0 ./build/test_wifi
	$(PYTHON) -m unittest discover -s tests -p test_bus_client.py

build/test_feed_cycle: $(CORE) $(HEADER) tests/test_feed_cycle.c Makefile | build
	$(CC) -std=c11 $(WARNINGS) -O1 -g -fsanitize=address,undefined $(INCLUDES) $(CORE) tests/test_feed_cycle.c -o $@

arm-check: build/feed_cycle.arm.o build/controller.arm.o
	@echo "Cortex-M3 core object compiled; no target image or board validation."

build/feed_cycle.arm.o: $(CORE) $(HEADER) Makefile | build
	$(ARM_CC) -std=c11 $(WARNINGS) -Os -mcpu=cortex-m3 -mthumb -ffreestanding -fno-builtin $(INCLUDES) -c $(CORE) -o $@

build/controller.arm.o: firmware/bridge/controller.c firmware/bridge/controller.h firmware/common/bus_packet.h Makefile | build
	$(ARM_CC) -std=c11 $(WARNINGS) -Os -mcpu=cortex-m3 -mthumb -ffreestanding -fno-builtin -Ifirmware/common $(INCLUDES) -c $< -o $@

build:
	mkdir -p build

# The shared native runner includes the original cycle suite plus bus checks.
build/test_bus: firmware/bridge/controller.c firmware/bridge/controller.h tests/test_bridge.c firmware/common/bus_packet.c firmware/common/bus_packet.h firmware/common/softwire.c firmware/common/softwire.h firmware/feeder/node.c firmware/feeder/node.h firmware/native/main.c tests/test_bus.c tests/test_feed_cycle.c $(CORE) $(HEADER) Makefile | build
	$(CC) -std=c11 $(WARNINGS) -O1 -g -fsanitize=address,undefined -Ifirmware/common $(INCLUDES) firmware/common/*.c firmware/bridge/controller.c $(CORE) firmware/feeder/node.c firmware/native/main.c -o $@

build/test_wifi: tests/test_wifi.c tests/fakes/pico/cyw43_arch.h tests/fakes/pico/stdlib.h tests/fakes/lwip/tcp.h firmware/bridge/pico/wifi.c firmware/bridge/pico/wifi.h Makefile | build
	$(CC) -std=c11 $(WARNINGS) -O1 -g -fsanitize=address,undefined -Itests/fakes tests/test_wifi.c -o $@
