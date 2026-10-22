// Derived from MicroSMT/Bing-feeder V485 firmware. Local HAL/PlatformIO port.
// Original authors retain credit; see README.md and CHANGELOG.md.
//
// Shared wiring and application settings for both PlatformIO environments.
// Change the build environment to choose width behaviour; pins/timings stay
// here. Clock/crystal and memory settings also involve platformio.ini/board.c.

#pragma once

#include "stm32f1xx_hal.h"

// Unreleased development firmware; no physical unit programmed or tested yet.
// Independent of upstream V26/V25. See CHANGELOG.md.
#define FIRMWARE_VERSION "0.1.0"

// Only the dedicated bootloader environments define this as 1.
#ifndef FEEDER_BOOTLOADER
#define FEEDER_BOOTLOADER 0
#endif
// Image personality is checked before erase and before application startup.
#define FEEDER_VARIANT_ID (FEEDER_WIDE + 1U)

// Selected by the PlatformIO environment, never by editing this header.
#ifndef FEEDER_WIDE
#error "Select a V485 feeder environment in platformio.ini"
#elif FEEDER_WIDE == 1
#define FEEDER_VARIANT "12-16-24mm"
#elif FEEDER_WIDE == 0
#define FEEDER_VARIANT "8mm"
#else
#error "FEEDER_WIDE must be 0 (8 mm) or 1 (12/16/24 mm)"
#endif

// Wider feeders may peel during normal idle; PA2 tension feedback gates it.
// Both variants remain stopped during startup, settings, updates and faults.

// Source wiring, using STM32 GPIO names. GPIO A/B clocks are enabled in board.c.
// LED sinks current: writing LOW lights it, HIGH turns it off.
#define LED_PORT GPIOB
#define LED_PIN GPIO_PIN_5
#define LED_ON() HAL_GPIO_WritePin(LED_PORT, LED_PIN, GPIO_PIN_RESET)
#define LED_OFF() HAL_GPIO_WritePin(LED_PORT, LED_PIN, GPIO_PIN_SET)

// Two motor channels: A=HIGH/B=LOW runs the indexed motor; both HIGH stops.
// Peel uses PA12=HIGH/PA8=LOW to run, gated by PA2 in the application tick.
#define MOTOR_PORT GPIOA
#define MOTOR_INDEX_A_PIN GPIO_PIN_6
#define MOTOR_INDEX_B_PIN GPIO_PIN_7
#define MOTOR_PEEL_A_PIN GPIO_PIN_8
#define MOTOR_PEEL_B_PIN GPIO_PIN_12
#define MOTOR_ALL_PINS (MOTOR_INDEX_A_PIN | MOTOR_INDEX_B_PIN | MOTOR_PEEL_A_PIN | MOTOR_PEEL_B_PIN)

// PA4 is the sole active-low button. PA2 now reads an isolated dry contact.
// COM -> GND, NC -> PA2: closed/slack permits peel; open/tension stops it.
// Remove or leave the old PA2 button unused. No motor voltage on this input.
#define BUTTON_PORT GPIOA
#define BUTTON_PIN GPIO_PIN_4
#define PEEL_SWITCH_PORT GPIOA
#define PEEL_SWITCH_PIN GPIO_PIN_2
#define PEEL_RUN_LEVEL GPIO_PIN_RESET
// Opening stops immediately; require a stable closed contact before restarting.
#define PEEL_DEBOUNCE_MS 20U
#define PEEL_RESTART_MS 100U
#define PEEL_TIMEOUT_MS 10000U

// Interrupt handlers are EXTI3 and EXTI9_5. Moving these pins also requires
// updating routing in board.c and handlers in feeder.c; don't change only the pin.
#define COUNT_PORT GPIOA
#define COUNT_PIN GPIO_PIN_3
#define TRIGGER_PORT GPIOB
#define TRIGGER_PIN GPIO_PIN_6

