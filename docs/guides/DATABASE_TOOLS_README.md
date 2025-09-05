# 数据库探索和自定义因子生成工具

## 📋 概述

本工具集基于您的股票数据库表结构，提供了强大的数据库探索和自定义因子计算功能。包含以下主要组件：

1. **DatabaseExplorer** - 数据库探索器
2. **CustomFactorGenerator** - 基础自定义因子生成器  
3. **AdvancedFactorLibrary** - 高级因子库

## 🗄️ 数据库表结构

系统支持以下数据表：

### 基础数据表
- `stock_basic` - 股票基本信息
- `stock_daily_history` - 日线行情数据
- `stock_daily_basic` - 日线基本数据
- `stock_factor` - 技术指标数据

### 财务数据表
- `stock_income_statement` - 利润表
- `stock_balance_sheet` - 资产负债表
- `stock_cash_flow` - 现金流量表

### 市场数据表
- `stock_moneyflow` - 资金流向数据
- `stock_cyq_perf` - 筹码分布数据
- `stock_ma_data` - 移动平均线数据

### 因子存储表
- `factor_definition` - 因子定义表
- `factor_values` - 因子值存储表
- `ml_model_definition` - 模型定义表
- `ml_predictions` - 预测结果表

## 🚀 快速开始

### 1. 环境准备

确保已安装必要的依赖：

```bash
pip install pymysql pandas numpy
```

### 2. 数据库配置

默认数据库连接配置：
- 主机: localhost
- 用户: root
- 密码: root
- 数据库: stock_cursor

如需修改，请在代码中调整连接参数。

### 3. 快速测试

运行测试脚本验证环境：

```bash
python run_database_explorer.py
```

## 📊 功能详解

### DatabaseExplorer - 数据库探索器

#### 主要功能
- 查看所有数据表
- 查看表结构和字段说明
- 获取表的统计信息
- 查看样本数据

#### 使用示例

```python
from database_explorer import DatabaseExplorer

# 初始化探索器
db_explorer = DatabaseExplorer()

# 连接数据库
db_explorer.connect()

# 显示所有表
tables = db_explorer.show_tables()

# 查看表结构
db_explorer.describe_table('stock_daily_history')

# 获取表统计信息
stats = db_explorer.get_table_stats('stock_daily_history')

# 查看样本数据
sample = db_explorer.get_table_sample('stock_daily_history', 10)

# 关闭连接
db_explorer.close()
```

### CustomFactorGenerator - 基础因子生成器

#### 支持的因子类型

1. **价格动量因子**
   - 5日、10日、20日、60日动量
   - 成交量比率
   - 相对强弱指标

2. **基本面因子**
   - ROA、ROE
   - 收入增长率、利润增长率
   - 资产周转率
   - 现金流质量

3. **技术面因子**
   - 布林带位置
   - MACD信号强度
   - KDJ超买超卖信号
   - 技术指标一致性

4. **市场微观结构因子**
   - 大单净流入比例
   - 主力资金强度
   - 散户资金比例
   - 资金流向一致性

#### 使用示例

```python
from database_explorer import DatabaseExplorer, CustomFactorGenerator

# 初始化
db_explorer = DatabaseExplorer()
db_explorer.connect()
factor_generator = CustomFactorGenerator(db_explorer)

# 计算动量因子
momentum_factors = factor_generator.calculate_price_momentum_factors(
    ts_code="000001.SZ",
    start_date="2023-01-01",
    end_date="2023-12-31"
)

# 计算基本面因子
fundamental_factors = factor_generator.calculate_fundamental_factors(
    ts_code="000001.SZ",
    end_date="2023-12-31"
)

# 保存自定义因子
factor_generator.save_custom_factors(
    momentum_factors, 
    "momentum", 
    "price_momentum_5d"
)
```

### AdvancedFactorLibrary - 高级因子库

#### 支持的高级因子

1. **Alpha因子** (基于WorldQuant Alpha101)
   - Alpha001-Alpha005
   - 基于价格、成交量的复杂计算

2. **质量因子**
   - 盈利质量、盈利稳定性
   - 增长质量、资产质量
   - 财务杠杆质量、现金流质量

3. **情绪因子**
   - 主力资金情绪、散户情绪
   - 交易活跃度情绪
   - 价格位置情绪、估值情绪

4. **风险因子**
   - 价格波动率、下行风险
   - 最大回撤、VaR
   - 流动性风险、跳跃风险

5. **宏观因子**
   - 行业相对表现
   - 市值效应、价值效应
   - 地域效应、流动性效应

#### 使用示例

```python
from advanced_factor_library import AdvancedFactorLibrary

# 初始化高级因子库
factor_lib = AdvancedFactorLibrary()

# 生成综合因子报告
factor_report = factor_lib.generate_factor_report(
    ts_code="000001.SZ",
    start_date="2023-01-01",
    end_date="2023-12-31"
)

# 单独计算特定因子
alpha_factors = factor_lib.calculate_alpha_factors("000001.SZ", "2023-01-01", "2023-12-31")
sentiment_factors = factor_lib.calculate_sentiment_factors("000001.SZ", "2023-01-01", "2023-12-31")
risk_factors = factor_lib.calculate_risk_factors("000001.SZ", "2023-01-01", "2023-12-31")
```

