# V485 feeder controller

> Designs and original files by [MicroSMT](https://github.com/microsmt/Bing-feeder). [Credits and local changes](../../CREDITS.md).

This is the ESP32-C3 controller for the V485 feeder bus. The local firmware waits for an advance to finish before acknowledging M600, and also passes firmware updates from USB to the feeders over RS485. This machine uses the [direct USB–RS485 PC host](../V485-feeder/USB_host/README.md); the ESP32 controller is an alternative bus bridge.

| Browse | Contents |
| --- | --- |
| [Controller PCB](PCB_ControlBoard/README.md) | Gerber ZIP, schematic, BOM and three board views |
| [ESP32-C3 firmware](CODE_esp32C3/README.md) | PlatformIO C++ project, configuration and module notes |
| [180 mm busbars](PCB_busbar_short_180mm/README.md) | Three Gerber sets with individual board previews |
| [480 mm busbar](PCB_busbar_long_480mm/README.md) | Gerber ZIP, supplied notes and three board views |
