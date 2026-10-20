# OpenPnP motion and output commands

Reviewed initial Pi configuration. These are the configured commands for the
stock five-axis LPC1769 Smoothieware PnP controller. Runtime configuration lives
in OpenPnP's machine.xml; preserved SD files are not modified.

## Operating profile

| Axis | Speed | Acceleration |
| --- | --- | --- |
| X / Y | 200 mm/s | 1000 mm/s² |
| Z | 50 mm/s | 500 mm/s² |
| A / B | 360°/s | 2000°/s² |

These are selected starting operating limits, not demonstrated maximums.
Earlier measurements verified X/Y travel at 100 mm/s, Z at 5 mm/s and small
nozzle rotations at 10°/s. Faster operation, combined moves and repeatability
still need measurement. After the command review, the owner reported successful
OpenPnP homing and that motion speed feels good so far; homing remains slow but
acceptable. That observation does not establish maximum performance.
Vendor controller limits are considerably higher
and are not evidence of usable mechanical speed. OpenPnP axis limits and the
controller connect/home profiles now agree; no slow test caps are restored.

## Homing behavior

Automatic home on enable remains enabled. Stock firmware searches X/Y together
and then Z; three-axis simultaneous searching is not supported by this
Cartesian homing implementation. Stock fast search rates are X50/Y40/Z50 mm/s,
with 25 mm/s slow rates. The shared XY move need not reach both independent
fast-rate values. Increasing ordinary velocity limits beyond these values does
not increase configured homing rates. A configured homing_order or home_z_first
can alter the sequence. The current preserved SD configuration sets neither.

The Z gate is central and stock Z searches negative. Start with heads level
or N2 below N1. Software limits do not constrain an unhomed homing search.
There is no G0 Z0 before homing. G92 A0 B0 establishes an arbitrary current
rotation reference; neither nozzle has a proven rotational home sensor.

## Command blocks

Semicolon comments appear in OpenPnP command editors and are stripped before
transmission. Response regex fields cannot contain G-code comments.

### POSITION_REPORT_REGEX

```text
^.*X:(?<X>-?\d+\.\d+)\s+Y:(?<Y>-?\d+\.\d+)\s+Z:(?<Z>-?\d+\.\d+)\s+A:(?<A>-?\d+\.\d+)\s+B:(?<B>-?\d+\.\d+).*
```

### COMMAND_CONFIRM_REGEX

```text
^ok\b.*
```

### CONNECT_COMMAND

```gcode
; Establish machine units and operating limits without moving axes
G21 ; Use millimetres
G90 ; Absolute positioning on all motion axes
G54 ; Use the first work coordinate system
M203 X200 Y200 Z50 ; Cartesian velocity limits, mm/s
M203.1 X200 Y200 Z50 A360 B360 ; Motor limits: XYZ mm/s, A/B degrees/s
M204 X1000 Y1000 Z500 A2000 B2000 ; Acceleration: XYZ mm/s^2, A/B degrees/s^2
M801 ; Close N1 vacuum valve
M803 ; Close N2 vacuum valve
M809 ; Stop vacuum pump
M805 ; Bottom camera light off
M807 ; Top camera light off
```

### DISABLE_COMMAND

```gcode
M400 ; Finish queued movement before normal machine shutdown
M801 ; Close N1 vacuum valve
M803 ; Close N2 vacuum valve
M809 ; Stop vacuum pump
M805 ; Bottom camera light off
M807 ; Top camera light off
M84 ; Disable stepper drivers last
```

### HOME_COMMAND