## 🔧 自定义因子开发

### 添加新因子

1. **在CustomFactorGenerator中添加新方法**

```python
def calculate_my_custom_factor(self, ts_code=None, start_date=None, end_date=None):
    """计算自定义因子"""
    query = """
    SELECT 
        ts_code,
        trade_date,
        close,
        vol,
        -- 自定义计算逻辑
        close / LAG(close, 20) OVER (PARTITION BY ts_code ORDER BY trade_date) as my_factor
    FROM stock_daily_history
    WHERE ...
    """
    
    df = pd.read_sql(query, self.db.connection)
    
    # 进一步的Python计算
    df['enhanced_factor'] = df['my_factor'] * df['vol']
    
    return df
```

2. **在AdvancedFactorLibrary中添加复杂因子**

```python
def calculate_complex_factor(self, ts_code=None, start_date=None, end_date=None):
    """计算复杂因子"""
    # 多表联合查询
    query = """
    SELECT 
        h.ts_code,
        h.trade_date,
        h.close,
        m.net_mf_amount,
        d.pe,
        -- 复杂的SQL计算
    FROM stock_daily_history h
    LEFT JOIN stock_moneyflow m ON h.ts_code = m.ts_code AND h.trade_date = m.trade_date
    LEFT JOIN stock_daily_basic d ON h.ts_code = d.ts_code AND h.trade_date = d.trade_date
    """
    
    df = pd.read_sql(query, self.connection)
    
    # 复杂的pandas计算
    df['complex_factor'] = df.groupby('ts_code').apply(
        lambda x: some_complex_calculation(x)
    ).reset_index(0, drop=True)
    
    return df
```

## 📈 因子应用场景

### 1. 选股策略
- 使用质量因子筛选优质公司
- 使用动量因子识别趋势股票
- 使用估值因子寻找低估股票

### 2. 择时策略
- 使用情绪因子判断市场情绪
- 使用技术因子确定买卖时机
- 使用宏观因子分析市场环境

### 3. 风险管理
- 使用风险因子评估投资风险
- 使用波动率因子调整仓位
- 使用相关性因子进行组合优化

### 4. 量化研究
- 因子有效性分析
- 因子组合构建
- 回测验证

## 🛠️ 高级用法

### 批量计算因子

```python
# 批量计算多只股票的因子
stocks = ["000001.SZ", "000002.SZ", "600000.SH"]
all_factors = []

for stock in stocks:
    factors = factor_lib.generate_factor_report(
        stock, "2023-01-01", "2023-12-31"
    )
    if factors is not None:
        all_factors.append(factors)

# 合并所有因子数据
combined_factors = pd.concat(all_factors, ignore_index=True)
```

### 因子回测

```python
# 获取因子数据和收益数据
factors = factor_lib.calculate_alpha_factors("000001.SZ", "2023-01-01", "2023-12-31")

# 计算未来收益
factors['future_return'] = factors.groupby('ts_code')['close'].pct_change().shift(-1)

# 因子与收益的相关性分析
correlation = factors['alpha001'].corr(factors['future_return'])
print(f"Alpha001因子与未来收益相关性: {correlation:.4f}")
```

### 因子组合

```python
# 多因子组合
def create_composite_factor(df):
    """创建复合因子"""
    # 标准化各个因子
    df['alpha001_norm'] = (df['alpha001'] - df['alpha001'].mean()) / df['alpha001'].std()
    df['sentiment_norm'] = (df['composite_sentiment'] - df['composite_sentiment'].mean()) / df['composite_sentiment'].std()
    
    # 加权组合
    df['composite_factor'] = 0.4 * df['alpha001_norm'] + 0.6 * df['sentiment_norm']
    
    return df
```

## ⚠️ 注意事项

1. **数据质量**
   - 确保数据库中有足够的历史数据
   - 注意处理缺失值和异常值
   - 定期更新数据

2. **计算性能**
   - 大量数据计算时注意内存使用
   - 可以分批处理或使用数据库聚合
   - 考虑建立适当的数据库索引

3. **因子有效性**
   - 新因子需要进行回测验证
   - 注意避免过拟合
   - 定期评估因子衰减

4. **风险控制**
   - 因子投资存在风险
   - 需要结合风险管理
   - 注意市场环境变化

## 📞 技术支持

如有问题或建议，请：
1. 检查数据库连接配置
2. 确认数据表结构完整
3. 查看错误日志信息
4. 参考示例代码

## 🔄 更新日志

- v1.0: 初始版本，包含基础数据库探索功能
- v1.1: 添加自定义因子生成器
- v1.2: 增加高级因子库
- v1.3: 完善文档和示例代码

---

**祝您使用愉快！** 🎉 