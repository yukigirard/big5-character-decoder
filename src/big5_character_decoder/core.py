"""Big5 (Traditional Chinese) decoder and encoder using only the standard library.

CPython's ``codecs`` module ships a Big5 codec, but its behavior around the
unassigned lead-byte ranges (0x81-0x8D, 0x8E-0xA0) and the undecodable gap
at 0x8140-0x817E differs by Python version. This module provides a single,
version-independent surface so tests and consumers see the same errors on every
supported Python.

Scope and the one decision that matters
---------------------------------------
Big5 is a lead/trail byte encoding. A lead byte in 0x81..0xFE is followed by
a trail byte in 0x40..0x7E or 0xA1..0xFE. Two ranges of lead bytes are
**unassigned** by the 1984 standard and by every common table:

    0x81-0x8D   (``UNASSIGNED_LEAD_RANGES``)
    0x8E-0xA0   (``UNASSIGNED_LEAD_RANGES``)

The brief says "Big5 character encoding standard". Two interpretations are
reasonable:

  (a) treat bytes in those ranges as errors (strict, spec-faithful), or
  (b) fall back to the UDA (User Defined Area) at U+E000+, as some
      vendor codecs do.

This library picks **(a)** and tests it. Bytes whose lead byte is in an
unassigned range raise ``Big5DecodeError``. If you need UDA fallback, this is
the wrong library.

The codec used for the actual code-point mapping is Python's built-in ``big5``
via ``codecs.lookup``. We wrap it so that the only behavior we own -- which
bytes are rejected up front, and what exception type is raised -- is stable.
"""

from __future__ import annotations

import codecs
from typing import List, Tuple, Union

__all__ = [
    "Big5Decoder",
    "Big5Encoder",
    "Big5DecodeError",
    "Big5EncodeError",
    "UNASSIGNED_LEAD_RANGES",
]


# Lead-byte ranges that the Big5 standard leaves unassigned. A sequence whose
# lead byte falls in any of these ranges is rejected before we even consult the
# codec table. We pin this as data so the behavior is identical across Python
# versions even if the bundled codec table changes.
UNASSIGNED_LEAD_RANGES: Tuple[Tuple[int, int], ...] = (
    (0x81, 0x8D),
    (0x8E, 0xA0),
)


def _is_unassigned_lead(lead: int) -> bool:
    """Return True if ``lead`` is a Big5-unassigned lead byte."""
    return any(lo <= lead <= hi for lo, hi in UNASSIGNED_LEAD_RANGES)


def _is_valid_trail(trail: int) -> bool:
    """Return True if ``trail`` is a legal Big5 trail byte (0x40-0x7E, 0xA1-0xFE)."""
    return (0x40 <= trail <= 0x7E) or (0xA1 <= trail <= 0xFE)


class Big5DecodeError(ValueError):
    """Raised when a byte sequence cannot be decoded as Big5.

    Carries the offending byte sequence, the byte offset within the input
    where decoding stopped, and the reason. Subclassing ValueError keeps
    compatibility with code that catches the stdlib's UnicodeDecodeError
    by its ValueError parent.
    """

    def __init__(self, data: bytes, start: int, end: int, reason: str) -> None:
        self.data = data
        self.start = start
        self.end = end
        self.reason = reason
        # Reproduce the useful slice of the input that the stdlib error carries.
        bad = data[start:end]
        super().__init__(
            f"{reason}: bytes {start}:{end} of {data!r} -> {bad!r}"
        )


class Big5EncodeError(ValueError):
    """Raised when a character cannot be encoded in Big5."""

    def __init__(self, text: str, index: int, reason: str) -> None:
        self.text = text
        self.index = index
        self.reason = reason
        ch = text[index] if 0 <= index < len(text) else ""
        super().__init__(f"{reason}: character at index {index} -> {ch!r}")


