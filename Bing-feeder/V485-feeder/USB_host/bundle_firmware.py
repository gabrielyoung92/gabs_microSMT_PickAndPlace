#!/usr/bin/env python3
"""Package one universal V485 application for the dashboard; never opens hardware.

Original MicroSMT designs retain credit. Local host integration by Gab.
"""
import argparse
import base64
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile

PROJECT = Path(__file__).resolve().parents[1] / 'CODE_feeder'
sys.path.insert(0, str(PROJECT / 'tools'))
from rs485_upload import APP_MAX, inspect_image

BUNDLE = Path(__file__).with_name('firmware.json')


def read_bundle(path=BUNDLE):
    """Read and verify one atomic bundle; return metadata and exact image bytes."""
    with Path(path).open('rb') as source:
        raw = source.read(APP_MAX * 2 + 1)
    if len(raw) > APP_MAX * 2:
        raise ValueError('Firmware bundle is oversized')
    value = json.loads(raw)
    if not isinstance(value, dict): raise ValueError('Invalid firmware bundle')
    image = base64.b64decode(value.pop('image_base64'), validate=True)
    variant, size, checksum = inspect_image(image)
    digest = hashlib.sha256(image).hexdigest()
    if (value.get('variant'), value.get('bytes'), value.get('crc32'), value.get('sha256')) != (variant, size, f'{checksum:08X}', digest):
        raise ValueError('Firmware bundle checksum or metadata mismatch')
    if not re.fullmatch(r'[0-9A-Za-z][0-9A-Za-z.+_-]{0,63}', value.get('version', '')):
        raise ValueError('Firmware bundle has no valid version')
    return value, image


def package(image_path, output=BUNDLE):
    image = Path(image_path).read_bytes()
    variant, size, checksum = inspect_image(image)
    version = re.search(r'^#define FIRMWARE_VERSION "([^"]+)"',
                        (PROJECT / 'src/config.h').read_text(), re.MULTILINE).group(1)
    value = dict(version=version, variant=variant, bytes=size, crc32=f'{checksum:08X}',
                 sha256=hashlib.sha256(image).hexdigest(),
                 built_at=datetime.fromtimestamp(Path(image_path).stat().st_mtime, timezone.utc).isoformat(),
                 image_base64=base64.b64encode(image).decode('ascii'))
    output = Path(output)
    # Metadata and image travel together; a reader sees the old or new bundle.
    fd, temporary = tempfile.mkstemp(prefix='.firmware-', dir=output.parent)
    try:
        with os.fdopen(fd, 'w') as stream:
            json.dump(value, stream, indent=2)
            stream.write('\n')
        read_bundle(temporary)
        os.chmod(temporary, 0o644)
        os.replace(temporary, output)
    finally:
        if os.path.exists(temporary): os.unlink(temporary)
    print(f'Dashboard firmware: {version}, {size} bytes, CRC32 {checksum:08X}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image', type=Path, default=PROJECT / '.pio/build/v485/firmware.bin')
    parser.add_argument('--output', type=Path, default=BUNDLE)
    args = parser.parse_args()
    package(args.image, args.output)
