nonexistent-deps-subject = 软件包 { $pkg } 的 lilac.yaml 指定了不存在的依赖
nonexistent-deps-body = 软件包 { $pkg } 的 lilac.yaml 指定了 repo_depends，然而其直接或者间接的依赖项 { $deps } 并不在本仓库中。

update_on_build-error = %s update_on_build 检查出错

dependency-issue-subject = %s 出现依赖问题
dependency-issue-failed = { $pkg } 的依赖 { $faileddeps } 打包失败了。
dependency-issue-failed-this-batch = { $pkg } 缺少依赖 { $deps }，其中 { $faileddeps } 本次打包失败了。
