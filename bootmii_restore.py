import argparse
import hashlib
import pathlib
import sys
import time

import serial

import nand_tools as nt

# Restores a BootMii nand.bin on the chip: checks the image, erases the chip (bad blocks are
# never erased), writes every page and verifies every block with the SHA256 computed by the Pico.
# Usage: python ./bootmii_restore.py -P"COM10"

parser = argparse.ArgumentParser(description="BootMii style NAND restore")
parser.add_argument('-P', dest='port', required=True, help="serial port of the Pico")
parser.add_argument('-i', dest='image', default='bootmii_restore/nand.bin', help="BootMii nand.bin to restore")
parser.add_argument('-k', dest='keys', default='bootmii_restore/keys.bin',
                    help="console keys.bin (optional if appended to the image)")
args = parser.parse_args()

pathlib.Path("bootmii_restore").mkdir(exist_ok=True)
log = open(F'bootmii_restore/restore-{int(time.time())}_log.txt', 'w')

def out(line):
    print(line)
    log.write(line + "\n")
    log.flush()

def fail(message):
    out("ERROR: " + message)
    log.close()
    sys.exit(1)


# ===== image checks =====

image = pathlib.Path(args.image).read_bytes()
if len(image) not in (nt.NAND_SIZE, nt.BOOTMII_SIZE):
    fail(F"{args.image} has a wrong size ({len(image)} bytes)")
nand = image[:nt.NAND_SIZE]
appended_keys = image[nt.NAND_SIZE:] or None

keys = None
if pathlib.Path(args.keys).is_file():
    keys = nt.load_keys(args.keys)
    if appended_keys is not None and appended_keys != keys:
        fail(F"keys appended to {args.image} differ from {args.keys}: they come from different consoles")
elif appended_keys is not None:
    keys = appended_keys
else:
    fail("no keys: put keys.bin next to the image, or use a nand.bin with keys appended")

out(F"Image: {args.image}")
out("=====IMAGE CHECK=====")
if not nt.analyze(nand, keys, out=out):
    fail("no superblock HMAC matches the console keys: this image does not belong to this console")
image_bad = nt.image_bad_blocks(nand)

ser = serial.Serial(args.port, 115200, timeout=3, write_timeout=3)

try:
    # ===== chip checks =====
    out("")
    out("=====CHIP CHECK=====")
    out(F"NAND ID: {nt.check_id(ser)}")
    chip_bad = nt.chip_bad_blocks(ser)
    out(F"Bad blocks on chip: {chip_bad}")
    if chip_bad != image_bad:
        fail(F"bad blocks of the chip {chip_bad} differ from the image ones {image_bad}")

    print("")
    print("The chip will be ERASED and rewritten with the image.")
    if input("Type YES to continue: ").strip() != "YES":
        fail("aborted by user")

    # ===== erase =====
    out("")
    out("=====ERASE=====")
    skipped, failed = nt.erase_chip(ser)
    out(F"Bad blocks skipped: {skipped}, erase errors: {failed}")
    if failed:
        fail("erase errors, chip not written")
    if skipped != chip_bad:
        fail(F"the firmware skipped blocks {skipped}, expected {chip_bad}")

    # ===== write =====
    out("")
    out("=====WRITE=====")
    start_time = time.time()
    last_time = start_time
    for block in range(nt.BLOCK_COUNT):
        if block % 64 == 0:
            print(F"writing block {block} ({block * nt.BLOCK_SIZE / 1E6:.1f} MB), {time.time() - last_time:.1f} s")
            last_time = time.time()
        if block in image_bad:
            continue
        for pg in range(nt.PAGE_COUNT):
            index = block * nt.PAGE_COUNT + pg
            data = nt.page(nand, index)
            if data != nt.ERASED_PAGE:  # the chip is already erased
                nt.write_page(ser, index, data)
    out(F"Write completed in {(time.time() - start_time) / 60:.1f} minutes.")

    # ===== verify =====
    out("")
    out("=====VERIFY=====")
    mismatches = []
    for block in range(nt.BLOCK_COUNT):
        if block % 512 == 0:
            print(F"verifying block {block}...")
        if block in image_bad:
            continue
        expected = hashlib.sha256(nt.block(nand, block)).hexdigest()
        if nt.chip_block_sha(ser, block) != expected:
            # read again before reporting: a single read glitch is not a write error
            if nt.chip_block_sha(ser, block) != expected:
                mismatches.append(block)
                out(F"block {block}: MISMATCH")

except nt.NandError as e:
    fail(str(e))
finally:
    ser.close()

if mismatches:
    fail(F"{len(mismatches)} blocks differ from the image: {mismatches}")
out(F"RESTORE OK: all {nt.BLOCK_COUNT - len(image_bad)} blocks match the image.")
log.close()
