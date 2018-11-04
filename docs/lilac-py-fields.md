# `lilac.py` 文件说明

## 打包流程
* `pre_build`: 打包前执行的函数。
* `post_build`: 打包成功后执行的函数。
* `post_build_always`: 打包最后执行的函数，不论成功与否。可选。
* `update_on`: （弃用；请使用 lilac.yaml）配置更新触发器。这是一个提供给 [nvchecker](https://github.com/lilydjwg/nvchecker) 的配置的列表。其中第一项为软件本体，检测到的版本信息会通过 `_G` 变量传递回来。例子：

```python
update_on = [{
  'pypi': 'trio',
}, {
  'archpkg': 'python',
  'from_pattern': r'^(\d+\.\d+)\..*',
  'to_pattern': r'\1',
}]
```

## 辅助信息
* `build_prefix`: 打包命令的前缀，如 `extra-x86_64`、`multilib`、`archlinuxcn-x86_64` 等。不同前缀会启动不同的仓库。可选，默认为 `extra-x86_64`。
* `depends`: 位于本仓库中的依赖项，为一列表，其中的元素为 `pkgname`（对于普通包）或者 `(pkgbase, pkgname)`（对于 split package）。pkgname 或者 pkgbase 与对应包所在的目录名一致。可选。
* `time_limit_hours`: 表示打包的超时时间，单位为小时。可选，默认为1小时。
* `makechrootpkg_args`: 传递给 `makechrootpkg` 的额外参数。可选。

## 提供的信息
* `_G.oldver`: 旧版本号。可能为 `None`。
* `_G.newver`: 新版本号。可能为 `None`。
