# Causal Studio · 因果发现工作台

面向表格数据的中文桌面应用，支持 **Windows 与 macOS**。从导入数据、选择变量到运行算法和导出因果结构，可在一个独立窗口中完成；分析与导出均在本机执行，无需云端 API 或账号。

**当前版本：0.5.0** · **9 种因果发现算法** · **CSV / TSV / XLSX / DTA** · **最多 100,000 行、30 个分析变量**


## 主要功能

- **两种分析模式**：普通观测数据与单条时间序列，分别提供适用的算法和参数。
- **可视化选择变量**：按名称搜索，按数值、类别、缺失、已选或常数列筛选，批量勾选或取消；已选变量以可移除标签显示。
- **可交互的因果结构图**：拖动节点调整布局，拖动画布平移，滚轮缩放，并可适应窗口或重置布局。
- **多算法对照**：依次运行同类算法，在当前会话的“历史与对照”中查看结果及结构差异。
- **图形和文本导出**：保存 PNG、SVG、TXT，复制结构文本，或导出含报告、关系表和配置的 ZIP 结果包。
- **运行过程可取消**：算法在独立子进程中计算，界面保持响应。

## 下载与安装

### macOS

适用于 **macOS 15 及以上**，按芯片类型选择：

| Mac 芯片 | 安装包 |
| --- | --- |
| Apple 芯片（M 系列） | [CausalStudio-macOS-arm64](https://github.com/Kirihara-Ryouji/causal-studio/actions/runs/38523282001/artifacts/11874477183) |
| Intel 芯片 | [CausalStudio-macOS-x86_64](https://github.com/Kirihara-Ryouji/causal-studio/actions/runs/38523282001/artifacts/11874548379) |

登录 GitHub 后下载构建产物，解压可获得 `.pkg`、`.dmg` 和含 SHA-256 的 `manifest.json`。双击 `.pkg` 按向导安装，或打开 `.dmg` 将 `CausalStudio.app` 拖入“应用程序”；无需安装 Python。

### Windows

Windows x64 便携包名为 `CausalStudio-Windows-x64.zip`。解压后运行 `CausalStudio/CausalStudio.exe`，无需安装 Python。分发时需保留整个 `CausalStudio` 文件夹及其中的 `_internal`。

当前仓库未托管 Windows 二进制下载文件；可以按下方说明从源码运行或生成便携包。

## 快速上手

1. 选择“普通观测数据”或“时间序列”模式。
2. 导入 CSV、TSV、XLSX 或 DTA；Excel 可选择工作表，也可先载入示例。
3. 在“数据与变量”中勾选 **2–30 个分析变量**，排除 ID、时间索引和常数列。
4. 选择算法及检验方法。时间序列需指定时间列，或确认当前行顺序代表等间隔观测。
5. 点击运行，查看“因果关系图”“关系明细”和分析说明；可调整节点位置。
6. 需要比较时，依次运行同类算法并查看“历史与对照”。
7. 点击“导出图与文本”或“导出结果包”保存结果。

变量名称搜索支持空格分隔的多个关键词，匹配任一关键词即可显示。“选中筛选结果”与“取消筛选结果”仅操作当前显示的变量，切换筛选不会清空已有选择。点击已选变量标签可移除该变量。

节点拖动只调整图形布局，不修改关系、方向或统计量。历史及布局保留在当前会话内；更换数据或关闭应用前请导出需要保留的结果。

## 已接入的算法

| 算法 | 数据模式 | 本项目实现与主要条件 | 输出 |
| --- | --- | --- | --- |
| **PC-stable** | 普通观测 | Fisher-Z 或离散 G²；要求无潜在共同原因 | 有向与未定向边 |
| **FCI** | 普通观测 | Fisher-Z 或离散 G²；允许潜在共同原因 | 保留不确定端点的 PAG |
| **GES** | 普通观测 | 连续变量，线性高斯 BIC 评分；无潜在共同原因 | 因果等价类结构 |
| **DirectLiNGAM** | 普通观测 | 连续变量，线性非高斯、独立噪声、无环；无潜在共同原因 | 有向结构与标准化系数 |
| **RESIT** | 普通观测 | 随机森林回归 + HSIC；连续变量、非线性加性噪声、无环、无潜在共同原因 | 有向连接结构 |
| **PCMCI** | 时间序列 | ParCorr / GPDC / CMIknn；等间隔、平稳、无潜在共同原因 | 滞后 1…τmax 的关系，BH-FDR 校正 |
| **PCMCI+** | 时间序列 | 同上，同期结构要求无环 | 同期与滞后关系；本版不作 FDR 校正 |
| **VARLiNGAM** | 时间序列 | 线性非高斯、独立噪声、同期无环；最大滞后作为固定 VAR 阶数 | 同期和滞后结构、标准化系数 |
| **LPCMCI** | 时间序列 | 实验性；允许潜在共同原因，支持三种时序检验 | 同期和滞后 PAG；不作 FDR 校正 |

PC / FCI 的 Fisher-Z 适用于线性高斯条件独立检验；离散 G² 要求每列有 2–20 个类别，并需要足够的条件列联表样本。软件不会自动把类别编码解释为连续数值。

时序检验中，**ParCorr** 检查线性条件依赖，**GPDC** 基于加性噪声模型的残差距离相关，**CMIknn** 估计条件互信息。非线性检验可设置 99–9999 次重采样，默认 199 次；增加次数会提高 p 值分辨率并增加耗时。最大滞后可设为 1–20 个采样步长。

以上条件为简要说明，使用前应结合领域知识检查样本、变量与模型假设。方法背景见 [causal-learn PC 文档](https://causal-learn.readthedocs.io/en/latest/search_methods_index/Constraint-based%20causal%20discovery%20methods/PC.html)、[LiNGAM / RESIT 文档](https://lingam.readthedocs.io/en/latest/tutorial/resit.html)和 [Tigramite 官方项目](https://github.com/jakobrunge/tigramite)。

## 数据格式与处理

| 项目 | 支持范围 |
| --- | --- |
| 文件格式 | `.csv`、`.tsv`、`.xlsx`、`.dta`；旧 `.xls` 需先转换 |
| 文件大小 | 每文件最多 512 MB |
| 数据行数 | 最多 100,000 行；超过上限时报错，不静默截断 |
| 分析变量 | 每次选择 2–30 个；导入文件可以包含更多列 |
| 表头 | CSV / TSV / XLSX 首行须为非空且唯一的列名；DTA 使用原始变量名 |
| 文本编码 | CSV 支持 UTF-8、UTF-8 BOM、GB18030；TSV 使用制表符 |
| 数据预览 | 显示前 100 行；分析使用全部选定数据，不会自动抽样 |

**100,000 行 × 30 个变量是允许提交的输入上限，实际耗时与内存需求取决于算法、图的复杂程度及电脑配置。** RESIT、GPDC、CMIknn 等非线性方法在大样本下可能计算很慢，运行中可取消。

连续变量计算前会标准化；无法解析的数值、非有限值、常数列及严重共线情况会被拦截。离散 G² 使用类别编码，并在结果中记录映射。

- **普通观测数据**：默认遇到缺失值停止，也可选择仅使用完整行，并报告删除行数和可能的选择偏差。
- **时间序列**：所选变量有缺失值时停止，不通过删行压缩时间。指定时间列时检查唯一性和等间隔，按升序排序；无时间列时需要使用者确认行顺序和采样间隔。
- **Stata DTA**：保留原始变量名、数值编码与日期信息；变量标签和值标签作为来源元数据保存，不替换原始数值。普通缺失、扩展缺失和空字符串统一按缺失值处理。

时间序列模式面向**单条等间隔序列**，不支持将多个受试者的面板数据直接拼接。软件不自动插值、差分、检查平稳性或选择 VAR 阶数。滞后单位是采样步长。

## 导出内容与结果解读

### 图与结构文本

在关系图上方点击“导出图与文本”：

- **PNG**：完整画布图片，可插入文档或演示文稿。
- **SVG**：可缩放的矢量结构图。
- **TXT**：完整变量名称、逐条关系、端点标记、时间滞后、可用统计量、算法条件和参数。
- **复制结构文本**：将结构说明复制到剪贴板。

图形导出保留拖动后的布局。导出历史分析时，先选择相应历史记录。

### ZIP 结果包

“导出结果包”生成以下文件：

| 文件 | 内容 |
| --- | --- |
| `report.html` | 可在浏览器打开的分析报告 |
| `graph.svg` | 因果结构矢量图 |
| `structure.txt` | 因果结构文本 |
| `edges.csv` | 关系明细表 |
| `result.json` | 结构、参数、数据处理、来源元数据、依赖版本及布局 |

结果包不包含原始数据；PNG 通过图形菜单单独导出。

### 如何理解边与统计量

- 有向边反映算法假设下识别出的方向；无向边表示方向未识别，圆端点表示端点不确定。
- FCI / LPCMCI 的双箭头表示潜在混杂结构，不代表两变量互为因果；PAG 有向边也不一定表示直接效应。
- PC / FCI / GES 没有可简单视为“每条边显著性”的单一 p 值，相应列留空。
- PCMCI 的 q 值为 BH 调整后的 MCI 检验值。PCMCI+ 的 p 值描述邻接关系，不检验同期方向；LPCMCI 的 p 值也不能解释为方向显著性。
- LiNGAM 系数、偏相关、距离相关和条件互信息的含义不同，不能直接横向比较。RESIT 输出连接，不将邻接矩阵的 1 当作效应。

算法间一致不等于因果已被证实，边数更多也不意味着算法更好。输出用于探索候选因果结构，不直接提供干预效应或因果成立概率；变量集、缺失处理和模式不同的结果不应直接比较。

## 从源码运行

获取当前完整源码：

```bash
git clone --branch codex/macos-installer https://github.com/Kirihara-Ryouji/causal-studio.git
cd causal-studio
```

### Windows x64 · Python 3.14

在项目目录的 PowerShell 中运行：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe make_examples.py
.\.venv\Scripts\python.exe launch.py
```

### macOS · 原生 Python 3.12

使用与 Mac 芯片匹配的 Python 3.12，并使用 Mac 专用依赖文件：

```bash
python3.12 -m venv .venv-macos
source .venv-macos/bin/activate
python -m pip install -r requirements-macos.lock
python make_examples.py
python launch.py
```

依赖安装完成后，正常分析和导出无需联网。Windows 新环境使用 `requirements.txt` 解析兼容依赖，`requirements-lock.txt` 记录已有构建环境的版本快照；macOS 使用经过原生构建验证的 `requirements-macos.lock`。

### 模拟示例

`make_examples.py` 生成 `examples/` 目录，包括普通观测、时间序列、非高斯链、非线性加性噪声、非高斯时序和 DTA 示例。内置普通观测示例为线性高斯模型，不满足 DirectLiNGAM 的非高斯识别条件；算法选择应与示例假设匹配。模拟数据上的验证不保证能恢复真实数据中的因果结构。

## 打包与小样本检查

Windows 在已安装依赖并生成示例后运行：

```powershell
.\build.ps1
.\.venv\Scripts\python.exe package_release.py
```

输出为 `dist/CausalStudio/` 与 `dist/CausalStudio-Windows-x64.zip`。

macOS 在相应芯片的机器上运行：

```bash
python build_macos.py --arch arm64
# Intel Mac 使用：python build_macos.py --arch x86_64
```

输出位于 `dist/macos/<架构>/`，包含 `.pkg`、`.dmg` 与校验清单。云端可在完整源码分支的 GitHub Actions 中运行 **Build macOS installers** 工作流，分别生成两种原生架构安装包；签名配置见 [MACOS.md](https://github.com/Kirihara-Ryouji/causal-studio/blob/codex/macos-installer/MACOS.md)。

已完成的两种 Mac 构建均通过 **100 行、5 变量**的桌面小样本检查，覆盖 CSV / XLSX / DTA 导入、PC 子进程计算、布局调整及 PNG / SVG / TXT / ZIP 导出，同时检查可选算法依赖能否导入。该检查不代表九种算法都已在十万行数据上完成验证。

开发者可手动运行同一小样本检查：

```powershell
# Windows
.\.venv\Scripts\python.exe launch.py --smoke-test output\smoke
```

```bash
# macOS，已激活虚拟环境
python launch.py --smoke-test output/smoke
```

## 项目结构

```text
causal_studio/
  engine.py          数据读取、校验与因果发现
  ui.py              桌面界面、变量选择、交互图和历史
  report.py          结构文本、SVG 与结果包
  graphics_export.py PNG 导出
  fonts.py           平台字体配置
  smoke.py           小样本桌面检查
launch.py            应用入口
make_examples.py     生成模拟示例
requirements-lock.txt   Windows 依赖锁定
requirements-macos.lock macOS 依赖锁定
build.ps1            Windows 打包
build_macos.py       macOS 应用及安装包构建
packaging/           macOS 运行配置与打包钩子
.github/workflows/   macOS 云端构建
MACOS.md             macOS 安装、构建与签名说明
```

## 技术栈与反馈

桌面界面使用 **PySide6 / Qt**；数据处理使用 **pandas、NumPy、SciPy**；因果发现使用 **causal-learn、LiNGAM、Tigramite**。第三方依赖遵循各自许可证。

当前尚未提供背景知识约束、bootstrap 稳定性分析、干预效应估计和可重新载入的持久化项目文件。

功能建议与问题可提交到 [GitHub Issues](https://github.com/Kirihara-Ryouji/causal-studio/issues)。报告问题时请注明系统与芯片、应用版本、算法、变量数、行数、参数及错误信息；如需示例，优先提供可复现的模拟数据。
