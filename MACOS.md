# Causal Studio · macOS 版本

适用于 macOS 15 或更新系统。提供两个独立版本：

- `arm64`：Apple 芯片 Mac（M1、M2、M3、M4 等）。
- `x86_64`：Intel Mac。

## 安装和运行

使用 `.pkg` 时，双击文件并按安装向导操作，应用将安装到 `/Applications/CausalStudio.app`。

使用 `.dmg` 时，打开磁盘映像，把 `CausalStudio.app` 拖到 `Applications`，然后从“应用程序”运行。

无需安装 Python。表格及计算保留在本机。支持 CSV / TSV / XLSX / DTA、最多 100,000 行和 30 个选中分析变量，以及原有九种算法、拖动节点和图像/文本导出。大型非线性计算仍受内存和耗时限制。

本次默认使用本地临时签名，尚未使用 Apple Developer ID 或 Apple 公证。macOS 首次运行可能显示开发者身份无法验证；仅对你信任的本项目构建结果，按“系统设置 → 隐私与安全性”中的系统提示允许打开。不要关闭系统的整体安全检查。

## 云端重新构建

打开 GitHub 仓库的 Actions，选择 **Build macOS installers**，运行工作流。两个架构均构建成功后，下载对应的 `CausalStudio-macOS-arm64` 或 `CausalStudio-macOS-x86_64` 产物，解压可获得 `.pkg`、`.dmg` 和 SHA-256 校验信息。

工作流仅做 100 行、5 个变量的小样本检查，覆盖 CSV / XLSX / DTA 导入、PC 子进程分析、拖动布局以及 PNG / SVG / TXT / ZIP 导出；同时检查可选算法依赖能否导入。不会运行十万行计算或全套算法复查。

## 在 Mac 上构建

使用与目标芯片匹配的 Python 3.12：

```bash
python3.12 -m venv .venv-macos
source .venv-macos/bin/activate
python -m pip install -r requirements-macos.lock
python make_examples.py
python build_macos.py --arch arm64
```

Intel Mac 最后一行改为 `--arch x86_64`。输出位于 `dist/macos/<架构>/`。

签名可选环境变量：`MACOS_CODESIGN_IDENTITY`（Developer ID Application）、`MACOS_INSTALLER_IDENTITY`（Developer ID Installer）、`MACOS_NOTARY_PROFILE`（已配置到 Mac 钥匙串的 notarytool profile）。若配置公证，必须同时配置两类签名身份；构建会在提交成功后附加公证票据。证书和口令不应写入源码或仓库。

依赖及第三方许可证随应用保留。Numba 和字体缓存写入用户的 `~/Library/Caches/CausalStudio/`。
