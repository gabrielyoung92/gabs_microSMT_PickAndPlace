# Feeder EEPROM and saved data

The feeder has a **24C02 EEPROM: 2 kilobits, or 256 bytes**, addressed from
`0x00` to `0xFF`. It is separate from the STM32 program flash and keeps its
contents when power is removed. The current firmware uses **28 bytes**;
**228 bytes are unused**.

**There are no text fields or reel quantities in feeder EEPROM.** You cannot
currently store a part number or name there: the supported text capacity is
**zero characters**. The dashboard stores reel information on the computer and
assigns the selected part in OpenPnP.

## What the feeder saves

Every setting below is an unsigned 8-bit integer: one byte, with no text
encoding or terminating character.

| Offset | Bytes | Field | Meaning and allowed values |
| --- | ---: | --- | --- |
| `0x00` | 1 | Bus ID | `0` = unassigned; `1–99` = operating ID. Unassigned units cannot run either motor. |
| `0x01` | 1 | Default advance count | `1–99` optical sensor events per ordinary feed. This is **not** remaining quantity. |
| `0x02` | 1 | Tape width | `8`, `12`, `16` or `24`, in mm. |
| `0x03` | 1 | Width check | Bitwise complement of the width byte; both bytes must XOR to `0xFF`. |
| `0x04` | 1 | Motor/switch options | Three flags, described below; valid combined values `0–7`. |
| `0x05` | 1 | Options check | Bitwise complement of the options byte. |
| `0x06` | 1 | Options format marker | `0xA1` identifies a committed options record. |
| `0x07–0x1E` | 24 | Unused | No current field or text allocation. |
| `0x1F` | 1 | Bootloader state | `0xA5` = valid application, `0x5A` = update requested, `0x00` = writing. |
| `0x20–0x33` | 20 | Application record | Five 32-bit unsigned integers, detailed below. |
| `0x34–0xFF` | 204 | Unused | No current field or text allocation. |

Motor/switch options at `0x04`:

| Bit | Mask | Clear (`0`) | Set (`1`) |
| --- | --- | --- | --- |
| 0 | `0x01` | Normal feed direction | Reversed feed direction |
| 1 | `0x02` | Normal peel direction | Reversed peel direction |
| 2 | `0x04` | NC tension switch | NO tension switch |

Part spacing is converted to sensor events:

| Feeder width | Distance per event | Saved count range | Supported spacing |
| --- | --- | --- | --- |
| 8 mm | 2 mm | 1–99 | 2–198 mm, in 2 mm steps |
| 12 / 16 / 24 mm | 4 mm | 1–99 | 4–396 mm, in 4 mm steps |

For example, 4 mm part spacing means count **2** on an 8 mm feeder and count
**1** on a wider feeder. The saved count is shared by the local feed button and
commands that request the default advance. It is not a separate record per part.

## Bootloader record

These are binary numbers in little-endian order, four bytes each. They describe
the application image; the firmware binary itself lives in STM32 flash.

| Offset | Field | Value |
| --- | --- | --- |
| `0x20–0x23` | Record magic | `0x31423556` |
| `0x24–0x27` | Image variant | `3` for the universal application |
| `0x28–0x2B` | Image size | Application length in bytes; application flash capacity is 57,344 bytes |
| `0x2C–0x2F` | Image CRC32 | Checksum of the application bytes |
| `0x30–0x33` | Record CRC32 | Checksum of the preceding 16 record bytes |

The physical feeder width is the setting at `0x02`, not the image variant.
The bootloader updates its state and application record during firmware uploads.

## Reel text, parts and quantity on the computer

These are the current dashboard limits, **not EEPROM allocations**:

| Field | Limit | Stored in |
| --- | --- | --- |
| Reel label | 128 characters | Host stock SQLite database |
| Loaded quantity | Integer `0–1,000,000,000` | Host stock database |
| Low-stock warning threshold | Integer `0–1,000,000,000` | Host stock database |
| New part ID | 128 characters, non-empty | OpenPnP configuration |
| Part name | 256 characters | OpenPnP configuration |
| New package ID | 128 characters, non-empty | OpenPnP configuration |
| Package description | 1,024 characters | OpenPnP configuration |

The host keeps the selected part association and stock against the MCU's fixed
UID. Saving a part also updates the matching powered feeder in OpenPnP.
The UID is 12 bytes provided by the STM32, not a field in the external EEPROM.
Reel label/part edits preserve consumption unless **Set quantity** is checked.
Saving part spacing also saves and verifies the feeder default advance count.
Remaining stock is estimated from the loaded quantity and observed movement;
it is not written into the feeder for every advance.

Text limits count characters rather than reserving that many EEPROM bytes.
Use ordinary letters, digits and punctuation; Unicode symbols can count
differently between the browser and Python/Java validation. These limits apply
to this web interface, not every possible OpenPnP editor or import format.

## What survives an update or reset

- Normal application updates preserve valid bus ID, width, default count and
  motor/switch settings. They replace program flash and update boot metadata.
- Clear error does not write EEPROM or reboot. Watchdog resets do not erase
  saved settings. Boot token, fault state, input-test state and movement counter
  are runtime data, not EEPROM fields.
- Blank ID becomes `0`. An invalid count is replaced with the default: **2**
  for a valid 8 mm width, otherwise **1**. Width requires a valid checked pair.
- Completely blank motor options use reversed feed / normal peel / NC for
  8 mm, and normal feed / normal peel / NC for wider units. A partial or invalid
  options record blocks operation until corrected.
- The driver checks write acknowledgements, waits 5 ms and verifies each byte
  by reading it back. Telemetry and normal advances do not write EEPROM.

Unused space is available for a future firmware change; it does not currently
make part text or quantity portable with the feeder. No EEPROM layout change
is included in firmware 0.1.3.

Source: [field definitions](Bing-feeder/V485-feeder/CODE_feeder/src/config.h),
[settings handling](Bing-feeder/V485-feeder/CODE_feeder/src/feeder.c),
[EEPROM driver](Bing-feeder/V485-feeder/CODE_feeder/src/eeprom.c),
[boot record](Bing-feeder/V485-feeder/CODE_feeder/src/boot.h),
[host stock](Bing-feeder/V485-feeder/USB_host/host_service.py) and
[OpenPnP field validation](Bing-feeder/V485-feeder/USB_host/OpenPnP-Web.py).
