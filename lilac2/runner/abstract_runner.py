#!/bin/python
from datetime import datetime
from pathlib import Path
from ..cmd import run_cmd
from ..lilacyaml import LilacDirectory

class NotLilacDirectory(Exception):
    pass

class RunnerStatusError(RuntimeError):
    pass

class AbstractRunner:

    class BuildJob:

        def __init__(self, pkgbase: LilacDirectory):
            self.pkgbase = pkgbase
            self.status = 'INITIALIZED'
            self.runner_id = None
            self.package_url = None
            self.patch_url = None
            self.log_url = None

        def __start_build__(self):
            self.status = 'RUNNING'

        def start(self):
            if not self.status == 'INITIALIZED':
                raise RunnerStatusError('status is not INITIALIZED')

            self.start_time = datetime.now()
            try:
                self.__start_build__()
            except:
                self.fail()
                raise

        def is_stopped(self):
            if self.status in ['SUCCESS', 'FAIL', 'TIMEOUT']:
                return True
            return False

        def stop(self):
            self.stop_time = datetime.now()

        def success(self):
            self.status = 'SUCCESS'
            self.stop()

        def fail(self):
            self.status = 'FAIL'
            self.stop()

        def timeout(self):
            self.status = 'TIMEOUT'
            self.stop()

        def __str__(self):
            return f"<{type(self).__name__}({self.pkgbase}) status {self.status}>"

        __repr__ = __str__

    def __init__(self, name=None, parallel=1):
        self.name = type(self).__name__ if name is None else name
        self.parallel = parallel

        if type(self).BuildJob is AbstractRunner.BuildJob:
            raise NotImplementedError(f'Please specific {type(self).__name__}.BuildJob')

        self.jobs = self.read_jobs()

    def available(self):
        if len(self.jobs) >= self.parallel:
            return False
        return True

    def read_jobs(self):
        # Get from database according to self.name
        return []

    def build(self, pkgbase: LilacDirectory, *args, **kwargs):
        job = type(self).BuildJob(pkgbase, *args, **kwargs)
        job.start()
        self.jobs.append(job)
        # save job to database
        # self.jobs.append(job)

    def post_build(self, job: BuildJob):
        for job in self.jobs:
            if job.is_stopped():
                # delete job from database
                # sign packages
                # copy packages to archrepo folder
                pass

    def __str__(self):
        return f"<{type(self).__name__}({self.name}) jobs: {self.jobs}>"

    __repr__ = __str__
