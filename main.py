import os
import sys
import re
import ctypes
import string
import shutil
import hashlib
import urllib.request
import xml.etree.ElementTree as ET
import ssl
from glob import glob

ssl._create_default_https_context = ssl._create_unverified_context

# ─────────────────────────────── EA Content URL ───────────────────────────────
# CONTENT_URL = "https://fifa21.content.easports.com/fifa/fltOnlineAssets/21D4F1AC-91A3-458D-A64E-895AA6D871D1/2021/"
# CONTENT_URL = "https://fifa22.content.easports.com/fifa/fltOnlineAssets/22747632-e3df-4904-b3f6-bb0035736505/2022/"
# CONTENT_URL = "https://fifa23.content.easports.com/fifa/fltOnlineAssets/23DF3AC5-9539-438B-8414-146FAFDE3FF2/2023/"
# CONTENT_URL = "https://eafc24.content.easports.com/fc/fltOnlineAssets/24B23FDE-7835-41C2-87A2-F453DFDB2E82/2024/"
# CONTENT_URL = "https://eafc25.content.easports.com/fc/fltOnlineAssets/25E4CDAE-799B-45BE-B257-667FDCDE8044/2025/"
CONTENT_URL      = "https://eafc26.content.easports.com/fc/fltOnlineAssets/26E4D4D6-8DBB-4A9A-BD99-9C47D3AA341D/2026/"
ROSTERUPDATE_XML = "rosterupdate.xml"

# ──────────────────────────── Binary Signatures ───────────────────────────────
T3DB     = b"\x44\x42\x00\x08"
FBCHUNKS = b"\x46\x42\x43\x48\x55\x4E\x4B\x53\x01\x00"
BNRY     = (b"\x42\x4E\x52\x59\x00\x00\x00\x02\x4C\x54\x4C\x45\x01\x01\x03\x00"
            b"\x00\x00\x63\x64\x73\x01\x00\x00\x00\x00\x01\x03\x00\x00\x00\x63\x64\x73")

# ────────────────────────────── Directory Layout ──────────────────────────────
DOWNLOADED_DIR = "downloaded"   # EA squad data, always refreshed
BACKUP_DIR     = "backup"       # PS4 save backups (persistent across runs)
OUTPUT_DIR     = "output"       # Patched files, ready to copy back to PS4
INPUT_DIR      = "input"        # Local drop folder for saves when no USB is used

# ──────────────────────────── Platform Config ─────────────────────────────────
# All platforms served by EA's content server:
#   pc64  — PC (Windows 64-bit)
#   nx    — Nintendo Switch
#   nx2   — Nintendo Switch 2
#   ps4   — PlayStation 4
#   ps5   — PlayStation 5
#   xbsx  — Xbox Series X/S
#   xone  — Xbox One
ALLOWED_PLATFORMS = {"ps4"}

# Apollo save path (relative to USB drive root) and folder pattern
APOLLO_PATH        = os.path.join("PS4", "APOLLO")
APOLLO_SQUADS_GLOB = "*_*_Squads*"

# Windows drive type constants (returned by GetDriveTypeW)
DRIVE_REMOVABLE = 2
DRIVE_FIXED     = 3

# Fixed size of the EA-generated header prepended by save_squads()
SQUADS_HEADER_SIZE = 1126 + 48 + 4   # prefix_header + main_header + data_size field = 1178

# Filename stored in each backup folder to track the last successfully applied DB content
LAST_DB_HASH_FILE = ".last_db_hash"

# Max characters for the save-name portion of a backup container folder
SAVE_NAME_MAX_LEN = 26


# ═══════════════════════════════════════════════════════════════════════════════
#  LOW-LEVEL EA DOWNLOAD & PROCESSING  (unchanged logic from original script)
# ═══════════════════════════════════════════════════════════════════════════════

def download(fpath, url):
    """Download a file from url and write it to fpath."""
    print(f"  Downloading: {url}")
    with open(fpath, "wb") as f:
        try:
            response = urllib.request.urlopen(url)
            f.write(response.read())
        except Exception as e:
            print(f"  ERROR downloading: {e}")


def process_rosterupdate():
    """Fetch and parse the EA roster update manifest.
    Returns a dict with a 'platforms' list, each entry containing 'name' and 'tags'."""
    roster_url = f"{CONTENT_URL}fc/fclive/genxtitle/rosterupdate.xml"
    download(ROSTERUPDATE_XML, roster_url)

    result     = {"platforms": []}
    to_collect = ["dbMajor", "dbFUTVer", "dbMajorLoc", "dbFUTLoc"]
    try:
        root         = ET.parse(ROSTERUPDATE_XML).getroot()
        squadinfoset = root[0]
        for child in squadinfoset:
            platform = {
                "name": child.attrib["platform"],
                "tags": {node.tag: node.text for node in child.iter() if node.tag in to_collect},
            }
            result["platforms"].append(platform)
    except Exception as e:
        print(f"ERROR parsing roster update: {e}")

    return result


