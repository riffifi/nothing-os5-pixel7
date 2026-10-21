#!/usr/bin/env python3
"""Package verified partition images as a standalone fastboot release."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("installer", ROOT / "flash.py")
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)
DOCUMENTS = ("README.md", "FLASHING.md", "KNOWN_ISSUES.md", "flash.py", "release.json")


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def unpack_image(entry, target, expected):
    if target.exists():
        if target.stat().st_size == expected["size"] and digest(target) == expected["sha256"]:
            return
        raise ValueError(f"Existing output differs: {target}")
    source = Path(entry["compressed_path"])
    if digest(source) != entry["compressed_sha256"]:
        raise ValueError(f"Archive checksum mismatch: {source}")
    partial = target.with_suffix(".img.partial")
    try:
        with partial.open("wb") as output:
            subprocess.run(["zstd", "-q", "-d", "-c", source], stdout=output, check=True)
        if partial.stat().st_size != expected["size"] or digest(partial) != expected["sha256"]:
            raise ValueError(f"Decoded image mismatch: {source}")
        partial.replace(target)
    finally:
        partial.unlink(missing_ok=True)


def verify_archive(archive, folder, expected):
    seen = set()
    decoder = subprocess.Popen(["zstd", "-q", "-d", "-c", archive], stdout=subprocess.PIPE)
    try:
        with tarfile.open(fileobj=decoder.stdout, mode="r|") as tar:
            for member in tar:
                if member.name == folder or member.name == folder + "/":
                    if not member.isdir():
                        raise ValueError("Invalid archive root")
                    continue
                prefix = folder + "/"
                if not member.name.startswith(prefix):
                    raise ValueError(f"Unexpected archive path: {member.name}")
                name = member.name[len(prefix):]
                if name in seen or name not in expected or not member.isfile():
                    raise ValueError(f"Unexpected archive member: {member.name}")
                with tar.extractfile(member) as stream:
                    actual = hashlib.file_digest(stream, "sha256").hexdigest()
                if actual != expected[name]:
                    raise ValueError(f"Archive content mismatch: {name}")
                seen.add(name)
                print(f"Archive verified: {name}", flush=True)
        # Consume final tar padding so the decoder can exit normally.
        while decoder.stdout.read(1024 * 1024):
            pass
        if decoder.wait() or seen != set(expected):
            raise ValueError("Archive is incomplete")
    finally:
        decoder.stdout.close()
        if decoder.poll() is None:
            decoder.kill()
            decoder.wait()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--vbmeta", type=Path, required=True)
    parser.add_argument("--pixel-camera", type=Path)
    parser.add_argument("--github-only", action="store_true", help="prepare individual assets below 2 GiB")
    parser.add_argument("--output", type=Path, default=ROOT / "dist")
    args = parser.parse_args()
    release = installer.load_release(ROOT)
    candidate = json.loads(args.candidate.read_text())
    if str(candidate["revision"]) != release["version"]:
        raise ValueError("Candidate revision differs from release.json")
    if not candidate.get("runtime_boot_verified") or candidate.get("runtime_selinux") != "Enforcing":
        raise ValueError("Candidate must have booted with SELinux enforcing")
    args.output.mkdir(parents=True, exist_ok=True)
    folder = f"nothing-os5-panther-v{release['version']}"
    bundle = args.output / folder
    bundle.mkdir(exist_ok=True)
    sources = {e["partition"] + "_a": e for e in candidate["images"]}
    for image in release["images"]:
        if image["partition"] == "vbmeta_a":
            if args.vbmeta.stat().st_size != image["size"] or digest(args.vbmeta) != image["sha256"]:
                raise ValueError("vbmeta differs from release.json")
            shutil.copyfile(args.vbmeta, bundle / image["file"])
        else:
            source = sources[image["partition"]]
            if source["sha256"] != image["sha256"] or source["size"] != image["size"]:
                raise ValueError("Candidate image differs from release.json")
            print(f"Preparing {image['file']}", flush=True)
            unpack_image(source, bundle / image["file"], image)
    for name in DOCUMENTS:
        shutil.copyfile(ROOT / name, bundle / name)
    allowed = set(DOCUMENTS) | {i["file"] for i in release["images"]} | {"SHA256SUMS"}
    if {p.name for p in bundle.iterdir()} - allowed:
        raise ValueError("Output directory contains unexpected files")
    sums = {p.name: digest(p) for p in sorted(bundle.iterdir()) if p.name != "SHA256SUMS"}
    (bundle / "SHA256SUMS").write_text("".join(f"{value}  {name}\n" for name, value in sums.items()))
    sums["SHA256SUMS"] = digest(bundle / "SHA256SUMS")

    if args.github_only:
        downloads = {}
        for image in release["images"]:
            if image["partition"] == "vbmeta_a":
                continue
            entry = sources[image["partition"]]
            source = Path(entry["compressed_path"])
            target = args.output / (image["file"] + ".zst")
            if target.exists():
                if digest(target) != entry["compressed_sha256"]:
                    raise ValueError(f"Existing asset differs: {target}")
            else:
                os.link(source, target)
            if target.stat().st_size >= 2 * 1024**3:
                raise ValueError(f"GitHub asset too large: {target}")
            downloads[target.name] = entry["compressed_sha256"]
        archive = args.output / (folder + "-installer.zip")
        with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as output:
            for name in (*DOCUMENTS, "vbmeta.img", "SHA256SUMS"):
                output.write(bundle / name, name)
        with zipfile.ZipFile(archive) as check:
            if check.testzip() is not None:
                raise ValueError("Installer ZIP failed CRC verification")
            for name in check.namelist():
                if hashlib.sha256(check.read(name)).hexdigest() != sums[name]:
                    raise ValueError(f"Installer ZIP content mismatch: {name}")
        downloads[archive.name] = digest(archive)
        (args.output / "SHA256SUMS.downloads").write_text("".join(
            f"{value}  {name}\n" for name, value in sorted(downloads.items())))
        if args.pixel_camera:
            apk = args.output / "PixelCamera-9.8.102-panther.apk"
            if not apk.exists():
                os.link(args.pixel_camera, apk)
            if digest(apk) != digest(args.pixel_camera):
                raise ValueError("Pixel Camera asset differs")
            apk.with_name(apk.name + ".sha256").write_text(f"{digest(apk)}  {apk.name}\n")
        print(f"GitHub assets ready: {args.output}", flush=True)
        return

    archive = args.output / (folder + ".tar.zst")
    partial = archive.with_suffix(".zst.partial")
    tar = subprocess.Popen(["tar", "--sort=name", "--mtime=@0", "--owner=0", "--group=0",
                            "--numeric-owner", "-C", args.output, "-cf", "-", folder],
                           stdout=subprocess.PIPE)
    try:
        subprocess.run(["zstd", "-q", "-T2", "-3", "-f", "-o", partial],
                       stdin=tar.stdout, check=True)
        tar.stdout.close()
        if tar.wait():
            raise ValueError("tar failed")
        verify_archive(partial, folder, sums)
        partial.replace(archive)
    finally:
        tar.stdout.close()
        if tar.poll() is None:
            tar.kill()
            tar.wait()
        partial.unlink(missing_ok=True)
    archive.with_name(archive.name + ".sha256").write_text(f"{digest(archive)}  {archive.name}\n")
    if args.pixel_camera:
        apk = args.output / "PixelCamera-9.8.102-panther.apk"
        if apk.exists():
            if digest(apk) != digest(args.pixel_camera):
                raise ValueError("Existing Pixel Camera APK differs")
        else:
            try:
                os.link(args.pixel_camera, apk)
            except OSError:
                shutil.copyfile(args.pixel_camera, apk)
        apk.with_name(apk.name + ".sha256").write_text(f"{digest(apk)}  {apk.name}\n")
    print(f"Release ready: {archive} ({archive.stat().st_size:,} bytes)", flush=True)


if __name__ == "__main__":
    main()
