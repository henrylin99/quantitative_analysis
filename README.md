# 多因子选股系统

一个面向 A 股市场的量化分析系统，涵盖实时行情分析、因子计算、机器学习建模、交易信号、组合管理、风险管理、回测验证等完整链路。v2.0 采用 Parquet + SQLite 架构，**零外部数据库依赖，克隆即可运行**。

## 项目定位

本项目适合量化交易学习、策略研究和二次开发。

- 适用场景：量化入门学习、策略研究、二次开发
- 不适用场景：直接用于实盘交易
- 技术支持：如需定制化开发，可联系 39189996@qq.com

## 功能概览

### 📊 实时行情分析（v2.0 新增）

- **技术指标**：通达信分钟数据接入，支持 MACD/KDJ/RSI/布林带等指标计算与展示
- **交易信号**：多策略信号生成、信号融合、信号监控、策略回测
- **风险管理**：投资组合持仓管理、实时价格刷新（通达信接口）、风险指标、预警管理、压力测试
- **分析报告**：5 种报告类型（每日总结/组合分析/风险评估/信号分析/市场概览），支持指标卡片、表格、图表可视化
- **实时监控**：板块表现、异动检测、市场情绪指标

### 🧮 因子与选股

- 内置因子计算 + 自定义因子表达式（白名单校验）
- 基础因子评分与 ML 选股
- 机器学习模型创建、训练（XGBoost / LightGBM / RandomForest）、预测

### 📈 组合与回测

- 等权重、均值方差、风险平价、因子中性组合优化
- 投资组合 CRUD：创建、持仓增删改、优化结果落库
- 单策略与多策略回测

### 💾 数据管理

- **行情数据**：Parquet 格式存储，支持通达信和 Baostock 双数据源
- **应用状态**：SQLite 管理持仓、报告、预警等
- **离线数据包**：提供预下载的历史数据，解压即用

## 数据下载
- 视频讲解地址：https://youtu.be/SpHsZdlyii8
- 为方便学习使用，数据已改为 Parquet 模式，下载后安装环境即可使用，不需要安装 MySQL
- 数据更新到 2026 年 06 月 03 日，包含历史行情、基本面、技术面、资金流入、筹码分布，后续不定期更新
- 由于历史数据第一次下载较大，百度网盘没会员下载较慢，现提供其它几个网盘，请根据实际情况选择其中一个下载，后面日更新的数据文件不大，继续放百度网盘
- 夸克网盘：https://pan.quark.cn/s/30fe0b6ddb86
- 123网盘：https://1859852554.share.123pan.cn/123pan/tRlivd-xOXLH
- 百度网盘：https://pan.baidu.com/s/1V7GW68EmA3Ad8lKTLsuG3Q?pwd=bie3
- 如有 Tushare 接口，可通过数据管理页面更新数据

## 工具下载
- anaconda或者python 二选一就行，以免环境冲突，简单一点用python，需要更多功能用anaconda  
- anaconda下载地址： https://mirrors.tuna.tsinghua.edu.cn/anaconda/archive/
- python下载地址，建议用3.12.10
https://www.python.org/downloads/windows/

- 查看SQLite数据库，免费软件可以下载 https://sqlitebrowser.org/dl/ 然后把stock_cursor.sqlite3文件拖入软件中即可使用。

![系统主界面](./images/1-2.png)

## 🌟 系统特色

### 核心功能
- **📊 因子管理**: 内置因子和受限自定义因子能力
- **🤖 机器学习**: 支持随机森林、XGBoost、LightGBM 等模型定义与训练
- **🎯 基础选股评分**: 支持基础因子评分与 ML 选股链路
- **📈 组合优化**: 当前仅保留已验证的优化方法
- **🔄 回测验证**: 提供基础回测结果和多策略比较能力
- **📋 分析页面**: 仅展示真实返回结果，不再自动填充演示数据

![系统功能概览](./images/1-3.png)

### 技术架构
- **后端**: Python 3.8+ / Flask / SQLAlchemy
- **数据处理**: Pandas / NumPy / Scikit-learn
- **机器学习**: XGBoost / LightGBM / CVXPY
- **前端**: Bootstrap 5 / JavaScript
- **市场数据源**: Parquet 文件为主，市场数据统一落在 `data/`
- **ML 因子状态层**: Parquet 文件，状态数据统一落在 `data/ml_factor_state/`
- **应用状态层**: 低并发状态与元数据统一使用 SQLite

## 🚀 快速开始

### 1. 环境要求
- Python 3.8+
- 运行系统不需要 MySQL；默认使用 SQLite + Parquet

