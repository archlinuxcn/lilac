nonexistent-deps-subject = 软件包 { $pkg } 的 lilac.yaml 指定了不存在的依赖
nonexistent-deps-body = 软件包 { $pkg } 的 lilac.yaml 指定了 repo_depends，然而其直接或者间接的依赖项 { $deps } 并不在本仓库中。

update_on_build-error = %s update_on_build 检查出错

dependency-issue-subject = %s 出现依赖问题
dependency-issue-failed = { $pkg } 的依赖 { $faileddeps } 打包失败了。
dependency-issue-failed-this-batch = { $pkg } 缺少依赖 { $deps }，其中 { $faileddeps } 本次打包失败了。

aur-submit-error = 提交软件包 %s 到 AUR 时出错

package-staged-subject = { $pkg } { $version } 刚刚打包了
package-staged-body = 软件包已被置于 staging 目录，请查验后手动发布。

too-much-output = 输出过多，已击杀。

log-too-long = 日志过长，省略ing……

nvchecker-error-report = nvchecker 错误报告

github-token-not-set = 未设置 github token，无法从 GitHub 取得用户 Email 地址
github-email-error = 从 GitHub 获取维护者 Email 地址时出错：{ $error }
github-email-private = GitHub 用户 { $user } 未公开 Email 地址
unsupported-maintainer-info = 不支持的格式：{ $info }

maintainers-error-subject = { $pkg } 的 maintainers 信息有误
maintainers-error-body = 以下 maintainers 信息有误，请修正。

packaging-error-subprocess-subject = 在打包软件包 %s 时发生错误
packaging-error-subprocess =
    命令执行失败！
    
    命令 { $cmd } 返回了错误号 { $returncode }。
packaging-error-subprocess-output = 命令的输出如下：
packaging-error-traceback = 调用栈如下：
packaging-error-aur-subject = 在获取AUR包 %s 时发生错误
packaging-error-aur = 获取AUR包失败！
packaging-error-timeout-subject = 打包软件包 %s 超时
packaging-error-unknown-subject = 在打包软件包 %s 时发生未知错误
packaging-error-unknown = 发生未知错误！
packaging-log = 打包日志：

lilac-yaml-loadding-error = 为软件包 %s 载入 lilac.yaml 时失败

package-in-official-group = 软件包被加入了官方组：{ $groups }
package-replacing-official-package = 软件包将取代官方包：{ $packages }
package-conflicts-with-official-repos = %s 与官方软件库冲突
package-older-subject = %s 新打的包比仓库里的包旧
package-older-body = 包 { $pkg } 打的版本为 { $built_version }，但在仓库里已有较新版本 { $repo_version }。
