import argparse
import hashlib
import pathlib
import sys
import time

import nand_tools as nt

# Dumps the whole NAND in BootMii format (raw NAND + keys.bin appended) and checks that it
# is coherent with the console keys and with a reference backup.
# Usage: python ./bootmii_backup.py -P"COM10"

parser = argparse.ArgumentParser(description="BootMii style NAND backup")
parser.add_argument('-P', dest='port', required=True, help="serial port of the Pico")
parser.add_argument('-k', dest='keys', default='nand_backup/keys.bin', help="BootMii keys.bin to append")
parser.add_argument('-r', dest='reference', default='nand_backup/nand.bin',
                    help="reference BootMii nand.bin to compare with ('' to skip)")
args = parser.parse_args()

def fail(message):
    print("ERROR: " + message)
    sys.exit(1)

try:
    keys = nt.load_keys(args.keys)
    reference = None
    if args.reference:
        reference = nt.read_file(args.reference, "reference image")
        if len(reference) != nt.BOOTMII_SIZE:
            fail(F"{args.reference} is not a BootMii nand.bin ({len(reference)} bytes)")
    ser = nt.open_serial(args.port)
except nt.NandError as e:
    fail(str(e))

pathlib.Path("bootmii_backup").mkdir(exist_ok=True)
filename = F'bootmii_backup/nand-bootmii-{time.time()}.bin'
log = open(filename + '_log.txt', 'w')

def out(line):
    print(line)
    log.write(line + "\n")
    log.flush()

start_time = time.time()

try:
    out(F"NAND ID: {nt.check_id(ser)}")
    out(F"Dumping {nt.BLOCK_COUNT} blocks to {filename}")

    nand = bytearray()
    for block in range(nt.BLOCK_COUNT):
        block_time = time.time()

        # each block is checked against the SHA256 computed by the Pico on a second, independent read
        chip_sha = nt.chip_block_sha(ser, block)
        for attempt in range(3):
            data = b''.join(nt.read_page(ser, block * nt.PAGE_COUNT + pg) for pg in range(nt.PAGE_COUNT))
            if hashlib.sha256(data).hexdigest() == chip_sha:
                break
            out(F"block {block}: read mismatch, retrying")
            chip_sha = nt.chip_block_sha(ser, block)
        else:
            out(F"WARNING: block {block} could not be read consistently")
        nand += data
        print(F"block {block}/{nt.BLOCK_COUNT - 1} read ({len(nand) / 1E6:.1f} MB), {time.time() - block_time:.2f} s")

except nt.NandError as e:
    out(F"ERROR: {e}")
    out("Dump interrupted, nothing written.")
    log.close()
    sys.exit(1)
finally:
    ser.close()

with open(filename, 'wb') as f:
    f.write(nand)
    f.write(keys)

out(F"Dump completed in {(time.time() - start_time) / 60:.1f} minutes.")
out(F"Written {filename} ({len(nand) + len(keys)} bytes, BootMii format)")
out("")
out("=====COHERENCE CHECK=====")
if nt.analyze(nand, keys, reference, out):
    out("RESULT: the NAND belongs to the console of keys.bin.")
else:
    out("RESULT: WARNING, no superblock HMAC matches keys.bin: NAND and keys are not coherent!")
log.close()
