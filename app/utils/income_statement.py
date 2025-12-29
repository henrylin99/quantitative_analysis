from db_utils import DatabaseUtils
import pandas as pd
import time

# 初始化Tushare API
pro = DatabaseUtils.init_tushare_api()

# 连接到MySQL数据库
conn, cursor = DatabaseUtils.connect_to_mysql()

# 创建利润表数据表结构（如果还没有创建）
cursor.execute('''
    CREATE TABLE IF NOT EXISTS `stock_income_statement` (
      `ts_code` varchar(20) NOT NULL COMMENT 'TS股票代码',
      `ann_date` varchar(8) DEFAULT NULL COMMENT '公告日期',
      `f_ann_date` varchar(8) DEFAULT NULL COMMENT '实际公告日期',
      `end_date` varchar(8) NOT NULL COMMENT '报告期',
      `report_type` varchar(10) DEFAULT NULL COMMENT '报告类型',
      `comp_type` varchar(10) DEFAULT NULL COMMENT '公司类型',
      `end_type` varchar(10) DEFAULT NULL COMMENT '报告期类型',
      `basic_eps` decimal(10,4) DEFAULT NULL COMMENT '基本每股收益',
      `diluted_eps` decimal(10,4) DEFAULT NULL COMMENT '稀释每股收益',
      `total_revenue` decimal(20,4) DEFAULT NULL COMMENT '营业总收入',
      `revenue` decimal(20,4) DEFAULT NULL COMMENT '营业收入',
      `int_income` decimal(20,4) DEFAULT NULL COMMENT '利息收入',
      `prem_earned` decimal(20,4) DEFAULT NULL COMMENT '已赚保费',
      `comm_income` decimal(20,4) DEFAULT NULL COMMENT '手续费及佣金收入',
      `n_commis_income` decimal(20,4) DEFAULT NULL COMMENT '手续费及佣金净收入',
      `n_oth_income` decimal(20,4) DEFAULT NULL COMMENT '其他经营净收益',
      `n_oth_b_income` decimal(20,4) DEFAULT NULL COMMENT '加:其他业务净收益',
      `prem_income` decimal(20,4) DEFAULT NULL COMMENT '保险业务收入',
      `out_prem` decimal(20,4) DEFAULT NULL COMMENT '减:分出保费',
      `une_prem_reser` decimal(20,4) DEFAULT NULL COMMENT '提取未到期责任准备金',
      `reins_income` decimal(20,4) DEFAULT NULL COMMENT '其中:分保费收入',
      `n_sec_tb_income` decimal(20,4) DEFAULT NULL COMMENT '代理买卖证券业务净收入',
      `n_sec_uw_income` decimal(20,4) DEFAULT NULL COMMENT '证券承销业务净收入',
      `n_asset_mg_income` decimal(20,4) DEFAULT NULL COMMENT '受托客户资产管理业务净收入',
      `oth_b_income` decimal(20,4) DEFAULT NULL COMMENT '其他业务收入',
      `fv_value_chg_gain` decimal(20,4) DEFAULT NULL COMMENT '加:公允价值变动净收益',
      `invest_income` decimal(20,4) DEFAULT NULL COMMENT '加:投资净收益',
      `ass_invest_income` decimal(20,4) DEFAULT NULL COMMENT '其中:对联营企业和合营企业的投资收益',
      `forex_gain` decimal(20,4) DEFAULT NULL COMMENT '加:汇兑净收益',
      `total_cogs` decimal(20,4) DEFAULT NULL COMMENT '营业总成本',
      `oper_cost` decimal(20,4) DEFAULT NULL COMMENT '减:营业成本',
      `int_exp` decimal(20,4) DEFAULT NULL COMMENT '减:利息支出',
      `comm_exp` decimal(20,4) DEFAULT NULL COMMENT '减:手续费及佣金支出',
      `biz_tax_surchg` decimal(20,4) DEFAULT NULL COMMENT '减:营业税金及附加',
      `sell_exp` decimal(20,4) DEFAULT NULL COMMENT '减:销售费用',
      `admin_exp` decimal(20,4) DEFAULT NULL COMMENT '减:管理费用',
      `fin_exp` decimal(20,4) DEFAULT NULL COMMENT '减:财务费用',
      `assets_impair_loss` decimal(20,4) DEFAULT NULL COMMENT '减:资产减值损失',
      `prem_refund` decimal(20,4) DEFAULT NULL COMMENT '退保金',
      `compens_payout` decimal(20,4) DEFAULT NULL COMMENT '赔付总支出',
      `reser_insur_liab` decimal(20,4) DEFAULT NULL COMMENT '提取保险责任准备金',
      `div_payt` decimal(20,4) DEFAULT NULL COMMENT '保户红利支出',
      `reins_exp` decimal(20,4) DEFAULT NULL COMMENT '分保费用',
      `oper_exp` decimal(20,4) DEFAULT NULL COMMENT '营业支出',
      `compens_payout_refu` decimal(20,4) DEFAULT NULL COMMENT '减:摊回赔付支出',
      `insur_reser_refu` decimal(20,4) DEFAULT NULL COMMENT '减:摊回保险责任准备金',
      `reins_cost_refund` decimal(20,4) DEFAULT NULL COMMENT '减:摊回分保费用',
      `other_bus_cost` decimal(20,4) DEFAULT NULL COMMENT '其他业务成本',
      `operate_profit` decimal(20,4) DEFAULT NULL COMMENT '营业利润',
      `non_oper_income` decimal(20,4) DEFAULT NULL COMMENT '加:营业外收入',
      `non_oper_exp` decimal(20,4) DEFAULT NULL COMMENT '减:营业外支出',
      `nca_disploss` decimal(20,4) DEFAULT NULL COMMENT '其中:减:非流动资产处置净损失',
      `total_profit` decimal(20,4) DEFAULT NULL COMMENT '利润总额',
      `income_tax` decimal(20,4) DEFAULT NULL COMMENT '所得税费用',
      `n_income` decimal(20,4) DEFAULT NULL COMMENT '净利润',
      `n_income_attr_p` decimal(20,4) DEFAULT NULL COMMENT '归属于母公司所有者的净利润',
      `minority_gain` decimal(20,4) DEFAULT NULL COMMENT '少数股东损益',
      `oth_compr_income` decimal(20,4) DEFAULT NULL COMMENT '其他综合收益',
      `t_compr_income` decimal(20,4) DEFAULT NULL COMMENT '综合收益总额',
      `compr_inc_attr_p` decimal(20,4) DEFAULT NULL COMMENT '归属于母公司所有者的综合收益总额',
      `compr_inc_attr_m_s` decimal(20,4) DEFAULT NULL COMMENT '归属于少数股东的综合收益总额',
      `ebit` decimal(20,4) DEFAULT NULL COMMENT '息税前利润',
      `ebitda` decimal(20,4) DEFAULT NULL COMMENT '息税折旧摊销前利润',
      `insurance_exp` decimal(20,4) DEFAULT NULL COMMENT '保险业务支出',
      `undist_profit` decimal(20,4) DEFAULT NULL COMMENT '年初未分配利润',
      `distable_profit` decimal(20,4) DEFAULT NULL COMMENT '可分配利润',
      `rd_exp` decimal(20,4) DEFAULT NULL COMMENT '研发费用',
      `fin_exp_int_exp` decimal(20,4) DEFAULT NULL COMMENT '财务费用:利息费用',
      `fin_exp_int_inc` decimal(20,4) DEFAULT NULL COMMENT '财务费用:利息收入',
      `transfer_surplus_rese` decimal(20,4) DEFAULT NULL COMMENT '转入盈余公积',
      `transfer_housing_imprest` decimal(20,4) DEFAULT NULL COMMENT '转入住房周转金',
      `transfer_oth` decimal(20,4) DEFAULT NULL COMMENT '转入其他',
      `adj_lossgain` decimal(20,4) DEFAULT NULL COMMENT '调整以前年度损益',
      `withdra_legal_surplus` decimal(20,4) DEFAULT NULL COMMENT '提取法定盈余公积',
      `withdra_legal_pubfund` decimal(20,4) DEFAULT NULL COMMENT '提取法定公益金',
      `withdra_biz_devfund` decimal(20,4) DEFAULT NULL COMMENT '提取企业发展基金',
      `withdra_rese_fund` decimal(20,4) DEFAULT NULL COMMENT '提取储备基金',
      `withdra_oth_ersu` decimal(20,4) DEFAULT NULL COMMENT '提取其他',
      `workers_welfare` decimal(20,4) DEFAULT NULL COMMENT '职工奖金福利',
      `distr_profit_shrhder` decimal(20,4) DEFAULT NULL COMMENT '可供股东分配的利润',
      `prfshare_payable_dvd` decimal(20,4) DEFAULT NULL COMMENT '应付优先股股利',
      `comshare_payable_dvd` decimal(20,4) DEFAULT NULL COMMENT '应付普通股股利',
      `capit_comstock_div` decimal(20,4) DEFAULT NULL COMMENT '转作股本的普通股股利',
      `continued_net_profit` decimal(20,4) DEFAULT NULL COMMENT '持续经营净利润',
      `update_flag` varchar(1) DEFAULT NULL COMMENT '更新标识',
      PRIMARY KEY (`ts_code`,`end_date`)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='利润表数据表';
''')

