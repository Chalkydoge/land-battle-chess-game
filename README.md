# Author: Yiwen (Victor) Song

Welcome to the Land Battle Chess Game.

If you do not know how to play, read this Wikipedia page:
https://en.wikipedia.org/wiki/Luzhanqi

## Local One-Click Run

This repository now provides a local web version with a one-click launcher for Windows.

### Recommended way

Double-click [run-local.bat](run-local.bat).

The launcher will:
- detect Python 3
- create `.venv` automatically if needed
- install dependencies from `requirements.txt`
- start the local web server on `127.0.0.1`
- open the game in your browser automatically

You can also start it from a terminal:

```powershell
.\run-local.bat
```

To stop the game, close the terminal window or press `Ctrl+C`.

## Requirements

- Windows
- Python 3.11 or newer
- internet access the first time you install dependencies

## Project Entrypoints

- [app.py](app.py): current local web version
- [run-local.bat](run-local.bat): Windows double-click launcher
- [run-local-launcher.ps1](run-local-launcher.ps1): launcher implementation used by the batch file

## Legacy Mode

The older socket + Tkinter multiplayer flow is still present for reference:
- [server.py](server.py)
- [__init__.py](__init__.py)

That flow is now considered legacy and is no longer the recommended startup path for local use.
