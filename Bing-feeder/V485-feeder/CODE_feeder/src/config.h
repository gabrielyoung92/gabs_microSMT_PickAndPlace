// Derived from MicroSMT/Bing-feeder V485 firmware. Local HAL/PlatformIO port.
// Original authors retain credit; see README.md and CHANGELOG.md.
//
// Shared wiring and application settings for the universal firmware.
// Feeder width is saved at commissioning; pins/timings stay
// here. Clock/crystal and memory settings also involve platformio.ini/board.c.

#pragma once

#include "stm32f1xx_hal.h"

// Unreleased development firmware; initial startup, display and RS485 updates checked on one board.
// Independent of upstream V26/V25. See CHANGELOG.md.
#define FIRMWARE_VERSION "0.1.2"

// Only the dedicated bootloader environments define this as 1.
#ifndef FEEDER_BOOTLOADER
#define FEEDER_BOOTLOADER 0
#endif
// One image for every feeder width; physical type is a checked EEPROM setting.
#define FEEDER_VARIANT_ID 3U
#define FEEDER_VARIANT "universal"
static inline uint8_t Feeder_TypeValid(uint32_t width) {
    return width == 8U || width == 12U || width == 16U || width == 24U;
}

// 8 mm finishes a feed-triggered peel cycle at tension, including after indexing.
// Wider feeders may take up during idle. Menus/tests/faults inhibit both motors.

// Source wiring, using STM32 GPIO names. GPIO A/B clocks are enabled in board.c.
// LED sinks current: writing LOW lights it, HIGH turns it off.
#define LED_PORT GPIOB
#define LED_PIN GPIO_PIN_5
#define LED_ON() HAL_GPIO_WritePin(LED_PORT, LED_PIN, GPIO_PIN_RESET)
#define LED_OFF() HAL_GPIO_WritePin(LED_PORT, LED_PIN, GPIO_PIN_SET)

// Two motor channels: A=HIGH/B=LOW runs the indexed motor; both HIGH stops.
// Peel uses PA12=HIGH/PA8=LOW to run, gated by PB6 in the application tick.
#define MOTOR_PORT GPIOA
#define MOTOR_INDEX_A_PIN GPIO_PIN_6
#define MOTOR_INDEX_B_PIN GPIO_PIN_7
#define MOTOR_PEEL_A_PIN GPIO_PIN_8
#define MOTOR_PEEL_B_PIN GPIO_PIN_12
#define MOTOR_ALL_PINS (MOTOR_INDEX_A_PIN | MOTOR_INDEX_B_PIN | MOTOR_PEEL_A_PIN | MOTOR_PEEL_B_PIN)

// Retain both active-low board buttons: PA4 feed, PA2 settings/update menu.
// PB6 replaces the unused external trigger with an isolated dry contact.
// COM -> GND, NC -> PB6: closed/slack permits peel; open/tension stops it.
// Keep the existing PB6 pull-up/filter. No motor voltage on this input.
#define BUTTON_PORT GPIOA
#define BUTTON_PIN GPIO_PIN_4
#define MENU_BUTTON_PORT GPIOA
#define MENU_BUTTON_PIN GPIO_PIN_2
#define PEEL_SWITCH_PORT GPIOB
#define PEEL_SWITCH_PIN GPIO_PIN_6
// NC default requests peel at LOW; EEPROM NO mode requests it at HIGH.
// Removing the run request stops immediately; debounce requests before restarting.
#define PEEL_DEBOUNCE_MS 20U
#define PEEL_RESTART_MS 100U
#define PEEL_TIMEOUT_MS 10000U

// Only the PA3 index counter uses EXTI. PB6 is sampled, never a feed trigger.
#define COUNT_PORT GPIOA
#define COUNT_PIN GPIO_PIN_3

