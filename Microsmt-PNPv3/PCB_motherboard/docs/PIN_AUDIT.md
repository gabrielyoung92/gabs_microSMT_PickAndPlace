# Motherboard pin audit and expansion reservations

This inventory applies to the supplied LPC1769 motherboard CAM/PDF reference.
It does not establish the delivered board revision or runtime firmware configuration.
The complete 100-pin inventory is in [mcu-pins.csv](mcu-pins.csv) and
[mcu-pins.json](mcu-pins.json). Positions use the recovered KiCad board coordinates.

## Pin inventory

| Purpose | MCU GPIO / function | LQFP100 pin | Supplied PCB evidence | Decision |
| --- | --- | --- | --- | --- |
| Vacuum sensor, head 1 | P0.23 / AD0.0 | 9 | Source NET_19 has only IC1 pin 9; isolated pad | Reserve for analog vacuum input |
| Vacuum sensor, head 2 | P0.24 / AD0.1 | 8 | Source NET_18 has only IC1 pin 8; isolated pad | Reserve for analog vacuum input |
| Future serial TX | P0.2 / TXD0 | 98 | TX_0 routes to S6 pin 3 | Reserved; do not use for feeder bus |
| Future serial RX | P0.3 / RXD0 | 99 | RX_0 routes to S6 pin 4 | Reserved; do not use for feeder bus |
| Feeder bus, preferred candidate | P2.11 / EINT1 / I2STX_CLK | 52 | Source NET_30 has only IC1 pin 52; isolated pad | Candidate GPIO connection; firmware resource audit still required |
| Feeder bus, alternate | P0.18 / MOSI0 / DCD1 | 60 | Source NET_31 has only IC1 pin 60; isolated pad | Candidate; consumes an SSP0/SPI0 signal |
| Feeder bus, alternate | P0.17 / MISO0 / CTS1 | 61 | Source NET_32 has only IC1 pin 61; isolated pad | Candidate; consumes an SSP0/SPI0 signal |
| Vacuum sensor, pump/manifold | P1.30 / AD0.4 | 21 | Source NET_25 has only IC1 pin 21; isolated pad | Reserve for analog vacuum input |
| Additional analog input | P1.31 / AD0.5 | 20 | Source NET_24 has only IC1 pin 20; isolated pad | Leave available |

The source contains 26 GPIOs without another component terminal on their net.
Four of these have UART RX/TX alternate functions: P0.15, P0.16, P0.25 and P0.26.
They are conservatively reserved as future serial options, leaving 22 non-UART
candidates. Reserving the three vacuum inputs leaves 19 of those for other uses.
The already-routed dedicated UART0 header remains intact.

The unused non-UART candidates are listed automatically in the CSV. They include
pins associated with Ethernet, I2C, trace, ADC and timers, so "unused in this PCB"
does not mean "free in a running Smoothieware configuration".

## GPIO connection notes

P2.11 is a useful first candidate because it is unused in both the supplied
schematic and terminal net map, supports an edge-sensitive GPIO interrupt,
and does not consume an ADC channel or a UART TX/RX pin. All LPC176x GPIOs
support open-drain mode; Port 0 and Port 2 support GPIO edge interrupts.
These capabilities are from the [NXP LPC1769 family datasheet, sections 2 and 7](https://www.nxp.com/docs/en/data-sheet/LPC1769_68_67_66_65_64_63.pdf).
The timer and interrupt allocations of the exact PnP firmware have not been audited.
An EINT1 alternate function is not the same thing as a free timer or interrupt handler.

None of the preferred bus or analog candidates is routed to a spare source connector.
A wire to an MCU lead/pad, a reviewed adapter, or a later PCB revision is necessary.
The LPC package has fine-pitch leads; board inspection should establish a practical
attachment point before choosing the physical modification. The KiCad reference
keeps the original copper and does not add a bus interface or sensor circuitry.

This machine uses the separate USB–RS485 feeder host. These GPIO candidates
are not connections to that bus. V3 busbars carry individual trigger nets.

## Sensor wiring for this machine

Use two sensors on a separate ESP32-C3 USB board. No pump sensor or motherboard
ADC connection is planned. Wiring, divider values, conversion and bench checks
are in the [sensor guide](../../docs/vacuum-sensors.md).

The table above records available motherboard pins, not installed wiring.
P0.25/AD0.2 and P0.26/AD0.3 also lack other component terminals but are reserved
for TXD3/RXD3. ADC6/7 share UART0 pins. VDDA/VREFP are on 3.3V;
VSSA/VREFN are on GND.

Before using any spare pin, confirm the fitted board/MCU, continuity, pin mux
and firmware timer/interrupt ownership. No bus interface or sensor circuit has
been added to this KiCad reference.
