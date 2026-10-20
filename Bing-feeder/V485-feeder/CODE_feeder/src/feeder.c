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

// Operating modes
#define MODE_NORMAL  0                  // Normal mode
#define MODE_ADDR    1                  // Address adjustment mode
#define MODE_COUNT   2                  // Count adjustment mode
static volatile uint8_t mode = MODE_NORMAL;

// RESERVED claims the next feed while the RS485 acceptance reply is sent.
// External/manual triggers cannot replace its count during that turnaround.
typedef enum { FEED_IDLE, FEED_RESERVED, FEED_RUNNING, FEED_FAULT } FeedState;
static volatile FeedState feedState = FEED_IDLE;
static volatile uint8_t feedReady = 0;
static volatile uint8_t pa3TriggerCount = 0;
static volatile uint8_t motorCount = 0;
static volatile uint32_t feedStartedAt = 0;
static volatile uint32_t pa4TriggerMute = 0;  // PA2 manual-trigger inhibition
static volatile uint8_t displayDirty = 1;

// Button states: 0 = released, 1 = confirm on next scan, 2 = held.
// Short/long flags record events; ignoreShort suppresses the next short event
// after a mode change. These are scan-based states, not a hardware debounce.
typedef struct {
    uint8_t  state;
    uint32_t press_tick;
    uint8_t  short_trig;
    uint8_t  long_trig;
    uint8_t  ignoreShort;
} KEY_Typedef;
static KEY_Typedef key_inc;                    // PA2 button
static KEY_Typedef key_dec;                    // PA4 button

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
                    ? motorCount : (mode == MODE_COUNT ? currentCount : currentAddr);
    displayDirty = 0;
    __set_PRIMASK(irqMask);

    if (state == FEED_FAULT) {
        CH455_SetDisplay(1, DISPLAY_ERROR_SEGMENTS);
        CH455_SetDisplay(3, DISPLAY_ERROR_SEGMENTS);
        LED_ON();
    } else {
        CH455_RefreshNum(value);
    }
}

// Blocking feedback: period_ms is each on/off interval. display_num=0xFFFF
// leaves the displayed number alone; other values are shown then restored.
static void led_flash_times(uint8_t times, uint16_t period_ms, uint16_t display_num) {
    if (display_num != 0xFFFF) {
        for (uint8_t i = 0; i < times; i++) {
            CH455_RefreshNum(display_num);
            LED_ON();
            delay_ms(period_ms);
            LED_OFF();
            delay_ms(period_ms);
        }
        RefreshDisplay();
    } else {
        for (uint8_t i = 0; i < times; i++) {
            LED_ON();
            delay_ms(period_ms);
            LED_OFF();
            delay_ms(period_ms);
        }
    }
}

