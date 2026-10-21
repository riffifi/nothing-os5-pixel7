import copy
import hashlib
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("flash", ROOT / "flash.py")
flash = importlib.util.module_from_spec(spec)
spec.loader.exec_module(flash)


class Device:
    def __init__(self, release, overrides=None, fail=None):
        self.values = {
            "product": "panther", "version-bootloader": release["bootloader"],
            "version-baseband": release["baseband"], "current-slot": "a",
            "unlocked": "yes", "snapshot-update-status": "none", "is-userspace": "no",
        }
        for image in release["images"]:
            self.values["partition-size:" + image["partition"]] = hex(image["size"])
        self.values.update(overrides or {})
        self.calls = []
        self.fail = fail

    def getvar(self, name):
        return self.values[name]

    def expect(self, name, expected):
        if self.getvar(name) != expected:
            raise ValueError(name)

    def run(self, *args, timeout=60):
        self.calls.append(args)
        if self.fail and self.fail in args:
            raise RuntimeError("simulated USB failure")
        if args == ("reboot", "fastboot"):
            self.values["is-userspace"] = "yes"
        if args == ("reboot", "bootloader"):
            self.values["is-userspace"] = "no"


class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.release = flash.load_release(ROOT)

    def install(self, device, clean=True):
        word = "ERASE" if clean else "UPDATE"
        with patch.object(flash.sys.stdin, "isatty", return_value=True), \
             patch("builtins.input", return_value=f"{word} panther {self.release['base_build']}"):
            flash.install(device, self.release, ROOT, clean)

    def test_incompatible_devices_rejected_before_any_mutation(self):
        for field, value in (("product", "cheetah"), ("unlocked", "no"),
                             ("current-slot", "b"), ("snapshot-update-status", "merging"),
                             ("version-bootloader", "newer"), ("version-baseband", "wrong")):
            with self.subTest(field=field):
                device = Device(self.release, {field: value})
                with self.assertRaises(ValueError):
                    self.install(device)
                self.assertEqual(device.calls, [])

    def test_confirmation_rejected_before_reboot_or_writes(self):
        device = Device(self.release)
        with patch.object(flash.sys.stdin, "isatty", return_value=True), \
             patch("builtins.input", return_value="no"):
            with self.assertRaises(ValueError):
                flash.install(device, self.release, ROOT, True)
        self.assertEqual(device.calls, [])

    def test_clean_install_writes_only_allowed_partitions_and_then_wipes(self):
        device = Device(self.release)
        self.install(device)
        writes = [c for c in device.calls if "flash" in c]
        partitions = [c[c.index("flash") + 1] for c in writes]
        self.assertEqual(set(partitions), flash.PARTITIONS)
        self.assertEqual(len(partitions), 4)
        for call in writes[:3]:
            self.assertEqual(call[:2], ("-S", "16M"))
        self.assertIn("--disable-verification", writes[-1])
        self.assertGreater(device.calls.index(("-w",)), device.calls.index(writes[-1]))
        self.assertEqual(device.calls[-1], ("reboot",))

    def test_update_does_not_wipe_or_delete_partitions(self):
        device = Device(self.release)
        self.install(device, clean=False)
        self.assertFalse(any("-w" in c or "erase" in c or "delete-logical-partition" in c
                             for c in device.calls))

    def test_transfer_failure_stops_before_wipe_and_final_reboot(self):
        device = Device(self.release, fail="system_ext_a")
        with self.assertRaises(RuntimeError):
            self.install(device)
        self.assertNotIn(("-w",), device.calls)
        self.assertNotIn(("reboot",), device.calls)
        self.assertFalse(any("vbmeta_a" in c for c in device.calls))

    def test_all_sizes_validated_before_any_resize(self):
        device = Device(self.release, {"partition-size:product_a": "invalid"})
        with self.assertRaises(ValueError):
            self.install(device)
        self.assertFalse(any("resize-logical-partition" in c for c in device.calls))

    def test_resize_frees_space_before_growing(self):
        images = self.release["images"]
        device = Device(self.release, {
            "partition-size:system_a": hex(images[0]["size"] - 4096),
            "partition-size:product_a": hex(images[2]["size"] + 4096),
        })
        self.install(device)
        resizes = [c[1] for c in device.calls if c[0] == "resize-logical-partition"]
        self.assertEqual(resizes, ["product_a", "system_a"])

    def test_corrupt_same_size_image_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            (path / "system.img").write_bytes(b"bad")
            release = {"images": [{"file": "system.img", "size": 3,
                                   "sha256": hashlib.sha256(b"yes").hexdigest()}]}
            with self.assertRaisesRegex(ValueError, "Checksum mismatch"):
                flash.verify_images(release, path)

    def test_verify_only_never_constructs_a_usb_client(self):
        with patch.object(flash.sys, "argv", ["flash.py", "--verify-only"]), \
             patch.object(flash, "verify_images"), patch.object(flash, "Fastboot") as usb:
            flash.main()
        usb.assert_not_called()

    def test_path_traversal_manifest_rejected(self):
        release = copy.deepcopy(self.release)
        release["images"][0]["file"] = "../system.img"
        with tempfile.TemporaryDirectory() as tmp:
            import json
            root = Path(tmp)
            (root / "release.json").write_text(json.dumps(release))
            with self.assertRaises(ValueError):
                flash.load_release(root)


if __name__ == "__main__":
    unittest.main()
