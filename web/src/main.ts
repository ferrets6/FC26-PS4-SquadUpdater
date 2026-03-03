import { decompress } from "./refpack";
import { patch }      from "./patcher";
import "./style.css";

// ─── DOM refs ────────────────────────────────────────────────────────────────

const dropZone     = document.getElementById("drop-zone")     as HTMLDivElement;
const dropDefault  = document.getElementById("drop-default")  as HTMLDivElement;
const dropLoaded   = document.getElementById("drop-loaded")   as HTMLDivElement;
const dropFilename = document.getElementById("drop-filename") as HTMLParagraphElement;
const statusEl     = document.getElementById("status")        as HTMLDivElement;
const downloadBtn  = document.getElementById("download-btn")  as HTMLButtonElement;

// ─── State ───────────────────────────────────────────────────────────────────

let patchedBlob: Blob | null = null;

// ─── Helpers ─────────────────────────────────────────────────────────────────

const T3DB_MARKER = new Uint8Array([0x44, 0x42, 0x00, 0x08]);

/** Find the T3DB marker in a DATA file, skipping the first 1000 bytes. */
function findT3db(data: Uint8Array): number {
  outer: for (let i = 1000; i <= data.length - 4; i++) {
    for (let j = 0; j < 4; j++) {
      if (data[i + j] !== T3DB_MARKER[j]) continue outer;
    }
    return i;
  }
  return -1;
}

/** Compute SHA-256 of a byte array and return it as a lowercase hex string. */
async function sha256hex(data: Uint8Array): Promise<string> {
  // Copy into a fresh ArrayBuffer — crypto.subtle.digest requires ArrayBuffer, not ArrayBufferLike
  const copy = new Uint8Array(data);
  const buf  = await crypto.subtle.digest("SHA-256", copy);
  return Array.from(new Uint8Array(buf))
    .map(b => b.toString(16).padStart(2, "0"))
    .join("");
}

// ─── Drop-zone state ─────────────────────────────────────────────────────────

function showFileInDropZone(name: string): void {
  dropDefault.hidden       = true;
  dropLoaded.hidden        = false;
  dropFilename.textContent = name;
}

// ─── Drag-and-drop ───────────────────────────────────────────────────────────

dropZone.addEventListener("dragenter", (e) => {
  e.preventDefault();
  dropZone.classList.add("is-dragging");
});

dropZone.addEventListener("dragover", (e) => {
  e.preventDefault(); // required to allow drop
});

dropZone.addEventListener("dragleave", (e) => {
  // Only remove class when leaving the drop zone itself, not a child element
  if (!dropZone.contains(e.relatedTarget as Node)) {
    dropZone.classList.remove("is-dragging");
  }
});

dropZone.addEventListener("drop", (e) => {
  e.preventDefault();
  dropZone.classList.remove("is-dragging");
  const file = e.dataTransfer?.files[0];
  if (file) void run(file);
});

// Click-to-browse
dropZone.addEventListener("click", openFilePicker);
dropZone.addEventListener("keydown", (e) => {
  if (e.key === "Enter" || e.key === " ") openFilePicker();
});

function openFilePicker() {
  const input    = document.createElement("input");
  input.type     = "file";
  input.onchange = () => {
    if (input.files?.[0]) void run(input.files[0]);
  };
  input.click();
}

// ─── Download ────────────────────────────────────────────────────────────────

/** Enable or disable the download button, with an optional tooltip reason. */
function setDownloadReady(ready: boolean, reason = ""): void {
  downloadBtn.disabled = !ready;
  downloadBtn.title    = reason;
}

downloadBtn.addEventListener("click", () => {
  if (!patchedBlob) return;
  const url = URL.createObjectURL(patchedBlob);
  const a   = document.createElement("a");
  a.href     = url;
  a.download = "DATA";
  a.click();
  // Revoke after a delay to ensure the browser has started the download
  setTimeout(() => URL.revokeObjectURL(url), 60_000);
});

// ─── Main pipeline ───────────────────────────────────────────────────────────

async function run(file: File): Promise<void> {
  // Reset state
  patchedBlob = null;
  setDownloadReady(false, "Processing…");
  showFileInDropZone(file.name);
  setStatus("loading", "Reading file…");

  try {
    // 1. Read the user's DATA file
    const userData = new Uint8Array(await file.arrayBuffer());

    // 2. Fetch the compressed squad .bin from the EA CDN (via the Netlify proxy)
    setStatus("loading", "Downloading squad update from EA servers…");
    const proxyRes = await fetch("/api/squad-proxy");
    if (!proxyRes.ok) {
      let msg = `Proxy error ${proxyRes.status}`;
      try {
        const body = await proxyRes.json() as { error?: string };
        if (body.error) msg = body.error;
      } catch { /* ignore */ }
      throw new Error(msg);
    }
    const binBytes = new Uint8Array(await proxyRes.arrayBuffer());

    // 3. Decompress (EA RefPack)
    setStatus("loading", "Decompressing…");
    const dbContent = decompress(binBytes);

    // 4. Check if the squads are already up to date
    setStatus("loading", "Checking for updates…");
    const t3dbPos = findT3db(userData);
    if (t3dbPos >= 0) {
      // Compare the DB portion only (same length as dbContent), ignoring the BNRY tail
      const [newHash, curHash] = await Promise.all([
        sha256hex(dbContent),
        sha256hex(userData.slice(t3dbPos, t3dbPos + dbContent.length)),
      ]);
      if (newHash === curHash) {
        setDownloadReady(false, "Squads are already up to date — no new patch available");
        setStatus("warning", "Squads are already up to date — no patch needed.");
        return;
      }
    }

    // 5. Patch the DATA file
    setStatus("loading", "Patching…");
    const result = patch(userData, dbContent);

    // 6. Done — prepare the download
    patchedBlob = new Blob([result.data], { type: "application/octet-stream" });
    setDownloadReady(true);
    setStatus("success", "Done! Your updated DATA file is ready to download.");

  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    setDownloadReady(false, `Error: ${msg}`);
    setStatus("error", msg);
  }
}

// ─── UI helpers ──────────────────────────────────────────────────────────────

function setStatus(type: "loading" | "success" | "warning" | "error", message: string): void {
  statusEl.className = `status is-${type}`;

  if (type === "loading") {
    // Spinner + text
    const spinner = document.createElement("span");
    spinner.className = "spinner";
    const text = document.createTextNode(message);
    statusEl.replaceChildren(spinner, text);
  } else {
    statusEl.textContent = message;
  }
}
