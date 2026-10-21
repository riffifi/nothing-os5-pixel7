# Nothing OS 5.0 for Pixel 7

Unofficial port for **Pixel 7 (`panther`)**. Release **27** requires Google's
Android 17 **DP11.260918.006** firmware. Pixel 7 Pro and Pixel 7a are not supported.

Download the three compressed partition images, installer ZIP and download
checksums from this repo's release assets. Follow [FLASHING.md](FLASHING.md)
to extract the images and install them.

## Features

- Nothing launcher, apps, Settings and boot animation.
- Modified Nothing Camera with photo capture, QR scanning, 4K/30 video and
  1080p/120 slow motion. Pixel Camera is a separate optional APK.
- Bluetooth media audio, vibration, eSIM and Battery Share.
- Quick Tap gestures, including Essential Space capture.
- Pixel hardware information, Adaptive colour through Alive mode and HDR boost
  during HDR playback.
- Face enrollment and unlock, with no live preview during enrollment.

This build has booted on one Pixel 7 with SELinux enforcing. A clean installation
on a second phone has not been tested. Read [KNOWN_ISSUES.md](KNOWN_ISSUES.md)
before installing. First installation erases data; keep the bootloader unlocked.

## Release files

- `system.img.zst`, `system_ext.img.zst`, `product.img.zst` — partition images.
- `nothing-os5-panther-v27-installer.zip` — installer, `vbmeta.img` and docs.
- `SHA256SUMS.downloads` — checksums for the four required downloads.
- `PixelCamera-9.8.102-panther.apk` and its `.sha256` — optional Google Camera.

The images contain proprietary Nothing and Google software. This repository
contains release tools and documentation, not the full Android build source.
Images, APKs, device logs and signing keys are excluded from Git.

## Packaging

Python 3.11+, GNU tar and zstd are required to package an existing verified image
set. This command packages the current images; it does not build Android from
source:

```sh
python3 -m unittest discover -s tests
python3 tools/package_release.py --candidate .local/rom/candidate-v27/images.json \
  --vbmeta .local/rom/release-v27/vbmeta.img \
  --pixel-camera .local/rom/PixelCamera-9.8.102-panther.apk --github-only
```

Output is written to `dist/`. The packager verifies image hashes against
`release.json` and prepares assets below GitHub's 2 GiB per-file limit. Upload the image files,
installer ZIP, checksums and optional APK as release assets; do not add them to Git.