# 获取股票代码列表
cursor.execute('''
SELECT ts_code FROM stock_basic limit 200 offset 4500;
''')
stock_list = cursor.fetchall()

print(f"总共需要处理 {len(stock_list)} 只股票的利润表数据")

# 定义字段列表
fields = [
    "ts_code", "ann_date", "f_ann_date", "end_date", "report_type", "comp_type", "end_type",
    "basic_eps", "diluted_eps", "total_revenue", "revenue", "int_income", "prem_earned",
    "comm_income", "n_commis_income", "n_oth_income", "n_oth_b_income", "prem_income",
    "out_prem", "une_prem_reser", "reins_income", "n_sec_tb_income", "n_sec_uw_income",
    "n_asset_mg_income", "oth_b_income", "fv_value_chg_gain", "invest_income",
    "ass_invest_income", "forex_gain", "total_cogs", "oper_cost", "int_exp", "comm_exp",
    "biz_tax_surchg", "sell_exp", "admin_exp", "fin_exp", "assets_impair_loss",
    "prem_refund", "compens_payout", "reser_insur_liab", "div_payt", "reins_exp",
    "oper_exp", "compens_payout_refu", "insur_reser_refu", "reins_cost_refund",
    "other_bus_cost", "operate_profit", "non_oper_income", "non_oper_exp", "nca_disploss",
    "total_profit", "income_tax", "n_income", "n_income_attr_p", "minority_gain",
    "oth_compr_income", "t_compr_income", "compr_inc_attr_p", "compr_inc_attr_m_s",
    "ebit", "ebitda", "insurance_exp", "undist_profit", "distable_profit", "rd_exp",
    "fin_exp_int_exp", "fin_exp_int_inc", "transfer_surplus_rese", "transfer_housing_imprest",
    "transfer_oth", "adj_lossgain", "withdra_legal_surplus", "withdra_legal_pubfund",
    "withdra_biz_devfund", "withdra_rese_fund", "withdra_oth_ersu", "workers_welfare",
    "distr_profit_shrhder", "prfshare_payable_dvd", "comshare_payable_dvd",
    "capit_comstock_div", "continued_net_profit", "update_flag"
]

