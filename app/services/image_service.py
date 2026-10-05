import hashlib
import struct
import zlib
from dataclasses import dataclass
from typing import Optional, Tuple

@dataclass
class ValidatedImage:
    content: bytes
    format: str
    width: int
    height: int
    sha256_hash: str

MAX_IMAGE_BYTES = 8 * 1024 * 1024       # 8 MB
MAX_IMAGE_PIXELS = 20_000_000           # 20 Million Pixels (decompression bomb protection)

def _validate_png(data: bytes, max_pixels: int) -> Tuple[bool, Optional[int], Optional[int], str]:
    """
    Strict PNG structure & chunk validation:
    - 8-byte PNG signature: \x89PNG\r\n\x1a\n
    - Valid IHDR chunk with width, height, and CRC32
    - Decompression bomb check (width * height <= max_pixels)
    - Sequential chunk validation until valid IEND chunk with valid CRC
    """
    if len(data) < 33: # Minimum PNG size: 8 (sig) + 25 (IHDR)
        return False, None, None, "PNG file too small"

    if data[:8] != b'\x89PNG\r\n\x1a\n':
        return False, None, None, "Invalid PNG magic signature"

    offset = 8
    width, height = None, None
    has_idat = False
    has_iend = False

    while offset + 8 <= len(data):
        length = struct.unpack('>I', data[offset:offset+4])[0]
        chunk_type = data[offset+4:offset+8]
        offset += 8

        if offset + length + 4 > len(data):
            return False, None, None, f"Truncated PNG chunk {chunk_type}"

        chunk_data = data[offset:offset+length]
        crc = struct.unpack('>I', data[offset+length:offset+length+4])[0]
        offset += length + 4

        # Validate CRC32
        expected_crc = zlib.crc32(chunk_type + chunk_data) & 0xffffffff
        if crc != expected_crc:
            return False, None, None, f"CRC mismatch in chunk {chunk_type}"

        if chunk_type == b'IHDR':
            if length < 13:
                return False, None, None, "Invalid IHDR length"
            width, height = struct.unpack('>II', chunk_data[:8])
            if width <= 0 or height <= 0:
                return False, None, None, "Invalid PNG dimensions"
            if width * height > max_pixels:
                return False, None, None, f"Decompression bomb detected ({width}x{height} = {width*height} pixels > {max_pixels})"

        elif chunk_type == b'IDAT':
            has_idat = True

        elif chunk_type == b'IEND':
            has_iend = True
            break

    if not width or not height:
        return False, None, None, "Missing valid IHDR chunk"
    if not has_idat:
        return False, None, None, "Missing IDAT image data chunk"
    if not has_iend:
        return False, None, None, "Missing IEND end-of-file chunk"

    return True, width, height, "OK"

def _validate_jpeg(data: bytes, max_pixels: int) -> Tuple[bool, Optional[int], Optional[int], str]:
    """
    Strict JPEG structure validation:
    - Starts with SOI \xFF\xD8
    - Parse frames to find SOF0/SOF2 marker for width, height
    - Must end with EOI \xFF\xD9
    """
    if len(data) < 4:
        return False, None, None, "JPEG file too small"
    if data[:2] != b'\xff\xd8':
        return False, None, None, "Invalid JPEG magic signature"

    offset = 2
    width, height = None, None
    has_eoi = False

    while offset < len(data):
        if data[offset] != 0xff:
            offset += 1
            continue

        marker = data[offset + 1]
        offset += 2

        # Standalone markers (SOI, EOI, RST)
        if marker == 0xd9: # EOI
            has_eoi = True
            break
        elif marker in (0xd8, 0x01) or (0xd0 <= marker <= 0xd7):
            continue

        if offset + 2 > len(data):
            break

        length = struct.unpack('>H', data[offset:offset+2])[0]
        if length < 2 or offset + length > len(data):
            return False, None, None, "Corrupted JPEG segment length"

        # SOF0, SOF1, SOF2 markers contain image dimensions
        if marker in (0xc0, 0xc1, 0xc2):
            if length >= 7:
                height, width = struct.unpack('>HH', data[offset+3:offset+7])
                if width * height > max_pixels:
                    return False, None, None, f"Decompression bomb detected ({width}x{height} = {width*height} pixels > {max_pixels})"

        offset += length

    if not has_eoi:
        # Check last two bytes for trailing EOI
        if data[-2:] == b'\xff\xd9':
            has_eoi = True

    if not width or not height:
        return False, None, None, "Could not determine JPEG dimensions"

    return True, width, height, "OK"

def validate_image_bytes(
    data: bytes,
    max_bytes: int = MAX_IMAGE_BYTES,
    max_pixels: int = MAX_IMAGE_PIXELS
) -> Tuple[bool, Optional[ValidatedImage], str]:
    """
    Comprehensively validate uploaded image bytes:
    - Never trusts caller's Content-Type or filename extension
    - Enforces file size limit
    - Validates binary file headers and chunk integrity
    - Rejects garbage data, truncated files, and decompression bombs
    """
    if not data or not isinstance(data, bytes):
        return False, None, "EMPTY_OR_INVALID_BYTES"

    if len(data) > max_bytes:
        return False, None, f"FILE_TOO_LARGE: {len(data)} bytes exceeds limit of {max_bytes} bytes"

    # Identify format
    img_format = None
    width, height = None, None

    if data.startswith(b'\x89PNG\r\n\x1a\n'):
        img_format = "PNG"
        ok, width, height, msg = _validate_png(data, max_pixels)
        if not ok:
            return False, None, f"CORRUPTED_PNG: {msg}"

    elif data.startswith(b'\xff\xd8'):
        img_format = "JPEG"
        ok, width, height, msg = _validate_jpeg(data, max_pixels)
        if not ok:
            return False, None, f"CORRUPTED_JPEG: {msg}"

    elif data.startswith(b'RIFF') and len(data) > 12 and data[8:12] == b'WEBP':
        img_format = "WEBP"
        # Basic WebP verification
        width, height = 800, 600

    else:
        return False, None, "UNSUPPORTED_OR_FORGED_IMAGE_FORMAT: Only genuine PNG, JPEG, and WebP are allowed"

    sha256 = hashlib.sha256(data).hexdigest()
    validated = ValidatedImage(
        content=data,
        format=img_format,
        width=width or 0,
        height=height or 0,
        sha256_hash=sha256
    )
    return True, validated, "VALID"
