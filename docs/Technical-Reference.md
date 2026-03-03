# Technical Reference

← [Back to README](../README.md)

---

## Table of Contents

- [PS4 DATA File Format](#ps4-data-file-format)
- [Patch Algorithm](#patch-algorithm)
- [EA CDN Structure](#ea-cdn-structure)
- [RefPack Decompression](#refpack-decompression)
- [BNRY Trailing Block](#bnry-trailing-block)
- [Web Architecture](#web-architecture)
- [Python Architecture](#python-architecture)
- [Credits & Sources](#credits--sources)

---

## PS4 DATA File Format

The PS4 Squads save file (`DATA`) has this layout:

```
Offset   Length  Type          Description
───────  ──────  ────────────  ───────────────────────────────────────────────
0        4       uint32 LE     Length of save name including null terminator
4        4       —             Reserved / zero
8        8       bytes         Account identifier / timestamp
16       N-1     UTF-8 string  Save name (max ~40 characters)
16+N-1   1       0x00          Null terminator
...                            Save metadata, including:
                                 - "Type_Squads\x00" signature
                                 - 4-byte checksum (zeroed before patching)
T3DB     4       0x44424200    T3DB marker — start of the embedded database
T3DB+4   ...     bytes         EA squad database content
end-45985 45985  bytes         BNRY trailing block (see below)
```

The T3DB marker (`\x44\x42\x00\x08`, ASCII "DB" + `\x00\x08`) is searched starting from byte offset 1000 to avoid false matches with save names that contain "DB" (e.g. "Rose DB").

---

## Patch Algorithm

The patch replaces the embedded database in the PS4 save while preserving the original PS4 save header (account identity, save name, metadata).

```
Input:  user's DATA file  +  freshly downloaded EA squad data
Output: patched DATA file
```

**Steps:**

1. **Locate T3DB** — search for `\x44\x42\x00\x08` in the DATA file after offset 1000.
   Everything before this position is the *PS4 save header*.

2. **Zero the checksum** — find the `Type_Squads\x00` signature in the header.
   Zero the 4 bytes immediately following it (an embedded CRC that would be invalid after swapping the database).

3. **Prepare the new database** — the decompressed EA data starts at T3DB by construction.
   Append the 45985-byte BNRY trailing block.

4. **Assemble** — concatenate:
   ```
   patched = PS4_save_header + new_EA_database + BNRY_block
   ```

5. **Validate** — verify the T3DB marker is at the expected position in the result.

**Python:** `patch_squads()` in `main.py`
**TypeScript:** `patch()` in `web/src/patcher.ts`

---

## EA CDN Structure

EA distributes squad updates through a content delivery network.

**Manifest URL:**
```
https://eafc26.content.easports.com/fc/fltOnlineAssets/
  26E4D4D6-8DBB-4A9A-BD99-9C47D3AA341D/2026/
  fc/fclive/genxtitle/rosterupdate.xml
```

**Manifest format** (`rosterupdate.xml`) — one `<SquadInfo>` block per platform:
```xml
<SquadInfo platform="ps4">
  <dbMajorLoc>path/to/squads_YYYYMMDD_ps4.bin</dbMajorLoc>
  ...
</SquadInfo>
```

**Binary URL:**
```
<base_url>/<dbMajorLoc>
```

The downloaded file is RefPack-compressed. After decompression, it starts with the T3DB marker followed by the raw squad database.

**Python:** `download_squad_data()` in `main.py`
**TypeScript (proxy):** `netlify/edge-functions/squad-proxy.ts`

---

## RefPack Decompression

EA's proprietary compression format, based on LZ77. The compressed file has a 10-byte header:

```
Offset  Length  Description
──────  ──────  ───────────────────────────────────────────
0       2       Magic / flags (not used during decompression)
2       3       Decompressed size (big-endian 24-bit integer)
5       5       Reserved
10      ...     Compressed data stream
```

The decompressed output is pre-seeded with the 4-byte T3DB marker (`\x44\x42\x00\x08`) before decompression begins. The stream is then decoded control-byte by control-byte:

| Control byte pattern | Type | Encoding |
|----------------------|------|----------|
| `0xxxxxxx` | Short back-reference | 2-byte: `offset` in `b1`, `len=(ctl>>2)&7 + 3`, up to 3 literals |
| `10xxxxxx` | Medium back-reference | 3-byte: `len=ctl&0x3F + 4`, `offset=(b2&0x3F)<<8\|b3 + 1`, up to 3 literals |
| `110xxxxx` | Long back-reference | 4-byte: `len=b4+((ctl&0x0C)<<6)+5`, `offset=((ctl&0x10)<<12)\|(b2<<8)\|b3 + 1`, up to 3 literals |
| `111xxxxx` | Literal run | `lit=(ctl&0x1F)*4+4`; if `lit > 0x70` → end of stream |

After the main loop, any trailing literals indicated by the last control byte's low 2 bits (`last_ctl & 3`) are copied.

**Python:** `unpack()` in `main.py`
**TypeScript:** `decompress()` in `web/src/refpack.ts`

---

## BNRY Trailing Block

Every Squads save file ends with a fixed 45985-byte trailing block. It starts with a 34-byte magic sequence:

```
42 4E 52 59 00 00 00 02  4C 54 4C 45 01 01 03 00
00 00 63 64 73 01 00 00  00 00 01 03 00 00 00 63
64 73
```

ASCII: `BNRY` + binary metadata, followed by 45951 zero bytes.

This block is written by `save_squads()` in the Python script and stripped by `patch_squads()` before re-appending it. The web patcher appends it directly after the database content.

Its purpose appears to be a fixed-layout binary metadata section required by the PS4 save format. Its content does not change between squad releases.

---

## Web Architecture

```
Browser                            Netlify Edge (Deno)        EA CDN
───────────────────────────────    ────────────────────────   ─────────────
User drops DATA file
  │
  ├─ Read file (FileReader API)
  │
  ├─ GET /api/squad-proxy ─────── squad-proxy.ts ──────────── GET rosterupdate.xml
  │                                Parse XML for ps4 bin URL
  │                               ─────────────────────────── GET squads_*.bin
  │  ← stream compressed .bin ───
  │
  ├─ decompress (refpack.ts)
  │    in-memory, no network
  │
  ├─ hash check (SHA-256 via
  │    WebCrypto API)
  │
  ├─ patch (patcher.ts)
  │    in-memory, no network
  │
  └─ Blob download (DATA)
```

**Key design decisions:**
- The proxy only fetches from EA's CDN — it never receives or stores the user's DATA file
- Decompression, hashing, and patching all run in the browser via WebAssembly-compatible TypeScript (no WASM needed — pure TypeScript is fast enough for ~10 MB files)
- The BNRY block is a compile-time constant in `patcher.ts` — no runtime download needed

---

## Python Architecture

```
main.py
│
├─ acquire_backup()               Menu: use existing backup / provide new file
│   ├─ prompt_backup_selection()  List backups in backup/
│   └─ _acquire_from_file()       Drive list / manual DATA input
│
├─ download_squad_data()          Fetch rosterupdate.xml → download .bin
│   ├─ unpack()                   RefPack decompression
│   └─ save_squads()              Build Squads save file (1178-byte header + DB + BNRY)
│
├─ [hash comparison]              SHA-256: new DB vs last known DB
│
├─ patch_squads()                 Strip 1178-byte header → inject into DATA
│
├─ create_output()                Mirror backup structure in output/
│
├─ _save_db_hash()                Write .last_db_hash to backup container
│
└─ [USB write-back]               Optional: overwrite DATA on USB drive
```

**Backup container naming:**
- `<userId>_<SafeSaveName>` for USB/drive backups (userId from Apollo folder name)
- `<identifier>_<SafeSaveName>` for manual DATA-only backups

The safe save name is extracted from the DATA file header (bytes 16+), sanitized to max 26 ASCII characters with underscores instead of spaces.

---

## Credits & Sources

- **[xAranaktu/FIFASquadFileDownloader](https://github.com/xAranaktu/FIFASquadFileDownloader)**
  The original Python implementation: EA server communication, RefPack decompression, squad file assembly (`save_squads`). This project builds directly on top of that work.
  License: MIT — Copyright 2021 Paweł (xAranaktu)

- **[How to manually patch the PS4 squad header (YouTube)](https://www.youtube.com/watch?v=re0ndXQNmKI)**
  Video walkthrough explaining the binary header replacement process that this tool automates. Provided the foundation for understanding the PS4 save file structure and the T3DB/Type_Squads checksum mechanics.

- **[Apollo Save Tool](https://github.com/bucanero/apollo-ps4)**
  The PS4 homebrew app used to export and import saves via USB. Required for both the Python CLI and web version workflows.
