# FC26 PS4 Squad Updater

Update your EA FC 26 PS4 squads with the latest EA data — no need to relaunch the game.

**Two ways to use it:**

|  | Web Version | Python CLI |
|--|-------------|------------|
| No installation | ✅ | ❌ |
| Works on any OS | ✅ | Windows only |
| Internet required | ✅ | ✅ |
| Your file stays local | ✅ (browser only) | ✅ |

---

## Web Version

**[fc26-ps4-squadupdater.netlify.app](https://fc26-ps4-squadupdater.netlify.app/)**

Drop your `DATA` file, download the patched version.
All processing happens in your browser — your file is never uploaded anywhere.

→ **[docs/Web-Version.md](docs/Web-Version.md)**

---

## Python CLI

```bash
python main.py
```

Export your Squads save with [Apollo Save Tool](https://github.com/bucanero/apollo-ps4),
plug in your USB, run the script. Done.

Requires Python 3.8+ and Windows.

→ **[docs/Python-CLI.md](docs/Python-CLI.md)**

---

## Documentation

| Page | Description |
|------|-------------|
| [Python CLI](docs/Python-CLI.md) | Installation, all flows, backup structure, configuration |
| [Web Version](docs/Web-Version.md) | How to use, how it works, self-hosting on Netlify |
| [Technical Reference](docs/Technical-Reference.md) | Algorithms, DATA format, RefPack, architecture |

Full details also available on the [**Wiki**](https://github.com/ferrets6/FC26-PS4-SquadUpdater/wiki).

---

## Credits & Sources

- **[xAranaktu/FIFASquadFileDownloader](https://github.com/xAranaktu/FIFASquadFileDownloader)** — The original Python implementation: EA server communication, RefPack decompression, squad file assembly. This project builds directly on top of that work. License: MIT — Copyright 2021 Paweł (xAranaktu)
- **[How to manually patch the PS4 squad header (YouTube)](https://www.youtube.com/watch?v=your-video-id)** — Video walkthrough explaining the binary header replacement process that this tool automates. Provided the foundation for understanding the PS4 save file structure and the T3DB/Type_Squads checksum mechanics.
- **[Apollo Save Tool](https://github.com/bucanero/apollo-ps4)** — The PS4 homebrew app used to export and import saves via USB. Required for both the Python CLI and web version workflows.

---

## License

MIT — see [LICENSE](LICENSE).