// USART1 uses PA9/PA10 without remapping. DE and /RE share PA1.
#define RS485_PORT GPIOA
#define RS485_TX_PIN GPIO_PIN_9
#define RS485_RX_PIN GPIO_PIN_10
#define RS485_DIR_PORT GPIOA
#define RS485_DIR_PIN GPIO_PIN_1
#define RS485_BAUD 115200U
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
#define EEPROM_TYPE_ADDR 0x02U
#define EEPROM_TYPE_CHECK_ADDR 0x03U
// Versioned motor/switch record; boot metadata begins at 0x1F.
#define EEPROM_OPTIONS_ADDR 0x04U
#define EEPROM_OPTIONS_CHECK_ADDR 0x05U
#define EEPROM_OPTIONS_VERSION_ADDR 0x06U
#define OPTIONS_VERSION 0xA1U
#define OPTION_FEED_REVERSE 0x01U
#define OPTION_PEEL_REVERSE 0x02U
#define OPTION_SWITCH_NO 0x04U
#define OPTIONS_MASK 0x07U

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
// Item moves carry a full 32-bit event target, with independent stall/total guards.
#define JOG_MAX_EVENTS 10000U
#define JOG_STALL_TIMEOUT_MS 3000U
#define JOG_STARTUP_BUDGET_MS 2000U
#define JOG_EVENT_BUDGET_MS 1000U
#define JOG_MAX_DURATION_MS (JOG_STARTUP_BUDGET_MS + JOG_MAX_EVENTS * JOG_EVENT_BUDGET_MS)
// CH455 segment mask for E; the display driver pairs it with a fault number.
#define DISPLAY_ERROR_SEGMENTS 0xF2U
// Runtime E1=index deadline, E2=peel deadline, E3=settings read/write failure.
#define FAULT_NONE 0U
#define FAULT_INDEX 1U
#define FAULT_PEEL 2U
#define FAULT_SETTINGS 3U
#define FAULT_STOP 4U
// Debounced PA4 tap advances; PA2 hold cycles menu 01..05; release selects.
// In an editor, hold then release to save. Inactivity discards unsaved edits.
#define BUTTON_DEBOUNCE_MS 25U
#define BUTTON_HOLD_MS 2000U
#define UI_TIMEOUT_MS 20000U
#define UI_BLINK_MS 400U
// Additional PA4 manual-feed inhibition, counted down by SysTick.
#define MANUAL_TRIGGER_MUTE_MS 300U
// Operating IDs are 1..99. ID 0 means unassigned and cannot drive either motor.
// The commissioning/update transport may still address 0. F0 uses saved count.
// Default-count adjustment and EEPROM loading require COUNT_MIN..VALUE_MAX.
#define ADDRESS_MIN 1
#define VALUE_MAX 99
#define COUNT_MIN 1U
// Used only if the EEPROM byte is missing/invalid; valid saved values win.
#define DEFAULT_ADDRESS 0U
#define DEFAULT_COUNT 1U
#define DEFAULT_COUNT_8MM 2U
#define DEFAULT_OPTIONS_8MM OPTION_FEED_REVERSE

// Invalid configuration must fail at build time rather than disable the guard.
_Static_assert(COUNT_MIN >= 1U && DEFAULT_COUNT >= COUNT_MIN && DEFAULT_COUNT <= VALUE_MAX &&
               DEFAULT_COUNT_8MM >= COUNT_MIN && DEFAULT_COUNT_8MM <= VALUE_MAX,
               "Default feed count must be positive and fit the two-digit display");
_Static_assert(FEED_TIMEOUT_MS > 0U && FEED_TIMEOUT_MS < 0x80000000U,
               "Feed timeout must be a positive interval below half the tick range");

_Static_assert(PEEL_TIMEOUT_MS > 0U && PEEL_TIMEOUT_MS < 0x80000000U &&
               PEEL_DEBOUNCE_MS > 0U && PEEL_RESTART_MS >= PEEL_DEBOUNCE_MS,
               "Peel debounce/restart/deadline configuration is invalid");

_Static_assert(JOG_MAX_EVENTS > 99U && JOG_MAX_EVENTS <= 10000U &&
               JOG_STALL_TIMEOUT_MS > 0U && JOG_STALL_TIMEOUT_MS < 0x80000000U &&
               JOG_EVENT_BUDGET_MS > 0U && JOG_MAX_DURATION_MS < 0x80000000U,
               "Item move bounds/deadlines must fit wrap-safe 32-bit counters");
