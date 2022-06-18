Notes on Arch Linux ARM
=======================

devtools
--------

Install ``devtools-archlinuxcn``, ``devtools-cn-git`` and ``devtools-arm-git``

``alarm/devtools-alarm`` is broken because ``MAKEFLAGS`` and ``PACKAGER`` aren't passed in. (It also doesn't ship ``extra-aarch64-build``)

``extra/devtools`` is broken because it cannot handle alarm mirror URL.

Building for a different arch
-----------------------------

ArchLinuxARM does not use the same file for `any` packages across different architectures. This means that chroot build for a different architecture (e.g. building armv7h on aarch64) may not work due to package signature mismatch.