def unpack(fpath):
    """Decompress an EA RefPack-compressed .bin file.
    Returns (decompressed_bytes, decompressed_size)."""
    print(f"  Unpacking: {fpath}")

    SHORT_COPY  = 0x80
    MEDIUM_COPY = 0x40
    LONG_COPY   = 0x20

    with open(fpath, "rb") as f:
        data = f.read()

    size   = int.from_bytes(data[2:5], "big")
    outbuf = bytearray(size)
    outbuf[:len(T3DB)] = T3DB

    ipos, opos      = 10, len(T3DB)
    in_len, out_len = len(data), len(outbuf)
    last_control    = 0

    while ipos < in_len and opos < out_len:
        control      = data[ipos]
        last_control = control
        ipos        += 1

        if not (control & SHORT_COPY):
            b1 = data[ipos]; ipos += 1
            lit = control & 3
            if lit:
                outbuf[opos:opos+lit] = data[ipos:ipos+lit]; ipos += lit; opos += lit
            length = ((control >> 2) & 7) + 3
            offset = b1 + ((control & 0x60) << 3) + 1
            src    = opos - offset
            for _ in range(length):
                outbuf[opos] = outbuf[src]; opos += 1; src += 1

        elif not (control & MEDIUM_COPY):
            b2, b3 = data[ipos:ipos+2]; ipos += 2
            lit = b2 >> 6
            if lit:
                outbuf[opos:opos+lit] = data[ipos:ipos+lit]; ipos += lit; opos += lit
            length = (control & 0x3F) + 4
            offset = ((b2 & 0x3F) << 8 | b3) + 1
            src    = opos - offset
            for _ in range(length):
                outbuf[opos] = outbuf[src]; opos += 1; src += 1

        elif not (control & LONG_COPY):
            b2, b3, b4 = data[ipos:ipos+3]; ipos += 3
            lit = control & 3
            if lit:
                outbuf[opos:opos+lit] = data[ipos:ipos+lit]; ipos += lit; opos += lit
            length = b4 + ((control & 0x0C) << 6) + 5
            offset = (((control & 0x10) << 12) | (b2 << 8) | b3) + 1
            src    = opos - offset
            for _ in range(length):
                outbuf[opos] = outbuf[src]; opos += 1; src += 1

        else:  # literal copy
            lit = (control & 0x1F) * 4 + 4
            if lit > 0x70:
                break
            outbuf[opos:opos+lit] = data[ipos:ipos+lit]; ipos += lit; opos += lit

    trailing = last_control & 3
    if trailing and opos < out_len:
        end_pos = min(opos + trailing, out_len)
        outbuf[opos:end_pos] = data[ipos:ipos + (end_pos - opos)]

    return bytes(outbuf), size


def save_squads(buf, path, filename):
    """Build and write a Squads (or FUT Squads) save file with the EA header structure."""
    fullpath = os.path.join(path, filename)
    is_fut   = "Fut" in filename
    db_size  = len(buf)

    save_type_squads = b"SaveType_Squads\x00"
    save_type_fut    = b"SaveType_FUTSqu\x00"
    author_sign      = b"Aranaktu"

    # FC26 chunk sizes
    prefix_header_size = 1126
    main_header_size   = 48
    bnry_size          = 0 if is_fut else 45985
    file_size          = main_header_size + 4 + db_size + bnry_size

    # Build prefix header
    prefix_header = bytearray(prefix_header_size)
    pos = 0

    prefix_header[pos:pos+len(FBCHUNKS)] = FBCHUNKS
    pos += len(FBCHUNKS)

    main_header_offset = prefix_header_size - pos - 8
    prefix_header[pos:pos+4] = main_header_offset.to_bytes(4, "little"); pos += 4
    prefix_header[pos:pos+4] = file_size.to_bytes(4, "little");          pos += 4

    ingame_name = f"EA_{filename}".encode()[:40]
    prefix_header[pos:pos+len(ingame_name)] = ingame_name
    pos += len(ingame_name)

    sign_size = 4 if is_fut else 7
    pos += sign_size
    prefix_header[pos:pos+len(author_sign)] = author_sign

    # Build main header
    main_header = bytearray(main_header_size)
    save_type   = save_type_fut if is_fut else save_type_squads
    main_header[:len(save_type)] = save_type
    crc_pos = len(save_type)
    main_header[crc_pos:crc_pos+4] = (0).to_bytes(4, "little")

    data_size = 0 if is_fut else db_size + bnry_size

    with open(fullpath, "wb") as f:
        f.write(bytes(prefix_header))
        f.write(bytes(main_header))
        f.write(data_size.to_bytes(4, "little"))
        f.write(buf)
        if not is_fut:
            f.write(BNRY)
            f.write(b"\x00" * (bnry_size - len(BNRY)))

    return filename


