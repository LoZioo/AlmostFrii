# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Raspberry Pi Pico firmware (`src/`) plus host Python scripts to read, erase and program a Wii NAND chip (Hynix HY27UF084G2B and compatible, ID `ad dc 10 95`) over USB serial. Fork of MCMANIRX/AlmostFrii; `README.MD` keeps the original docs and appends a "Fork changes" section. Keep that structure and the credits to the original author when editing the README. The README uses CRLF line endings.

## Build the firmware

Pico SDK 2.2.0 and its toolchain are installed by the Raspberry Pi Pico VS Code extension under `~/.pico-sdk`. The build dir is `src/build`. From Git Bash:

```bash
cd src/build
export PATH=~/.pico-sdk/toolchain/14_2_Rel1/bin:~/.pico-sdk/ninja/v1.12.1:~/.pico-sdk/cmake/v3.31.5/bin:$PATH
cmake --build .
```

The output is `src/build/wii-nand-interf.uf2`. The user flashes it by copying it to the Pico in BOOTSEL mode. There are no tests or linters. To check the Python scripts, run `python -m py_compile <file>.py`.

## Python scripts

Set up with `python -m venv .venv` and `pip install -r requirements.txt` (only `pyserial`). Every script takes `-P"COMx"` for the serial port; the user's Pico is on COM10.

- `nand_tools.py` is the shared module used by the newer scripts (`bootmii_backup.py`, `bootmii_restore.py`, `bad_blocks.py`). It contains:
  - geometry constants;
  - the serial protocol helpers;
  - the Wii ECC (Hamming, 4 bytes per 512-byte sector at spare 0x30–0x3F, single-bit correction);
  - the SFFS superblock HMAC check, keyed with the NAND HMAC key from `keys.bin` at 0x144;
  - the FAT bad-block extraction;
  - `analyze()`, the coherence report.
- The original scripts `nand_dump.py` and `nand_program.py` use their own inline protocol code, plus `console_commands.py`.

`bootmii_restore.py` erases and rewrites the chip. **Never run any script that talks to the real chip yourself.** The user runs all hardware operations; you may only analyze images and logs offline.

## Serial protocol (firmware ↔ host)

Command strings are defined twice and must stay in sync: `src/console_commands.h` and `console_commands.py`. The command format is `&<addr>$cmd$me` (for example `$pr` reads a page, `$bsha` returns the SHA256 of a block computed on the Pico, `$id`, `$NANDErase`, `$BLOCKErase`).

- **Page read**: the firmware sends `$bs\r\n`, then 2112 raw bytes, then `$bf`.
- **Page write**:
  1. The host sends `$swa`, then `$pi$me`, then `$bs` + data + `$bf`.
  2. The firmware prints `SHA: …`.
  3. The host answers `w` (write) or `c` (cancel/resend).
  4. The firmware prints `WERR` on program failure, then `wc`.

  Don't add extra waits per page: an extra `wait_line` cost 1–3 s per page.

Firmware layout:
- `main.c`: the command loop and parsing.
- `commands.c`: the NAND operations. Status polling uses `wait_ready()`. Bad-block checks use `is_bad_block()`, which reads the marker on pages 0 and 1. `erase_chip`/`erase_block` never erase factory bad blocks.
- `pio/read_io_sm.pio`: the PIO state machine for page reads. RE idles high, and RE is held low for 8 cycles before sampling. A dummy RE pulse shifts data by one byte, so don't reintroduce one.

## NAND / image facts

- **Geometry**: a page is 2112 bytes (2048 data + 64 spare). A block is 64 pages, and the chip has 4096 blocks. A raw image is 553,648,128 bytes. A BootMii `nand.bin` is that raw image plus the 1024-byte `keys.bin` appended.
- **Factory bad block**: spare byte 0 of page 0 or 1 is not `0xFF`.
- **Runtime bad blocks**: the console can also mark a block bad in the SFFS FAT (`0xFFFD`). The restore skips both kinds.
- **Pages without ECC**: boot2 blockmap pages 191 and 447 are intentionally written without ECC (spare all `0xFF`). They are not errors.
- **SFFS superblocks**: there are 16, in blocks 4064–4095. Worn cells there give correctable single-bit errors, so verify HMACs on ECC-corrected data.
- **Read errors are usually wiring, not the chip**: data-dependent errors that repeat identically across dumps were ground bounce. The fix is in the README's hardware notes. Rule out wiring before concluding the chip is damaged.

## Local data (gitignored, contains console keys)

These folders hold the console keys and must never be committed or published:
- `nand_backup/`: the reference BootMii backup (`nand.bin` + `keys.bin`).
- `bootmii_backup/`: output of `bootmii_backup.py`.
- `bootmii_restore/`: input of `bootmii_restore.py`.
- `nand_dumps/`: raw dumps and `bad_blocks.py` logs.

In Git Bash, use forward slashes in paths; backslashes get eaten.
