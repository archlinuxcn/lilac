#!/bin/python
from .abstract_runner import AbstractRunner
from ..lilacyaml import LilacDirectory

class LocalRunner(AbstractRunner):

    class BuildJob(AbstractRunner.BuildJob):

        def __init__(self, pkgbase: LilacDirectory, session='lilac'):
            super().__init__(pkgbase)
            self.runner_id = session

        def __start_build__(self):
            # run lilac_build command at pkgbase
            super().__start_build__()

        def stop(self):
            # rm -rf /var/lib/archbuild/build_prefix/session
            super().stop()

        def fail(self):
            # send log
            super().fail()

        def timeout(self):
            # kill process
            # send log
            super().timeout()

if __name__ == '__main__':
    # python -m lilac2.runner.local_runner
    import os
    from time import sleep

    pkgbase = LilacDirectory(os.path.expanduser('~/dummy'))
    runner = LocalRunner()
    runner.build(pkgbase)

    while not runner.jobs[0].is_stopped():
        print(runner)
        sleep(5)

    runner.post_build()
