前言
====
这个分支提供一些 ``lilac.py`` 的模板，以便新建 ``lilac.py`` 时使用。

模板文件
========

lilac.py-aur_simple
-------------------
最简单的 ``lilac.py`` ，适用于绝大多数 AUR 软件包。

lilac.py-aur_complex
--------------------
复杂版本的 ``lilac.py`` ，通常在以下几种情况下使用：

1. AUR 中的 ``PKGBUILD`` 已经 ``out-of-date`` ，但是希望通过 AUR 中的 ``PKGBUILD`` 来构建软件包，需要修改 ``pkgver`` 和 hash 值时；
#. AUR 中的 ``PKGBUILD`` 修改包括依赖、构建函数等才能正确构建软件包时；
#. 通过 sourceforge 等其他网站直接检查版本更新，但希望通过修改 AUR 中的 ``PKGBUILD`` 来构建软件包时。

* See also:

 + `repo/chrome-remote-desktop <https://github.com/archlinuxcn/repo/blob/master/chrome-remote-desktop/lilac.py>`_

lilac.py-pypi
-------------
从 PyPI 直接构建软件包时使用，除了依赖，几乎不需要进行修改。

lilac.py-custom
---------------
自定义 ``lilac.py`` ，复杂情况下使用。

* See also:

 + `repo/vim-lily <https://github.com/archlinuxcn/repo/blob/master/vim-lily/lilac.py>`_
