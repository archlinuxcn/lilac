from pathlib import Path
import types

mydir = Path('~/.lilac').expanduser()
AUR_REPO_DIR = mydir / 'aur'
AUR_REPO_DIR.mkdir(parents=True, exist_ok=True)

SPECIAL_FILES = ('package.list', 'lilac.py', 'lilac.yaml', '.gitignore')

_G = types.SimpleNamespace()
# repo: Repo
# mod: LilacMod
