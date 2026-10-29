"""Tiny PDFs built in pure Python, for tests that need a real one (no PDF writer is a
dependency of this service). `encrypted_pdf` uses the PDF standard security handler
(RC4, 40-bit, revision 2), so PDFium asks for the password exactly as it does for a
locked PDF from a scanner or Acrobat."""

import hashlib
import os
import struct

# The 32-byte padding string from the PDF specification (7.6.3.3).
_PAD = bytes.fromhex("28BF4E5E4E758A4164004E56FFFA01082E2E00B6D0683E802F0CA9FE6453697A")
_PERMISSIONS = -44  # print + copy allowed; the value only has to be stored and hashed


def _padded(password: str) -> bytes:
    return (password.encode("latin-1") + _PAD)[:32]


def _rc4(key: bytes, data: bytes) -> bytes:
    s = list(range(256))
    j = 0
    for i in range(256):
        j = (j + s[i] + key[i % len(key)]) % 256
        s[i], s[j] = s[j], s[i]
    out = bytearray()
    i = j = 0
    for byte in data:
        i = (i + 1) % 256
        j = (j + s[i]) % 256
        s[i], s[j] = s[j], s[i]
        out.append(byte ^ s[(s[i] + s[j]) % 256])
    return bytes(out)


def _build(objects: list[bytes], trailer_extra: bytes) -> bytes:
    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % number + body + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    for offset in offsets:
        out += b"%010d 00000 n \n" % offset
    out += (
        b"trailer\n<< /Size %d /Root 1 0 R " % (len(objects) + 1)
        + trailer_extra
        + b" >>\n"
    )
    out += b"startxref\n%d\n%%%%EOF\n" % xref
    return bytes(out)


_PAGE_OBJECTS = [
    b"<< /Type /Catalog /Pages 2 0 R >>",
    b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
    b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] >>",
]


def blank_pdf() -> bytes:
    """A valid one-page PDF with an empty page."""
    return _build(list(_PAGE_OBJECTS), b"")


def encrypted_pdf(user: str = "secret", owner: str = "owner") -> bytes:
    """A one-page PDF that opens only with the `user` password."""
    file_id = os.urandom(16)
    owner_value = _rc4(hashlib.md5(_padded(owner)).digest()[:5], _padded(user))
    key = hashlib.md5(
        _padded(user) + owner_value + struct.pack("<i", _PERMISSIONS) + file_id
    ).digest()[:5]
    user_value = _rc4(key, _PAD)
    encrypt = b"<< /Filter /Standard /V 1 /R 2 /Length 40 /O <%s> /U <%s> /P %d >>" % (
        owner_value.hex().encode(),
        user_value.hex().encode(),
        _PERMISSIONS,
    )
    trailer = b"/Encrypt 4 0 R /ID [<%s> <%s>]" % (
        file_id.hex().encode(),
        file_id.hex().encode(),
    )
    # The page objects hold no strings or streams, so nothing else needs encrypting.
    return _build([*_PAGE_OBJECTS, encrypt], trailer)
