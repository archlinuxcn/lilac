![lilac.png](https://github.com/archlinuxcn/artworks/raw/master/lilac-logo/example%20banners/banner-small.png)

依赖
====

配置
----

正确配置 Python 库路径 `PYTHONPATH` 及命令路径 `PATH`。批量更新时还需要无密码的 GPG 签名。

命令
----

* Python >= 3.7
* curl
* git
* makepkg
* zsh (batch)
* nvchecker (batch); 可选放置 keyfile 于 `~/.lilac/nvchecker_keyfile.toml`
* gpg (batch)
* Local MTA (batch)
* devtools (batch)
* [kill_children](https://github.com/lilydjwg/pid_children) (batch) (a suid program to kill all descendant processes of its parent)
* fakeroot (batch)

Python 库
---------

* requests
* lxml
* winterpy (will auto download if not available)
* toposort
* pyyaml
* toml
* pyalpm
* structlog
* prctl
