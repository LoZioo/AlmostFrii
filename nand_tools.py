import hashlib
import hmac
import struct
import time

import console_commands as cc

# Shared helpers for bootmii_backup.py and bootmii_restore.py

PAGE_SIZE = 2112
DATA_SIZE = 2048
PAGE_COUNT = 64
BLOCK_COUNT = 4096
BLOCK_SIZE = PAGE_SIZE * PAGE_COUNT
NAND_SIZE = BLOCK_SIZE * BLOCK_COUNT          # raw NAND with spare areas
KEYS_SIZE = 1024
BOOTMII_SIZE = NAND_SIZE + KEYS_SIZE          # BootMii nand.bin: raw NAND + keys.bin

NAND_ID = "ad dc 10 95"
ERASED_PAGE = b'\xff' * PAGE_SIZE
BYTES_START = (cc.BYTES_START + "\r\n").encode()


class NandError(Exception):
    pass


# ===== serial protocol =====

def command(ser, cmd, addr=None):
    payload = cmd + cc.MESSAGE_END
    if addr is not None:
        payload = '&{:X}'.format(addr) + payload
    ser.write(payload.encode())


def wait_line(ser, prefixes, timeout=3):
    """Reads lines until one starts with one of prefixes. Returns it, or None on timeout."""
    end = time.time() + timeout
    while time.time() < end:
        line = ser.readline().decode('utf-8', errors='replace').strip()
        for prefix in prefixes:
            if line.startswith(prefix):
                return line
    return None


def check_id(ser):
    ser.reset_input_buffer()
    command(ser, cc.NAND_ID)
    line = wait_line(ser, ["ID: "])
    if line is None:
        raise NandError("no answer to ID command")
    chip_id = line[4:].strip()
    if chip_id != NAND_ID:
        raise NandError(F"wrong NAND ID '{chip_id}' (expected '{NAND_ID}'): check wiring")
    return chip_id


def read_page(ser, page):
    ser.write(('&{:X}'.format(page) + cc.READ_PAGE + cc.MESSAGE_END + '\r').encode())
    end = time.time() + 10
    while time.time() < end:
        if ser.readline() == BYTES_START:
            data = ser.read(PAGE_SIZE)
            if len(data) == PAGE_SIZE:
                return data
            break
    raise NandError(F"timeout reading page {page}")


def chip_block_sha(ser, block):
    command(ser, cc.BLOCK_SHA, block)
    line = wait_line(ser, ["SHA: "])
    if line is None:
        raise NandError(F"timeout on SHA256 of block {block}")
    return line[5:].strip()


def chip_bad_blocks(ser, progress=print):
    bad = []
    for block in range(BLOCK_COUNT):
        if block % 512 == 0:
            progress(F"  scanning block {block}...")
        for pg in (0, 1):
            if read_page(ser, block * PAGE_COUNT + pg)[DATA_SIZE] != 0xff:
                bad.append(block)
                break
    return bad


def erase_chip(ser, progress=print):
    """Erases the whole chip (the firmware skips factory bad blocks). Returns (skipped, failed) block lists."""
    ser.reset_input_buffer()
    command(ser, cc.CHIP_ERASE)
    skipped = []
    failed = []
    end = time.time() + 300
    while time.time() < end:
        line = ser.readline().decode('utf-8', errors='replace').strip()
        if not line:
            continue
        if line.startswith("erase complete"):
            return skipped, failed
        if line.endswith("bad block, skipped"):
            skipped.append(int(line.split()[1].rstrip(':')))
        elif line.endswith("EERR"):
            failed.append(int(line.split()[1].rstrip(':')))
        progress("  " + line)
    raise NandError("timeout during chip erase")


def write_page(ser, page, data, retries=5):
    command(ser, cc.SET_W_ADDR, page)
    expected = hashlib.sha256(data).hexdigest()

    for _ in range(retries):
        command(ser, cc.PAGE_IN)
        ser.write(cc.BYTES_START.encode() + data + cc.BYTES_FINISHED.encode())

        line = wait_line(ser, ["SHA: "])
        if line is None:
            raise NandError(F"no SHA from Pico for page {page}")

        if line[5:].strip() != expected:
            # corrupted on USB: the Pico drops the page and we send it again
            ser.write(b'c')
            wait_line(ser, ["page not written"])
            continue

        ser.write(b'w')
        line = wait_line(ser, ["wc", "WERR"])
        if line is None:
            raise NandError(F"no write ACK for page {page}")
        if line.startswith("WERR"):
            raise NandError(F"write error on page {page} (block {page // PAGE_COUNT})")
        wait_line(ser, ["wc"], timeout=1)  # WERR, if any, is followed by wc
        return

    raise NandError(F"page {page}: data corrupted on USB {retries} times")


