Setup lilac
===========

In this article we'll see how to setup and configure lilac.

Installation
------------

It's recommended to run lilac on full-fledged Arch Linux (or derived) system, not in a Docker container or a different distribution.

An easy way to install lilac and its dependencies is to install the ``lilac-git`` package from the `[archlinuxcn] repository <https://wiki.archlinux.org/title/Unofficial_user_repositories#archlinuxcn>`_ or AUR.

As a workaround, instead of ``devtools``, ``devtools-archlinuxcn`` from ``[archlinuxcn]`` should be used until `this --keep-unit issue <https://gitlab.archlinux.org/archlinux/devtools/-/merge_requests/197>`_ is resolved.

.. code-block:: sh

  pacman -Syu lilac-git devtools-archlinuxcn

Lilac can store (and in the future use) a kind of build logs in a database. Let's use PostgreSQL this time. Support for other database may come in the future.

To use PostgreSQL, the following dependencies need to be installed (besides the database itself):

.. code-block:: sh

  pacman -S python-sqlalchemy python-psycopg2

Lilac can send error reports via email. A local mail transfer agent (MTA) is preferred (e.g. Postfix) but a remote one is supported too. We'll disable this in this article.

User and Data
-------------

Lilac needs a normal Linux user to run. You can create a dedicated user:

.. code-block:: sh

  useradd -m -g pkg lilac

The ``pkg`` group is created by the ``pid_children-git`` package, which lilac uses to clean up subprocesses. Users in this group have the power to kill subprocesses with root privileges. We'll configure this group to be able to build packages with devtools.

Remember to fully terminate existing processes and re-login (or more easily, reboot) to get the group privileges applied.

Lilac will use ``~/.lilac`` to store various data including build logs.

Make sure in ``/etc/makepkg.conf`` or similar files there aren't any changes to ``PKGDEST`` or the like, or lilac won't find them.

The ``PKGBUILD`` files needs to be in a git repo. A subdirectory inside it is recommended.

Setup a passphrase-less GPG key for the build user to sign packages:

.. code-block:: sh

  gpg --gen-key

Create a git repository for ``PKGBUILD``\ s and push it somewhere (e.g. GitHub). The directory structure is as follows::

  worktree root
  ├── README.md
  ├── .gitignore
  └── myrepo
      ├── pkgbase1
      │   ├── lilac.yaml
      │   └── PKGBUILD
      ├── pkgbase2
      │   ├── lilac.yaml
      │   ├── PKGBUILD
      └── pkgbase3
          ├── lilac.yaml
          ├── PKGBUILD
          └── pkgbase3.install

It contains a directory of pkgbase-named directories which contain PKGBUILDs, and a couple of other files you may want.

Generate a pair of ssh keys, and configure ssh / git so that you can push via ssh to the git repository above.

.. code-block:: sh

  ssh-keygen -t ed25519

Configure lilac
---------------

It's time to configure lilac now. Login as the user which lilac will run as first. Other than a fresh login, we can switch users with ``machinectl`` (don't use ``su`` or ``sudo`` to switch user, but if you can use ``sudo machinectl`` if needed):

.. code-block:: sh

  machinectl shell lilac@

Clone the git repository for ``PKGBUILD``\ s:

.. code-block:: sh

  git clone git@github.com:myorg/myrepo-pkgbuilds

Create a directory for built packages:

.. code-block:: sh

  mkdir ~/packages

Copy ``/usr/share/doc/lilac/config.toml.sample`` to ``~/.lilac/config.toml`` and edit it. We'll change the following options in this article.

In the ``[envvars]`` section we set ``TZ`` to control the timezone lilac uses. It affects timestamps in various places including the log file.

In the ``[repository]`` section:

name
  the repository name: ``myrepo`` in this article.

email
  an email address for undirected error reports (e.g. a list address that all maintainers will receive messages from): ``repo@localhost`` in this article.

repodir
  path to the directory containing all the ``PKGBUILD`` directories: ``/home/lilac/myrepo-pkgbuilds/myrepo`` in this article.

destdir
  where built packages go: ``/home/lilac/packages`` in this article.

In the ``[lilac]`` section:

name
  the bot's name. The error report mails will be sent from this name and have it in the subject.

email
  the address where lilac sends mails from. This should be the same one lilac uses for git commits.

master
  email address of the admin of this lilac instance. In case of any unhandled errors a report will be sent here. E.g. ``Admin <lilac-admin@example.net>``.

rebuild_failed_pkgs
  Whether to rebuild failed packages. We assume a failed package won't recover by itself and so set to ``false`` to avoid needless rebuilds.

git_push
  If this is set to ``true``, lilac pushes updated ``PKGBUILD``\ s to the remote git repository. We also need to generate a ssh key and configure it so that git pushes succeed. In this article we keep it ``false``.

