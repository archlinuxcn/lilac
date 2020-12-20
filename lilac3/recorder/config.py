#!/bin/python

if __name__ == '__main__':
    import json
    from common.options import Options

    config = Options()
    config.ENGINE = 'django.db.backends.mysql'
    config.HOST = 'host'
    config.PORT = 'port'
    config.NAME = 'database'
    config.USER = 'username'
    config.PASSWORD = 'password'
    config.OPTIONS.charset = 'utf8mb4'
    config.OPTIONS.init_command = "SET sql_mode='STRICT_TRANS_TABLES'"

    print(json.dumps(config))
