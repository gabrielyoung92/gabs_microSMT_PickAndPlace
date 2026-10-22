// Derived from MicroSMT/Bing-feeder V485 firmware. Local HAL/PlatformIO port.
// Original authors retain credit; see README.md and CHANGELOG.md.
//
// Application state machine: settings, buttons and counted feeds. Short critical
// sections protect motor transitions shared with EXTI/SysTick. Display transfers
// run only in main context; interrupts request a refresh through displayDirty.

#include "feeder.h"
#include "board.h"
#include "config.h"
#include "display.h"
#include "eeprom.h"
#include "rs485.h"
#include "boot.h"
#include <string.h>
#include <stdio.h>

static volatile uint8_t  currentAddr  = 0;     // Current slave address
static volatile uint8_t  currentCount = 0;     // Current default count

// PA4 hold menu: 01 remote ID, 02 update, 03 local ID, 04 default count.
enum { MODE_NORMAL, MODE_MENU, MODE_ASSIGN, MODE_ADDR, MODE_COUNT };
static volatile uint8_t mode = MODE_NORMAL;
static uint8_t menuItem = 1, editValue, uiBlink;
static uint32_t uiLastAction;
static uint8_t buttonRaw = 1, buttonStable = 1, buttonReady, buttonDown, buttonEligible;
static uint32_t buttonChangedAt, buttonPressedAt;
// Peel state is owned by SysTick; main only clears it with interrupts masked.
static volatile uint8_t peelRunning;
static volatile uint32_t peelStartedAt, peelOffAt;
static uint8_t peelClosed;
static uint32_t peelClosedAt;

// RESERVED claims the next feed while the RS485 acceptance reply is sent.
// External/manual triggers cannot replace its count during that turnaround.
typedef enum { FEED_IDLE, FEED_RESERVED, FEED_RUNNING, FEED_FAULT } FeedState;
static volatile FeedState feedState = FEED_IDLE;
static volatile uint8_t feedReady = 0;
static volatile uint8_t pa3TriggerCount = 0;
static volatile uint8_t motorCount = 0;
static volatile uint32_t feedStartedAt = 0;
static volatile uint32_t manualTriggerMute = 0;  // PA4 manual-trigger inhibition
static volatile uint8_t displayDirty = 1;
// Retain the latest addressed request's outcome separately from manual feeds.
// Only main writes its tokens; ISRs latch completion/fault without bus traffic.
typedef enum { REQUEST_UNKNOWN, REQUEST_RUNNING, REQUEST_DONE, REQUEST_FAULT } RequestResult;
static volatile RequestResult requestResult = REQUEST_UNKNOWN;
static uint32_t requestTokens[2];
static uint8_t settingsFault;
static uint8_t feedbackToggles;
static uint8_t feedbackOn;
static uint32_t feedbackTick;

static void RefreshDisplay(void);
static uint8_t Motor_Reserve(uint8_t requestedCount);
static void Motor_Start(void);
static void Motor_Stop(void);

// Snapshot shared state and acknowledge the refresh request before writing the
// bus. An interrupt during the transfer leaves displayDirty set for another pass.
static void RefreshDisplay(void) {
    uint32_t irqMask = __get_PRIMASK();
    __disable_irq();
    FeedState state = feedState;
    uint8_t value = (state == FEED_RESERVED || state == FEED_RUNNING)
                    ? motorCount : mode == MODE_MENU ? menuItem : mode == MODE_ASSIGN ? 1U :
                      (mode == MODE_ADDR || mode == MODE_COUNT) ? editValue : currentAddr;
    uint8_t blank = (mode == MODE_ASSIGN || mode == MODE_ADDR || mode == MODE_COUNT) && uiBlink;
    displayDirty = 0;
    __set_PRIMASK(irqMask);

    if (state == FEED_FAULT && mode != MODE_MENU) {
        CH455_SetDisplay(1, DISPLAY_ERROR_SEGMENTS);
        CH455_SetDisplay(3, DISPLAY_ERROR_SEGMENTS);
        LED_ON();
    } else if (blank) {
        CH455_SetDisplay(1, 0);
        CH455_SetDisplay(3, 0);
    } else {
        CH455_RefreshNum(value);
    }
}