class Big5Decoder:
    """Decode Big5 bytes to ``str``.

    The decoder walks the input byte by byte. ASCII (0x00-0x7F) is passed
    through. A lead byte in an unassigned range is an error. A lead byte with
    a valid trail byte is decoded via Python's bundled Big5 table; if the
    two-byte sequence has no mapping, that is also an error.

    errors="strict" raises on the first bad byte. errors="replace" substitutes
    U+FFFD for each bad lead byte (and its trail byte if consumed). We do not
    implement "ignore" because silently dropping bytes from a multibyte
    stream tends to misalign subsequent characters in ways that are hard to
    reason about; callers who want that can post-process.
    """

    def __init__(self, errors: str = "strict") -> None:
        if errors not in ("strict", "replace"):
            raise ValueError(
                f"unsupported errors value {errors!r}; use 'strict' or 'replace'"
            )
        self.errors = errors
        # Look up the codec once. We use it only as the authoritative table;
        # we do our own byte walking so we control which bytes are rejected.
        self._codec = codecs.lookup("big5")

    def decode(self, data: bytes) -> str:
        """Decode ``data`` (Big5 bytes) into a ``str``.

        Raises ``Big5DecodeError`` in strict mode on the first invalid byte.
        """
        if isinstance(data, bytearray):
            data = bytes(data)
        if not isinstance(data, (bytes, bytearray)):
            raise TypeError(
                f"Big5Decoder.decode expects bytes, got {type(data).__name__}"
            )

        out: List[str] = []
        i = 0
        n = len(data)
        while i < n:
            b = data[i]
            # ASCII fast path: 0x00-0x7F are single-byte in Big5 (it is
            # ASCII-compatible by design, unlike e.g. UTF-16).
            if b <= 0x7F:
                out.append(chr(b))
                i += 1
                continue

            # Lead byte ranges that Big5 leaves unassigned. Reject up front
            # rather than letting the codec table's per-version quirks leak.
            if _is_unassigned_lead(b):
                if self.errors == "strict":
                    raise Big5DecodeError(
                        data, i, i + 1, "unassigned lead byte range"
                    )
                out.append("\ufffd")
                i += 1
                continue

            # Two-byte sequence: need a trail byte.
            if i + 1 >= n:
                if self.errors == "strict":
                    raise Big5DecodeError(
                        data, i, i + 1, "truncated two-byte sequence"
                    )
                out.append("\ufffd")
                i += 1
                continue

            trail = data[i + 1]
            if not _is_valid_trail(trail):
                # The trail byte is out of range. The lead byte is valid,
                # so we consume only the lead byte and let the trail byte be
                # re-examined on the next loop iteration (it may be ASCII or
                # another lead byte). This matches the stdlib codec's
                # resync behavior for malformed trails.
                if self.errors == "strict":
                    raise Big5DecodeError(
                        data, i, i + 1, "invalid trail byte for lead byte"
                    )
                out.append("\ufffd")
                i += 1
                continue

            pair = data[i : i + 2]
            try:
                decoded = self._codec.decode(pair, "strict")[0]
            except UnicodeDecodeError as exc:
                # The pair is structurally valid but has no code point.
                if self.errors == "strict":
                    raise Big5DecodeError(
                        data, i, i + 2, "unmapped two-byte sequence"
                    ) from exc
                out.append("\ufffd")
                i += 2
                continue

            out.append(decoded)
            i += 2

        return "".join(out)


class Big5Encoder:
    """Encode ``str`` to Big5 bytes.

    ASCII characters (U+0000-U+007F) encode as their single-byte form. Other
    characters are looked up in Python's bundled Big5 table; any character
    without a mapping raises ``Big5EncodeError`` in strict mode or becomes
    b'?' in replace mode.
    """

    def __init__(self, errors: str = "strict") -> None:
        if errors not in ("strict", "replace"):
            raise ValueError(
                f"unsupported errors value {errors!r}; use 'strict' or 'replace'"
            )
        self.errors = errors
        self._codec = codecs.lookup("big5")

    def encode(self, text: str) -> bytes:
        """Encode ``text`` into Big5 bytes."""
        if not isinstance(text, str):
            raise TypeError(
                f"Big5Encoder.encode expects str, got {type(text).__name__}"
            )

        out = bytearray()
        for idx, ch in enumerate(text):
            cp = ord(ch)
            if cp <= 0x7F:
                out.append(cp)
                continue
            try:
                encoded = self._codec.encode(ch, "strict")[0]
            except UnicodeEncodeError as exc:
                if self.errors == "strict":
                    raise Big5EncodeError(
                        text, idx, "character not in Big5"
                    ) from exc
                out.extend(b"?")
                continue
            out.extend(encoded)
        return bytes(out)