# 批量处理股票数据
batch_size = 50  # 减少批次大小，避免API限制
success_count = 0
error_count = 0

for i in range(0, len(stock_list), batch_size):
    batch_stock_list = stock_list[i:i + batch_size]
    
    for stock in batch_stock_list:
        ts_code = stock[0]

        # 批次间稍作休息
        time.sleep(3.3)
        
        try:
            # 调用Tushare利润表接口
            data = pro.income(**{
                "ts_code": ts_code,
                "ann_date": "",
                "f_ann_date": "",
                "start_date": 20200101,
                "end_date": 20250430,
                "period": "",
                "report_type": "",
                "comp_type": "",
                "is_calc": "",
                "limit": "",
                "offset": ""
            }, fields=fields)
            
            if not data.empty:
                # 插入数据到数据库
                for index, row in data.iterrows():
                    # 构建插入SQL语句
                    placeholders = ', '.join(['%s'] * len(fields))
                    columns = ', '.join(fields)
                    
                    insert_sql = f'''
                    INSERT IGNORE INTO stock_income_statement ({columns})
                    VALUES ({placeholders})
                    '''
                    
                    # 准备数据值，处理NaN值
                    values = []
                    for field in fields:
                        value = row[field] if pd.notna(row[field]) else None
                        values.append(value)
                    
                    cursor.execute(insert_sql, values)
                
                success_count += 1
                print(f"成功处理股票 {ts_code}，获取到 {len(data)} 条利润表记录")
            else:
                print(f"股票 {ts_code} 没有利润表数据")
                
        except Exception as e:
            error_count += 1
            print(f"处理股票 {ts_code} 时出错: {str(e)}")
    
    # 每个批次提交一次事务
    conn.commit()
    print(f"已处理 {min(i + batch_size, len(stock_list))} / {len(stock_list)} 只股票")

print(f"\n数据获取完成！")
print(f"成功处理: {success_count} 只股票")
print(f"处理失败: {error_count} 只股票")

# 关闭数据库连接
cursor.close()
conn.close() 