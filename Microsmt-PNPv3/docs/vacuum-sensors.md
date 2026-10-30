# N1/N2 vacuum sensors

Plan: two **CFSensor XGZP6847A100KPGN33** sensors on a separate USB-powered
ESP32-C3, one per nozzle. OpenPnP runs on the Debian machine computer.
No motherboard modification or pump sensor is planned. Five sensors are on hand:
two for installation and three spares. The C3 board, firmware and OpenPnP read
protocol still need selecting and testing.

## Sensor and wiring

[Datasheet PDF](datasheets/XGZP6847A-Pressure-Sensor-V2.8.pdf), pages 2–5;
page 3 gives pin orientation. [Manufacturer copy](https://cfsensor.com/wp-content/uploads/2026/09/XGZP6847A-Pressure-Sensor-V2.8.pdf).

| Property | Value |
| --- | --- |
| Interface | Analogue voltage |
| Pressure | −100 to 0 kPa gauge |
| Supply | 3.3 V nominal; 3.0–3.6 V |
| Output | 0.2 V at −100 kPa; 2.7 V at atmosphere |
| Typical current / response | 1.8 mA / 5 ms T90 |
| Medium | Air or non-corrosive gas |
| Pin 1 | NC; leave open |
| Pins 2 / 4 | VDD |
| Pins 3 / 6 | GND |
| Pin 5 | OUT |

Power from regulated **3V3**, not USB 5 V or machine 24 V. Use common ground
and local decoupling; start with 100 nF plus a small bulk capacitor per sensor.
Check the package view, regulator capacity and supply noise before connecting.

Proposed ADC inputs are **GPIO0/ADC1_CH0 for N1** and **GPIO1/ADC1_CH1 for N2**,
subject to the actual board schematic. GPIO1/GPIO3 are alternatives. ADC1 uses
GPIO0–4; GPIO5 is ADC2. Leave GPIO18/19 free for native USB and avoid conflicting
use of strapping pins GPIO2/8/9. See [pin mapping](https://documentation.espressif.com/esp32-c3_datasheet_en.html)
and [board guidance](https://docs.espressif.com/projects/esp-hardware-design-guidelines/en/latest/esp32c3/schematic-checklist.html).

The sensor's 2.7 V output exceeds the C3's approximately 2.5 V ADC measurement
range at maximum attenuation. Use this proposed divider on **each** channel:

```text
sensor OUT ---- 4.7 kΩ ----+---- ADC1 input
                          |
                        10 kΩ
                          |
                         GND

ADC input ---- 100 nF ---- GND
```

Use 1% resistors. Divider ratio: 0.6803; nominal maximum ADC input: 1.837 V.
RC time constant: about 0.32 ms. Check loading, settling and pump/motor noise.
Use calibrated ADC millivolts, modest averaging and retain raw readings.

```text
sensor_voltage = ADC_voltage * 1.47
pressure_kPa = (sensor_voltage - 2.7) / 0.025
```

Stronger vacuum lowers voltage. Calibrate atmospheric zero and span on each
installed channel; nominal values and ADC resolution do not establish accuracy.

## Plumbing and OpenPnP

Tee each sensor into its nozzle line **after that nozzle's valve**, near the head.
Keep branches short, atmospheric vents open and pressure ports free of debris
or liquid. Confirm valve routing: incorrect N1 tubing was found during testing.

Measure an open nozzle, a sealed nozzle, representative picked parts and release.
Set thresholds and settling time per nozzle. A closed valve can trap vacuum,
so pressure alone cannot prove a part was released or securely picked.

Firmware must report independent N1/N2 values, units, sample age and faults.
USB loss or stalled sampling must not count as a successful pickup. Before use,
verify physical nozzle association, voltage/divider ratio, reference pressure,
response time and noise with motors, valves and pump running.
