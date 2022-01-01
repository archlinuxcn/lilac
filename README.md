![lilac.png](https://github.com/archlinuxcn/artworks/raw/master/lilac-logo/example%20banners/banner-small.png)

What does lilac do?
----

lilac is an automatic packaging tool for Arch Linux. It basically does the following things:

* figure out which packages have been updated or need rebuilding by calling [nvchecker](https://github.com/lilydjwg/nvchecker)
* figure out the order to build packages
* generate or update PKGBUILDs with custom configuration scripts ([common routines avaiable](https://lilac.readthedocs.io/en/latest/api.html))
* call devtools to actually build packages
* handle built packages over to [archrepo2](https://github.com/lilydjwg/archrepo2) to update the repository database
* report any errors to maintainers via mail

To run lilac on a build server, you'll need to install and setup.

Why a SQL database?
----

lilac can optionally record build results in a SQL database. This can be used to generate webpages about building logs and status and arrange parallel builds in a more efficient way.

Packages
----

You can install from [archlinuxcn] or AUR and the dependencies will be installed for you.

If you want to run manually (or you're the packager for lilac), you'll need the following:

* Python >= 3.9
* git
* devtools-cn-git from the [archlinuxcn] repo (you may get issues with devtools)
* [nvchecker](https://github.com/lilydjwg/nvchecker)
* gnupg
* fakeroot
* bubblewrap
* pacman-contrib
* A Local MTA (e.g. postfix; a remote MTA works but you may have issues when the network glitches because no error handling is present)
* The command [kill_children](https://github.com/lilydjwg/pid_children) (a suid program to kill all descendant processes of its parent). You may need to add the build user to `pkg` group to use it (use `ls -l $(which kill_children)` to check). Note that there may be security implications for people who can execute this program.
* A SQL database supported by SQLAlchemy (optional)

Python libraries
----

* requests
* lxml
* PyYAML
* tomli
* tomli-w
* pyalpm
* structlog
* prctl
* sqlalchemy (optional; plus the database driver you configure to use)

Setup
----

lilac runs under a normal Linux user that has `sudo` setup to run devtools commands. It's prefered to use a dedicated user but it's not required. lilac will put its own data under `~/.lilac`.

Setup the git repository containing `PKGBUILD`. Give the account `git push` permissions (e.g. setup a ssh key without passphrase). The repository should have the structure `pkgbase/{PKGBUILD,lilac.yaml,...}` under the root or a subdirectory. Setup gpg so that you can sign files without entering a passphrase. No passphrase is expected by lilac.

Copy `config.toml.sample` to `config.toml` and edit as appropriate.

If you track GitHub or GitLab, get your API tokens and put your keyfile at `~/.lilac/nvchecker_keyfile.toml`.

Setup your mail server so that lilac can send out error reports. You may want to disable mail during testing though.

Setup your database if you configure to use one.

lilac only produces packages and put them in a directory, but doesn't update the pacman repository database. You may use [archrepo2](https://github.com/lilydjwg/archrepo2) to do that.

Make sure you have `kill_children` install as privileged program. Try to execute: `kill_children && echo ok`. If you install from [archlinuxcn] or AUR, you'll need to be in the `pkg` group (remember to re-login after modifying your groups). Note taht there may be security implications for people who can execute this program.

The `build-cleaner` inside `scripts/` needs to be in `$PATH` and runs with `sudo` without a password to release space.

Setup a GPG key to sign packages without a passphrase.

Setup a cron job, or a systemd.timer, or whatever to run lilac, e.g. `LANG=en_US.UTF-8 PATH=$HOME/bin:$PATH ~/soft/lilac/lilac`.

If you have a lot of memory (e.g. >100G), you may want to mount `/var/lib/archbuild` as a tmpfs.

There are other scripts in [misc_scripts](https://github.com/archlinuxcn/misc_scripts) that does things like cleanups, issue processing.

Usage
----

Please see [usage.rst](./usage.rst) (in Chinese).

License
-------

This project is licensed under GPLv3.
