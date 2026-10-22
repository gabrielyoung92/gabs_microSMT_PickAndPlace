// Adapted from MicroSMT/Bing-feeder: https://github.com/microsmt/Bing-feeder
// Changes by Gab with ChatGPT assistance; see CHANGELOG.md.
// USB carries feed commands and the local addressed/CRC32 update protocol.

#include <Arduino.h>
#include <esp_system.h>
#include <ctype.h>
#include <string.h>
#include "config.h"

HardwareSerial Serial485(RS485_UART);

enum class AckResult { Accepted, Busy, Running, Done, Fault, Unknown, Timeout, InvalidResponse };
const struct { const char* name; AckResult result; } feedReplies[] = {
  {"ACCEPT", AckResult::Accepted}, {"BUSY", AckResult::Busy},
  {"RUNNING", AckResult::Running}, {"DONE", AckResult::Done},
  {"FAULT", AckResult::Fault}, {"UNKNOWN", AckResult::Unknown}
};

uint32_t lastRunLedToggle = 0;
bool runLedState = false;
uint8_t flashTogglesLeft = 0;
bool flashLedOn = false;
uint32_t flashLastTick = 0;

char commandBuffer[UPDATE_PACKET_MAX_LENGTH + 1];
size_t commandLength = 0;
bool discardingCommand = false;
uint32_t lastCommandByteAt = 0;
char updateReply[UPDATE_PACKET_MAX_LENGTH + 1];
size_t updateReplyLength = 0;
bool discardingUpdateReply = false;
bool updateTrafficSeen = false;
uint32_t lastUpdateAt = 0;
uint32_t feedSession = 0;
uint32_t feedSequence = 0;

bool validUpdatePacket(const char* line, bool request);

uint32_t packetCrc32(const char* data, size_t size) {
  uint32_t crc = 0xFFFFFFFFU;
  for (size_t i = 0; i < size; ++i) {
    crc ^= static_cast<uint8_t>(data[i]);
    for (uint8_t bit = 0; bit < 8; ++bit)
      crc = (crc >> 1) ^ (0xEDB88320U & (0U - (crc & 1U)));
  }
  return ~crc;
}

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

// Exact grammar: [M600 ]N<1..99> F<0..99>, case-insensitive, with whitespace.
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
  if (*cursor != '\0' || parsedAddress == 0) return false;
  address = parsedAddress;
  count = parsedCount;
  return true;
}

// A bare OK, another feeder's reply or a previous request can never confirm a feed.
AckResult classifyAck(const char* response, uint8_t address, uint32_t session, uint32_t sequence) {
  if (!validUpdatePacket(response, false)) return AckResult::InvalidResponse;
  for (const auto& status : feedReplies) {
    char expected[64];
    int length = snprintf(expected, sizeof(expected), "B%02u %s %08lX %08lX",
                          static_cast<unsigned>(address), status.name,
                          static_cast<unsigned long>(session), static_cast<unsigned long>(sequence));
    size_t size = strlen(response);
    if (size && response[size - 1] == '\r') --size;
    if (length > 0 && size == static_cast<size_t>(length) + 9 &&
        memcmp(response, expected, static_cast<size_t>(length)) == 0)
      return status.result;
  }
  return AckResult::InvalidResponse;
}

