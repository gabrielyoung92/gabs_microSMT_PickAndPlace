# Feeder firmware

`feed_cycle.c` implements the part of feeder behavior that can be specified and
tested before hardware arrives: a bounded operation completes only after the
requested number of qualified index events. Missing events cause a latched
timeout fault. Aborting a cycle stops its motor request and records an abort.

The implementation is new project code. The downloaded vendor source stays in
the `../../Bing-feeder/` and `../../Microsmt-PNPv3/` directories. It informed the requirement to preserve optical completion, but its
blocking interrupt handlers and board setup have not been copied here.

## Integration contract

- Initialize the object once before use. All pointers must be valid.
- Run the API in one execution context; it is not ISR/thread safe. A future
  adapter should queue sensor events and process them without losing timestamps.
- The application must enforce power/arming conditions before starting a cycle.
- `FEED_START_ACCEPTED` means an operation has begun. Only `FEED_DONE` means the
  requested index events were received. The bus will need separate acceptance
  and completion responses.
- A request while busy cannot replace or extend the active feed. A request after
  its deadline observes the fault. Fault clearing is an explicit application
  operation after recovery; it must not be automatic when another FEED arrives.
- Supply a monotonically advancing uint32 millisecond clock. Poll regularly so
  a missing sensor event cannot leave a cycle running. Unsigned subtraction
  handles clock rollover; pauses of an entire 32-bit clock period are unsupported.
- `feed_cycle_index()` takes a qualified physical indexing event. It does not
  sample the optical input. The adapter must establish sensor polarity, edge
  sequence, debounce, start-of-cycle qualification and pitch conversion from
  measured hardware. One event must not be assumed to mean 2 mm or 4 mm yet.
- Apply motor stop intent promptly on DONE/FAULT, including after polling. The
  board adapter owns driver truth tables, brake/coast choice, hardware watchdog
  and output initialization. The core does not provide electrical safety alone.
- The peel motor needs its own measured sequencing; it is not implemented here.
- Command IDs, duplicate detection, retry/session handling and persistent identity
  belong to the future transport/application. A new start after DONE currently
  begins a new operation; **do not connect an automatically retrying command
  transport without adding replay protection**.

Timeouts in the tests are synthetic inputs, not recommended feeder settings.
Internal enums are not a stable published motion packet format. The new `node.c`
and `stm32/main.c` provide a CMSIS-only diagnostic bench image, linked with startup
and linker support from PlatformIO. FEED is unconditionally inhibited; the core
is not connected to motors or raw sensor events. OpenPnP integration, persistent
configuration and a project bootloader are still absent. See the
[PlatformIO guide](../README.md) and [bench protocol](../../docs/feeder-bus-bench.md).

## Checks

From the project root:

```sh
make test
make arm-check
```

The host tests exercise completion, missing sensor events, attempts to restart a
busy operation, timeout boundaries, abort/recovery, invalid inputs, maximum
counter size and timer rollover. The ARM check compiles an object only; it does
not confirm the identity of the feeder MCU or establish firmware acceptance.
