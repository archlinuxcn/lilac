写在前面
========
lilac 是由百合仙子（a.k.a. `依云 <https://github.com/lilydjwg>`_\ ）为社区编译机写的编译机器人。该机器人通过与 `nvchecker <https://github.com/lilydjwg/nvchecker>`_ 配合检查软件包新的版本，并通过社区源软件包目录下的 ``lilac.{py,yaml}`` 文件对有新版本释出的软件自动进行打包构建，减去了手工打包的麻烦。在此特别感谢仙子~

安装及配置
==========

如果你想建立自己的仓库，可以安装并配置 lilac 以实现与 [archlinuxcn] 同样的自动化打包。

安装
----

lilac 可以从 [archlinuxcn] 仓库安装::

  pacman -S lilac-git

配置
----

``cp /usr/share/doc/lilac/config.toml.sample config.toml`` 并按照文件中的注释修改 ``config.toml`` 以适应本地需求。

使用 lilac
==========

编写 lilac.py
-------------
每一个软件包对应一个 ``lilac.py`` 及一个 ``lilac.yaml``\ ，该文件应当和软件的 ``PKGBUILD`` 在同一目录下。

``lilac.py`` 定义如何更新打包脚本。\ ``lilac.yaml`` 中定义打包相关的数据和元信息。可选的 ``package.list`` 中可以每行一个地列出 split package 会产生的包，避免额外的包被清理。

* `lilac.yaml 文档 <https://archlinuxcn.github.io/lilac/>`_
* `lilac.py API 文档 <https://lilac.readthedocs.io/en/latest/api.html>`_

测试 lilac.py
-------------

如果你已经完成了 ``lilac.py`` 的编写，并正确设置好了 ``PYTHONPATH`` 以及 ``PATH`` 环境变量，则可以在 ``lilac.py`` 最后加入以下代码进行测试： ::

  if __name__ == '__main__':
    single_main()

保存并运行 ``lilac.py``\ ： ::

  ./lilac.py

使用模板
--------
一些预定的模板已经为大家准备好，克隆 lilac 仓库后，模板位于 ``lilac/templates`` 中。详细的模板使用信息请参考 ``lilac/templates/README.rst``\ 。

在线阅读 `README <https://github.com/archlinuxcn/lilac/tree/master/templates>`_\ 。

Tips & Tricks
-------------
通过使用 ``lilaclib.py`` 中的函数、变量可以使 ``lilac.py`` 的编写变得简单。以下讲述一些技巧：

1. 在 ``lilac.py`` 中如果需要抓取网页内容（例如抓取版本号），可以使用 ``s`` 对象，这是一个在 ``lilaclib.py`` 中定义的一个 ``requests.Session`` 对象。

#. 在 ``lilac.py`` 中执行外部 shell 命令，可以使用 ``run_cmd`` 函数，该函数接受一个 list 类型参数，list 中每个元素为命令参数。如果指定了 ``use_pty=True``\ ，则会将子进程连接到 pty（伪终端）。如果指定了 ``silent=True``\ ，则不在日志文件中显示命令输出（因为这个命令的输出无甚价值）。

嗯，欢迎各位补充。

See also
========
`repo <https://github.com/archlinuxcn/repo>`_ 中已有的 ``lilac.py``\ 。
