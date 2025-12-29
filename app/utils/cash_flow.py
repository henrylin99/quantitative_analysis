from db_utils import DatabaseUtils
import pandas as pd
import time

# 初始化Tushare API
pro = DatabaseUtils.init_tushare_api()

# 连接到MySQL数据库
conn, cursor = DatabaseUtils.connect_to_mysql()

# 创建现金流量表数据表结构（如果还没有创建）
cursor.execute('''
    CREATE TABLE IF NOT EXISTS `stock_cash_flow` (
      `ts_code` varchar(20) NOT NULL COMMENT 'TS股票代码',
      `ann_date` varchar(8) DEFAULT NULL COMMENT '公告日期',
      `f_ann_date` varchar(8) DEFAULT NULL COMMENT '实际公告日期',
      `end_date` varchar(8) NOT NULL COMMENT '报告期',
      `comp_type` varchar(10) DEFAULT NULL COMMENT '公司类型',
      `report_type` varchar(10) DEFAULT NULL COMMENT '报告类型',
      `end_type` varchar(10) DEFAULT NULL COMMENT '报告期类型',
      `net_profit` decimal(20,4) DEFAULT NULL COMMENT '净利润',
      `finan_exp` decimal(20,4) DEFAULT NULL COMMENT '财务费用',
      `c_fr_sale_sg` decimal(20,4) DEFAULT NULL COMMENT '销售商品、提供劳务收到的现金',
      `recp_tax_rends` decimal(20,4) DEFAULT NULL COMMENT '收到的税费返还',
      `n_depos_incr_fi` decimal(20,4) DEFAULT NULL COMMENT '客户存款和同业存放款项净增加额',
      `n_incr_loans_cb` decimal(20,4) DEFAULT NULL COMMENT '向中央银行借款净增加额',
      `n_inc_borr_oth_fi` decimal(20,4) DEFAULT NULL COMMENT '向其他金融机构拆入资金净增加额',
      `prem_fr_orig_contr` decimal(20,4) DEFAULT NULL COMMENT '收到原保险合同保费取得的现金',
      `n_incr_insured_dep` decimal(20,4) DEFAULT NULL COMMENT '保户储金净增加额',
      `n_reinsur_prem` decimal(20,4) DEFAULT NULL COMMENT '收到再保业务现金净额',
      `n_incr_disp_tfa` decimal(20,4) DEFAULT NULL COMMENT '处置交易性金融资产净增加额',
      `ifc_cash_incr` decimal(20,4) DEFAULT NULL COMMENT '收取利息和手续费净增加额',
      `n_incr_disp_faas` decimal(20,4) DEFAULT NULL COMMENT '处置可供出售金融资产净增加额',
      `n_incr_loans_oth_bank` decimal(20,4) DEFAULT NULL COMMENT '拆入资金净增加额',
      `n_cap_incr_repur` decimal(20,4) DEFAULT NULL COMMENT '回购业务资金净增加额',
      `c_fr_oth_operate_a` decimal(20,4) DEFAULT NULL COMMENT '收到其他与经营活动有关的现金',
      `c_inf_fr_operate_a` decimal(20,4) DEFAULT NULL COMMENT '经营活动现金流入小计',
      `c_paid_goods_s` decimal(20,4) DEFAULT NULL COMMENT '购买商品、接受劳务支付的现金',
      `c_paid_to_for_empl` decimal(20,4) DEFAULT NULL COMMENT '支付给职工以及为职工支付的现金',
      `c_paid_for_taxes` decimal(20,4) DEFAULT NULL COMMENT '支付的各项税费',
      `n_incr_clt_loan_adv` decimal(20,4) DEFAULT NULL COMMENT '客户贷款及垫款净增加额',
      `n_incr_dep_cbob` decimal(20,4) DEFAULT NULL COMMENT '存放央行和同业款项净增加额',
      `c_pay_claims_orig_inco` decimal(20,4) DEFAULT NULL COMMENT '支付原保险合同赔付款项的现金',
      `pay_handling_chrg` decimal(20,4) DEFAULT NULL COMMENT '支付手续费的现金',
      `pay_comm_insur_plcy` decimal(20,4) DEFAULT NULL COMMENT '支付保单红利的现金',
      `oth_cash_pay_oper_act` decimal(20,4) DEFAULT NULL COMMENT '支付其他与经营活动有关的现金',
      `st_cash_out_act` decimal(20,4) DEFAULT NULL COMMENT '经营活动现金流出小计',
      `n_cashflow_act` decimal(20,4) DEFAULT NULL COMMENT '经营活动产生的现金流量净额',
      `oth_recp_ral_inv_act` decimal(20,4) DEFAULT NULL COMMENT '收到其他与投资活动有关的现金',
      `c_disp_withdrwl_invest` decimal(20,4) DEFAULT NULL COMMENT '收回投资收到的现金',
      `c_recp_return_invest` decimal(20,4) DEFAULT NULL COMMENT '取得投资收益收到的现金',
      `n_recp_disp_fiolta` decimal(20,4) DEFAULT NULL COMMENT '处置固定资产无形资产和其他长期资产收回的现金净额',
      `n_recp_disp_sobu` decimal(20,4) DEFAULT NULL COMMENT '处置子公司及其他营业单位收到的现金净额',
      `stot_inflows_inv_act` decimal(20,4) DEFAULT NULL COMMENT '投资活动现金流入小计',
      `c_pay_acq_const_fiolta` decimal(20,4) DEFAULT NULL COMMENT '购建固定资产无形资产和其他长期资产支付的现金',
      `c_paid_invest` decimal(20,4) DEFAULT NULL COMMENT '投资支付的现金',
      `n_disp_subs_oth_biz` decimal(20,4) DEFAULT NULL COMMENT '取得子公司及其他营业单位支付的现金净额',
      `oth_pay_ral_inv_act` decimal(20,4) DEFAULT NULL COMMENT '支付其他与投资活动有关的现金',
      `n_incr_pledge_loan` decimal(20,4) DEFAULT NULL COMMENT '质押贷款净增加额',
      `stot_out_inv_act` decimal(20,4) DEFAULT NULL COMMENT '投资活动现金流出小计',
      `n_cashflow_inv_act` decimal(20,4) DEFAULT NULL COMMENT '投资活动产生的现金流量净额',
      `c_recp_borrow` decimal(20,4) DEFAULT NULL COMMENT '取得借款收到的现金',
      `proc_issue_bonds` decimal(20,4) DEFAULT NULL COMMENT '发行债券收到的现金',
      `oth_cash_recp_ral_fnc_act` decimal(20,4) DEFAULT NULL COMMENT '收到其他与筹资活动有关的现金',
      `stot_cash_in_fnc_act` decimal(20,4) DEFAULT NULL COMMENT '筹资活动现金流入小计',
      `free_cashflow` decimal(20,4) DEFAULT NULL COMMENT '企业自由现金流量',
      `c_prepay_amt_borr` decimal(20,4) DEFAULT NULL COMMENT '偿还债务支付的现金',
      `c_pay_dist_dpcp_int_exp` decimal(20,4) DEFAULT NULL COMMENT '分配股利、利润或偿付利息支付的现金',
      `incl_dvd_profit_paid_sc_ms` decimal(20,4) DEFAULT NULL COMMENT '其中:子公司支付给少数股东的股利、利润',
      `oth_cashpay_ral_fnc_act` decimal(20,4) DEFAULT NULL COMMENT '支付其他与筹资活动有关的现金',
      `stot_cashout_fnc_act` decimal(20,4) DEFAULT NULL COMMENT '筹资活动现金流出小计',
      `n_cash_flows_fnc_act` decimal(20,4) DEFAULT NULL COMMENT '筹资活动产生的现金流量净额',
      `eff_fx_flu_cash` decimal(20,4) DEFAULT NULL COMMENT '汇率变动对现金的影响',
      `n_incr_cash_cash_equ` decimal(20,4) DEFAULT NULL COMMENT '现金及现金等价物净增加额',
      `c_cash_equ_beg_period` decimal(20,4) DEFAULT NULL COMMENT '期初现金及现金等价物余额',
      `c_cash_equ_end_period` decimal(20,4) DEFAULT NULL COMMENT '期末现金及现金等价物余额',
      `c_recp_cap_contrib` decimal(20,4) DEFAULT NULL COMMENT '吸收投资收到的现金',
      `incl_cash_rec_saims` decimal(20,4) DEFAULT NULL COMMENT '其中:子公司吸收少数股东投资收到的现金',
      `uncon_invest_loss` decimal(20,4) DEFAULT NULL COMMENT '未确认投资损失',
      `prov_depr_assets` decimal(20,4) DEFAULT NULL COMMENT '加:资产减值准备',
      `depr_fa_coga_dpba` decimal(20,4) DEFAULT NULL COMMENT '固定资产折旧、油气资产折耗、生产性生物资产折旧',
      `amort_intang_assets` decimal(20,4) DEFAULT NULL COMMENT '无形资产摊销',
      `lt_amort_deferred_exp` decimal(20,4) DEFAULT NULL COMMENT '长期待摊费用摊销',
      `decr_deferred_exp` decimal(20,4) DEFAULT NULL COMMENT '待摊费用减少',
      `incr_acc_exp` decimal(20,4) DEFAULT NULL COMMENT '预提费用增加',
      `loss_disp_fiolta` decimal(20,4) DEFAULT NULL COMMENT '处置固定、无形资产和其他长期资产的损失',
      `loss_scr_fa` decimal(20,4) DEFAULT NULL COMMENT '固定资产报废损失',
      `loss_fv_chg` decimal(20,4) DEFAULT NULL COMMENT '公允价值变动损失',
      `invest_loss` decimal(20,4) DEFAULT NULL COMMENT '投资损失',
      `decr_def_inc_tax_assets` decimal(20,4) DEFAULT NULL COMMENT '递延所得税资产减少',
      `incr_def_inc_tax_liab` decimal(20,4) DEFAULT NULL COMMENT '递延所得税负债增加',
      `decr_inventories` decimal(20,4) DEFAULT NULL COMMENT '存货的减少',
      `decr_oper_payable` decimal(20,4) DEFAULT NULL COMMENT '经营性应收项目的减少',
      `incr_oper_payable` decimal(20,4) DEFAULT NULL COMMENT '经营性应付项目的增加',
      `others` decimal(20,4) DEFAULT NULL COMMENT '其他',
      `im_net_cashflow_oper_act` decimal(20,4) DEFAULT NULL COMMENT '经营活动产生的现金流量净额(间接法)',
      `conv_debt_into_cap` decimal(20,4) DEFAULT NULL COMMENT '债务转为资本',
      `conv_copbonds_due_within_1y` decimal(20,4) DEFAULT NULL COMMENT '一年内到期的可转换公司债券',
      `fa_fnc_leases` decimal(20,4) DEFAULT NULL COMMENT '融资租入固定资产',
      `im_n_incr_cash_equ` decimal(20,4) DEFAULT NULL COMMENT '现金及现金等价物净增加额(间接法)',
      `net_dism_capital_add` decimal(20,4) DEFAULT NULL COMMENT '拆出资金净增加额',
      `net_cash_rece_sec` decimal(20,4) DEFAULT NULL COMMENT '代理买卖证券收到的现金净额',
      `credit_impa_loss` decimal(20,4) DEFAULT NULL COMMENT '信用减值损失',
      `use_right_asset_dep` decimal(20,4) DEFAULT NULL COMMENT '使用权资产折旧',
      `oth_loss_asset` decimal(20,4) DEFAULT NULL COMMENT '其他资产减值损失',
      `end_bal_cash` decimal(20,4) DEFAULT NULL COMMENT '现金的期末余额',
      `beg_bal_cash` decimal(20,4) DEFAULT NULL COMMENT '现金的期初余额',
      `end_bal_cash_equ` decimal(20,4) DEFAULT NULL COMMENT '现金等价物的期末余额',
      `beg_bal_cash_equ` decimal(20,4) DEFAULT NULL COMMENT '现金等价物的期初余额',
      `update_flag` varchar(1) DEFAULT NULL COMMENT '更新标识',
      PRIMARY KEY (`ts_code`,`end_date`)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='现金流量表数据表';
''')

