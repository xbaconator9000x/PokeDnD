DEVKITPRO ?= /opt/devkitpro
DEVKITARM ?= $(DEVKITPRO)/devkitARM
CC := $(DEVKITARM)/bin/arm-none-eabi-gcc
OBJCOPY := $(DEVKITARM)/bin/arm-none-eabi-objcopy
GBAFIX := $(DEVKITPRO)/tools/bin/gbafix
CFLAGS := -std=c99 -O2 -Wall -Wextra -Werror -mcpu=arm7tdmi -mthumb -mthumb-interwork -I../include
LINKFLAGS := -mthumb -mthumb-interwork -specs=gba.specs
.PHONY: all clean
all: build/pokednd-poc.gba
build/pokednd-poc.elf: main.c ../src/d20.c ../include/d20.h
	mkdir -p build
	$(CC) $(CFLAGS) main.c ../src/d20.c $(LINKFLAGS) -o $@
build/pokednd-poc.gba: build/pokednd-poc.elf
	$(OBJCOPY) -O binary $< $@
	$(GBAFIX) $@ -tPOKEDND -cPD20 -m00
clean:
	rm -rf build