# ═══════════════════════════════════════════════════════════════════════════════
#  DRIVE MANAGEMENT
# ═══════════════════════════════════════════════════════════════════════════════

def _get_volume_label(path):
    """Return the volume label for a Windows drive path (e.g. 'E:\\')."""
    buf = ctypes.create_unicode_buffer(261)
    ctypes.windll.kernel32.GetVolumeInformationW(
        ctypes.c_wchar_p(path), buf, 261, None, None, None, None, 0
    )
    return buf.value


def list_drives():
    """Return a list of dicts describing all logical drives on this Windows machine.
    Each dict contains: letter, path, type_id, type_label, label (volume name)."""
    type_names = {
        1: "No Root", 2: "Removable", 3: "Fixed",
        4: "Network",  5: "CD-ROM",   6: "RAM Disk",
    }
    drives  = []
    bitmask = ctypes.windll.kernel32.GetLogicalDrives()

    for letter in string.ascii_uppercase:
        if bitmask & 1:
            path    = f"{letter}:\\"
            type_id = ctypes.windll.kernel32.GetDriveTypeW(path)
            label   = ""
            try:
                label = _get_volume_label(path)
            except Exception:
                pass
            drives.append({
                "letter":     letter,
                "path":       path,
                "type_id":    type_id,
                "type_label": type_names.get(type_id, "Unknown"),
                "label":      label,
            })
        bitmask >>= 1

    return drives


def find_apollo_saves(search_dir):
    """Find Squads save folders matching *_*_Squads* directly under search_dir.
    Returns a list of absolute directory paths."""
    if not os.path.isdir(search_dir):
        return []
    return [p for p in glob(os.path.join(search_dir, APOLLO_SQUADS_GLOB)) if os.path.isdir(p)]


# ═══════════════════════════════════════════════════════════════════════════════
#  SAVE NAME EXTRACTION
# ═══════════════════════════════════════════════════════════════════════════════

_SAFE_CHARS_RE = re.compile(r"[^\w\s\-.]", re.ASCII)
_MULTI_SPACE_RE = re.compile(r"[\s_]+")


def _extract_save_name(data_path):
    """Extract the PS4 save name from the header of a DATA file.

    Header format:
      bytes 0-3  : uint32 LE — length of name including null terminator
      bytes 8-15 : 8-byte account/timestamp identifier (ignored)
      bytes 16+  : UTF-8 null-terminated save name

    Returns the decoded name string, or None on failure.
    """
    try:
        with open(data_path, "rb") as f:
            header = f.read(200)
        name_len = int.from_bytes(header[0:4], "little")
        if name_len < 1 or name_len > 128:
            return None
        raw = header[16 : 16 + name_len - 1]   # exclude null terminator
        return raw.decode("utf-8")
    except Exception:
        return None


def _safe_folder_name(name, max_len=SAVE_NAME_MAX_LEN):
    """Convert a PS4 save name to a safe folder name (Windows / Linux / macOS).

    Keeps ASCII alphanumeric, hyphens, dots; replaces whitespace / consecutive
    underscores with a single underscore; strips everything else; truncates to
    max_len characters.
    """
    safe = _SAFE_CHARS_RE.sub("", name)
    safe = _MULTI_SPACE_RE.sub("_", safe.strip())
    safe = safe[:max_len].strip("_")
    return safe or "unknown"


def _container_name_from_folder(save_folder_path):
    """Compute a human-readable backup container name for an Apollo save folder.

    Format: <userId>_<SafeSaveName>
    where userId is the first '_'-delimited segment of the Apollo folder name.
    """
    folder_name = os.path.basename(save_folder_path)
    user_id     = folder_name.split("_")[0]
    data_file   = os.path.join(save_folder_path, "DATA")
    save_name   = _extract_save_name(data_file)
    safe_name   = _safe_folder_name(save_name) if save_name else "unknown"
    return f"{user_id}_{safe_name}"


