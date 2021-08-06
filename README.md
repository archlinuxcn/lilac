![lilac.png](https://github.com/archlinuxcn/artworks/raw/master/lilac-logo/example%20banners/banner-small.png)

To run lilac on a build server, you'll need to install and setup.

Packages
----

You'll need the following:

* Python >= 3.9
* git
* devtools-cn-git from the [archlinuxcn] repo (you may get issues with devtools)
* [nvchecker](https://github.com/lilydjwg/nvchecker)
* gnupg
* fakeroot
* bubblewrap
* A Local MTA (e.g. postfix; a remote MTA works but you may have issues when the network glitches because no error handling is present)
* The command [kill_children](https://github.com/lilydjwg/pid_children) (a suid program to kill all descendant processes of its parent)

Python libraries
----

* requests
* lxml
* PyYAML
* toml
* pyalpm
* structlog
* prctl

Setup
----

lilac runs under a normal Linux user that has `sudo` setup to run devtools commands. It's prefered to use a dedicated user but it's not required. lilac will put its own data under `~/.lilac`.

Setup the git repository containing `PKGBUILD`. Give the account `git push` permissions (e.g. setup a ssh key without passphrase). The repository should have the structure `pkgbase/{PKGBUILD,lilac.yaml,...}` under the root or a subdirectory. Setup gpg so that you can sign files without entering a passphrase. No passphrase is expected by lilac.

Copy `config.toml.sample` to `config.toml` and edit as appropriate.

If you track GitHub or GitLab, get your API tokens and put your keyfile at `~/.lilac/nvchecker_keyfile.toml`.

Setup your mail server so that lilac can send out error reports.

lilac only produces packages and put them in a directory, but doesn't update the pacman repository database. You may use [archrepo2](https://github.com/lilydjwg/archrepo2) to do that.

Compile the `kill_children` binary and put it in `$PATH`, `chown` to root and `chmod u+s` so that it runs with root privileges.

The `build-cleaner` inside `scripts/` needs to be in `$PATH` and runs with `sudo` without a password to release space.

Setup a cron job, or a systemd.timer, or whatever to run lilac, e.g. `LANG=en_US.UTF-8 PATH=$HOME/bin:$PATH ~/soft/lilac/lilac`.

If you have a lot of memory (e.g. >100G), you may want to mount `/var/lib/archbuild` as a tmpfs.

There are other scripts in [misc_scripts](https://github.com/archlinuxcn/misc_scripts) that does things like cleanups, issue processing.

Usage
----

Please see [usage.rst](./usage.rst) (in Chinese).

License
-------

This project is licensed under GPLv3.
