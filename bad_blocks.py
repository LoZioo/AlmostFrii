import pathlib
import sys
import time

import nand_tools as nt

# Scans the bad block markers (first spare byte of pages 0 and 1 of every block).
# Usage: python ./bad_blocks.py -P"COM10" [nand_backup/nand.bin]
# If a NAND image is given, its bad block map is compared with the chip's one.

PAGE_COUNT = nt.PAGE_COUNT
PAGE_SIZE = nt.PAGE_SIZE
DATA_SIZE = nt.DATA_SIZE
BLOCK_COUNT = nt.BLOCK_COUNT
BLOCK_SIZE = nt.BLOCK_SIZE
MARKER_PAGES = (0, 1)

serial_port = ""
image_file = ""

for arg in sys.argv[1:]:
    if arg.startswith('-P'):
        serial_port = arg[2:]
    else:
        image_file = arg

if not serial_port:
    print("ERROR: No serial port given")
    sys.exit(1)

if image_file and not pathlib.Path(image_file).is_file():
    print(f"ERROR: NAND image {image_file} does not exist")
    sys.exit(1)


def ecc_ok(page, shift):
    # shift = -1: page read with its first byte missing (known read glitch)
    sectors = range(4) if shift == 0 else range(1, 4)
    for k in sectors:
        start = k * 512 + shift
        stored = page[DATA_SIZE + shift + 0x30 + 4 * k : DATA_SIZE + shift + 0x34 + 4 * k]
        if nt.sector_ecc(page[start : start + 512]) != stored:
            return False
    return True


try:
    ser = nt.open_serial(serial_port)
except nt.NandError as e:
    print(f"ERROR: {e}")
    sys.exit(1)

def page_marker(page):
    """Returns (marker, note): marker is the first spare byte as best known, note explains how it was read."""
    if page.count(0xff) == PAGE_SIZE:
        return 0xff, "erased"
    if page[DATA_SIZE] == 0xff:
        return 0xff, ""  # valid pages may hold all-zero data (e.g. Wii superblocks)
    if page.count(0x00) > PAGE_SIZE * 0.9:
        return 0x00, "page all 00"
    if ecc_ok(page, 0):
        return page[DATA_SIZE], "ECC ok"
    if ecc_ok(page, -1):
        return page[DATA_SIZE - 1], "read shifted by 1 byte"
    return page[DATA_SIZE], "ECC mismatch"


pathlib.Path("nand_dumps").mkdir(parents=True, exist_ok=True)
log = open(F'nand_dumps/bad_blocks-{int(time.time())}.txt', 'w')

def out(line):
    print(line)
    log.write(line + "\n")
    log.flush()

start_time = time.time()
bad = {}
suspect = {}

try:
    for block in range(BLOCK_COUNT):
        if block % 256 == 0:
            print(f"scanning block {block}...")

        notes = []
        markers = []
        for pg in MARKER_PAGES:
            page = nt.read_page(ser, block * PAGE_COUNT + pg)
            marker, note = page_marker(page)
            markers.append(marker)
            notes.append(f"page {pg}: marker {marker:02x} {note}".strip())

        if all(m == 0xff for m in markers):
            continue

        # a page of 00, or a non-FF marker confirmed by a valid ECC, is a real bad block marker
        if any(m != 0xff and ("ECC ok" in n or "shifted" in n or "all 00" in n) for m, n in zip(markers, notes)):
            bad[block] = notes
        else:
            suspect[block] = notes
except nt.NandError as e:
    out(f"ERROR: {e}")
    log.close()
    sys.exit(1)
finally:
    ser.close()

out(f"Scan completed in {time.time() - start_time:.1f} seconds.")
out(f"Bad blocks on chip: {len(bad)}")
for block, notes in bad.items():
    out(f"  block {block} (0x{block:X}): " + "; ".join(notes))
out(f"Suspect blocks (non-FF marker, data not verifiable): {len(suspect)}")
for block, notes in suspect.items():
    out(f"  block {block} (0x{block:X}): " + "; ".join(notes))

if image_file:
    image_bad = []
    with open(image_file, 'rb') as f:
        for block in range(BLOCK_COUNT):
            for pg in MARKER_PAGES:
                f.seek(block * BLOCK_SIZE + pg * PAGE_SIZE + DATA_SIZE)
                if f.read(1) != b'\xff':
                    image_bad.append(block)
                    break
    chip_bad = sorted(bad) + sorted(suspect)
    out(f"Bad blocks in image {image_file}: {image_bad}")
    out(f"Bad on chip but not in image: {sorted(set(chip_bad) - set(image_bad))}")
    out(f"Bad in image but not on chip: {sorted(set(image_bad) - set(chip_bad))}")

log.close()
