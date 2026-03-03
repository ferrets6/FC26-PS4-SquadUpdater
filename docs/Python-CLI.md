# Python CLI Guide

← [Back to README](../README.md)

---

## Table of Contents

- [Prerequisites](#prerequisites)
- [Setup](#setup)
- [First Run — Provide a New Save File](#first-run--provide-a-new-save-file)
  - [USB Flow (recommended)](#usb-flow-recommended)
  - [Fixed Drive Flow](#fixed-drive-flow)
  - [Manual Flow (DATA file only)](#manual-flow-data-file-only)
- [Subsequent Runs — Use an Existing Backup](#subsequent-runs--use-an-existing-backup)
- [Backup & Output Structure](#backup--output-structure)
- [Update Detection](#update-detection)
- [Configuration](#configuration)

---

## Prerequisites

- **Python 3.8+** (Windows only — drive detection uses the Windows API)
- **[Apollo Save Tool](https://github.com/bucanero/apollo-ps4)** installed on your PS4
- A **USB drive** formatted as FAT32 or exFAT

No third-party Python packages are required — the script uses only the standard library.

---

## Setup

1. Clone or download this repository
2. Run the script from the project root:

```bash
python main.py
```

No virtual environment or `pip install` needed.

---

## First Run — Provide a New Save File

Choose **`2. Provide a new save file`** at the main menu.

Use this flow the first time you run the tool, or any time you want to re-export a fresh save from your PS4 (e.g. after manually editing squads in-game).

### USB Flow (recommended)

1. On your PS4, open **Apollo Save Tool** and back up your Squads save to USB
2. Plug the USB into your Windows PC
3. Run `python main.py` and select **`2. Provide a new save file`**
4. Select your USB drive from the drive list — removable drives are marked `[USB]`
5. The script finds the Squads save folder automatically (or asks you to pick one if multiple saves are present)
6. A backup is created in `backup/<userId>_<SaveName>/`
7. The latest squad data is downloaded from EA, patched, and saved to `output/<userId>_<SaveName>/`
8. The patched `DATA` file is **automatically written back to your USB**
9. Plug the USB back into your PS4 and use Apollo Save Tool to restore the save

### Fixed Drive Flow

If Windows detects your USB as a fixed (non-removable) drive:

1. Copy the Apollo save folder into the `input/` directory at the project root
2. Run the script and select the drive from the list
3. The script reads the save from `input/` instead of the drive's `PS4/APOLLO/` path
4. No automatic USB write-back — manually copy the output folder to your USB

### Manual Flow (DATA file only)

If you only have the raw `DATA` file without the full Apollo folder:

1. Copy the file to `input/DATA`
2. Run the script and choose **`0. Skip`** in the drive list
3. Enter an identifier (e.g. `Gianni`) — used as a prefix for the backup folder name
4. Output is written to `output/<identifier>_<SaveName>/DATA`

> ⚠️ This creates an *incomplete* backup. The output will only contain the `DATA` file — other files that Apollo needs for a valid restore (like `DATA.bin`) will not be present. Use the USB flow whenever possible.

---

## Subsequent Runs — Use an Existing Backup

Choose **`1. Use an existing backup`** at the main menu.

Use this flow once you already have a backup — no need to re-export from your PS4 every time you want to check for updates.

1. The script lists all backups found in `backup/`
2. Select the one you want to update
3. The latest EA data is downloaded and compared to the last applied version
4. **If no update is available:** prints `No updates available.` — nothing is written
5. **If an update is available:** the backup `DATA` is patched and saved to `output/`
6. You are asked whether to write the result back to a USB drive — insert the USB, press Enter, and select the Apollo save folder on the USB

> On the first run of this flow (no `.last_db_hash` yet), the script compares the EA download directly against the DB content currently in the backup DATA file.

---

## Backup & Output Structure

```
backup/
  1d125704_Rose_DB/                         ← container: userId + save name
    1d125704_CUSA52342_Squads20260303.../   ← original Apollo folder (complete backup)
      DATA
      DATA.bin
      ...
    .last_db_hash                           ← SHA-256 of last applied EA DB (auto-managed)

  Gianni_Rose_DB/                           ← container: identifier + save name (manual)
    DATA
    .last_db_hash

output/                                     ← mirrors backup structure; ready for PS4
  1d125704_Rose_DB/
    1d125704_CUSA52342_Squads20260303.../
      DATA                                  ← patched
      DATA.bin                              ← copied from backup unchanged
      ...
```

The save name part of the folder (e.g. `Rose_DB`) is extracted from the PS4 DATA file metadata and sanitized for filesystem compatibility: max 26 ASCII characters, spaces replaced with `_`, special characters removed.

---

## Update Detection

The script tracks the last applied EA database using a `.last_db_hash` file (SHA-256) inside each backup container.

| Flow | How the current DB is identified |
|------|----------------------------------|
| Use existing backup | Reads `.last_db_hash` if present; otherwise hashes the DB portion of the backup DATA |
| Provide new file | Always hashes the DB portion of the provided DATA directly |

After a successful patch, `.last_db_hash` is updated in both flows.

---

## Configuration

At the top of `main.py`:

```python
# Only download squad data for these platforms
ALLOWED_PLATFORMS = {"ps4"}
```

To download for additional platforms, add their key to the set:

| Key | Platform |
|-----|----------|
| `pc64` | PC (Windows 64-bit) |
| `nx` | Nintendo Switch |
| `nx2` | Nintendo Switch 2 |
| `ps4` | PlayStation 4 |
| `ps5` | PlayStation 5 |
| `xbsx` | Xbox Series X/S |
| `xone` | Xbox One |