### 2. 安装依赖
```bash
# 克隆项目
git clone <repository-url>
cd quantitative_analysis

# 安装依赖
pip install -r requirements.txt
```

### 2.1 容器化启动
```bash
cp .env.example .env
docker compose up --build
```

默认会同时启动 Web、SQLite 和 Redis；其中市场数据和 ml-factor 状态仍以本地 parquet 文件为准。

### 3. 启动系统
```bash
# 常规启动入口
python run.py
```

常规 Web 启动统一使用 `python run.py`。

- `run.py`：唯一标准 Web 启动入口
- `run_system.py` 用于初始化与诊断：检查依赖、校验数据库和补建基础表，不作为日常启动入口

run_system.py 用于初始化与诊断，不作为日常启动入口。

# 遇到以下问题
```
Traceback (most recent call last):
  File "/root/stock/run.py", line 9, in <module>
    app = create_app(os.getenv('FLASK_ENV', 'default'))

执行：pip install eventlet
```

![系统启动界面](./images/1-4.png)

### 4. 访问系统
- Web界面: http://localhost:5000
- API入口: http://localhost:5000/api

## 📖 使用指南

### 启动方式

#### 1. 常规启动
运行 `python run.py` 后，系统会输出启动检查摘要，并默认在开发环境下启动 Web 服务。

#### 2. 初始化与诊断
运行 `python run_system.py` 后，可执行以下操作：

1. **检查系统依赖** - 验证Python版本和必需包
2. **初始化数据库** - 创建数据表和内置因子
3. **启动Web服务器** - 启动开发模式服务器（调试用途）
4. **启动Web服务器(生产模式)** - 启动生产模式服务器
5. **运行系统演示** - 运行当前已接通功能入口
6. **显示系统信息** - 查看系统功能概览

![系统启动选项](./images/1-5.png)

### Web界面操作

#### 1. 仪表盘
- 查看系统状态和统计信息
- 快速访问主要功能

![仪表盘界面](./images/1-6.png)

#### 2. 因子管理
- 查看内置因子列表
- 创建自定义因子
- 计算因子值

![因子管理界面](./images/1-7.png)

![因子列表](./images/1-8.png)

#### 3. 模型管理
- 创建机器学习模型
- 训练模型
- 模型预测

![模型管理界面](./images/1-9.png)

![模型训练](./images/1-10.png)

#### 4. 股票选择
- 基于因子的选股
- 基于ML模型的选股
- 配置选股参数

![股票选择界面](./images/1-11.png)

![选股结果](./images/1-12.png)

#### 5. 组合优化
- 多种优化方法
- 约束条件设置
- 权重分配结果

![组合优化界面](./images/1-13.png)

![优化结果](./images/1-14.png)

#### 6. 分析报告
- 行业分析
- 因子贡献度分析

![分析报告界面](./images/1-15.png)

![行业分析](./images/1-16.png)

#### 7. 回测验证
- 单策略回测
- 多策略比较
- 失败时不再自动展示模拟结果

![回测验证界面](./images/1-17.png)

![回测结果](./images/1-18.png)

![策略比较](./images/1-19.png)

### API接口使用

![API接口文档](./images/1-20.png)

## 🏗️ 系统架构

![系统架构图](./images/1-21.png)

### 目录结构
```
quantitative_analysis/
├── app/                          # 应用主目录
│   ├── api/                     # API 蓝图（ml_factor、realtime_*等）
│   ├── models/                  # 数据模型（SQLAlchemy + Parquet事件）
│   ├── services/                # 业务服务（因子引擎、信号引擎、风控等）
│   ├── routes/                  # 页面路由
│   ├── templates/               # Jinja2 HTML 模板
│   ├── static/                  # CSS/JS/图片静态资源
│   ├── utils/                   # 数据下载脚本（通达信/Baostock/Tushare）
│   ├── websocket/               # WebSocket 推送服务
│   └── services/tongdaxin/      # 通达信行情客户端
├── data/                         # 数据目录（Parquet 行情 + SQLite 状态）
│   ├── stock_minute/            # 分钟级行情 Parquet
│   ├── ml_factor_state/         # ML因子状态 Parquet
│   └── realtime_events/        # 实时事件 Parquet
├── tests/                        # 测试用例
├── config.py                     # 配置文件
├── requirements.txt              # 依赖包
├── run.py                        # Web 启动入口
├── run_system.py                 # 初始化与诊断工具
└── README.md                     # 说明文档
```

### 核心模块

#### 1. 因子引擎 (FactorEngine)
- 因子定义管理
- 因子值计算
- 支持自定义公式

#### 2. 机器学习管理器 (MLModelManager)
- 模型创建和训练
- 预测和评估
- 支持多种算法

