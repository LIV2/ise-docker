import hashlib
import importlib.util
import os
from pathlib import Path
import struct
import unittest


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("patcher", ROOT / "tools/patch-iostreams.py")
patcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(patcher)


class InputTests(unittest.TestCase):
    def test_unknown_library_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "unsupported input SHA-256"):
            patcher.patch(b"not the supported vendor library")


@unittest.skipUnless(os.environ.get("ISE_TEST_LIBRARY"), "requires local vendor library")
class VendorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original = Path(os.environ["ISE_TEST_LIBRARY"]).read_bytes()
        cls.result = patcher.patch(cls.original)

    def test_matches_runtime_tested_binary(self):
        self.assertEqual(
            hashlib.sha256(self.result).hexdigest(),
            "c36110fd6d5c826e9397070c33e7a196623554b1fa0b3caf923a3f4bb1c16772",
        )

    def test_first_check_and_encrypted_payload_are_unchanged(self):
        # Walk the vendor's actual initial checksum/decryption range table.
        # Changes must not affect any input byte or the expected checksum.
        offset = 0xA3187C
        while True:
            address, length = struct.unpack_from("<II", self.original, offset)
            if address == 0xFFFFFFFF:
                break
            file_offset = address - 0x200000 if 0x402000 <= address < 0x42A0E8 else address
            self.assertEqual(
                self.original[file_offset:file_offset + length],
                self.result[file_offset:file_offset + length],
            )
            offset += 8
        self.assertEqual(self.original[0xA31878:offset + 4], self.result[0xA31878:offset + 4])

    def test_second_check_still_detects_a_changed_instruction(self):
        expected = patcher.product(self.original)
        self.assertEqual(patcher.product(self.result), expected)
        corrupted = bytearray(self.result)
        corrupted[0xA47320] ^= 2
        self.assertNotEqual(patcher.product(corrupted), expected)

    def test_map_checks_and_rolling_continuation_are_preserved(self):
        self.assertEqual(patcher.xor_checksum(self.original), 0x7630E03D)
        self.assertEqual(patcher.xor_checksum(self.result), 0x7630E03D)
        self.assertEqual(patcher.rolling_state(self.original), (0xD31EA9C7, 23))
        self.assertEqual(patcher.rolling_state(self.result), (0xD31EA9C7, 23))
        corrupted = bytearray(self.result)
        corrupted[0xA47320] ^= 2
        self.assertNotEqual(patcher.xor_checksum(corrupted), 0x7630E03D)
        self.assertNotEqual(patcher.rolling_state(corrupted), (0xD31EA9C7, 23))

    def test_protected_hdl_rolling_continuation_is_preserved(self):
        expected = (0x8499ADEF, 27)
        self.assertEqual(patcher.hdl_rolling_state(self.original), expected)
        self.assertEqual(patcher.hdl_rolling_state(self.result), expected)
        corrupted = bytearray(self.result)
        corrupted[0xA472E8] ^= 1
        self.assertNotEqual(patcher.hdl_rolling_state(corrupted), expected)

    def test_balance_bytes_are_skipped_by_equivalent_jumps(self):
        for offset, replacement in patcher.BALANCED_JUMPS:
            end = offset + len(replacement)
            self.assertEqual(self.original[offset:end],
                             bytes.fromhex("e900000000") * (len(replacement) // 5))
            self.assertEqual(self.result[offset], 0xEB)
            self.assertEqual(offset + 2 + self.result[offset + 1], end)

    def test_rejects_double_patch_and_corrupt_input(self):
        for data in (self.result, self.original[:-1] + b"x"):
            with self.assertRaisesRegex(ValueError, "unsupported input SHA-256"):
                patcher.patch(data)

    def test_scratch_initializers_are_file_backed_without_moving_bss(self):
        phoff = struct.unpack_from("<Q", self.result, 32)[0]
        segment = struct.unpack_from("<IIQQQQQQ", self.result, phoff + 56)
        self.assertEqual(segment, (1, 6, 0x202000, 0x402000, 0x402000,
                                   0x25EDC, 0x280E8, 0x200000))
        self.assertEqual(self.result[0x227ED4:0x227EDC],
                         self.original[0xA46E68:0xA46E70])


if __name__ == "__main__":
    unittest.main()
