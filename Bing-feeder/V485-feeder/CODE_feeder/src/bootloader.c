// Gab's local RS485 loader for MicroSMT-derived V485 firmware.
// Only this entry point owns flash erase/program; drivers are shared with app.
#include "boot.h"
#include "board.h"
#include "config.h"
#include "display.h"
#include "eeprom.h"
#include "rs485.h"
#include <string.h>

static BootRecord pending;
static uint32_t nextOffset;
static uint8_t sessionActive;

void SysTick_Handler(void) { HAL_IncTick(); }

// No C stack access is allowed after replacing MSP. Startup Reset_Handler
// initialises application data/BSS, with VTOR already pointing to its vectors.
__attribute__((naked, noreturn))
static void JumpToReset(uint32_t stack __attribute__((unused)),
                        uint32_t reset __attribute__((unused))) {
    __asm volatile("msr msp, r0\n"
                   "movs r2, #0\n"
                   "msr control, r2\n"
                   "isb\n"
                   "cpsie i\n"
                   "bx r1\n");
}

// Restore a quiet interrupt/clock state without resetting the GPIO peripheral:
// both motor channels must remain driven STOP throughout this handoff.
__attribute__((noreturn))
static void JumpToApplication(void) {
    RS485_DeInit();
    if (HAL_RCC_DeInit() != HAL_OK) Board_ErrorHandler();
    __disable_irq();
    SysTick->CTRL = 0;
    SysTick->LOAD = 0;
    SysTick->VAL = 0;
    for (uint8_t bank = 0; bank < 8; bank++) {
        NVIC->ICER[bank] = 0xFFFFFFFFU;
        NVIC->ICPR[bank] = 0xFFFFFFFFU;
    }
    SCB->ICSR = SCB_ICSR_PENDSTCLR_Msk | SCB_ICSR_PENDSVCLR_Msk;
    SCB->VTOR = BOOT_APP_START;
    __DSB(); __ISB();
    const uint32_t* vectors = (const uint32_t*)BOOT_APP_START;
    JumpToReset(vectors[0], vectors[1]);
}

// Three fixed-width fields, with exact separators and no trailing characters.
static uint8_t ParseManifest(const char* text, BootRecord* record) {
    return Boot_ParseHex(&text, &record->variant) && *text++ == ' ' &&
           Boot_ParseHex(&text, &record->size) && *text++ == ' ' &&
           Boot_ParseHex(&text, &record->imageCrc) && *text == 0;
}

// Never mass erase. Bounds are checked before reaching this function and each
// programmed address is also constrained by the declared application size.
static uint8_t EraseApplication(uint32_t size) {
    if (HAL_FLASH_Unlock() != HAL_OK) return 0;
    __HAL_FLASH_CLEAR_FLAG(FLASH_FLAG_EOP | FLASH_FLAG_PGERR | FLASH_FLAG_WRPERR);
    FLASH_EraseInitTypeDef erase = {0};
    erase.TypeErase = FLASH_TYPEERASE_PAGES;
    erase.PageAddress = BOOT_APP_START;
    erase.NbPages = (size + BOOT_PAGE_SIZE - 1U) / BOOT_PAGE_SIZE;
    uint32_t error = 0;
    HAL_StatusTypeDef result = HAL_FLASHEx_Erase(&erase, &error);
    HAL_FLASH_Lock();
    return result == HAL_OK;
}

static int HexDigit(char ch) {
    if (ch >= '0' && ch <= '9') return ch - '0';
    if (ch >= 'A' && ch <= 'F') return ch - 'A' + 10;
    if (ch >= 'a' && ch <= 'f') return ch - 'a' + 10;
    return -1;
}

// Stop-and-wait chunks, at most 32 bytes. Retry a completed chunk by comparing
// flash, never programming it twice. Only the last chunk may have odd length.
static uint8_t WriteChunk(const char* text) {
    uint32_t offset;
    if (!sessionActive || !Boot_ParseHex(&text, &offset) || *text++ != ' ') return 0;
    size_t chars = strlen(text);
    if (!chars || chars > BOOT_CHUNK_SIZE * 2U || (chars & 1U)) return 0;
    uint32_t size = chars / 2U;
    if ((offset & 1U) || offset > pending.size || size > pending.size - offset ||
        ((size & 1U) && offset + size != pending.size)) return 0;
    uint8_t data[BOOT_CHUNK_SIZE];
    for (uint32_t i = 0; i < size; i++) {
        int high = HexDigit(text[i * 2]), low = HexDigit(text[i * 2 + 1]);
        if (high < 0 || low < 0) return 0;
        data[i] = (uint8_t)((high << 4) | low);
    }
    const uint8_t* flash = (const uint8_t*)(BOOT_APP_START + offset);
    if (offset < nextOffset)
        return offset + size <= nextOffset && !memcmp(flash, data, size);
    if (offset != nextOffset) return 0;
    if (HAL_FLASH_Unlock() != HAL_OK) { sessionActive = 0; return 0; }
    __HAL_FLASH_CLEAR_FLAG(FLASH_FLAG_EOP | FLASH_FLAG_PGERR | FLASH_FLAG_WRPERR);
    uint8_t ok = 1;
    for (uint32_t i = 0; i < size; i += 2) {
        uint16_t halfword = data[i] | ((i + 1U < size ? data[i + 1U] : 0xFFU) << 8);
        if (HAL_FLASH_Program(FLASH_TYPEPROGRAM_HALFWORD, BOOT_APP_START + offset + i,
                              halfword) != HAL_OK) { ok = 0; break; }
    }
    HAL_FLASH_Lock();
    if (!ok || memcmp(flash, data, size)) { sessionActive = 0; return 0; }
    nextOffset += size;
    CH455_RefreshNum((uint16_t)((nextOffset * 99U) / pending.size));
    return 1;
}