def _container_name_from_manual(data_file_path, identifier):
    """Compute a human-readable backup container name for a manually provided DATA file.

    Format: <identifier>_<SafeSaveName>
    """
    save_name = _extract_save_name(data_file_path)
    safe_name = _safe_folder_name(save_name) if save_name else "unknown"
    return f"{identifier}_{safe_name}"


# ═══════════════════════════════════════════════════════════════════════════════
#  BACKUP MANAGEMENT
# ═══════════════════════════════════════════════════════════════════════════════

def _find_apollo_subfolder(container_path):
    """Return the first Apollo save subfolder inside a backup container, or None."""
    candidates = [
        p for p in glob(os.path.join(container_path, APOLLO_SQUADS_GLOB))
        if os.path.isdir(p)
    ]
    return candidates[0] if candidates else None


def _get_data_path(container_path):
    """Return the path to DATA inside a backup container.

    Complete backups (Apollo subfolder present): DATA is inside the subfolder.
    Manual backups (DATA-only):                 DATA is directly in the container.
    """
    apollo_sub = _find_apollo_subfolder(container_path)
    if apollo_sub and os.path.isfile(os.path.join(apollo_sub, "DATA")):
        return os.path.join(apollo_sub, "DATA")
    return os.path.join(container_path, "DATA")


def _is_complete_backup(container_path):
    """Return True if the backup container has a full Apollo save subfolder."""
    return _find_apollo_subfolder(container_path) is not None


def backup_from_folder(save_folder_path, container_name):
    """Copy an Apollo save folder into backup/<container_name>/<apolloFolder>/.

    The container uses a human-readable name; the original Apollo folder is
    preserved as a subdirectory inside it.

    Returns the container path.
    Raises PermissionError if the source cannot be read.
    """
    container_path = os.path.join(BACKUP_DIR, container_name)
    apollo_dest    = os.path.join(container_path, os.path.basename(save_folder_path))
    os.makedirs(container_path, exist_ok=True)
    shutil.copytree(save_folder_path, apollo_dest, dirs_exist_ok=True)
    print(f"  Backup created: {container_path}")
    return container_path


def backup_manual(data_file_path, container_name):
    """Copy a single DATA file into backup/<container_name>/DATA.

    Returns the container path.
    """
    container_path = os.path.join(BACKUP_DIR, container_name)
    os.makedirs(container_path, exist_ok=True)
    shutil.copy2(data_file_path, os.path.join(container_path, "DATA"))
    print("  Warning: Incomplete save data, only DATA file present")
    print(f"  Backup created: {container_path}")
    return container_path


# ═══════════════════════════════════════════════════════════════════════════════
#  SQUAD DOWNLOAD
# ═══════════════════════════════════════════════════════════════════════════════

def download_squad_data():
    """Download fresh squad data from EA servers into DOWNLOADED_DIR (always from scratch).
    Returns the path to the PS4 Squads file, or None if PS4 data was not found."""

    # Always start fresh — no cache
    if os.path.isdir(DOWNLOADED_DIR):
        shutil.rmtree(DOWNLOADED_DIR)
    os.makedirs(DOWNLOADED_DIR)

    print("\nFetching roster update manifest...")
    roster   = process_rosterupdate()
    ps4_path = None

    for platform in roster.get("platforms", []):
        if platform["name"] not in ALLOWED_PLATFORMS:
            continue

        tags          = platform["tags"]
        platform_path = os.path.join(DOWNLOADED_DIR, platform["name"])
        os.makedirs(platform_path, exist_ok=True)
        print(f"\n[{platform['name'].upper()}]")

        # ── Squads ──────────────────────────────────────────────────────────
        ver      = tags["dbMajor"]
        ver_path = os.path.join(platform_path, "squads", ver)
        os.makedirs(ver_path, exist_ok=True)

        loc       = tags["dbMajorLoc"]
        bin_fname = os.path.basename(loc)
        bin_path  = os.path.join(ver_path, bin_fname)
        download(bin_path, f"{CONTENT_URL}{loc}")

        fdate           = bin_fname.split("_")[1]
        squads_filename = f"Squads{fdate}000000"
        buf, _          = unpack(bin_path)
        save_squads(buf, ver_path, squads_filename)

        if platform["name"] == "ps4":
            ps4_path = os.path.join(ver_path, squads_filename)

        # ── FUT ─────────────────────────────────────────────────────────────
        ver      = tags["dbFUTVer"]
        ver_path = os.path.join(platform_path, "FUT", ver)
        os.makedirs(ver_path, exist_ok=True)

        loc       = tags["dbFUTLoc"]
        bin_fname = os.path.basename(loc)
        bin_path  = os.path.join(ver_path, bin_fname)
        download(bin_path, f"{CONTENT_URL}{loc}")

        fdate = bin_fname.split("_")[1]
        buf, _ = unpack(bin_path)
        save_squads(buf, ver_path, f"FutSquads{fdate}000000")

    return ps4_path


