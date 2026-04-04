# 多因子选股系统

一个用于学习和二次开发的多因子选股系统原型，当前包含因子计算、机器学习建模、股票选择、组合优化和回测验证等模块的基础实现。

## 项目定位

本项目目前仍处于原型阶段，仅适合学习、研究和二次开发，不应视为完整交付版量化平台。

- 适用场景：功能验证、学习交流、二次开发
- 不适用场景：未经补齐前直接作为实盘、生产交付或完整商业系统
- 当前原则：主路径只保留真实可用能力，演示/占位/模拟能力持续下线中

如需定制化开发，可联系 39189996@qq.com。

## 功能状态矩阵

### 已实现

- 内置因子计算基础链路
- 自定义因子表达式白名单校验
- 机器学习模型创建与真实训练任务轮询
- 基础选股评分
- 等权重、均值方差、风险平价、因子中性组合优化
- 基础回测结果返回与前后端字段对齐

### 部分实现

- 分析报告页已移除演示数据，但总结与管理能力仍较弱
- 投资组合页面已下线演示数据，但真实 CRUD / 再平衡闭环未完成
- 实时分析已清理 demo/mock 主路径，但真实数据接入与推送能力仍需继续完善
- 文档和页面仍在持续收口，部分截图和说明可能落后于当前代码状态

### 未实现/未开放

- 投资组合完整 CRUD 与删除闭环
- Black-Litterman、行业约束等高级优化能力
- 模型删除闭环
- 完整报告管理后台
- 统一的数据来源审计与功能状态标记机制

### 后续开发
- 完善因子构建
- 完善基础策略开发
- 完善投资组合真实管理闭环
- 完善实时数据接口与监测链路

### 新版本开发中，演示地址：http://223.4.156.201:5173/

### 数据库下载地址：
-- 数据更新到2026年02月13日，包含历史行情、基本面、技术面、资金流入、筹码分布。
-- 通过网盘分享的文件：stock_data_20260213.zip
链接: https://pan.baidu.com/s/1XYMvl_OAnFycV8bOBkyQ0g?pwd=ctfq 提取码: ctfq
-- 如果有tushare接口，可以直接通过 quantitative_analysis/app/utils 目录下的文件直接下载，例如：
```
# 下载历史行情数据：
# 首先进入下载工具的目录
cd app/utils

# tushare数据下载
# 先下载交易日期数据，所有下载数据接口都依赖这个文件
python trade_calendar.py

# 下载所有股票列表，所有按股票代码下载的数据接口都依赖这个文件
python stock_basic.py

# 运行历史数据，根据自己的需要，修改下载日期，代码在第33-34行，例如：
   and cal_date >= '2025-01-01' 
    and cal_date <= '2025-12-31'
# 然后运行，下载天数越多，下载时间越长
python daily_history_by_date.py

# baostock 数据下载

# 日线
python baostock_daily.py

# 分钟线 min5.py min15.py min30.py min60.py
python min5.py
```

![系统主界面](./images/1-2.png)

## 🌟 系统特色

### 核心功能
- **📊 因子管理**: 内置因子和受限自定义因子能力
- **🤖 机器学习**: 支持随机森林、XGBoost、LightGBM 等模型定义与训练
- **🎯 智能选股**: 支持基础因子评分与 ML 选股链路
- **📈 组合优化**: 当前仅保留已验证的优化方法
- **🔄 回测验证**: 提供基础回测结果和多策略比较能力
- **📋 分析页面**: 仅展示真实返回结果，不再自动填充演示数据

![系统功能概览](./images/1-3.png)

### 技术架构
- **后端**: Python 3.8+ / Flask / SQLAlchemy
- **数据处理**: Pandas / NumPy / Scikit-learn
- **机器学习**: XGBoost / LightGBM / CVXPY
- **前端**: Bootstrap 5 / JavaScript
- **数据库**: MySQL / SQLite

## 🚀 快速开始

### 1. 环境要求
- Python 3.8+
- MySQL 5.7或8.x

### 2. 安装依赖
```bash
# 克隆项目
git clone <repository-url>
cd quantitative_analysis

# 安装依赖
pip install -r requirements.txt
```

### 3. 启动系统
```bash
# 使用真实启动脚本
python run_system.py

# 按提示选择初始化数据库或启动 Web 服务
```
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
- API文档: http://localhost:5000/api

## 📖 使用指南

### 系统启动器
运行 `python run_system.py` 后，选择相应操作：

1. **检查系统依赖** - 验证Python版本和必需包
2. **初始化数据库** - 创建数据表和内置因子
3. **启动Web服务器** - 启动开发模式服务器
4. **启动Web服务器(生产模式)** - 启动生产模式服务器
5. **运行系统演示** - 执行完整功能演示
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

#### 因子相关接口
```python
import requests

# 获取因子列表
response = requests.get('http://localhost:5000/api/ml-factor/factors/list')

# 创建自定义因子
factor_data = {
    "factor_id": "custom_momentum",
    "factor_name": "自定义动量因子",
    "factor_type": "momentum",
    "factor_formula": "close.pct_change(10)",
    "description": "10日价格变化率"
}
response = requests.post('http://localhost:5000/api/ml-factor/factors/custom', json=factor_data)

# 计算因子值
calc_data = {
    "trade_date": "2024-01-15",
    "factor_ids": ["momentum_1d", "momentum_5d"]
}
response = requests.post('http://localhost:5000/api/ml-factor/factors/calculate', json=calc_data)
```

