import serial
import time
import pathlib
import console_commands as cc
import sys

# Scans the bad block markers (first spare byte of pages 0 and 1 of every block).
# Usage: python ./bad_blocks.py -P"COM10" [./nand/nand.bin]
# If a NAND image is given, its bad block map is compared with the chip's one.

PAGE_COUNT = 64
PAGE_SIZE = 2112
DATA_SIZE = 2048
BLOCK_COUNT = 4096
BLOCK_SIZE = PAGE_SIZE * PAGE_COUNT
MARKER_PAGES = (0, 1)

BYTES_START = (cc.BYTES_START + "\r\n").encode()

serial_port = ""
image_file = ""

for arg in sys.argv[1:]:
    if arg.startswith('-P'):
        serial_port = arg[2:]
    else:
        image_file = arg

if not serial_port:
    print("ERROR: No serial port given")
    quit()

if image_file and not pathlib.Path(image_file).is_file():
    print(f"ERROR: NAND image {image_file} does not exist")
    quit()


# Wii NAND ECC: 4 bytes for each 512 byte sector, stored at spare offset 0x30
def parity(x):
    return bin(x).count('1') & 1

ECC_MASKS = []
for j in range(9):
    m = 0
    for i in range(512):
        if (i >> j) & 1:
            m |= 0xff << (8 * (511 - i))
    ECC_MASKS.append(m)

def xor_bytes(v):
    s = 2048
    while s >= 8:
        v = (v >> s) ^ (v & ((1 << s) - 1))
        s //= 2
    return v

def calc_ecc(data):
    v = int.from_bytes(data, 'big')
    x_all = xor_bytes(v)
    a = [[0, 0] for _ in range(12)]
    for j in range(9):
        odd = xor_bytes(v & ECC_MASKS[j])
        a[3 + j] = [x_all ^ odd, odd]
    x = a[3][0] ^ a[3][1]
    a[0] = [x & 0x55, x & 0xaa]
    a[1] = [x & 0x33, x & 0xcc]
    a[2] = [x & 0x0f, x & 0xf0]
    a0 = a1 = 0
    for j in range(12):
        a0 |= parity(a[j][0]) << j
        a1 |= parity(a[j][1]) << j
    return bytes([a0 & 0xff, a0 >> 8, a1 & 0xff, a1 >> 8])

def ecc_ok(page, shift):
    # shift = -1: page read with its first byte missing (known read glitch)
    sectors = range(4) if shift == 0 else range(1, 4)
    for k in sectors:
        start = k * 512 + shift
        stored = page[DATA_SIZE + shift + 0x30 + 4 * k : DATA_SIZE + shift + 0x34 + 4 * k]
        if calc_ecc(page[start : start + 512]) != stored:
            return False
    return True


ser = serial.Serial(serial_port, 115200, timeout=3, write_timeout=3)

def read_page(addr):
    payload = '&{:X}'.format(addr) + cc.READ_PAGE + cc.MESSAGE_END + '\r'
    ser.write(payload.encode())
    start = time.time()
    while time.time() - start <= 10:
        if ser.readline() == BYTES_START:
            return ser.read(PAGE_SIZE)
    print("Timeout error. Exiting!")
    quit()

def page_marker(page):
    """Returns (marker, note). marker is the real first spare byte, or None if unknown."""
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

for block in range(BLOCK_COUNT):
    if block % 256 == 0:
        print(f"scanning block {block}...")

    notes = []
    markers = []
    for pg in MARKER_PAGES:
        page = read_page(block * PAGE_COUNT + pg)
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
