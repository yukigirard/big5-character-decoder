import unittest

from big5_character_decoder import (
    Big5Decoder,
    Big5Encoder,
    Big5DecodeError,
    Big5EncodeError,
)
from big5_character_decoder.core import UNASSIGNED_LEAD_RANGES


class TestDecoderASCII(unittest.TestCase):
    def test_empty_input(self):
        self.assertEqual(Big5Decoder().decode(b""), "")

    def test_ascii_passthrough(self):
        self.assertEqual(Big5Decoder().decode(b"hello"), "hello")

    def test_ascii_full_range(self):
        # Every byte 0x00-0x7F should map to the corresponding code point.
        data = bytes(range(0x80))
        expected = "".join(chr(b) for b in range(0x80))
        self.assertEqual(Big5Decoder().decode(data), expected)


class TestDecoderHappyPath(unittest.TestCase):
    def test_known_two_byte_sequence(self):
        # 0xA440 is the first character in the Big5 standard (U+4E00, CJK
        # Unified Ideograph '一'). This is a stable, well-known anchor.
        self.assertEqual(Big5Decoder().decode(b"\xa4\x40"), "\u4e00")

    def test_mixed_ascii_and_big5(self):
        # ASCII 'A' then '一' then 'B'.
        data = b"A\xa4\x40B"
        self.assertEqual(Big5Decoder().decode(data), "A\u4e00B")


class TestDecoderUnassigned(unittest.TestCase):
    def test_unassigned_lead_raises_strict(self):
        # 0x81 is in the first unassigned range.
        with self.assertRaises(Big5DecodeError) as ctx:
            Big5Decoder().decode(b"\x81\x40")
        self.assertEqual(ctx.exception.start, 0)
        self.assertEqual(ctx.exception.end, 1)
        self.assertIn("unassigned", ctx.exception.reason)

    def test_unassigned_lead_replace(self):
        # In replace mode the unassigned lead byte becomes U+FFFD and the
        # trail byte 0x40 is reprocessed as ASCII '@'.
        self.assertEqual(
            Big5Decoder("replace").decode(b"\x81\x40"),
            "\ufffd@",
        )

    def test_all_unassigned_leads_strict(self):
        for lo, hi in UNASSIGNED_LEAD_RANGES:
            for lead in range(lo, hi + 1):
                with self.assertRaises(Big5DecodeError):
                    Big5Decoder().decode(bytes([lead, 0x40]))


class TestDecoderMalformed(unittest.TestCase):
    def test_truncated_two_byte_strict(self):
        # Lead byte 0xA4 (valid, assigned) with no trail byte.
        with self.assertRaises(Big5DecodeError) as ctx:
            Big5Decoder().decode(b"\xa4")
        self.assertEqual(ctx.exception.start, 0)
        self.assertIn("truncated", ctx.exception.reason)

    def test_truncated_two_byte_replace(self):
        self.assertEqual(Big5Decoder("replace").decode(b"\xa4"), "\ufffd")

    def test_invalid_trail_byte_strict(self):
        # 0xA4 is a valid lead; 0x80 is not a legal trail byte.
        with self.assertRaises(Big5DecodeError) as ctx:
            Big5Decoder().decode(b"\xa4\x80")
        self.assertEqual(ctx.exception.start, 0)
        self.assertEqual(ctx.exception.end, 1)
        self.assertIn("trail", ctx.exception.reason)

    def test_invalid_trail_byte_replace_resyncs(self):
        # 0xA4 is invalid (bad trail 0x80), so -> U+FFFD. Then 0x80 is a
        # lead byte with no trail -> another U+FFFD in replace mode.
        self.assertEqual(
            Big5Decoder("replace").decode(b"\xa4\x80"),
            "\ufffd\ufffd",
        )

    def test_invalid_trail_then_ascii_resyncs(self):
        # 0xA4 lead with 0x3F trail (0x3F is not a valid trail byte, since
        # valid trails are 0x40-0x7E or 0xA1-0xFE) -> U+FFFD; then 0x3F is
        # ASCII '?' and 0x41 is ASCII 'A'.
        self.assertEqual(
            Big5Decoder("replace").decode(b"\xa4\x3fA"),
            "\ufffd?A",
        )


class TestDecoderTypes(unittest.TestCase):
    def test_bytearray_accepted(self):
        self.assertEqual(Big5Decoder().decode(bytearray(b"hi")), "hi")

    def test_non_bytes_rejected(self):
        with self.assertRaises(TypeError):
            Big5Decoder().decode("hi")  # type: ignore[arg-type]

    def test_bad_errors_value(self):
        with self.assertRaises(ValueError):
            Big5Decoder("ignore")


class TestEncoder(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(Big5Encoder().encode(""), b"")

    def test_ascii(self):
        self.assertEqual(Big5Encoder().encode("hello"), b"hello")

    def test_known_char(self):
        # U+4E00 ('一') round-trips to 0xA440.
        self.assertEqual(Big5Encoder().encode("\u4e00"), b"\xa4\x40")

    def test_unmappable_strict(self):
        # U+1F600 (grinning face emoji) is not in Big5.
        with self.assertRaises(Big5EncodeError) as ctx:
            Big5Encoder().encode("hi \U0001f600")
        self.assertEqual(ctx.exception.index, 3)
        self.assertIn("not in Big5", ctx.exception.reason)

    def test_unmappable_replace(self):
        self.assertEqual(
            Big5Encoder("replace").encode("a\U0001f600b"),
            b"a?b",
        )

    def test_non_str_rejected(self):
        with self.assertRaises(TypeError):
            Big5Encoder().encode(b"hi")  # type: ignore[arg-type]


class TestRoundTrip(unittest.TestCase):
    def test_roundtrip_mixed(self):
        text = "A\u4e00B\u4e8c"
        enc = Big5Encoder().encode(text)
        dec = Big5Decoder().decode(enc)
        self.assertEqual(dec, text)

    def test_roundtrip_ascii_only(self):
        text = "plain ascii 123"
        self.assertEqual(
            Big5Decoder().decode(Big5Encoder().encode(text)),
            text,
        )


if __name__ == "__main__":
    unittest.main()
