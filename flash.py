#!/usr/bin/env python3
"""Download and install Nothing OS 5.0 for Pixel 7 on Linux or Windows."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import time
import urllib.request
import urllib.error
import zipfile
import importlib
import http.client
import re
import shutil
import subprocess
import sys

if sys.version_info < (3, 11):
    raise SystemExit("Python 3.11 or newer is required: https://www.python.org/downloads/")

ROOT = Path(__file__).resolve().parent
PARTITIONS = {"system_a", "system_ext_a", "product_a", "vbmeta_a"}

REPOSITORY = "riffifi/nothing-os5-pixel7"
RELEASE_DATA = {'name': 'Nothing OS 5.0 for Pixel 7',
 'version': '27',
 'status': 'experimental',
 'device': 'panther',
 'base_build': 'DP11.260918.006',
 'bootloader': 'cloudripper-17.0-16334835',
 'baseband': 'g5300q-260818-260901-B-16228442',
 'slot': 'a',
 'images': [{'file': 'system.img',
             'partition': 'system_a',
             'size': 1879175168,
             'sha256': '7ec4f42c6f524d827e808a0da088719fa6d8076e96717b326dc7cd69d15f50ee'},
            {'file': 'system_ext.img',
             'partition': 'system_ext_a',
             'size': 1436680192,
             'sha256': '0f3965972d182987e0df6586948ae576b7e71cc005271f8edbf367a7b6f3c33f'},
            {'file': 'product.img',
             'partition': 'product_a',
             'size': 3985092608,
             'sha256': '9a0b49a278b51ca4f559c5b90024003cb0766ac6575252f84f2b372141d414d2'},
            {'file': 'vbmeta.img',
             'partition': 'vbmeta_a',
             'size': 12288,
             'sha256': 'e2816555dd931ba574c86ce33f7208a64117cdf754cc043762b7bf3fc9840a71'}],
 'validation': {'boot': 'verified on one Pixel 7',
                'selinux': 'Enforcing',
                'clean_install': 'not tested on a second device',
                'ota': False}}
COMPRESSED = {'system.img.zst': {'sha256': '4fbe4da2c3e3fe384e915365e50179e3bd5d7eacd92c6d7b6f4287f4ab5d8ee3',
                    'size': 1102520146},
 'system_ext.img.zst': {'sha256': '572e90ee48219d18632f56f61548de8420252b1e19a913f36d4537302b767558',
                        'size': 601071673},
 'product.img.zst': {'sha256': 'd7754a77b33e253db4bd29f736e306797918a40393fe2d5ac116c2332738d61a',
                     'size': 1965301839}}
DOWNLOADS = "https://github.com/" + REPOSITORY + "/releases/download/v27/"



def load_release(root=ROOT):
    release = json.loads((root / "release.json").read_text()) if (root / "release.json").exists() else json.loads(json.dumps(RELEASE_DATA))
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
    def __init__(self, serial, executable=None):
        executable = executable or os.environ.get("FASTBOOT", "fastboot")
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


def file_hash(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def download(url, path, sha256=None, size=None):
    """Cache completed downloads and resume interrupted HTTP transfers."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and (size is None or path.stat().st_size == size):
        if sha256 is None or file_hash(path) == sha256:
            return path
    partial = path.with_name(path.name + ".part")
    for attempt in range(3):
        offset = partial.stat().st_size if partial.exists() else 0
        headers = {"User-Agent": "Pixel7-ROM-Installer/27"}
        if offset:
            headers["Range"] = f"bytes={offset}-"
        try:
            request = urllib.request.Request(url, headers=headers)
            print(f"Downloading {path.name}" + (f" (resuming at {offset:,} bytes)" if offset else ""), flush=True)
            with urllib.request.urlopen(request, timeout=60) as response:
                resume = offset and response.status == 206
                if resume and not response.headers.get("Content-Range", "").startswith(f"bytes {offset}-"):
                    raise ValueError("Server returned an invalid download range")
                received = offset if resume else 0
                last = time.monotonic()
                with partial.open("ab" if resume else "wb") as output:
                    while chunk := response.read(1024 * 1024):
                        output.write(chunk)
                        received += len(chunk)
                        if size is not None and received > size:
                            raise ValueError(f"Download exceeds expected size: {path.name}")
                        if time.monotonic() - last >= 5:
                            print(f"  {received / 1024**2:,.0f} MiB" +
                                  (f" / {size / 1024**2:,.0f} MiB" if size else ""), flush=True)
                            last = time.monotonic()
            if size is not None and partial.stat().st_size != size:
                raise OSError(f"Incomplete download: {path.name}")
            if sha256 is not None and file_hash(partial) != sha256:
                partial.unlink()
                raise ValueError(f"Download checksum mismatch: {path.name}")
            partial.replace(path)
            return path
        except urllib.error.HTTPError as error:
            if error.code == 416:
                partial.unlink(missing_ok=True)
            elif error.code not in (429, 500, 502, 503, 504):
                raise
            if attempt == 2:
                raise
        except (OSError, urllib.error.URLError, http.client.IncompleteRead):
            if attempt == 2:
                raise
        time.sleep(2)
    raise RuntimeError(f"Could not download {path.name}")


