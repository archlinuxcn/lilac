# `lilac.py` 文件说明

## 打包流程
* `pre_build`: 打包前执行的函数。
* `post_build`: 打包成功后执行的函数。
* `post_build_always`: 打包最后执行的函数，不论成功与否。可选。
* `prepare`: 清理前执行的函数。可选。如果返回字符串，则跳过打包。用于在明知无法打包时留下上一次打的包，以便依赖使用。

## 辅助信息
* `time_limit_hours`: `*-build` 的时间限制。单位为小时，默认为 1 。
* `build_args`: 传递给 `*-build` 的额外参数。可选。
* `makechrootpkg_args`: 传递给 `makechrootpkg` 的额外参数。可选。
* `makepkg_args`: 传递给 `makepkg` 的额外参数。可选。

## 提供的信息
* `_G.oldver`: 旧版本号。可能为 `None`。当被非第一项 `update_on` 触发（rebuild）时，也可能与新版本号相同。
* `_G.newver`: 新版本号。可能为 `None`。
* `_G.oldvers`: 对应的 `update_on` 项目的旧版本号列表。
* `_G.newvers`: 对应的 `update_on` 项目的新版本号列表。
* `lilac.yaml` 中的信息（如 `repo_depends`、`maintainers`，已进行基本的解析）