#### 模型相关接口
```python
# 创建模型
model_data = {
    "model_id": "my_xgb_model",
    "model_name": "我的XGBoost模型",
    "model_type": "xgboost",
    "factor_list": ["momentum_1d", "momentum_5d", "volatility_20d"],
    "target_type": "return_5d"
}
response = requests.post('http://localhost:5000/api/ml-factor/models/create', json=model_data)

# 训练模型
train_data = {
    "model_id": "my_xgb_model",
    "start_date": "2023-01-01",
    "end_date": "2023-12-31"
}
response = requests.post('http://localhost:5000/api/ml-factor/models/train', json=train_data)
```

#### 选股相关接口
```python
# 基于因子选股
selection_data = {
    "trade_date": "2024-01-15",
    "factor_list": ["momentum_1d", "momentum_5d"],
    "method": "equal_weight",
    "top_n": 50
}
response = requests.post('http://localhost:5000/api/ml-factor/scoring/factor-based', json=selection_data)

# 基于ML模型选股
ml_selection_data = {
    "trade_date": "2024-01-15",
    "model_ids": ["my_xgb_model"],
    "top_n": 50
}
response = requests.post('http://localhost:5000/api/ml-factor/scoring/ml-based', json=ml_selection_data)
```

#### 组合优化接口
```python
# 组合优化
optimization_data = {
    "expected_returns": {"000001.SZ": 0.05, "000002.SZ": 0.03},
    "method": "mean_variance",
    "constraints": {
        "max_weight": 0.1,
        "risk_aversion": 1.0
    }
}
response = requests.post('http://localhost:5000/api/ml-factor/portfolio/optimize', json=optimization_data)
```

## 🏗️ 系统架构

![系统架构图](./images/1-21.png)

### 目录结构
```
stock_analysis/
├── app/                    # 应用主目录
│   ├── api/               # API接口
│   ├── models/            # 数据模型
│   ├── services/          # 业务服务
│   ├── routes/            # 路由
│   └── utils/             # 工具函数
├── templates/             # HTML模板
├── static/               # 静态文件
├── examples/             # 使用示例
├── config.py             # 配置文件
├── requirements.txt      # 依赖包
├── run_system.py         # 系统启动器
└── README.md            # 说明文档
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
在 `config.py` 中修改数据库连接：

```python
# SQLite（不建议使用，数据太大，速度较慢）
SQLALCHEMY_DATABASE_URI = 'sqlite:///stock_analysis.db'

# MySQL (默认，建议用MySQL)
SQLALCHEMY_DATABASE_URI = 'mysql+pymysql://user:password@localhost/stock_analysis'
```

### 日志配置
```python
LOG_LEVEL = 'INFO'
LOG_FILE = 'logs/app.log'
```

## 🧪 运行演示

系统提供了完整的功能演示：

```bash
# 运行完整演示
python examples/complete_system_example.py

# 或通过启动器运行
python run_system.py
# 选择 "5. 运行系统演示"
```

![系统演示](./images/1-22.png)

演示内容包括：
1. 因子管理演示
2. 模型管理演示
3. 股票选择演示
4. 组合优化演示
5. 集成选股和优化演示
6. 回测验证演示
7. 分析功能演示

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

如果遇到 `empyrical` 或 `TA-Lib` 安装失败，请使用修复版启动脚本：

```bash
# 使用修复版快速启动（推荐）
python quick_start_fixed.py

# 或使用最小化依赖
pip install -r requirements_minimal.txt
```

### 常见问题

1. **依赖包安装失败**
   ```bash
   # 方案1：使用修复版启动脚本
   python quick_start_fixed.py
   
   # 方案2：手动安装核心依赖
   pip install Flask pandas numpy scikit-learn
   
   # 方案3：使用国内镜像
   pip install -r requirements_minimal.txt -i https://pypi.tuna.tsinghua.edu.cn/simple/
   ```

2. **Python版本兼容性**
   - 推荐使用 Python 3.8-3.11
   - Python 3.12 可能有部分包兼容性问题
   - 使用修复版脚本可以自动处理

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
- 完整的多因子选股系统
- 支持因子管理和计算
- 机器学习模型集成
- 组合优化功能
- 回测验证引擎
- Web界面和API接口

## 📄 许可证

本项目采用 MIT 许可证。

## 🤝 贡献

欢迎提交Issue和Pull Request来改进这个项目。

## 📞 联系方式

如有问题或建议，请通过以下方式联系：
- 提交Issue
- 发送邮件：39189996@qq.com

---

**多因子选股系统** - 让量化投资更简单！ 

## 日频数据中心（新增）

现在可以在页面直接触发 `app/utils` 中的数据下载脚本，无需手工进入目录执行。

- 页面入口：`/realtime-analysis` -> `日频数据中心`
- API 前缀：`/api/data-jobs`
- 任务能力：提交、查询、重试、状态过滤、进度轮询、历史展示

### 运行要求
1. 启动 Redis
2. 启动 Flask 服务
3. 启动 Celery Worker

```bash
celery -A app.celery_app.celery worker -l info
```

### 快速验证
```bash
bash scripts/validation/validate_data_jobs_flow.sh
```

### 常用 API
```bash
# 提交任务
curl -X POST http://127.0.0.1:5001/api/data-jobs/submit \
  -H 'Content-Type: application/json' \
  -d '{"job_type":"daily_basic","params":{"start_date":"2026-01-01","end_date":"2026-01-31"}}'

# 查看最近任务
curl "http://127.0.0.1:5001/api/data-jobs/list?limit=20"

# 仅看失败任务
curl "http://127.0.0.1:5001/api/data-jobs/list?status=failed&limit=20"
```
