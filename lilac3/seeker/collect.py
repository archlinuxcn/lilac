#!/bin/python

if __name__ == '__main__':
    import logging
    import sys
    import traceback
    from pathlib import Path
    import yaml
    import toml
    from tornado.log import enable_pretty_logging
    from tornado.options import options
    from common.options import Options

    options.logging = 'debug'
    logger = logging.getLogger()
    enable_pretty_logging(options=options, logger=logger)

    repository = Path(sys.argv[1])

    with open(Path(__file__).parent / 'aliases.yaml') as f:
        aliases = yaml.safe_load(f)

    config = Options()
    config.__config__.oldver = '/dev/null'
    config.__config__.newver = 'newver.json'

    for i in repository.rglob('lilac.yaml'):
        try:
            pkgbase = str(i.parent)[len(str(repository))+1:]
            with open(i) as f:
                lilac = yaml.safe_load(f)
            for j, update_on in enumerate(lilac['update_on']):
                if 'alias' in update_on.keys():
                    config[f'{pkgbase}:{j}'] = aliases[update_on['alias']]
                else:
                    for key, value in update_on.items():
                        if value is None:
                            update_on[key] = i.parent.name
                    config[f'{pkgbase}:{j}'] = update_on
            logger.debug('Loaded %s', pkgbase)
        except:
            logger.error(f'Failed to load %s', pkgbase)
            traceback.print_exc()

    with open('nvchecker.toml', 'w') as f:
        toml.dump(config, f)
