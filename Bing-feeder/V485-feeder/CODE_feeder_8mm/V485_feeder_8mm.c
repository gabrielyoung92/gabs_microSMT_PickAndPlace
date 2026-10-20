// ============================================================
//  STM32F103 Slave (Feeder) Firmware  8mm  V26
//  Features:
//    1. Encoder PB6 trigger (rising edge), PA3 count (rising edge), motor stops at motorCount
//    2. Buttons PA2/PA4 short press to adjust address/count, long press to switch mode
//    3. RS485 receive N<addr> F<cnt>, execute only when addr==currentAddr
//    4. 24C02 saves address and count
//    5. CH455 digital tube display
//    6. LED indication: on while motor runs, off when stopped; fast flash on button/command
//  Version: V25
// ============================================================

#include "stm32f10x.h"
#include <string.h>
#include <stdlib.h>
#include <stdio.h>
#include <ctype.h>

// ================== Constants ==================
#define RX_BUFFER_SIZE      32      // Max length of a single command line
#define RS485_RX_BUF_SIZE   64      // RS485 ring receive buffer size
#define BLANKING_TIME       120     // Silent window after command execution (ms)
#define LED_FLASH_INTERVAL  100     // LED fast flash interval (ms)
#define SHORT_PRESS_TIME    1000    // Short press threshold (ms)
#define LONG_PRESS_TIME     3000    // Long press threshold (ms)
#define VALUE_MIN           0       // Minimum address/count value
#define VALUE_MAX           99      // Maximum address/count value

// ================== LED ==================
// Active low (common anode / sink current connection)
#define LED_ON()            GPIO_ResetBits(GPIOB, GPIO_Pin_5)
#define LED_OFF()           GPIO_SetBits(GPIOB, GPIO_Pin_5)

// ================== 24C02 ==================
#define I2C_SCL_PIN         GPIO_Pin_15
#define I2C_SDA_PIN         GPIO_Pin_14
#define I2C_PORT            GPIOB
#define EEPROM_ADDR_W       0xA0        // Write address
#define EEPROM_ADDR_R       0xA1        // Read address
#define EEPROM_DATA_ADDR    0x00        // EEPROM offset for saving address
#define EEPROM_COUNT_ADDR   0x01        // EEPROM offset for saving count

// ================== CH455 Digital Tube Driver ==================
#define CH455_SCL_PIN       GPIO_Pin_12
#define CH455_SDA_PIN       GPIO_Pin_13
#define CH455_SCL_PORT      GPIOB
#define CH455_SDA_PORT      GPIOB
#define CH455_SYS_CMD       0x48        // System parameter command
#define CH455_DIG0_WR       0x68        // Digit 0 write
#define CH455_DIG1_WR       0x6A        // Digit 1 write
#define CH455_DIG2_WR       0x6C        // Digit 2 write
#define CH455_DIG3_WR       0x6E        // Digit 3 write
#define CH455_ENA           0x01
#define CH455_INTENS_SHIFT  3

// Seven-segment code table (0~9)
const uint8_t seg_table[] = {
    0x7E, 0x0C, 0xB6, 0x9E, 0xCC, 0xDA, 0xFA, 0x0E, 0xFE, 0xDE
};

// ================== Global Variables ==================
volatile uint32_t sysTick_ms = 0;       // System millisecond counter
volatile uint8_t  currentAddr  = 0;     // Current slave address
volatile uint8_t  currentCount = 0;     // Current default count

// Operating modes
#define MODE_NORMAL  0                  // Normal mode
#define MODE_ADDR    1                  // Address adjustment mode
#define MODE_COUNT   2                  // Count adjustment mode
volatile uint8_t mode = MODE_NORMAL;

volatile uint8_t  encoderMute = 0;      // Only used for RS485 echo prevention
volatile uint8_t  pa3TriggerCount = 0;  // PA3 pulse count
volatile uint8_t  pa3CountEnabled = 0;  // Real busy flag: motor is running
volatile uint32_t pa4TriggerMute = 0;   // PA2 manual trigger debounce

volatile uint8_t  rs485TempCount = 0;   // Count brought by RS485 command
volatile uint8_t  motorCount = 0;       // Number of steps the motor needs to run this time

volatile uint8_t  tempDisplayActive = 0; // Temporary display (during command execution)
volatile uint8_t  tempDisplayValue  = 0; // Temporary display value
volatile uint8_t  keyDisplayActive  = 0; // Temporary display on key trigger