// Return 1 only after END has committed a verified image. The caller jumps
// after sending DONE; a lost DONE can be confirmed using the application's INFO.
static uint8_t ProcessPacket(uint8_t id, char* line) {
    char* command = Boot_DecodePacket(line, id);
    if (!command) return 0;
    if (!strcmp(command, "HELLO")) {
        uint32_t values[] = {FEEDER_VARIANT_ID, BOOT_APP_START, BOOT_APP_MAX};
        Boot_Reply(id, "READY", values, 3);
    } else if (!strncmp(command, "BEGIN ", 6)) {
        BootRecord record = {0};
        if (!ParseManifest(command + 6, &record) || record.variant != FEEDER_VARIANT_ID ||
            record.size < BOOT_TAG_OFFSET + 16U || record.size > BOOT_APP_MAX) {
            Boot_Reply(id, "ERROR IMAGE", NULL, 0);
            return 0;
        }
        // Identical BEGIN retries retain a live session's progress. A reboot
        // loses RAM progress, so restart from zero after invalidating metadata.
        if (!sessionActive || record.variant != pending.variant ||
            record.size != pending.size || record.imageCrc != pending.imageCrc) {
            sessionActive = 0;
            if (!Boot_WriteState(BOOT_WRITING)) {
                Boot_Reply(id, "ERROR EEPROM", NULL, 0);
                return 0;
            }
            if (!EraseApplication(record.size)) {
                Boot_Reply(id, "ERROR FLASH", NULL, 0);
                return 0;
            }
            pending = record;
            nextOffset = 0;
            sessionActive = 1;
            CH455_RefreshNum(0);
        }
        Boot_Reply(id, "OK", &nextOffset, 1);
    } else if (!strncmp(command, "DATA ", 5)) {
        if (WriteChunk(command + 5)) Boot_Reply(id, "OK", &nextOffset, 1);
        else Boot_Reply(id, "ERROR DATA", NULL, 0);
    } else if (!strncmp(command, "END ", 4)) {
        const char* text = command + 4;
        uint32_t crc;
        if (!sessionActive || !Boot_ParseHex(&text, &crc) || *text ||
            crc != pending.imageCrc || nextOffset != pending.size || !Boot_ImageValid(&pending)) {
            Boot_Reply(id, "ERROR VERIFY", NULL, 0);
        } else if (!Boot_SaveRecord(&pending)) {
            Boot_Reply(id, "ERROR EEPROM", NULL, 0);
        } else {
            Boot_Reply(id, "DONE", &pending.imageCrc, 1);
            return 1;
        }
    } else Boot_Reply(id, "ERROR COMMAND", NULL, 0);
    return 0;
}

int main(void) {
    Board_Init();  // Boot build always stops BOTH motors, including wide variant.
    EEPROM_Init();
    BootRecord record;
    uint8_t state;
    if (Boot_ReadRecord(&record, &state) && state == BOOT_VALID && Boot_ImageValid(&record))
        JumpToApplication(); // No listen delay or display startup on normal boot.

    // Requested update, empty/invalid image or interrupted upload: wait here
    // indefinitely. No motor EXTI handlers are enabled in this image.
    Display_Init();
    LED_ON();
    RS485_Init();
    // ID cannot be edited in the loader. Cache one checked EEPROM value for
    // the whole session rather than reading the I2C bus for every UART poll.
    uint8_t id;
    while (!Boot_ReadId(&id)) {
        CH455_SetDisplay(1, DISPLAY_ERROR_SEGMENTS);
        CH455_SetDisplay(3, DISPLAY_ERROR_SEGMENTS);
        delay_ms(100); // Failed access must never manufacture a destination ID.
    }
    CH455_RefreshNum(id);
    while (1) {
        char line[RX_BUFFER_SIZE];
        if (RS485_ReadLine(line, sizeof(line)) && ProcessPacket(id, line))
            JumpToApplication();
    }
}
