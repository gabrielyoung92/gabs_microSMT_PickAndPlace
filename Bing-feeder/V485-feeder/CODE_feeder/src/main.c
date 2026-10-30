// Derived from MicroSMT/Bing-feeder V485 firmware. Local HAL/PlatformIO port.
// Original authors retain credit; see README.md and CHANGELOG.md.
//
// Entry point: initialise hardware before the drivers that depend on its
// clock/delays, then run the feeder application. No Arduino runtime is used.

#include "board.h"
#include "display.h"
#include "eeprom.h"
#include "feeder.h"
#include "boot.h"
#include "config.h"

// Fixed-offset tag lets the loader reject wrong-width or old unrelocated files.
__attribute__((used, section(".firmware_info")))
const struct { char magic[8]; uint32_t variant, base; } firmwareInfo = {
    "V485APP", FEEDER_VARIANT_ID, BOOT_APP_START
};

// Run once per millisecond, including during startup. HAL timeouts and the
// manual-trigger countdown must keep advancing while the main loop is blocked.
void SysTick_Handler(void) {
    HAL_IncTick();
    Feeder_Tick();
}

// Initialise in dependency order. Feeder_Init loads settings and enables feed
// interrupts; Board_Init already applies the selected variant's motor levels.
int main(void) {
    Board_Init();
    EEPROM_Init();
    Display_Init();
    Feeder_Init();
    while (1) {
        Feeder_Run();
        Board_WatchdogFeed();
    }
}