send_email
  We'll disable this and keep it ``false``. No error reports will be sent in this case.

logurl
  We can make the build logs public via HTTP(S) with some web server, e.g.  https://github.com/imlonghao/archlinuxcn-packages. This option configures the URL pointing to the log, and will appear in the error report.

  Three placeholder is available:

  - pkgbase
  - datetime: a ``%Y-%m-%dT%H:%M:%S`` format time when this batch of build starts (corresponding to the directory name in ``~/.lilac/log``)
  - timestamp: UNIX timestamp (in seconds) when the error report generates

github_token
  A GitHub token to retrieve maintainer's public email address from their login, so they don't need to configure an email address in ``lilac.yaml``.

dburl
  The database URL in SQLAlchemy's format. For local PostgreSQL we use ``postgresql:///``.

max_concurrency
  limit the concurrent builds at the same time.

If you track GitHub or GitLab, get your API tokens and put your keyfile at ``~/.lilac/nvchecker_keyfile.toml`` (see `nvchecker's documentation <https://nvchecker.readthedocs.io/en/latest/>`_ for details).

Configure other parts
---------------------

Setup the database server if you don't already have one (run as root):

.. code-block:: sh

  pacman -S postgresql
  su - postgres -c "initdb --locale en_US.UTF-8 -D '/var/lib/postgres/data'"
  systemctl enable --now postgresql

Create the database user and database if needed:

.. code-block:: sh

  su - postgres -c 'createuser lilac'
  su - postgres -c 'createdb -O lilac lilac'

You should be able to login into the database server now.

Setup the database tables (run as lilac):

.. code-block:: sh

  psql ANY_ARGS_YOU_MAY_NEED < /usr/share/doc/lilac/dbsetup.sql

Edit ``/etc/sudoers`` like::

  Defaults env_keep += "PACKAGER MAKEFLAGS GNUPGHOME BUILDTOOL LOGDEST"

  %pkg ALL= NOPASSWD: /usr/bin/build-cleaner, /usr/bin/extra-x86_64-build, /usr/bin/multilib-build

The first line to allow setting some environment variables and the second line is to configure packagers to run build commands without a password. You should add all devtools commands you'll need to run. ``build-cleaner`` is a script to clean up build chroots which lilac may run.

Add something like this to ``/etc/profile.d/build.sh`` (at least update the domain name):

.. code-block:: sh

  NPROC="$(nproc)"
  export MAKEFLAGS="-j$NPROC"
  unset NPROC

  if groups | grep -q "\<pkg\>"; then
    export PACKAGER="$USER <$USER@example.org>"
  fi

To avoid using too much CPU, you can use cgroups v2 and put the following in ``/etc/systemd/system/user@.service.d/resources.conf`` to fairly share CPU among users (and between system and users).

.. code-block:: ini

  [Service]
  CPUWeight=100

To avoid the OOM Killer killing maintainer's processes unfairly, add ``OOMScoreAdjust=0`` to the above file, and set ``DefaultOOMScoreAdjust=0`` in ``/etc/systemd/user.conf``.

If you have a lot of memory (e.g. >100G), you may want to mount ``/var/lib/archbuild`` as a tmpfs to speed up building.

Run
---

Let create our first lilac-managed package.

In ``~/myrepo-pkgbuilds/myrepo`` create our package directory and ``PKGBUILD``:

.. code-block:: sh

  mkdir testpkg && cd testpkg
  vim PKGBUILD

Create a minimal `lilac.yaml` file like this:

.. code-block:: yaml

  maintainers:
  - github: lilydjwg

  update_on:
  - source: manual
    manual: 1

Create a git commit and push it somewhere.

Now it's time to run ``lilac``:

.. code-block:: sh

  lilac

Check ``~/.lilac/log`` for the logs. If everything goes well, you can change the ``config.toml`` to do git pushes, send email reports, etc.

Setup a cron job or systemd.timer to run ``lilac`` periodically. Don't forget to make the user instance of systemd always run:

.. code-block:: sh

  loginctl enable-linger

lilac only produces packages and put them in a directory, but doesn't update the pacman repository database. You may use `archrepo2 <https://github.com/lilydjwg/archrepo2>`_ to do that.

Or you can upload packages to another server via the ``postrun`` config in ``~/.lilac/config.toml`` and run ``archrepo2`` and an HTTP server there.

You can also setup a `HTTP service for build status and logs <https://github.com/imlonghao/archlinuxcn-packages>`_.

There are a lot of files that are no longer needed. You'll need to setup `routine cleanup scripts <cleanup.html>`_ after things are working.

`archlinuxcn/misc_scripts <https://github.com/archlinuxcn/misc_scripts>`_ contains some auxiliary scripts for maintenance and GitHub issues.

