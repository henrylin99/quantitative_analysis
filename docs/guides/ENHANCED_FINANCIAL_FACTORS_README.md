# 增强版财务因子计算工具

## 📋 概述

基于利润表（stock_income_statement）、资产负债表（stock_balance_sheet）、现金流量表（stock_cash_flow）三张财务报表的完整字段，计算超过100个细分财务因子的综合工具。

## 🎯 主要特点

- **📊 全面覆盖**: 利用三张财务报表的所有字段
- **🧮 丰富因子**: 计算超过100个细分财务因子
- **📈 多维分析**: 涵盖盈利、偿债、营运、现金流、成长五大维度
- **⏰ 时间序列**: 支持历史数据趋势分析
- **🔄 增长分析**: 同比、环比、复合增长率计算
- **📊 质量评估**: 财务质量和稳定性分析

## 🗂️ 财务因子分类

### 1. 💰 盈利能力因子（约25个）

#### 基础盈利指标
- `gross_profit_margin` - 毛利率
- `operating_profit_margin` - 营业利润率  
- `net_profit_margin` - 净利润率
- `ebit_margin` - EBIT利润率
- `ebitda_margin` - EBITDA利润率

#### 费用控制能力
- `expense_ratio` - 期间费用率
- `selling_expense_ratio` - 销售费用率
- `admin_expense_ratio` - 管理费用率
- `rd_expense_ratio` - 研发费用率
- `finance_expense_ratio` - 财务费用率

#### 投资与其他收益
- `investment_income_ratio` - 投资收益率
- `fair_value_gain_ratio` - 公允价值变动收益率
- `non_operating_income_ratio` - 营业外收入比例

#### 税收效率
- `effective_tax_rate` - 实际税率
- `tax_burden` - 税收负担率

#### 盈利质量
- `core_profit_ratio` - 核心利润比例
- `minority_profit_ratio` - 少数股东损益比例

### 2. 🏦 偿债能力因子（约20个）

#### 短期偿债能力
- `current_ratio` - 流动比率
- `quick_ratio` - 速动比率
- `cash_ratio` - 现金比率
- `super_quick_ratio` - 超速动比率

#### 长期偿债能力
- `debt_to_equity` - 资产负债率
- `debt_to_assets` - 负债总资产比
- `equity_ratio` - 股东权益比率
- `long_debt_to_equity` - 长期负债权益比

#### 债务结构
- `short_debt_ratio` - 短期债务比例
- `long_debt_ratio` - 长期债务比例
- `interest_bearing_debt_ratio` - 有息债务比率

#### 利息保障能力
- `interest_coverage` - 利息保障倍数
- `ebitda_interest_coverage` - EBITDA利息保障倍数
- `cashflow_interest_coverage` - 现金流利息保障倍数

#### 财务杠杆
- `financial_leverage` - 财务杠杆
- `contingent_liability_ratio` - 或有负债比例

### 3. ⚡ 营运能力因子（约20个）

#### 资产周转能力
- `total_asset_turnover` - 总资产周转率
- `fixed_asset_turnover` - 固定资产周转率
- `current_asset_turnover` - 流动资产周转率
- `working_capital_turnover` - 营运资本周转率

#### 应收账款管理
- `receivables_turnover` - 应收账款周转率
- `receivables_days` - 应收账款周转天数
- `receivables_ratio` - 应收账款占收入比
- `bad_debt_ratio` - 坏账比例

#### 存货管理
- `inventory_turnover` - 存货周转率
- `inventory_days` - 存货周转天数
- `inventory_ratio` - 存货占流动资产比

#### 应付账款管理
- `payables_turnover` - 应付账款周转率
- `payables_days` - 应付账款周转天数
- `cash_conversion_cycle` - 现金转换周期

#### 资产结构分析
- `intangible_asset_ratio` - 无形资产比例
- `goodwill_ratio` - 商誉比例
- `rd_asset_ratio` - 研发资产比例
- `capital_intensity` - 资本密集度

### 4. 💰 现金流因子（约25个）

#### 现金流基本比率
- `operating_cashflow_ratio` - 经营现金流比率
- `free_cashflow_ratio` - 自由现金流比率
- `cashflow_coverage_ratio` - 现金流量覆盖比率

