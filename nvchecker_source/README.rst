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

R packages from CRAN and Bioconductor
-------------------------------------
::

  source = "rpkgs"

Check versions from CRAN and Bioconductor. This source is optimized for checking large amounts of packages at once. If you want to check only a few, the ``cran`` source is better for CRAN packages.

pkgname
  Name of the R package.

repo
  The repo of the package. Possible values are ``cran``, ``bioc``, ``bioc-data-annotation``, ``bioc-data-experiment`` and ``bioc-workflows``.

md5
  If set to ``true``, a ``#`` character and the md5sum of the source archive is appended to the version. Defaults to ``false``.
