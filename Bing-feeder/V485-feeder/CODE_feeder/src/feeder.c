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
#include "stock.h"
#include <string.h>
#include <stdio.h>

static volatile uint8_t  currentAddr  = 0;     // Current slave address
static uint8_t optionsUnconfigured;
static uint8_t optionsFault; // Invalid extension: keep serial/menu recovery available, motors inhibited.
static volatile uint8_t motorOptions; // bits: feed reverse, peel reverse, NO switch
static volatile uint8_t currentType = 0;  // 0 means unconfigured; motors inhibited.
static volatile uint8_t  currentCount = 0;     // Current default count

// PA2 hold menu: 01 remote ID, 02 update, 03 local ID, 04 default count, 05 physical width.
enum { MODE_NORMAL, MODE_MENU, MODE_ASSIGN, MODE_ADDR, MODE_COUNT, MODE_TYPE, MODE_TEST, MODE_LOAD };
static volatile uint8_t mode = MODE_NORMAL;
static uint8_t menuItem = 1, editValue, uiBlink;
static uint32_t uiLastAction;
static uint8_t buttonRaw = 1, buttonStable = 1, buttonReady, buttonDown, buttonEligible;
static uint32_t buttonChangedAt, buttonPressedAt;
static uint8_t feedButtonRaw = 1, feedButtonStable = 1, feedButtonReady;
static uint8_t feedButtonDown, feedButtonEligible, feedButtonClearsFault;
static uint32_t feedButtonChangedAt, feedButtonPressedAt;
// Peel state is owned by SysTick; main only clears it with interrupts masked.
static volatile uint8_t peelRunning;
// Test mode latches until an explicit exit/reset; browser loss must not resume motors.
static volatile uint32_t testSwitchChanges;
static uint8_t testSwitchRaw, testSwitchStable;
static uint32_t testSwitchChangedAt;
static volatile uint32_t peelStartedAt, peelOffAt;
static uint8_t peelClosed;
static uint32_t peelClosedAt;

// RESERVED claims the next feed while the RS485 acceptance reply is sent.
// Manual feeds cannot replace its count during that turnaround.
typedef enum { FEED_IDLE, FEED_RESERVED, FEED_RUNNING, FEED_FAULT } FeedState;
static volatile FeedState feedState = FEED_IDLE;
static volatile uint8_t feedReady = 0;
static volatile uint32_t pa3TriggerCount = 0;
// Runtime movement count includes every index-sensor edge, including manual
// feeds/hand movement and partial feeds. No EEPROM write per part or per boot.
static volatile uint32_t movementTotal;
// The host claims an initially empty runtime token. It survives host restarts
// in MCU RAM, but clears on MCU reset so inventory can detect a lost interval.
static uint32_t monitorToken[2];
static volatile uint8_t faultReason;
// Last fault snapshot in RAM; cleared only by Clear Error/reset.
static volatile uint32_t faultFlags, faultTarget, faultReceived, faultDuration;
static volatile uint8_t loadPeel;
static uint8_t emptyShown;
// Boot/clear/jog hold: the first ordinary feed arms switch-controlled take-up.
static volatile uint8_t jogPeelHold = 1, retractMove;
static volatile uint32_t motorCount = 0;
static volatile uint32_t jogItems, lastProgressAt, moveDeadlineMs;
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
static volatile uint8_t locateToggles;
static uint8_t locateBlank;
static uint32_t locateTick;

static void RefreshDisplay(void);
static uint8_t Motor_Reserve(uint8_t requestedCount);
static uint8_t Motor_ReserveMove(uint32_t requestedCount, uint8_t jog, uint8_t retract, uint32_t items);
static void Motor_Start(void);
static void Motor_Stop(void);

