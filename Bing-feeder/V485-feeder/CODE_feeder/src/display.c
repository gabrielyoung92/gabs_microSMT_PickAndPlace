// Derived from MicroSMT/Bing-feeder V485 firmware. Local HAL/PlatformIO port.
// Original authors retain credit; see README.md and CHANGELOG.md.
//
// CH455 two-wire display driver using the vendor byte/segment sequence.
// All callers run in main context. Feed/SysTick ISRs only mark a display
// refresh request, so display transactions cannot interrupt each other.
// The vendor display acknowledgement level is still not checked.

#include "display.h"
#include "board.h"
#include "config.h"

static const uint8_t seg_table[] = {
    0x7E, 0x0C, 0xB6, 0x9E, 0xCC, 0xDA, 0xFA, 0x0E, 0xFE, 0xDE
};

// Take control of SDA for command/data bits, using the vendor push-pull mode.
static void CH455_SDA_Out(void) {
    Board_ConfigurePin(CH455_SDA_PORT, CH455_SDA_PIN, GPIO_MODE_OUTPUT_PP);
}

// Release SDA during the display's acknowledgement clock.
static void CH455_SDA_In(void) {
    Board_ConfigurePin(CH455_SDA_PORT, CH455_SDA_PIN, GPIO_MODE_INPUT);
}

// Prepare software clock/data outputs. Board GPIO clocks must already be on.
static void CH455_GPIO_Init(void) {
    Board_ConfigurePin(CH455_SCL_PORT, CH455_SCL_PIN, GPIO_MODE_OUTPUT_PP);
    Board_ConfigurePin(CH455_SDA_PORT, CH455_SDA_PIN, GPIO_MODE_OUTPUT_PP);
    HAL_GPIO_WritePin(CH455_SCL_PORT, CH455_SCL_PIN, GPIO_PIN_SET);
    HAL_GPIO_WritePin(CH455_SDA_PORT, CH455_SDA_PIN, GPIO_PIN_SET);
}

// Drive the display transaction's START edge before sending a command byte.
static void CH455_Start(void) {
    CH455_SDA_Out();
    HAL_GPIO_WritePin(CH455_SCL_PORT, CH455_SCL_PIN, GPIO_PIN_SET);   delay_us(5);
    HAL_GPIO_WritePin(CH455_SDA_PORT, CH455_SDA_PIN, GPIO_PIN_RESET); delay_us(5);
    HAL_GPIO_WritePin(CH455_SCL_PORT, CH455_SCL_PIN, GPIO_PIN_RESET);
}

// Finish the transaction and leave both bus lines high.
static void CH455_Stop(void) {
    CH455_SDA_Out();
    HAL_GPIO_WritePin(CH455_SCL_PORT, CH455_SCL_PIN, GPIO_PIN_RESET);
    HAL_GPIO_WritePin(CH455_SDA_PORT, CH455_SDA_PIN, GPIO_PIN_RESET); delay_us(5);
    HAL_GPIO_WritePin(CH455_SCL_PORT, CH455_SCL_PIN, GPIO_PIN_SET);   delay_us(5);
    HAL_GPIO_WritePin(CH455_SDA_PORT, CH455_SDA_PIN, GPIO_PIN_SET);   delay_us(5);
}

// Send MSB first and provide the display's ACK clock. The vendor sequence
// releases SDA here but does not read/validate the acknowledgement level.
static void CH455_WriteByte(uint8_t dat) {
    uint8_t i;
    CH455_SDA_Out();
    for (i = 0; i < 8; i++) {
        HAL_GPIO_WritePin(CH455_SCL_PORT, CH455_SCL_PIN, GPIO_PIN_RESET); delay_us(2);
        if (dat & 0x80) HAL_GPIO_WritePin(CH455_SDA_PORT, CH455_SDA_PIN, GPIO_PIN_SET);
        else            HAL_GPIO_WritePin(CH455_SDA_PORT, CH455_SDA_PIN, GPIO_PIN_RESET);
        dat <<= 1; delay_us(2);
        HAL_GPIO_WritePin(CH455_SCL_PORT, CH455_SCL_PIN, GPIO_PIN_SET); delay_us(2);
    }
    HAL_GPIO_WritePin(CH455_SCL_PORT, CH455_SCL_PIN, GPIO_PIN_RESET);
    CH455_SDA_In();             // Release SDA for ACK; level is not sampled
    delay_us(3);
    HAL_GPIO_WritePin(CH455_SCL_PORT, CH455_SCL_PIN, GPIO_PIN_SET);
    delay_us(3);
}

// Send one command/address byte and one payload byte in a single transaction.
static void CH455_WriteCmd(uint8_t byte1, uint8_t byte2) {
    CH455_Start();
    CH455_WriteByte(byte1);
    CH455_WriteByte(byte2);
    CH455_Stop();
}

// Write the display configuration byte; startup retains the vendor value 0x71.
static void CH455_SetSysParam(uint8_t param) {
    CH455_WriteCmd(CH455_SYS_CMD, param);
}

// Translate logical digit index 0..3 into a CH455 digit-write command.
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

// Render 0..99 using the board's non-adjacent digit positions: tens at 1, units
// at 3. Caller limits the number; an out-of-range tens value exceeds seg_table.
void CH455_RefreshNum(uint16_t num) {
    uint8_t lo = num % 10;
    uint8_t hi = num / 10;
    CH455_SetDisplay(1, seg_table[hi]);
    CH455_SetDisplay(3, seg_table[lo]);
}

// Allow the display to settle, then repeat its setup write as the vendor does.
// Requires Board_Init so GPIO and micro/millisecond waits are usable.
void Display_Init(void) {
    CH455_GPIO_Init();
    delay_ms(150);
    // Retain the vendor's two CH455 configuration writes and settling times.
    CH455_SetSysParam(0x71);
    delay_ms(10);
    CH455_SetSysParam(0x71);
    delay_ms(10);
}