// Key state machine
typedef struct {
    uint8_t  state;
    uint32_t press_tick;
    uint8_t  short_trig;
    uint8_t  long_trig;
    uint8_t  ignoreShort;
} KEY_Typedef;
KEY_Typedef key_inc;                    // PA2 button
KEY_Typedef key_dec;                    // PA4 button

// RS485 ring receive buffer
volatile uint8_t  rs485RxBuf[RS485_RX_BUF_SIZE];
volatile uint16_t rs485RxHead = 0;
volatile uint16_t rs485RxTail = 0;
volatile uint8_t  rs485LineReady = 0;   // Flag: complete line received ('\n')

volatile uint8_t  flashCount = 0;       // Number of pending fast flashes

// ================== Forward Declarations ==================
void delay_ms(uint32_t ms);
void delay_us(uint32_t us);
void SysTick_Init(void);
void CH455_RefreshNum(uint16_t num);
void led_flash_times(uint8_t times, uint16_t period_ms, uint16_t display_num);
void RefreshDisplay(void);
void KeyScan(void);
void Motor_Start(void);
void Motor_Stop(void);
void RS485_SetTransmit(uint8_t enable);
void USART1_SendByte(uint8_t ch);
void USART1_SendString(const char* str);
void USART1_Init(void);
void ProcessRS485(void);

// ================== 24C02 Software I2C ==================
#define SCL_HIGH()  GPIO_SetBits(I2C_PORT, I2C_SCL_PIN)
#define SCL_LOW()   GPIO_ResetBits(I2C_PORT, I2C_SCL_PIN)
#define SDA_HIGH()  GPIO_SetBits(I2C_PORT, I2C_SDA_PIN)
#define SDA_LOW()   GPIO_ResetBits(I2C_PORT, I2C_SDA_PIN)
#define SDA_READ()  GPIO_ReadInputDataBit(I2C_PORT, I2C_SDA_PIN)

void I2C_Software_Init(void) {
    GPIO_InitTypeDef GPIO_InitStruct;
    RCC_APB2PeriphClockCmd(RCC_APB2Periph_GPIOB, ENABLE);
    GPIO_InitStruct.GPIO_Pin   = I2C_SCL_PIN | I2C_SDA_PIN;
    GPIO_InitStruct.GPIO_Mode  = GPIO_Mode_Out_OD;   // Open drain, external pull-up required
    GPIO_InitStruct.GPIO_Speed = GPIO_Speed_50MHz;
    GPIO_Init(I2C_PORT, &GPIO_InitStruct);
    SCL_HIGH(); SDA_HIGH();
    delay_us(5);
}

void I2C_Start(void) {
    SDA_HIGH(); SCL_HIGH(); delay_us(5);
    SDA_LOW();  delay_us(5);
    SCL_LOW();  delay_us(5);
}

void I2C_Stop(void) {
    SDA_LOW();  SCL_HIGH(); delay_us(5);
    SDA_HIGH(); delay_us(5);
}

uint8_t I2C_WriteByte(uint8_t byte) {
    uint8_t i;
    for (i = 0; i < 8; i++) {
        if (byte & 0x80) SDA_HIGH(); else SDA_LOW();
        byte <<= 1;
        SCL_HIGH(); delay_us(2);
        SCL_LOW();  delay_us(2);
    }
    SDA_HIGH();
    SCL_HIGH(); delay_us(3);
    uint8_t ack = SDA_READ();   // Read slave ACK
    SCL_LOW();  delay_us(2);
    return ack;
}

uint8_t I2C_ReadByte(uint8_t ack) {
    uint8_t byte = 0;
    SDA_HIGH();
    for (uint8_t i = 0; i < 8; i++) {
        byte <<= 1;
        SCL_HIGH(); delay_us(2);
        if (SDA_READ()) byte |= 0x01;
        SCL_LOW();  delay_us(2);
    }
    if (ack) SDA_HIGH(); else SDA_LOW();   // Master ACK
    SCL_HIGH(); delay_us(3);
    SCL_LOW();  delay_us(2);
    SDA_HIGH();
    return byte;
}

void EEPROM_WriteByte(uint8_t eeprom_addr, uint8_t data) {
    I2C_Start();
    if (I2C_WriteByte(EEPROM_ADDR_W)) { I2C_Stop(); return; }
    if (I2C_WriteByte(eeprom_addr))   { I2C_Stop(); return; }
    I2C_WriteByte(data);
    I2C_Stop();
    delay_ms(5);                // Wait for EEPROM internal write completion
}

