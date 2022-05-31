Routine Cleanups
================

tmpfiles.d
----------

This page records things should be configured to clean things up. Adjust if you want.

Pacman package cache: ``/etc/tmpfiles.d/pkgcache.conf``::

  e /var/cache/pacman - - - 20d

Lilac build logs and caches for builds: ``~/.config/user-tmpfiles.d``::

  e %h/.lilac/log - - - 30d
  
  e %h/.cargo/registry/cache/* - - - 30d
  e %h/.cargo/registry/src/* - - - 30d
  e %h/.cargo/checkouts/* - - - 30d
  
  e %h/.cache/archbuild-bind-cache/* - - - 30d
  e %h/.cache/pip/* - - - 30d

Start the timer:

.. code-block:: sh

  systemctl --user enable --now  systemd-tmpfiles-clean.timer

Cron jobs or systemd.timer
--------------------------

You need to run these scripts periodically:

build-cleaner

  Clean up chroots used by devtools: these chroots are re-usable but they can be too many.

  This script comes with lilac and requires root privileges.

lilac-cleaner

  Clean up files downloaded and extracted during packaging. They are in the git repository, side-by-side with PKGBUILDs and built packages. Use `lilac-cleaner` in the `scripts/` directory to clean them up. (Note a `-f` argument is needed to actually delete files.)

  You can also run this script locally.

  This script is in the ``scripts/`` directory of `lilac's source repository <https://github.com/archlinuxcn/lilac>`_.

repocleaner

  Clean up old packages inside the package repository.
  
  This script is at `repocleaner <https://github.com/archlinuxcn/misc_scripts/blob/master/repocleaner>`_ and should be edited before running. It should be run where the package repository is managed.