// UI feedback must never postpone serial processing or override the motor LED.
static void StartFeedback(uint8_t times) {
    if (feedState != FEED_IDLE || !times) return;
    feedbackToggles = times * 2U - 1U;
    feedbackOn = 1;
    feedbackTick = HAL_GetTick();
    LED_ON();
}

static void UpdateFeedback(void) {
    if (feedState != FEED_IDLE) { feedbackToggles = 0; return; }
    if (feedbackToggles && (uint32_t)(HAL_GetTick() - feedbackTick) >= 200U) {
        feedbackTick = HAL_GetTick();
        feedbackOn = !feedbackOn;
        if (feedbackOn) LED_ON(); else LED_OFF();
        --feedbackToggles;
    }
}

// One latch for feed deadline, peel deadline and uncertain EEPROM writes.
// Caller may be main or SysTick; no display/EEPROM/bus work belongs here.
static void Motor_Fault(void) {
    uint32_t mask = __get_PRIMASK();
    __disable_irq();
    feedReady = 0;
    feedState = FEED_FAULT;
    peelRunning = 0;
    HAL_GPIO_WritePin(MOTOR_PORT, MOTOR_ALL_PINS, GPIO_PIN_SET);
    if (requestResult == REQUEST_RUNNING) requestResult = REQUEST_FAULT;
    displayDirty = 1;
    __set_PRIMASK(mask);
}

static uint8_t SaveSetting(uint8_t offset, uint8_t value) {
    if (settingsFault) return 0;
    if (EEPROM_WriteByte(offset, value)) return 1;
    settingsFault = 1;
    Motor_Fault();
    return 0;
}

// Used by menu 02 and the addressed BOOT command. Requesting an update never
// erases flash: the loader waits for a valid BEGIN manifest before doing that.
static int8_t RequestBoot(void) {
    uint32_t mask = __get_PRIMASK();
    __disable_irq();
    uint8_t busy = feedState == FEED_RUNNING || feedState == FEED_RESERVED;
    if (!busy) Motor_Fault();
    __set_PRIMASK(mask);
    if (busy) return -1;
    return SaveSetting(BOOT_STATE_ADDR, BOOT_REQUESTED) ? 1 : 0;
}

// Atomically stop idle peeling and exclude serial/external feeds from the UI.
static uint8_t EnterMenu(void) {
    uint32_t mask = __get_PRIMASK();
    __disable_irq();
    uint8_t accepted = !settingsFault && mode == MODE_NORMAL &&
                       ((feedReady && feedState == FEED_IDLE) || feedState == FEED_FAULT);
    if (accepted) {
        mode = MODE_MENU;
        peelRunning = 0;
        peelOffAt = HAL_GetTick();
        Board_MotorIdle();
        displayDirty = 1;
    }
    __set_PRIMASK(mask);
    return accepted;
}

static void LeaveMenu(void) {
    // A remote ID save can finish while PA4 is down. Its release is consumed.
    if (buttonDown) buttonEligible = 0;
    mode = MODE_NORMAL;
    displayDirty = 1;
}

