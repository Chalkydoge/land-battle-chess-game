# Author: Yiwen (Victor) Song

## Secondary Development Notice

This repository is a secondary development based on the original Land Battle Chess project by Yiwen (Victor) Song.

- Original project author: Yiwen (Victor) Song
- Secondary development and maintenance: doge
- License: MIT

This project follows the MIT License requirements. The original copyright notice and the MIT License text are retained in the [LICENSE](LICENSE) file.

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

## One-Click Update And Run (For Other Machines)

If this project was cloned by Git on another machine, you can update to the latest code and start the app in one click.

### Recommended way

Double-click [update-and-run.bat](update-and-run.bat).

This script will:
- check that the folder is a Git repository
- abort when local uncommitted changes exist (to avoid overwrite)
- pull the latest code by fast-forward only
- start the local launcher automatically after update

You can also run it in PowerShell:

```powershell
.\update-and-run.ps1
```

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