// Poll the active-low keys from main context. Release before SHORT_PRESS_TIME
// creates a short event; holding for LONG_PRESS_TIME changes the key's mode.
// EEPROM writes, LED feedback and display updates may block this main-loop pass.
static void KeyScan(void) {
    // ---------- PA4 (key_dec): decrement / address-mode key ----------
    // The original local name inc_pin reads PA4; retained to avoid a logic edit.
    uint8_t inc_pin = HAL_GPIO_ReadPin(BUTTON_PORT, BUTTON_DEC_PIN);
    switch (key_dec.state) {
        case 0U:
            if (inc_pin == 0U) { key_dec.state = 1U; key_dec.press_tick = HAL_GetTick(); key_dec.long_trig = 0; }
            break;
        case 1U:
            if (inc_pin == 0U) key_dec.state = 2U;
            else               key_dec.state = 0U;
            break;
        case 2U:
            if (inc_pin == 1U) {
                if (HAL_GetTick() - key_dec.press_tick < SHORT_PRESS_TIME)
                    key_dec.short_trig = 1U;
                key_dec.state = 0U;
            } else {
                if ((HAL_GetTick() - key_dec.press_tick >= LONG_PRESS_TIME) && !key_dec.long_trig) {
                    key_dec.long_trig = 1U;
                    if (mode == MODE_NORMAL) {
                        mode = MODE_ADDR;
                        led_flash_times(3, 200, 0xFFFF);
                        key_dec.ignoreShort = 1;
                        RefreshDisplay();
                    } else if (mode == MODE_ADDR) {
                        mode = MODE_NORMAL;
                        led_flash_times(3, 200, 0xFFFF);
                        key_dec.ignoreShort = 1;
                        RefreshDisplay();
                    }
                    key_dec.state = 0U;
                }
            }
            break;
    }

    // ---------- PA2 (key_inc): increment / count-mode / manual-feed key ----------
    // Likewise, the original dec_pin local reads PA2.
    uint8_t dec_pin = HAL_GPIO_ReadPin(BUTTON_PORT, BUTTON_INC_PIN);
    switch (key_inc.state) {
        case 0U:
            if (dec_pin == 0U) { key_inc.state = 1U; key_inc.press_tick = HAL_GetTick(); key_inc.long_trig = 0; }
            break;
        case 1U:
            if (dec_pin == 0U) key_inc.state = 2U;
            else               key_inc.state = 0U;
            break;
        case 2U:
            if (dec_pin == 1U) {
                if (HAL_GetTick() - key_inc.press_tick < SHORT_PRESS_TIME)
                    key_inc.short_trig = 1U;
                key_inc.state = 0U;
            } else {
                if ((HAL_GetTick() - key_inc.press_tick >= LONG_PRESS_TIME) && !key_inc.long_trig) {
                    key_inc.long_trig = 1U;
                    if (mode == MODE_NORMAL) {
                        mode = MODE_COUNT;
                        led_flash_times(3, 200, 0xFFFF);
                        key_inc.ignoreShort = 1;
                        RefreshDisplay();
                    } else if (mode == MODE_COUNT) {
                        mode = MODE_NORMAL;
                        led_flash_times(3, 200, 0xFFFF);
                        key_inc.ignoreShort = 1;
                        RefreshDisplay();
                    }
                    key_inc.state = 0U;
                }
            }
            break;
    }

    // ---------- Short press handling: PA4 ----------
    if (key_dec.short_trig) {
        key_dec.short_trig = 0U;
        if (key_dec.ignoreShort) {
            key_dec.ignoreShort = 0U;
        } else {
            if (mode == MODE_ADDR) {
                if (currentAddr > VALUE_MIN) {
                    currentAddr--;
                    EEPROM_WriteByte(EEPROM_DATA_ADDR, currentAddr);
                    led_flash_times(1, 200, 0xFFFF);
                    RefreshDisplay();
                }
            } else if (mode == MODE_COUNT) {
                if (currentCount > COUNT_MIN) {
                    currentCount--;
                    EEPROM_WriteByte(EEPROM_COUNT_ADDR, currentCount);
                    led_flash_times(1, 200, 0xFFFF);
                    RefreshDisplay();
                }
            }
        }
    }

    // ---------- Short press handling: PA2 ----------
    if (key_inc.short_trig) {
        key_inc.short_trig = 0U;
        if (key_inc.ignoreShort) {
            key_inc.ignoreShort = 0U;
        } else {
            if (mode == MODE_ADDR) {
                if (currentAddr < VALUE_MAX) {
                    currentAddr++;
                    EEPROM_WriteByte(EEPROM_DATA_ADDR, currentAddr);
                    led_flash_times(1, 200, 0xFFFF);
                    RefreshDisplay();
                }
            } else if (mode == MODE_COUNT) {
                if (currentCount < VALUE_MAX) {
                    currentCount++;
                    EEPROM_WriteByte(EEPROM_COUNT_ADDR, currentCount);
                    led_flash_times(1, 200, 0xFFFF);
                    RefreshDisplay();
                }
            } else {
                // Reserve atomically, just like an addressed serial command.
                if (pa4TriggerMute == 0 && Motor_Reserve(0)) {
                    Motor_Start();
                    pa4TriggerMute = MANUAL_TRIGGER_MUTE_MS;
                }
            }
        }
    }
}

// Claim a feed and its resolved count before any ACK delay or motor output.
// F0/manual/external requests use the positive stored default. All callers use
// this same guarded transition so no trigger can overwrite a reserved command.
static uint8_t Motor_Reserve(uint8_t requestedCount) {
    uint32_t irqMask = __get_PRIMASK();
    __disable_irq();
    uint8_t count = requestedCount ? requestedCount : currentCount;
    uint8_t accepted = feedReady && feedState == FEED_IDLE &&
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
        HAL_GPIO_WritePin(MOTOR_PORT, MOTOR_INDEX_A_PIN | MOTOR_PEEL_B_PIN, GPIO_PIN_SET);
        HAL_GPIO_WritePin(MOTOR_PORT, MOTOR_INDEX_B_PIN | MOTOR_PEEL_A_PIN, GPIO_PIN_RESET);
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
        Board_MotorIdle();
        LED_OFF();
        pa3TriggerCount = 0;
        feedState = FEED_IDLE;
        displayDirty = 1;
    }
    __set_PRIMASK(irqMask);
}

