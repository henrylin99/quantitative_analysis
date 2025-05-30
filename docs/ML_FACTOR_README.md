# 多因子选股&机器学习模型系统

## 概述

本系统实现了基于多因子模型和机器学习算法的股票选择系统，支持自定义因子计算、机器学习模型训练和预测、以及多种选股策略。

## 核心功能

### 1. 因子工程
- **内置因子**: 提供12个预定义因子，包括动量、波动率、技术指标、成交量和基本面因子
- **自定义因子**: 支持通过公式定义自定义因子
- **因子计算**: 自动计算因子值并进行标准化处理
- **因子分析**: 提供因子贡献度分析和行业分析

### 2. 机器学习模型
- **支持算法**: 随机森林、XGBoost、LightGBM
- **模型管理**: 模型定义、训练、预测、评估的完整生命周期
- **特征工程**: 自动特征选择、缩放和处理
- **模型评估**: 多种评估指标和交叉验证

### 3. 股票选择策略
- **因子权重法**: 基于因子权重的综合打分
- **机器学习法**: 基于ML模型预测的选股
- **集成方法**: 多模型集成选股
- **过滤条件**: 支持多种过滤条件

## 系统架构

```
app/
├── models/                     # 数据模型
│   ├── factor_definition.py   # 因子定义模型
│   ├── factor_values.py       # 因子值模型
│   ├── ml_model_definition.py # ML模型定义
│   ├── ml_predictions.py      # ML预测结果
│   ├── stock_income_statement.py # 利润表
│   └── stock_balance_sheet.py  # 资产负债表
├── services/                   # 业务逻辑
│   ├── factor_engine.py       # 因子计算引擎
│   ├── ml_models.py           # ML模型管理器
│   └── stock_scoring.py       # 股票打分引擎
└── api/                       # API接口
    └── ml_factor_api.py       # 多因子ML API
```

## 数据表结构

### 因子定义表 (factor_definition)
```sql
CREATE TABLE factor_definition (
    factor_id VARCHAR(50) PRIMARY KEY,
    factor_name VARCHAR(100) NOT NULL,
    factor_formula TEXT NOT NULL,
    factor_type VARCHAR(20) NOT NULL,
    description TEXT,
    params JSON,
    is_active BOOLEAN DEFAULT TRUE,
    created_at DATETIME,
    updated_at DATETIME
);
```

### 因子值表 (factor_values)
```sql
CREATE TABLE factor_values (
    ts_code VARCHAR(20),
    trade_date DATE,
    factor_id VARCHAR(50),
    factor_value DECIMAL(15,6),
    percentile_rank DECIMAL(5,2),
    z_score DECIMAL(10,4),
    created_at DATETIME,
    PRIMARY KEY (ts_code, trade_date, factor_id)
);
```

### ML模型定义表 (ml_model_definition)
```sql
CREATE TABLE ml_model_definition (
    model_id VARCHAR(50) PRIMARY KEY,
    model_name VARCHAR(100) NOT NULL,
    model_type VARCHAR(30) NOT NULL,
    factor_list JSON NOT NULL,
    target_type VARCHAR(20) NOT NULL,
    model_params JSON,
    training_config JSON,
    is_active BOOLEAN DEFAULT TRUE,
    created_at DATETIME,
    updated_at DATETIME
);
```

### ML预测结果表 (ml_predictions)
```sql
CREATE TABLE ml_predictions (
    ts_code VARCHAR(20),
    trade_date DATE,
    model_id VARCHAR(50),
    predicted_return DECIMAL(10,4),
    probability_score DECIMAL(10,4),
    rank_score INTEGER,
    created_at DATETIME,
    PRIMARY KEY (ts_code, trade_date, model_id)
);
```

## API接口

### 因子管理

#### 1. 创建自定义因子
```http
POST /api/ml-factor/factors/custom
Content-Type: application/json

{
    "factor_id": "momentum_10d_custom",
    "factor_name": "自定义10日动量",
    "factor_formula": "close.pct_change(10)",
    "factor_type": "momentum",
    "description": "自定义的10日价格变化率因子",
    "params": {"period": 10}
}
```

#### 2. 计算因子值
```http
POST /api/ml-factor/factors/calculate
Content-Type: application/json

{
    "trade_date": "2024-01-15",
    "factor_ids": ["momentum_1d", "momentum_5d", "volatility_20d"],
    "ts_codes": ["000001.SZ", "000002.SZ"]
}
```

#### 3. 获取因子列表
```http
GET /api/ml-factor/factors/list?factor_type=momentum&is_active=true
```

### 机器学习模型

