#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
增强版财务因子测试脚本
测试基于三张财务报表的丰富因子计算
"""

from enhanced_financial_factors import EnhancedFinancialFactors
import pandas as pd

def test_enhanced_financial_factors():
    """测试增强版财务因子计算"""
    print("🧪 测试增强版财务因子计算工具")
    print("=" * 80)
    
    # 初始化计算器
    calculator = EnhancedFinancialFactors()
    
    try:
        # 测试参数
        test_stocks = ["000001.SZ", "000002.SZ", "600000.SH"]  # 多只股票测试
        start_date = "2021-12-31"
        end_date = "2023-12-31"
        
        all_results = []
        
        for stock in test_stocks:
            print(f"\n{'='*60}")
            print(f"📊 测试股票: {stock}")
            print(f"{'='*60}")
            
            # 生成财务因子报告
            financial_factors = calculator.generate_financial_report(stock, start_date, end_date)
            
            if financial_factors is not None and not financial_factors.empty:
                print(f"\n✅ 股票 {stock} 财务因子计算成功")
                print(f"📊 数据条数: {len(financial_factors)}")
                
                # 显示最新一期的关键因子
                latest_data = financial_factors.sort_values('end_date').tail(1)
                
                key_metrics = [
                    'gross_profit_margin', 'net_profit_margin', 'current_ratio', 
                    'debt_to_equity', 'total_asset_turnover', 'operating_cashflow_ratio',
                    'revenue_growth_yoy', 'net_profit_growth_yoy'
                ]
                
                print(f"\n📋 股票 {stock} 最新财务因子:")
                for metric in key_metrics:
                    if metric in latest_data.columns:
                        value = latest_data[metric].iloc[0]
                        if pd.notna(value):
                            print(f"  {metric}: {value:.4f}")
                        else:
                            print(f"  {metric}: N/A")
                
                all_results.append(financial_factors)
            else:
                print(f"❌ 股票 {stock} 财务因子计算失败")
        
        # 综合分析
        if all_results:
            print(f"\n{'='*80}")
            print("📊 综合分析结果")
            print(f"{'='*80}")
            
            combined_data = pd.concat(all_results, ignore_index=True)
            
            print(f"📈 总计处理数据: {len(combined_data)} 条记录")
            print(f"📊 涉及股票数量: {combined_data['ts_code'].nunique()} 只")
            print(f"📅 时间跨度: {combined_data['end_date'].min()} 至 {combined_data['end_date'].max()}")
            
            # 因子统计
            numeric_columns = combined_data.select_dtypes(include=['float64', 'int64']).columns
            factor_count = len([col for col in numeric_columns if col not in ['ts_code', 'end_date']])
            print(f"🧮 计算因子数量: {factor_count} 个")
            
            print("\n📊 主要财务因子统计摘要:")
            key_stats = [
                'gross_profit_margin', 'net_profit_margin', 'current_ratio',
                'debt_to_equity', 'total_asset_turnover', 'revenue_growth_yoy'
            ]
            
            for stat in key_stats:
                if stat in combined_data.columns:
                    values = combined_data[stat].dropna()
                    if len(values) > 0:
                        print(f"  {stat}:")
                        print(f"    均值: {values.mean():.4f}")
                        print(f"    中位数: {values.median():.4f}")
                        print(f"    标准差: {values.std():.4f}")
                        print(f"    最小值: {values.min():.4f}")
                        print(f"    最大值: {values.max():.4f}")
            
            return combined_data
        else:
            print("❌ 未能获取任何财务因子数据")
            return None
            
    except Exception as e:
        print(f"❌ 测试过程中出错: {e}")
        return None
    finally:
        calculator.close()

def demo_factor_categories():
    """演示各类财务因子的计算"""
    print("\n🎯 财务因子分类演示")
    print("=" * 80)
    
    calculator = EnhancedFinancialFactors()
    
    try:
        # 获取原始财务数据
        sample_stock = "000001.SZ"
        financial_data = calculator.get_comprehensive_financial_data(
            ts_code=sample_stock, 
            start_date="2022-12-31", 
            end_date="2023-12-31"
        )
        
        if financial_data is None or financial_data.empty:
            print("❌ 未获取到财务数据")
            return
        
        print(f"📊 原始财务数据: {len(financial_data)} 条记录")
        
        # 分别演示各类因子计算
        print("\n🔍 分类计算各类财务因子:")
        
        # 1. 盈利能力因子
        profitability_data = calculator.calculate_profitability_factors(financial_data.copy())
        profit_factors = [col for col in profitability_data.columns if 'margin' in col or 'ratio' in col][:5]
        print(f"  💰 盈利能力因子: {len(profit_factors)} 个")
        print(f"     示例: {', '.join(profit_factors)}")
        
        # 2. 偿债能力因子
        solvency_data = calculator.calculate_solvency_factors(financial_data.copy())
        solvency_factors = [col for col in solvency_data.columns if 'ratio' in col or 'debt' in col][:5]
        print(f"  🏦 偿债能力因子: {len(solvency_factors)} 个")
        print(f"     示例: {', '.join(solvency_factors)}")
        
        # 3. 营运能力因子
        operational_data = calculator.calculate_operational_efficiency_factors(financial_data.copy())
        operational_factors = [col for col in operational_data.columns if 'turnover' in col or 'days' in col][:5]
        print(f"  ⚡ 营运能力因子: {len(operational_factors)} 个")
        print(f"     示例: {', '.join(operational_factors)}")
        
        # 4. 现金流因子
        cashflow_data = calculator.calculate_cashflow_factors(financial_data.copy())
        cashflow_factors = [col for col in cashflow_data.columns if 'cashflow' in col or 'cash' in col][:5]
        print(f"  💰 现金流因子: {len(cashflow_factors)} 个")
        print(f"     示例: {', '.join(cashflow_factors)}")
        
        # 5. 成长能力因子
        growth_data = calculator.calculate_growth_factors(financial_data.copy())
        growth_factors = [col for col in growth_data.columns if 'growth' in col][:5]
        print(f"  📈 成长能力因子: {len(growth_factors)} 个")
        print(f"     示例: {', '.join(growth_factors)}")
        
        print(f"\n📊 总计财务因子数量: 估计超过100个")
        print("💡 这些因子覆盖了公司财务分析的各个维度")
        
    except Exception as e:
        print(f"❌ 演示过程中出错: {e}")
    finally:
        calculator.close()

def main():
    """主函数"""
    print("🚀 增强版财务因子测试工具")
    print("基于利润表、资产负债表、现金流量表的全面财务因子计算")
    print("=" * 100)
    
    # 1. 基础功能测试
    result = test_enhanced_financial_factors()
    
    # 2. 因子分类演示
    demo_factor_categories()
    
    print("\n🎉 测试完成!")
    print("\n💡 主要特点:")
    print("1. 📊 利用三张财务报表的所有字段计算因子")
    print("2. 💰 盈利能力: 毛利率、净利率、费用控制、投资收益等")
    print("3. 🏦 偿债能力: 流动比率、资产负债率、利息保障等")
    print("4. ⚡ 营运能力: 资产周转率、现金转换周期、资产管理等")
    print("5. 💰 现金流质量: 现金流比率、现金流稳定性等")
    print("6. 📈 成长能力: 收入增长、利润增长、可持续增长等")
    print("7. 🧮 超过100个细分财务因子，全面覆盖财务分析维度")
    
    print("\n📋 使用建议:")
    print("1. 可以单独使用某一类因子进行专项分析")
    print("2. 结合多类因子进行综合财务健康度评估")
    print("3. 通过时间序列分析观察财务状况变化趋势")
    print("4. 可以将这些因子用于机器学习模型的特征工程")

if __name__ == "__main__":
    main() 