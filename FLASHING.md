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

The matching factory download is
[panther DP11.260918.006](https://dl.google.com/developers/android/cinnamonbun/images/factory/panther_beta-dp11.260918.006-factory-a2f235d7.zip).
Its SHA-256 is:

```text
a2f235d773da922fe5f8ee6dea1fbea7f5fb9badc5b3856aa5ca5f20ed7fa278
```

Back up your data, unlock the bootloader and install that factory package using
Google's included instructions. Unlocking and factory installation erase data.
Do not substitute a newer build or downgrade a newer bootloader to force a match.
If the required base cannot be installed, this release is not compatible.

The installer checks device, bootloader, radio, slot and snapshot status. Those
checks cannot prove every retained partition matches: installing the full base
is still required. It preserves Pixel boot, vendor and radio partitions.

## Extract and verify

Use Linux, Python 3.11+, unzip, zstd and Android Platform Tools. Fastboot 34.0.5
with 16 MiB transfers was used on the development phone; newer fastboot caused
USB transfer failures there. Use a reliable data cable. Allow 8 GB for extraction,
in addition to the downloaded files. Download all three `.img.zst` files,
`nothing-os5-panther-v27-installer.zip` and `SHA256SUMS.downloads` into one folder.

```sh
sha256sum -c SHA256SUMS.downloads
unzip nothing-os5-panther-v27-installer.zip -d nothing-os5-panther-v27
for image in system system_ext product; do
  zstd -d "$image.img.zst" -o "nothing-os5-panther-v27/$image.img"
done
cd nothing-os5-panther-v27
sha256sum -c SHA256SUMS
python3 flash.py --verify-only
```

`--verify-only` reads the images without contacting a phone. Decompression produces
raw, fastboot-flashable images. The installer ZIP is not a recovery-flashable ZIP.

## First installation

With the matching Google base installed, check its build in Android:

```sh
adb shell getprop ro.build.id
adb reboot bootloader
fastboot devices
```

Use the device serial printed by fastboot in place of `SERIAL`:

```sh
python3 flash.py --check SERIAL
python3 flash.py --install SERIAL
```

The installer asks you to type `ERASE panther DP11.260918.006`. It enters
fastbootd, resizes and flashes `system_a`, `system_ext_a` and `product_a`, then
returns to the bootloader, flashes `vbmeta_a` with verification disabled,
erases user data, selects slot A and reboots. It does not modify slot B or delete
partitions to make room.

If a resize or transfer fails, stop and leave the phone in fastboot. Check the
cable and required base before retrying the same bundle. Do not boot a partially
written installation. An insufficient-space error can require reinstalling the
full factory base; do not delete arbitrary logical partitions.

After Android starts, complete setup and check:

```sh
adb wait-for-device
adb shell getprop sys.boot_completed
adb shell getenforce
```

Expected results: `1` and `Enforcing`. Test calls, mobile data, cameras, sound and
charging before relying on the phone. Known limitations are in
[KNOWN_ISSUES.md](KNOWN_ISSUES.md).

## Updates

For an existing installation of this port on the same firmware base:

```sh
adb reboot bootloader
python3 flash.py --update SERIAL
```

Update mode asks for `UPDATE panther DP11.260918.006` and preserves user data.
Do not use it to migrate from stock or another ROM. Back up before updating.
Set `FASTBOOT=/path/to/fastboot` to choose a particular fastboot executable.

## Optional Pixel Camera

Download `PixelCamera-9.8.102-panther.apk` and its checksum alongside the ROM.
The APK is Google-signed, version `9.8.102.738511538.14`, from the matching Pixel
factory image. Rear and front photos have been tested on this port.

```sh
sha256sum -c PixelCamera-9.8.102-panther.apk.sha256
adb install -r PixelCamera-9.8.102-panther.apk
```

The modified Nothing Camera is already included. If installing Pixel Camera
reports a signature conflict, keep the existing app and its data.

## Restore stock

Use the matching Google factory package and its included flashing instructions.
Restoring stock erases data. Never relock the bootloader with this port installed;
only consider relocking after an unmodified stock installation has booted.
