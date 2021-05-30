写在前面
========
lilac 是由百合仙子（a.k.a. `依云 <https://github.com/lilydjwg>`_\ ）为社区编译机写的编译机器人。该机器人通过与 `nvchecker <https://github.com/lilydjwg/nvchecker>`_ 配合检查软件包新的版本，并通过社区源软件包目录下的 ``lilac.py`` 脚本对有新版本释出的软件自动进行打包构建，减去了手工打包的麻烦。在此特别感谢仙子~

目前 lilac 每日北京时间1, 9, 17点17分在社区编译机上运行，以检查软件的新版本及自动打包。

注意（非常重要）
----------------
1. Stephen Zhang/zsrkmyn 用血的经验告诉乃：任何情况下，维护者个人请勿在社区编译机上直接运行 ``lilac``\ ，否则会导致严重后果！

2. 本地调试 lilac.py 文件，只需要设置好 ``PYTHONPATH`` 以及 ``PATH`` 环境变量，然后直接运行 ``./lilac.py``\ 。

3. 如果需要在本地调试 lilac 时，请\ **务必**\ 注意以下几点：

 1. ``cp config.ini.sample config.ini`` 并修改 ``config.ini`` 以适应本地需求；

 #. 设置 ``git_push=no`` 以防止对远程仓库的污染；

 #. 设置 ``send_email=no`` 以防止对其他维护者发送出错时的报错邮件，或者因为连接不上邮件服务器而出错。


安装及配置
==========

在编译机上的配置
----------------

执行以下代码以获得一个较小的 lilac 调试环境： ::

  cd ~
  git clone https://github.com/archlinuxcn/lilac.git
  cd lilac
  wget "https://raw.githubusercontent.com/lilydjwg/winterpy/master/pylib/"{archpkg,htmlutils,mailutils,myutils,nicelogger,serializer}.py

**再次强调**\ ：除非你很清楚 lilac 的运作，否则请勿直接运行 ``lilac``\ ！

设置环境变量
------------
为了后续编写及调试 ``lilac.py`` 的方便，应当设置 ``PYTHONPATH`` 环境变量，使 python 能够使用 ``lilaclib`` 。如果使用了上述方法构建了 lilac 调试环境，使用以下代码设置环境变量： ::

  export PYTHONPATH=$PYTHONPATH:$HOME/lilac:$HOME/lilac/vendor
  export PATH=$PATH:$HOME/lilac

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
如果你已经完成了 ``lilac.py`` 的编写，并正确配置了 lilac 的运行环境，则可以在 ``lilac.py`` 最后加入以下代码进行测试： ::

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

1. 在 ``lilac.py`` 中如果需要抓取网页内容（例如抓取版本号），可以使用 ``s`` 对象，这是一个在 ``lilaclib.py`` 中定义的一个 ``requests.Session`` 对象。具体实例可参考 `octave-general/lilac.py <https://github.com/archlinuxcn/repo/blob/master/octave-general/lilac.py>`_\ 。

#. 在 ``lilac.py`` 中执行外部 shell 命令，可以使用 ``run_cmd`` 函数，该函数接受一个 list 类型参数，list 中每个元素为命令参数。例如，更新 ``PKGBUILD`` 中的 hash 值时，简单地使用 ``run_cmd(['sh', '-c', 'makepkg -g >> PKGBUILD'])`` 即可（注意删除原有的 hash 值）。如果指定了 ``use_pty=True``\ ，则会将子进程连接到 pty（伪终端）。如果指定了 ``silent=True``\ ，则不在日志文件中显示命令输出（因为这个命令的输出无甚价值）。

嗯，欢迎各位补充。

See also
========
`repo <https://github.com/archlinuxcn/repo>`_ 中已有的 ``lilac.py``\ 。
