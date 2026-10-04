# 从零安装指南

面向**第一次接触本项目的用户**，从一台空白的电脑开始，一步步把系统跑起来。全程约 20–40 分钟（取决于网速）。

> 装完你将得到：本地运行的量化分析系统，浏览器打开 `http://localhost:5173` 即可使用 AI 工作台、因子计算、组合回测等功能。
>
> 已经熟悉命令行？快速路径直接看 [README 的「快速开始」](README.md) 即可，本文是它的详细展开版。

---

## 目录

1. [准备基础软件](#1-准备基础软件)
2. [获取代码](#2-获取代码)
3. [安装 Python 依赖](#3-安装-python-依赖)
4. [配置环境变量](#4-配置环境变量)
5. [初始化系统](#5-初始化系统)
6. [启动后端](#6-启动后端)
7. [启动前端界面](#7-启动前端界面)
8. [下载行情数据](#8-下载行情数据)
9. [常用命令速查](#9-常用命令速查)
10. [常见问题排查](#10-常见问题排查faq)
11. [Docker 方式启动（可选）](#11-docker-方式启动可选)

---

## 1. 准备基础软件

系统需要以下软件。**每一项装完都建议用"验证"里的命令确认一下。**

### 1.1 Git（拉取代码用）

- 下载安装：
  - Windows：https://git-scm.com/download/win ，安装时全部默认下一步即可
  - macOS：终端执行 `xcode-select --install`，或用 Homebrew：`brew install git`
  - Linux（Ubuntu/Debian）：`sudo apt install git`
- 验证（打开终端 / PowerShell / Git Bash）：

```bash
git --version
# 输出版本号如 git version 2.39 即成功
```

> 💡 不知道"终端"在哪？Windows 按 `Win + R` 输入 `powershell` 回车；macOS 在启动台搜"终端"。

### 1.2 Python（后端运行环境）

- 版本要求：**3.10 – 3.12**（最低 3.8 可运行，但推荐 3.12）
- 下载安装：https://www.python.org/downloads/
  - ⚠️ **Windows 安装时务必勾选第一屏的 `Add python.exe to PATH`**，否则后面所有 `python` 命令都会报"不是内部或外部命令"
- 验证：

```bash
python --version
# 输出 Python 3.12.x 即成功（macOS/Linux 若无输出，试试 python3 --version，下文同理）
```

### 1.3 Node.js（前端界面用）

React 前端需要 Node.js。版本要求：**22 LTS（或至少 20.19 以上）**。

- 下载安装：https://nodejs.org/ （选 LTS 版本）
- 验证：

```bash
node -v
npm -v
# 各输出版本号即成功
```

> 不想用前端界面、只用 API？可以跳过 Node.js，但**强烈不建议**——系统的绝大部分功能入口都在网页界面上。

### 1.4 Docker Desktop（可选）

只有在你想用容器方式一键部署时才需要。见[第 11 节](#11-docker-方式启动可选)。新手建议先跳过，用上面的原生方式。

### 1.5 （国内网络可选）配置下载加速

如果 pip / npm 下载很慢或超时，配置国内镜像源（执行一次即可，永久生效）：

```bash
# pip 清华镜像
pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple

# npm 淘宝镜像
npm config set registry https://registry.npmmirror.com
```

---

## 2. 获取代码

打开终端，选一个你放代码的目录（例如 `cd ~/Documents` 或 `cd D:\projects`），执行：

```bash
git clone https://github.com/henrylin99/quantitative_analysis.git
cd quantitative_analysis
```

验证：`ls`（Windows 用 `dir`）应能看到 `run.py`、`README.md`、`frontend/` 等文件。

> 自 v4.0.0 起前端已合入 master 主分支，无需再切换任何分支。

---

## 3. 安装 Python 依赖

### 3.1 创建虚拟环境（强烈建议）

虚拟环境把本项目的依赖隔离在自己的文件夹里，不污染系统 Python，删掉重装也方便。

```bash
# macOS / Linux
python3 -m venv .venv
source .venv/bin/activate

# Windows（PowerShell）
python -m venv .venv
.venv\Scripts\Activate.ps1

# Windows（CMD）
python -m venv .venv
.venv\Scripts\activate.bat
```

激活成功后，命令行前面会出现 `(.venv)` 字样。

> ⚠️ Windows PowerShell 如果报"禁止运行脚本"，先执行一次：
> `Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser`，输入 `Y` 回车，再重新激活。
>
> 💡 以后**每次新开终端**都要先重新执行激活命令，再运行本项目命令。

### 3.2 安装依赖包

```bash
pip install -r requirements.txt
```

这一步会下载 Flask、pandas、XGBoost 等约 30 个包，大概 2–10 分钟。

如果个别包（如 `xgboost`、`lightgbm`、`cvxpy`）在你的系统上安装失败，改用精简依赖：

```bash
pip install -r requirements_minimal.txt
```

> 精简版缺少部分机器学习包，核心行情功能不受影响，ML 建模功能需要之后自行补装。

验证：

```bash
python -c "import flask, pandas, sklearn; print('依赖安装成功')"
```

---

## 4. 配置环境变量

### 4.1 创建配置文件和数据库目录

```bash
# 复制模板
cp .env.example .env          # Windows 用 copy .env.example .env

# 创建数据库目录（模板中的数据库路径指向 instance/ 目录，需手动创建）
mkdir instance                # Windows 用 md instance
```

> ⚠️ **`mkdir instance` 这步不能省**，否则首次启动会报 `unable to open database file`。

### 4.2 修改 `.env` 配置

用任意文本编辑器打开 `.env`（Windows 可用记事本：`notepad .env`；macOS 可用 `open -e .env`）：

| 配置项 | 必改？ | 说明 |
| --- | --- | --- |
| `SECRET_KEY` | **建议改** | 会话加密密钥。终端执行下面命令生成一个填进去 |
| `TUSHARE_TOKEN` | 可选 | Tushare 数据源令牌。**不填也能跑**：系统自动改用免费的 Baostock 数据源；但部分数据集（如资金流）只有 Tushare 提供。注册 https://tushare.pro 可获取 token |
| `LLM_API_KEY` 等 | 可选 | AI 智能工作台用的大模型配置。不填则 AI 对话功能不可用，其余功能完全正常。可用 DeepSeek（充值几块钱即可）或本地 Ollama（免费，见 `.env` 内注释） |
| `DATA_JOB_EXECUTION_MODE` | 不用动 | 保持 `inline` 即可，任务在本地进程执行，无需任何外部服务 |

生成随机 SECRET_KEY：

```bash
python -c "import secrets; print(secrets.token_hex(32))"
# 把输出的一长串字符填到 .env 的 SECRET_KEY= 后面
```

---

## 5. 初始化系统

项目自带初始化与诊断工具。在**激活了虚拟环境**的项目根目录执行：

```bash
python run_system.py
```

会出现交互菜单：

```
请选择操作:
1. 检查系统依赖
2. 初始化数据库
3. 启动Web服务器
...
```

依次执行：

1. 输入 `1` 回车 —— 检查依赖，全部显示 ✅ 为正常（个别 ❌ 按提示补装对应包）
2. 输入 `2` 回车 —— 初始化数据库，首次运行会自动创建 SQLite 数据表
3. 输入 `0` 回车 —— 退出（日常启动不用这个工具）

> 以后想重新体检，随时可以再跑 `python run_system.py`。

---

## 6. 启动后端

```bash
python run.py
```

看到类似下面的输出即成功：

```
DATA_JOB_EXECUTION_MODE=inline
日频数据中心任务将在当前 Web 进程内执行
 * Running on all addresses (0.0.0.0)
 * Running on http://127.0.0.1:5000
```

浏览器打开 http://localhost:5000/api/data-jobs/jobs 能看到 JSON 数据，说明后端正常。

> ⚠️ 这个终端窗口**不要关**，关了后端就停了。想停后端按 `Ctrl + C`。

---

## 7. 启动前端界面

**再新开一个终端窗口**（记得第 2 个终端也要进入项目目录），执行：

```bash
cd frontend
npm install       # 首次执行，下载依赖约 2–5 分钟
npm run dev
```

看到类似输出即成功：

```
  VITE v7.x.x  ready in xxx ms
  ➜  Local:   http://localhost:5173/
```

浏览器打开 **http://localhost:5173** —— 这就是系统主界面。

> 原理说明：前端开发服务器（5173）会自动把 API 请求转发给后端（5000），这个代理已在项目里配置好，无需额外设置。**因此浏览前端的界面时请始终用 5173 地址**，两个终端都要保持运行。
>
> 以后每次使用系统 = 两个终端分别执行 `python run.py` 和（frontend 目录下）`npm run dev`。

---

## 8. 下载行情数据

系统装好后是"空仓库"，需要先下载 A 股基础数据才能选股、回测：

1. 打开前端界面 → 左侧 **数据管理 / 日频数据中心**
2. 按顺序提交下载任务：**交易日历 → 股票基础信息（stock_basic）→ 其他需要的数据集**（日线行情、财务数据等）。顺序很重要，后续数据依赖前两类
3. 在任务列表里可以看到下载进度，完成后即可去因子/选股/回测页面使用

也可以直接在 **AI 智能工作台**用自然语言操作，例如输入"更新所有数据"。

数据就绪后，还可以在 AI 工作台体验「构建因子数据 → 回测」的完整链路，直接用自然语言输入：

- "构建 alpha191 从 2026 年 1 月至今的数据"（全市场批量计算，后台任务，约需十几分钟）
- "以沪深300为基准，基于 alpha_001 因子回测 2026 年 9 月"

系统会自动提交后台任务并返回任务号，用自然语言追问进度即可；回测完成后会给出收益、最大回撤、夏普比率等指标（历史数据统计，不构成投资建议）。

详细的数据集说明见 [README 的「数据下载」章节](README.md)。

> 💡 未配置 `TUSHARE_TOKEN` 时系统用 Baostock 免费源，基础日线够用；配置后可解锁资金流等更多数据集。数据保存在本地 `data/` 目录（Parquet 格式），首次下载后自动生成。

### 8.1 计算因子

数据下载完成后，还需要一步「因子计算」把原始行情加工成因子值（动量、估值分位、Alpha191 等）——因子打分、选股和回测读取的都是这些因子值。因子计算依赖已下载的行情/资金流/筹码/财务数据，缺哪类数据就少对应类别的因子。

**方式一：网页界面（推荐新手）**

左侧 **数据管理 / 日频数据中心** → 提交「因子计算」任务；或在 **AI 智能工作台**用自然语言操作，例如"构建 alpha191 从 2026 年 1 月至今的数据"。

**方式二：命令行脚本**

脚本为 `app/utils/factor_compute.py`，在**项目根目录（已激活虚拟环境）**执行：

```bash
# 1) 默认：计算最新交易日的全部因子
python app/utils/factor_compute.py

# 2) 指定区间计算全部因子（回填历史）
DATA_JOB_START_DATE=2024-01-01 DATA_JOB_END_DATE=2026-09-30 python app/utils/factor_compute.py

# 3) 只算某一个因子，从 2024 年至今（macOS / Linux 写法）
DATA_JOB_START_DATE=2024-01-01 DATA_JOB_END_DATE=2026-10-02 \
DATA_JOB_PARAM_FACTOR_IDS=alpha_001 python app/utils/factor_compute.py
```

Windows PowerShell 下环境变量要分开设置（对应第 3 个例子）：

```powershell
$env:DATA_JOB_START_DATE = "2024-01-01"
$env:DATA_JOB_END_DATE = "2026-10-02"
$env:DATA_JOB_PARAM_FACTOR_IDS = "alpha_001"
python app/utils/factor_compute.py
```

环境变量说明：

| 环境变量 | 说明 |
| --- | --- |
| `DATA_JOB_TRADE_DATE` | 单日模式：只计算这一个交易日 |
| `DATA_JOB_START_DATE` / `DATA_JOB_END_DATE` | 区间模式：一次算完整个区间（回填历史用） |
| `DATA_JOB_PARAM_FACTOR_IDS` | 逗号分隔的因子 ID 列表，如 `alpha_001,momentum_20d`；不传则计算全部因子 |
| `DATA_JOB_PARAM_TS_CODES` | 逗号分隔的股票代码列表；不传则全市场 |

> 💡 **因子 ID 从哪来？** 内置因子（`momentum_20d`、`pe_percentile` 等）和 Alpha191（`alpha_001` ~ `alpha_191`）在前端「ML 因子」页面的因子列表可查；自己创建的自定义表达式因子用创建时填写的因子 ID。
>
> ⚠️ **两个易踩的坑：**
> - 日期格式必须是 `YYYY-MM-DD`（如 `2024-01-01`），写成 `20240101` 会报错。
> - Alpha191 因子按区间整段批量计算（全市场宽面板只加载一次）：成本主要在面板加载与 189 个公式，与输出区间长度基本无关。单个因子回填 2024 年至今约 1 分钟；**首次**全量回填 alpha191 约需 1 小时上下，建议让它在后台慢慢跑（网页界面提交即是后台任务）。
> - 重复跑全区间回填是安全的，且很快：已回填过的 alpha191 因子按「已有覆盖天数」自动跳过重算（显式点名 `DATA_JOB_PARAM_FACTOR_IDS` 的因子不跳过）；内置/自定义因子走逐因子整段向量化 + 跨因子缓冲合并落盘，每张数据表全区间只读一次、每个交易日分区每缓冲组只重写一次。全部因子重跑 2024 年至今约 40–60 分钟（其中约 15 分钟是 roe/roa/growth 等基本面因子的全表财务数据读取，若财务数据未覆盖目标区间则该段时间产出为 0）。

计算结果保存在本地 `data/ml_factor_state/`（按交易日分区的 Parquet 文件），前端「ML 因子」页面可查看覆盖天数，回测时自动读取。

### 8.2 重建股票分区

`data/` 下的日频数据表同时保存两种布局：**按日期分区**（下载作业写入）和**按股票分区**（每只股票一个文件）。个股查询优先走股票分区——单只股票的历史只读一个文件，速度快。

每次日频下载后，股票分区可能落后于最新数据。落后时系统**不会报错**：查询自动回退扫描日期分区，结果完全一样，只是明显变慢（后端日志会出现「股票分区落后于日期分区，回退扫描 XXXXXX.SZ」的提示）。跑大批量因子计算、回测之前，建议先重建一次股票分区。

重建脚本是 `app/utils/stock_partition_rebuild.py`，覆盖 6 张日频表（`daily_history` 日线行情、`daily_basic` 每日指标、`moneyflow` 资金流、`cyq_perf` 筹码分布、`stk_factor`、`adj_factor` 复权因子），在**项目根目录（已激活虚拟环境）**执行：

```bash
# 全量重建（推荐日常使用，几分钟）
python app/utils/stock_partition_rebuild.py

# 只增量合并某个日期窗口（与下载作业传同一窗口即可）
DATA_JOB_START_DATE=2026-09-01 DATA_JOB_END_DATE=2026-09-30 python app/utils/stock_partition_rebuild.py

# 强制全量重建（忽略窗口参数）
DATA_JOB_FULL_REFRESH=1 python app/utils/stock_partition_rebuild.py
```

Windows PowerShell 下环境变量分开设置（对应第 2 个例子）：

```powershell
$env:DATA_JOB_START_DATE = "2026-09-01"
$env:DATA_JOB_END_DATE = "2026-09-30"
python app/utils/stock_partition_rebuild.py
```

> 💡 也可以不动命令行：**数据管理 / 日频数据中心**页面提交「股票分区重建」任务，或在 **AI 智能工作台**直接说"重建股票分区"。默认 16 线程并行，可用环境变量 `STOCK_REBUILD_WORKERS` 调整。
>
> ⚠️ 两个参数的区别：窗口模式只合并窗口内的交易日（快，适合每天下载后同步增量）；股票分区还不存在时会自动转为全量重建。想让所有股票从头重建一遍，用 `DATA_JOB_FULL_REFRESH=1`。

---

## 9. 常用命令速查

| 操作 | 命令 | 在哪个目录执行 |
| --- | --- | --- |
| 启动后端 | `python run.py` | 项目根目录（先激活虚拟环境） |
| 启动前端 | `npm run dev` | `frontend/` |
| 计算因子 | `python app/utils/factor_compute.py`（环境变量用法见[第 8.1 节](#81-计算因子)） | 项目根目录 |
| 重建股票分区 | `python app/utils/stock_partition_rebuild.py`（用法见[第 8.2 节](#82-重建股票分区)） | 项目根目录 |
| 初始化/体检 | `python run_system.py` | 项目根目录 |
| 停止服务 | `Ctrl + C` | 对应的终端窗口 |
| 运行测试 | `pytest tests/ -q` | 项目根目录 |

---

## 10. 常见问题排查（FAQ）

**Q1：启动后端报 `Address already in use` / 端口 5000 被占用？**
macOS 的"隔空播放接收器"（AirPlay）默认占用 5000 端口：系统设置 → 通用 → 隔空播放投递 → 关闭"隔空播放接收器"。或者换端口启动：`PORT=5010 python run.py`（Windows：`set PORT=5010` 再 `python run.py`），注意此时需要把 `frontend/vite.config.ts` 里两处 `target: 'http://127.0.0.1:5000'` 的 5000 改成 5010。

**Q2：前端页面能打开，但点任何功能都报错 / 提示网络错误？**
后端没启动。回到项目根目录的终端执行 `python run.py`，前端界面的所有数据都依赖后端（5000 端口）。

**Q3：`python` 命令不存在 / 不是内部或外部命令？**
Windows：安装 Python 时没勾选 "Add to PATH"，重新运行安装程序勾上；macOS：用 `python3` 代替 `python`。

**Q4：`pip install` 某个包报一大片红色编译错误？**
用精简依赖：`pip install -r requirements_minimal.txt`。之后需要 ML 功能时再单独 `pip install xgboost lightgbm cvxpy`；需要通达信实时行情时再单独 `pip install pytdx`。

**Q5：启动报 `unable to open database file`？**
`instance/` 目录没创建（见第 4.1 步），或 `.env` 里 `SQLITE_DATABASE_PATH` 路径写错。

**Q6：报 `database is locked`？**
多个程序同时在写同一个数据库文件。正常单机单人使用不会遇到；如果有多个终端在跑任务，等其中一个完成再操作。

**Q7：`npm install` 很慢或失败？**
配置镜像源（见第 1.5 节）后删除 `frontend/node_modules` 目录重新 `npm install`。

**Q8：AI 智能工作台没有回应？**
`.env` 里 `LLM_API_KEY` 没配（或余额不足），或用 Ollama 时本地模型服务没启动。AI 功能是可选的，不影响其他功能。

**Q9：想彻底重来？**
关掉两个服务后：

```bash
# 项目根目录执行
rm -rf .venv instance data frontend/node_modules   # Windows: rmdir /s /q 对应目录
# 然后从第 3 步重新开始
```

---

## 11. Docker 方式启动（可选）

不想装 Python/Node，机器上有 Docker 即可（前端界面需另行按第 7 节启动，或直接使用容器提供的 API 服务）：

```bash
cp .env.example .env    # Windows: copy .env.example .env
docker compose up --build
```

启动单只包含 Web 服务的容器（SQLite 与 Parquet 状态均为本地文件，无任何外部数据库/缓存依赖），访问 http://localhost:5000。

---

## 下一步

- [README](README.md) —— 项目功能总览与使用指南
- [CLAUDE.md](CLAUDE.md) —— 架构说明与开发规范（准备参与开发必读）
- 遇到本文没覆盖的问题，欢迎提 issue 联系我们
