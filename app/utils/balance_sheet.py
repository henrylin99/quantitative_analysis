from db_utils import DatabaseUtils
import pandas as pd
import time

# 初始化Tushare API
pro = DatabaseUtils.init_tushare_api()

# 连接到MySQL数据库
conn, cursor = DatabaseUtils.connect_to_mysql()

# 创建资产负债表数据表结构（如果还没有创建）
cursor.execute('''
    CREATE TABLE IF NOT EXISTS `stock_balance_sheet` (
      `ts_code` varchar(20) NOT NULL COMMENT 'TS股票代码',
      `ann_date` varchar(8) DEFAULT NULL COMMENT '公告日期',
      `f_ann_date` varchar(8) DEFAULT NULL COMMENT '实际公告日期',
      `end_date` varchar(8) NOT NULL COMMENT '报告期',
      `report_type` varchar(10) DEFAULT NULL COMMENT '报告类型',
      `comp_type` varchar(10) DEFAULT NULL COMMENT '公司类型',
      `end_type` varchar(10) DEFAULT NULL COMMENT '报告期类型',
      `total_share` decimal(20,4) DEFAULT NULL COMMENT '期末总股本',
      `cap_rese` decimal(20,4) DEFAULT NULL COMMENT '资本公积金',
      `undistr_porfit` decimal(20,4) DEFAULT NULL COMMENT '未分配利润',
      `surplus_rese` decimal(20,4) DEFAULT NULL COMMENT '盈余公积金',
      `special_rese` decimal(20,4) DEFAULT NULL COMMENT '专项储备',
      `money_cap` decimal(20,4) DEFAULT NULL COMMENT '货币资金',
      `trad_asset` decimal(20,4) DEFAULT NULL COMMENT '交易性金融资产',
      `notes_receiv` decimal(20,4) DEFAULT NULL COMMENT '应收票据',
      `accounts_receiv` decimal(20,4) DEFAULT NULL COMMENT '应收账款',
      `oth_receiv` decimal(20,4) DEFAULT NULL COMMENT '其他应收款',
      `prepayment` decimal(20,4) DEFAULT NULL COMMENT '预付款项',
      `div_receiv` decimal(20,4) DEFAULT NULL COMMENT '应收股利',
      `int_receiv` decimal(20,4) DEFAULT NULL COMMENT '应收利息',
      `inventories` decimal(20,4) DEFAULT NULL COMMENT '存货',
      `amor_exp` decimal(20,4) DEFAULT NULL COMMENT '长期待摊费用',
      `nca_within_1y` decimal(20,4) DEFAULT NULL COMMENT '一年内到期的非流动资产',
      `sett_rsrv` decimal(20,4) DEFAULT NULL COMMENT '结算备付金',
      `loanto_oth_bank_fi` decimal(20,4) DEFAULT NULL COMMENT '拆出资金',
      `premium_receiv` decimal(20,4) DEFAULT NULL COMMENT '应收保费',
      `reinsur_receiv` decimal(20,4) DEFAULT NULL COMMENT '应收分保账款',
      `reinsur_res_receiv` decimal(20,4) DEFAULT NULL COMMENT '应收分保合同准备金',
      `pur_resale_fa` decimal(20,4) DEFAULT NULL COMMENT '买入返售金融资产',
      `oth_cur_assets` decimal(20,4) DEFAULT NULL COMMENT '其他流动资产',
      `total_cur_assets` decimal(20,4) DEFAULT NULL COMMENT '流动资产合计',
      `fa_avail_for_sale` decimal(20,4) DEFAULT NULL COMMENT '可供出售金融资产',
      `htm_invest` decimal(20,4) DEFAULT NULL COMMENT '持有至到期投资',
      `lt_eqt_invest` decimal(20,4) DEFAULT NULL COMMENT '长期股权投资',
      `invest_real_estate` decimal(20,4) DEFAULT NULL COMMENT '投资性房地产',
      `time_deposits` decimal(20,4) DEFAULT NULL COMMENT '定期存款',
      `oth_assets` decimal(20,4) DEFAULT NULL COMMENT '其他资产',
      `lt_rec` decimal(20,4) DEFAULT NULL COMMENT '长期应收款',
      `fix_assets` decimal(20,4) DEFAULT NULL COMMENT '固定资产',
      `cip` decimal(20,4) DEFAULT NULL COMMENT '在建工程',
      `const_materials` decimal(20,4) DEFAULT NULL COMMENT '工程物资',
      `fixed_assets_disp` decimal(20,4) DEFAULT NULL COMMENT '固定资产清理',
      `produc_bio_assets` decimal(20,4) DEFAULT NULL COMMENT '生产性生物资产',
      `oil_and_gas_assets` decimal(20,4) DEFAULT NULL COMMENT '油气资产',
      `intan_assets` decimal(20,4) DEFAULT NULL COMMENT '无形资产',
      `r_and_d` decimal(20,4) DEFAULT NULL COMMENT '开发支出',
      `goodwill` decimal(20,4) DEFAULT NULL COMMENT '商誉',
      `lt_amor_exp` decimal(20,4) DEFAULT NULL COMMENT '长期待摊费用',
      `defer_tax_assets` decimal(20,4) DEFAULT NULL COMMENT '递延所得税资产',
      `decr_in_disbur` decimal(20,4) DEFAULT NULL COMMENT '发放贷款及垫款',
      `oth_nca` decimal(20,4) DEFAULT NULL COMMENT '其他非流动资产',
      `total_nca` decimal(20,4) DEFAULT NULL COMMENT '非流动资产合计',
      `cash_reser_cb` decimal(20,4) DEFAULT NULL COMMENT '现金及存放中央银行款项',
      `depos_in_oth_bfi` decimal(20,4) DEFAULT NULL COMMENT '存放同业和其它金融机构款项',
      `prec_metals` decimal(20,4) DEFAULT NULL COMMENT '贵金属',
      `deriv_assets` decimal(20,4) DEFAULT NULL COMMENT '衍生金融资产',
      `rr_reins_une_prem` decimal(20,4) DEFAULT NULL COMMENT '应收分保未到期责任准备金',
      `rr_reins_outstd_cla` decimal(20,4) DEFAULT NULL COMMENT '应收分保未决赔款准备金',
      `rr_reins_lins_liab` decimal(20,4) DEFAULT NULL COMMENT '应收分保寿险责任准备金',
      `rr_reins_lthins_liab` decimal(20,4) DEFAULT NULL COMMENT '应收分保长期健康险责任准备金',
      `refund_depos` decimal(20,4) DEFAULT NULL COMMENT '存出保证金',
      `ph_pledge_loans` decimal(20,4) DEFAULT NULL COMMENT '保户质押贷款',
      `refund_cap_depos` decimal(20,4) DEFAULT NULL COMMENT '存出资本保证金',
      `indep_acct_assets` decimal(20,4) DEFAULT NULL COMMENT '独立账户资产',
      `client_depos` decimal(20,4) DEFAULT NULL COMMENT '其中：客户资金存款',
      `client_prov` decimal(20,4) DEFAULT NULL COMMENT '其中：客户备付金',
      `transac_seat_fee` decimal(20,4) DEFAULT NULL COMMENT '其中:交易席位费',
      `invest_as_receiv` decimal(20,4) DEFAULT NULL COMMENT '应收款项类投资',
      `total_assets` decimal(20,4) DEFAULT NULL COMMENT '资产总计',
      `lt_borr` decimal(20,4) DEFAULT NULL COMMENT '长期借款',
      `st_borr` decimal(20,4) DEFAULT NULL COMMENT '短期借款',
      `cb_borr` decimal(20,4) DEFAULT NULL COMMENT '向中央银行借款',
      `depos_ib_deposits` decimal(20,4) DEFAULT NULL COMMENT '吸收存款及同业存放',
      `loan_oth_bank` decimal(20,4) DEFAULT NULL COMMENT '拆入资金',
      `trading_fl` decimal(20,4) DEFAULT NULL COMMENT '交易性金融负债',
      `notes_payable` decimal(20,4) DEFAULT NULL COMMENT '应付票据',
      `acct_payable` decimal(20,4) DEFAULT NULL COMMENT '应付账款',
      `adv_receipts` decimal(20,4) DEFAULT NULL COMMENT '预收款项',
      `sold_for_repur_fa` decimal(20,4) DEFAULT NULL COMMENT '卖出回购金融资产款',
      `comm_payable` decimal(20,4) DEFAULT NULL COMMENT '应付手续费及佣金',
      `payroll_payable` decimal(20,4) DEFAULT NULL COMMENT '应付职工薪酬',
      `taxes_payable` decimal(20,4) DEFAULT NULL COMMENT '应交税费',
      `int_payable` decimal(20,4) DEFAULT NULL COMMENT '应付利息',
      `div_payable` decimal(20,4) DEFAULT NULL COMMENT '应付股利',
      `oth_payable` decimal(20,4) DEFAULT NULL COMMENT '其他应付款',
      `acc_exp` decimal(20,4) DEFAULT NULL COMMENT '预提费用',
      `deferred_inc` decimal(20,4) DEFAULT NULL COMMENT '递延收益',
      `st_bonds_payable` decimal(20,4) DEFAULT NULL COMMENT '应付短期债券',
      `payable_to_reinsurer` decimal(20,4) DEFAULT NULL COMMENT '应付分保账款',
      `rsrv_insur_cont` decimal(20,4) DEFAULT NULL COMMENT '保险合同准备金',
      `acting_trading_sec` decimal(20,4) DEFAULT NULL COMMENT '代理买卖证券款',
      `acting_uw_sec` decimal(20,4) DEFAULT NULL COMMENT '代理承销证券款',
      `non_cur_liab_due_1y` decimal(20,4) DEFAULT NULL COMMENT '一年内到期的非流动负债',
      `oth_cur_liab` decimal(20,4) DEFAULT NULL COMMENT '其他流动负债',
      `total_cur_liab` decimal(20,4) DEFAULT NULL COMMENT '流动负债合计',
      `bond_payable` decimal(20,4) DEFAULT NULL COMMENT '应付债券',
      `lt_payable` decimal(20,4) DEFAULT NULL COMMENT '长期应付款',
      `specific_payables` decimal(20,4) DEFAULT NULL COMMENT '专项应付款',
      `estimated_liab` decimal(20,4) DEFAULT NULL COMMENT '预计负债',
      `defer_tax_liab` decimal(20,4) DEFAULT NULL COMMENT '递延所得税负债',
      `defer_inc_non_cur_liab` decimal(20,4) DEFAULT NULL COMMENT '递延收益-非流动负债',
      `oth_ncl` decimal(20,4) DEFAULT NULL COMMENT '其他非流动负债',
      `total_ncl` decimal(20,4) DEFAULT NULL COMMENT '非流动负债合计',
      `depos_oth_bfi` decimal(20,4) DEFAULT NULL COMMENT '同业和其它金融机构存放款项',
      `deriv_liab` decimal(20,4) DEFAULT NULL COMMENT '衍生金融负债',
      `depos` decimal(20,4) DEFAULT NULL COMMENT '吸收存款',
      `agency_bus_liab` decimal(20,4) DEFAULT NULL COMMENT '代理业务负债',
      `oth_liab` decimal(20,4) DEFAULT NULL COMMENT '其他负债',
      `prem_receiv_adva` decimal(20,4) DEFAULT NULL COMMENT '预收保费',
      `depos_received` decimal(20,4) DEFAULT NULL COMMENT '存入保证金',
      `ph_invest` decimal(20,4) DEFAULT NULL COMMENT '保户储金及投资款',
      `reser_une_prem` decimal(20,4) DEFAULT NULL COMMENT '未到期责任准备金',
      `reser_outstd_claims` decimal(20,4) DEFAULT NULL COMMENT '未决赔款准备金',
      `reser_lins_liab` decimal(20,4) DEFAULT NULL COMMENT '寿险责任准备金',
      `reser_lthins_liab` decimal(20,4) DEFAULT NULL COMMENT '长期健康险责任准备金',
      `indept_acc_liab` decimal(20,4) DEFAULT NULL COMMENT '独立账户负债',
      `pledge_borr` decimal(20,4) DEFAULT NULL COMMENT '其中：质押借款',
      `indem_payable` decimal(20,4) DEFAULT NULL COMMENT '应付赔付款',
      `policy_div_payable` decimal(20,4) DEFAULT NULL COMMENT '应付保单红利',
      `total_liab` decimal(20,4) DEFAULT NULL COMMENT '负债合计',
      `treasury_share` decimal(20,4) DEFAULT NULL COMMENT '减:库存股',
      `ordin_risk_reser` decimal(20,4) DEFAULT NULL COMMENT '一般风险准备',
      `forex_differ` decimal(20,4) DEFAULT NULL COMMENT '外币报表折算差额',
      `invest_loss_unconf` decimal(20,4) DEFAULT NULL COMMENT '未确认投资损失',
      `minority_int` decimal(20,4) DEFAULT NULL COMMENT '少数股东权益',
      `total_hldr_eqy_exc_min_int` decimal(20,4) DEFAULT NULL COMMENT '股东权益合计(不含少数股东权益)',
      `total_hldr_eqy_inc_min_int` decimal(20,4) DEFAULT NULL COMMENT '股东权益合计(含少数股东权益)',
      `total_liab_hldr_eqy` decimal(20,4) DEFAULT NULL COMMENT '负债及股东权益总计',
      `lt_payroll_payable` decimal(20,4) DEFAULT NULL COMMENT '长期应付职工薪酬',
      `oth_comp_income` decimal(20,4) DEFAULT NULL COMMENT '其他综合收益',
      `oth_eqt_tools` decimal(20,4) DEFAULT NULL COMMENT '其他权益工具',
      `oth_eqt_tools_p_shr` decimal(20,4) DEFAULT NULL COMMENT '其他权益工具(优先股)',
      `lending_funds` decimal(20,4) DEFAULT NULL COMMENT '融出资金',
      `acc_receivable` decimal(20,4) DEFAULT NULL COMMENT '应收款项',
      `st_fin_payable` decimal(20,4) DEFAULT NULL COMMENT '应付短期融资款',
      `payables` decimal(20,4) DEFAULT NULL COMMENT '应付款项',
      `hfs_assets` decimal(20,4) DEFAULT NULL COMMENT '持有待售资产',
      `hfs_sales` decimal(20,4) DEFAULT NULL COMMENT '持有待售负债',
      `cost_fin_assets` decimal(20,4) DEFAULT NULL COMMENT '以摊余成本计量的金融资产',
      `fair_value_fin_assets` decimal(20,4) DEFAULT NULL COMMENT '以公允价值计量且其变动计入其他综合收益的金融资产',
      `contract_assets` decimal(20,4) DEFAULT NULL COMMENT '合同资产',
      `contract_liab` decimal(20,4) DEFAULT NULL COMMENT '合同负债',
      `accounts_receiv_bill` decimal(20,4) DEFAULT NULL COMMENT '应收票据及应收账款',
      `accounts_pay` decimal(20,4) DEFAULT NULL COMMENT '应付票据及应付账款',
      `oth_rcv_total` decimal(20,4) DEFAULT NULL COMMENT '其他应收款(合计)',
      `fix_assets_total` decimal(20,4) DEFAULT NULL COMMENT '固定资产(合计)',
      `cip_total` decimal(20,4) DEFAULT NULL COMMENT '在建工程(合计)',
      `oth_pay_total` decimal(20,4) DEFAULT NULL COMMENT '其他应付款(合计)',
      `long_pay_total` decimal(20,4) DEFAULT NULL COMMENT '长期应付款(合计)',
      `debt_invest` decimal(20,4) DEFAULT NULL COMMENT '债权投资',
      `oth_debt_invest` decimal(20,4) DEFAULT NULL COMMENT '其他债权投资',
      `update_flag` varchar(1) DEFAULT NULL COMMENT '更新标识',
      PRIMARY KEY (`ts_code`,`end_date`)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='资产负债表数据表';
''')