uint8_t EEPROM_ReadByte(uint8_t eeprom_addr) {
    uint8_t data = 0;
    I2C_Start();
    if (I2C_WriteByte(EEPROM_ADDR_W)) { I2C_Stop(); return 0xFF; }
    if (I2C_WriteByte(eeprom_addr))   { I2C_Stop(); return 0xFF; }
    I2C_Start();
    if (I2C_WriteByte(EEPROM_ADDR_R)) { I2C_Stop(); return 0xFF; }
    data = I2C_ReadByte(1);
    I2C_Stop();
    return data;
}

// ================== CH455 Digital Tube ==================
static void CH455_SDA_Out(void) {
    GPIO_InitTypeDef GPIO_InitStruct;
    GPIO_InitStruct.GPIO_Pin   = CH455_SDA_PIN;
    GPIO_InitStruct.GPIO_Mode  = GPIO_Mode_Out_PP;
    GPIO_InitStruct.GPIO_Speed = GPIO_Speed_50MHz;
    GPIO_Init(CH455_SDA_PORT, &GPIO_InitStruct);
}

static void CH455_SDA_In(void) {
    GPIO_InitTypeDef GPIO_InitStruct;
    GPIO_InitStruct.GPIO_Pin   = CH455_SDA_PIN;
    GPIO_InitStruct.GPIO_Mode  = GPIO_Mode_IN_FLOATING;
    GPIO_Init(CH455_SDA_PORT, &GPIO_InitStruct);
}

void CH455_GPIO_Init(void) {
    GPIO_InitTypeDef GPIO_InitStruct;
    RCC_APB2PeriphClockCmd(RCC_APB2Periph_GPIOB, ENABLE);

    GPIO_InitStruct.GPIO_Pin   = CH455_SCL_PIN;
    GPIO_InitStruct.GPIO_Mode  = GPIO_Mode_Out_PP;
    GPIO_InitStruct.GPIO_Speed = GPIO_Speed_50MHz;
    GPIO_Init(CH455_SCL_PORT, &GPIO_InitStruct);

    GPIO_InitStruct.GPIO_Pin   = CH455_SDA_PIN;
    GPIO_InitStruct.GPIO_Mode  = GPIO_Mode_Out_PP;
    GPIO_InitStruct.GPIO_Speed = GPIO_Speed_50MHz;
    GPIO_Init(CH455_SDA_PORT, &GPIO_InitStruct);

    GPIO_SetBits(CH455_SCL_PORT, CH455_SCL_PIN);
    GPIO_SetBits(CH455_SDA_PORT, CH455_SDA_PIN);
}

void CH455_Start(void) {
    CH455_SDA_Out();
    GPIO_SetBits(CH455_SCL_PORT, CH455_SCL_PIN);   delay_us(5);
    GPIO_ResetBits(CH455_SDA_PORT, CH455_SDA_PIN); delay_us(5);
    GPIO_ResetBits(CH455_SCL_PORT, CH455_SCL_PIN);
}

void CH455_Stop(void) {
    CH455_SDA_Out();
    GPIO_ResetBits(CH455_SCL_PORT, CH455_SCL_PIN);
    GPIO_ResetBits(CH455_SDA_PORT, CH455_SDA_PIN); delay_us(5);
    GPIO_SetBits(CH455_SCL_PORT, CH455_SCL_PIN);   delay_us(5);
    GPIO_SetBits(CH455_SDA_PORT, CH455_SDA_PIN);   delay_us(5);
}

void CH455_WriteByte(uint8_t dat) {
    uint8_t i;
    CH455_SDA_Out();
    for (i = 0; i < 8; i++) {
        GPIO_ResetBits(CH455_SCL_PORT, CH455_SCL_PIN); delay_us(2);
        if (dat & 0x80) GPIO_SetBits(CH455_SDA_PORT, CH455_SDA_PIN);
        else            GPIO_ResetBits(CH455_SDA_PORT, CH455_SDA_PIN);
        dat <<= 1; delay_us(2);
        GPIO_SetBits(CH455_SCL_PORT, CH455_SCL_PIN); delay_us(2);
    }
    GPIO_ResetBits(CH455_SCL_PORT, CH455_SCL_PIN);
    CH455_SDA_In();             // Release SDA, ready to read ACK
    delay_us(3);
    GPIO_SetBits(CH455_SCL_PORT, CH455_SCL_PIN);
    delay_us(3);
}

void CH455_WriteCmd(uint8_t byte1, uint8_t byte2) {
    CH455_Start();
    CH455_WriteByte(byte1);
    CH455_WriteByte(byte2);
    CH455_Stop();
}

void CH455_SetSysParam(uint8_t param) {
    CH455_WriteCmd(CH455_SYS_CMD, param);
}

