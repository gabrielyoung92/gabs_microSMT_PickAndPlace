#include "feed_cycle.h"

void feed_cycle_init(feed_cycle_t *cycle)
{
    *cycle = (feed_cycle_t){.state = FEED_IDLE, .error = FEED_ERROR_NONE};
}

void feed_cycle_poll(feed_cycle_t *cycle, uint32_t now_ms)
{
    if (cycle->state == FEED_BUSY &&
        (uint32_t)(now_ms - cycle->started_ms) >= cycle->timeout_ms) {
        cycle->state = FEED_FAULT;
        cycle->error = FEED_ERROR_TIMEOUT;
    }
}

feed_start_result_t feed_cycle_start(feed_cycle_t *cycle, uint16_t indexes,
                                     uint32_t timeout_ms, uint32_t now_ms)
{
    feed_cycle_poll(cycle, now_ms);
    if (cycle->state == FEED_BUSY) {
        return FEED_START_BUSY;
    }
    if (cycle->state == FEED_FAULT) {
        return FEED_START_FAULT;
    }
    if (indexes == 0 || timeout_ms == 0 || timeout_ms > INT32_MAX) {
        return FEED_START_INVALID;
    }
    *cycle = (feed_cycle_t){
        .state = FEED_BUSY,
        .error = FEED_ERROR_NONE,
        .started_ms = now_ms,
        .timeout_ms = timeout_ms,
        .target_indexes = indexes,
        .completed_indexes = 0
    };
    return FEED_START_ACCEPTED;
}

void feed_cycle_index(feed_cycle_t *cycle, uint32_t now_ms)
{
    /* Timeout wins at the deadline, even if an index event arrives then. */
    feed_cycle_poll(cycle, now_ms);
    if (cycle->state != FEED_BUSY) {
        return;
    }
    ++cycle->completed_indexes;
    if (cycle->completed_indexes == cycle->target_indexes) {
        cycle->state = FEED_DONE;
    }
}

void feed_cycle_abort(feed_cycle_t *cycle)
{
    if (cycle->state == FEED_BUSY) {
        cycle->state = FEED_FAULT;
        cycle->error = FEED_ERROR_ABORTED;
    }
}

bool feed_cycle_clear_fault(feed_cycle_t *cycle)
{
    if (cycle->state != FEED_FAULT) {
        return false;
    }
    feed_cycle_init(cycle);
    return true;
}

bool feed_cycle_motor_requested(const feed_cycle_t *cycle)
{
    return cycle->state == FEED_BUSY;
}
