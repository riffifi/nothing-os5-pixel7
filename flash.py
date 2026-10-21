#!/usr/bin/env python3
"""Verify and install the Pixel 7 release from an extracted image bundle."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
PARTITIONS = {"system_a", "system_ext_a", "product_a", "vbmeta_a"}


def load_release(root=ROOT):
    release = json.loads((root / "release.json").read_text())
    if release["device"] != "panther" or release["slot"] != "a":
        raise ValueError("Unsupported release target")
    images = release["images"]
    if len(images) != 4 or {i["partition"] for i in images} != PARTITIONS:
        raise ValueError("Expected system, system_ext, product and vbmeta")
    for image in images:
        if image["file"] != image["partition"].removesuffix("_a") + ".img":
            raise ValueError("Invalid image filename")
        if image["size"] <= 0 or not re.fullmatch(r"[0-9a-f]{64}", image["sha256"]):
            raise ValueError("Invalid image size or checksum")
    return release


def verify_images(release, root=ROOT):
    for image in release["images"]:
        path = root / image["file"]
        if path.stat().st_size != image["size"]:
            raise ValueError(f"Wrong size: {path.name}")
        with path.open("rb") as stream:
            actual = hashlib.file_digest(stream, "sha256").hexdigest()
        if actual != image["sha256"]:
            raise ValueError(f"Checksum mismatch: {path.name}")
        print(f"Verified {path.name}", flush=True)


class Fastboot:
    def __init__(self, serial):
        executable = os.environ.get("FASTBOOT", "fastboot")
        if not shutil.which(executable):
            raise ValueError("fastboot is required; set FASTBOOT to its executable path")
        self.command = [executable, "-s", serial]

    def run(self, *args, timeout=60):
        print("fastboot " + " ".join(args), flush=True)
        result = subprocess.run(self.command + list(args), text=True,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                timeout=timeout)
        print(result.stdout, end="", flush=True)
        if result.returncode:
            raise RuntimeError(f"fastboot {' '.join(args)} failed")
        return result.stdout

    def getvar(self, name):
        output = self.run("getvar", name)
        for line in output.splitlines():
            line = line.removeprefix("(bootloader) ").strip()
            if line.startswith(name + ": "):
                return line[len(name) + 2:].strip()
        raise ValueError(f"fastboot did not report {name}")

    def expect(self, name, expected):
        actual = self.getvar(name)
        if actual != expected:
            raise ValueError(f"{name}: expected {expected}, got {actual}")


def check_device(fb, release):
    for name, expected in (
        ("product", release["device"]),
        ("version-bootloader", release["bootloader"]),
        ("version-baseband", release["baseband"]),
        ("current-slot", "a"), ("unlocked", "yes"),
        ("snapshot-update-status", "none"),
    ):
        fb.expect(name, expected)


def resize_plan(fb, images):
    shrink, grow = [], []
    for image in images:
        if image["partition"] == "vbmeta_a":
            continue
        raw = fb.getvar("partition-size:" + image["partition"])
        if not re.fullmatch(r"0x[0-9a-fA-F]+", raw):
            raise ValueError(f"Invalid partition size: {raw}")
        current = int(raw, 16)
        if current > image["size"]:
            shrink.append(image)
        elif current < image["size"]:
            grow.append(image)
    return shrink + grow


def install(fb, release, root, clean):
    check_device(fb, release)
    if fb.getvar("is-userspace") != "no":
        raise ValueError("Start in bootloader fastboot, not fastbootd")
    if not sys.stdin.isatty():
        raise ValueError("Run interactively to confirm the base build and data handling")
    action = "ERASE" if clean else "UPDATE"
    expected = f"{action} panther {release['base_build']}"
    print("First installation erases all phone data." if clean else
          "Update mode is only for an existing installation of this port.")
    print("The exact Google base must already be installed on slot A.")
    if input(f"Type {expected}: ").strip() != expected:
        raise ValueError("Confirmation did not match")
    fb.run("reboot", "fastboot")
    fb.expect("is-userspace", "yes")
    check_device(fb, release)
    # Read every size first; shrink before growing. Never delete other partitions.
    for image in resize_plan(fb, release["images"]):
        fb.run("resize-logical-partition", image["partition"], str(image["size"]))
    for image in release["images"]:
        if image["partition"] != "vbmeta_a":
            fb.run("-S", "16M", "flash", image["partition"],
                   str(root / image["file"]), timeout=600)
    fb.run("reboot", "bootloader")
    check_device(fb, release)
    fb.run("--disable-verity", "--disable-verification", "flash", "vbmeta_a",
           str(root / "vbmeta.img"))
    if clean:
        fb.run("-w", timeout=180)
    fb.run("set_active", "a")
    fb.run("reboot")
    print("Flashing complete. Keep the bootloader unlocked.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--verify-only", action="store_true", help="check images without USB access")
    mode.add_argument("--check", metavar="SERIAL", help="check images and device without writes")
    mode.add_argument("--install", metavar="SERIAL", help="first installation; erases phone data")
    mode.add_argument("--update", metavar="SERIAL", help="update this port; preserves phone data")
    args = parser.parse_args()
    release = load_release()
    verify_images(release)
    if args.verify_only:
        return
    fb = Fastboot(args.check or args.install or args.update)
    if args.check:
        check_device(fb, release)
        print("Device checks passed. No writes performed.")
    else:
        install(fb, release, ROOT, clean=bool(args.install))


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError, RuntimeError, subprocess.SubprocessError,
            EOFError, KeyboardInterrupt) as error:
        print(f"Stopped: {error}", file=sys.stderr)
        print("If writing had started, leave the phone in fastboot and retry with the same bundle. "
              "Do not boot a partial installation or relock the bootloader.", file=sys.stderr)
        sys.exit(1)
