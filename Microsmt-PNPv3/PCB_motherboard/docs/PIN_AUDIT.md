# Motherboard pin audit and expansion reservations

This inventory applies to the supplied LPC1769 motherboard CAM/PDF reference.
It does not establish the delivered board revision or runtime firmware configuration.
The complete 100-pin inventory is in [mcu-pins.csv](mcu-pins.csv) and
[mcu-pins.json](mcu-pins.json). Positions use the recovered KiCad board coordinates.

## Reservations and proposed connections

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

## Feeder bus connection

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

This pin investigation considered a custom open-drain feeder bus; no such
interface is implemented in the recovered motherboard. The original V3 busbars
carry individual trigger nets. An addressed shared bus would require a reviewed
electrical interface and deliberate feeder-bank adaptation.

## Analog vacuum inputs

**Current decision:** use two sensors on a separate ESP32-C3 USB board,
with no pump sensor or motherboard modification. See the
[current sensor plan](../../docs/vacuum-sensors.md). The three-channel
proposal below is retained as a historical motherboard expansion reference.


Selected sensor: **CFSensor XGZP6847A100KPGN33**. Use three independent channels:
one per head on P0.23/AD0.0 and P0.24/AD0.1, plus a pump/common-manifold sensor
on P1.30/AD0.4. P1.31/AD0.5 remains an additional analog candidate.

The [manufacturer datasheet V2.8, 2026-09-04, pages 2–5](https://cfsensor.com/wp-content/uploads/2026/09/XGZP6847A-Pressure-Sensor-V2.8.pdf)
lists the exact part as a **−100 to 0 kPa gauge** sensor with **3.3 V supply**
(3.0–3.6 V operating range) and **0.2–2.7 V analog output**. At nominal supply,
0.2 V represents −100 kPa and 2.7 V represents atmospheric pressure (0 kPa gauge).
The nominal conversion is `pressure_kPa = (output_V - 2.7) / 0.025`.
Stronger vacuum produces a lower voltage. Calibrate atmospheric zero and span
against a reference before choosing pickup thresholds; the output is ratiometric.

Sensor pins, using the manufacturer's package numbering: 1 = NC, 2/4 = VDD,
3/6 = GND, 5 = OUT. Leave pin 1 unconnected and verify the package view before wiring.
Use a regulated 3.3 V rail and common ground, with local decoupling and reviewed
ADC filtering/protection. The nominal output fits the board's 3.3 V ADC reference;
electrical tolerance, wiring faults and disconnected-sensor behaviour still need review.
The source's VDDA/VREFP are on 3.3V and VSSA/VREFN are on GND.

Planned pneumatic placement: tee each head sensor into its nozzle line downstream
of the corresponding vacuum valve, close to the head. Tee the third sensor into
the common vacuum supply at the pump inlet, upstream of the head valves. It measures
supply vacuum rather than pump flow. Compare readings with valve states: a leaking
head can also reduce common-line vacuum, so low pump-line vacuum alone does not
prove a faulty pump. Keep the sensors' atmospheric vents open and keep contamination
out of their pressure ports. The manufacturer specifies air/non-corrosive gas.

P0.25/AD0.2 and P0.26/AD0.3 are also unused in the source, but are left reserved
because they are alternate TXD3/RXD3 pins. ADC channels 6/7 share the UART0 pins,
so they are not available under the RX/TX reservation.

## Acceptance still required

1. Confirm delivered PCB revision, fitted MCU and continuity against this reference.
2. Establish source/bootloader recovery and inspect the actual Smoothieware PnP
   configuration, pin mux and timer/interrupt ownership.
3. Verify the XGZP6847A100KPGN33 interface circuits and test three calibrated channels.
4. Develop the feeder module with bounded, nonblocking work and observable faults.
5. Verify the bus waveform and sensor readings under demanding simultaneous motion.

No board modification, firmware upload, powered measurement or machine operation
was performed for this recovery.