#### 现金流质量
- `operating_cf_to_net_income` - 经营现金流与净利润比
- `free_cf_to_net_income` - 自由现金流与净利润比
- `accruals_ratio` - 应计项目比率

#### 现金管理能力
- `cash_to_assets` - 现金资产比
- `cash_to_current_liab` - 现金流动负债比
- `cash_growth_rate` - 现金增长率

#### 投资现金流分析
- `capex_ratio` - 资本支出比率
- `capex_to_operating_cf` - 资本支出与经营现金流比
- `investment_intensity` - 投资强度

#### 筹资现金流分析
- `debt_financing_ratio` - 债务筹资比例
- `equity_financing_ratio` - 股权筹资比例
- `dividend_payout_ratio` - 股利支付率

#### 现金流稳定性
- `operating_cf_variability` - 经营现金流变异性
- `free_cf_variability` - 自由现金流变异性
- `cf_prediction_ability` - 现金流预测能力

### 5. 📈 成长能力因子（约30个）

#### 收入增长
- `revenue_growth_yoy` - 同比收入增长率
- `revenue_growth_qoq` - 环比收入增长率
- `revenue_cagr_3y` - 3年收入复合增长率

#### 利润增长
- `net_profit_growth_yoy` - 同比净利润增长率
- `operating_profit_growth_yoy` - 同比营业利润增长率
- `ebit_growth_yoy` - 同比EBIT增长率
- `ebitda_growth_yoy` - 同比EBITDA增长率

#### 资产增长
- `total_assets_growth_yoy` - 同比总资产增长率
- `fixed_assets_growth_yoy` - 同比固定资产增长率
- `net_assets_growth_yoy` - 同比净资产增长率

#### 每股指标增长
- `eps_growth_yoy` - 同比每股收益增长率
- `book_value_per_share_growth` - 每股净资产增长率

#### 现金流增长
- `operating_cf_growth_yoy` - 同比经营现金流增长率
- `free_cf_growth_yoy` - 同比自由现金流增长率

#### 研发增长
- `rd_growth_yoy` - 同比研发支出增长率
- `rd_intensity_change` - 研发强度变化

#### 成长质量
- `sustainable_growth_rate` - 可持续增长率
- `revenue_profit_growth_match` - 收入利润增长匹配度
- `asset_profit_growth_match` - 资产利润增长匹配度

#### 增长趋势与稳定性
- `revenue_growth_trend` - 收入增长趋势
- `profit_growth_trend` - 利润增长趋势
- `revenue_growth_stability` - 收入增长稳定性
- `profit_growth_stability` - 利润增长稳定性

## 🚀 快速开始

### 1. 基本使用

```python
from enhanced_financial_factors import EnhancedFinancialFactors

# 初始化计算器
calculator = EnhancedFinancialFactors()

# 生成财务因子报告
financial_factors = calculator.generate_financial_report(
    ts_code="000001.SZ",
    start_date="2020-12-31",
    end_date="2023-12-31"
)

# 关闭连接
calculator.close()
```

### 2. 分类计算因子

```python
# 获取原始财务数据
financial_data = calculator.get_comprehensive_financial_data(
    ts_code="000001.SZ", 
    start_date="2020-12-31", 
    end_date="2023-12-31"
)

# 分别计算各类因子
profitability_factors = calculator.calculate_profitability_factors(financial_data)
solvency_factors = calculator.calculate_solvency_factors(financial_data)
operational_factors = calculator.calculate_operational_efficiency_factors(financial_data)
cashflow_factors = calculator.calculate_cashflow_factors(financial_data)
growth_factors = calculator.calculate_growth_factors(financial_data)
```

### 3. 批量分析多只股票

```python
stocks = ["000001.SZ", "000002.SZ", "600000.SH"]
all_results = []

for stock in stocks:
    result = calculator.generate_financial_report(stock, "2020-12-31", "2023-12-31")
    if result is not None:
        all_results.append(result)

# 合并数据进行横向对比
import pandas as pd
combined_data = pd.concat(all_results, ignore_index=True)
```

## 📊 数据来源

### 利润表字段（stock_income_statement）
- 营业收入、成本、费用明细
- 各项损益科目
- 税费、净利润
- 每股收益指标
- 综合收益项目

### 资产负债表字段（stock_balance_sheet）
- 流动资产、非流动资产明细
- 流动负债、非流动负债明细  
- 股东权益各项目
- 特殊行业科目（银行、保险等）

