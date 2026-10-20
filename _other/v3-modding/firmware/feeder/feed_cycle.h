#ifndef GABS_MICROSMT_FEED_CYCLE_H
#define GABS_MICROSMT_FEED_CYCLE_H

#include <stdbool.h>
#include <stdint.h>

/* Internal enums, not wire-protocol values. Call from one execution context. */
typedef enum {
    FEED_IDLE,
    FEED_BUSY,
    FEED_DONE,
    FEED_FAULT
} feed_state_t;

typedef enum {
    FEED_ERROR_NONE,
    FEED_ERROR_TIMEOUT,
    FEED_ERROR_ABORTED
} feed_error_t;

typedef enum {
    FEED_START_ACCEPTED,
    FEED_START_BUSY,
    FEED_START_FAULT,
    FEED_START_INVALID
} feed_start_result_t;

typedef struct {
    feed_state_t state;
    feed_error_t error;
    uint32_t started_ms;
    uint32_t timeout_ms;
    uint16_t target_indexes;
    uint16_t completed_indexes;
} feed_cycle_t;

void feed_cycle_init(feed_cycle_t *cycle);

/* timeout_ms must be 1..INT32_MAX; indexes must be nonzero.
 * A new request may replace DONE, but never BUSY or an uncleared FAULT.
 * Transport/session replay protection belongs above this cycle core.
 */
feed_start_result_t feed_cycle_start(feed_cycle_t *cycle, uint16_t indexes,
                                     uint32_t timeout_ms, uint32_t now_ms);

/* Call regularly, including when the sensor produces no events. */
void feed_cycle_poll(feed_cycle_t *cycle, uint32_t now_ms);

/* One mechanically qualified index completion, not a raw GPIO edge.
 * The board adapter must reject bounce/stale edges and apply the stop request
 * promptly. Timestamp comes from the same monotonic clock as poll/start.
 */
void feed_cycle_index(feed_cycle_t *cycle, uint32_t now_ms);

/* Aborting a running cycle leaves a latched fault, never DONE. */
void feed_cycle_abort(feed_cycle_t *cycle);

/* Call only after the higher-level recovery procedure permits another feed. */
bool feed_cycle_clear_fault(feed_cycle_t *cycle);

/* Abstract intent only: no GPIO polarity, brake mode or peel motor implied. */
bool feed_cycle_motor_requested(const feed_cycle_t *cycle);

#endif
