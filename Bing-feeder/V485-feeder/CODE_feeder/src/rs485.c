// Derived from MicroSMT/Bing-feeder V485 firmware. Local HAL/PlatformIO port.
// Original authors retain credit; see README.md and CHANGELOG.md.
//
// Owns USART1, transceiver direction and a bounded complete-line receive ring.
// Damaged/overlong/overflowed input is discarded through LF; older committed
// commands stay queued. Main never parses a fragment of an invalid line.

#include "rs485.h"
#include "board.h"
#include "config.h"
#include <stddef.h>

static UART_HandleTypeDef rs485Uart;
// Single producer (UART ISR), single consumer (main). Head publishes complete
// lines only. The producer can roll back a damaged partial line without changing
// committed bytes or the consumer's tail. Capacity is RS485_RX_BUF_SIZE-1 bytes.
static volatile uint8_t rs485RxBuf[RS485_RX_BUF_SIZE];
static volatile uint16_t rs485RxHead;
static volatile uint16_t rs485RxTail;
static uint16_t rs485WriteHead;
static uint8_t rs485LineLength;
static uint8_t rs485DiscardLine;

// A high DE//RE control drives the bus; low releases it for receive.
static void RS485_SetTransmit(uint8_t enable) {
    HAL_GPIO_WritePin(RS485_DIR_PORT, RS485_DIR_PIN,
                      enable ? GPIO_PIN_SET : GPIO_PIN_RESET);
}

// Wait for data-register space before writing one byte. Direction is managed
// by the string sender; this byte wait does not wait for the final stop bit.
static void USART1_SendByte(uint8_t ch) {
    while (__HAL_UART_GET_FLAG(&rs485Uart, UART_FLAG_TXE) == RESET);
    rs485Uart.Instance->DR = ch;
}

// Hold TX direction for the complete string. TC means the final stop bit has
// left the UART; TXE alone would release the bus too early. No timeout is used.
void RS485_SendString(const char* str) {
    RS485_SetTransmit(1);
    delay_us(RS485_DIRECTION_SETTLE_US);                           // Direction setup

    while (*str) {
        USART1_SendByte((uint8_t)*str++);
    }

    while (__HAL_UART_GET_FLAG(&rs485Uart, UART_FLAG_TC) == RESET);  // Wait for last byte to finish
    delay_us(RS485_DIRECTION_SETTLE_US);                           // Direction hold
    RS485_SetTransmit(0);
}

// Configure 9600/default 8N1 with RXNE interrupts; reception bypasses HAL
// callbacks because this module owns the byte ring and USART1 IRQ directly.
void RS485_Init(void) {
    __HAL_RCC_USART1_CLK_ENABLE();
    Board_ConfigurePin(RS485_PORT, RS485_TX_PIN, GPIO_MODE_AF_PP);
    Board_ConfigurePin(RS485_PORT, RS485_RX_PIN, GPIO_MODE_INPUT);
    Board_ConfigurePin(RS485_DIR_PORT, RS485_DIR_PIN, GPIO_MODE_OUTPUT_PP);
    RS485_SetTransmit(0);

    rs485Uart.Instance = USART1;
    rs485Uart.Init.BaudRate = RS485_BAUD;
    rs485Uart.Init.WordLength = UART_WORDLENGTH_8B;
    rs485Uart.Init.StopBits = UART_STOPBITS_1;
    rs485Uart.Init.Parity = UART_PARITY_NONE;
    rs485Uart.Init.Mode = UART_MODE_TX_RX;
    rs485Uart.Init.HwFlowCtl = UART_HWCONTROL_NONE;
    rs485Uart.Init.OverSampling = UART_OVERSAMPLING_16;
    if (HAL_UART_Init(&rs485Uart) != HAL_OK) Board_ErrorHandler();

    // Keep the vendor's byte ring buffer rather than adding HAL RX callbacks.
    __HAL_UART_CLEAR_OREFLAG(&rs485Uart);
    __HAL_UART_ENABLE_IT(&rs485Uart, UART_IT_RXNE);
    HAL_NVIC_SetPriority(USART1_IRQn, 0, 0);
    HAL_NVIC_EnableIRQ(USART1_IRQn);
}

// Throw away only the producer's uncommitted line, then wait for a clean LF.
// Already queued complete commands are left intact, even when the ring is full.
static void RS485_RejectLine(void) {
    rs485WriteHead = rs485RxHead;
    rs485LineLength = 0;
    rs485DiscardLine = 1;
}

