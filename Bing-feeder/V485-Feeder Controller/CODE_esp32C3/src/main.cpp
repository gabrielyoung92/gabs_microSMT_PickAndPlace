// Adapted from MicroSMT/Bing-feeder: https://github.com/microsmt/Bing-feeder
// Changes by Gab with ChatGPT assistance; see CHANGELOG.md.
// USB commands select a feeder and count; RS485 ACKs report acceptance only.

#include <Arduino.h>
#include <ctype.h>
#include <string.h>
#include "config.h"

HardwareSerial Serial485(RS485_UART);

enum class AckResult { Accepted, Busy, Timeout, InvalidResponse };

uint32_t lastRunLedToggle = 0;
bool runLedState = false;
uint8_t flashTogglesLeft = 0;
bool flashLedOn = false;
uint32_t flashLastTick = 0;

char commandBuffer[USB_COMMAND_MAX_LENGTH + 1];
size_t commandLength = 0;
bool discardingCommand = false;
uint32_t lastCommandByteAt = 0;

// These handlers do not wait; call them while idle and while awaiting an ACK.
void updateRunLed() {
  uint32_t now = millis();
  if (now - lastRunLedToggle >= RUN_LED_INTERVAL) {
    lastRunLedToggle = now;
    runLedState = !runLedState;
    digitalWrite(RUN_LED_PIN, runLedState ? HIGH : LOW);
  }
}

void ledFlashStart() {
  flashLedOn = true;
  flashTogglesLeft = 3;  // Two on pulses: on -> off -> on -> off.
  flashLastTick = millis();
  digitalWrite(LED_PIN, HIGH);
}

void updateLedFlash() {
  if (flashTogglesLeft == 0) return;
  uint32_t now = millis();
  if (now - flashLastTick >= FLASH_INTERVAL) {
    flashLastTick = now;
    flashLedOn = !flashLedOn;
    digitalWrite(LED_PIN, flashLedOn ? HIGH : LOW);
    --flashTogglesLeft;
  }
}

// Accept spaces/tabs and the CR from a CRLF console line. LF ends the line.
bool commandSpace(char c) {
  return c == ' ' || c == '\t' || c == '\r';
}

void skipCommandSpace(const char*& cursor) {
  while (commandSpace(*cursor)) ++cursor;
}

bool parseField(const char*& cursor, char field, uint8_t& result) {
  if (toupper(static_cast<unsigned char>(*cursor)) != field) return false;
  ++cursor;
  if (*cursor < '0' || *cursor > '9') return false;
  unsigned value = 0;
  while (*cursor >= '0' && *cursor <= '9') {
    value = value * 10 + static_cast<unsigned>(*cursor - '0');
    if (value > 99) return false;  // Check each digit, before overflow is possible.
    ++cursor;
  }
  result = static_cast<uint8_t>(value);
  return true;
}

// Exact grammar: [M600 ]N<0..99> F<0..99>, case-insensitive, with whitespace.
// Reject unknown commands, duplicate fields, negative values and trailing tokens.
bool parseCommand(const char* input, uint8_t& address, uint8_t& count) {
  const char* cursor = input;
  skipCommandSpace(cursor);
  if (toupper(static_cast<unsigned char>(*cursor)) == 'M') {
    if (strncmp(cursor + 1, "600", 3) != 0) return false;
    cursor += 4;
    if (!commandSpace(*cursor)) return false;
    skipCommandSpace(cursor);
  }
  uint8_t parsedAddress = 0, parsedCount = 0;
  if (!parseField(cursor, 'N', parsedAddress)) return false;
  if (!commandSpace(*cursor)) return false;
  skipCommandSpace(cursor);
  if (!parseField(cursor, 'F', parsedCount)) return false;
  skipCommandSpace(cursor);
  if (*cursor != '\0') return false;
  address = parsedAddress;
  count = parsedCount;
  return true;
}

// Called only for a complete, bounded line. CRLF, surrounding whitespace and
// lowercase replies are accepted, but an incomplete or overlong line never is.
AckResult classifyAck(char* response) {
  char* start = response;
  while (commandSpace(*start)) ++start;
  size_t length = strlen(start);
  while (length > 0 && commandSpace(start[length - 1])) start[--length] = '\0';
  for (char* cursor = start; *cursor; ++cursor) {
    *cursor = static_cast<char>(toupper(static_cast<unsigned char>(*cursor)));
  }
  if (strcmp(start, "OK") == 0) return AckResult::Accepted;
  if (strcmp(start, "BUSY") == 0) return AckResult::Busy;
  return AckResult::InvalidResponse;
}

