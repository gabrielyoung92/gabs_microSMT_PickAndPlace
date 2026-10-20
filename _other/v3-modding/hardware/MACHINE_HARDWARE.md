# Machine hardware inventory

Physical MicroSMT PNPv3 setup inventory. The top down camera and motion
controller were inspected on 2026-10-14 (Australia/Brisbane).
Other delivered components remain to be identified against the actual machine.

## Top down camera

The owner reports an earlier successful camera test. The USB and V4L2 queries
below confirm enumeration and advertised capabilities; frame capture, optical
calibration and OpenPnP operation were not tested during this inspection.
No camera settings were changed.

| Property | Observed value |
| --- | --- |
| Machine role | Top down camera, identified by owner |
| USB manufacturer / product strings | `HBVCAM Camera` / `top` |
| USB vendor ID / product ID | `1e45:8023` |
| USB serial | `HB2025070001` |
| Device revision | `bcdDevice 31.00` (`3100` in udev) |
| USB / UVC versions | USB 2.00 / UVC 1.00 |
| Negotiated USB speed | High Speed, 480 Mb/s |
| Power descriptor | Bus powered; maximum declared draw 500 mA, not measured draw |
| Linux driver | `uvcvideo`, version `6.12.107` |
| Image capture node at inspection | `/dev/video0` |
| Persistent image device path | `/dev/v4l/by-id/usb-HBVCAM_Camera_top_HB2025070001-video-index0` |
| Metadata node at inspection | `/dev/video1`, `UVCH` UVC payload header metadata |
| Persistent metadata path | `/dev/v4l/by-id/usb-HBVCAM_Camera_top_HB2025070001-video-index1` |
| Current image configuration | 1920 × 1080, MJPEG (`MJPG`), 30 fps |
| Current USB device location | Bus 001, device 049; port chain `1-1.4.2.2.1.4` |

Use the persistent image path when the capture backend accepts device paths;
`/dev/video0` and the USB device number can change after reconnection.
The two video nodes belong to one camera, not two image streams.
The current connection passes through multiple USB hubs; bandwidth is shared.

### Supported image modes

These are driver-enumerated modes, not measured sustained frame rates.

| Resolution | MJPEG fps | Uncompressed YUYV 4:2:2 fps |
| --- | --- | --- |
| 1920 × 1080 | 30, 25, 20, 15, 10 | 5, 3 |
| 1280 × 720 | 30, 25, 20, 15, 10 | 10, 5 |
| 640 × 480 | 30, 25, 20, 15, 10 | 30, 25, 20, 15 |
| 352 × 288 | 30, 25, 20, 15, 10 | 30, 25, 20, 15 |
| 320 × 240 | 30, 25, 20, 15, 10 | 30, 25, 20, 15 |
| 176 × 144 | 30, 25, 20, 15, 10 | 30, 25, 20, 15 |
| 160 × 120 | 30, 25, 20, 15, 10 | 30, 25, 20, 15 |

### Camera controls

All observed values matched the reported defaults at inspection.
The manual exposure and white balance temperature controls are inactive while
their automatic modes are enabled.

| V4L2 control | Range or choices | Step | Current value |
| --- | --- | --- | --- |
| `brightness` | -64 to 64 | 1 | 0 |
| `contrast` | 0 to 100 | 1 | 34 |
| `saturation` | 0 to 128 | 1 | 68 |
| `hue` | -180 to 180 | 1 | 0 |
| `white_balance_automatic` | Off / on | — | On |
| `gamma` | 100 to 500 | 1 | 300 |
| `gain` | 0 to 128 | 1 | 64 |
| `power_line_frequency` | 0 disabled, 1 50 Hz, 2 60 Hz | — | 1 (50 Hz) |
| `white_balance_temperature` | 2800 to 6500 | 10 | 4600, inactive |
| `sharpness` | 0 to 100 | 1 | 40 |
| `backlight_compensation` | 0 to 2 | 1 | 0 |
| `auto_exposure` | 1 manual, 3 aperture priority | — | 3 (automatic exposure) |
| `exposure_time_absolute` | 2 to 10000 | 1 | 166, inactive |
| `exposure_dynamic_framerate` | Off / on | — | Off |
| `pan_absolute` | -57600 to 57600 | 3600 | 0 |
| `tilt_absolute` | -43200 to 43200 | 3600 | 0 |

Pan/tilt entries establish exposed controls only; physical pan/tilt hardware is
not established. No focus control was exposed. Sensor model, shutter type,
lens, field of view, working distance and illumination remain unidentified.

The USB device also advertises audio interfaces bound to `snd-usb-audio`.
This does not establish that a microphone is physically fitted or functional.

### Inspection evidence

Raw output is retained under [evidence/top-camera-2026-10-14](evidence/top-camera-2026-10-14/):

- [USB descriptors](evidence/top-camera-2026-10-14/usb-descriptors.txt)
- [V4L2 image modes, controls and current configuration](evidence/top-camera-2026-10-14/v4l2-video0.txt)
- [V4L2 metadata node](evidence/top-camera-2026-10-14/v4l2-video1.txt)
- [Image node udev properties](evidence/top-camera-2026-10-14/udev-video0.txt)
- [Metadata node udev properties](evidence/top-camera-2026-10-14/udev-video1.txt)
- [USB topology](evidence/top-camera-2026-10-14/usb-topology.txt)

Queries used `lsusb -v -d 1e45:8023`, `lsusb -t`, `udevadm info` and
`v4l2-ctl --all --list-formats-ext --list-ctrls-menus` (image node), plus
`v4l2-ctl --all` (metadata node). V4L2 inspection used version 1.30.1 extracted
temporarily without installing system packages. Device access required sudo;
the inspection account's ordinary access returned permission denied.
USB descriptor output includes an access warning and a short processing-unit
descriptor warning; the mode and control tables above use successful V4L2
queries, rather than assuming every USB descriptor control is usable.

## Motion controller

The delivered controller responds over USB serial as a five-axis LPC1769
Smoothieware controller. See [controller inspection](CONTROLLER_INSPECTION.md)
for firmware identity, SD backup hashes, live status, axis configuration and
the boundary before motor testing.

## Raspberry Pi camera and output validation

Both cameras now stream on the Pi and return 1920×1080 frames through OpenPnP.
Concurrent MJPEG capture produced 150 frames per camera in five seconds.
The bottom camera is HBVCAM `bottom`, USB `1e46:8024`, serial `HB2025070001`.
Both cameras share that serial but have distinct product identities. Its image
path is `/dev/v4l/by-id/usb-HBVCAM_Camera_bottom_HB2025070001-video-index0`;
metadata is index1. At inspection the bottom image node was `/dev/video2`.

Owner identified bottom/up-looking LED M804/M805 and top/down-looking LED
M806/M807. Pump operation was heard, and configured N1 valve was identified;
incorrect tubing was found. Verified nozzle suction/release and N2 valve test
remain pending. See [current setup status](../docs/machine-setup-status.md).

## Remaining hardware identification

- Camera optics, final mounting, focus and geometric calibration.
- Delivered motion controller physical PCB revision and recovery procedure
  (USB identity, running firmware and SD file backup recorded).
- Feeder PCB revisions, MCU markings and actual connector wiring.
- Motors, drivers, endstops, power supplies and grounding.
- Vacuum pump, valves, sensors, nozzles and lighting.