// Handle one parsed command for this address. Busy/OK acknowledge acceptance
// state only; there is no completion reply or transaction identifier.
static void ProcessRS485(void) {
    char line[RX_BUFFER_SIZE];
    if (!RS485_ReadLine(line, sizeof(line))) return;
    // Firmware commands use a separate addressed, checksummed grammar. Legacy
    // feed commands stay compatible. CRC includes the destination feeder ID.
    if (line[0] == 'B') {
        char* command = Boot_DecodePacket(line, currentAddr);
        if (command == NULL) return;
        if (!strcmp(command, "INFO")) {
            BootRecord record;
            uint8_t state;
            if (Boot_ReadRecord(&record, &state) && state == BOOT_VALID) {
                uint32_t values[] = {FEEDER_VARIANT_ID, record.size, record.imageCrc};
                Boot_Reply(currentAddr, "APP", values, 3);
            } else Boot_Reply(currentAddr, "ERROR METADATA", NULL, 0);
        } else if (!strcmp(command, "BOOT")) {
            // Claim shutdown before EEPROM access. External triggers cannot
            // start a feed between the idle check and reset. Fault recovery is
            // allowed, but an active/reserved feed must finish first.
            uint32_t mask = __get_PRIMASK();
            __disable_irq();
            uint8_t busy = feedState == FEED_RUNNING || feedState == FEED_RESERVED;
            if (!busy) {
                feedReady = 0;
                feedState = FEED_FAULT;
                HAL_GPIO_WritePin(MOTOR_PORT, MOTOR_ALL_PINS, GPIO_PIN_SET);
                displayDirty = 1;
            }
            __set_PRIMASK(mask);
            if (busy) Boot_Reply(currentAddr, "ERROR BUSY", NULL, 0);
            else if (!Boot_WriteState(BOOT_REQUESTED))
                Boot_Reply(currentAddr, "ERROR EEPROM", NULL, 0);
            else {
                Boot_Reply(currentAddr, "RESET", NULL, 0);
                NVIC_SystemReset();
            }
        }
        return;
    }
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

// Finish settings, feedback and startup output before enabling feed inputs.
// feedReady remains false until every startup idle-output write is complete.
void Feeder_Init(void) {
    feedReady = 0;
    // Read EEPROM address
    uint8_t saved = EEPROM_ReadByte(EEPROM_DATA_ADDR);
    if (saved != 0xFF && saved <= VALUE_MAX) {
        currentAddr = saved;
    } else {
        currentAddr = DEFAULT_ADDRESS;
        EEPROM_WriteByte(EEPROM_DATA_ADDR, currentAddr);
    }

    // Read EEPROM count
    uint8_t savedCount = EEPROM_ReadByte(EEPROM_COUNT_ADDR);
    if (savedCount >= COUNT_MIN && savedCount <= VALUE_MAX) {
        currentCount = savedCount;
    } else {
        currentCount = DEFAULT_COUNT;
        EEPROM_WriteByte(EEPROM_COUNT_ADDR, currentCount);
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
// Existing key feedback may block main, but SysTick still enforces the deadline.
void Feeder_Run(void) {
    KeyScan();
    ProcessRS485();
    if (displayDirty) RefreshDisplay();
    if (feedState == FEED_FAULT) LED_ON();
    delay_ms(5);
}

// Enforce the total feed deadline in SysTick, even during blocking UI/ACK waits.
// A fault stops BOTH motors and latches until reset. Do not call variant-idle
// here: the wider variant's normal idle deliberately runs the peel motor.
void Feeder_Tick(void) {
    if (pa4TriggerMute > 0) pa4TriggerMute--;
    if (feedState == FEED_RUNNING &&
        (uint32_t)(HAL_GetTick() - feedStartedAt) >= FEED_TIMEOUT_MS) {
        HAL_GPIO_WritePin(MOTOR_PORT, MOTOR_ALL_PINS, GPIO_PIN_SET);
        LED_ON();
        feedState = FEED_FAULT;
        pa3TriggerCount = 0;
        displayDirty = 1;
    }
}