# ═══════════════════════════════════════════════════════════════════════════════
#  PATCHING
# ═══════════════════════════════════════════════════════════════════════════════

def patch_squads(squads_path, data_path):
    """Apply the PS4 save header from data_path onto the downloaded Squads file.

    Steps:
      1. Strip the generated EA header (fixed 1178 bytes) from the Squads file.
      2. Locate T3DB (0x44 42 00 08) in DATA — everything before it is the PS4 header.
         Searches only after byte 1000 to skip any accidental 'DB' bytes in the save name.
      3. Zero the 4-byte checksum that immediately follows the 'Type_Squads\\x00' signature.
      4. Prepend the cleaned header to the squad DB content.

    Returns the patched bytes on success, or None on failure.
    """
    # ── 1. Extract DB content from Squads ────────────────────────────────────
    with open(squads_path, "rb") as f:
        squads = f.read()

    db_content = squads[SQUADS_HEADER_SIZE:]

    if db_content[:2] != b"DB":
        print(f"  ERROR: DB marker not found at Squads offset {SQUADS_HEADER_SIZE}")
        return None
    print(f"  DB confirmed at Squads offset {SQUADS_HEADER_SIZE} (0x{SQUADS_HEADER_SIZE:X})")

    # ── 2. Locate T3DB in DATA ───────────────────────────────────────────────
    with open(data_path, "rb") as f:
        data = f.read()

    t3db_pos = data.find(T3DB)
    if t3db_pos < 1000:
        print(f"  ERROR: T3DB not found after byte 1000 (found at {t3db_pos})")
        return None
    print(f"  T3DB in DATA at byte {t3db_pos} (0x{t3db_pos:X})")

    # ── 3. Build cleaned header ──────────────────────────────────────────────
    new_header = bytearray(data[:t3db_pos])

    ts_sig = b"Type_Squads\x00"
    ts_pos = new_header.find(ts_sig)
    if ts_pos == -1:
        print("  ERROR: 'Type_Squads\\x00' signature not found in DATA header")
        return None

    crc_offset = ts_pos + len(ts_sig)
    print(f"  Zeroing checksum at byte {crc_offset}: {bytes(new_header[crc_offset:crc_offset+4]).hex()}")
    new_header[crc_offset:crc_offset + 4] = b"\x00" * 4

    # ── 4. Assemble & validate ───────────────────────────────────────────────
    patched = bytes(new_header) + db_content

    if patched[t3db_pos:t3db_pos + 2] != b"DB":
        print("  ERROR: DB marker not at expected position in patched data")
        return None

    if len(patched) != len(data):
        print(f"  WARNING: size mismatch — original {len(data)} B, patched {len(patched)} B")
    else:
        print(f"  Size check passed: {len(patched)} bytes")

    return patched


# ═══════════════════════════════════════════════════════════════════════════════
#  OUTPUT
# ═══════════════════════════════════════════════════════════════════════════════

def create_output(backup_container, patched_data, is_complete):
    """Write the output files ready to be transferred to PS4.

    Mirrors the backup container structure:
    - Complete (Apollo subfolder present):
        output/<container>/<apolloFolder>/DATA  (patched)
        output/<container>/<apolloFolder>/*     (rest of save, copied from backup)
    - Incomplete (DATA-only):
        output/<container>/DATA                 (patched)

    Returns the output container directory path.
    """
    container_name = os.path.basename(backup_container)
    out_container  = os.path.join(OUTPUT_DIR, container_name)

    if os.path.isdir(out_container):
        shutil.rmtree(out_container)

    if is_complete:
        apollo_sub  = _find_apollo_subfolder(backup_container)
        apollo_name = os.path.basename(apollo_sub)
        out_apollo  = os.path.join(out_container, apollo_name)
        shutil.copytree(apollo_sub, out_apollo)
        data_out = os.path.join(out_apollo, "DATA")
    else:
        os.makedirs(out_container, exist_ok=True)
        data_out = os.path.join(out_container, "DATA")

    with open(data_out, "wb") as f:
        f.write(patched_data)

    return out_container