# 获取股票代码列表
cursor.execute('''
SELECT ts_code FROM stock_basic limit 200 offset 4500;
''')
stock_list = cursor.fetchall()

print(f"总共需要处理 {len(stock_list)} 只股票的现金流量表数据")

# 定义字段列表
fields = [
    "ts_code", "ann_date", "f_ann_date", "end_date", "comp_type", "report_type", "end_type",
    "net_profit", "finan_exp", "c_fr_sale_sg", "recp_tax_rends", "n_depos_incr_fi",
    "n_incr_loans_cb", "n_inc_borr_oth_fi", "prem_fr_orig_contr", "n_incr_insured_dep",
    "n_reinsur_prem", "n_incr_disp_tfa", "ifc_cash_incr", "n_incr_disp_faas",
    "n_incr_loans_oth_bank", "n_cap_incr_repur", "c_fr_oth_operate_a", "c_inf_fr_operate_a",
    "c_paid_goods_s", "c_paid_to_for_empl", "c_paid_for_taxes", "n_incr_clt_loan_adv",
    "n_incr_dep_cbob", "c_pay_claims_orig_inco", "pay_handling_chrg", "pay_comm_insur_plcy",
    "oth_cash_pay_oper_act", "st_cash_out_act", "n_cashflow_act", "oth_recp_ral_inv_act",
    "c_disp_withdrwl_invest", "c_recp_return_invest", "n_recp_disp_fiolta", "n_recp_disp_sobu",
    "stot_inflows_inv_act", "c_pay_acq_const_fiolta", "c_paid_invest", "n_disp_subs_oth_biz",
    "oth_pay_ral_inv_act", "n_incr_pledge_loan", "stot_out_inv_act", "n_cashflow_inv_act",
    "c_recp_borrow", "proc_issue_bonds", "oth_cash_recp_ral_fnc_act", "stot_cash_in_fnc_act",
    "free_cashflow", "c_prepay_amt_borr", "c_pay_dist_dpcp_int_exp", "incl_dvd_profit_paid_sc_ms",
    "oth_cashpay_ral_fnc_act", "stot_cashout_fnc_act", "n_cash_flows_fnc_act", "eff_fx_flu_cash",
    "n_incr_cash_cash_equ", "c_cash_equ_beg_period", "c_cash_equ_end_period", "c_recp_cap_contrib",
    "incl_cash_rec_saims", "uncon_invest_loss", "prov_depr_assets", "depr_fa_coga_dpba",
    "amort_intang_assets", "lt_amort_deferred_exp", "decr_deferred_exp", "incr_acc_exp",
    "loss_disp_fiolta", "loss_scr_fa", "loss_fv_chg", "invest_loss", "decr_def_inc_tax_assets",
    "incr_def_inc_tax_liab", "decr_inventories", "decr_oper_payable", "incr_oper_payable",
    "others", "im_net_cashflow_oper_act", "conv_debt_into_cap", "conv_copbonds_due_within_1y",
    "fa_fnc_leases", "im_n_incr_cash_equ", "net_dism_capital_add", "net_cash_rece_sec",
    "credit_impa_loss", "use_right_asset_dep", "oth_loss_asset", "end_bal_cash", "beg_bal_cash",
    "end_bal_cash_equ", "beg_bal_cash_equ", "update_flag"
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
            # 调用Tushare现金流量表接口
            data = pro.cashflow(**{
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
                    INSERT IGNORE INTO stock_cash_flow ({columns})
                    VALUES ({placeholders})
                    '''
                    
                    # 准备数据值，处理NaN值
                    values = []
                    for field in fields:
                        value = row[field] if pd.notna(row[field]) else None
                        values.append(value)
                    
                    cursor.execute(insert_sql, values)
                
                success_count += 1
                print(f"成功处理股票 {ts_code}，获取到 {len(data)} 条现金流量表记录")
            else:
                print(f"股票 {ts_code} 没有现金流量表数据")
                
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