def extract_zip(archive, destination):
    with zipfile.ZipFile(archive) as source:
        for item in source.infolist():
            target = (destination / item.filename).resolve()
            if not target.is_relative_to(destination.resolve()) or "\\" in item.filename:
                raise ValueError("Unsafe path in downloaded ZIP")
            if (item.external_attr >> 16) & 0o170000 == 0o120000:
                raise ValueError("Symlink in downloaded ZIP")
        source.extractall(destination)


def platform_tools(root):
    override = os.environ.get("FASTBOOT")
    if override:
        executable = shutil.which(override)
        if not executable:
            raise ValueError("FASTBOOT does not point to an executable")
        return executable
    system = platform.system()
    if system not in ("Windows", "Linux"):
        raise ValueError("Automatic setup supports Windows and Linux")
    if platform.machine().lower() not in ("amd64", "x86_64"):
        raise ValueError("Automatic Platform Tools setup requires a 64-bit Intel/AMD computer")
    tools = root / ".tools"
    # Use the version used for this port, avoiding the observed fastboot 37 USB failures.
    suffix = "windows" if system == "Windows" else "linux"
    archive = tools / f"platform-tools_r34.0.5-{suffix}.zip"
    binary = tools / "platform-tools" / ("fastboot.exe" if system == "Windows" else "fastboot")
    if not binary.exists():
        download(f"https://dl.google.com/android/repository/{archive.name}", archive)
        extract_zip(archive, tools)
        if system == "Linux":
            for name in ("fastboot", "adb", "mke2fs", "make_f2fs", "make_f2fs_casefold"):
                path = tools / "platform-tools" / name
                if path.exists():
                    path.chmod(path.stat().st_mode | 0o111)
    if not binary.exists():
        raise ValueError("Downloaded Platform Tools does not contain fastboot")
    return str(binary)


def zstandard_module(root):
    """Install binary Python dependencies locally, without changing system Python."""
    target = root / ".tools" / "python"
    sys.path.insert(0, str(target))
    try:
        return importlib.import_module("zstandard")
    except ImportError:
        pass
    # Bootstrap pip from its wheel so Linux does not need pip/venv system packages.
    pip_version = "25.3"
    request = urllib.request.Request(f"https://pypi.org/pypi/pip/{pip_version}/json",
                                     headers={"User-Agent": "Pixel7-ROM-Installer/27"})
    with urllib.request.urlopen(request, timeout=60) as response:
        info = json.load(response)
    wheel = next(item for item in info["urls"] if item["filename"].endswith("py3-none-any.whl"))
    archive = download(wheel["url"], root / ".tools" / wheel["filename"],
                       wheel["digests"]["sha256"], wheel["size"])
    pip_root = root / ".tools" / "pip"
    extract_zip(archive, pip_root)
    print("Installing the local Zstandard decoder...", flush=True)
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(pip_root)
    subprocess.run([sys.executable, "-m", "pip", "install", "--disable-pip-version-check",
                    "--no-warn-script-location", "--only-binary=:all:", "--no-deps",
                    "--index-url", "https://pypi.org/simple", "--target", str(target),
                    "zstandard==0.25.0"], check=True, env=environment)
    importlib.invalidate_caches()
    return importlib.import_module("zstandard")


def prepare_images(release, root):
    root.mkdir(parents=True, exist_ok=True)
    pending = []
    for image in release["images"]:
        path = root / image["file"]
        if path.exists() and path.stat().st_size == image["size"] and file_hash(path) == image["sha256"]:
            print(f"Verified {path.name}", flush=True)
            continue
        if path.exists():
            raise ValueError(f"Existing image differs: {path}. Remove it to download a fresh copy.")
        pending.append(image)
    needed = sum(i["size"] for i in pending)
    needed += sum(COMPRESSED[i["file"] + ".zst"]["size"] for i in pending if i["file"] != "vbmeta.img")
    if shutil.disk_usage(root).free < needed + 256 * 1024**2:
        raise ValueError(f"Allow {(needed / 1024**3) + 0.25:.1f} GiB of free space for downloads and images")
    decoder = zstandard_module(root) if any(i["file"] != "vbmeta.img" for i in pending) else None
    for image in pending:
        target = root / image["file"]
        partial = target.with_name(target.name + ".part")
        try:
            if image["file"] == "vbmeta.img":
                archive = download(DOWNLOADS + "nothing-os5-panther-v27-installer.zip",
                                   root / ".downloads" / "nothing-os5-panther-v27-installer.zip")
                with zipfile.ZipFile(archive) as source:
                    if source.getinfo("vbmeta.img").file_size != image["size"]:
                        raise ValueError("vbmeta size mismatch in installer ZIP")
                    partial.write_bytes(source.read("vbmeta.img"))
            else:
                name = image["file"] + ".zst"
                metadata = COMPRESSED[name]
                archive = download(DOWNLOADS + name, root / ".downloads" / name,
                                   metadata["sha256"], metadata["size"])
                print(f"Extracting {image['file']}...", flush=True)
                written = 0
                with archive.open("rb") as compressed, partial.open("wb") as output:
                    with decoder.ZstdDecompressor().stream_reader(compressed) as source:
                        while chunk := source.read(4 * 1024**2):
                            written += len(chunk)
                            if written > image["size"]:
                                raise ValueError("Decompressed image exceeds expected size")
                            output.write(chunk)
            if partial.stat().st_size != image["size"] or file_hash(partial) != image["sha256"]:
                raise ValueError(f"Image checksum mismatch: {image['file']}")
            partial.replace(target)
            print(f"Verified {target.name}", flush=True)
        finally:
            partial.unlink(missing_ok=True)