# ===== image analysis =====

def page(nand, index):
    return nand[index * PAGE_SIZE:(index + 1) * PAGE_SIZE]


def block(nand, index):
    return nand[index * BLOCK_SIZE:(index + 1) * BLOCK_SIZE]


def image_bad_blocks(nand):
    return [b for b in range(BLOCK_COUNT)
            if any(nand[(b * PAGE_COUNT + pg) * PAGE_SIZE + DATA_SIZE] != 0xff for pg in (0, 1))]


# Wii NAND ECC: 4 bytes for each 512 byte sector, stored at spare offset 0x30
def _parity(x):
    return bin(x).count('1') & 1

_ECC_MASKS = []
for _j in range(9):
    _m = 0
    for _i in range(512):
        if (_i >> _j) & 1:
            _m |= 0xff << (8 * (511 - _i))
    _ECC_MASKS.append(_m)

def _xor_bytes(v):
    s = 2048
    while s >= 8:
        v = (v >> s) ^ (v & ((1 << s) - 1))
        s //= 2
    return v

def _sector_ecc(data):
    v = int.from_bytes(data, 'big')
    x_all = _xor_bytes(v)
    a = [[0, 0] for _ in range(12)]
    for j in range(9):
        odd = _xor_bytes(v & _ECC_MASKS[j])
        a[3 + j] = [x_all ^ odd, odd]
    x = a[3][0] ^ a[3][1]
    a[0] = [x & 0x55, x & 0xaa]
    a[1] = [x & 0x33, x & 0xcc]
    a[2] = [x & 0x0f, x & 0xf0]
    a0 = a1 = 0
    for j in range(12):
        a0 |= _parity(a[j][0]) << j
        a1 |= _parity(a[j][1]) << j
    return bytes([a0 & 0xff, a0 >> 8, a1 & 0xff, a1 >> 8])

def correct_page(p):
    """Applies the Wii ECC like the console does: single bit errors in a 512 byte sector are
    corrected. Returns (page, state), state is 'ok', 'corrected' or 'uncorrectable'."""
    if p == ERASED_PAGE:
        return p, 'ok'
    if p[DATA_SIZE + 0x30:DATA_SIZE + 0x40] == b'\xff' * 16:
        return p, 'ok'  # written without ECC on purpose (e.g. the boot2 blockmap pages)
    fixed = bytearray(p)
    state = 'ok'
    for k in range(4):
        stored = p[DATA_SIZE + 0x30 + 4 * k:DATA_SIZE + 0x34 + 4 * k]
        calc = _sector_ecc(p[k * 512:(k + 1) * 512])
        if calc == stored:
            continue
        e0 = (calc[0] | calc[1] << 8) ^ (stored[0] | stored[1] << 8)
        e1 = (calc[2] | calc[3] << 8) ^ (stored[2] | stored[3] << 8)
        if (e0 | e1) >> 12:
            state = 'uncorrectable'                         # damaged ECC bytes
        elif e0 ^ e1 == 0xfff:
            fixed[k * 512 + (e1 >> 3)] ^= 1 << (e1 & 7)     # single bit error in data
            state = 'corrected' if state == 'ok' else state
        elif bin(e0).count('1') + bin(e1).count('1') == 1:
            state = 'corrected' if state == 'ok' else state  # single bit error in the ECC itself
        else:
            state = 'uncorrectable'
    return bytes(fixed), state

def ecc_report(nand, skip_blocks=(), progress=print):
    """Returns (corrected, uncorrectable) page lists."""
    corrected = []
    uncorrectable = []
    for b in range(BLOCK_COUNT):
        if b % 512 == 0:
            progress(F"  ECC check, block {b}...")
        if b in skip_blocks:
            continue
        for pg in range(PAGE_COUNT):
            index = b * PAGE_COUNT + pg
            state = correct_page(page(nand, index))[1]
            if state == 'corrected':
                corrected.append(index)
            elif state == 'uncorrectable':
                uncorrectable.append(index)
    return corrected, uncorrectable


# ===== BootMii keys and SFFS superblocks =====

def load_keys(path):
    with open(path, 'rb') as f:
        keys = f.read()
    if len(keys) != KEYS_SIZE or not keys.startswith(b'BackupMii'):
        raise NandError(F"{path} is not a BootMii keys.bin")
    return keys

