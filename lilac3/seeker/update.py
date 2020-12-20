#!/bin/python

if __name__ == '__main__':
    import os
    import sys
    import json
    import logging
    from datetime import datetime, timedelta
    from tornado.log import enable_pretty_logging
    from tornado.options import options
    from recorder.models import Status, Version
    from django.db.models import F

    options.logging = 'debug'
    logger = logging.getLogger()
    enable_pretty_logging(options=options, logger=logger)

    with open('newver.json') as f:
        newver = json.load(f)

    logger.info('Updating newver')
    for key, value in newver.items():
        try:
            record = Version.objects.get(key=key)
        except Version.DoesNotExist:
            record = Version(key=key)
        if record.newver != value:
            record.newver = value
            record.save()

    logger.info('Marking staled')

    for record in Version.objects.exclude(newver__exact=F('oldver')):
        key = record.key[:record.key.find(':')]
        try:
            status = Status.objects.get(key=key)
        except Status.DoesNotExist:
            status = Status(key=key)

        if status.status in ['', 'PUBLISHED']:
            status.status = 'STALED'
            status.save()
        elif status.status == 'ERROR' and datetime.now() - status.timestamp > timedelta(days=1):
            status.status = 'STALED'
            status.save()

        if status.status == 'STALED':
            logger.debug(f'{key}: {record.oldver} -> {record.newver}')
        else:
            logger.debug(f'{key}: {status.status} on {status.timestamp}')
