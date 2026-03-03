# Web Version Guide

← [Back to README](../README.md)

---

## Table of Contents

- [How to Use](#how-to-use)
- [What Happens Step by Step](#what-happens-step-by-step)
- [Update Detection](#update-detection)
- [Privacy](#privacy)
- [Self-Hosting on Netlify](#self-hosting-on-netlify)
- [Limitations](#limitations)

---

## How to Use

1. Export your Squads save from your PS4 using [Apollo Save Tool](https://github.com/bucanero/apollo-ps4) to a USB drive
2. Copy the `DATA` file from the Apollo save folder to your computer
3. Open the web app
4. **Drop** the `DATA` file onto the page, or click to browse and select it
5. The app downloads the latest EA squad data, patches your file, and shows a download button
6. Download the updated `DATA` file and copy it back to the Apollo save folder on your USB
7. Plug the USB into your PS4 and restore the save with Apollo Save Tool

If your squads are already up to date, the app will tell you — no download will be offered.

---

## What Happens Step by Step

When you drop a file, the app runs this pipeline entirely in your browser:

1. **Read** — the `DATA` file is read into memory as a byte array
2. **Download** — the app fetches the latest PS4 squad `.bin` file from EA's CDN via a server-side proxy (needed only to bypass CORS headers — the proxy streams the file without storing it)
3. **Decompress** — the `.bin` is decoded using the EA RefPack algorithm (a custom LZ77-family compression)
4. **Check for updates** — a SHA-256 hash of the new EA database is compared against the same region in your `DATA` file; if they match, the squads are already up to date
5. **Patch** — if there is an update, your PS4 save header is extracted and prepended to the new database
6. **Download** — the patched file is offered as a download named `DATA`

→ See [Technical Reference](Technical-Reference.md) for implementation details.

---

## Update Detection

The hash comparison uses the raw decompressed EA database bytes (without the trailing BNRY block). Specifically:

- **New DB hash** = SHA-256 of the freshly decompressed EA data
- **Current DB hash** = SHA-256 of the same-length slice starting at the T3DB marker in your DATA file

If they are equal: `Squads are already up to date — no patch needed.`

---

## Privacy

- Your `DATA` file is **read locally** in the browser — it is never sent to any server
- The only network request is to `/api/squad-proxy`, which fetches the squad binary from EA's CDN; this request contains no user data
- No cookies, no analytics, no tracking

The footer on the page says: *"Your file never leaves your browser"* — this is technically accurate.

---

## Self-Hosting on Netlify

The web app requires a Netlify Edge Function as a proxy for EA's CDN (to bypass CORS restrictions). To host your own instance:

1. Fork this repository
2. Connect it to a Netlify site (Import from GitHub)
3. Set the branch to deploy (e.g. `main` or `website-version`)
4. Netlify reads `netlify.toml` automatically — no manual configuration needed

The build settings from `netlify.toml`:

```toml
[build]
  command = "cd web && npm run build"
  publish = "web/dist"

[[edge_functions]]
  function = "squad-proxy"
  path     = "/api/squad-proxy"
```

For local development:

```bash
# Install Netlify CLI globally (once)
npm install -g netlify-cli

# Install frontend dependencies
cd web && npm install && cd ..

# Start local dev server with Edge Function support
netlify dev
```

This starts Vite on port 5173 and the Netlify Edge Function runtime on port 8888. Open `http://localhost:8888`.

---

## Limitations

- **PS4 only** — the app downloads and patches only the PS4 squad file. Other platforms are not supported in the web version.
- **No backup** — unlike the Python CLI, the web version does not keep a local backup of your original DATA. Save it before dropping it if you want to keep a copy.
- **No `.last_db_hash`** — each session is stateless; the update check compares against the DATA you provide, not a stored hash from a previous session.