AckResult readAck() {
  char response[ACK_MAX_LENGTH + 1];
  size_t length = 0;
  bool invalid = false;
  uint32_t startedAt = millis();
  while (static_cast<uint32_t>(millis() - startedAt) < ACK_TIMEOUT_MS) {
    while (Serial485.available() > 0) {
      if (static_cast<uint32_t>(millis() - startedAt) >= ACK_TIMEOUT_MS) break;
      int incoming = Serial485.read();
      if (incoming < 0) break;
      char c = static_cast<char>(incoming);
      if (c == '\n') {
        if (invalid) return AckResult::InvalidResponse;
        response[length] = '\0';
        return classifyAck(response);
      }
      if (c == '\0' || length == ACK_MAX_LENGTH) {
        invalid = true;  // Discard overflow; never classify its truncated prefix.
      } else {
        response[length++] = c;
      }
    }
    updateRunLed();
    updateLedFlash();
    if (static_cast<uint32_t>(millis() - startedAt) >= ACK_TIMEOUT_MS) break;
    delay(1);  // Yield while waiting; the deadline includes these intervals.
  }
  return (length > 0 || invalid) ? AckResult::InvalidResponse : AckResult::Timeout;
}

// Send once. The feeder protocol has no transaction ID or duplicate protection,
// so losing an ACK must not automatically cause another physical feed.
AckResult sendCommandWithAck(uint8_t address, uint8_t count) {
  while (Serial485.available() > 0) Serial485.read();  // Discard queued old input.
  char command[16];
  int length = snprintf(command, sizeof(command), "N%u F%u\n",
                        static_cast<unsigned>(address), static_cast<unsigned>(count));
  if (length <= 0 || length >= static_cast<int>(sizeof(command))) {
    return AckResult::InvalidResponse;
  }

  digitalWrite(DE_RE_PIN, HIGH);
  delayMicroseconds(RS485_DIRECTION_SETTLE_US);
  Serial485.write(reinterpret_cast<const uint8_t*>(command), static_cast<size_t>(length));
  // In the pinned Arduino core, flush() waits for the UART transmitter to be
  // idle, including the last byte. Release DE immediately so replies can arrive.
  Serial485.flush();
  digitalWrite(DE_RE_PIN, LOW);
  delayMicroseconds(RS485_DIRECTION_SETTLE_US);
  return readAck();
}

void executeCommand(const char* line) {
  uint8_t address = 0, count = 0;
  if (!parseCommand(line, address, count)) {
    Serial.println("ERROR: expected N0..99 F0..99, optionally prefixed with M600.");
    return;
  }
  Serial.printf("Sending: N%u F%u\n", static_cast<unsigned>(address), static_cast<unsigned>(count));
  switch (sendCommandWithAck(address, count)) {
    case AckResult::Accepted:
      Serial.println("ACK: command accepted; tape movement has not been verified.");
      ledFlashStart();
      break;
    case AckResult::Busy:
      Serial.println("BUSY: feeder did not accept this command.");
      break;
    case AckResult::Timeout:
      Serial.println("ERROR: ACK timeout; command outcome unknown. Not retried.");
      break;
    case AckResult::InvalidResponse:
      Serial.println("ERROR: invalid/incomplete ACK; command outcome unknown. Not retried.");
      break;
  }
}

// Collect USB input without blocking. After overflow or timeout, discard through
// the next LF: a command tail must never become a separate movement command.
void readUsbCommands() {
  if (commandLength > 0 && !discardingCommand &&
      static_cast<uint32_t>(millis() - lastCommandByteAt) >= USB_COMMAND_TIMEOUT_MS) {
    commandLength = 0;
    discardingCommand = true;
    Serial.println("ERROR: incomplete USB command timed out; discard until newline.");
  }
  // Bound work per loop so a continuous USB stream cannot starve the indicators.
  for (size_t processed = 0; processed <= USB_COMMAND_MAX_LENGTH && Serial.available() > 0; ++processed) {
    int incoming = Serial.read();
    if (incoming < 0) break;
    char c = static_cast<char>(incoming);
    if (c == '\n') {
      if (!discardingCommand && commandLength > 0) {
        commandBuffer[commandLength] = '\0';
        executeCommand(commandBuffer);
      }
      commandLength = 0;
      discardingCommand = false;
      return;
    }
    if (discardingCommand) continue;
    if (c == '\0' || commandLength == USB_COMMAND_MAX_LENGTH) {
      commandLength = 0;
      discardingCommand = true;
      Serial.println("ERROR: invalid/overlong USB command; discard until newline.");
      continue;
    }
    commandBuffer[commandLength++] = c;
    lastCommandByteAt = millis();
  }
}

void setup() {
  Serial.begin(USB_BAUD);
  pinMode(DE_RE_PIN, OUTPUT);
  digitalWrite(DE_RE_PIN, LOW);
  pinMode(LED_PIN, OUTPUT);
  digitalWrite(LED_PIN, LOW);
  pinMode(RUN_LED_PIN, OUTPUT);
  digitalWrite(RUN_LED_PIN, LOW);
  lastRunLedToggle = millis();
  Serial485.begin(RS485_BAUD, SERIAL_8N1, RS485_RX_PIN, RS485_TX_PIN);
  Serial.printf("Gab's MicroSMT ESP32-C3 RS485 controller v%s (MicroSMT V25 base)\n", FIRMWARE_VERSION);
  Serial.println("Send N12 F4 or M600 N12 F4, followed by a newline. No automatic retries.");
}

void loop() {
  updateRunLed();
  updateLedFlash();
  readUsbCommands();
}
