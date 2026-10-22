#pragma once

#include <stdint.h>

// Unreleased development firmware; no physical unit programmed or tested yet.
// Based on MicroSMT V25. See CHANGELOG.md.
constexpr char FIRMWARE_VERSION[] = "0.1.0";

// MicroSMT's original wiring. Numbers are GPIOs, not header positions.
constexpr uint8_t DE_RE_PIN = 9;    // HIGH: transmit; LOW: receive. Also BOOT.
constexpr uint8_t LED_PIN = 7;      // ACK indicator; firmware drives HIGH for on.
constexpr uint8_t RUN_LED_PIN = 8;  // Run indicator; firmware toggles the output.
constexpr uint8_t RS485_RX_PIN = 20;
constexpr uint8_t RS485_TX_PIN = 21;

// UART0 carries RS485; the command console uses native USB via platformio.ini.
constexpr uint8_t RS485_UART = 0;
constexpr uint32_t RS485_BAUD = 9600;
constexpr uint32_t USB_BAUD = 115200;  // Match monitor_speed in platformio.ini.

// LED intervals in milliseconds per toggle/phase.
constexpr uint32_t RUN_LED_INTERVAL = 250;  // Full blink period: 500 ms.
constexpr uint32_t FLASH_INTERVAL = 100;

// Time allowed for a complete ACK after releasing the RS485 transmitter.
// Motion commands are sent ONCE: a missing ACK does not prove a failed feed.
constexpr uint32_t ACK_TIMEOUT_MS = 300;
// Feeder's default motor deadline is 10 s. Leave time for final STATUS replies.
constexpr uint32_t FEED_COMPLETION_TIMEOUT_MS = 12000;
constexpr uint32_t FEED_STATUS_INTERVAL_MS = 100;
constexpr uint32_t RS485_DIRECTION_SETTLE_US = 50;

// Reject incomplete USB input after this inter-byte gap; require a fresh line.
constexpr uint32_t USB_COMMAND_TIMEOUT_MS = 1000;

// Maximum bytes before LF, excluding the terminating NUL in our buffers.
constexpr uint8_t USB_COMMAND_MAX_LENGTH = 32;
constexpr uint8_t ACK_MAX_LENGTH = 79;

// USB bridge capacity. Current feeder DATA requests use 91 bytes before LF.
constexpr uint8_t UPDATE_PACKET_MAX_LENGTH = 127;
// Block feeds until update traffic has been idle this long. No motion retries.
constexpr uint32_t UPDATE_IDLE_TIMEOUT_MS = 10000;