#### 3. 股票打分引擎 (StockScoringEngine)
- 因子打分
- ML模型打分
- 综合评分

#### 4. 组合优化器 (PortfolioOptimizer)
- 多种优化算法
- 约束条件支持
- 风险模型估计

#### 5. 回测引擎 (BacktestEngine)
- 策略回测
- 性能指标计算
- 多策略比较

## 📊 内置因子

### 动量因子
- `momentum_1d`: 1日动量
- `momentum_5d`: 5日动量
- `momentum_20d`: 20日动量

### 波动率因子
- `volatility_20d`: 20日波动率

### 技术指标
- `rsi_14`: RSI相对强弱指标

### 成交量因子
- `turnover_rate`: 换手率

### 基本面因子
- `pe_ratio`: 市盈率
- `pb_ratio`: 市净率
- `roe`: 净资产收益率
- `debt_ratio`: 资产负债率
- `current_ratio`: 流动比率
- `gross_margin`: 毛利率

## 🔧 配置说明

### 数据库配置
已经改成parquet模式，不需要数据库

### 日志配置
```python
LOG_LEVEL = 'INFO'
LOG_FILE = 'logs/app.log'
```

## 📈 性能指标

系统支持的回测指标：
- 总收益率
- 年化收益率
- 年化波动率
- 夏普比率
- 最大回撤
- 胜率
- 卡尔玛比率

## 🛠️ 开发指南

### 添加自定义因子
1. 在因子管理界面创建因子定义
2. 编写因子计算公式
3. 测试因子计算结果

### 扩展机器学习模型
1. 在 `MLModelManager` 中添加新算法
2. 实现训练和预测方法
3. 更新API接口

### 添加优化算法
1. 在 `PortfolioOptimizer` 中实现新方法
2. 添加约束条件支持
3. 测试优化结果

## 🐛 故障排除

### ⚠️ 依赖包兼容性问题

如果遇到 `empyrical` 或 `TA-Lib` 安装失败，请优先安装标准依赖；若本地环境仍有兼容性问题，再退回最小依赖安装：

```bash
# 使用最小化依赖
pip install -r requirements_minimal.txt
```

### 常见问题

1. **依赖包安装失败**
   ```bash
   # 方案1：安装标准依赖
   pip install -r requirements.txt
   
   # 方案2：使用国内镜像安装最小依赖
   pip install -r requirements_minimal.txt -i https://pypi.tuna.tsinghua.edu.cn/simple/
   ```

2. **Python版本兼容性**
   - 推荐使用 Python 3.8-3.11
   - Python 3.12 可能有部分包兼容性问题

3. **数据库连接失败**
   - 检查数据库配置
   - 确保数据库服务运行
   - 验证连接权限

4. **因子计算失败**
   - 检查数据是否存在
   - 验证因子公式语法
   - 查看日志错误信息

5. **模型训练失败**
   - 确保有足够的训练数据
   - 检查因子数据完整性
   - 调整模型参数

## 📝 更新日志

### v1.0.0 (2025-06-01)
- 多因子选股系统初始版本
- 因子管理和计算、机器学习模型集成
- 组合优化、回测验证引擎
- Web 界面和 API 接口

### v2.0.0-parquet (2026-06-06)

**架构升级**：从 MySQL 迁移到 Parquet + SQLite，零外部数据库依赖，克隆即可运行。

- 实时行情分析模块：技术指标、交易信号（生成/融合/监控/回测）、风险管理（持仓/预警/压力测试）、分析报告（5种类型，可视化渲染）、实时监控（板块/异动/情绪）
- 通达信实时行情接入，支持批量获取报价和自动刷新持仓价格
- 日频数据中心：页面内直接触发数据下载脚本，支持任务管理和进度轮询
- 数据存储全面迁移到 Parquet（行情/指标/信号/状态），SQLite 仅保留应用元数据
- 投资组合管理完整闭环：创建、持仓增删改、实时价格刷新、优化落库
- 报告可视化：指标卡片、HTML 表格、ECharts 图表、预警卡片等类型化渲染
- 离线数据包：提供预下载的 A 股历史数据，解压即用

## 📄 许可证

本项目采用 MIT 许可证。

## 🤝 贡献

欢迎提交Issue和Pull Request来改进这个项目。

## 📞 联系方式

如有问题或建议，请通过以下方式联系：
- 提交Issue
- 发送邮件：39189996@qq.com

---

**多因子选股系统原型** - 适合继续补齐后再扩展使用。 

## 日线、分钟线数据中心（新增）

- 页面入口：`/data-management` -> `数据管理`
- 任务能力：提交、查询、重试、状态过滤、进度轮询、历史展示