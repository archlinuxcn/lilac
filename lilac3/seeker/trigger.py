#!/bin/python

if __name__ == '__main__':
    import sys
    from recorder.models import Status

    pkgbase = sys.argv[1]
    print(f'Marking {pkgbase} as staled')
    status = Status.objects.get(key=pkgbase)
    if not status.status == 'STALED':
        status.status = 'STALED'
        status.save()
