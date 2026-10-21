# Known issues — release 27

| Area | Status |
| --- | --- |
| Face unlock | Enrollment and unlock work. Enrollment has no live camera preview; guidance is in English. |
| Nothing Camera | Panorama, 240 fps and some filters remain broken. Long recordings have not been tested. |
| Glyph | Pixel 7 has no Glyph LEDs. Some effects use the rear flashlight; full Glyph compatibility is unavailable. |
| Notifications | A clipped banner was reported once. It has not been reproduced. |
| Essential Space | Double back tap capture works. Triple back tap to open Space needs physical confirmation. |
| NFC | Tag and iPhone pass reading work. Campus-pass emulation needs testing at the reader. |
| Wireless charging | Battery Share was tested with a charging receiver. Charging the Pixel on a Qi pad is untested. |
| Battery | Background crash/retry loops were fixed. Battery endurance has not been measured. |
| OTA | No update service. Install updates through fastboot. |
| Play Store | Compatibility varies by app. Payments, device certification and integrity checks are not guaranteed. |

The partition set has booted on one Pixel 7. The public installer has been tested
with simulated fastboot responses and verified image files; a fresh installation
on another phone is untested. This is an experimental release.

Verified Boot is disabled and the bootloader must remain unlocked. The port uses
modified framework code and locally signed components. SELinux remains enforcing.
