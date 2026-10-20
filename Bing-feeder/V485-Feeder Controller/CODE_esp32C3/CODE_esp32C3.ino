// ============================================================
//  ESP32-C3 RS485 Host (Master) Firmware V25
//  Features:
//    1. Read manually entered commands from USB serial (e.g. "M600 N12 F4")
//    2. Parse N (address) and F (count/parameter)
//    3. Send to the slave (Feeder) at the specified address via RS485
//    4. Wait for ACK from the slave ("OK" or "BUSY")
//    5. Automatically retry on failure
//    6. Two indicator LEDs:
//         GPIO8: run LED, blinks with a 500ms period
//         GPIO7: flash LED, blinks twice quickly when ACK is received
//  Version: V25
// ============================================================

#include <Arduino.h>

// ================== Pin Definitions ==================
#define DE_RE_PIN   9          // RS485 direction control: HIGH=transmit, LOW=receive
#define LED_PIN     7          // Flash LED (blinks when ACK is received)
#define RUN_LED_PIN 8          // Run LED (blinks with 500ms period)

// ================== Serial Parameters ==================
#define RS485_BAUD      9600   // RS485 baud rate (must match the slave)
#define RS485_RX_PIN    20     // RS485 RX pin
#define RS485_TX_PIN    21     // RS485 TX pin

// Use UART0 as the RS485 serial port
HardwareSerial Serial485(0);

// ================== Command Parse Result ==================
int parsedN = -1;              // Parsed target address (N value)
int parsedF = -1;              // Parsed count/parameter (F value)

// ================== GPIO8 Run LED ==================
unsigned long lastRunLedToggle = 0;                  // Last toggle time
const unsigned long RUN_LED_INTERVAL = 250;          // 250ms toggle -> 500ms period
bool runLedState = false;                            // Current level state

// ================== GPIO7 Flash State Machine ==================
bool          flashActive   = false;                 // Whether flashing is active
uint8_t       flashRemain   = 0;                     // Remaining toggles (on+off = 2)
bool          flashPhaseOn  = false;                 // Whether currently in "on" phase
unsigned long flashLastTick = 0;                     // Last toggle time
const unsigned long FLASH_INTERVAL = 100;            // 100ms for each on/off phase

// ============================================================
//  Key function: send data over RS485 and wait until it is
//  truly transmitted before switching back to receive
// ------------------------------------------------------------
//  Why this function is needed:
//    ESP32's Serial.flush() only guarantees data is written into
//    the UART hardware FIFO; it does NOT guarantee the last byte
//    has physically left the TX pin.
//    If DE is pulled low (switched back to receive) too early,
//    the last byte will be truncated, and the slave will receive
//    an incomplete command, causing parse failure or merged frames.
//
//  Solution:
//    1) flush() to wait for the FIFO to empty
//    2) then compute the time needed to send all bytes at the
//       given baud rate, plus 2ms margin
//    3) only then pull DE low
//
//  At 9600bps, 1 byte = 10 bits / 9600 = 1.0417ms
//  For "N30 F4\n" (7 bytes) it takes about 7.3ms
// ============================================================
static void rs485_send_and_wait(const char* data, size_t len) {
  digitalWrite(DE_RE_PIN, HIGH);         // Switch to transmit mode
  delayMicroseconds(50);                 // Wait for transceiver direction to settle

  Serial485.write((const uint8_t*)data, len);  // Write data
  Serial485.flush();                     // Wait for data to enter TX FIFO

  // Compute time to send len bytes at baud rate, plus 2ms margin
  // Each byte = 10 bits / 9600bps = 1.0417ms
  uint32_t ms = (uint32_t)((len * 10ULL * 1000ULL) / RS485_BAUD) + 2;
  delay(ms);

  digitalWrite(DE_RE_PIN, LOW);          // Switch back to receive mode
  delayMicroseconds(50);                 // Wait for transceiver direction to settle
}

