from __future__ import annotations

from pathlib import Path
import types

mydir = Path('~/.lilac').expanduser()
AUR_REPO_DIR = mydir / 'aur'
AUR_REPO_DIR.mkdir(parents=True, exist_ok=True)
PACMAN_DB_DIR = mydir / 'pacmandb'
PACMAN_DB_DIR.mkdir(exist_ok=True)
(mydir / 'gnupg').mkdir(exist_ok=True)

SPECIAL_FILES = ('package.list', 'lilac.py', 'lilac.yaml', '.gitignore')
OFFICIAL_REPOS = ('core', 'extra', 'community', 'multilib')

_G = types.SimpleNamespace()
# main process:
#   repo: Repo
#   mod: LilacMod
# worker:
#   repo: Repo (for sending reports; not loading all lilacinfos)
#   mod: LilacMod
#   built_version: Optional[str]
