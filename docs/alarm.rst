Notes on Arch Linux ARM
=======================

devtools
--------

Use ``devtools-archlinuxcn`` and manually setup for aarch64:

.. code-block:: sh

  ln -s archbuild /usr/bin/extra-aarch64-build
  cd /usr/share/devtools
  sed 's/x86[-_]64/aarch64/g' makepkg-x86_64.conf > makepkg-aarch64.conf

``alarm/devtools-alarm`` is broken because ``MAKEFLAGS`` and ``PACKAGER`` aren't passed in. (It also doesn't ship ``extra-aarch64-build``)

``archlinuxcn/devtools-arm-git`` is broken because it reports errors and bails out very early.
