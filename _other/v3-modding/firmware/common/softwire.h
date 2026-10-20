#ifndef MICROSMT_SOFTWIRE_H
#define MICROSMT_SOFTWIRE_H
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#define SOFTWIRE_TICK_US 26u
#define SOFTWIRE_QUEUE 64u
/* One tick owner. Main-context access must exclude the tick interrupt. */
typedef struct {
    uint8_t rx[SOFTWIRE_QUEUE], tx[SOFTWIRE_QUEUE];
    uint8_t rx_read,rx_write,tx_length,tx_index,tx_bit,tx_phase;
    uint8_t rx_state,rx_wait,rx_bit,rx_value,idle_high;
    bool transmitting,drive_low;
    uint32_t framing_errors,overruns,collisions,timing_errors;
} softwire_t;
void softwire_init(softwire_t *wire);
/* true means sink LOW. false means release/high impedance, NEVER drive HIGH. */
bool softwire_tick(softwire_t *wire, bool line_high);
bool softwire_send(softwire_t *wire, const uint8_t *data, size_t length);
bool softwire_read(softwire_t *wire, uint8_t *byte);
bool softwire_busy(const softwire_t *wire);
void softwire_cancel(softwire_t *wire);
void softwire_timing_fault(softwire_t *wire);
#endif
