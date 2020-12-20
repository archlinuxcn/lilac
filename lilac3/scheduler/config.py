#!/bin/python

if __name__ == '__main__':
    import json
    from common.options import Options

    config = Options()

    #config.ResouceGroupName.max_parallel = 20
    config.default = 'GitHubActions'
    config.GitHubActions.max_parallel = 20
    config.x86_64.max_parallel = 1
    config.arm.max_parallel = 1

    print(json.dumps(config))