### 现金流量表字段（stock_cash_flow）
- 经营活动现金流详细项目
- 投资活动现金流详细项目
- 筹资活动现金流详细项目
- 现金及等价物变动
- 补充资料项目

## 🔧 高级用法

### 1. 因子筛选与排名

```python
# 选择特定因子进行分析
key_factors = [
    'gross_profit_margin', 'net_profit_margin', 'current_ratio',
    'total_asset_turnover', 'operating_cashflow_ratio', 'revenue_growth_yoy'
]

# 计算因子排名
for factor in key_factors:
    financial_factors[f'{factor}_rank'] = financial_factors.groupby('end_date')[factor].rank(pct=True)
```

### 2. 财务健康度评分

```python
def calculate_financial_health_score(df):
    """计算财务健康度综合评分"""
    
    # 盈利能力权重
    profitability_score = (
        df['gross_profit_margin'].rank(pct=True) * 0.3 +
        df['net_profit_margin'].rank(pct=True) * 0.4 +
        df['operating_profit_margin'].rank(pct=True) * 0.3
    )
    
    # 偿债能力权重
    solvency_score = (
        df['current_ratio'].rank(pct=True) * 0.4 +
        (1 - df['debt_to_equity'].rank(pct=True)) * 0.6  # 负债率越低越好
    )
    
    # 营运能力权重
    operational_score = (
        df['total_asset_turnover'].rank(pct=True) * 0.5 +
        df['receivables_turnover'].rank(pct=True) * 0.3 +
        df['inventory_turnover'].rank(pct=True) * 0.2
    )
    
    # 综合评分
    health_score = (
        profitability_score * 0.4 +
        solvency_score * 0.3 +
        operational_score * 0.3
    )
    
    return health_score

# 应用评分函数
financial_factors['health_score'] = calculate_financial_health_score(financial_factors)
```

### 3. 时间序列分析

```python
# 分析财务指标趋势
def analyze_trends(df, metric):
    """分析特定指标的趋势"""
    df_sorted = df.sort_values(['ts_code', 'end_date'])
    
    # 计算变化率
    df_sorted[f'{metric}_change'] = df_sorted.groupby('ts_code')[metric].pct_change()
    
    # 计算趋势斜率
    df_sorted[f'{metric}_trend'] = df_sorted.groupby('ts_code')[metric].rolling(4).apply(
        lambda x: np.polyfit(range(len(x)), x, 1)[0] if len(x) >= 2 else np.nan
    )
    
    return df_sorted

# 分析关键指标趋势
financial_factors = analyze_trends(financial_factors, 'net_profit_margin')
financial_factors = analyze_trends(financial_factors, 'revenue_growth_yoy')
```

## 📈 应用场景

### 1. 基本面分析
- 公司财务健康度评估
- 盈利能力分析
- 风险评估

### 2. 投资研究
- 股票筛选
- 投资组合构建
- 风险管理

### 3. 量化投资
- 多因子模型构建
- 特征工程
- 机器学习建模

### 4. 财务分析
- 同行业对比分析
- 历史趋势分析
- 预警系统构建

## ⚠️ 注意事项

### 1. 数据质量
- 确保财务数据的完整性和准确性
- 注意处理特殊情况（重组、会计政策变更等）
- 关注数据的时效性

### 2. 行业差异
- 不同行业的财务指标标准不同
- 金融行业需要特殊处理
- 新兴行业可能缺乏对比基准

### 3. 计算限制
- 分母为零的情况需要特殊处理
- 极值可能影响分析结果
- 需要考虑会计准则变化的影响

### 4. 解释说明
- 因子值需要结合行业背景解释
- 单一因子不能完全说明问题
- 需要综合多个维度进行分析

## 🔄 更新日志

- v1.0: 初始版本，包含5大类100+财务因子
- v1.1: 优化计算逻辑，提高数据处理效率
- v1.2: 增加异常值处理和数据验证
- v1.3: 完善文档和使用示例

## 📞 技术支持

如有问题或建议：
1. 检查数据库表结构是否完整
2. 确认数据库连接配置正确
3. 查看计算过程中的警告信息
4. 参考使用示例和文档说明

---

**这是目前最全面的财务因子计算工具，充分利用了三张财务报表的丰富数据！** 🎉 