# ═══════════════════════════════════════════════════════════════════════════════
#  INTERACTIVE PROMPTS
# ═══════════════════════════════════════════════════════════════════════════════

def prompt_drive_selection():
    """List all drives and ask the user to pick one (or skip for manual mode).
    Returns the selected drive dict, or None if the user skips."""
    drives = list_drives()

    print("\nAvailable drives:")
    for i, d in enumerate(drives, 1):
        usb_tag   = " [USB]"      if d["type_id"] == DRIVE_REMOVABLE else ""
        label_tag = f" ({d['label']})" if d["label"] else ""
        print(f"  {i}. {d['path']}{usb_tag}{label_tag}")
    print("  0. Skip  (provide a DATA file manually)")

    while True:
        raw = input("\nSelect drive [0]: ").strip()
        if not raw or raw == "0":
            return None
        if raw.isdigit() and 1 <= int(raw) <= len(drives):
            return drives[int(raw) - 1]
        print("  Invalid selection, try again.")


def prompt_apollo_save(search_dir):
    """Find and let the user pick an Apollo Squads save folder inside search_dir.
    Returns the selected folder path, or None if nothing was found."""
    saves = find_apollo_saves(search_dir)

    if not saves:
        print(f"  No Squads saves found under {search_dir}.")
        print( "  Please copy the folder extracted with Apollo Save Tool to that location.")
        print( "  Folder name pattern:  <userId>_CUSA<titleNumber>_Squads<YYYYMMDDHHmmss>")
        print( "  Example:              1234567890_CUSA12345_Squads20260218093045")
        return None

    if len(saves) == 1:
        print(f"  Found: {os.path.basename(saves[0])}")
        return saves[0]

    print("\nMultiple saves found:")
    for i, s in enumerate(saves, 1):
        print(f"  {i}. {os.path.basename(s)}")

    while True:
        raw = input("Select save: ").strip()
        if raw.isdigit() and 1 <= int(raw) <= len(saves):
            return saves[int(raw) - 1]
        print("  Invalid selection, try again.")


def _prompt_existing_backup(name):
    """Ask whether to reuse an existing backup or overwrite it.
    Returns 'y' (keep existing) or 'n' (overwrite). Defaults to 'y' on Enter."""
    print(f"\nBackup already exists for '{name}'.")
    print("  [y] Use existing backup  — original files preserved, nothing will be re-copied  (default)")
    print("  [n] Overwrite backup     — WARNING: if the source DATA is corrupted,")
    print("                            the backup will be corrupted too")
    while True:
        ans = input("Choice [y]: ").strip().lower()
        if ans == "" or ans == "y":
            return "y"
        if ans == "n":
            return "n"
        print("  Please enter 'y' or 'n'.")


def _get_saved_db_hash(backup_path):
    """Return the SHA-256 hash saved from the last successful patch, or None if absent."""
    path = os.path.join(backup_path, LAST_DB_HASH_FILE)
    if os.path.isfile(path):
        with open(path, "r") as f:
            return f.read().strip()
    return None


def _save_db_hash(backup_path, db_hash):
    """Persist the SHA-256 hash of the applied DB content to the backup folder."""
    with open(os.path.join(backup_path, LAST_DB_HASH_FILE), "w") as f:
        f.write(db_hash)


def list_backups():
    """Return a sorted list of backup container paths."""
    if not os.path.isdir(BACKUP_DIR):
        return []
    return sorted(
        os.path.join(BACKUP_DIR, d)
        for d in os.listdir(BACKUP_DIR)
        if os.path.isdir(os.path.join(BACKUP_DIR, d))
    )


def prompt_backup_selection():
    """List existing backups and ask the user to pick one.
    Returns the selected container path, or None if no backups exist."""
    backups = list_backups()
    if not backups:
        print("\nNo backups found. Use 'Provide new save file' to create one first.")
        return None

    print("\nSaved backups:")
    for i, b in enumerate(backups, 1):
        print(f"  {i}. {os.path.basename(b)}")

    while True:
        raw = input("Select backup: ").strip()
        if raw.isdigit() and 1 <= int(raw) <= len(backups):
            return backups[int(raw) - 1]
        print("  Invalid selection, try again.")