// A debounced press has exactly one release action. Holds do not repeat, and
// a held button at power-up must first be released before it can do anything.
static void KeyScan(void) {
    uint32_t now = HAL_GetTick();
    uint8_t raw = HAL_GPIO_ReadPin(BUTTON_PORT, BUTTON_PIN) != GPIO_PIN_RESET;
    if (raw != buttonRaw) { buttonRaw = raw; buttonChangedAt = now; }
    if (raw != buttonStable && (uint32_t)(now - buttonChangedAt) >= BUTTON_DEBOUNCE_MS) {
        buttonStable = raw;
        if (!raw && buttonReady) {
            buttonDown = 1;
            buttonPressedAt = now;
            uiLastAction = now;
            // A press beginning during motion/fault must never become a feed
            // or menu action after that motion finishes.
            buttonEligible = !settingsFault && ((feedReady && feedState == FEED_IDLE) || feedState == FEED_FAULT);
        } else if (raw) {
            buttonReady = 1;
            if (buttonDown) {
                buttonDown = 0;
                uint32_t held = now - buttonPressedAt;
                uiLastAction = now;
                if (!settingsFault && buttonEligible) {
                    if (mode == MODE_MENU) {
                        if (menuItem == 2U) {
                            if (RequestBoot() == 1) NVIC_SystemReset();
                        } else if (feedState == FEED_IDLE) {
                            mode = menuItem == 1U ? MODE_ASSIGN : menuItem == 3U ? MODE_ADDR : MODE_COUNT;
                            editValue = mode == MODE_COUNT ? currentCount : currentAddr;
                        } else LeaveMenu(); // A motor fault only permits menu 02.
                    } else if (mode == MODE_ADDR || mode == MODE_COUNT) {
                        if (held >= BUTTON_HOLD_MS) {
                            uint8_t offset = mode == MODE_ADDR ? EEPROM_DATA_ADDR : EEPROM_COUNT_ADDR;
                            if (SaveSetting(offset, editValue)) {
                                if (mode == MODE_ADDR) { currentAddr = editValue; requestResult = REQUEST_UNKNOWN; }
                                else currentCount = editValue;
                                LeaveMenu();
                                StartFeedback(1);
                            }
                        } else {
                            editValue = editValue >= VALUE_MAX ? (mode == MODE_COUNT ? COUNT_MIN : VALUE_MIN) : editValue + 1U;
                        }
                    } else if (mode == MODE_NORMAL && held < BUTTON_HOLD_MS && !manualTriggerMute) {
                        if (Motor_Reserve(0)) { Motor_Start(); manualTriggerMute = MANUAL_TRIGGER_MUTE_MS; }
                    } else if (mode == MODE_ASSIGN && held >= BUTTON_HOLD_MS) LeaveMenu();
                }
                displayDirty = 1;
            }
        }
    }
    if (!settingsFault && buttonDown && buttonEligible && !buttonStable) {
        uint32_t held = now - buttonPressedAt;
        if (held >= BUTTON_HOLD_MS && mode == MODE_NORMAL) EnterMenu();
        if (mode == MODE_MENU) {
            uint8_t item = (held / BUTTON_HOLD_MS - 1U) % 4U + 1U;
            if (item != menuItem) { menuItem = item; displayDirty = 1; }
        }
    }
    // Never time out a hold and reinterpret its release as a normal feed.
    if (mode != MODE_NORMAL && mode != MODE_MENU && !buttonDown &&
        (uint32_t)(now - uiLastAction) >= UI_TIMEOUT_MS) LeaveMenu();
    uint8_t blink = ((uint32_t)(now - uiLastAction) / UI_BLINK_MS) & 1U;
    if (blink != uiBlink) { uiBlink = blink; if (mode != MODE_NORMAL) displayDirty = 1; }
}

// Claim a feed and its resolved count before any ACK delay or motor output.
// F0/manual/external requests use the positive stored default. All callers use
// this same guarded transition so no trigger can overwrite a reserved command.
static uint8_t Motor_Reserve(uint8_t requestedCount) {
    uint32_t irqMask = __get_PRIMASK();
    __disable_irq();
    uint8_t count = requestedCount ? requestedCount : currentCount;
    uint8_t accepted = feedReady && mode == MODE_NORMAL && feedState == FEED_IDLE &&
                       count >= COUNT_MIN && count <= VALUE_MAX;
    if (accepted) {
        motorCount = count;
        pa3TriggerCount = 0;
        feedState = FEED_RESERVED;
        displayDirty = 1;
    }
    __set_PRIMASK(irqMask);
    return accepted;
}

// Arm counting before driving the motor. Only a previously reserved feed can
// start; clearing stale count edges prevents idle pulses becoming feed progress.
static void Motor_Start(void) {
    uint32_t irqMask = __get_PRIMASK();
    __disable_irq();
    if (feedState == FEED_RESERVED) {
        __HAL_GPIO_EXTI_CLEAR_IT(COUNT_PIN);
        pa3TriggerCount = 0;
        feedStartedAt = HAL_GetTick();
        feedState = FEED_RUNNING;
        HAL_GPIO_WritePin(MOTOR_PORT, MOTOR_INDEX_A_PIN, GPIO_PIN_SET);
        HAL_GPIO_WritePin(MOTOR_PORT, MOTOR_INDEX_B_PIN, GPIO_PIN_RESET);
        LED_ON();
        displayDirty = 1;
    }
    __set_PRIMASK(irqMask);
}

