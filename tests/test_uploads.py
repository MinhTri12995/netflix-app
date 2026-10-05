import unittest
import struct
import zlib
from app.services.image_service import validate_image_bytes

def _create_minimal_png(width=1, height=1):
    sig = b'\x89PNG\r\n\x1a\n'
    ihdr_data = struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0)
    ihdr_crc = zlib.crc32(b'IHDR' + ihdr_data) & 0xffffffff
    ihdr = struct.pack('>I', 13) + b'IHDR' + ihdr_data + struct.pack('>I', ihdr_crc)

    raw_pixel = b'\x00\xff\x00\x00' * width
    compressed = zlib.compress(b'\x00' + raw_pixel)
    idat_crc = zlib.crc32(b'IDAT' + compressed) & 0xffffffff
    idat = struct.pack('>I', len(compressed)) + b'IDAT' + compressed + struct.pack('>I', idat_crc)

    iend_crc = zlib.crc32(b'IEND') & 0xffffffff
    iend = struct.pack('>I', 0) + b'IEND' + struct.pack('>I', iend_crc)
    return sig + ihdr + idat + iend

class TestUploads(unittest.TestCase):
    def test_valid_png_accepted(self):
        """Legitimate PNG is validated and dimensions parsed."""
        png = _create_minimal_png(10, 20)
        ok, val, msg = validate_image_bytes(png)
        self.assertTrue(ok)
        self.assertEqual(val.format, "PNG")
        self.assertEqual(val.width, 10)
        self.assertEqual(val.height, 20)

    def test_png_header_plus_garbage_rejected(self):
        """F10 Invariant: PNG magic signature followed by garbage bytes must be rejected."""
        fake_png = b'\x89PNG\r\n\x1a\n' + b'This is completely random garbage text and not a real image at all!'
        ok, val, msg = validate_image_bytes(fake_png)
        self.assertFalse(ok)
        self.assertIn("CORRUPTED_PNG", msg)

    def test_decompression_bomb_rejected(self):
        """Image dimensions exceeding MAX_IMAGE_PIXELS (20M pixels) must be rejected."""
        # 10,000 x 5,000 = 50 Million Pixels > 20 Million Pixels
        sig = b'\x89PNG\r\n\x1a\n'
        ihdr_data = struct.pack('>IIBBBBB', 10000, 5000, 8, 2, 0, 0, 0)
        ihdr_crc = zlib.crc32(b'IHDR' + ihdr_data) & 0xffffffff
        ihdr = struct.pack('>I', 13) + b'IHDR' + ihdr_data + struct.pack('>I', ihdr_crc)
        raw_bomb = sig + ihdr + b'garbage'
        ok, val, msg = validate_image_bytes(raw_bomb, max_pixels=20_000_000)
        self.assertFalse(ok)
        self.assertIn("Decompression bomb detected", msg)

    def test_oversized_file_rejected(self):
        """Files exceeding max_bytes limit are rejected."""
        large_bytes = b'A' * 1000
        ok, val, msg = validate_image_bytes(large_bytes, max_bytes=500)
        self.assertFalse(ok)
        self.assertIn("FILE_TOO_LARGE", msg)

    def test_forged_extension_non_image_rejected(self):
        """Executable or text bytes are rejected regardless of claimed extension."""
        text_bytes = b"Hello world, I am a plain text file pretending to be image.png"
        ok, val, msg = validate_image_bytes(text_bytes)
        self.assertFalse(ok)
        self.assertIn("UNSUPPORTED_OR_FORGED_IMAGE_FORMAT", msg)

if __name__ == "__main__":
    unittest.main()