def _prompt_usb_writeback(patched_data):
    """Interactively offer to write the patched DATA to a USB drive.

    Prompts the user to insert a USB, then selects the drive and Apollo save
    folder, then writes with retry / skip on failure.
    """
    print("\nDo you want to write the patched DATA to a USB drive?")
    ans = input("Insert USB and press Enter, or 'n' to skip [Enter]: ").strip().lower()
    if ans == "n":
        return

    # Find removable drives
    drives = [d for d in list_drives() if d["type_id"] == DRIVE_REMOVABLE]
    if not drives:
        print("  No removable drives found. Copy the output folder manually.")
        return

    # Select drive (auto if only one)
    if len(drives) == 1:
        usb_drive = drives[0]
        label_tag = f" ({usb_drive['label']})" if usb_drive["label"] else ""
        print(f"  Using drive: {usb_drive['path']}{label_tag}")
    else:
        print("\nAvailable USB drives:")
        for i, d in enumerate(drives, 1):
            label_tag = f" ({d['label']})" if d["label"] else ""
            print(f"  {i}. {d['path']}{label_tag}")
        while True:
            raw = input("Select drive: ").strip()
            if raw.isdigit() and 1 <= int(raw) <= len(drives):
                usb_drive = drives[int(raw) - 1]
                break
            print("  Invalid selection, try again.")

    # Find Apollo save folder on USB
    apollo_dir  = os.path.join(usb_drive["path"], APOLLO_PATH)
    save_folder = prompt_apollo_save(apollo_dir)
    if save_folder is None:
        print("  Skipping USB writeback. Copy the output folder manually.")
        return

    # Write with retry / skip
    dest = os.path.join(save_folder, "DATA")
    while True:
        try:
            with open(dest, "wb") as f:
                f.write(patched_data)
            print(f"  DATA written to USB: {dest}")
            return
        except (PermissionError, OSError) as e:
            print(f"  Failed: {e}")
            ans = input("  Press Enter to retry, or 'n' to skip: ").strip().lower()
            if ans == "n":
                print("  Failed. Copy the files manually from the output folder.")
                return


# ═══════════════════════════════════════════════════════════════════════════════
#  BACKUP ACQUISITION
# ═══════════════════════════════════════════════════════════════════════════════

def _acquire_from_file():
    """Provide-file flow: select a drive or provide DATA manually.

    Returns (backup_container, usb_folder) where usb_folder is the Apollo
    save folder on the removable USB (for automatic write-back), or None.
    """
    selected_drive = prompt_drive_selection()

    # ── No drive selected: look for DATA in input/ ────────────────────────────
    if selected_drive is None:
        os.makedirs(INPUT_DIR, exist_ok=True)
        data_in_input = os.path.join(INPUT_DIR, "DATA")

        if not os.path.isfile(data_in_input):
            all_files = [f for f in os.listdir(INPUT_DIR)
                         if os.path.isfile(os.path.join(INPUT_DIR, f))]
            if all_files:
                print(f"\nFiles found in {INPUT_DIR}/:")
                for f in all_files:
                    print(f"  • {f}")
            print(f"  ERROR: No DATA file found in {INPUT_DIR}/.")
            print(f"  Please rename or copy your PS4 save file to {INPUT_DIR}/DATA.")
            sys.exit(1)

        print(f"  Found DATA in {INPUT_DIR}/")

        identifier = input("Identifier name for this save (e.g. 'Gianni'): ").strip()
        if not identifier:
            identifier = "unknown"

        container_name = _container_name_from_manual(data_in_input, identifier)
        existing       = os.path.join(BACKUP_DIR, container_name)

        if os.path.isdir(existing):
            if _prompt_existing_backup(container_name) == "y":
                print(f"  Using existing backup: {existing}")
                return existing, None

        container = backup_manual(data_in_input, container_name)
        return container, None

    # ── Drive selected: find Apollo save folder ────────────────────────────────
    is_removable = selected_drive["type_id"] == DRIVE_REMOVABLE
    search_dir   = os.path.join(selected_drive["path"], APOLLO_PATH) if is_removable else INPUT_DIR

    if not is_removable:
        os.makedirs(INPUT_DIR, exist_ok=True)

    save_folder = prompt_apollo_save(search_dir)
    if save_folder is None:
        sys.exit(1)

    container_name = _container_name_from_folder(save_folder)
    existing       = os.path.join(BACKUP_DIR, container_name)

    if os.path.isdir(existing):
        if _prompt_existing_backup(container_name) == "y":
            print(f"  Using existing backup: {existing}")
            usb_folder = save_folder if is_removable else None
            return existing, usb_folder

    try:
        container = backup_from_folder(save_folder, container_name)
    except PermissionError as e:
        print(f"ERROR: permission denied reading drive: {e}")
        sys.exit(1)

    usb_folder = save_folder if is_removable else None
    return container, usb_folder