// Finish a counted feed. Keep this short: no display bus transfers in the ISR.
// The critical section also prevents timeout from interleaving the idle outputs.
static void Motor_Stop(void) {
    uint32_t irqMask = __get_PRIMASK();
    __disable_irq();
    if (feedState == FEED_RUNNING) {
        HAL_GPIO_WritePin(MOTOR_PORT, MOTOR_INDEX_A_PIN | MOTOR_INDEX_B_PIN, GPIO_PIN_SET);
#if !FEEDER_WIDE
        HAL_GPIO_WritePin(MOTOR_PORT, MOTOR_PEEL_A_PIN | MOTOR_PEEL_B_PIN, GPIO_PIN_SET);
        peelRunning = 0;
        peelOffAt = HAL_GetTick();
#endif
        if (requestResult == REQUEST_RUNNING) requestResult = REQUEST_DONE;
        LED_OFF();
        pa3TriggerCount = 0;
        feedState = FEED_IDLE;
        displayDirty = 1;
    }
    __set_PRIMASK(irqMask);
}

// Addressed feeds report acceptance, then retain a sensor-confirmed result for
// STATUS polls. Legacy Busy/OK remain acceptance-only for direct adapters.
static void ProcessRS485(void) {
    char line[RX_BUFFER_SIZE];
    if (!RS485_ReadLine(line, sizeof(line))) return;
    // Firmware commands use a separate addressed, checksummed grammar. Legacy
    // feed commands stay compatible. CRC includes the destination feeder ID.
    if (line[0] == 'B') {
        char* command = Boot_DecodePacket(line, currentAddr);
        if (command == NULL) return;
        if (!strncmp(command, "STATUS ", 7)) {
            const char* text = command + 7;
            uint32_t tokens[2];
            if (!Boot_ParseHex(&text, &tokens[0]) || *text++ != ' ' ||
                !Boot_ParseHex(&text, &tokens[1]) || *text) return;
            RequestResult result = requestResult;
            if (tokens[0] != requestTokens[0] || tokens[1] != requestTokens[1])
                result = REQUEST_UNKNOWN;
            const char* statuses[] = {"UNKNOWN", "RUNNING", "DONE", "FAULT"};
            Boot_Reply(currentAddr, statuses[result], tokens, 2);
            return;
        }
        if (!strncmp(command, "IDENT ", 6)) {
            const char* text = command + 6;
            uint32_t nonce;
            if (!Boot_ParseHex(&text, &nonce) || *text) return;
            uint32_t values[] = {nonce, HAL_GetUIDw0(), HAL_GetUIDw1(), HAL_GetUIDw2(),
                                 mode == MODE_ASSIGN && !settingsFault};
            Boot_Reply(currentAddr, "IDENT", values, 5);
            return;
        }
        if (settingsFault) return;
        if (!strncmp(command, "SETID ", 6)) {
            const char* text = command + 6;
            uint32_t values[5];
            for (uint8_t i = 0; i < 5; i++) {
                if (!Boot_ParseHex(&text, &values[i]) || (i < 4 ? *text++ != ' ' : *text != 0)) return;
            }
            if (values[1] != HAL_GetUIDw0() || values[2] != HAL_GetUIDw1() || values[3] != HAL_GetUIDw2()) return;
            if (mode != MODE_ASSIGN || values[4] > VALUE_MAX || feedState != FEED_IDLE) {
                Boot_Reply(currentAddr, "ERROR NOTARMED", NULL, 0);
            } else if (!SaveSetting(EEPROM_DATA_ADDR, (uint8_t)values[4])) {
                Boot_Reply(currentAddr, "ERROR EEPROM", NULL, 0);
            } else {
                uint8_t oldId = currentAddr;
                currentAddr = (uint8_t)values[4];
                requestResult = REQUEST_UNKNOWN;
                LeaveMenu();
                uint32_t reply[] = {values[0], currentAddr};
                Boot_Reply(oldId, "ID", reply, 2);
            }
        } else if (!strncmp(command, "FEED ", 5)) {
            const char* text = command + 5;
            uint32_t values[2], count;
            if (!Boot_ParseHex(&text, &values[0]) || *text++ != ' ' ||
                !Boot_ParseHex(&text, &values[1]) || *text++ != ' ' ||
                !Boot_ParseHex(&text, &count) || *text || count > VALUE_MAX) return;
            uint8_t accepted = Motor_Reserve((uint8_t)count);
            if (accepted) {
                requestTokens[0] = values[0];
                requestTokens[1] = values[1];
                requestResult = REQUEST_RUNNING;
            }
            Boot_Reply(currentAddr, accepted ? "ACCEPT" : (feedState == FEED_FAULT ? "FAULT" : "BUSY"), values, 2);
            if (accepted) Motor_Start();
        } else if (!strcmp(command, "INFO")) {
            BootRecord record;
            uint8_t state;
            if (Boot_ReadRecord(&record, &state) && state == BOOT_VALID) {
                uint32_t values[] = {FEEDER_VARIANT_ID, record.size, record.imageCrc};
                Boot_Reply(currentAddr, "APP", values, 3);
            } else Boot_Reply(currentAddr, "ERROR METADATA", NULL, 0);
        } else if (!strcmp(command, "BOOT")) {
            int8_t result = RequestBoot();
            if (result < 0) Boot_Reply(currentAddr, "ERROR BUSY", NULL, 0);
            else if (!result) Boot_Reply(currentAddr, "ERROR EEPROM", NULL, 0);
            else {
                Boot_Reply(currentAddr, "RESET", NULL, 0);
                NVIC_SystemReset();
            }
        }
        return;
    }
    if (settingsFault) return;
    int cmdAddr = -1, freq = -1;
    if (!RS485_ParseFeedCommand(line, &cmdAddr, &freq)) return;

    if (cmdAddr != (int)currentAddr) return; // Address mismatch, silently ignore

    // Claim the feed BEFORE allowing interrupts during the ACK turnaround.
    // Subsequent queued commands remain in the receive ring for later passes.
    if (!Motor_Reserve((uint8_t)freq)) {
        delay_ms(ACK_TURNAROUND_MS);
        RS485_SendString("Busy\n");
        return;
    }

    delay_ms(ACK_TURNAROUND_MS);
    RS485_SendString("OK\n");  // Accepted, not a completion report.
    Motor_Start();
}