AckResult readAck(uint8_t address, uint32_t session, uint32_t sequence) {
  char response[ACK_MAX_LENGTH + 1];
  size_t length = 0;
  bool invalid = false;
  bool sawInvalid = false;
  uint32_t startedAt = millis();
  while (static_cast<uint32_t>(millis() - startedAt) < ACK_TIMEOUT_MS) {
    while (Serial485.available() > 0) {
      if (static_cast<uint32_t>(millis() - startedAt) >= ACK_TIMEOUT_MS) break;
      int incoming = Serial485.read();
      if (incoming < 0) break;
      char c = static_cast<char>(incoming);
      if (c == '\n') {
        if (!invalid) {
          response[length] = '\0';
          AckResult result = classifyAck(response, address, session, sequence);
          if (result != AckResult::InvalidResponse) return result;
        }
        sawInvalid = true;
        length = 0;
        invalid = false;
        continue;
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
  return (length > 0 || invalid || sawInvalid) ? AckResult::InvalidResponse : AckResult::Timeout;
}

// Release the half-duplex bus only after the complete line's final stop bit.
void sendRs485(const char* line, size_t length) {
  digitalWrite(DE_RE_PIN, HIGH);
  delayMicroseconds(RS485_DIRECTION_SETTLE_US);
  Serial485.write(reinterpret_cast<const uint8_t*>(line), length);
  Serial485.write('\n');
  // In the pinned Arduino core, flush() waits for the UART transmitter to be
  // idle, including the last byte. Release DE immediately so replies can arrive.
  Serial485.flush();
  digitalWrite(DE_RE_PIN, LOW);
  delayMicroseconds(RS485_DIRECTION_SETTLE_US);
}

// Validate the existing Bdd <body> <CRC32> framing, including destination.
// Keep bytes unchanged; only a final CR is excluded from CRC as on the feeder.
bool validUpdatePacket(const char* line, bool request) {
  size_t length = strlen(line);
  if (length > UPDATE_PACKET_MAX_LENGTH) return false;
  if (length && line[length - 1] == '\r') --length;
  if (length < 14 || line[0] != 'B' || line[1] < '0' || line[1] > '9' ||
      line[2] < '0' || line[2] > '9' || line[3] != ' ' || line[length - 9] != ' ') return false;
  for (size_t i = 0; i < length; ++i) {
    if (line[i] < ' ' || line[i] > '~') return false;
  }
  uint32_t expected = 0;
  for (size_t i = length - 8; i < length; ++i) {
    char ch = line[i];
    uint8_t digit;
    if (ch >= '0' && ch <= '9') digit = ch - '0';
    else if (ch >= 'A' && ch <= 'F') digit = ch - 'A' + 10;
    else if (ch >= 'a' && ch <= 'f') digit = ch - 'a' + 10;
    else return false;
    expected = (expected << 4) | digit;
  }
  if (packetCrc32(line, length - 9) != expected) return false;
  if (!request) return true;  // Uploader checks reply ID, label and DATA offset.
  const char* commands[] = {"INFO", "BOOT", "HELLO", "BEGIN", "DATA", "END", "IDENT", "SETID"};
  size_t bodyLength = length - 13;
  for (const char* command : commands) {
    size_t size = strlen(command);
    if (bodyLength >= size && memcmp(line + 4, command, size) == 0 &&
        (bodyLength == size || line[4 + size] == ' ')) return true;
  }
  return false;
}

bool updateActive() {
  if (updateTrafficSeen &&
      static_cast<uint32_t>(millis() - lastUpdateAt) >= UPDATE_IDLE_TIMEOUT_MS) updateTrafficSeen = false;
  return updateTrafficSeen;
}

// Feed replies carry two request tokens; loader DONE carries only one CRC.
bool isFeedReply(const char* line) {
  size_t length = strlen(line);
  if (length && line[length - 1] == '\r') --length;
  for (const auto& status : feedReplies) {
    size_t size = strlen(status.name);
    if (length == 4 + size + 18 + 9 && !memcmp(line + 4, status.name, size) && line[4 + size] == ' ')
      return true;
  }
  return false;
}

// No request timeout or retries here: the existing PC uploader owns those.
// Drain complete CRC-valid replies continuously, including late acknowledgements.
void readUpdateReplies() {
  for (size_t processed = 0; processed <= UPDATE_PACKET_MAX_LENGTH && Serial485.available() > 0; ++processed) {
    int incoming = Serial485.read();
    if (incoming < 0) break;
    char c = static_cast<char>(incoming);
    if (c == '\n') {
      if (!discardingUpdateReply && updateReplyLength > 0) {
        updateReply[updateReplyLength] = '\0';
        // Late feed acknowledgements are not update traffic or USB console replies.
        if (validUpdatePacket(updateReply, false) && !isFeedReply(updateReply)) {
          Serial.write(reinterpret_cast<const uint8_t*>(updateReply), updateReplyLength);
          Serial.write('\n');
          updateTrafficSeen = true;
          lastUpdateAt = millis();
        }
      }
      updateReplyLength = 0;
      discardingUpdateReply = false;
    } else if (!discardingUpdateReply) {
      if (c == '\0' || updateReplyLength == UPDATE_PACKET_MAX_LENGTH) {
        updateReplyLength = 0;
        discardingUpdateReply = true;
      } else updateReply[updateReplyLength++] = c;
    }
  }
}

// Send FEED once, then poll its retained result. A lost ACCEPT or STATUS reply
// may cause another read-only STATUS request, never another tape advance.
AckResult sendCommandWithAck(uint8_t address, uint8_t count) {
  while (Serial485.available() > 0) Serial485.read();  // Discard queued old input.
  if (++feedSequence == 0) { feedSession = esp_random(); ++feedSequence; }
  char command[80];
  int length = snprintf(command, sizeof(command), "B%02u FEED %08lX %08lX %08lX",
                        static_cast<unsigned>(address), static_cast<unsigned long>(feedSession),
                        static_cast<unsigned long>(feedSequence), static_cast<unsigned long>(count));
  if (length <= 0 || length + 9 >= static_cast<int>(sizeof(command))) return AckResult::InvalidResponse;
  uint32_t crc = packetCrc32(command, static_cast<size_t>(length));
  snprintf(command + length, sizeof(command) - static_cast<size_t>(length), " %08lX", static_cast<unsigned long>(crc));
  sendRs485(command, static_cast<size_t>(length) + 9);
  uint32_t startedAt = millis();
  AckResult result = readAck(address, feedSession, feedSequence);
  while (static_cast<uint32_t>(millis() - startedAt) < FEED_COMPLETION_TIMEOUT_MS) {
    if (result == AckResult::Done || result == AckResult::Busy ||
        result == AckResult::Fault || result == AckResult::Unknown) return result;
    length = snprintf(command, sizeof(command), "B%02u STATUS %08lX %08lX",
                      static_cast<unsigned>(address), static_cast<unsigned long>(feedSession),
                      static_cast<unsigned long>(feedSequence));
    crc = packetCrc32(command, static_cast<size_t>(length));
    snprintf(command + length, sizeof(command) - static_cast<size_t>(length), " %08lX", static_cast<unsigned long>(crc));
    sendRs485(command, static_cast<size_t>(length) + 9);
    result = readAck(address, feedSession, feedSequence);
    if (result == AckResult::Running || result == AckResult::Accepted ||
        result == AckResult::Timeout || result == AckResult::InvalidResponse) {
      updateRunLed();
      updateLedFlash();
      delay(FEED_STATUS_INTERVAL_MS);
    }
  }
  return AckResult::Timeout;
}

void executeCommand(const char* line) {
  if (line[0] == 'B') {
    if (validUpdatePacket(line, true)) {
      updateTrafficSeen = true;
      lastUpdateAt = millis();
      sendRs485(line, strlen(line));
    }
    return;  // Invalid update packets never become feeds or receive fake ACKs.
  }
  uint8_t address = 0, count = 0;
  if (!parseCommand(line, address, count)) {
    Serial.println("error: expected N1..99 F0..99, optionally prefixed with M600.");
    return;
  }
  if (updateActive()) {
    Serial.println("error: update/settings traffic active; wait 10 seconds after closing tool.");
    return;
  }
  switch (sendCommandWithAck(address, count)) {
    case AckResult::Done:
      Serial.printf("ok N%u F%u\n", static_cast<unsigned>(address), static_cast<unsigned>(count));
      ledFlashStart();
      break;
    case AckResult::Busy:
      Serial.println("error: feeder busy; advance rejected.");
      break;
    case AckResult::Fault:
      Serial.println("error: feeder fault; advance incomplete. Inspect feeder before resetting.");
      break;
    case AckResult::Unknown:
      Serial.println("error: feeder has no result for this request; outcome unknown. Not retried.");
      break;
    default:
      Serial.println("error: completion timeout; advance outcome unknown. Not retried.");
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
    Serial.println("error: incomplete USB command timed out; discard until newline.");
  }
  // Bound work per loop so a continuous USB stream cannot starve the indicators.
  for (size_t processed = 0; processed <= UPDATE_PACKET_MAX_LENGTH && Serial.available() > 0; ++processed) {
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
    size_t limit = commandLength && commandBuffer[0] == 'B' ? UPDATE_PACKET_MAX_LENGTH : USB_COMMAND_MAX_LENGTH;
    if (c == '\0' || commandLength == limit) {
      commandLength = 0;
      discardingCommand = true;
      Serial.println("error: invalid/overlong USB command; discard until newline.");
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
  feedSession = esp_random();
  Serial485.begin(RS485_BAUD, SERIAL_8N1, RS485_RX_PIN, RS485_TX_PIN);
  Serial.printf("Gab's MicroSMT ESP32-C3 RS485 controller v%s (MicroSMT V25 base)\n", FIRMWARE_VERSION);
  Serial.println("Send N12 F4 or M600 N12 F4; ok follows confirmed index completion. Feeds are never retried.");
  Serial.println("Addressed Bdd update packets are forwarded between USB and RS485.");
}

void loop() {
  updateRunLed();
  updateLedFlash();
  (void)updateActive();  // Expire even while USB is idle, before millis() wraps again.
  readUpdateReplies();
  readUsbCommands();
}
