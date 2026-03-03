/**
 * PS4 DATA file patcher — TypeScript port of patch_squads() from main.py.
 *
 * Takes the user's original PS4 Squads DATA file and replaces its embedded
 * database with the freshly downloaded EA database, while preserving the
 * original PS4 save header (account metadata, save name, etc.).
 */

// The 4-byte DB marker that separates the PS4 header from the database content
const T3DB = new Uint8Array([0x44, 0x42, 0x00, 0x08]);

// "Type_Squads\x00" — the signature whose 4-byte checksum we must zero
const TYPE_SQUADS_SIG = new Uint8Array([
  0x54, 0x79, 0x70, 0x65, 0x5f, 0x53, 0x71, 0x75, 0x61, 0x64, 0x73, 0x00,
]);

// Fixed 34-byte BNRY magic that opens the trailing block appended by save_squads()
const BNRY_MAGIC = new Uint8Array([
  0x42, 0x4E, 0x52, 0x59, 0x00, 0x00, 0x00, 0x02,
  0x4C, 0x54, 0x4C, 0x45, 0x01, 0x01, 0x03, 0x00,
  0x00, 0x00, 0x63, 0x64, 0x73, 0x01, 0x00, 0x00,
  0x00, 0x00, 0x01, 0x03, 0x00, 0x00, 0x00, 0x63,
  0x64, 0x73,
]);

// Total size of the BNRY trailing block (BNRY_MAGIC + zero padding)
const BNRY_BLOCK_SIZE = 45985;

/** Find the first occurrence of `needle` in `haystack` starting at `from`. */
function indexOf(haystack: Uint8Array, needle: Uint8Array, from = 0): number {
  outer: for (let i = from; i <= haystack.length - needle.length; i++) {
    for (let j = 0; j < needle.length; j++) {
      if (haystack[i + j] !== needle[j]) continue outer;
    }
    return i;
  }
  return -1;
}

export interface PatchResult {
  /** The fully patched DATA bytes, ready to be written back to the PS4 save. */
  data: Uint8Array<ArrayBuffer>;
}

/**
 * Patch a PS4 Squads DATA file with new database content.
 *
 * @param userData   The raw bytes of the user's original DATA file.
 * @param dbContent  The decompressed EA database bytes (output of refpack.decompress).
 *                   Must start with the T3DB marker (0x44 42 00 08 = "DB\x00\x08").
 * @returns          A PatchResult on success, or throws an Error with a description.
 */
export function patch(userData: Uint8Array, dbContent: Uint8Array): PatchResult {
  // Verify the DB content starts with the expected marker
  if (dbContent[0] !== 0x44 || dbContent[1] !== 0x42) {
    throw new Error(
      "DB marker not found at the start of the EA database. " +
      "The downloaded squad file may be corrupt."
    );
  }

  // Find T3DB in the DATA file, skipping the first 1000 bytes.
  // The skip avoids false matches in save names that contain "DB"
  // (e.g. a save named "Rose DB" would otherwise match at a low offset).
  const t3dbPos = indexOf(userData, T3DB, 1000);
  if (t3dbPos < 0) {
    throw new Error(
      "T3DB marker not found in the DATA file after offset 1000. " +
      "Make sure you uploaded a PS4 Squads DATA file, not a different save."
    );
  }

  // Extract the PS4 save header (everything before the database)
  const header = userData.slice(0, t3dbPos).slice(); // mutable copy

  // Locate the Type_Squads\x00 signature and zero the 4 checksum bytes after it.
  // The checksum would become invalid after swapping the database, so we clear it.
  const sigPos = indexOf(header, TYPE_SQUADS_SIG);
  if (sigPos < 0) {
    throw new Error(
      "Type_Squads signature not found in the DATA header. " +
      "Make sure you uploaded a PS4 Squads DATA file."
    );
  }
  const crcOffset = sigPos + TYPE_SQUADS_SIG.length;
  header.fill(0x00, crcOffset, crcOffset + 4);

  // Assemble the patched file: cleaned header + new database content + BNRY trailing block.
  // The BNRY block (45985 bytes: 34-byte magic + zero padding) mirrors what save_squads()
  // appends in the Python script, and is stripped/re-added by patch_squads() there.
  // Use an explicit ArrayBuffer so the result type is Uint8Array<ArrayBuffer>
  // (required by the Blob constructor in modern TypeScript).
  const totalSize = header.length + dbContent.length + BNRY_BLOCK_SIZE;
  const patched   = new Uint8Array(new ArrayBuffer(totalSize));
  patched.set(header,    0);
  patched.set(dbContent, header.length);
  patched.set(BNRY_MAGIC, header.length + dbContent.length);
  // remaining BNRY_BLOCK_SIZE - BNRY_MAGIC.length bytes are zero by default

  // Sanity check: the T3DB marker must be exactly at t3dbPos in the result
  if (patched[t3dbPos] !== 0x44 || patched[t3dbPos + 1] !== 0x42) {
    throw new Error("DB marker is not at the expected position in the patched file.");
  }

  return { data: patched };
}
