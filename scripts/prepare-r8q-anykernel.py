#!/usr/bin/env python3
"""Add the hardware-bound r8q port fallback to the tested AK3 template."""
import argparse
import hashlib
from pathlib import Path

EXPECTED_UPDATE_BINARY_SHA256 = 'cf3ebe7183d5e3f25e9215cde7ef9dd956e836232a70f2a671891ab4889c7e7d'
MARKER = '  # NotKernel r8q hardware fallback v1\n'
ANCHOR = '  if [ ! "$match" ]; then\n    abort " " "Unsupported device. Aborting...";\n  fi;\n'
FALLBACK = '''  # NotKernel r8q hardware fallback v1
  if [ ! "$match" ] && [ "$(file_getprop anykernel.sh device.name1)" = r8q ]; then
    if [ -r tools/r8q-devicecheck.sh ]; then
      . tools/r8q-devicecheck.sh;
      if r8q_port_devicecheck; then
        match=1;
      fi;
    fi;
  fi;
'''


def prepare(directory):
    directory = Path(directory)
    config = (directory / 'anykernel.sh').read_text(encoding='utf-8')
    if '\ndo.devicecheck=1\n' not in config or '\ndevice.name1=r8q\n' not in config:
        raise ValueError('Expected r8q template with device checking enabled')
    target = directory / 'META-INF/com/google/android/update-binary'
    data = target.read_bytes()
    text = data.decode('utf-8')
    if MARKER in text:
        if text.count(FALLBACK) != 1:
            raise ValueError('Conflicting existing r8q device fallback')
        original = text.replace(FALLBACK, '', 1).encode('utf-8')
    else:
        original = data
    if hashlib.sha256(original).hexdigest() != EXPECTED_UPDATE_BINARY_SHA256:
        raise ValueError('Untested AnyKernel update-binary; use AK3_COMMIT=88a81141d54934af9f8407be913c21aed5f51026')
    if original.decode('utf-8').count(ANCHOR) != 1:
        raise ValueError('Unique AnyKernel device rejection gate missing')
    helper = Path(__file__).with_name('anykernel') / 'r8q-devicecheck.sh'
    destination = directory / 'tools/r8q-devicecheck.sh'
    if destination.exists() and destination.read_bytes() != helper.read_bytes():
        raise ValueError('Existing r8q helper differs; refusing to replace it')
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(helper.read_bytes())
    if MARKER not in text:
        target.write_bytes(text.replace(ANCHOR, FALLBACK + ANCHOR, 1).encode('utf-8'))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    args = parser.parse_args()
    try:
        prepare(args.directory)
    except (OSError, UnicodeError, ValueError) as error:
        parser.exit(1, str(error) + '\n')
