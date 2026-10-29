# Bing feeders and controllers

> Designs and original files by [MicroSMT](https://github.com/microsmt/Bing-feeder). [Credits and local changes](../CREDITS.md).

Choose V3 or V485 below. Each has its own models, board files, firmware and assembly notes.

| Browse | Contents |
| --- | --- |
| [Powered-feeder dashboard](V485-feeder/USB_host/README.md) | PC host, firmware updates, configuration, stock and OpenPnP integration |
| [V485 feeder](V485-feeder/README.md) | 8/12/16/24 mm mechanics, shared parts, feeder/display PCBs and STM32 sources |
| [V485 controller](V485-Feeder%20Controller/README.md) | ESP32-C3 PlatformIO firmware, controller PCB and RS485 busbars |
| [V3 feeder](V3-feeder/README.md) | 8/12/16/24 mm parts, shared parts, STM32 sources and manuals |
| [V3 controller](V3-Feeder%20Controller/README.md) | Mega2560 sketch, controller board and feeder busbars |
| [STM32 build guide](STM32-BUILD.txt) | Universal V485 PlatformIO build and V3 source requirements |
| [License](LICENSE) | Supplied upstream license |

Latest [upstream comparison and photo check](UPSTREAM-2026-10-25.md): 25 October 2026.

## Vendor reference photo

![MicroSMT assembled Bing feeders](photos/Bing_feeders_reference.jpg)

Original MicroSMT photo from `Doc/微信图片_20250123114300.jpg`.

## About Bing feeders

MicroSMT’s Bing feeder uses a sprocket and position sensor to advance component tape. It was designed for the PNPv3 and can be triggered by a high-level pulse through OpenPnP’s ReferenceAutoFeeder. Using it on another machine still needs the right wiring and control setup.

Kits: [microsmt.com.cn](https://www.microsmt.com.cn) · Support: [Discord](https://discord.gg/qT7ZAAgspy) · [Google group](https://groups.google.com/g/pnpv3-bing-feeder)


![image](picture30.jpg)


### Position sensing
An optical sensor tracks the sprocket position so the feeder can control how far the tape advances.
![image](picture32.jpg)


### Tape support
The elastic pad underneath accommodates different tape thicknesses and helps reduce vibration and parts bouncing out.
![image](picture33.jpg)

### Magnetic mounting
The magnetic mount lets you remove and swap feeders quickly.
![image](picture34.jpg)
