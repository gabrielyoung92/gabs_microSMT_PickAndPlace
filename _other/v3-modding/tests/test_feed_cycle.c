#include "feed_cycle.h"

#include <assert.h>
#include <stdio.h>

static void completion_requires_indexes(void)
{
    feed_cycle_t cycle;
    feed_cycle_init(&cycle);
    assert(!feed_cycle_motor_requested(&cycle));
    feed_cycle_index(&cycle, 9); /* Stray event while idle. */
    assert(cycle.completed_indexes == 0);
    assert(feed_cycle_start(&cycle, 2, 100, 10) == FEED_START_ACCEPTED);
    feed_cycle_poll(&cycle, 30);
    assert(cycle.state == FEED_BUSY);
    assert(feed_cycle_motor_requested(&cycle));
    feed_cycle_index(&cycle, 40);
    assert(cycle.state == FEED_BUSY && cycle.completed_indexes == 1);
    feed_cycle_index(&cycle, 50);
    assert(cycle.state == FEED_DONE && cycle.completed_indexes == 2);
    assert(cycle.error == FEED_ERROR_NONE);
    assert(!feed_cycle_motor_requested(&cycle));
    feed_cycle_index(&cycle, 51);
    feed_cycle_poll(&cycle, 500);
    feed_cycle_abort(&cycle);
    assert(cycle.state == FEED_DONE && cycle.completed_indexes == 2);
    assert(!feed_cycle_clear_fault(&cycle));
    assert(feed_cycle_start(&cycle, 1, 100, 600) == FEED_START_ACCEPTED);
    assert(cycle.completed_indexes == 0);
}

static void busy_request_cannot_extend_deadline(void)
{
    feed_cycle_t cycle;
    feed_cycle_init(&cycle);
    assert(feed_cycle_start(&cycle, 2, 100, 1000) == FEED_START_ACCEPTED);
    feed_cycle_index(&cycle, 1010);
    assert(feed_cycle_start(&cycle, 1, 5000, 1050) == FEED_START_BUSY);
    assert(cycle.started_ms == 1000 && cycle.timeout_ms == 100);
    assert(cycle.target_indexes == 2 && cycle.completed_indexes == 1);
    feed_cycle_poll(&cycle, 1099);
    assert(cycle.state == FEED_BUSY);
    assert(feed_cycle_start(&cycle, 1, 5000, 1100) == FEED_START_FAULT);
    assert(cycle.error == FEED_ERROR_TIMEOUT);
    assert(!feed_cycle_motor_requested(&cycle));
}

static void timeout_latches_and_beats_late_sensor(void)
{
    feed_cycle_t cycle;
    feed_cycle_init(&cycle);
    assert(feed_cycle_start(&cycle, 1, 100, 0) == FEED_START_ACCEPTED);
    feed_cycle_index(&cycle, 100);
    assert(cycle.state == FEED_FAULT && cycle.error == FEED_ERROR_TIMEOUT);
    assert(cycle.completed_indexes == 0);
    feed_cycle_index(&cycle, 101);
    assert(feed_cycle_start(&cycle, 1, 100, 102) == FEED_START_FAULT);
    assert(!feed_cycle_motor_requested(&cycle));
    assert(feed_cycle_clear_fault(&cycle));
    assert(cycle.state == FEED_IDLE && cycle.error == FEED_ERROR_NONE);
    assert(feed_cycle_start(&cycle, 1, 100, 103) == FEED_START_ACCEPTED);
    feed_cycle_index(&cycle, 202);
    assert(cycle.state == FEED_DONE); /* One ms before deadline. */
}

static void no_sensor_still_stops(void)
{
    feed_cycle_t cycle;
    feed_cycle_init(&cycle);
    assert(feed_cycle_start(&cycle, 1, 25, 50) == FEED_START_ACCEPTED);
    feed_cycle_poll(&cycle, 75);
    assert(cycle.state == FEED_FAULT && cycle.error == FEED_ERROR_TIMEOUT);
    assert(!feed_cycle_motor_requested(&cycle));
}

