写在前面
========
lilac 是由百合仙子（依云/lilydjwg）为社区编译机写的编译机器人。该机器人通过与 ``nvchecker`` 配合检查软件包新的版本，并通过社区源软件包目录下的 ``lilac.py`` 脚本对有新版本释出的软件自动进行打包构建，减去了手工打包的麻烦。在此特别感谢仙子~

lilac 每日定时在社区编译机上执行，以检查软件的新版本及自动打包。

注意（非常重要）
---------------
1. Stephen Zhang/zsrkmyn 用血的经验告诉乃：任何情况下，维护者个人请勿在社区编译机上直接运行 ``lilac`` 或 ``lilacrun`` ，否则会导致严重后果！！！
 
2. 在本地调试时，请 **务必修改** lilac中的代码，注意以下几点：

 1. 注释 ``git_push()`` 相关代码，防止对远程仓库的污染；

 #. 修改 ``lilac`` 顶部定义的相关变量，以适应本地需求；

 #. 修改或注释 ``sendmail()`` 相关代码，防止对其他维护者发送出错时的报错邮件。


安装及配置
==========

在编译机上的配置
----------------

执行以下代码以获得一个较小的 lilac 调试环境： ::

  cd ~
  git clone https://github.com/archlinuxcn/lilac.git
  cd lilac
  wget "https://raw.githubusercontent.com/lilydjwg/winterpy/master/pylib/{archpkg,htmlutils,mailutils,myutils,nicelogger,serializer}.py"

**再次强调** ：维护者个人请勿直接运行 ``lilac`` 或 ``lilacrun`` ！！！

设置环境变量
------------
为了后续编写及调试 ``lilac.py`` 的方便，应当设置 ``PYTHONPATH`` 环境变量，使 python 能够使用 ``lilaclib`` 。如果使用了上述方法构建了 lilac 调试环境，使用以下代码设置环境变量： ::

  export PYTHONPATH=$PYTHONPATH:~/lilac

使用 lilac
==========

编写 lilac.py
-------------
每一个软件包对应一个 ``lilac.py`` ，该文件应当和软件的 ``PKGBUILD`` 在同一目录下。

``lilac.py`` 中定义了几个函数及变量， lilac 运行时会检查相关变量，并调用此文件中的相关函数。以下做详细说明：

函数
~~~~
pre_build()
  该函数在构建过程开始之前执行。通常用于修改直接从 AUR 获取到的 ``PKGBUILD`` ，以使构建过程能够正常进行。

post_build()
  该函数在 *成功* 构建软件包后执行，通常用于清理目录，运行 ``git add PKGBUILD`` 和 ``git commit`` 。

post_build_always(success)
  该函数在构建软件包后执行（无论是否构建成功）。 ``success`` 参数传入构建状态： ``True`` 表示构建成功， ``False`` 表示构建失败。

变量
~~~~
build_prefix
  str 类型，指定要使用的 devtools 中的构建工具的前缀，通常使用 ``'archlinuxcn-x86_64'`` ，构建 32 位包时通常使用 ``'multilib-archlinuxcn'`` 。详细信息请参考 `打包 <https://github.com/archlinuxcn/repo/wiki/%E6%89%93%E5%8C%85>`_ 。

depends
  list 类型，用于定义该软件包的依赖。构建软件包时首先检查此变量，若依赖没有被满足，则跳过该软件包构建其依赖，在其依赖构建成功后才会构建此软件包。

packages
  list 类型，用于定义 ``PACKAGE SPLITING (man 5 PKGBUILD)`` 。

测试 lilac.py
-------------
如果你已经完成了 ``lilac.py`` 的编写，并正确配置了 lilac 的运行环境，则可以在 ``lilac.py`` 最后加入以下代码进行测试： ::

  if __name__ == '__main__'
    single_main()

保存并运行 ``lilac.py`` ： ::

  ./lilac.py

更新 nvchecker.ini
------------------
要使 lilac 正确工作，还需要将软件包的信息添加到社区源仓库中的 ``nvchecker.ini`` 中。

详细信息请参看 `关于 nvchecker 的使用 <https://github.com/archlinuxcn/repo/wiki/%E5%85%B3%E4%BA%8Envchecker%E7%9A%84%E4%BD%BF%E7%94%A8>`_ 。

使用模板
--------
一些预定的模板已经为大家准备好，克隆 lilac 仓库后，模板位于 ``lilac/templates`` 中。详细的模板使用信息请参考 ``lilac/templates/README.rst`` 。

在线阅读 `README <https://github.com/archlinuxcn/lilac/tree/master/templates>`_ 。

Tips & Tricks
-------------
通过使用 ``lilaclib.py`` 中的函数、变量可以使 ``lilac.py`` 的编写变得简单。以下讲述一些技巧：

1. 在 ``lilac.py`` 中如果需要抓取网页内容（例如抓取版本号），可是使用 ``s`` 对象，这是一个在 ``lilaclib.py`` 中定义的一个 ``requests.Session`` 对象。具体实例可参考 `octave-general/lilac.py <https://github.com/archlinuxcn/repo/blob/master/octave-general/lilac.py>`_ 。

#. 在 ``lilac.py`` 中执行外部 shell 命令，可以使用 ``run_cmd`` 函数，该函数接受一个 list 类型参数，list 中每个元素为命令参数。例如，更新 ``PKGBUILD`` 中的 hash 值时，简单地使用 ``run_cmd(['sh', '-c', 'makepkg -g >> PKGBUILD'])`` 即可（注意删除原有的 hash 值）。

嗯，欢迎各位补充。

See also
========
repo 中已有的 ``lilac.py`` 。
