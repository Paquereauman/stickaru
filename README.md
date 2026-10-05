<div align="center">

# <img src="chat_logo.png" alt="" height="46" align="absmiddle">&nbsp;Stickaru

### Your sticker and meme library for Windows: search, click, paste.

**English** · [Français](README.fr.md)

![windows](https://img.shields.io/badge/Windows-0078D6?style=for-the-badge&logo=windows&logoColor=white)
![python](https://img.shields.io/badge/Python-3.10+-3776AB?style=for-the-badge&logo=python&logoColor=white)
![version](https://img.shields.io/github/v/release/Paquereauman/stickaru?style=for-the-badge&color=2bb673)
![pygame](https://img.shields.io/badge/pygame-interface-2bb673?style=for-the-badge)
![api key](https://img.shields.io/badge/API%20key-none-f4a300?style=for-the-badge)

</div>

<p align="center"><img src="docs/capture.png" alt="Screenshot of Stickaru" width="860"></p>

---

## 📥 Download

Go to the **[Releases](../../releases/latest)** tab and download:

- **`Stickaru-Setup.exe`**: installer (installs into your user profile, creates Start menu and Desktop shortcuts, no administrator rights needed);
- **`Stickaru.exe`**: portable version, run it directly.

> Windows may show "Windows protected your PC" (SmartScreen) because the executables are not signed. Click *More info → Run anyway*.

## ✨ Features

| | |
|---|---|
| 🔎 **Search** | Animated stickers (Tenor, GIPHY), Telegram packs (public combot.org directory) and RisiBank, **with no API key and no sign-up**. |
| 📋 **One click = copied** | Click an image and it is copied to the clipboard (with transparency), ready to paste into WhatsApp, Discord, WeChat… |
| 💾 **My stickers** | Right-click to save to your local collection, ⭐ to mark a favourite. |
| 🔗 **Import by URL** | Paste the address of a sticker, a GIF or a pack to add it. |
| 🌍 **Multilingual interface** | French, English and Chinese (`langue.py`). |
| 🖥️ **Sharp rendering** | Per-monitor DPI support (Windows 10/11), light theme. |

## 🚀 Installation

```bash
pip install -r requirements.txt
python bibliotheque.py
```

### Build an executable (example)

```bash
pip install pyinstaller
pyinstaller --noconsole --onefile --icon chat.ico --name Stickaru bibliotheque.py
```

Or simply run the portable `Stickaru.exe` from the [Releases](../../releases/latest) page.

## 🗂️ Structure

```
bibliotheque.py   main interface (search, clipboard, favourites)
packs_index.json  index of recommended Telegram packs
sources.py        open-access sources (Tenor, GIPHY, Telegram/combot, RisiBank, URL)
langue.py         interface translations (fr / en / zh)
installer/        Windows installer sources (Python + PyInstaller)
docs/capture.png  screenshot
```

The `stickers/` and `memes/` folders and the caches are not in the repository: they are created and filled as you use the app.

## 🤝 Contributing

- **Bug or idea?** Open an [issue](https://github.com/Paquereauman/stickaru/issues).
- **Add a Telegram pack:** edit `packs_index.json` and open a pull request.
- See the [changelog](CHANGELOG.md) for what changed in each version.

## ⚠️ Good to know

Stickers belong to their authors. Stickaru only searches public content and copies it for personal use; please respect the terms of use of the sites it queries.

<div align="center">

[Source code](https://github.com/Paquereauman/stickaru) · [Releases](https://github.com/Paquereauman/stickaru/releases) · [MIT License](LICENSE)

</div>
