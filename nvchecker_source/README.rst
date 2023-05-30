Version Control System (VCS) (git, hg, svn, bzr)
------------------------------------------------
::

  source = "vcs"

Check a VCS repo for new commits. The version returned is currently not related to the version of the software and will increase whenever the referred VCS branch changes. This is mainly for Arch Linux.

vcs
  The url of the remote VCS repo, using the same syntax with a VCS url in PKGBUILD (`Pacman`_'s build script). The first VCS url found in the source array of the PKGBUILD will be used if this option is omitted. (Note: for a blank ``vcs`` setting to work correctly, the PKGBUILD has to be in a directory with the name of the software under the path where nvchecker is run. Also, all the commands, if any, needed when sourcing the PKGBUILD need to be installed).

use_max_tag
  Set this to ``true`` to check for the max tag. Currently only supported for ``git``.
  This option returns the biggest tag sorted by ``pkg_resources.parse_version``.

This source supports `list options`_ when ``use_max_tag`` is set.

.. _list options: https://github.com/lilydjwg/nvchecker#list-options

ALPM files database
-------------------
::

  source = "archfiles"

Search package files in a local ALPM files database. The package does not need to be installed.

archfiles
  Name of the package.

filename
  Regular expression for the file name. If it contains a matching group, the first group is returned. Otherwise return the whole file name.

repo
  Name of the package repository in which the package resides. If not provided, search all repositories.

strip_dir
  Strip directory from the path before matching. Defaults to ``true``.

dbpath
  Path to the ALPM database directory. Lilac sets this automatically.

pkgpart
  Deprecated, use ``archfiles`` and ``repo`` instead. Has the form ``<repo>/<arch>/<packagename>``.
