# 打包目录中的特殊文件

* `lilac.py`: 打包控制脚本
* `PKGBUILD`: 打包脚本
* `package.list`: 对于无法使用正则确定包名的 split package，此文件每行一个包名，列出打包结果。用于防止软件包被自动清理
* `.gitignore`: git 忽略文件。此文件不会被清理或者内建 AUR 下载器覆盖
