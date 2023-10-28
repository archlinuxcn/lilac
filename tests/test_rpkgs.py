import asyncio

import pytest
import pytest_asyncio

pytestmark = pytest.mark.asyncio

from nvchecker import core, __main__ as main
from nvchecker.util import Entries, VersData, RawResult

async def run(entries: Entries) -> VersData:
  task_sem = asyncio.Semaphore(20)
  result_q: asyncio.Queue[RawResult] = asyncio.Queue()
  keymanager = core.KeyManager(None)

  dispatcher = core.setup_httpclient()
  entry_waiter = core.EntryWaiter()
  futures = dispatcher.dispatch(
    entries, task_sem, result_q,
    keymanager, entry_waiter, 1, {},
  )

  oldvers: VersData = {}
  result_coro = core.process_result(oldvers, result_q, entry_waiter)
  runner_coro = core.run_tasks(futures)

  vers, _has_failures = await main.run(result_coro, runner_coro)
  return vers

@pytest_asyncio.fixture(scope='module')
async def get_version():
  async def __call__(name, config):
    entries = {name: config}
    newvers = await run(entries)
    return newvers.get(name)

  return __call__

loop = asyncio.new_event_loop()
@pytest.fixture(scope='module')
def event_loop(request):
  yield loop
  loop.close()


async def test_cran(get_version):
  assert await get_version('xml2', {
    'source': 'rpkgs',
    'pkgname': 'xml2',
    'repo': 'cran',
    'md5': True,
  }) == '1.3.5#20780f576451bb22e74ba6bb3aa09435'

async def test_bioc(get_version):
  assert await get_version('BiocVersion', {
    'source': 'rpkgs',
    'pkgname': 'BiocVersion',
    'repo': 'bioc',
  }) == '3.18.0'

async def test_bioc_data_annotation(get_version):
  assert await get_version('GO.db', {
    'source': 'rpkgs',
    'pkgname': 'GO.db',
    'repo': 'bioc-data-annotation',
  }) == '3.18.0'

async def test_bioc_data_experiment(get_version):
  assert await get_version('ALL', {
    'source': 'rpkgs',
    'pkgname': 'ALL',
    'repo': 'bioc-data-experiment',
  }) == '1.44.0'

async def test_bioc_workflows(get_version):
  assert await get_version('liftOver', {
    'source': 'rpkgs',
    'pkgname': 'liftOver',
    'repo': 'bioc-workflows',
    'md5': True,
  }) == '1.26.0#65b97e4b79a79c7a4bbdebcb647f1faf'
