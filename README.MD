# AlmostFrii

> **Fork** of [MCMANIRX/AlmostFrii](https://github.com/MCMANIRX/AlmostFrii), original project by MCMANIRX. See [Fork changes](#fork-changes) for the fixes and the new BootMii backup/restore scripts added in this fork.

Raspberry Pi Pico controller for Nintendo Wii NAND, HY27UF084G2B/M 512MByte parallel NAND flash or equivalents. This project currently only supports 1:1 NAND flashing i.e. no ECC calculation.

![image](./img/circuit.png)

## Features

- Read/Write individual pages by row address (0x00->0x03FFFF)

- Read manufacturer code

- Block (0x00->0xFFF) and full chip erase

- On-chip SHA256 calculation for individual pages or blocks

- Logging for NAND dumps and programs

## Notes

- Page size: **2KB** (2048 valid data +64 ECC bytes, so **2112 bytes** in total)

- Block Size: 64 Pages = **128KB** (**135168 bytes total**) 
- Block count: **4096**

## Hardware Setup

This project requires:
1. Raspberry Pi Pico (basic or W)
2. TSOP48 breakout 
3. [Wii-supported NAND chip](https://wiibrew.org/wiki/Hardware/NAND#Supported_chips)
4. Recommended 0.1uF capacitor across Vss and Vcc.

### Wiring Guide

| Pin  | Pico | NAND     |
|-------|-----|----------|
| R/B | GPIO 11  | 7 |
| RE   | GPIO 12  | 8   |
| CE | GPIO 13  | 9    |
| Vcc | Pin 36  | 12, 37 |
| Vss   | Pin 38  | 13, 36   |
| CLE | GPIO 18  | 16 |
| ALE   | GPIO 19  | 17   |
| WE | GPIO 20  | 18    |
| WP | GPIO 21  | 19    |
| IO0 | GPIO 2  | 29    |
| IO1 | GPIO 3  | 30    |
| IO2 | GPIO 4  | 31    |
| IO3 | GPIO 5  | 32    |
| IO4 | GPIO 6  | 41    |
| IO5 | GPIO 7  | 42    |
| IO6 | GPIO 8  | 43    |
| IO7 | GPIO 9  | 44    |

## Basic Usage

### Dumping NAND

To dump the full NAND, run:

 ```bash
 python ./nand_dump.py -P"/your/port"
 ``` 
replacing `/your/port` with whatever serial port your Pi Pico shows up as.

### Writing NAND

When writing a NAND backup to another NAND, it is probably a good idea to erase the chip first.

In a serial monitor such as the Arduino IDE, VS Code serial monitor, PuTTY, etc. enter

```bash
$NANDErase$me
```

and wait for the chip to complete full erasure. Then, **after closing the monitor**, run

 ```bash
 python ./nand_program.py ./path-to-file -wb -4096 -a0 -P"/your/port"
 ``` 

 again replacing `/your/port`, and `./path-to-file` with the path to your NAND backup.



## Advanced Usage

### Python Scripts

- **nand_dump.py**: automatically dumps entire chip to `nand_dumps/nand-{epoch}.bin`. Takes ~20min.

- **program.py**: programs NAND chip from file input and computes SHA256 per-block and per-page. takes ~1.5hrs.

## `nand_dump.py` Arguments

- `P` sets the port to use

- `l` sets the **l**ength of blocks to read (default 4096)

- `a` sets the block **a**ddress **in hex** to begin reading (default 0)

- `d` enables command **d**ebug mode, quitting program before NAND interfacing begins

## `nand_dump.py` Examples

### Example 1
 ```bash
 python ./nand_dump.py -P"/dev/tty.usbmodem101" -l800 -a800
 ```

- Dumps 800 pages of NAND starting from block address 0x800 (2048) using `/dev/tty.usbmodem101`

**output:**

```bash
Reading 800 blocks from start address 2048 with port COM13.
```

### Example 2
 ```bash
 python ./nand_dump.py -P"/dev/tty.usbmodem101"
 ``` 

- Dumps entire NAND using `/dev/tty.usbmodem101`

**output:**

```bash
Reading 4096 blocks from start address 0 with port COM13.
```

## `nand_program.py` Arguments

- `w` enables write mode

- `t` enables **t**est write mode ("writes pattern `0xAD`)

- `p` enables per-**p**age SH256A calculation
- `P` sets the port to use

- `b` enables per-**b**lock SHA256 calculation (enabled by default)

    - May be disabled with `B`

- `l` sets the **l**ength of write in blocks (default 0)

- `a` sets the block **a**ddress **in hex** to begin writing (default 0)
    - **NOTE:** this begins writing the NAND image relative to 0 at the specified address i.e. the arguments `-a8 -l8` will write blocks 8-15 from the selected NAND image, skipping blocks 0-7.  

- `d` enables command **d**ebug mode, quitting program before NAND interfacing begins

## `nand_program.py` Examples

### Example 1
 ```bash
 python ./nand_program.py ./path-to-file -wpbd -l60 -aA8 -P"/dev/tty.usbmodem101"
 ```  

- Starting from the address of block `0xA8`, will write 60 blocks to NAND using port `/dev/tty.usbmodem101` provided file and computes per-block and per-page SHA256, but exits program after printing debug message.

**output:**

```bash
Doing write from image ./path-to-file with per-page and per-block SHA256 calculation, starting at block address 0xa8 for 60 blocks
```

\*program exits\*

### Serial Commands

These commands are intended to be typed into a serial monitor such as PuTTY. 

 
**NOTE: ALL HEX ADDRESSES MUST BE UPPERCASE!!**

- `$id$me` - print out NAND chip ID (should be: `ad dc 10 95`) 

- `$pr$me` - read a page, with hex address input

    - usage: `&3F$pr$me` reads page `0x3F`

- `$BLOCKErase$me` - erase block, with hex address input

    - usage: `&3F$BLOCKErase$me` erases page `0x3F`

- `$NANDErase$me` - erases entire NAND chip

- `$pwt$me` - write page full of test string `quickbrownfox` 

    - usage: `&3F$pwt$me` writes page `0x3F` of test string

- `$bsha$me` - compute SHA256 hash of block at given address
    - usage: `&3F$bsha$me` computes SHA256 hash of block `0x3F`

- `$psha$me` - compute SHA256 hash of page at given address
    - usage: `&3F$psha$me` computes SHA256 hash of page `0x3F`



# Fork changes

This fork extends [AlmostFrii](https://github.com/MCMANIRX/AlmostFrii) by [MCMANIRX](https://github.com/MCMANIRX) (with contributions from [Byrom90](https://github.com/Byrom90)). All the documentation above is the original one; this section describes what changed in the fork and how to use it.

## Flashing the firmware

Prebuilt firmware is published in the [Releases](https://github.com/LoZioo/AlmostFrii/releases) page of this fork. Download the `wii-nand-interf.uf2` file of the latest release. The same file works on the Pico and on the Pico W (same RP2040 and pins); the Pico 2 / Pico 2 W (RP2350) are not supported by this build.

1. Unplug the Pico from USB.
2. Hold the **BOOTSEL** button and plug the Pico back in, then release the button. A drive named `RPI-RP2` appears.
3. Copy the `.uf2` file to `RPI-RP2`. The Pico reboots by itself and appears as a serial port (COM port on Windows, `/dev/tty.usbmodem*` on macOS, `/dev/ttyACM*` on Linux).
4. Check the wiring and the firmware: in a serial monitor send `$id$me`, the answer must be `ad dc 10 95`.

To build the firmware yourself instead, see the Pico SDK setup in `src/` and run `cmake -S src -B src/build -G Ninja && cmake --build src/build`; the file is generated in `src/build/wii-nand-interf.uf2`.

## Running the Python scripts with a virtual environment

From the repository folder, create the virtual environment once and install the dependencies:

```bash
python -m venv .venv
```

Activate it (once per terminal):

- Windows PowerShell: `.venv\Scripts\Activate.ps1` (if scripts are blocked, run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once)
- Windows Git Bash: `source .venv/Scripts/activate`
- Linux / macOS: `source .venv/bin/activate`

then install the requirements:

```bash
pip install -r requirements.txt
```

Now every `python ./script.py ...` command of this README runs inside the virtual environment. Use `deactivate` to leave it. Without activating, the interpreter can also be called directly, e.g. `.venv\Scripts\python.exe ./nand_dump.py -P"COM10"`.

> On Windows Git Bash, use forward slashes in paths (`nand_backup/nand.bin`): backslashes are escape characters there.

## Quick usage

| Task | Command |
|---|---|
| Check the wiring | `$id$me` in a serial monitor, must answer `ad dc 10 95` |
| Bad block map (and comparison with an image) | `python ./bad_blocks.py -P"COM10" nand_backup/nand.bin` |
| Raw dump (`nand_dumps/`) | `python ./nand_dump.py -P"COM10"` |
| BootMii format backup (`bootmii_backup/`) | `python ./bootmii_backup.py -P"COM10"` |
| BootMii format restore (`bootmii_restore/`) | `python ./bootmii_restore.py -P"COM10"` |
| Raw write of an image | `$NANDErase$me`, then `python ./nand_program.py ./nand.bin -wb -l4096 -a0 -P"COM10"` |

**Notes on the original documentation above:**

- the write command in the *Writing NAND* section (`-wb -4096`) lacks the `l` and writes 0 blocks; the correct option is `-l4096`. `nand_program.py` now stops with an error when `-l` is missing;
- `program.py` is `nand_program.py`;
- `&3F$BLOCKErase$me` erases **block** `0x3F` (pages `0xFC0`-`0xFFF`), not page `0x3F`;
- hex addresses are accepted in lowercase too.

### Folders

| Folder | Content |
|---|---|
| `nand_backup/` | reference BootMii backup of the console: `nand.bin` and `keys.bin` |
| `bootmii_backup/` | dumps made by `bootmii_backup.py` (`nand-bootmii-{epoch}.bin` + log) |
| `bootmii_restore/` | `nand.bin` to restore and the console `keys.bin` |
| `nand_dumps/` | raw dumps of `nand_dump.py` and logs of `bad_blocks.py` |
| `program_log/` | logs of `nand_program.py` |

These folders contain the console keys and are ignored by git: never publish them.

## New scripts

- **`bootmii_backup.py`**: dumps the whole chip and saves it in BootMii format (raw NAND + `keys.bin` appended, 553,649,152 bytes), so it can be used with the usual Wii NAND tools. Every block is compared with the SHA256 computed by the Pico on an independent read and read again on mismatch. Then a coherence report is written:
  - HMAC of the 16 SFFS superblocks, verified with the console NAND HMAC key of `keys.bin` after the ECC correction: a valid HMAC proves that the NAND belongs to that console;
  - factory bad blocks (marker on the chip) and bad blocks marked by the console in the FAT;
  - pages with single bit ECC errors (corrected by the console, typical of the most worn superblock area) and pages with uncorrectable ECC errors;
  - comparison with the reference backup (`nand_backup/nand.bin`): keys, bad blocks, boot1, identical pages, new ECC mismatches.

  Options: `-k` keys file (default `nand_backup/keys.bin`), `-r` reference image (default `nand_backup/nand.bin`, `-r ""` to skip).
- **`bootmii_restore.py`**: restores a BootMii `nand.bin` (default `bootmii_restore/nand.bin`, keys from `bootmii_restore/keys.bin` or appended to the image). Before touching the chip it checks the image size, that the appended keys match `keys.bin`, the superblock HMAC (images of other consoles are refused), the NAND ID and that every factory bad block of the chip is excluded by the image (the image may have more bad blocks: those marked by the console in its FAT are not written either). After a `YES` confirmation it erases the chip (bad blocks excluded), writes every non-empty page (each page is checked with SHA256 before programming and resent if corrupted on USB) and verifies every block against the image. This is also useful to recreate a clean NAND from a backup: see the [Wii factory reset guide](https://wii.hacks.guide/wii-factory-reset#restoring-the-wii-nand-to-stock) for the restoring steps on a stock NAND.
- **`bad_blocks.py`**: reads pages 0 and 1 of every block and lists the factory bad block markers in about 40 seconds, optionally comparing them with an image. Markers are cross-checked with the Wii ECC to filter out read errors.
- **`nand_tools.py`**: shared module of the three scripts above (serial protocol, Wii ECC, SFFS superblock HMAC, keys parsing, coherence report). Missing files and a wrong serial port are reported with a readable error.

## Firmware changes

- **Address parsing**: `addr_to_u32()` in `main.c` had no `return`, so the compiled firmware used address 0 for every command: every page read returned page 0, `$BLOCKErase$me` always erased block 0 (boot1) and every write went to page 0.
- **PIO read timing** (`read_io_sm.pio`):
  - the "dummy read" RE pulse before each page was removed: depending on timing it consumed the first byte, so some pages were read shifted by one byte;
  - RE is kept low for 8 PIO cycles (~64 ns at 125 MHz) before sampling, instead of 1 cycle plus the input synchronizer (~24 ns), well above tREA (20 ns);
  - RE idles high when the state machine is initialized, and is set high before being switched back to GPIO: before, the first read after power-up was shifted by one byte.
- **Status register**: `read_status()` now respects tWHR (≥ 60 ns) and tREA. A new `wait_ready()` waits tWB before polling R/B (the chip may need up to 100 ns to pull it low) and then reads the status. Before, an erase could be considered finished before it started, and the next command was sent to a busy chip.
- **Write errors**: `write_page()` now reads the status register after programming, so `WERR` is actually reported (before it checked a stale status).
- **Bad blocks are never erased**: `$NANDErase$me` reads the marker of pages 0 and 1 of every block (`is_bad_block()`) and skips factory bad blocks, whose marker would otherwise be destroyed. It prints a summary (`bad blocks skipped: N, erase errors: N`). `$BLOCKErase$me` also skips bad blocks and prints `erased` or `EERR`.
- **Write error recovery**: when the host rejects a page buffer (bad SHA256) the firmware drops the page and goes back to the console, so the host can resend it. Before, it entered an endless loop blinking the LED and the retry implemented in `nand_program.py` could never work. Two `strcpy()` reading past the end of non terminated buffers were fixed.
- **No more freezes needing a replug**:
  - a page transfer that stops halfway (e.g. a script interrupted with Ctrl+C) is abandoned after 2 seconds with `timeout`, instead of waiting forever for the missing bytes;
  - a command with a missing or malformed `&address` answers `bad address` and is not executed, instead of freezing with the LED on (it also no longer falls back to address 0, which for `$BLOCKErase` would be boot1);
  - garbage on the serial line without `$me` no longer overflows the command buffer.
- **Page transmission**: `read_page()` sent the page only while bytes were waiting in the USB *receive* buffer (it worked thanks to the `\r` sent by the scripts after each command) and could send bytes past the end of the page. It now waits for room in the *transmit* buffer and sends exactly 2112 bytes.
- **`$id$me`**: the four ID bytes are printed in a well defined order (the arguments of `printf()` were evaluated in an unspecified order).
- **Pico and Pico W**: the unused LED code (and the separate `pico_w` build, which only initialized the wireless chip to drive the LED) was removed: the same `.uf2` runs on both boards.

## Script changes

- **`nand_program.py`**: stops if `-l` is missing; fixed the initial file seek (it used a page index as a byte offset, wrong with `-a` ≠ 0); blocks marked bad in the image are not written nor verified; a write ACK timeout or `WERR` stops the script instead of looping; non-UTF-8 bytes on the serial line no longer crash it.
- **`nand_dump.py`**: the SHA verification no longer crashes on non-UTF-8 bytes on the serial line.

## Hardware notes

With a single ground return through a breadboard, reads showed **data dependent errors**: bytes following a byte with few bits set (e.g. `00` → `FF`) were read wrong or shifted, always in the same pages. When 8 outputs switch together the ground bounce produces spurious RE edges. The errors are identical in every dump, so they look like corrupted data in the chip (wrong Wii ECC on many pages, fake bad block markers), but they are a wiring problem. What fixed it:

- 3V3 wired directly from the Pico (pin 36) to NAND pin 12, with pins 12 and 37 bridged on the adapter;
- a 100 nF ceramic capacitor between pins 12 and 13, another one between 37 and 36, and a 10 µF capacitor between 12 and 13;
- **two ground wires** from NAND pins 13 and 36 to two different GND pins of the Pico (e.g. 38 and 8);
- short wires (~10 cm).

A good setup gives identical dumps, and boot1 (block 0) identical to a BootMii backup of the same console.

## Credits

This project would not be possible without the incredible documentation and reverse-engineering efforts of the people at [wiibrew.org](https://wiibrew.org/wiki/Hardware/NAND).

Original project by [MCMANIRX](https://github.com/MCMANIRX/AlmostFrii), with the wiring guide fix by [Byrom90](https://github.com/Byrom90).