// Snapshot shared state and acknowledge the refresh request before writing the
// bus. An interrupt during the transfer leaves displayDirty set for another pass.
static void RefreshDisplay(void) {
    uint32_t irqMask = __get_PRIMASK();
    __disable_irq();
    FeedState state = feedState;
    uint32_t shown = jogPeelHold ? jogItems : motorCount;
    uint8_t value = (state == FEED_RESERVED || state == FEED_RUNNING)
                    ? (shown > 99U ? 99U : (uint8_t)shown) : mode == MODE_MENU ? menuItem : mode == MODE_ASSIGN ? 1U :
                      (mode == MODE_ADDR || mode == MODE_COUNT || mode == MODE_TYPE) ? editValue : currentAddr;
    uint32_t quantity, completed, sequence;
    Stock_Read(&quantity, &completed, &sequence);
    uint8_t empty = quantity == 0 && mode == MODE_NORMAL && state == FEED_IDLE &&
                    currentAddr >= ADDRESS_MIN && Feeder_TypeValid(currentType) && !locateToggles &&
                    ((HAL_GetTick() / 1000U) & 1U);
    uint8_t blank = (mode == MODE_ASSIGN || mode == MODE_ADDR || mode == MODE_COUNT || mode == MODE_TYPE ||
                     (mode == MODE_NORMAL && (currentAddr < ADDRESS_MIN || !Feeder_TypeValid(currentType)))) && uiBlink;
    if (locateToggles && mode == MODE_NORMAL && state == FEED_IDLE) blank = locateBlank;
    displayDirty = 0;
    __set_PRIMASK(irqMask);

    if (state == FEED_FAULT && mode != MODE_MENU) {
        CH455_RefreshFault(faultReason);
        LED_ON();
    } else if (empty) {
        CH455_SetDisplay(1, 0x70U); // L
        CH455_SetDisplay(3, 0xB8U); // o
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

// Visual location never changes settings or enables either motor. It stops
// idle peeling while active and cancels when the user enters a menu.
static void UpdateLocate(void) {
    if (!locateToggles) return;
    if (mode != MODE_NORMAL || feedState != FEED_IDLE) {
        locateToggles = locateBlank = 0;
        if (feedState == FEED_IDLE) LED_OFF();
        displayDirty = 1;
        return;
    }
    if ((uint32_t)(HAL_GetTick() - locateTick) >= 200U) {
        locateTick = HAL_GetTick();
        locateBlank = !locateBlank;
        --locateToggles;
        if (!locateToggles) locateBlank = 0;
        if (locateToggles && !locateBlank) LED_ON(); else LED_OFF();
        displayDirty = 1;
    }
}

// One latch for feed deadline, peel deadline and uncertain EEPROM writes.
// Caller may be main or SysTick; no display/EEPROM/bus work belongs here.
static void Motor_Fault(uint8_t reason) {
    uint32_t mask = __get_PRIMASK();
    __disable_irq();
    if (reason && !faultReason) {
        faultFlags = reason | ((uint32_t)(HAL_GPIO_ReadPin(PEEL_SWITCH_PORT, PEEL_SWITCH_PIN) == GPIO_PIN_RESET) << 8) |
                     ((uint32_t)(!!(motorOptions & OPTION_SWITCH_NO)) << 9) | ((uint32_t)peelRunning << 10);
        faultTarget = feedState == FEED_RUNNING ? motorCount : 0;
        faultReceived = feedState == FEED_RUNNING ? pa3TriggerCount : 0;
        faultDuration = reason == FAULT_PEEL ? HAL_GetTick() - peelStartedAt :
                        feedState == FEED_RUNNING ? HAL_GetTick() - feedStartedAt : 0;
    }
    loadPeel = 0;
    feedReady = 0;
    feedState = FEED_FAULT;
    faultReason = reason;
    peelRunning = 0;
    HAL_GPIO_WritePin(MOTOR_PORT, MOTOR_ALL_PINS, GPIO_PIN_SET);
    if (requestResult == REQUEST_RUNNING) requestResult = REQUEST_FAULT;
    displayDirty = 1;
    __set_PRIMASK(mask);
}

static uint8_t ClearFault(void) {
    uint32_t mask = __get_PRIMASK(); __disable_irq();
    uint8_t result = ((mode != MODE_NORMAL && mode != MODE_TEST && mode != MODE_LOAD) ||
                      feedState == FEED_RUNNING || feedState == FEED_RESERVED || locateToggles) ? 1U :
                     (settingsFault || optionsFault || !Feeder_TypeValid(currentType) ||
                      currentAddr < ADDRESS_MIN || currentAddr > VALUE_MAX) ? 2U : 0U;
    if (!result) {
        Board_MotorIdle(); loadPeel = peelRunning = peelClosed = 0;
        peelOffAt = HAL_GetTick(); jogPeelHold = 1;
        faultReason = FAULT_NONE; faultFlags = faultTarget = faultReceived = faultDuration = 0;
        feedState = FEED_IDLE; feedReady = mode != MODE_TEST;
        feedButtonEligible = buttonEligible = 0; displayDirty = 1;
    }
    __set_PRIMASK(mask);
    return result;
}

static uint8_t SaveSetting(uint8_t offset, uint8_t value) {
    if (settingsFault) return 0;
    if (EEPROM_WriteByte(offset, value)) return 1;
    settingsFault = 1;
    Motor_Fault(FAULT_SETTINGS);
    return 0;
}

// Invalidate first and commit width last. An interrupted configuration must
// never turn old/random EEPROM bytes into a usable physical type on restart.
static uint8_t SaveType(uint8_t width) {
    uint8_t saved = Feeder_TypeValid(width) && SaveSetting(EEPROM_TYPE_ADDR, 0) &&
                    SaveSetting(EEPROM_TYPE_CHECK_ADDR, (uint8_t)~width) &&
                    SaveSetting(EEPROM_TYPE_ADDR, width);
    if (saved && optionsUnconfigured) motorOptions = width == 8U ? DEFAULT_OPTIONS_8MM : 0;
    return saved;
}

// Blank extension bytes preserve 0.1.0 behaviour without boot-time writes.
// Any partial/unknown record fails closed rather than changing motor direction.
static uint8_t LoadOptions(void) {
    uint8_t value, check, version;
    if (!EEPROM_ReadChecked(EEPROM_OPTIONS_ADDR, &value) ||
        !EEPROM_ReadChecked(EEPROM_OPTIONS_CHECK_ADDR, &check) ||
        !EEPROM_ReadChecked(EEPROM_OPTIONS_VERSION_ADDR, &version)) return 0;
    if (value == 0xFFU && check == 0xFFU && version == 0xFFU) {
        optionsUnconfigured = 1;
        motorOptions = currentType == 8U ? DEFAULT_OPTIONS_8MM : 0;
        optionsFault = 0;
        return 1;
    }
    optionsUnconfigured = 0;
    if (version != OPTIONS_VERSION || (value & ~OPTIONS_MASK) ||
        (uint8_t)(value ^ check) != 0xFFU) {
        optionsFault = 1;
        motorOptions = 0;
        return 1;
    }
    optionsFault = 0;
    motorOptions = value;
    return 1;
}

static uint8_t SaveOptions(uint8_t value) {
    if (!SaveSetting(EEPROM_OPTIONS_VERSION_ADDR, 0) ||
        !SaveSetting(EEPROM_OPTIONS_ADDR, value) ||
        !SaveSetting(EEPROM_OPTIONS_CHECK_ADDR, (uint8_t)~value) ||
        !SaveSetting(EEPROM_OPTIONS_VERSION_ADDR, OPTIONS_VERSION)) return 0;
    motorOptions = value;
    optionsUnconfigured = 0;
    optionsFault = 0;
    return 1;
}

// Bus settings require no button. Atomically exclude every motor start while
// EEPROM is written, including idle peeling and manual requests during ACKs.
static uint8_t BeginRemoteSettings(void) {
    uint32_t mask = __get_PRIMASK();
    __disable_irq();
    uint8_t allowed = mode != MODE_TEST && !settingsFault && (feedState == FEED_IDLE ||
                      (faultReason == FAULT_SETTINGS && feedState == FEED_FAULT));
    if (allowed) {
        feedReady = 0;
        Board_MotorIdle();
        peelRunning = peelClosed = 0;
        peelOffAt = HAL_GetTick();
    }
    __set_PRIMASK(mask);
    return allowed;
}

static void EndRemoteSettings(void) {
    uint32_t mask = __get_PRIMASK();
    __disable_irq();
    feedReady = !settingsFault && feedState == FEED_IDLE;
    __set_PRIMASK(mask);
}

static uint8_t PeelRequested(void) {
    uint8_t closed = HAL_GPIO_ReadPin(PEEL_SWITCH_PORT, PEEL_SWITCH_PIN) == GPIO_PIN_RESET;
    return (motorOptions & OPTION_SWITCH_NO) ? !closed : closed;
}

// Used by menu 02 and the addressed BOOT command. Requesting an update never
// erases flash: the loader waits for a valid BEGIN manifest before doing that.
static int8_t RequestBoot(void) {
    uint32_t mask = __get_PRIMASK();
    __disable_irq();
    uint8_t busy = feedState == FEED_RUNNING || feedState == FEED_RESERVED;
    if (!busy) Motor_Fault(FAULT_NONE);
    __set_PRIMASK(mask);
    if (busy) return -1;
    return SaveSetting(BOOT_STATE_ADDR, BOOT_REQUESTED) ? 1 : 0;
}

// Atomically stop idle peeling and exclude serial/manual feeds from the UI.
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
    // A remote ID save can finish while PA2 is down. Its release is consumed.
    if (buttonDown) buttonEligible = 0;
    mode = MODE_NORMAL;
    displayDirty = 1;
}

// A debounced press has exactly one release action. Holds do not repeat, and
// a held button at power-up must first be released before it can do anything.
static void MenuKeyScan(void) {
    uint32_t now = HAL_GetTick();
    uint8_t raw = HAL_GPIO_ReadPin(MENU_BUTTON_PORT, MENU_BUTTON_PIN) != GPIO_PIN_RESET;
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
                        } else if (feedState == FEED_IDLE || (optionsFault && menuItem == 1U)) {
                            mode = menuItem == 1U ? MODE_ASSIGN : menuItem == 3U ? MODE_ADDR :
                                   menuItem == 4U ? MODE_COUNT : MODE_TYPE;
                            editValue = mode == MODE_TYPE ? (Feeder_TypeValid(currentType) ? currentType : 8U) :
                                        mode == MODE_COUNT ? currentCount :
                                        currentAddr < ADDRESS_MIN ? ADDRESS_MIN : currentAddr;
                        } else LeaveMenu(); // A motor fault only permits menu 02.
                    } else if (mode == MODE_ADDR || mode == MODE_COUNT || mode == MODE_TYPE) {
                        if (held >= BUTTON_HOLD_MS) {
                            uint8_t offset = mode == MODE_ADDR ? EEPROM_DATA_ADDR :
                                             mode == MODE_TYPE ? EEPROM_TYPE_ADDR : EEPROM_COUNT_ADDR;
                            if (mode == MODE_TYPE ? SaveType(editValue) : SaveSetting(offset, editValue)) {
                                if (mode == MODE_ADDR) { currentAddr = editValue; requestResult = REQUEST_UNKNOWN; }
                                else if (mode == MODE_TYPE) currentType = editValue;
                                else currentCount = editValue;
                                LeaveMenu();
                                StartFeedback(1);
                            }
                        } else {
                            if (mode == MODE_TYPE) editValue = editValue == 8U ? 12U : editValue == 12U ? 16U : editValue == 16U ? 24U : 8U;
                            else editValue = editValue >= VALUE_MAX ? (mode == MODE_COUNT ? COUNT_MIN : ADDRESS_MIN) : editValue + 1U;
                        }
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
            uint8_t item = (held / BUTTON_HOLD_MS - 1U) % 5U + 1U;
            if (item != menuItem) { menuItem = item; displayDirty = 1; }
        }
    }
    // Never time out a hold and reinterpret its release as a normal feed.
    if (mode != MODE_NORMAL && mode != MODE_MENU && mode != MODE_TEST && mode != MODE_LOAD && !buttonDown &&
        (uint32_t)(now - uiLastAction) >= UI_TIMEOUT_MS) LeaveMenu();
    uint8_t blink = ((uint32_t)(now - uiLastAction) / UI_BLINK_MS) & 1U;
    if (blink != uiBlink) {
        uiBlink = blink;
        if (mode != MODE_NORMAL || currentAddr < ADDRESS_MIN) displayDirty = 1;
    }
}

