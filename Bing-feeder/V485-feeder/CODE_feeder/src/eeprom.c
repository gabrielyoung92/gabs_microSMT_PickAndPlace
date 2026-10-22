// Derived from MicroSMT/Bing-feeder V485 firmware. Local HAL/PlatformIO port.
// Original authors retain credit; see README.md and CHANGELOG.md.
//
// Bit-banged 24C02 bus, used from main context for settings. Pulling an
// open-drain line high releases it; the PCB pull-ups provide the high level.

#include "eeprom.h"
#include "board.h"
#include "config.h"

#define SCL_HIGH()  HAL_GPIO_WritePin(I2C_PORT, I2C_SCL_PIN, GPIO_PIN_SET)
#define SCL_LOW()   HAL_GPIO_WritePin(I2C_PORT, I2C_SCL_PIN, GPIO_PIN_RESET)
#define SDA_HIGH()  HAL_GPIO_WritePin(I2C_PORT, I2C_SDA_PIN, GPIO_PIN_SET)
#define SDA_LOW()   HAL_GPIO_WritePin(I2C_PORT, I2C_SDA_PIN, GPIO_PIN_RESET)
#define SDA_READ()  HAL_GPIO_ReadPin(I2C_PORT, I2C_SDA_PIN)

// Start with both lines released. Board_Init must provide GPIO clocks and
// the cycle-counter delays before this driver runs.
void EEPROM_Init(void) {
    Board_ConfigurePin(I2C_PORT, I2C_SCL_PIN | I2C_SDA_PIN, GPIO_MODE_OUTPUT_OD);
    SCL_HIGH(); SDA_HIGH();
    delay_us(5);
}

// Create START (or repeated START): SDA falls while SCL is high.
static void I2C_Start(void) {
    SDA_HIGH(); SCL_HIGH(); delay_us(5);
    SDA_LOW();  delay_us(5);
    SCL_LOW();  delay_us(5);
}

// Create STOP: SDA rises while SCL is high, returning the bus to idle.
static void I2C_Stop(void) {
    SDA_LOW();  SCL_HIGH(); delay_us(5);
    SDA_HIGH(); delay_us(5);
}

// Send MSB first, then release SDA for the slave ACK clock. Return 0 for ACK
// or 1 for NACK; the caller decides whether to stop the transaction.
static uint8_t I2C_WriteByte(uint8_t byte) {
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

// Read one byte, then drive ACK when ack=0 or release SDA for NACK when ack=1.
// The single-byte public read ends with NACK before issuing STOP.
static uint8_t I2C_ReadByte(uint8_t ack) {
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

// Refuse a stuck bus rather than interpreting a permanently LOW SDA as ACKs
// and a false EEPROM value of zero (which could manufacture destination ID 0).
static uint8_t I2C_BusReady(void) {
    SDA_HIGH(); SCL_HIGH(); delay_us(5);
    return HAL_GPIO_ReadPin(I2C_PORT, I2C_SCL_PIN) == GPIO_PIN_SET &&
           SDA_READ() == GPIO_PIN_SET;
}

// Check the final data ACK as well as device/offset selection. Readback after
// the maximum 24C02 write cycle prevents metadata from claiming an unwritten byte.
uint8_t EEPROM_WriteByte(uint8_t address, uint8_t value) {
    if (!I2C_BusReady()) return 0;
    I2C_Start();
    uint8_t failed = I2C_WriteByte(EEPROM_ADDR_W) ||
                     I2C_WriteByte(address) || I2C_WriteByte(value);
    I2C_Stop();
    if (failed) return 0;
    delay_ms(5);
    uint8_t actual;
    return EEPROM_ReadChecked(address, &actual) && actual == value;
}

// Selection failure is explicit; leave the output untouched on failure.
uint8_t EEPROM_ReadChecked(uint8_t address, uint8_t* value) {
    if (!I2C_BusReady()) return 0;
    I2C_Start();
    if (I2C_WriteByte(EEPROM_ADDR_W) || I2C_WriteByte(address)) {
        I2C_Stop();
        return 0;
    }
    I2C_Start();
    if (I2C_WriteByte(EEPROM_ADDR_R)) { I2C_Stop(); return 0; }
    *value = I2C_ReadByte(1);
    I2C_Stop();
    return 1;
}