// External triggers use the same reservation as serial/manual requests. This
// handler touches only motor/state GPIO; display work waits for the main loop.
void EXTI9_5_IRQHandler(void) {
    if (__HAL_GPIO_EXTI_GET_IT(TRIGGER_PIN) != RESET) {
        __HAL_GPIO_EXTI_CLEAR_IT(TRIGGER_PIN);
        if (Motor_Reserve(0)) Motor_Start();
    }
}

// Count edges during an active feed. No bit-banged transfers or delays here.
void EXTI3_IRQHandler(void) {
    if (__HAL_GPIO_EXTI_GET_IT(COUNT_PIN) != RESET) {
        __HAL_GPIO_EXTI_CLEAR_IT(COUNT_PIN);
        uint32_t irqMask = __get_PRIMASK();
        __disable_irq();
        if (feedState == FEED_RUNNING && ++pa3TriggerCount >= motorCount) {
            Motor_Stop();
        }
        __set_PRIMASK(irqMask);
    }
}

// Read both settings without manufacturing defaults on communication failures.
// Only a successfully read blank address may become commissioning ID 0.
static uint8_t LoadSettings(void) {
    uint8_t address, count;
    if (!EEPROM_ReadChecked(EEPROM_DATA_ADDR, &address) ||
        !EEPROM_ReadChecked(EEPROM_COUNT_ADDR, &count)) return 0;
    if (address == 0xFFU) {
        address = DEFAULT_ADDRESS;
        if (!EEPROM_WriteByte(EEPROM_DATA_ADDR, address)) return 0;
    } else if (address > VALUE_MAX) return 0;
    if (count < COUNT_MIN || count > VALUE_MAX) {
        count = DEFAULT_COUNT;
        if (!EEPROM_WriteByte(EEPROM_COUNT_ADDR, count)) return 0;
    }
    currentAddr = address;
    currentCount = count;
    return 1;
}