# 获取股票代码列表
cursor.execute('''
SELECT ts_code FROM stock_basic limit 200 offset 4500;
''')
stock_list = cursor.fetchall()

print(f"总共需要处理 {len(stock_list)} 只股票的资产负债表数据")

# 定义字段列表
fields = [
    "ts_code", "ann_date", "f_ann_date", "end_date", "report_type", "comp_type", "end_type",
    "total_share", "cap_rese", "undistr_porfit", "surplus_rese", "special_rese", "money_cap",
    "trad_asset", "notes_receiv", "accounts_receiv", "oth_receiv", "prepayment", "div_receiv",
    "int_receiv", "inventories", "amor_exp", "nca_within_1y", "sett_rsrv", "loanto_oth_bank_fi",
    "premium_receiv", "reinsur_receiv", "reinsur_res_receiv", "pur_resale_fa", "oth_cur_assets",
    "total_cur_assets", "fa_avail_for_sale", "htm_invest", "lt_eqt_invest", "invest_real_estate",
    "time_deposits", "oth_assets", "lt_rec", "fix_assets", "cip", "const_materials",
    "fixed_assets_disp", "produc_bio_assets", "oil_and_gas_assets", "intan_assets", "r_and_d",
    "goodwill", "lt_amor_exp", "defer_tax_assets", "decr_in_disbur", "oth_nca", "total_nca",
    "cash_reser_cb", "depos_in_oth_bfi", "prec_metals", "deriv_assets", "rr_reins_une_prem",
    "rr_reins_outstd_cla", "rr_reins_lins_liab", "rr_reins_lthins_liab", "refund_depos",
    "ph_pledge_loans", "refund_cap_depos", "indep_acct_assets", "client_depos", "client_prov",
    "transac_seat_fee", "invest_as_receiv", "total_assets", "lt_borr", "st_borr", "cb_borr",
    "depos_ib_deposits", "loan_oth_bank", "trading_fl", "notes_payable", "acct_payable",
    "adv_receipts", "sold_for_repur_fa", "comm_payable", "payroll_payable", "taxes_payable",
    "int_payable", "div_payable", "oth_payable", "acc_exp", "deferred_inc", "st_bonds_payable",
    "payable_to_reinsurer", "rsrv_insur_cont", "acting_trading_sec", "acting_uw_sec",
    "non_cur_liab_due_1y", "oth_cur_liab", "total_cur_liab", "bond_payable", "lt_payable",
    "specific_payables", "estimated_liab", "defer_tax_liab", "defer_inc_non_cur_liab", "oth_ncl",
    "total_ncl", "depos_oth_bfi", "deriv_liab", "depos", "agency_bus_liab", "oth_liab",
    "prem_receiv_adva", "depos_received", "ph_invest", "reser_une_prem", "reser_outstd_claims",
    "reser_lins_liab", "reser_lthins_liab", "indept_acc_liab", "pledge_borr", "indem_payable",
    "policy_div_payable", "total_liab", "treasury_share", "ordin_risk_reser", "forex_differ",
    "invest_loss_unconf", "minority_int", "total_hldr_eqy_exc_min_int", "total_hldr_eqy_inc_min_int",
    "total_liab_hldr_eqy", "lt_payroll_payable", "oth_comp_income", "oth_eqt_tools",
    "oth_eqt_tools_p_shr", "lending_funds", "acc_receivable", "st_fin_payable", "payables",
    "hfs_assets", "hfs_sales", "cost_fin_assets", "fair_value_fin_assets", "contract_assets",
    "contract_liab", "accounts_receiv_bill", "accounts_pay", "oth_rcv_total", "fix_assets_total",
    "cip_total", "oth_pay_total", "long_pay_total", "debt_invest", "oth_debt_invest", "update_flag"
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
            # 调用Tushare资产负债表接口
            data = pro.balancesheet(**{
                "ts_code": ts_code,
                "ann_date": "",
                "f_ann_date": "",
                "start_date": 20200101,
                "end_date": 20250430,
                "period": "",
                "report_type": "",
                "comp_type": "",
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
                    INSERT IGNORE INTO stock_balance_sheet ({columns})
                    VALUES ({placeholders})
                    '''
                    
                    # 准备数据值，处理NaN值
                    values = []
                    for field in fields:
                        value = row[field] if pd.notna(row[field]) else None
                        values.append(value)
                    
                    cursor.execute(insert_sql, values)
                
                success_count += 1
                print(f"成功处理股票 {ts_code}，获取到 {len(data)} 条资产负债表记录")
            else:
                print(f"股票 {ts_code} 没有资产负债表数据")
                
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