# `lilac.py` 文件说明

## 打包流程
* `pre_build`: 打包前执行的函数。
* `post_build`: 打包成功后执行的函数。
* `post_build_always`: 打包最后执行的函数，不论成功与否。可选。

## 辅助信息
* `build_prefix`: 打包命令的前缀，如 `extra-x86_64`、`multilib`、`archlinuxcn-x86_64` 等。不同前缀会启动不同的仓库。
* `depends`: 位于本仓库中的依赖项，为一列表，其中的元素为 `pkgname`（对于普通包）或者 `(pkgbase, pkgname)`（对于 split package）。pkgname 或者 pkgbase 与对应包所在的目录名一致。可选。
* `makechrootpkg_args`: 传递给 `makechrootpkg` 的额外参数。可选。

## 提供的信息
* `_G.oldver`: 旧版本号。可能为 `None`。
* `_G.newver`: 新版本号。可能为 `None`。