void CH455_SetDisplay(uint8_t dig, uint8_t seg_dat) {
    uint8_t cmd;
    switch (dig) {
        case 0: cmd = CH455_DIG0_WR; break;
        case 1: cmd = CH455_DIG1_WR; break;
        case 2: cmd = CH455_DIG2_WR; break;
        case 3: cmd = CH455_DIG3_WR; break;
        default: return;
    }
    CH455_WriteCmd(cmd, seg_dat);
}

// Refresh digital tube display for a two-digit number (high digit at position 1, low digit at position 3)
void CH455_RefreshNum(uint16_t num) {
    uint8_t lo = num % 10;
    uint8_t hi = num / 10;
    CH455_SetDisplay(1, seg_table[hi]);
    CH455_SetDisplay(3, seg_table[lo]);
}

// ================== Display Refresh ==================
void RefreshDisplay(void) {
    if (tempDisplayActive) {
        CH455_RefreshNum(tempDisplayValue);     // Temporary display takes priority
    } else if (keyDisplayActive) {
        CH455_RefreshNum(currentCount);         // Key trigger displays count
    } else {
        if (mode == MODE_COUNT) CH455_RefreshNum(currentCount);
        else                    CH455_RefreshNum(currentAddr);
    }
}

// ================== LED Fast Flash (blocking) ==================
void led_flash_times(uint8_t times, uint16_t period_ms, uint16_t display_num) {
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

// ================== Buttons ==================
void Key_GPIO_Init(void) {
    GPIO_InitTypeDef GPIO_InitStruct;
    RCC_APB2PeriphClockCmd(RCC_APB2Periph_GPIOA, ENABLE);
    GPIO_InitStruct.GPIO_Pin   = GPIO_Pin_2 | GPIO_Pin_4;
    GPIO_InitStruct.GPIO_Mode  = GPIO_Mode_IN_FLOATING;
    GPIO_InitStruct.GPIO_Speed = GPIO_Speed_50MHz;
    GPIO_Init(GPIOA, &GPIO_InitStruct);
}

// Key scan: state machine, supports short press/long press
void KeyScan(void) {
    // ---------- PA4 (key_dec) ----------
    uint8_t inc_pin = GPIO_ReadInputDataBit(GPIOA, GPIO_Pin_4);
    switch (key_dec.state) {
        case 0U:
            if (inc_pin == 0U) { key_dec.state = 1U; key_dec.press_tick = sysTick_ms; key_dec.long_trig = 0; }
            break;
        case 1U:
            if (inc_pin == 0U) key_dec.state = 2U;
            else               key_dec.state = 0U;
            break;
        case 2U:
            if (inc_pin == 1U) {
                if (sysTick_ms - key_dec.press_tick < SHORT_PRESS_TIME)
                    key_dec.short_trig = 1U;
                key_dec.state = 0U;
            } else {
                if ((sysTick_ms - key_dec.press_tick >= LONG_PRESS_TIME) && !key_dec.long_trig) {
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

    // ---------- PA2 (key_inc) ----------
    uint8_t dec_pin = GPIO_ReadInputDataBit(GPIOA, GPIO_Pin_2);
    switch (key_inc.state) {
        case 0U:
            if (dec_pin == 0U) { key_inc.state = 1U; key_inc.press_tick = sysTick_ms; key_inc.long_trig = 0; }
            break;
        case 1U:
            if (dec_pin == 0U) key_inc.state = 2U;
            else               key_inc.state = 0U;
            break;
        case 2U:
            if (dec_pin == 1U) {
                if (sysTick_ms - key_inc.press_tick < SHORT_PRESS_TIME)
                    key_inc.short_trig = 1U;
                key_inc.state = 0U;
            } else {
                if ((sysTick_ms - key_inc.press_tick >= LONG_PRESS_TIME) && !key_inc.long_trig) {
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
                if (currentCount > VALUE_MIN) {
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
                // Normal mode: PA2 short press = manually trigger motor once
                // Busy check uses pa3CountEnabled
                if (pa4TriggerMute == 0 && pa3CountEnabled == 0) {
                    rs485TempCount = 0;     // 0 means use currentCount
                    Motor_Start();
                    encoderMute = 1;
                    pa4TriggerMute = 300;
                }
            }
        }
    }
}

// ================== Motor ==================
void Motor_Start(void) {
    // Determine how many steps the motor should run this time
    if (rs485TempCount != 0) {
        motorCount = rs485TempCount;        // Count brought by RS485 command
        rs485TempCount = 0;
    } else {
        motorCount = currentCount;          // Manual trigger uses currentCount
        keyDisplayActive = 1;
        RefreshDisplay();
    }

    // Motor start: pull PA7 low, pull PA6 high
    GPIO_SetBits(GPIOA, GPIO_Pin_6);
    GPIO_ResetBits(GPIOA, GPIO_Pin_7);
    LED_ON();
    GPIO_SetBits(GPIOA, GPIO_Pin_12);
    GPIO_ResetBits(GPIOA, GPIO_Pin_8);

    pa3CountEnabled  = 1;                   // Set busy flag
    pa3TriggerCount  = 0;                   // Clear pulse count
}

void Motor_Stop(void) {
    // Motor stop
    GPIO_SetBits(GPIOA, GPIO_Pin_6 | GPIO_Pin_7);
    LED_OFF();
    GPIO_SetBits(GPIOA, GPIO_Pin_12);
    GPIO_SetBits(GPIOA, GPIO_Pin_8);

    pa3TriggerCount = 0;
    pa3CountEnabled = 0;                    // Clear busy flag

    // Restore display
    if (tempDisplayActive) {
        tempDisplayActive = 0;
        RefreshDisplay();
    }
    if (keyDisplayActive) {
        keyDisplayActive = 0;
        RefreshDisplay();
    }
}

// ================== Delay ==================
void delay_ms(uint32_t ms) {
    uint32_t start = sysTick_ms;
    while (sysTick_ms - start < ms);
}

void delay_us(uint32_t us) {
    for (uint32_t i = 0; i < us * 9; i++) __NOP();
}

// ============================================================
//  Section 2: RS485 communication + interrupts + init + main
//  Baseline V8, only four busy checks changed
// ============================================================

// ================== RS485 Direction Control ==================
void RS485_SetTransmit(uint8_t enable) {
    if (enable) GPIO_SetBits(GPIOA, GPIO_Pin_1);    // Transmit
    else        GPIO_ResetBits(GPIOA, GPIO_Pin_1);  // Receive
}

// Only responsible for sending one byte, does not switch direction
void USART1_SendByte(uint8_t ch) {
    USART_SendData(USART1, ch);
    while (USART_GetFlagStatus(USART1, USART_FLAG_TXE) == RESET);
}

// Switch direction once for the whole string: switch to TX before sending, wait for TC then switch back to RX
void USART1_SendString(const char* str) {
    RS485_SetTransmit(1);
    delay_us(50);                           // Direction setup

    while (*str) {
        USART1_SendByte((uint8_t)*str++);
    }

    while (USART_GetFlagStatus(USART1, USART_FLAG_TC) == RESET);  // Wait for last byte to finish
    delay_us(50);                           // Direction hold
    RS485_SetTransmit(0);
}

// ================== USART1 Initialization ==================
void USART1_Init(void) {
    GPIO_InitTypeDef GPIO_InitStruct;
    USART_InitTypeDef USART_InitStruct;
    NVIC_InitTypeDef NVIC_InitStruct;

    RCC_APB2PeriphClockCmd(RCC_APB2Periph_GPIOA | RCC_APB2Periph_AFIO, ENABLE);
    RCC_APB2PeriphClockCmd(RCC_APB2Periph_GPIOB, ENABLE);
    RCC_APB2PeriphClockCmd(RCC_APB2Periph_USART1, ENABLE);

    // PA9 = TX
    GPIO_InitStruct.GPIO_Pin   = GPIO_Pin_9;
    GPIO_InitStruct.GPIO_Mode  = GPIO_Mode_AF_PP;
    GPIO_InitStruct.GPIO_Speed = GPIO_Speed_50MHz;
    GPIO_Init(GPIOA, &GPIO_InitStruct);

    // PA10 = RX
    GPIO_InitStruct.GPIO_Pin   = GPIO_Pin_10;
    GPIO_InitStruct.GPIO_Mode  = GPIO_Mode_IN_FLOATING;
    GPIO_Init(GPIOA, &GPIO_InitStruct);

    // PA1 = DE/RE
    GPIO_InitStruct.GPIO_Pin   = GPIO_Pin_1;
    GPIO_InitStruct.GPIO_Mode  = GPIO_Mode_Out_PP;
    GPIO_InitStruct.GPIO_Speed = GPIO_Speed_50MHz;
    GPIO_Init(GPIOA, &GPIO_InitStruct);
    RS485_SetTransmit(0);

    // PB5 = LED
    GPIO_InitStruct.GPIO_Pin   = GPIO_Pin_5;
    GPIO_InitStruct.GPIO_Mode  = GPIO_Mode_Out_PP;
    GPIO_InitStruct.GPIO_Speed = GPIO_Speed_50MHz;
    GPIO_Init(GPIOB, &GPIO_InitStruct);
    LED_OFF();

    USART_InitStruct.USART_BaudRate            = 9600;
    USART_InitStruct.USART_WordLength          = USART_WordLength_8b;
    USART_InitStruct.USART_StopBits            = USART_StopBits_1;
    USART_InitStruct.USART_Parity              = USART_Parity_No;
    USART_InitStruct.USART_HardwareFlowControl = USART_HardwareFlowControl_None;
    USART_InitStruct.USART_Mode                = USART_Mode_Rx | USART_Mode_Tx;
    USART_Init(USART1, &USART_InitStruct);

    USART_ITConfig(USART1, USART_IT_RXNE, ENABLE);  // Enable receive interrupt

    NVIC_InitStruct.NVIC_IRQChannel                   = USART1_IRQn;
    NVIC_InitStruct.NVIC_IRQChannelPreemptionPriority = 0;
    NVIC_InitStruct.NVIC_IRQChannelSubPriority        = 0;
    NVIC_InitStruct.NVIC_IRQChannelCmd                = ENABLE;
    NVIC_Init(&NVIC_InitStruct);

    USART_Cmd(USART1, ENABLE);
}

// ================== USART1 Interrupt ==================
void USART1_IRQHandler(void) {
    if (USART_GetITStatus(USART1, USART_IT_RXNE) != RESET) {
        uint8_t ch = USART_ReceiveData(USART1);

        if (ch == '\r') return;             // Ignore \r

        uint16_t nextHead = (rs485RxHead + 1) % RS485_RX_BUF_SIZE;
        if (nextHead != rs485RxTail) {
            rs485RxBuf[rs485RxHead] = ch;
            rs485RxHead = nextHead;
            if (ch == '\n') rs485LineReady = 1;    // End of line
        } else {
            rs485RxTail = (rs485RxTail + 1) % RS485_RX_BUF_SIZE;  // Buffer full, discard oldest
        }
    }
}

// ================== Pop a line from ring buffer ==================
// Read until '\n', return 1; also discard any trailing residue
static uint8_t RS485_PopLine(char* out, uint16_t outSize) {
    if (!rs485LineReady) return 0;

    uint16_t i = 0;
    uint8_t  got = 0;

    while (rs485RxTail != rs485RxHead && i < outSize - 1) {
        uint8_t ch = rs485RxBuf[rs485RxTail];
        rs485RxTail = (rs485RxTail + 1) % RS485_RX_BUF_SIZE;
        if (ch == '\n') { got = 1; break; }
        out[i++] = (char)ch;
    }
    out[i] = '\0';

    if (got) {
        // Discard trailing residue
        while (rs485RxTail != rs485RxHead) {
            uint8_t ch = rs485RxBuf[rs485RxTail];
            rs485RxTail = (rs485RxTail + 1) % RS485_RX_BUF_SIZE;
            if (ch == '\n') break;
        }
        rs485LineReady = 0;
        return 1;
    }
    return 0;
}

// ================== Strictly parse "N<addr> F<cnt>" ==================
static uint8_t ParseCmdLine(const char* line, int* addr, int* cnt) {
    char buf[RX_BUFFER_SIZE];
    uint16_t n = 0;

    // Skip leading whitespace
    while (*line == ' ' || *line == '\t') line++;
    while (*line && n < sizeof(buf) - 1) buf[n++] = *line++;
    buf[n] = '\0';

    // Trim trailing whitespace
    while (n > 0 && (buf[n-1] == ' ' || buf[n-1] == '\t')) {
        buf[--n] = '\0';
    }
    if (n == 0) return 0;

    int a = -1, c = -1;
    char tail = 0;

    // Strict: must be exactly "N<digits> F<digits>", no extra characters
    int r = sscanf(buf, "N%d F%d%c", &a, &c, &tail);
    if (r != 2) return 0;
    if (a < 0 || a > 99) return 0;
    if (c < 0 || c > 99) return 0;

    *addr = a;
    *cnt  = c;
    return 1;
}

// ================== Process RS485 ==================
void ProcessRS485(void) {
    char line[RX_BUFFER_SIZE];

    if (!RS485_PopLine(line, sizeof(line))) return;

    // For debugging, can be enabled:
    // USART1_SendString("RX:[");
    // USART1_SendString(line);
    // USART1_SendString("]\n");

    int cmdAddr = -1, freq = -1;
    if (!ParseCmdLine(line, &cmdAddr, &freq)) {
        return;                             // Format error, silently discard
    }

    if (cmdAddr != (int)currentAddr) return; // Address mismatch, silently ignore

    // Clear RX to prevent receiving own echo
    while (rs485RxTail != rs485RxHead) {
        rs485RxTail = (rs485RxTail + 1) % RS485_RX_BUF_SIZE;
    }
    rs485LineReady = 0;

    // Change 1: busy check uses pa3CountEnabled (motor is running)
    if (pa3CountEnabled != 0) {
        delay_ms(20);
        USART1_SendString("Busy\n");
        return;
    }

    // Motor idle, execute
    rs485TempCount = (uint8_t)freq;

    // Wait for host to switch back to receive mode before sending ACK
    delay_ms(20);
    USART1_SendString("OK\n");

    tempDisplayActive = 1;
    tempDisplayValue  = rs485TempCount;
    CH455_RefreshNum(rs485TempCount);

    Motor_Start();
    encoderMute = 1;      // Only used for echo prevention
}

// ================== SysTick ==================
void SysTick_Handler(void) {
    sysTick_ms++;
    if (pa4TriggerMute > 0) pa4TriggerMute--;
}

void SysTick_Init(void) {
    if (SysTick_Config(SystemCoreClock / 1000U)) while (1);
    NVIC_SetPriority(SysTick_IRQn, 0);
}

// ================== GPIO Initialization ==================
void GPIO_Config(void) {
    GPIO_InitTypeDef GPIO_InitStructure;
    RCC_APB2PeriphClockCmd(RCC_APB2Periph_GPIOA | RCC_APB2Periph_AFIO, ENABLE);
    RCC_APB2PeriphClockCmd(RCC_APB2Periph_GPIOB | RCC_APB2Periph_AFIO, ENABLE);

    // PA6 PA7 PA8 PA12 output (motor control)
    GPIO_InitStructure.GPIO_Pin   = GPIO_Pin_6 | GPIO_Pin_7 | GPIO_Pin_8 | GPIO_Pin_12;
    GPIO_InitStructure.GPIO_Mode  = GPIO_Mode_Out_PP;
    GPIO_InitStructure.GPIO_Speed = GPIO_Speed_50MHz;
    GPIO_Init(GPIOA, &GPIO_InitStructure);

    // PB5 LED output
    GPIO_InitStructure.GPIO_Pin   = GPIO_Pin_5;
    GPIO_InitStructure.GPIO_Mode  = GPIO_Mode_Out_PP;
    GPIO_InitStructure.GPIO_Speed = GPIO_Speed_50MHz;
    GPIO_Init(GPIOB, &GPIO_InitStructure);

    // PA3 input (encoder pulse)
    GPIO_InitStructure.GPIO_Pin  = GPIO_Pin_3;
    GPIO_InitStructure.GPIO_Mode = GPIO_Mode_IN_FLOATING;
    GPIO_Init(GPIOA, &GPIO_InitStructure);

    // PB6 input (encoder trigger)
    GPIO_InitStructure.GPIO_Pin  = GPIO_Pin_6;
    GPIO_InitStructure.GPIO_Mode = GPIO_Mode_IN_FLOATING;
    GPIO_Init(GPIOB, &GPIO_InitStructure);

    // PA2 PA4 input (buttons)
    GPIO_InitStructure.GPIO_Pin  = GPIO_Pin_2 | GPIO_Pin_4;
    GPIO_InitStructure.GPIO_Mode = GPIO_Mode_IN_FLOATING;
    GPIO_Init(GPIOA, &GPIO_InitStructure);

    // Default levels
    GPIO_SetBits(GPIOA, GPIO_Pin_6 | GPIO_Pin_7 | GPIO_Pin_8 | GPIO_Pin_12);
    GPIO_SetBits(GPIOB, GPIO_Pin_5);
}

// ================== EXTI Initialization ==================
void EXTI_Config(void) {
    EXTI_InitTypeDef EXTI_InitStructure;
    NVIC_InitTypeDef NVIC_InitStructure;

    // PB6 -> EXTI6 (encoder trigger)
    GPIO_EXTILineConfig(GPIO_PortSourceGPIOB, GPIO_PinSource6);
    EXTI_InitStructure.EXTI_Line    = EXTI_Line6;
    EXTI_InitStructure.EXTI_Mode    = EXTI_Mode_Interrupt;
    EXTI_InitStructure.EXTI_Trigger = EXTI_Trigger_Rising;
    EXTI_InitStructure.EXTI_LineCmd = ENABLE;
    EXTI_Init(&EXTI_InitStructure);

    NVIC_InitStructure.NVIC_IRQChannel                   = EXTI9_5_IRQn;
    NVIC_InitStructure.NVIC_IRQChannelPreemptionPriority = 0x01;
    NVIC_InitStructure.NVIC_IRQChannelSubPriority        = 0x01;
    NVIC_InitStructure.NVIC_IRQChannelCmd                = ENABLE;
    NVIC_Init(&NVIC_InitStructure);

    // PA3 -> EXTI3 (encoder count)
    GPIO_EXTILineConfig(GPIO_PortSourceGPIOA, GPIO_PinSource3);
    EXTI_InitStructure.EXTI_Line    = EXTI_Line3;
    EXTI_InitStructure.EXTI_Trigger = EXTI_Trigger_Rising;
    EXTI_Init(&EXTI_InitStructure);

    NVIC_InitStructure.NVIC_IRQChannel                   = EXTI3_IRQn;
    NVIC_InitStructure.NVIC_IRQChannelPreemptionPriority = 0x01;
    NVIC_InitStructure.NVIC_IRQChannelSubPriority        = 0x01;
    NVIC_InitStructure.NVIC_IRQChannelCmd                = ENABLE;
    NVIC_Init(&NVIC_InitStructure);
}

// ================== EXTI Interrupts ==================
void EXTI9_5_IRQHandler(void) {
    if (EXTI_GetITStatus(EXTI_Line6) != RESET) {
        // Change 4: encoder trigger busy check uses pa3CountEnabled
        if (pa3CountEnabled == 0) {
            rs485TempCount = 0;             // 0 means use currentCount
            Motor_Start();
            encoderMute = 1;
        }
        EXTI_ClearITPendingBit(EXTI_Line6);
    }
}

void EXTI3_IRQHandler(void) {
    if (EXTI_GetITStatus(EXTI_Line3) != RESET) {
        // Change 2: remove encoderMute == 0, keep only pa3CountEnabled
        if (pa3CountEnabled) {
            pa3TriggerCount++;
            if (pa3TriggerCount >= motorCount) {
                Motor_Stop();
                pa3TriggerCount = 0;
                pa3CountEnabled = 0;
            }
        }
        EXTI_ClearITPendingBit(EXTI_Line3);
    }
}

// ================== main ==================
int main(void) {
    SystemInit();
    SysTick_Init();
    GPIO_Config();

    I2C_Software_Init();
    CH455_GPIO_Init();
    delay_ms(150);

    // CH455 initialization: 8 segments, display on, brightness
    CH455_SetSysParam(0x71);
    delay_ms(10);
    CH455_SetSysParam(0x71);
    delay_ms(10);

    // Read EEPROM address
    uint8_t saved = EEPROM_ReadByte(EEPROM_DATA_ADDR);
    if (saved != 0xFF && saved <= 99) {
        currentAddr = saved;
    } else {
        currentAddr = 0;
        EEPROM_WriteByte(EEPROM_DATA_ADDR, currentAddr);
    }

    // Read EEPROM count
    uint8_t savedCount = EEPROM_ReadByte(EEPROM_COUNT_ADDR);
    if (savedCount != 0xFF && savedCount <= 99) {
        currentCount = savedCount;
    } else {
        currentCount = 1;
        EEPROM_WriteByte(EEPROM_COUNT_ADDR, currentCount);
    }

    delay_ms(10);
    CH455_RefreshNum(currentAddr);
    delay_ms(5);

    Key_GPIO_Init();
    USART1_Init();
    EXTI_Config();

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

    // Print address on power-up
    {
        char buf[16];
        snprintf(buf, sizeof(buf), "Addr:%d\n", currentAddr);
        USART1_SendString(buf);
    }

    // Default levels
    GPIO_SetBits(GPIOA, GPIO_Pin_6 | GPIO_Pin_7);
    GPIO_SetBits(GPIOB, GPIO_Pin_5);
    GPIO_SetBits(GPIOA, GPIO_Pin_12);
    GPIO_SetBits(GPIOA, GPIO_Pin_8);

    // Main loop
    while (1) {
        KeyScan();
        delay_ms(5);
        ProcessRS485();

        if (flashCount > 0) {
            uint8_t times = flashCount;
            flashCount = 0;
            led_flash_times(times, 400, times);
        }

        // encoderMute is only used for echo prevention, cleared after 120ms
        // Not involved in busy check
        if (encoderMute == 1) {
            delay_ms(BLANKING_TIME);
            encoderMute = 0;
        }
    }
}