PS5_HOST ?= 192.168.1.197
PS5_PORT ?= 9021

ifdef PS5_PAYLOAD_SDK
include $(PS5_PAYLOAD_SDK)/toolchain/prospero.mk
else
$(error PS5_PAYLOAD_SDK is undefined)
endif

CFLAGS := -Wall -O2

all: c09diag.elf c09go.elf c09dump.elf

c09diag.elf: main.c
	$(CC) $(CFLAGS) -o $@ $^

c09go.elf: go.c
	$(CC) $(CFLAGS) -o $@ $^ -lSceSystemService

c09dump.elf: dump.c
	$(CC) $(CFLAGS) -o $@ $^ -lSceSystemService

clean:
	rm -f c09diag.elf c09go.elf c09dump.elf