#### 1. 创建模型定义
```http
POST /api/ml-factor/models/create
Content-Type: application/json

{
    "model_id": "rf_model_v1",
    "model_name": "随机森林选股模型V1",
    "model_type": "random_forest",
    "factor_list": [
        "momentum_1d", "momentum_5d", "momentum_20d",
        "volatility_20d", "rsi_14d", "ma_ratio_5_20"
    ],
    "target_type": "return_5d",
    "model_params": {
        "n_estimators": 200,
        "max_depth": 15,
        "min_samples_split": 10,
        "random_state": 42
    },
    "training_config": {
        "test_size": 0.2,
        "validation_method": "time_series_split",
        "cv_folds": 5,
        "feature_selection": True,
        "feature_selection_k": 15,
        "scaling_method": "robust"
    }
}
```

#### 2. 训练模型
```http
POST /api/ml-factor/models/train
Content-Type: application/json

{
    "model_id": "rf_model_v1",
    "start_date": "2023-01-01",
    "end_date": "2023-12-31"
}
```

#### 3. 模型预测
```http
POST /api/ml-factor/models/predict
Content-Type: application/json

{
    "model_id": "rf_model_v1",
    "trade_date": "2024-01-15",
    "ts_codes": null
}
```

#### 4. 模型评估
```http
POST /api/ml-factor/models/evaluate
Content-Type: application/json

{
    "model_id": "rf_model_v1",
    "start_date": "2024-01-01",
    "end_date": "2024-01-31"
}
```

### 股票选择和打分

#### 1. 基于因子的股票打分
```http
POST /api/ml-factor/scoring/factor-based
Content-Type: application/json

{
    "trade_date": "2024-01-15",
    "factor_list": [
        "momentum_5d", "momentum_20d", "volatility_20d",
        "rsi_14d", "ma_ratio_5_20", "turnover_rate_20d"
    ],
    "weights": {
        "momentum_5d": 0.2,
        "momentum_20d": 0.2,
        "volatility_20d": -0.1,
        "rsi_14d": 0.15,
        "ma_ratio_5_20": 0.25,
        "turnover_rate_20d": 0.2
    },
    "method": "factor_weight",
    "top_n": 20,
    "filters": {
        "min_percentile": 70,
        "exclude_codes": ["000001.SZ"]
    }
}
```

#### 2. 基于机器学习的股票选择
```http
POST /api/ml-factor/scoring/ml-based
Content-Type: application/json

{
    "trade_date": "2024-01-15",
    "model_ids": ["rf_model_v1", "xgb_model_v1"],
    "top_n": 30,
    "ensemble_method": "average"
}
```

### 分析功能

#### 1. 因子贡献度分析
```http
POST /api/ml-factor/analysis/factor-contribution
Content-Type: application/json

{
    "ts_code": "000001.SZ",
    "trade_date": "2024-01-15",
    "factor_list": [
        "momentum_5d", "momentum_20d", "volatility_20d",
        "rsi_14d", "ma_ratio_5_20", "pe_ttm", "pb_ratio"
    ]
}
```

#### 2. 行业分析
```http
POST /api/ml-factor/analysis/sector
Content-Type: application/json

{
    "trade_date": "2024-01-15",
    "factor_list": [
        "momentum_5d", "momentum_20d", "volatility_20d",
        "rsi_14d", "ma_ratio_5_20", "turnover_rate_20d"
    ],
    "top_n": 5
}
```

### 批量操作

#### 1. 批量计算因子并打分
```http
POST /api/ml-factor/batch/calculate-and-score
Content-Type: application/json

{
    "trade_date": "2024-01-15",
    "factor_list": [
        "momentum_1d", "momentum_5d", "volatility_20d",
        "rsi_14d", "ma_ratio_5_20"
    ],
    "weights": {
        "momentum_1d": 0.1,
        "momentum_5d": 0.3,
        "volatility_20d": -0.2,
        "rsi_14d": 0.2,
        "ma_ratio_5_20": 0.2
    },
    "method": "factor_weight",
    "top_n": 15
}
```

#### 2. 批量训练模型并预测
```http
POST /api/ml-factor/batch/train-and-predict
Content-Type: application/json

{
    "model_configs": [
        {
            "model_id": "rf_model_v1",
            "model_name": "随机森林模型V1",
            "model_type": "random_forest",
            "factor_list": ["momentum_1d", "momentum_5d", "volatility_20d"],
            "target_type": "return_5d"
        }
    ],
    "train_start_date": "2023-01-01",
    "train_end_date": "2023-12-31",
    "predict_date": "2024-01-15"
}
```

## 内置因子说明

### 动量因子
- `momentum_1d`: 1日价格变化率
- `momentum_5d`: 5日价格变化率  
- `momentum_20d`: 20日价格变化率

### 波动率因子
- `volatility_20d`: 20日收益率标准差

### 技术指标因子
- `rsi_14d`: 14日相对强弱指标
- `ma_ratio_5_20`: 5日/20日均线比率

### 成交量因子
- `turnover_rate_20d`: 20日平均换手率
- `volume_ratio_5_20`: 5日/20日成交量比率

### 基本面因子
- `pe_ttm`: 市盈率(TTM)
- `pb_ratio`: 市净率
- `roe_ttm`: 净资产收益率(TTM)
- `revenue_growth_yoy`: 营收同比增长率

