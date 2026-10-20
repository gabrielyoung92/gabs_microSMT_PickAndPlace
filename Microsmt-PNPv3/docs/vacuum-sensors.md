# N1/N2 vacuum sensors with ESP32-C3

## Selected arrangement

Use two CFSensor **XGZP6847A100KPGN33** sensors, one per nozzle, with a separate
USB-powered ESP32-C3 board. The board supplies regulated 3.3 V, measures both
analog outputs, and reports readings over USB serial to the Raspberry Pi running
OpenPnP. Retain the stock motion board without PCB modifications. Five sensors
are available; two are planned for installation and three remain spare.

This replaces the earlier three-channel motherboard ADC proposal. The reserved
motherboard pins remain historical expansion candidates, not current wiring.
The exact C3 development board, firmware and OpenPnP read protocol are not yet
selected or validated. No sensor installation or ESP32 flashing has occurred.

## Sensor specification

[Local manufacturer datasheet PDF](datasheets/XGZP6847A-Pressure-Sensor-V2.8.pdf):
page 3 shows package orientation and pin numbering.

Manufacturer evidence: [CFSensor datasheet V2.8, 2026-09-04, pages 2–5](https://cfsensor.com/wp-content/uploads/2026/09/XGZP6847A-Pressure-Sensor-V2.8.pdf).

| Property | Selected part |
| --- | --- |
| Interface | Analog voltage, not I2C |
| Pressure | −100 to 0 kPa gauge |
| Supply | 3.3 V nominal; 3.0–3.6 V |
| Output at nominal supply | 0.2–2.7 V; stronger vacuum lowers voltage |
| Nominal endpoints | −100 kPa: 0.2 V; atmospheric: 2.7 V |
| Current | 1.8 mA typical per sensor |
| Response | 5 ms typical T90 |
| Medium | Air / non-corrosive gas |
| Pin 1 | NC; leave unconnected |
| Pins 2 and 4 | VDD |
| Pins 3 and 6 | GND |
| Pin 5 | OUT |

Verify the manufacturer's package drawing and pin orientation before assembly.
Nominal conversion: `pressure_kPa = (sensor_output_V - 2.7) / 0.025`.
The output is ratiometric; calibrate the installed channels rather than assuming
nominal supply and conversion are exact.

## C3 inputs and power

Proposed assignment: **N1 = GPIO0 / ADC1_CH0**, **N2 = GPIO1 / ADC1_CH1**,
subject to checking the actual development-board schematic. GPIO1 and GPIO3
are an alternative if GPIO0 is occupied. ADC1 is on GPIO0–4; GPIO5 is ADC2.
GPIO0 is not a C3 boot strapping pin; GPIO2, GPIO8 and GPIO9 are strapping pins.
Keep GPIO18/19 available if the board uses native USB.
See [Espressif pin mapping](https://documentation.espressif.com/esp32-c3_datasheet_en.html)
and [hardware guidance](https://docs.espressif.com/projects/esp-hardware-design-guidelines/en/latest/esp32c3/schematic-checklist.html).

Power sensors from the board's regulated **3V3**, not USB 5 V or machine 24 V.
Connect sensor and C3 grounds. Add local supply decoupling at each sensor;
100 nF plus a small bulk capacitor is a proposed starting arrangement.
Verify regulator headroom and supply noise on the actual board.

The C3's specified ADC measurement range at maximum attenuation is approximately
0–2.5 V. A sensor can output 2.7 V at atmospheric pressure, so use a divider on
**each** output rather than directly connecting it to the ADC.

Proposed bench circuit, requiring electrical verification:

```text
sensor OUT ---- 4.7 kΩ ----+---- C3 ADC1 input
                          |
                        10 kΩ
                          |
                         GND
                          
ADC input ---- 100 nF ---- GND
```

Use 1% resistors. Divider ratio is 10/14.7 ≈ 0.6803; nominal maximum ADC voltage
is 1.837 V. Recover sensor voltage as `ADC_voltage * 1.47` before conversion.
The capacitor and divider add approximately 0.32 ms RC time constant. Check
sensor output loading, ADC settling and noise before finalizing the circuit.
Use calibrated ADC millivolts, modest averaging, and retain raw diagnostics.
Do not equate 12-bit resolution with pressure accuracy.

## Pneumatic placement and purpose

Tee each sensor into its own nozzle line **downstream of that nozzle's valve**,
preferably near the head. Keep branches short, atmospheric vents unobstructed,
and prevent debris or liquid entering the sensor. Check the actual valve ports
and routing before reconnecting: incorrect tubing was found during N1 testing.

N1/N2 readings measure conditions where pickup happens. Characterize each
channel with an open nozzle, a sealed nozzle and representative picked parts.
Use nozzle-specific thresholds and settling time. A pressure reading alone does
not prove a correctly oriented or mechanically secure part. Verify release too;
a closed valve may trap vacuum, depending on valve plumbing.

A pump-manifold sensor is **optional diagnostics**. It could help distinguish
weak common supply from a local leak or obstruction, and monitor supply buildup.
It cannot confirm whether either nozzle holds a part. Both nozzle readings
falling can suggest a common supply problem but do not uniquely identify it.
The current scope therefore omits the pump sensor; add one later only if these
diagnostics become useful.

## Integration and acceptance

Firmware should expose independent N1/N2 readings with units, sample age and
explicit channel faults. Disconnection, stalled sampling or USB loss must not
look like a successful pickup. Select a bounded request/reply protocol suitable
for an OpenPnP read actuator; implementation and configuration are pending.

Before using readings for placement, verify pin mapping, rail voltage, divider
ratio, atmospheric zero, span against a reference, physical nozzle association,
response time, release behavior, and noise during pump/valve/motor activity.
