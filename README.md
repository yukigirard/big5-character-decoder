# Big5 Character Decoder

Decodes and encodes Traditional Chinese text using the Big5 character encoding
standard, with a small, version-independent error surface.

```python
from big5_character_decoder import Big5Decoder, Big5Encoder

decoder = Big5Decoder()                # errors="strict" by default
encoder = Big5Encoder()

text = decoder.decode(b"\xa4\x40")     # -> '\u4e00'  (CJK '一')
bytes_ = encoder.encode("\u4e00")      # -> b'\xa4\x40'

# lenient mode:
Big5Decoder("replace").decode(b"\x81\x40")  # -> '\ufffd@'
```

Exported names: `Big5Decoder`, `Big5Encoder`, `Big5DecodeError`,
`Big5EncodeError`.

## Why this exists

CPython ships a Big5 codec, but its handling of the unassigned lead-byte
ranges (0x81-0x8D, 0x8E-0xA0) and malformed trails varies by Python version.
This library wraps the bundled table but walks bytes itself, so the bytes
that raise and the exception type raised are stable across versions. The
trade-off is that we re-implement the byte walker; the actual code-point
table still comes from the stdlib, so we do not control its contents.

## The awkward edge

Big5 leaves the lead-byte ranges 0x81-0x8D and 0x8E-0xA0 unassigned. Some
vendor codecs map these into the User Defined Area (UDA, U+E000+). This
library does **not**; bytes in those ranges are errors in strict mode and
U+FFFD in replace mode. If you need UDA round-tripping, this is not the
right tool.

Trail bytes must be in 0x40-0x7E or 0xA1-0xFE. A structurally valid lead
byte followed by an invalid trail byte raises in strict mode; in replace
mode the lead byte becomes U+FFFD and the bad trail byte is re-examined on
the next iteration, which usually resyncs cleanly.

## Performance

The window keeps a bounded buffer, so `push` is constant time and memory does not
grow with the length of the stream. `peak` and `trough` are linear in the window
size, which is the trade that keeps `push` cheap.

