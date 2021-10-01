#!/bin/python
from .abstract_runner import AbstractRunner
from ..lilacyaml import LilacDirectory

class GithubActionsRunner(AbstractRunner):

    class BuildJob(AbstractRunner.BuildJob):

        def __init__(self, pkgbase: LilacDirectory, runner_repo, token):
            super().__init__(pkgbase)
            self.runner_repo = runner_repo
            self.token = token
            # self.runner_id = workflow_id will be set by github actions

        def __start_build__(self):
            # trigger action
            super().__start_build__()

        def stop(self):
            # save self.log_url to database
            super().stop()

        def success(self):
            # save self.patch_url to database
            # save self.package_url to database
            super().success()

        def timeout(self):
            # kill action
            super().timeout()

    def __init__(self, runner_repo, token, **kwargs):
        super().__init__(name=runner_repo, **kwargs)
        self.token = token

    def build(self, pkgbase: LilacDirectory):
        super().build(pkgbase, self.name, self.token)

    def available(self):
        if not super().available():
            return False
        # check github status

if __name__ == '__main__':
    # python -m lilac2.runner.github_actions_runner
    import os
    from time import sleep

    pkgbase = LilacDirectory(os.path.expanduser('~/dummy'))
    runner = GithubActionsRunner('name/actions-runner-x86_64', 'token', parallel=20)
    runner.build(pkgbase)

    while not runner.jobs[0].is_stopped():
        print(runner)
        sleep(5)
