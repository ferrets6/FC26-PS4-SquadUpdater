/**
 * EA RefPack decompressor — TypeScript port of the Python implementation.
 *
 * The decompressed output always starts with the T3DB marker (0x44 42 00 08),
 * which is the beginning of the EA squad database.
 */

const T3DB = new Uint8Array([0x44, 0x42, 0x00, 0x08]);

const SHORT_COPY  = 0x80;
const MEDIUM_COPY = 0x40;
const LONG_COPY   = 0x20;

/**
 * Decompress a RefPack-compressed buffer.
 *
 * @param data  The raw compressed bytes (the .bin file from EA's CDN).
 * @returns     The decompressed database bytes, starting with the T3DB marker.
 * @throws      If the buffer is too short or the decompressed size field is invalid.
 */
export function decompress(data: Uint8Array): Uint8Array {
  if (data.length < 10) {
    throw new Error("Input buffer is too short to be a valid RefPack file");
  }

  // Decompressed size is a 3-byte big-endian integer at bytes 2-4
  const size = (data[2] << 16) | (data[3] << 8) | data[4];
  if (size <= 0 || size > 64 * 1024 * 1024) {
    throw new Error(`Unexpected decompressed size: ${size}`);
  }

  const out     = new Uint8Array(size);
  let   ipos    = 10;           // compressed data starts after 10-byte header
  let   opos    = T3DB.length;  // output starts after the 4-byte T3DB seed
  const inLen   = data.length;
  const outLen  = out.length;
  let   lastCtl = 0;

  // Seed the output with the T3DB marker
  out.set(T3DB, 0);

  while (ipos < inLen && opos < outLen) {
    const ctl = data[ipos++];
    lastCtl   = ctl;

    if (!(ctl & SHORT_COPY)) {
      // ── 2-byte control: short back-reference + up to 3 literal bytes ───────
      const b1    = data[ipos++];
      const lit   = ctl & 3;
      for (let i = 0; i < lit; i++) out[opos++] = data[ipos++];
      const len    = ((ctl >> 2) & 7) + 3;
      const offset = b1 + ((ctl & 0x60) << 3) + 1;
      let   src    = opos - offset;
      for (let i = 0; i < len; i++) out[opos++] = out[src++];

    } else if (!(ctl & MEDIUM_COPY)) {
      // ── 3-byte control: medium back-reference + up to 3 literal bytes ──────
      const b2    = data[ipos++];
      const b3    = data[ipos++];
      const lit   = b2 >> 6;
      for (let i = 0; i < lit; i++) out[opos++] = data[ipos++];
      const len    = (ctl & 0x3f) + 4;
      const offset = ((b2 & 0x3f) << 8 | b3) + 1;
      let   src    = opos - offset;
      for (let i = 0; i < len; i++) out[opos++] = out[src++];

    } else if (!(ctl & LONG_COPY)) {
      // ── 4-byte control: long back-reference + up to 3 literal bytes ────────
      const b2    = data[ipos++];
      const b3    = data[ipos++];
      const b4    = data[ipos++];
      const lit   = ctl & 3;
      for (let i = 0; i < lit; i++) out[opos++] = data[ipos++];
      const len    = b4 + ((ctl & 0x0c) << 6) + 5;
      const offset = (((ctl & 0x10) << 12) | (b2 << 8) | b3) + 1;
      let   src    = opos - offset;
      for (let i = 0; i < len; i++) out[opos++] = out[src++];

    } else {
      // ── Literal run ─────────────────────────────────────────────────────────
      const lit = (ctl & 0x1f) * 4 + 4;
      if (lit > 0x70) break;   // end-of-stream sentinel
      for (let i = 0; i < lit; i++) out[opos++] = data[ipos++];
    }
  }

  // Copy any remaining literal bytes indicated by the last control byte
  const trailing = lastCtl & 3;
  if (trailing && opos < outLen) {
    const end = Math.min(opos + trailing, outLen);
    for (let i = opos; i < end; i++) out[i] = data[ipos++];
  }

  return out;
}