// PA4 only feeds on a short release in normal idle operation. A press begun
// during a menu/feed, a simultaneous PA2 press, or a startup hold is consumed.
static void KeyScan(void) {
    MenuKeyScan();
    uint32_t now = HAL_GetTick();
    uint8_t raw = HAL_GPIO_ReadPin(BUTTON_PORT, BUTTON_PIN) != GPIO_PIN_RESET;
    if (raw != feedButtonRaw) { feedButtonRaw = raw; feedButtonChangedAt = now; }
    if (buttonDown || mode != MODE_NORMAL) feedButtonEligible = 0;
    if (raw == feedButtonStable ||
        (uint32_t)(now - feedButtonChangedAt) < BUTTON_DEBOUNCE_MS) return;
    feedButtonStable = raw;
    if (!raw && feedButtonReady) {
        feedButtonDown = 1;
        feedButtonPressedAt = now;
        feedButtonClearsFault = feedState == FEED_FAULT;
        feedButtonEligible = !settingsFault && ((feedReady && feedState == FEED_IDLE) || feedButtonClearsFault) &&
                             mode == MODE_NORMAL && !buttonDown;
    } else if (raw) {
        feedButtonReady = 1;
        if (feedButtonDown && feedButtonEligible && !manualTriggerMute) {
            uint32_t held = now - feedButtonPressedAt;
            if (feedButtonClearsFault && held >= BUTTON_HOLD_MS && feedState == FEED_FAULT) ClearFault();
            else if (!feedButtonClearsFault && held < BUTTON_HOLD_MS && Motor_Reserve(0)) {
                Motor_Start(); manualTriggerMute = MANUAL_TRIGGER_MUTE_MS;
            }
        }
        feedButtonDown = 0;
        feedButtonEligible = 0;
    }
}