def console_id(keys):
    header = keys[:0x100].split(b'\n')[0].decode('ascii', errors='replace')
    return header.split("ConsoleID:")[-1].strip()

def _superblock(nand, sb):
    """Returns (first cluster, ECC corrected data) of SFFS superblock sb."""
    cluster = 0x7F00 + sb * 16  # superblock = 16 clusters of 8 pages
    first = cluster * 8
    data = b''.join(correct_page(page(nand, first + i))[0][:DATA_SIZE] for i in range(128))
    return cluster, data

def check_superblocks(nand, keys):
    """Verifies the HMAC of the 16 SFFS superblocks with the console NAND HMAC key, after the
    ECC correction (as the console does). A valid HMAC proves that the NAND belongs to the
    console of keys.bin. Returns a list of (index, generation or None, hmac_ok)."""
    hmac_key = keys[0x100 + 0x44:0x100 + 0x58]  # OTP NAND HMAC key
    results = []
    for sb in range(16):
        cluster, data = _superblock(nand, sb)
        if data[:4] != b'SFFS':
            results.append((sb, None, False))
            continue
        generation = struct.unpack('>I', data[4:8])[0]
        salt = bytearray(0x40)
        salt[0x12:0x14] = struct.pack('>H', cluster)
        digest = hmac.new(hmac_key, bytes(salt) + data, hashlib.sha1).digest()
        hmac_page = correct_page(page(nand, (cluster + 15) * 8 + 6))[0]
        stored = hmac_page[DATA_SIZE + 1:DATA_SIZE + 21]
        results.append((sb, generation, digest == stored))
    return results

def fat_bad_blocks(nand, superblocks):
    """Blocks whose clusters are marked bad (0xFFFD) in the FAT of the newest valid superblock:
    blocks found bad by the console during use, which have no marker on the chip."""
    valid = [(sb, gen) for sb, gen, ok in superblocks if ok]
    if not valid:
        return []
    sb = max(valid, key=lambda v: v[1])[0]
    data = _superblock(nand, sb)[1]
    fat = struct.unpack('>32768H', data[12:12 + 0x10000])
    return sorted({cluster // 8 for cluster, value in enumerate(fat) if value == 0xFFFD})


def analyze(nand, keys, reference=None, out=print):
    """Coherence report of a raw NAND image. Returns True if it belongs to the console of keys."""
    out(F"Console ID (keys.bin): {console_id(keys)}")

    bad = image_bad_blocks(nand)
    out(F"Bad blocks (factory marker): {bad}")

    superblocks = check_superblocks(nand, keys)
    valid = [(sb, gen) for sb, gen, ok in superblocks if ok]
    out(F"SFFS superblocks with valid HMAC (after ECC correction): {len(valid)}/16")
    if valid:
        sb, gen = max(valid, key=lambda v: v[1])
        out(F"  newest valid superblock: #{sb}, generation {gen}")
    invalid = [(sb, gen) for sb, gen, ok in superblocks if not ok]
    if invalid:
        out(F"  superblocks without valid HMAC (index, generation): {invalid}")
    out(F"Bad blocks in the FAT (marked by the console): {fat_bad_blocks(nand, superblocks)}")

    def short(pages):
        return F"{len(pages)} {pages[:20]}{' ...' if len(pages) > 20 else ''}"

    corrected, uncorrectable = ecc_report(nand, bad, progress=lambda line: print(line))
    out(F"Pages with single bit ECC errors (corrected by the console): {short(corrected)}")
    out(F"Pages with uncorrectable ECC errors: {short(uncorrectable)}")

    if reference is not None:
        out("Comparison with reference image:")
        out(F"  keys appended to reference == keys.bin: {reference[NAND_SIZE:] == keys}")
        out(F"  factory bad blocks equal: {image_bad_blocks(reference) == bad}")
        out(F"  boot1 (block 0) identical: {block(nand, 0) == block(reference, 0)}")
        same_pages = sum(page(nand, i) == page(reference, i) for i in range(BLOCK_COUNT * PAGE_COUNT))
        out(F"  identical pages: {same_pages}/{BLOCK_COUNT * PAGE_COUNT}")
        ref_uncorrectable = set(ecc_report(reference, bad, progress=lambda line: None)[1])
        new_errors = [p for p in uncorrectable if p not in ref_uncorrectable]
        out(F"  uncorrectable ECC errors not already present in reference: {short(new_errors)}")

    return len(valid) > 0
