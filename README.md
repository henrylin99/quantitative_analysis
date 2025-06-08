# 多因子选股系统

一个功能完整的多因子选股系统，集成了因子计算、机器学习建模、股票选择、组合优化和回测验证等功能。

### 本系统仅限于学习交流，需要二次开发或定制化开发，请联系 39189996@qq.com

![系统主界面](./images/1-2.png)

## 🌟 系统特色

### 核心功能
- **📊 因子管理**: 内置12个常用因子，支持自定义因子创建
- **🤖 机器学习**: 支持随机森林、XGBoost、LightGBM等算法
- **🎯 智能选股**: 基于因子和ML模型的多种选股策略
- **📈 组合优化**: 等权重、均值-方差、风险平价等优化方法
- **🔄 回测验证**: 完整的策略回测和多策略比较
- **📋 分析报告**: 行业分析、因子贡献度等深度分析

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
- MySQL 5.7+ (可选，默认使用SQLite)

### 2. 安装依赖
```bash
# 克隆项目
git clone <repository-url>
cd stock_analysis

# 安装依赖
pip install -r requirements.txt
```

### 3. 启动系统
```bash
# 使用启动脚本（推荐）
python run_system.py

# 或者直接运行
python app.py
```

![系统启动界面](./images/1-4.png)

### 4. 访问系统
- Web界面: http://localhost:5000/ml-factor
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
# SQLite (默认)
SQLALCHEMY_DATABASE_URI = 'sqlite:///stock_analysis.db'

# MySQL
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

详细解决方案请查看：[安装指南](INSTALL_GUIDE.md)

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
