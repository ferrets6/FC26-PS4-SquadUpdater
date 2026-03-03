# FC26 PS4 Squad Updater

A Python tool that downloads the latest EA FC 26 squad update directly from EA's servers and patches it into a PlayStation 4 save file, without needing to run the game.

> **Windows only** — drive detection uses the Windows API.

---

## Quick Start

**What you need before starting:**
- Python 3.8+
- A PS4 with [Apollo Save Tool](https://github.com/bucanero/apollo-ps4) installed
- A USB drive formatted as FAT32 or exFAT

**Steps:**
1. On your PS4, open **Apollo Save Tool** and back up your Squads save to USB
2. Plug the USB into your PC
3. Run the script:
   ```
   python main.py
   ```
4. Select **`2. Provide a new save file`**, then select your USB drive from the list
5. The script finds your Squads save automatically, downloads the latest data from EA, patches it, and writes the updated `DATA` file back to your USB
6. Plug the USB back into your PS4 and use Apollo Save Tool to restore the save

That's it. Your squads are updated.

---

## How It Works

EA distributes squad updates as compressed binary files through their CDN. This tool:
1. Fetches the update manifest (`rosterupdate.xml`) to find the latest PS4 squad file
2. Downloads and decompresses it (EA RefPack format)
3. Takes the **PS4 save header** from your existing DATA file (which contains your account info, save name, and a checksum placeholder) and replaces the **database content** with the freshly downloaded one
4. The result is a valid PS4 save file with up-to-date squad data

The tool never modifies your original backup — patched files are always written to the `output/` folder (and optionally back to your USB).

---

## Prerequisites

- **Python 3.8+**
- **Apollo Save Tool** on your PS4 — used to export and re-import saves via USB
  - The save folder on USB must follow Apollo's naming convention:
    `<userId>_CUSA<titleId>_Squads<YYYYMMDDHHmmss>`
  - Example: `1234567890_CUSA12345_Squads20260301120000`

---

## Flows

### Flow 1 — Provide a new save file *(first time, or re-patching with a fresh export)*

Choose **`2. Provide a new save file`** at startup. Then select how you are providing the file:

#### From USB (recommended)

1. Export your Squads save with Apollo Save Tool to a USB drive
2. Plug the USB into your PC and run the script
3. Select the USB drive from the list — it will be marked `[USB]`
4. The script finds the save folder automatically (or asks you to pick if multiple saves are found)
5. A backup is created under `backup/<userId>_<SaveName>/`
6. The latest squad data is downloaded, patched, and saved to `output/<userId>_<SaveName>/`
7. The patched `DATA` file is **automatically written back to your USB**

#### From a fixed drive

If your Apollo save folder is on a non-removable drive (e.g. you mounted the USB as a drive letter but Windows sees it as Fixed):

1. Copy the Apollo save folder into the `input/` directory at the project root
2. Run the script and select that drive from the list
3. The save folder is picked up from `input/` instead of the drive's `PS4/APOLLO/` path
4. No automatic USB write-back — copy the `output/` folder manually

#### Manual (single DATA file)

If you only have the raw `DATA` file (no full Apollo folder):

1. Rename or copy the file to `input/DATA`
2. Run the script and choose **`0. Skip`** in the drive list
3. Enter an identifier name for this save (e.g. `Gianni`) — used as a prefix in the backup folder name
4. The backup is stored as `backup/<identifier>_<SaveName>/DATA`
5. Output is stored as `output/<identifier>_<SaveName>/DATA`

> This is an *incomplete* backup. You will only get the `DATA` file in the output — other save files (e.g. `DATA.bin`) that Apollo needs for a valid restore will not be present. Use the USB flow whenever possible.

---

### Flow 2 — Use an existing backup *(check for updates without a new export)*

Choose **`1. Use an existing backup`** at startup. This flow is useful when:
- You want to check whether a new squad update has been released since your last patch
- You don't want to re-export from your PS4 every time

1. The script lists all backups found in `backup/`
2. Select the one you want to update
3. The latest EA data is downloaded and compared to the last applied version (tracked via a `.last_db_hash` file inside each backup folder)
4. If no update is available: **"No updates available."** — nothing is written
5. If an update is available: the backup DATA is patched and the output is saved
6. You are then asked whether to write the patched `DATA` to a USB drive — insert the USB, press Enter, and select the save folder on the USB

> **On first use of this flow** (no `.last_db_hash` yet): the script compares the EA download directly against the DB content of the backup DATA file, so it still correctly detects whether your save is already up to date.

---

## Backup & Output Structure

```
backup/
  1d125704_Rose_DB/           ← human-readable container (userId + save name)
    1d125704_CUSA52342_Squads20260303132215/   ← original Apollo save folder
      DATA
      DATA.bin
      ...
    .last_db_hash             ← SHA-256 of the last applied EA DB (auto-managed)

  Gianni_Rose_DB/             ← manual backup (identifier + save name)
    DATA
    .last_db_hash

output/                       ← mirrors the backup structure; ready to copy to PS4
  1d125704_Rose_DB/
    1d125704_CUSA52342_Squads20260303132215/
      DATA                    ← patched
      DATA.bin                ← copied from backup unchanged
      ...
```

The `save name` part of the folder name (e.g. `Rose_DB`) is extracted directly from the PS4 DATA file metadata and sanitized for cross-platform filesystem compatibility (max 26 ASCII characters, spaces replaced with `_`).

---

## Technical Details

### Patching Algorithm

1. **Strip EA header** — remove the first 1178 bytes from the downloaded Squads file (fixed-size prefix generated by `save_squads()`). What remains is the raw database starting with the `DB` marker.
2. **Locate T3DB in DATA** — search for the byte sequence `\x44\x42\x00\x08` after offset 1000 (to avoid false matches with save names like "Rose DB"). Everything before this offset is the PS4 save header.
3. **Zero the checksum** — find the `Type_Squads\x00` signature in the header and zero the 4 bytes immediately following it (the embedded CRC/checksum).
4. **Assemble** — concatenate the cleaned PS4 header with the new EA database content.
5. **Validate** — verify the `DB` marker is at the expected position in the result and that the total file size matches the original.

### PS4 DATA File Header Format

```
Offset  Length  Description
------  ------  -----------
0       4       uint32 LE — length of save name (including null terminator)
4       4       (reserved / zero)
8       8       account identifier / timestamp
16      N-1     Save name — UTF-8 string (max ~40 characters)
16+N-1  1       null terminator
...             Save metadata
T3DB    4       DB marker \x44\x42\x00\x08 — start of the embedded database
```

### Available EA Platforms

The script is configured to download PS4 data only (`ALLOWED_PLATFORMS = {"ps4"}`).
All platforms served by EA's content server are:

| Key    | Platform           |
|--------|--------------------|
| `pc64` | PC (Windows 64-bit)|
| `nx`   | Nintendo Switch    |
| `nx2`  | Nintendo Switch 2  |
| `ps4`  | PlayStation 4      |
| `ps5`  | PlayStation 5      |
| `xbsx` | Xbox Series X/S    |
| `xone` | Xbox One           |

To enable additional platforms, add their keys to `ALLOWED_PLATFORMS` in `main.py`.

---

## Credits

- **[xAranaktu/FIFASquadFileDownloader](https://github.com/xAranaktu/FIFASquadFileDownloader)** — the original Python script that handles EA server communication, RefPack decompression, and squad file generation. This project is built on top of that work.

- **[How to manually patch the PS4 squad header (YouTube)](https://www.youtube.com/watch?v=re0ndXQNmKI)** — a video walkthrough explaining the binary header replacement process that this tool automates. Provided the foundation for understanding the PS4 save file format.

---

## License

MIT — see [LICENSE](LICENSE).