// ============================================================
//  Hardware reset UART: completely clear the RX FIFO
//  Called before each command transmission, so no residual ACK
//  data from the previous round remains
// ============================================================
void resetSerial485() {
  Serial485.end();                       // Close the serial port
  delay(5);
  Serial485.begin(RS485_BAUD, SERIAL_8N1, RS485_RX_PIN, RS485_TX_PIN);  // Reopen
  delay(5);
  while (Serial485.available()) Serial485.read();  // Clear residual data
}

// ============================================================
//  Parse manually entered command
//  Supported formats: "M600 N12 F4" / "N12 F4" / "n12 f4" etc.
//  Only extracts the N and F tokens; other tokens (e.g. M600)
//  are ignored
//  Returns true on success (both N and F are valid)
// ============================================================
bool parseCommand(String input) {
  parsedN = -1;
  parsedF = -1;
  input.trim();
  if (input.length() == 0) return false;

  int start = 0;
  while (start < (int)input.length()) {
    // Split into tokens by space
    int spaceIdx = input.indexOf(' ', start);
    String token;
    if (spaceIdx == -1) {
      token = input.substring(start);
      start = input.length();
    } else {
      token = input.substring(start, spaceIdx);
      start = spaceIdx + 1;
    }
    token.trim();
    if (token.length() == 0) continue;

    char c0 = token[0];                  // First character (N or F)
    String numPart = token.substring(1); // Numeric part after it

    // Numeric part must be all digits
    bool allDigits = numPart.length() > 0;
    for (size_t i = 0; i < numPart.length(); i++) {
      if (!isDigit(numPart[i])) { allDigits = false; break; }
    }
    if (!allDigits) continue;

    long v = numPart.toInt();
    if (c0 == 'N' || c0 == 'n') {
      if (v < 0 || v > 99) return false; // Address range 0~99
      parsedN = (int)v;
    } else if (c0 == 'F' || c0 == 'f') {
      if (v < 0 || v > 99) return false; // Count range 0~99
      parsedF = (int)v;
    }
  }
  return (parsedN != -1 && parsedF != -1);
}

// ============================================================
//  GPIO7 flash: start flashing (non-blocking)
//  times: number of blinks (each = 100ms on + 100ms off)
// ============================================================
void ledFlashStart(uint8_t times) {
  if (times == 0) return;
  flashRemain  = times * 2;              // Each blink = on + off = 2 phases
  flashActive  = true;
  flashPhaseOn = true;
  digitalWrite(LED_PIN, HIGH);           // Turn on immediately
  flashLastTick = millis();
}

// ============================================================
//  GPIO7 flash: non-blocking state machine refresh
//  Toggles every 100ms, stops after flashRemain toggles
// ============================================================
void updateLedFlash() {
  if (!flashActive) return;
  unsigned long now = millis();
  if (now - flashLastTick >= FLASH_INTERVAL) {
    flashLastTick = now;
    if (flashPhaseOn) {
      digitalWrite(LED_PIN, LOW);        // Switch to off
      flashPhaseOn = false;
    } else {
      digitalWrite(LED_PIN, HIGH);       // Switch to on
      flashPhaseOn = true;
    }
    flashRemain--;
    if (flashRemain == 0) {
      flashActive = false;
      digitalWrite(LED_PIN, LOW);        // Ensure it ends up off
    }
  }
}

// ============================================================
//  GPIO8 run LED: non-blocking toggle (500ms period)
// ============================================================
void updateRunLed() {
  unsigned long now = millis();
  if (now - lastRunLedToggle >= RUN_LED_INTERVAL) {
    lastRunLedToggle = now;
    runLedState = !runLedState;
    digitalWrite(RUN_LED_PIN, runLedState ? HIGH : LOW);
  }
}