// Claim a feed and its resolved count before any ACK delay or motor output.
// F0/manual requests use the positive stored default. All callers use
// this same guarded transition so no trigger can overwrite a reserved command.
static uint8_t Motor_Reserve(uint8_t requestedCount) {
    return Motor_ReserveMove(requestedCount, 0, 0, 0);
}

static uint8_t Motor_ReserveMove(uint32_t requestedCount, uint8_t jog, uint8_t retract, uint32_t items) {
    uint32_t irqMask = __get_PRIMASK();
    __disable_irq();
    uint32_t count = requestedCount ? requestedCount : currentCount;
    uint8_t accepted = feedReady && Feeder_TypeValid(currentType) && !locateToggles && currentAddr >= ADDRESS_MIN && currentAddr <= VALUE_MAX &&
                       (mode == MODE_NORMAL || (jog && mode == MODE_LOAD)) && feedState == FEED_IDLE && !loadPeel &&
                       count >= COUNT_MIN && count <= (jog ? JOG_MAX_EVENTS : VALUE_MAX);
    if (accepted) {
        jogPeelHold = jog;
        jogItems = items;
        moveDeadlineMs = jog ? JOG_STARTUP_BUDGET_MS + count * JOG_EVENT_BUDGET_MS : FEED_TIMEOUT_MS;
        retractMove = retract;
        if (jog) {
            HAL_GPIO_WritePin(MOTOR_PORT, MOTOR_PEEL_A_PIN | MOTOR_PEEL_B_PIN, GPIO_PIN_SET);
            peelRunning = 0;
            peelOffAt = HAL_GetTick();
        }
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
        feedStartedAt = lastProgressAt = HAL_GetTick();
        feedState = FEED_RUNNING;
        HAL_GPIO_WritePin(MOTOR_PORT, ((!!(motorOptions & OPTION_FEED_REVERSE)) ^ retractMove) ? MOTOR_INDEX_B_PIN : MOTOR_INDEX_A_PIN, GPIO_PIN_SET);
        HAL_GPIO_WritePin(MOTOR_PORT, ((!!(motorOptions & OPTION_FEED_REVERSE)) ^ retractMove) ? MOTOR_INDEX_A_PIN : MOTOR_INDEX_B_PIN, GPIO_PIN_RESET);
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
        if (!jogPeelHold) Stock_Advance();
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
static void ReportDiagnostics(uint32_t nonce) {
    uint32_t mask = __get_PRIMASK();
    __disable_irq();
    uint32_t flags = currentCount | ((uint32_t)faultReason << 8) |
                     ((uint32_t)feedState << 16) | ((uint32_t)mode << 20) |
                     ((uint32_t)PeelRequested() << 24) |
                     ((uint32_t)peelRunning << 25) | ((uint32_t)feedReady << 26) |
                     ((uint32_t)(currentAddr >= ADDRESS_MIN && currentAddr <= VALUE_MAX) << 27) |
                     ((uint32_t)(currentType > 8U) << 28) |
                     ((uint32_t)Feeder_TypeValid(currentType) << 29) |
                     ((uint32_t)(currentType == 12U ? 1U : currentType == 16U ? 2U : currentType == 24U ? 3U : 0U) << 30);
    uint32_t values[] = {nonce, monitorToken[0], monitorToken[1], movementTotal, flags};
    __set_PRIMASK(mask);
    Boot_Reply(currentAddr, "DIAG", values, 5);
}

// Test replies fit the existing five-word packet. Raw contact and interpreted
// request are separate; debounced transition counts retain short switch presses.
static void ReportTest(uint32_t nonce) {
    uint32_t mask = __get_PRIMASK();
    __disable_irq();
    uint32_t flags = (mode == MODE_TEST) |
        ((uint32_t)(HAL_GPIO_ReadPin(PEEL_SWITCH_PORT, PEEL_SWITCH_PIN) == GPIO_PIN_RESET) << 1) |
        ((uint32_t)PeelRequested() << 2) | ((uint32_t)peelRunning << 3) |
        ((uint32_t)(feedState == FEED_RUNNING) << 4) |
        ((uint32_t)(HAL_GPIO_ReadPin(BUTTON_PORT, BUTTON_PIN) == GPIO_PIN_RESET) << 5) |
        ((uint32_t)(HAL_GPIO_ReadPin(MENU_BUTTON_PORT, MENU_BUTTON_PIN) == GPIO_PIN_RESET) << 6) |
        ((uint32_t)(HAL_GPIO_ReadPin(COUNT_PORT, COUNT_PIN) == GPIO_PIN_SET) << 7);
    uint32_t values[] = {nonce, flags, testSwitchChanges, HAL_GetTick(), movementTotal};
    __set_PRIMASK(mask);
    Boot_Reply(currentAddr, "TEST", values, 5);
}

static void ProcessRS485(void) {
    char line[RX_BUFFER_SIZE];
    if (!RS485_ReadLine(line, sizeof(line))) return;
    // Firmware commands use a separate addressed, checksummed grammar. Legacy
    // feed commands stay compatible. CRC includes the destination feeder ID.
    if (line[0] == 'B') {
        char* command = Boot_DecodePacket(line, currentAddr);
        if (command == NULL) return;
        if (!strncmp(command, "HEALTH ", 7) || !strncmp(command, "FAULTINFO ", 10)) {
            uint8_t health = command[0] == 'H';
            const char* text = command + (health ? 7 : 10); uint32_t nonce;
            if (!Boot_ParseHex(&text, &nonce) || *text) return;
            uint32_t mask = __get_PRIMASK(); __disable_irq();
            uint32_t values[] = {nonce, faultFlags, faultTarget, faultReceived, faultDuration};
            if (health) { values[1] = Board_ResetFlags(); values[2] = HAL_GetTick(); }
            __set_PRIMASK(mask);
            Boot_Reply(currentAddr, health ? "HEALTH" : "FAULTINFO", values, health ? 3 : 5);
            return;
        }
        if (!strncmp(command, "LOAD ", 5)) {
            const char* text = command + 5; uint32_t values[5];
            for (uint8_t i = 0; i < 5; i++)
                if (!Boot_ParseHex(&text, &values[i]) || (i < 4 ? *text++ != ' ' : *text)) return;
            if (values[1] != HAL_GetUIDw0() || values[2] != HAL_GetUIDw1() || values[3] != HAL_GetUIDw2() || values[4] > 3U) return;
            uint32_t mask = __get_PRIMASK(); __disable_irq();
            uint8_t allowed = (mode == MODE_NORMAL || mode == MODE_LOAD) && !settingsFault && !optionsFault &&
                              Feeder_TypeValid(currentType) && currentAddr >= ADDRESS_MIN && currentAddr <= VALUE_MAX && !locateToggles &&
                              ((feedState == FEED_IDLE && (!peelRunning || values[4] == 1U)) || (mode == MODE_LOAD && (values[4] == 3U || (values[4] == 0U && feedState == FEED_FAULT))));
            // Other actions require an explicitly entered loading mode.
            if (values[4] >= 2U && mode != MODE_LOAD) allowed = 0;
            if (allowed) {
                Board_MotorIdle(); loadPeel = peelRunning = peelClosed = 0;
                peelOffAt = HAL_GetTick(); jogPeelHold = 1;
                if (values[4] == 3U && feedState != FEED_FAULT) {
                    if (requestResult == REQUEST_RUNNING) requestResult = REQUEST_FAULT;
                    feedState = FEED_IDLE;
                }
                mode = values[4] == 0U ? MODE_NORMAL : MODE_LOAD;
                if (values[4] == 2U && feedState == FEED_IDLE && PeelRequested()) loadPeel = 1;
                feedButtonEligible = buttonEligible = 0;
                displayDirty = 1;
            }
            uint32_t reply[] = {values[0], mode == MODE_LOAD, loadPeel};
            __set_PRIMASK(mask);
            Boot_Reply(currentAddr, allowed ? "LOAD" : "BUSY", reply, allowed ? 3 : 1);
            return;
        }
        if (!strncmp(command, "STOCKREAD ", 10) || !strncmp(command, "SETSTOCK ", 9)) {
            uint8_t setting = command[0] == 'S' && command[1] == 'E';
            const char* text = command + (setting ? 9 : 10);
            uint32_t values[5]; uint8_t count = setting ? 5 : 1;
            for (uint8_t i = 0; i < count; i++)
                if (!Boot_ParseHex(&text, &values[i]) || (i + 1 < count ? *text++ != ' ' : *text != 0)) return;
            if (setting) {
                if (values[1] != HAL_GetUIDw0() || values[2] != HAL_GetUIDw1() || values[3] != HAL_GetUIDw2()) return;
                if (values[4] > STOCK_MAX) { Boot_Reply(currentAddr, "ERROR QUANTITY", NULL, 0); return; }
                if (settingsFault || feedState == FEED_RUNNING || feedState == FEED_RESERVED || mode != MODE_NORMAL) {
                    Boot_Reply(currentAddr, "BUSY", values, 1); return;
                }
                Stock_Set((uint16_t)values[4]); displayDirty = 1;
            }
            if (settingsFault || (setting && !Stock_Flush())) {
                settingsFault = 1; Motor_Fault(FAULT_SETTINGS);
                Boot_Reply(currentAddr, "ERROR EEPROM", NULL, 0); return;
            }
            uint32_t reply[4] = {values[0], 0, 0, 0};
            uint32_t mask = __get_PRIMASK(); __disable_irq();
            Stock_Read(&reply[1], &reply[2], &reply[3]);
            __set_PRIMASK(mask);
            Boot_Reply(currentAddr, "STOCK", reply, 4);
            return;
        }
        if (!strncmp(command, "TESTREAD ", 9)) {
            const char* text = command + 9;
            uint32_t nonce;
            if (!Boot_ParseHex(&text, &nonce) || *text) return;
            ReportTest(nonce);
            return;
        }
        if (!strncmp(command, "TEST ", 5)) {
            const char* text = command + 5;
            uint32_t values[5];
            for (uint8_t i = 0; i < 5; i++) {
                if (!Boot_ParseHex(&text, &values[i]) || (i < 4 ? *text++ != ' ' : *text != 0)) return;
            }
            if (values[1] != HAL_GetUIDw0() || values[2] != HAL_GetUIDw1() || values[3] != HAL_GetUIDw2() || values[4] > 1U) return;
            uint32_t mask = __get_PRIMASK();
            __disable_irq();
            uint8_t allowed = (mode == MODE_NORMAL || mode == MODE_TEST) &&
                              (feedState == FEED_IDLE || feedState == FEED_FAULT);
            if (allowed) {
                Board_MotorIdle();
                peelRunning = peelClosed = 0;
                peelOffAt = HAL_GetTick();
                if (values[4] && mode != MODE_TEST) {
                    testSwitchRaw = testSwitchStable = HAL_GPIO_ReadPin(PEEL_SWITCH_PORT, PEEL_SWITCH_PIN) == GPIO_PIN_RESET;
                    testSwitchChanges = 0;
                    testSwitchChangedAt = HAL_GetTick();
                }
                mode = values[4] ? MODE_TEST : MODE_NORMAL;
                feedReady = !values[4] && !settingsFault && !optionsFault && feedState == FEED_IDLE;
                feedButtonEligible = buttonEligible = 0;
                locateToggles = 0;
                displayDirty = 1;
            }
            __set_PRIMASK(mask);
            if (allowed) ReportTest(values[0]);
            else Boot_Reply(currentAddr, "BUSY", values, 1);
            return;
        }
        if (!strncmp(command, "CLEAR ", 6)) {
            const char* text = command + 6;
            uint32_t values[4];
            for (uint8_t i = 0; i < 4; i++) {
                if (!Boot_ParseHex(&text, &values[i]) || (i < 3 ? *text++ != ' ' : *text != 0)) return;
            }
            if (values[1] != HAL_GetUIDw0() || values[2] != HAL_GetUIDw1() || values[3] != HAL_GetUIDw2()) return;
            uint8_t result = ClearFault();
            Boot_Reply(currentAddr, result == 1U ? "BUSY" : result == 2U ? "ERROR SETTINGS" : "CLEARED", values, 1);
            return;
        }
        if (!strncmp(command, "STOP ", 5)) {
            const char* text = command + 5;
            uint32_t nonce;
            if (!Boot_ParseHex(&text, &nonce) || *text) return;
            Motor_Fault(FAULT_STOP);
            Boot_Reply(currentAddr, "STOPPED", &nonce, 1);
            return;
        }
        if (!strncmp(command, "DIAG ", 5) || !strncmp(command, "MONITOR ", 8)) {
            uint8_t claim = command[0] == 'M';
            const char* text = command + (claim ? 8 : 5);
            uint32_t nonce, token[2];
            if (!Boot_ParseHex(&text, &nonce)) return;
            if (claim) {
                if (*text++ != ' ' || !Boot_ParseHex(&text, &token[0]) ||
                    *text++ != ' ' || !Boot_ParseHex(&text, &token[1]) || *text ||
                    !(token[0] | token[1])) return;
                // A claimed token is immutable until MCU reset. Claiming it
                // never clears movement, changes settings or permits motion.
                if (!(monitorToken[0] | monitorToken[1])) {
                    monitorToken[0] = token[0]; monitorToken[1] = token[1];
                }
            } else if (*text) return;
            ReportDiagnostics(nonce);
            return;
        }
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
        if (!strncmp(command, "CONFIG ", 7)) {
            const char* text = command + 7;
            uint32_t nonce;
            if (!Boot_ParseHex(&text, &nonce) || *text) return;
            uint32_t values[] = {nonce, !!(motorOptions & OPTION_FEED_REVERSE),
                                !!(motorOptions & OPTION_PEEL_REVERSE),
                                !!(motorOptions & OPTION_SWITCH_NO)};
            Boot_Reply(currentAddr, "CONFIG", values, 4);
            return;
        }
        if (!strncmp(command, "TYPE ", 5)) {
            const char* text = command + 5;
            uint32_t nonce;
            if (!Boot_ParseHex(&text, &nonce) || *text) return;
            uint32_t values[] = {nonce, currentType, currentCount,
                                 currentType == 8U ? 2000U : Feeder_TypeValid(currentType) ? 4000U : 0U};
            Boot_Reply(currentAddr, "TYPE", values, 4);
            return;
        }
        if (!strncmp(command, "LOCATE ", 7)) {
            const char* text = command + 7;
            uint32_t nonce;
            if (!Boot_ParseHex(&text, &nonce) || *text) return;
            if (settingsFault || feedState != FEED_IDLE || mode != MODE_NORMAL) {
                Boot_Reply(currentAddr, "BUSY", &nonce, 1);
            } else {
                uint32_t mask = __get_PRIMASK();
                __disable_irq();
                Board_MotorIdle();
                peelRunning = 0;
                peelOffAt = HAL_GetTick();
                locateToggles = 20;
                __set_PRIMASK(mask);
                locateBlank = 0; locateTick = HAL_GetTick();
                feedbackToggles = 0;
                LED_ON(); displayDirty = 1;
                Boot_Reply(currentAddr, "LOCATING", &nonce, 1);
            }
            return;
        }
        if (settingsFault) return;
        if (!strncmp(command, "SETCONFIG ", 10)) {
            const char* text = command + 10;
            uint32_t values[7];
            for (uint8_t i = 0; i < 7; i++) {
                if (!Boot_ParseHex(&text, &values[i]) || (i < 6 ? *text++ != ' ' : *text != 0)) return;
            }
            if (values[1] != HAL_GetUIDw0() || values[2] != HAL_GetUIDw1() || values[3] != HAL_GetUIDw2()) return;
            if (values[4] > 1U || values[5] > 1U || values[6] > 1U)
                Boot_Reply(currentAddr, "ERROR CONFIG", NULL, 0);
            else if (!BeginRemoteSettings())
                Boot_Reply(currentAddr, "ERROR BUSY", NULL, 0);
            else {
                uint8_t saved = SaveOptions((uint8_t)(values[4] | (values[5] << 1) | (values[6] << 2)));
                EndRemoteSettings();
                if (!saved) Boot_Reply(currentAddr, "ERROR EEPROM", NULL, 0);
                else {
                    uint32_t reply[] = {values[0], values[4], values[5], values[6]};
                    Boot_Reply(currentAddr, "CONFIGSET", reply, 4);
                    uiLastAction = HAL_GetTick();
                }
            }
            return;
        }
        if (!strncmp(command, "SETCOUNT ", 9)) {
            const char* text = command + 9;
            uint32_t values[5];
            for (uint8_t i = 0; i < 5; i++) {
                if (!Boot_ParseHex(&text, &values[i]) || (i < 4 ? *text++ != ' ' : *text != 0)) return;
            }
            if (values[1] != HAL_GetUIDw0() || values[2] != HAL_GetUIDw1() || values[3] != HAL_GetUIDw2()) return;
            if (values[4] < COUNT_MIN || values[4] > VALUE_MAX)
                Boot_Reply(currentAddr, "ERROR COUNT", NULL, 0);
            else if (!BeginRemoteSettings()) Boot_Reply(currentAddr, "ERROR BUSY", NULL, 0);
            else {
                uint8_t saved = SaveSetting(EEPROM_COUNT_ADDR, (uint8_t)values[4]);
                if (saved) currentCount = (uint8_t)values[4];
                EndRemoteSettings();
                if (!saved) Boot_Reply(currentAddr, "ERROR EEPROM", NULL, 0);
                else {
                    uint32_t reply[] = {values[0], currentCount};
                    Boot_Reply(currentAddr, "COUNTSET", reply, 2);
                    displayDirty = 1;
                }
            }
            return;
        }
        if (!strncmp(command, "SETTYPE ", 8)) {
            const char* text = command + 8;
            uint32_t values[5];
            for (uint8_t i = 0; i < 5; i++) {
                if (!Boot_ParseHex(&text, &values[i]) || (i < 4 ? *text++ != ' ' : *text != 0)) return;
            }
            if (values[1] != HAL_GetUIDw0() || values[2] != HAL_GetUIDw1() || values[3] != HAL_GetUIDw2()) return;
            if (!Feeder_TypeValid(values[4])) Boot_Reply(currentAddr, "ERROR TYPE", NULL, 0);
            else if (!BeginRemoteSettings()) Boot_Reply(currentAddr, "ERROR BUSY", NULL, 0);
            else {
                uint8_t saved = SaveType((uint8_t)values[4]);
                if (saved) currentType = (uint8_t)values[4];
                EndRemoteSettings();
                if (!saved) Boot_Reply(currentAddr, "ERROR EEPROM", NULL, 0);
                else {
                    uint32_t reply[] = {values[0], currentType};
                    Boot_Reply(currentAddr, "TYPESET", reply, 2);
                    uiLastAction = HAL_GetTick();
                    displayDirty = 1;
                }
            }
            return;
        }
        if (!strncmp(command, "SETID ", 6)) {
            const char* text = command + 6;
            uint32_t values[5];
            for (uint8_t i = 0; i < 5; i++) {
                if (!Boot_ParseHex(&text, &values[i]) || (i < 4 ? *text++ != ' ' : *text != 0)) return;
            }
            if (values[1] != HAL_GetUIDw0() || values[2] != HAL_GetUIDw1() || values[3] != HAL_GetUIDw2()) return;
            if (values[4] < ADDRESS_MIN || values[4] > VALUE_MAX) {
                Boot_Reply(currentAddr, "ERROR ID", NULL, 0);
            } else if (mode != MODE_ASSIGN || feedState != FEED_IDLE) {
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
        } else if (!strncmp(command, "JOG ", 4)) {
            const char* text = command + 4;
            uint32_t values[4]; // request tokens, retract (0/1), items
            for (uint8_t i = 0; i < 4; i++) {
                if (!Boot_ParseHex(&text, &values[i]) || (i < 3 ? *text++ != ' ' : *text != 0)) return;
            }
            if (values[2] > 1U || values[3] < 1U || values[3] > JOG_MAX_EVENTS ||
                currentCount < COUNT_MIN || values[3] > JOG_MAX_EVENTS / currentCount) {
                Boot_Reply(currentAddr, "ERROR JOG", NULL, 0);
                return;
            }
            uint8_t accepted = Motor_ReserveMove(values[3] * currentCount, 1, (uint8_t)values[2], values[3]);
            if (accepted) {
                requestTokens[0] = values[0]; requestTokens[1] = values[1];
                requestResult = REQUEST_RUNNING;
            }
            Boot_Reply(currentAddr, accepted ? "ACCEPT" :
                       (feedState == FEED_FAULT || currentAddr < ADDRESS_MIN || !Feeder_TypeValid(currentType) ? "FAULT" : "BUSY"), values, 2);
            if (accepted) Motor_Start();
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
            Boot_Reply(currentAddr, accepted ? "ACCEPT" :
                       (feedState == FEED_FAULT || currentAddr < ADDRESS_MIN || !Feeder_TypeValid(currentType) ? "FAULT" : "BUSY"), values, 2);
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

// Count edges during an active feed. No bit-banged transfers or delays here.
void EXTI3_IRQHandler(void) {
    if (__HAL_GPIO_EXTI_GET_IT(COUNT_PIN) != RESET) {
        __HAL_GPIO_EXTI_CLEAR_IT(COUNT_PIN);
        uint32_t irqMask = __get_PRIMASK();
        __disable_irq();
        movementTotal++;
        if (feedState == FEED_RUNNING) {
            lastProgressAt = HAL_GetTick();
            if (++pa3TriggerCount >= motorCount) Motor_Stop();
        }
        __set_PRIMASK(irqMask);
    }
}

// Read both settings without manufacturing defaults on communication failures.
// Only a successfully read blank address may become commissioning ID 0.
static uint8_t LoadSettings(void) {
    uint8_t address, count, type, typeCheck;
    if (!EEPROM_ReadChecked(EEPROM_DATA_ADDR, &address) ||
        !EEPROM_ReadChecked(EEPROM_COUNT_ADDR, &count) ||
        !EEPROM_ReadChecked(EEPROM_TYPE_ADDR, &type) ||
        !EEPROM_ReadChecked(EEPROM_TYPE_CHECK_ADDR, &typeCheck)) return 0;
    if (address == 0xFFU) {
        address = DEFAULT_ADDRESS;
        if (!EEPROM_WriteByte(EEPROM_DATA_ADDR, address)) return 0;
    } else if (address > VALUE_MAX) return 0;
    uint8_t validType = Feeder_TypeValid(type) && (uint8_t)(type ^ typeCheck) == 0xFFU ? type : 0;
    if (count < COUNT_MIN || count > VALUE_MAX) {
        count = validType == 8U ? DEFAULT_COUNT_8MM : DEFAULT_COUNT;
        if (!EEPROM_WriteByte(EEPROM_COUNT_ADDR, count)) return 0;
    }
    currentType = validType;
    if (!LoadOptions()) return 0;
    currentAddr = address;
    currentCount = count;
    return 1;
}

// Finish settings, feedback and startup output before enabling feed inputs.
// feedReady remains false until every startup idle-output write is complete.
void Feeder_Init(void) {
    feedReady = 0;
    HAL_GPIO_WritePin(MOTOR_PORT, MOTOR_ALL_PINS, GPIO_PIN_SET);
    buttonRaw = buttonStable = HAL_GPIO_ReadPin(MENU_BUTTON_PORT, MENU_BUTTON_PIN) != GPIO_PIN_RESET;
    buttonReady = buttonStable;
    feedButtonRaw = feedButtonStable = HAL_GPIO_ReadPin(BUTTON_PORT, BUTTON_PIN) != GPIO_PIN_RESET;
    feedButtonReady = feedButtonStable;
    while (!LoadSettings() || !Stock_Init()) {
        CH455_RefreshFault(FAULT_SETTINGS);
        LED_ON();
        delay_ms(100);
        Board_WatchdogFeed(); // Invalid settings can wait here without rebooting.
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

    // Best-effort startup hello. Stagger IDs; polling handles any collision/loss.
    {
        uint32_t uid[] = {HAL_GetUIDw0(), HAL_GetUIDw1(), HAL_GetUIDw2()};
        Board_WatchdogFeed();
        delay_ms(currentAddr * 12U + (uid[0] & 7U));
        Boot_Reply(currentAddr, "ONLINE", uid, 3);
    }

    Board_MotorIdle();
    LED_OFF();
    displayDirty = 1;
    RefreshDisplay();

    // No startup path can drive idle outputs after feeds become eligible.
    uint32_t irqMask = __get_PRIMASK();
    __disable_irq();
    Board_EnableFeedInterrupts();
    if (optionsFault) Motor_Fault(FAULT_SETTINGS);
    else feedReady = 1;
    __set_PRIMASK(irqMask);
}

// Process one queued command per pass and repaint only when state changes.
// Button feedback is nonblocking; SysTick independently enforces the deadline.
void Feeder_Run(void) {
    if (!settingsFault && !Stock_Flush()) { settingsFault = 1; Motor_Fault(FAULT_SETTINGS); }
    KeyScan();
    ProcessRS485();
    UpdateFeedback();
    UpdateLocate();
    uint32_t quantity, completed, sequence;
    Stock_Read(&quantity, &completed, &sequence);
    uint8_t showEmpty = quantity == 0 && ((HAL_GetTick() / 1000U) & 1U);
    if (showEmpty != emptyShown) { emptyShown = showEmpty; displayDirty = 1; }
    if (displayDirty) RefreshDisplay();
    if (feedState == FEED_FAULT) LED_ON();
    delay_ms(5);
}

// SysTick owns tension sampling and peel output changes, so a blocking display
// or serial transaction cannot leave a released/tensioned switch ignored.
void Feeder_Tick(void) {
    uint32_t now = HAL_GetTick();
    if (manualTriggerMute > 0) manualTriggerMute--;
    if (feedState == FEED_RUNNING &&
        ((uint32_t)(now - feedStartedAt) >= moveDeadlineMs ||
         (jogPeelHold && (uint32_t)(now - lastProgressAt) >= JOG_STALL_TIMEOUT_MS))) {
        Motor_Fault(FAULT_INDEX);
        LED_ON();
    }
    if (mode == MODE_TEST) {
        uint8_t raw = HAL_GPIO_ReadPin(PEEL_SWITCH_PORT, PEEL_SWITCH_PIN) == GPIO_PIN_RESET;
        if (raw != testSwitchRaw) { testSwitchRaw = raw; testSwitchChangedAt = now; }
        if (raw != testSwitchStable && (uint32_t)(now - testSwitchChangedAt) >= PEEL_DEBOUNCE_MS) {
            testSwitchStable = raw;
            testSwitchChanges++;
        }
    }
    uint8_t closed = PeelRequested();
    if (!closed) peelClosed = 0;
    else if (!peelClosed) { peelClosed = 1; peelClosedAt = now; }
    if (mode == MODE_LOAD && loadPeel && !closed) loadPeel = 0;
    uint8_t permitted = feedReady && ((!jogPeelHold && mode == MODE_NORMAL) || (mode == MODE_LOAD && loadPeel)) && Feeder_TypeValid(currentType) && !locateToggles && currentAddr >= ADDRESS_MIN && currentAddr <= VALUE_MAX &&
                        feedState != FEED_FAULT;
    if (!permitted || !closed) {
        if (peelRunning) {
            HAL_GPIO_WritePin(MOTOR_PORT, MOTOR_PEEL_A_PIN | MOTOR_PEEL_B_PIN, GPIO_PIN_SET);
            peelRunning = 0;
            peelOffAt = now;
        }
    } else if (peelRunning) {
        if ((uint32_t)(now - peelStartedAt) >= PEEL_TIMEOUT_MS) { Motor_Fault(FAULT_PEEL); LED_ON(); }
    } else if ((uint32_t)(now - peelClosedAt) >= PEEL_DEBOUNCE_MS &&
               (uint32_t)(now - peelOffAt) >= PEEL_RESTART_MS) {
        HAL_GPIO_WritePin(MOTOR_PORT, (motorOptions & OPTION_PEEL_REVERSE) ? MOTOR_PEEL_A_PIN : MOTOR_PEEL_B_PIN, GPIO_PIN_SET);
        HAL_GPIO_WritePin(MOTOR_PORT, (motorOptions & OPTION_PEEL_REVERSE) ? MOTOR_PEEL_B_PIN : MOTOR_PEEL_A_PIN, GPIO_PIN_RESET);
        peelStartedAt = now;
        peelRunning = 1;
    }
}
