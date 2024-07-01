import asyncio

import pytest
import pytest_asyncio

pytestmark = pytest.mark.asyncio(scope='session')

from nvchecker import core, __main__ as main
from nvchecker.util import Entries, RichResult, RawResult

async def run(entries: Entries) -> RichResult:
  task_sem = asyncio.Semaphore(20)
  result_q: asyncio.Queue[RawResult] = asyncio.Queue()
  keymanager = core.KeyManager(None)

  dispatcher = core.setup_httpclient()
  entry_waiter = core.EntryWaiter()
  futures = dispatcher.dispatch(
    entries, task_sem, result_q,
    keymanager, entry_waiter, 1, {},
  )

  oldvers: RichResult = {}
  result_coro = core.process_result(oldvers, result_q, entry_waiter)
  runner_coro = core.run_tasks(futures)

  vers, _has_failures = await main.run(result_coro, runner_coro)
  return vers

@pytest_asyncio.fixture(scope='session')
async def get_version():
  async def __call__(name, config):
    entries = {name: config}
    newvers = await run(entries)
    if r := newvers.get(name):
      return r.version

  return __call__


async def test_cran(get_version):
  assert await get_version('xml2', {
    'source': 'rpkgs',
    'pkgname': 'xml2',
    'repo': 'cran',
    'md5': True,
  }) == '1.3.6#fc6679028dca1f3047c8c745fb724524'

async def test_bioc(get_version):
  assert await get_version('BiocVersion', {
    'source': 'rpkgs',
    'pkgname': 'BiocVersion',
    'repo': 'bioc',
  }) == '3.19.1'

async def test_bioc_data_annotation(get_version):
  assert await get_version('GO.db', {
    'source': 'rpkgs',
    'pkgname': 'GO.db',
    'repo': 'bioc-data-annotation',
  }) == '3.19.1'

async def test_bioc_data_experiment(get_version):
  assert await get_version('ALL', {
    'source': 'rpkgs',
    'pkgname': 'ALL',
    'repo': 'bioc-data-experiment',
  }) == '1.46.0'

async def test_bioc_workflows(get_version):
  assert await get_version('liftOver', {
    'source': 'rpkgs',
    'pkgname': 'liftOver',
    'repo': 'bioc-workflows',
    'md5': True,
  }) == '1.28.0#336a9b7f29647ba8b26eb4dc139d755c'