```gcode
; Z centre-gate prerequisite: heads level or N2 below N1
; Apply the same operating profile even after external/manual commands
G21 ; Millimetres
G90 ; Absolute positioning
G54 ; First work coordinate system
G92.1 ; Clear temporary coordinate offsets without moving
M203 X200 Y200 Z50 ; Cartesian velocity limits, mm/s
M203.1 X200 Y200 Z50 A360 B360 ; Motor limits: XYZ mm/s, A/B degrees/s
M204 X1000 Y1000 Z500 A2000 B2000 ; Acceleration: XYZ mm/s^2, A/B degrees/s^2
; Firmware search speeds: X50, Y40, Z50 mm/s; second pass is 25 mm/s
G28 ; Home configured XYZ: X/Y search together, then Z, with stock ordering
M400 ; Wait until all queued movement has finished
G92 A0 B0 ; Set current nozzle angles to zero; this does not rotate or physically home them
```

### SET_GLOBAL_OFFSETS_COMMAND

```gcode
G92 {X:X%.4f} {Y:Y%.4f} {Z:Z%.4f} {A:A%.4f} {B:B%.4f} ; Assign coordinates here without movement
```

### GET_POSITION_COMMAND

```gcode
M114 ; Report current X/Y/Z/A/B coordinates
```

### MOVE_TO_COMMAND

```gcode
; OpenPnP substitutes only the axes being moved
; XYZ positions are mm; A/B positions are degrees; F is per minute
; Firmware plans acceleration using the per-axis M204 limits
G1 {X:X%.4f} {Y:Y%.4f} {Z:Z%.4f} {A:A%.4f} {B:B%.4f} {FeedRate:F%.2f} ; Coordinated move
```

### MOVE_TO_COMPLETE_COMMAND

```gcode
M400 ; Block until queued physical movement completes
```

### ACTUATE_BOOLEAN_COMMAND — VacuumPump

```gcode
{True:M808}{False:M809} ; Vacuum pump: true=on, false=off
```

### ACTUATE_BOOLEAN_COMMAND — N1 VAC_SW

```gcode
{True:M800}{False:M801} ; N1 vacuum valve: true=on, false=off
```

### ACTUATE_BOOLEAN_COMMAND — N2 VAC_SW

```gcode
{True:M802}{False:M803} ; N2 vacuum valve: true=on, false=off
```

### ACTUATE_BOOLEAN_COMMAND — Top Camera Light

```gcode
{True:M806}{False:M807} ; Top camera light, looking down: true=on, false=off
```

### ACTUATE_BOOLEAN_COMMAND — Bottom Camera Light

```gcode
{True:M804}{False:M805} ; Bottom camera light, looking up: true=on, false=off
```

### COMMAND_ERROR_REGEX

```text
(?i)^(?:error\b.*|alarm\b.*|!!.*|halt(?:ed)?\b.*|.*\bhalted\b.*)$
```

### ENABLE_COMMAND

```gcode
M17 ; Enable all stepper drivers; no movement
```

## Driver behavior

115200 baud, 8N1, no flow control, DTR/RTS false; persistent serial by-id path.
ToolpathFeedRate with firmware acceleration planning, acknowledged command
flow control and physical completion via M400. The async software queue holds
100 commands; this is not 100 unacknowledged serial commands. Serial position
reports confirm completion. Regex expects the measured five-axis M114 output.
Normal disable waits for motion, shuts outputs off and then disables motors;
it is not an emergency-stop sequence. Configuration validation does not test
the physical emergency-stop switch.

Pressure read actuators are not configured until the ESP32-C3 sensor interface
exists. Output commands retain the physically identified camera-light mappings.
No M500, SD writes, step scaling changes or firmware flashing are included.

## Sources and validation

[Exact firmware Endstops implementation](https://raw.githubusercontent.com/markmaker/Smoothieware/23a1f0db/src/modules/tools/endstops/Endstops.cpp),
[firmware Robot implementation](https://raw.githubusercontent.com/markmaker/Smoothieware/23a1f0db/src/modules/robot/Robot.cpp),
[OpenPnP 2.6 driver](https://raw.githubusercontent.com/openpnp/openpnp/2.6/src/main/java/org/openpnp/machine/reference/driver/GcodeDriver.java).

OpenPnP loader, comment preprocessing, substitutions, response patterns and
camera capture are checked locally. The revised motion profile is not executed
as part of configuration validation.