// Finish settings, feedback and startup output before enabling feed inputs.
// feedReady remains false until every startup idle-output write is complete.
void Feeder_Init(void) {
    feedReady = 0;
    HAL_GPIO_WritePin(MOTOR_PORT, MOTOR_ALL_PINS, GPIO_PIN_SET);
    buttonRaw = buttonStable = HAL_GPIO_ReadPin(BUTTON_PORT, BUTTON_PIN) != GPIO_PIN_RESET;
    buttonReady = buttonStable;
    while (!LoadSettings()) {
        CH455_SetDisplay(1, DISPLAY_ERROR_SEGMENTS);
        CH455_SetDisplay(3, DISPLAY_ERROR_SEGMENTS);
        LED_ON();
        delay_ms(100);
    }

    delay_ms(10);
    CH455_RefreshNum(currentAddr);
    delay_ms(5);

    // Power-on flash 5 times, display current address
    for (uint8_t i = 0; i < 5; i++) {
        CH455_RefreshNum(currentAddr);
        LED_ON();
        delay_ms(150);
        CH455_SetDisplay(1, 0x00);
        CH455_SetDisplay(3, 0x00);
        LED_OFF();
        delay_ms(150);
    }
    RefreshDisplay();

    RS485_Init();

    // Print address and local firmware version on power-up
    {
        char buf[40];
        snprintf(buf, sizeof(buf), "Addr:%u v%s %s\n", (unsigned)currentAddr, FIRMWARE_VERSION, FEEDER_VARIANT);
        RS485_SendString(buf);
    }

    Board_MotorIdle();
    LED_OFF();
    displayDirty = 1;
    RefreshDisplay();

    // No startup path can drive idle outputs after feeds become eligible.
    uint32_t irqMask = __get_PRIMASK();
    __disable_irq();
    Board_EnableFeedInterrupts();
    feedReady = 1;
    __set_PRIMASK(irqMask);
}

// Process one queued command per pass and repaint only when state changes.
// Button feedback is nonblocking; SysTick independently enforces the deadline.
void Feeder_Run(void) {
    KeyScan();
    ProcessRS485();
    UpdateFeedback();
    if (displayDirty) RefreshDisplay();
    if (feedState == FEED_FAULT) LED_ON();
    delay_ms(5);
}

// SysTick owns tension sampling and peel output changes, so a blocking display
// or serial transaction cannot leave a released/tensioned switch ignored.
void Feeder_Tick(void) {
    uint32_t now = HAL_GetTick();
    if (manualTriggerMute > 0) manualTriggerMute--;
    if (feedState == FEED_RUNNING && (uint32_t)(now - feedStartedAt) >= FEED_TIMEOUT_MS) {
        Motor_Fault();
        LED_ON();
    }
    uint8_t closed = HAL_GPIO_ReadPin(PEEL_SWITCH_PORT, PEEL_SWITCH_PIN) == PEEL_RUN_LEVEL;
    if (!closed) peelClosed = 0;
    else if (!peelClosed) { peelClosed = 1; peelClosedAt = now; }
    uint8_t permitted = feedReady && mode == MODE_NORMAL && feedState != FEED_FAULT &&
                        (FEEDER_WIDE || feedState == FEED_RUNNING);
    if (!permitted || !closed) {
        if (peelRunning) {
            HAL_GPIO_WritePin(MOTOR_PORT, MOTOR_PEEL_A_PIN | MOTOR_PEEL_B_PIN, GPIO_PIN_SET);
            peelRunning = 0;
            peelOffAt = now;
        }
    } else if (peelRunning) {
        if ((uint32_t)(now - peelStartedAt) >= PEEL_TIMEOUT_MS) { Motor_Fault(); LED_ON(); }
    } else if ((uint32_t)(now - peelClosedAt) >= PEEL_DEBOUNCE_MS &&
               (uint32_t)(now - peelOffAt) >= PEEL_RESTART_MS) {
        HAL_GPIO_WritePin(MOTOR_PORT, MOTOR_PEEL_B_PIN, GPIO_PIN_SET);
        HAL_GPIO_WritePin(MOTOR_PORT, MOTOR_PEEL_A_PIN, GPIO_PIN_RESET);
        peelStartedAt = now;
        peelRunning = 1;
    }
}