static void abort_is_not_completion(void)
{
    feed_cycle_t cycle;
    feed_cycle_init(&cycle);
    feed_cycle_abort(&cycle);
    assert(cycle.state == FEED_IDLE);
    assert(feed_cycle_start(&cycle, 2, 100, 0) == FEED_START_ACCEPTED);
    feed_cycle_index(&cycle, 20);
    feed_cycle_abort(&cycle);
    assert(cycle.state == FEED_FAULT && cycle.error == FEED_ERROR_ABORTED);
    assert(cycle.completed_indexes == 1);
    assert(!feed_cycle_motor_requested(&cycle));
    feed_cycle_index(&cycle, 30);
    feed_cycle_poll(&cycle, 200);
    assert(cycle.error == FEED_ERROR_ABORTED);
    assert(feed_cycle_start(&cycle, 1, 100, 201) == FEED_START_FAULT);
    assert(feed_cycle_clear_fault(&cycle));
    assert(!feed_cycle_clear_fault(&cycle));
}

static void invalid_requests_do_not_start(void)
{
    feed_cycle_t cycle;
    feed_cycle_init(&cycle);
    assert(feed_cycle_start(&cycle, 0, 100, 0) == FEED_START_INVALID);
    assert(feed_cycle_start(&cycle, 1, 0, 0) == FEED_START_INVALID);
    assert(feed_cycle_start(&cycle, 1, UINT32_MAX, 0) == FEED_START_INVALID);
    assert(feed_cycle_start(&cycle, 1, (uint32_t)INT32_MAX + 1, 0) == FEED_START_INVALID);
    assert(cycle.state == FEED_IDLE && !feed_cycle_motor_requested(&cycle));
    assert(feed_cycle_start(&cycle, 1, INT32_MAX, 0) == FEED_START_ACCEPTED);
    feed_cycle_poll(&cycle, (uint32_t)INT32_MAX);
    assert(cycle.error == FEED_ERROR_TIMEOUT);
}

static void clock_wrap_is_supported(void)
{
    feed_cycle_t cycle;
    feed_cycle_init(&cycle);
    assert(feed_cycle_start(&cycle, 1, 20, UINT32_MAX - 9) == FEED_START_ACCEPTED);
    feed_cycle_poll(&cycle, 9); /* 19 ms elapsed. */
    assert(cycle.state == FEED_BUSY);
    feed_cycle_poll(&cycle, 10);
    assert(cycle.state == FEED_FAULT && cycle.error == FEED_ERROR_TIMEOUT);
    assert(feed_cycle_clear_fault(&cycle));
    assert(feed_cycle_start(&cycle, 1, 20, UINT32_MAX - 9) == FEED_START_ACCEPTED);
    feed_cycle_index(&cycle, 5);
    assert(cycle.state == FEED_DONE);
}

static void maximum_index_count_does_not_overflow(void)
{
    feed_cycle_t cycle;
    feed_cycle_init(&cycle);
    assert(feed_cycle_start(&cycle, UINT16_MAX, 100000, 0) == FEED_START_ACCEPTED);
    for (uint32_t i = 1; i <= UINT16_MAX; ++i) {
        feed_cycle_index(&cycle, i);
    }
    assert(cycle.state == FEED_DONE && cycle.completed_indexes == UINT16_MAX);
    feed_cycle_index(&cycle, 70000);
    assert(cycle.completed_indexes == UINT16_MAX);
}

int main(void)
{
    completion_requires_indexes();
    busy_request_cannot_extend_deadline();
    timeout_latches_and_beats_late_sensor();
    no_sensor_still_stops();
    abort_is_not_completion();
    invalid_requests_do_not_start();
    clock_wrap_is_supported();
    maximum_index_count_does_not_overflow();
    puts("Feed-cycle tests passed (8 behavioral scenarios)");
    return 0;
}
