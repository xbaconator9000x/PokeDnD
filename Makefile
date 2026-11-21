CC ?= cc
CFLAGS ?= -std=c99 -O2 -Wall -Wextra -Werror -pedantic
CPPFLAGS ?= -Iinclude
.PHONY: test demo clean
test: build/test_d20 build/test_d20_field
	./build/test_d20
	./build/test_d20_field
demo: build/demo
	./build/demo
build/test_d20: src/d20.c include/d20.h tests/test_d20.c
	mkdir -p build
	$(CC) $(CPPFLAGS) $(CFLAGS) src/d20.c tests/test_d20.c -o $@
build/test_d20_field: src/d20.c src/d20_field.c include/d20_field.h include/d20.h tests/test_d20_field.c
	mkdir -p build
	$(CC) $(CPPFLAGS) $(CFLAGS) src/d20.c src/d20_field.c tests/test_d20_field.c -o $@
build/demo: src/d20.c include/d20.h examples/demo.c
	mkdir -p build
	$(CC) $(CPPFLAGS) $(CFLAGS) src/d20.c examples/demo.c -o $@
clean:
	rm -rf build