// ============================================================
//  Send command and wait for ACK
//  Parameters:
//    cmd        : command string to send (without \n)
//    timeout_ms : timeout for waiting for ACK (default 300ms)
//    retries    : number of retries (default 3)
//  Returns:
//    true  : received "OK"
//    false : received "BUSY" or retries exhausted
//
//  ACK decision rules:
//    - Whole line trimmed and uppercased equals "OK"   -> success
//    - Whole line trimmed and uppercased equals "BUSY" -> failure (slave busy)
//    - Anything else                                   -> retry
// ============================================================
bool sendCommandWithAck(const char* cmd, uint32_t timeout_ms = 300, uint8_t retries = 3) {
  for (uint8_t attempt = 0; attempt < retries; attempt++) {
    resetSerial485();                    // Clear RX to avoid leftovers from last round

    // Build the transmit content (append \n, send in one shot, no frame merging)
    char txbuf[32];
    int n = snprintf(txbuf, sizeof(txbuf), "%s\n", cmd);
    if (n <= 0 || n >= (int)sizeof(txbuf)) {
      Serial.println("[ERROR] cmd too long");
      return false;
    }

    rs485_send_and_wait(txbuf, (size_t)n);  // Send and wait for completion

    // ---- Read response: byte by byte until '\n' or timeout ----
    uint32_t startTime = millis();
    String response = "";
    bool gotLine = false;

    while (millis() - startTime < timeout_ms) {
      while (Serial485.available()) {
        char c = Serial485.read();
        if (c == '\r') continue;         // Ignore \r
        if (c == '\n') { gotLine = true; break; }  // End of line
        if (response.length() < 64) response += c; // Prevent unbounded growth
      }
      if (gotLine) break;
      updateRunLed();                    // Keep run LED blinking while waiting
      updateLedFlash();                  // Keep flash state machine running
    }

    // Drain any residual data
    while (Serial485.available()) Serial485.read();

    response.trim();
    String upper = response;
    upper.toUpperCase();

    // ---- Strict decision ----
    if (upper == "OK") {
      Serial.println("[ACK] OK");
      ledFlashStart(2);                  // ACK received, flash twice
      return true;
    }
    if (upper == "BUSY") {
      Serial.println("[BUSY] Device is busy");
      return false;                      // Slave busy, fail immediately, no retry
    }

    // Anything else: print warning, prepare to retry
    Serial.printf("[WARN] No valid ACK, attempt %d/%d, resp=[%s]\n",
                  attempt + 1, retries, response.c_str());

    // Before retry, wait a bit longer so the slave's BLANKING_TIME (120ms) passes
    delay(150);
  }
  Serial.println("[ERROR] Command failed after retries.");
  return false;
}

// ============================================================
//  setup: initialization
// ============================================================
void setup() {
  Serial.begin(115200);                  // USB debug serial
  Serial485.begin(RS485_BAUD, SERIAL_8N1, RS485_RX_PIN, RS485_TX_PIN);

  pinMode(DE_RE_PIN, OUTPUT);
  digitalWrite(DE_RE_PIN, LOW);          // Default to receive mode

  pinMode(LED_PIN, OUTPUT);
  digitalWrite(LED_PIN, LOW);

  pinMode(RUN_LED_PIN, OUTPUT);
  digitalWrite(RUN_LED_PIN, LOW);
  lastRunLedToggle = millis();

  delay(100);
  resetSerial485();                      // Clear UART

  Serial.println("ESP32-C3 RS485 Master Ready (safe version)");
  Serial.println("Send command like: N12 F4");
}

// ============================================================
//  loop: main loop
//  1. Refresh both indicator LEDs
//  2. If there is input on the USB serial, parse and send command
// ============================================================
void loop() {
  updateRunLed();
  updateLedFlash();

  if (Serial.available() > 0) {
    String input = Serial.readStringUntil('\n');
    input.trim();
    if (input.length() == 0) return;

    Serial.print("Received: ");
    Serial.println(input);

    if (parseCommand(input)) {
      // Build standard command: "N<addr> F<cnt>"
      char cmd[24];
      snprintf(cmd, sizeof(cmd), "N%d F%d", parsedN, parsedF);
      Serial.print("Sending command: ");
      Serial.println(cmd);

      if (sendCommandWithAck(cmd)) {
        Serial.println("Command executed successfully.");
      } else {
        Serial.println("Command execution failed (no ACK).");
      }
    } else {
      Serial.println("Parse error: invalid N/F.");
    }
  }
}