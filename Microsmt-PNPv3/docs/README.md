# Machine setup notes

Notes from setting up and inspecting the PNPv3. The original
[MicroSMT manuals](../README.md#manuals) are in the machine folder.

- [Current machine setup and remaining calibration](machine-setup-status.md)
- [OpenPnP commands and operating limits](openpnp-gcode.md)
- [Machine hardware and camera identification](MACHINE_HARDWARE.md)
- [Controller inspection and measured configuration](CONTROLLER_INSPECTION.md)
- [Two-nozzle vacuum sensor plan](vacuum-sensors.md) and [datasheet](datasheets/README.md)

The machine runs OpenPnP on a Debian 13 Dell OptiPlex. The
[feeder dashboard](../../Bing-feeder/V485-feeder/USB_host/README.md) handles the
separate RS485 adapter; motion and cameras stay directly in OpenPnP.

Controller and camera measurements are in `evidence/`. Private backups stay
in the ignored `.local/v3-modding/` folder. Use the machine's saved OpenPnP settings for positions and calibration.