def choose_serial(executable, requested=None):
    result = subprocess.run([executable, "devices"], capture_output=True, text=True, timeout=20, check=True)
    devices = [line.split()[0] for line in result.stdout.splitlines()
               if len(line.split()) >= 2 and line.split()[1] == "fastboot"]
    if not devices:
        adb = Path(executable).with_name("adb.exe" if platform.system() == "Windows" else "adb")
        if not adb.exists():
            found = shutil.which("adb")
            adb = Path(found) if found else adb
        if adb.exists():
            result = subprocess.run([str(adb), "devices"], capture_output=True, text=True,
                                    timeout=20, check=True)
            authorized = [line.split()[0] for line in result.stdout.splitlines()
                          if len(line.split()) == 2 and line.split()[1] == "device"]
            if requested:
                authorized = [serial for serial in authorized if serial == requested]
            if len(authorized) == 1:
                serial = authorized[0]
                result = subprocess.run([str(adb), "-s", serial, "shell", "getprop",
                                         "ro.product.vendor.device"], capture_output=True,
                                        text=True, timeout=20, check=True)
                if result.stdout.strip() != "panther":
                    raise ValueError("The connected Android device is not a Pixel 7")
                print("Rebooting the Pixel 7 to bootloader fastboot...", flush=True)
                subprocess.run([str(adb), "-s", serial, "reboot", "bootloader"], check=True, timeout=30)
                deadline = time.monotonic() + 90
                while time.monotonic() < deadline:
                    result = subprocess.run([executable, "devices"], capture_output=True,
                                            text=True, timeout=10, check=True)
                    if any(line.split()[:2] == [serial, "fastboot"] for line in result.stdout.splitlines()):
                        return serial
                    time.sleep(1)
    if requested:
        if requested not in devices:
            raise ValueError(f"Device {requested} is not in fastboot. Check its USB connection and driver.")
        return requested
    if len(devices) != 1:
        raise ValueError("Connect exactly one phone in bootloader fastboot, or specify its serial. "
                         "On Windows, install Google's USB driver if it is not detected.")
    return devices[0]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--verify-only", action="store_true", help="check images without USB access")
    mode.add_argument("--check", metavar="SERIAL", nargs="?", const="auto", help="check device without writes")
    mode.add_argument("--install", metavar="SERIAL", nargs="?", const="auto", help="first installation; erases phone data (default)")
    mode.add_argument("--update", metavar="SERIAL", nargs="?", const="auto", help="update this port; preserves phone data")
    mode.add_argument("--download-only", action="store_true", help="download and verify images without USB access")
    parser.add_argument("--directory", type=Path, default=ROOT, help="image/download directory")
    args = parser.parse_args()
    root = args.directory.resolve()
    release = load_release(root)
    if args.verify_only:
        verify_images(release, root)
        return
    prepare_images(release, root)
    if args.download_only:
        return
    executable = platform_tools(root)
    requested = args.check or args.install or args.update
    serial = choose_serial(executable, None if requested in (None, "auto") else requested)
    fb = Fastboot(serial, executable)
    if args.check:
        check_device(fb, release)
        print("Device checks passed. No writes performed.")
    else:
        install(fb, release, root, clean=not bool(args.update))


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError, RuntimeError, subprocess.SubprocessError,
            EOFError, KeyboardInterrupt, ImportError, zipfile.BadZipFile,
            http.client.HTTPException) as error:
        print(f"Stopped: {error}", file=sys.stderr)
        print("If writing had started, leave the phone in fastboot and retry with the same bundle. "
              "Do not boot a partial installation or relock the bootloader.", file=sys.stderr)
        sys.exit(1)
