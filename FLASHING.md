# Installation — release 27

For Pixel 7 (`panther`) only. **First installation erases all phone data.**
Keep the bootloader unlocked while this port is installed.

## Required base

Install the full Google factory build **DP11.260918.006** before this port.
An OTA update alone is not sufficient: pending snapshots or leftover snapshot
partitions can prevent the new images from fitting.

| Requirement | Value |
| --- | --- |
| Device | `panther` |
| Google build | `DP11.260918.006` |
| Bootloader | `cloudripper-17.0-16334835` |
| Baseband | `g5300q-260818-260901-B-16228442` |
| Active slot | `a` |
| Bootloader lock | Unlocked |
| Snapshot status | `none` |

Download the matching
[Google factory image](https://dl.google.com/developers/android/cinnamonbun/images/factory/panther_beta-dp11.260918.006-factory-a2f235d7.zip).
Its SHA-256 is `a2f235d773da922fe5f8ee6dea1fbea7f5fb9badc5b3856aa5ca5f20ed7fa278`.
Install it using Google's included instructions. Back up first: unlocking and
factory installation erase data. Do not downgrade a newer bootloader to force a
match. If this base cannot be installed, this release is not compatible.

The automatic installer checks the model, bootloader, radio, slot and snapshot
status. It preserves Pixel boot, vendor and radio partitions; it does not install
the factory base or unlock the bootloader.

## Automatic installation

Download [flash.py](https://github.com/riffifi/nothing-os5-pixel7/releases/download/v27/flash.py)
into an empty writable folder. Install Python 3.11+ from
[python.org](https://www.python.org/downloads/) if needed. Allow about 11 GiB of
free space for the compressed downloads, extracted images and tools.

On Windows, install the [Google USB driver](https://developer.android.com/studio/run/win-usb)
if the phone is not recognized. The phone must also be recognized after switching
into fastbootd. On Linux, your user needs USB device access through the distro's
Android udev rules. The script does not require a system installation of adb,
fastboot, pip or zstd.

Connect one Pixel 7 by USB. Either leave it in bootloader fastboot, or enable USB
debugging in Android and accept this computer's authorization prompt. Then run:

```sh
# Linux
python3 flash.py
```

```powershell
# Windows PowerShell
py -3 flash.py
```

The script downloads the three compressed ROM images, obtains `vbmeta.img` from
the installer ZIP, verifies the embedded checksums and extracts the images. It
installs a Zstandard decoder into `.tools/python` and downloads Google's Platform
Tools 34.0.5 into `.tools`. Python dependencies stay in this folder. That fastboot
version was used on the development phone; newer fastboot caused USB failures.

Completed downloads are reused; interrupted downloads resume when supported by
the server. Files remain next to the script unless `--directory PATH` is supplied.

The script selects the only connected phone, or accepts a serial number. With
an authorized ADB connection, it checks the Pixel model and reboots to the
bootloader. It checks the firmware and asks you to type
`ERASE panther DP11.260918.006` before writing or erasing anything.

It then resizes and flashes `system_a`, `system_ext_a` and `product_a` through
fastbootd, flashes `vbmeta_a` with verification disabled, erases user data,
selects slot A and reboots. Slot B is not flashed. Other partitions are not
deleted to make room.

If a transfer or resize fails, leave the phone in fastboot and retry with the
same script and folder after checking the cable and required base. Do not boot
a partial installation or relock. An insufficient-space error may require
reinstalling the full factory base.

## Options

The commands below use `python3`; on Windows replace it with `py -3`.

```sh
python3 flash.py --download-only       # Download, extract and verify; no USB access
python3 flash.py --verify-only         # Verify local images; no downloads or USB access
python3 flash.py --check               # Prepare images/tools and check the connected phone
python3 flash.py --install SERIAL      # Select a specific phone; first install wipes data
python3 flash.py --update              # Update an existing installation of this port
python3 flash.py --directory PATH      # Choose the image and tool storage folder
```

Update mode asks for `UPDATE panther DP11.260918.006` and preserves user data.
Use it only for this port on the same firmware base, not for migration from stock
or another ROM. Back up before updating. Set the `FASTBOOT` environment variable
to override the downloaded fastboot executable.

Manual download is also supported: place the extracted `system.img`,
`system_ext.img`, `product.img` and `vbmeta.img` beside the script. Verified
existing images are reused. Pixel Camera remains an optional separate APK in
the release assets; install it with `adb install -r PixelCamera-9.8.102-panther.apk`.
The modified Nothing Camera is already included.

## Validation and recovery

This image set has booted on one Pixel 7 with SELinux enforcing. The original
installer had simulated safety tests; the automatic downloader and Windows path
have not been run on a Windows machine. Review [KNOWN_ISSUES.md](KNOWN_ISSUES.md).

After Android starts, complete setup and check `adb shell getprop sys.boot_completed`
and `adb shell getenforce`: expected results are `1` and `Enforcing`. Test calls,
data, cameras, sound and charging before relying on the phone.

To restore stock, use the matching Google factory package and its included
instructions. Restoring stock erases data. Never relock with this port installed;
only consider relocking after an unmodified stock installation has booted.
