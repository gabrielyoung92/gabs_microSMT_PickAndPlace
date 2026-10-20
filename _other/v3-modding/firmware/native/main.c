/* Keep the original behavioral suite usable without Make or a test framework. */
#define main feed_cycle_tests
#include "../../tests/test_feed_cycle.c"
#undef main
#include "../../tests/test_bus.c"
#include "../../tests/test_bridge.c"
int main(void) { (void)feed_cycle_tests(); bus_tests(); bridge_tests(); return 0; }