// ISR-only byte collector. Reserve space for LF as part of each queued frame.
// No head publication happens until the whole bounded line has been validated.
static void RS485_ReceiveByte(uint8_t ch) {
    if (rs485DiscardLine) {
        if (ch == '\n') rs485DiscardLine = 0;
        return;
    }
    if (ch == '\0' || (ch != '\n' && rs485LineLength >= RX_BUFFER_SIZE - 1U)) {
        RS485_RejectLine();
        return;
    }
    uint16_t next = (rs485WriteHead + 1U) % RS485_RX_BUF_SIZE;
    if (next == rs485RxTail) {
        RS485_RejectLine();
        // A clean LF itself is a usable boundary, even if no room remains.
        if (ch == '\n') rs485DiscardLine = 0;
        return;
    }
    rs485RxBuf[rs485WriteHead] = ch;
    rs485WriteHead = next;
    if (ch == '\n') {
        __DMB();  // Publish payload writes before exposing the new queue head.
        rs485RxHead = rs485WriteHead;
        rs485LineLength = 0;
    } else {
        rs485LineLength++;
    }
}

// SR then DR clears F1 receive/error flags. An errored byte invalidates its
// entire current line, not just that byte; it cannot silently change F19 to F1.
void USART1_IRQHandler(void) {
    uint32_t status = rs485Uart.Instance->SR;
    if ((status & (USART_SR_RXNE | USART_SR_ORE | USART_SR_FE | USART_SR_NE | USART_SR_PE)) != 0) {
        uint8_t ch = (uint8_t)rs485Uart.Instance->DR;
        if ((status & USART_SR_RXNE) == 0 ||
            (status & (USART_SR_ORE | USART_SR_FE | USART_SR_NE | USART_SR_PE)) != 0) {
            RS485_RejectLine();
            return;
        }
        RS485_ReceiveByte(ch);
    }
}

// Main-only consumer. Consume exactly one LF-terminated line, keeping all later
// commands queued. Even a too-small output buffer discards the ENTIRE line.
uint8_t RS485_ReadLine(char* out, uint16_t outSize) {
    if (outSize < 2U) return 0;
    uint16_t length = 0;
    uint8_t invalid = 0;
    while (rs485RxTail != rs485RxHead) {
        uint8_t ch = rs485RxBuf[rs485RxTail];
        rs485RxTail = (rs485RxTail + 1U) % RS485_RX_BUF_SIZE;
        if (ch == '\n') {
            out[length] = '\0';
            return !invalid;
        }
        if (length < outSize - 1U) out[length++] = (char)ch;
        else invalid = 1;
    }
    return 0;
}

// Small bounded decimal reader: reject signs/non-digits and values above 99
// before they can overflow an integer. Leading zeroes remain harmless/valid.
static uint8_t ParseValue(const char** cursor, int* value) {
    const char* text = *cursor;
    if (*text < '0' || *text > '9') return 0;
    int parsed = 0;
    do {
        parsed = parsed * 10 + (*text++ - '0');
        if (parsed > VALUE_MAX) return 0;
    } while (*text >= '0' && *text <= '9');
    *cursor = text;
    *value = parsed;
    return 1;
}

// Accept N<digits> whitespace F<digits>, with optional surrounding spaces/tabs
// and a final CR from CRLF. Never accept embedded controls or trailing garbage.
uint8_t RS485_ParseFeedCommand(const char* line, int* addr, int* cnt) {
    while (*line == ' ' || *line == '\t') line++;
    int address, count;
    if (*line++ != 'N' || !ParseValue(&line, &address)) return 0;
    if (*line != ' ' && *line != '\t') return 0;
    while (*line == ' ' || *line == '\t') line++;
    if (*line++ != 'F' || !ParseValue(&line, &count)) return 0;
    while (*line == ' ' || *line == '\t') line++;
    if (*line == '\r') line++;
    if (*line != '\0' || address < ADDRESS_MIN) return 0;
    *addr = address;
    *cnt = count;
    return 1;
}

// May also run on the normal boot path before the UART was initialised.
void RS485_DeInit(void) {
    HAL_NVIC_DisableIRQ(USART1_IRQn);
    if (rs485Uart.Instance != NULL) HAL_UART_DeInit(&rs485Uart);
    RS485_SetTransmit(0);
}