def acquire_backup():
    """Run the backup acquisition flow.

    First asks whether to use an existing backup or provide a new save file,
    then runs the appropriate sub-flow.

    Returns (backup_container, use_saved_hash, usb_folder):
      backup_container — path to the backup container directory
      use_saved_hash   — True if .last_db_hash should be the reference for the
                         update check (False → compare against DATA content directly)
      usb_folder       — Apollo save folder on removable USB for auto write-back,
                         or None
    """
    os.makedirs(BACKUP_DIR, exist_ok=True)

    print("\nWhat would you like to do?")
    print("  1. Use an existing backup  (check for / apply updates)")
    print("  2. Provide a new save file  (from USB, drive, or manually)")

    while True:
        raw = input("\nChoice [1]: ").strip()
        if not raw or raw == "1":
            mode = "use_backup"
            break
        if raw == "2":
            mode = "provide_file"
            break
        print("  Please enter 1 or 2.")

    if mode == "use_backup":
        container = prompt_backup_selection()
        if container is None:
            sys.exit(1)
        return container, True, None

    container, usb_folder = _acquire_from_file()
    return container, False, usb_folder


# ═══════════════════════════════════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════════════════════════════════

def write_back_to_usb(usb_folder_path, patched_data):
    """Overwrite the DATA file in the USB Apollo save folder with the patched version."""
    dest = os.path.join(usb_folder_path, "DATA")
    try:
        with open(dest, "wb") as f:
            f.write(patched_data)
        print(f"  DATA written to USB: {dest}")
    except (PermissionError, OSError) as e:
        print(f"  WARNING: could not write DATA to USB: {e}")


def main():
    print("=== FC26 PS4 Squad Updater ===")

    # ── Step 1: acquire backup ─────────────────────────────────────────────────
    backup_container, use_saved_hash, usb_folder = acquire_backup()

    data_path   = _get_data_path(backup_container)
    is_complete = _is_complete_backup(backup_container)

    if not os.path.isfile(data_path):
        print(f"ERROR: DATA file not found in backup: {data_path}")
        sys.exit(1)

    # ── Step 2: download fresh EA squad data ──────────────────────────────────
    print("\nDownloading squad data from EA servers...")
    squads_path = download_squad_data()
    if squads_path is None:
        print("ERROR: PS4 squad file could not be retrieved.")
        sys.exit(1)

    # ── Step 3: determine reference hash for the update check ─────────────────
    with open(squads_path, "rb") as f:
        squads_bytes = f.read()
    new_db      = squads_bytes[SQUADS_HEADER_SIZE:]
    new_db_hash = hashlib.sha256(new_db).hexdigest()

    if use_saved_hash:
        # "Use backup" flow — prefer saved hash so we know what was last applied,
        # fall back to DATA content on first run (no hash file yet).
        saved_hash = _get_saved_db_hash(backup_container)
        if saved_hash is None:
            with open(data_path, "rb") as f:
                backup_data = f.read()
            t3db_pos = backup_data.find(T3DB)
            if t3db_pos >= 1000:
                saved_hash = hashlib.sha256(backup_data[t3db_pos:]).hexdigest()
    else:
        # "Provide file" flow — always compare directly against the provided
        # DATA file's current DB content (reflects the real state of the PS4 save).
        with open(data_path, "rb") as f:
            backup_data = f.read()
        t3db_pos = backup_data.find(T3DB)
        saved_hash = hashlib.sha256(backup_data[t3db_pos:]).hexdigest() if t3db_pos >= 1000 else None

    if saved_hash == new_db_hash:
        print("\nNo updates available.")
        return

    # ── Step 4: patch ─────────────────────────────────────────────────────────
    print("\nPatching...")
    patched = patch_squads(squads_path, data_path)
    if patched is None:
        print("Patching failed.")
        sys.exit(1)

    # ── Step 5: write output ──────────────────────────────────────────────────
    print("\nWriting output...")
    out_path = create_output(backup_container, patched, is_complete)

    # Persist hash so subsequent "use backup" runs can detect no-update correctly
    _save_db_hash(backup_container, new_db_hash)

    print(f"\nA copy of the patched files has been saved to: {out_path}")

    # ── Step 6: USB write-back ─────────────────────────────────────────────────
    if use_saved_hash:
        # "Use backup" flow: offer interactive USB write-back
        _prompt_usb_writeback(patched)
    elif usb_folder:
        # "Provide file" flow with removable USB: automatic write-back
        print("\nWriting DATA back to USB...")
        write_back_to_usb(usb_folder, patched)


if __name__ == "__main__":
    main()