// USART1 uses PA9/PA10 without remapping. DE and /RE share PA1.
#define RS485_PORT GPIOA
#define RS485_TX_PIN GPIO_PIN_9
#define RS485_RX_PIN GPIO_PIN_10
#define RS485_DIR_PORT GPIOA
#define RS485_DIR_PIN GPIO_PIN_1
#define RS485_BAUD 9600U
// Bus-driver enable/disable margins are microseconds, unlike the ms settings.
#define RS485_DIRECTION_SETTLE_US 50U
// Let the host release TX direction before sending Busy/OK back to it.
#define ACK_TURNAROUND_MS 20U

// 24C02 software I2C: external pull-ups are required.
#define I2C_PORT GPIOB
#define I2C_SCL_PIN GPIO_PIN_15
#define I2C_SDA_PIN GPIO_PIN_14
// Full address bytes for the software bus; the low bit selects write/read.
// Stored offsets stay compatible with the vendor firmware.
#define EEPROM_ADDR_W 0xA0U
#define EEPROM_ADDR_R 0xA1U
#define EEPROM_DATA_ADDR 0x00U
#define EEPROM_COUNT_ADDR 0x01U

// CH455 two-wire display connection and command bytes.
#define CH455_SCL_PORT GPIOB
#define CH455_SCL_PIN GPIO_PIN_12
#define CH455_SDA_PORT GPIOB
#define CH455_SDA_PIN GPIO_PIN_13
#define CH455_SYS_CMD 0x48U
#define CH455_DIG0_WR 0x68U
#define CH455_DIG1_WR 0x6AU
#define CH455_DIG2_WR 0x6CU
#define CH455_DIG3_WR 0x6EU

// Application limits/defaults and timing, in milliseconds unless noted.
// Includes the line buffer's terminating NUL; the UART ring is separate.
// Update DATA frames carry up to 32 bytes as hex plus destination/CRC.
// Both images share framing; every feeder can safely discard other IDs.
#define RX_BUFFER_SIZE 96U
#define RS485_RX_BUF_SIZE 256U
// Total feed deadline, enforced by SysTick. Validate for the slowest intended
// count/load on real hardware. Timeout stops BOTH motors and latches until reset.
#define FEED_TIMEOUT_MS 10000U
// CH455 segment mask for E: the main loop shows EE on a latched timeout fault.
#define DISPLAY_ERROR_SEGMENTS 0xF2U
// Debounced PA4: tap advances; hold cycles menu 01..04; release selects.
// In an editor, hold then release to save. Inactivity discards unsaved edits.
#define BUTTON_DEBOUNCE_MS 25U
#define BUTTON_HOLD_MS 2000U
#define UI_TIMEOUT_MS 20000U
#define UI_BLINK_MS 400U
// Additional PA4 manual-feed inhibition, counted down by SysTick.
#define MANUAL_TRIGGER_MUTE_MS 300U
// Address/command F range is 0..99; F0 selects the stored positive count.
// Default-count adjustment and EEPROM loading require COUNT_MIN..VALUE_MAX.
#define VALUE_MIN 0
#define VALUE_MAX 99
#define COUNT_MIN 1U
// Used only if the EEPROM byte is missing/invalid; valid saved values win.
#define DEFAULT_ADDRESS 0U
#define DEFAULT_COUNT 1U

// Invalid configuration must fail at build time rather than disable the guard.
_Static_assert(COUNT_MIN >= 1U && DEFAULT_COUNT >= COUNT_MIN && DEFAULT_COUNT <= VALUE_MAX,
               "Default feed count must be positive and fit the two-digit display");
_Static_assert(FEED_TIMEOUT_MS > 0U && FEED_TIMEOUT_MS < 0x80000000U,
               "Feed timeout must be a positive interval below half the tick range");

_Static_assert(PEEL_TIMEOUT_MS > 0U && PEEL_TIMEOUT_MS < 0x80000000U &&
               PEEL_DEBOUNCE_MS > 0U && PEEL_RESTART_MS >= PEEL_DEBOUNCE_MS,
               "Peel debounce/restart/deadline configuration is invalid");
