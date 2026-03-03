# FC26 PS4 Squad Updater — Wiki

Update your EA FC 26 PS4 squads with the latest EA data, without relaunching the game.

---

## Choose your tool

### Web Version *(no installation required)*

Open the app in your browser, drop your `DATA` file, and download the patched version.
Everything runs locally in your browser — your file is never uploaded anywhere.

→ **[Web Version guide](Web-Version)**

---

### Python CLI *(Windows, full-featured)*

A local script with backup management, automatic USB write-back, and update tracking.

→ **[Python CLI guide](Python-CLI)**

---

## How it works (overview)

EA distributes squad updates as compressed files on their CDN. Both tools:

1. Fetch the latest PS4 squad binary from EA's servers
2. Decompress it (EA RefPack format)
3. Replace the database embedded in your PS4 `DATA` save file, preserving your account header
4. Return the patched file — ready to restore via Apollo Save Tool

→ **[Technical Reference](Technical-Reference)** for full implementation details

---

## Quick navigation

| Page | Description |
|------|-------------|
| [Web Version](Web-Version) | How to use, privacy, self-hosting |
| [Python CLI](Python-CLI) | All flows, backup structure, configuration |
| [Technical Reference](Technical-Reference) | DATA format, patch algorithm, RefPack, architecture, credits |