## 使用流程

### 1. 初始化系统
```bash
# 创建数据表
python migrations/create_ml_factor_tables.py create

# 初始化内置因子定义
python migrations/create_ml_factor_tables.py init
```

### 2. 计算因子
```python
# 计算指定日期的所有因子
import requests

response = requests.post('http://localhost:5000/api/ml-factor/factors/calculate', json={
    'trade_date': '2024-01-15',
    'factor_ids': [],  # 空列表表示计算所有因子
    'ts_codes': []     # 空列表表示计算所有股票
})
```

### 3. 创建和训练模型
```python
# 创建模型定义
model_data = {
    "model_id": "my_model",
    "model_name": "我的选股模型",
    "model_type": "random_forest",
    "factor_list": ["momentum_5d", "volatility_20d", "rsi_14d"],
    "target_type": "return_5d"
}
requests.post('http://localhost:5000/api/ml-factor/models/create', json=model_data)

# 训练模型
train_data = {
    "model_id": "my_model",
    "start_date": "2023-01-01",
    "end_date": "2023-12-31"
}
requests.post('http://localhost:5000/api/ml-factor/models/train', json=train_data)
```

### 4. 股票选择
```python
# 基于因子的选股
scoring_data = {
    "trade_date": "2024-01-15",
    "factor_list": ["momentum_5d", "volatility_20d", "rsi_14d"],
    "weights": {"momentum_5d": 0.4, "volatility_20d": -0.3, "rsi_14d": 0.3},
    "method": "factor_weight",
    "top_n": 20
}
response = requests.post('http://localhost:5000/api/ml-factor/scoring/factor-based', json=scoring_data)

# 基于ML的选股
ml_data = {
    "trade_date": "2024-01-15",
    "model_ids": ["my_model"],
    "top_n": 20,
    "ensemble_method": "average"
}
response = requests.post('http://localhost:5000/api/ml-factor/scoring/ml-based', json=ml_data)
```

## 配置说明

### 模型参数配置
```python
# 随机森林参数
"model_params": {
    "n_estimators": 100,      # 树的数量
    "max_depth": 10,          # 最大深度
    "min_samples_split": 5,   # 分裂最小样本数
    "min_samples_leaf": 2,    # 叶子节点最小样本数
    "random_state": 42        # 随机种子
}

# XGBoost参数
"model_params": {
    "n_estimators": 100,      # 树的数量
    "max_depth": 6,           # 最大深度
    "learning_rate": 0.1,     # 学习率
    "subsample": 0.8,         # 样本采样比例
    "colsample_bytree": 0.8   # 特征采样比例
}
```

### 训练配置
```python
"training_config": {
    "test_size": 0.2,                    # 测试集比例
    "validation_method": "time_series_split",  # 验证方法
    "cv_folds": 5,                       # 交叉验证折数
    "feature_selection": True,           # 是否进行特征选择
    "feature_selection_k": 20,           # 选择的特征数量
    "scaling_method": "robust"           # 特征缩放方法
}
```

## 性能优化建议

### 1. 数据库优化
- 为因子值表创建合适的索引
- 定期清理历史数据
- 使用分区表存储大量历史数据

### 2. 计算优化
- 批量计算因子值
- 使用缓存减少重复计算
- 并行处理多个股票

### 3. 模型优化
- 定期重新训练模型
- 使用特征选择减少维度
- 调整模型参数提高性能

## 注意事项

1. **数据质量**: 确保输入数据的质量和完整性
2. **模型过拟合**: 注意防止模型过拟合，使用交叉验证
3. **因子失效**: 定期检查因子的有效性
4. **风险控制**: 结合风险管理进行股票选择
5. **回测验证**: 在实际使用前进行充分的回测验证

## 扩展功能

### 1. 自定义因子公式
支持更复杂的因子公式，包括：
- 数学运算符：+, -, *, /, **
- 统计函数：mean, std, max, min
- 技术指标：RSI, MACD, Bollinger Bands
- 时间序列函数：rolling, shift, pct_change

### 2. 高级选股策略
- 多因子IC加权
- 因子中性化
- 行业中性选股
- 风险平价组合

### 3. 模型集成
- Stacking集成
- Blending集成
- 动态权重调整
- 在线学习更新

## 故障排除

### 常见问题

1. **因子计算失败**
   - 检查数据源是否完整
   - 验证因子公式语法
   - 确认日期范围有效

2. **模型训练失败**
   - 检查训练数据是否充足
   - 验证因子数据完整性
   - 调整模型参数

3. **预测结果异常**
   - 检查模型是否已训练
   - 验证输入因子数据
   - 确认模型版本正确

### 日志查看
```bash
# 查看应用日志
tail -f logs/app.log

# 查看错误日志
grep ERROR logs/app.log
```

## 联系支持

如有问题或建议，请联系开发团队或查看项目文档。 