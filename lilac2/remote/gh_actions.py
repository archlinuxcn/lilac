from __future__ import annotations

from typing import List, Iterable, Dict, Any, Tuple
from collections import defaultdict
import logging
import os
import zipfile

from github import GitHub
from archpkg import pkgfile_pat

from ..typing import DepDesc
from .utils import RepoDownloader, PKG_CACHE_DIR

logger = logging.getLogger(__name__)

def _download_to(r: Any, filename: str) -> None:
  partfile = filename + '.part'
  with open(partfile, 'wb') as fd:
    for chunk in r.iter_content(chunk_size=4096):
      fd.write(chunk)
  os.rename(partfile, filename)

def _extract_zip(filename: str, pkgname: str) -> str:
  logger.info('Extracting pkgname %s from file %s',
              pkgname, filename)
  dir = os.path.dirname(filename)
  with zipfile.ZipFile(filename) as zip:
    for name in zip.namelist():
      if pkgfile_pat.match(name):
        zip.extract(name,  path=dir)
        logger.info('Found %s', name)
        return os.path.join(dir, name)
  raise FileNotFoundError(pkgname)

def download_packages(
  repo: str, 
  gh: GitHub,
  pkgs: Iterable[DepDesc],
  repo_name: str,
  servers: List[str],
) -> List[str]:
  artifacts = [x for x in gh.get_actions_artifacts(repo)]
  want = defaultdict(list)
  for d in pkgs:
    want[d.pkgbase].append(d.pkgname)

  download: Dict[Tuple[str, str], List[str]] = {}
  for artifact in artifacts:
    if artifact['name'] in want:
      download[
        (artifact['id'], artifact['archive_download_url'])
      ] = want.pop(artifact['name'])

  files: List[str] = []

  logger.info('Downloading artifacts: %r', download)
  s = gh.session
  for (aid, url), pkgnames in download.items():
    filename = os.path.join(PKG_CACHE_DIR, f'{aid}.zip')
    if not os.path.exists(filename):
      logger.info('Downloading %s', url)
      r = s.get(url, stream=True)
      _download_to(r, filename)
    else:
      logger.info('Using cached file for %s', url)

    for pkgname in pkgnames:
      files.append(_extract_zip(filename, pkgname))

  logger.info('Downloading from repo: %r', want)

  pkgnames2: List[str] = []
  for v in want.values():
    pkgnames2.extend(v)

  r = RepoDownloader(repo_name, servers)
  files.extend(r.download(pkgnames2))

  return files
