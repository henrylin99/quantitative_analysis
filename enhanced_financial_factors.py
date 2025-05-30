#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
增强版财务因子计算工具
基于利润表、资产负债表、现金流量表的完整字段，计算全面的财务因子
"""

import pymysql
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import warnings
warnings.filterwarnings('ignore')

class EnhancedFinancialFactors:
    """增强版财务因子计算器"""
    
    def __init__(self, host='localhost', user='root', password='root', 
                 database='stock_cursor', charset='utf8mb4'):
        """初始化数据库连接"""
        self.host = host
        self.user = user
        self.password = password
        self.database = database
        self.charset = charset
        self.connection = None
        self.connect()
        
    def connect(self):
        """建立数据库连接"""
        try:
            self.connection = pymysql.connect(
                host=self.host,
                user=self.user,
                password=self.password,
                database=self.database,
                charset=self.charset,
                cursorclass=pymysql.cursors.DictCursor
            )
            print(f"✅ 成功连接到数据库: {self.database}")
            return True
        except Exception as e:
            print(f"❌ 数据库连接失败: {e}")
            return False
    
    def close(self):
        """关闭数据库连接"""
        if self.connection:
            self.connection.close()
            print("🔒 数据库连接已关闭")
    
    def get_comprehensive_financial_data(self, ts_code=None, start_date=None, end_date=None):
        """获取综合财务数据"""
        print("\n💰 获取综合财务数据...")
        
        where_conditions = []
        if ts_code:
            where_conditions.append(f"i.ts_code = '{ts_code}'")
        if start_date:
            where_conditions.append(f"i.end_date >= '{start_date}'")
        if end_date:
            where_conditions.append(f"i.end_date <= '{end_date}'")
            
        where_clause = " AND ".join(where_conditions) if where_conditions else "1=1"
        
        query = f"""
        SELECT 
            -- 基本信息
            i.ts_code,
            i.end_date,
            i.ann_date,
            i.f_ann_date,
            i.report_type,
            
            -- 利润表完整数据
            i.total_revenue,
            i.revenue,
            i.int_income,
            i.prem_earned,
            i.comm_income,
            i.n_commis_income,
            i.n_oth_income,
            i.n_oth_b_income,
            i.prem_income,
            i.out_prem,
            i.une_prem_reser,
            i.reins_income,
            i.n_sec_tb_income,
            i.n_sec_uw_income,
            i.n_asset_mg_income,
            i.oth_b_income,
            i.fv_value_chg_gain,
            i.invest_income,
            i.ass_invest_income,
            i.forex_gain,
            i.total_cogs,
            i.oper_cost,
            i.int_exp,
            i.comm_exp,
            i.biz_tax_surchg,
            i.sell_exp,
            i.admin_exp,
            i.fin_exp,
            i.assets_impair_loss,
            i.prem_refund,
            i.compens_payout,
            i.reser_insur_liab,
            i.div_payt,
            i.reins_exp,
            i.oper_exp,
            i.compens_payout_refu,
            i.insur_reser_refu,
            i.reins_cost_refund,
            i.other_bus_cost,
            i.operate_profit,
            i.non_oper_income,
            i.non_oper_exp,
            i.nca_disploss,
            i.total_profit,
            i.income_tax,
            i.n_income,
            i.n_income_attr_p,
            i.minority_gain,
            i.oth_compr_income,
            i.t_compr_income,
            i.compr_inc_attr_p,
            i.compr_inc_attr_m_s,
            i.ebit,
            i.ebitda,
            i.insurance_exp,
            i.undist_profit,
            i.distable_profit,
            i.rd_exp,
            i.fin_exp_int_exp,
            i.fin_exp_int_inc,
            i.basic_eps,
            i.diluted_eps,
            i.continued_net_profit,
            
            -- 资产负债表完整数据
            b.total_share,
            b.cap_rese,
            b.undistr_porfit,
            b.surplus_rese,
            b.special_rese,
            b.money_cap,
            b.trad_asset,
            b.notes_receiv,
            b.accounts_receiv,
            b.oth_receiv,
            b.prepayment,
            b.div_receiv,
            b.int_receiv,
            b.inventories,
            b.amor_exp,
            b.nca_within_1y,
            b.sett_rsrv,
            b.loanto_oth_bank_fi,
            b.premium_receiv,
            b.reinsur_receiv,
            b.reinsur_res_receiv,
            b.pur_resale_fa,
            b.oth_cur_assets,
            b.total_cur_assets,
            b.fa_avail_for_sale,
            b.htm_invest,
            b.lt_eqt_invest,
            b.invest_real_estate,
            b.time_deposits,
            b.oth_assets,
            b.lt_rec,
            b.fix_assets,
            b.cip,
            b.const_materials,
            b.fixed_assets_disp,
            b.produc_bio_assets,
            b.oil_and_gas_assets,
            b.intan_assets,
            b.r_and_d,
            b.goodwill,
            b.lt_amor_exp,
            b.defer_tax_assets,
            b.decr_in_disbur,
            b.oth_nca,
            b.total_nca,
            b.cash_reser_cb,
            b.depos_in_oth_bfi,
            b.prec_metals,
            b.deriv_assets,
            b.rr_reins_une_prem,
            b.rr_reins_outstd_cla,
            b.rr_reins_lins_liab,
            b.rr_reins_lthins_liab,
            b.refund_depos,
            b.ph_pledge_loans,
            b.refund_cap_depos,
            b.indep_acct_assets,
            b.client_depos,
            b.client_prov,
            b.transac_seat_fee,
            b.invest_as_receiv,
            b.total_assets,
            b.lt_borr,
            b.st_borr,
            b.cb_borr,
            b.depos_ib_deposits,
            b.loan_oth_bank,
            b.trading_fl,
            b.notes_payable,
            b.acct_payable,
            b.adv_receipts,
            b.sold_for_repur_fa,
            b.comm_payable,
            b.payroll_payable,
            b.taxes_payable,
            b.int_payable,
            b.div_payable,
            b.oth_payable,
            b.acc_exp,
            b.deferred_inc,
            b.st_bonds_payable,
            b.payable_to_reinsurer,
            b.rsrv_insur_cont,
            b.acting_trading_sec,
            b.acting_uw_sec,
            b.non_cur_liab_due_1y,
            b.oth_cur_liab,
            b.total_cur_liab,
            b.bond_payable,
            b.lt_payable,
            b.specific_payables,
            b.estimated_liab,
            b.defer_tax_liab,
            b.defer_inc_non_cur_liab,
            b.oth_ncl,
            b.total_ncl,
            b.depos_oth_bfi,
            b.deriv_liab,
            b.depos,
            b.agency_bus_liab,
            b.oth_liab,
            b.prem_receiv_adva,
            b.depos_received,
            b.ph_invest,
            b.reser_une_prem,
            b.reser_outstd_claims,
            b.reser_lins_liab,
            b.reser_lthins_liab,
            b.indept_acc_liab,
            b.pledge_borr,
            b.indem_payable,
            b.policy_div_payable,
            b.total_liab,
            b.treasury_share,
            b.ordin_risk_reser,
            b.forex_differ,
            b.invest_loss_unconf,
            b.minority_int,
            b.total_hldr_eqy_exc_min_int,
            b.total_hldr_eqy_inc_min_int,
            b.total_liab_hldr_eqy,
            b.lt_payroll_payable,
            b.oth_comp_income,
            b.oth_eqt_tools,
            b.oth_eqt_tools_p_shr,
            b.lending_funds,
            b.acc_receivable,
            b.st_fin_payable,
            b.payables,
            b.hfs_assets,
            b.hfs_sales,
            b.cost_fin_assets,
            b.fair_value_fin_assets,
            b.contract_assets,
            b.contract_liab,
            b.accounts_receiv_bill,
            b.accounts_pay,
            b.oth_rcv_total,
            b.fix_assets_total,
            b.cip_total,
            b.oth_pay_total,
            b.long_pay_total,
            b.debt_invest,
            b.oth_debt_invest,
            
            -- 现金流量表完整数据
            c.net_profit,
            c.finan_exp,
            c.c_fr_sale_sg,
            c.recp_tax_rends,
            c.n_depos_incr_fi,
            c.n_incr_loans_cb,
            c.n_inc_borr_oth_fi,
            c.prem_fr_orig_contr,
            c.n_incr_insured_dep,
            c.n_reinsur_prem,
            c.n_incr_disp_tfa,
            c.ifc_cash_incr,
            c.n_incr_disp_faas,
            c.n_incr_loans_oth_bank,
            c.n_cap_incr_repur,
            c.c_fr_oth_operate_a,
            c.c_inf_fr_operate_a,
            c.c_paid_goods_s,
            c.c_paid_to_for_empl,
            c.c_paid_for_taxes,
            c.n_incr_clt_loan_adv,
            c.n_incr_dep_cbob,
            c.c_pay_claims_orig_inco,
            c.pay_handling_chrg,
            c.pay_comm_insur_plcy,
            c.oth_cash_pay_oper_act,
            c.st_cash_out_act,
            c.n_cashflow_act,
            c.oth_recp_ral_inv_act,
            c.c_disp_withdrwl_invest,
            c.c_recp_return_invest,
            c.n_recp_disp_fiolta,
            c.n_recp_disp_sobu,
            c.stot_inflows_inv_act,
            c.c_pay_acq_const_fiolta,
            c.c_paid_invest,
            c.n_disp_subs_oth_biz,
            c.oth_pay_ral_inv_act,
            c.n_incr_pledge_loan,
            c.stot_out_inv_act,
            c.n_cashflow_inv_act,
            c.c_recp_borrow,
            c.proc_issue_bonds,
            c.oth_cash_recp_ral_fnc_act,
            c.stot_cash_in_fnc_act,
            c.free_cashflow,
            c.c_prepay_amt_borr,
            c.c_pay_dist_dpcp_int_exp,
            c.incl_dvd_profit_paid_sc_ms,
            c.oth_cashpay_ral_fnc_act,
            c.stot_cashout_fnc_act,
            c.n_cash_flows_fnc_act,
            c.eff_fx_flu_cash,
            c.n_incr_cash_cash_equ,
            c.c_cash_equ_beg_period,
            c.c_cash_equ_end_period,
            c.c_recp_cap_contrib,
            c.incl_cash_rec_saims,
            c.uncon_invest_loss,
            c.prov_depr_assets,
            c.depr_fa_coga_dpba,
            c.amort_intang_assets,
            c.lt_amort_deferred_exp,
            c.decr_deferred_exp,
            c.incr_acc_exp,
            c.loss_disp_fiolta,
            c.loss_scr_fa,
            c.loss_fv_chg,
            c.invest_loss,
            c.decr_def_inc_tax_assets,
            c.incr_def_inc_tax_liab,
            c.decr_inventories,
            c.decr_oper_payable,
            c.incr_oper_payable,
            c.others,
            c.im_net_cashflow_oper_act,
            c.conv_debt_into_cap,
            c.conv_copbonds_due_within_1y,
            c.fa_fnc_leases,
            c.im_n_incr_cash_equ,
            c.net_dism_capital_add,
            c.net_cash_rece_sec,
            c.credit_impa_loss,
            c.use_right_asset_dep,
            c.oth_loss_asset,
            c.end_bal_cash,
            c.beg_bal_cash,
            c.end_bal_cash_equ,
            c.beg_bal_cash_equ
            
        FROM stock_income_statement i
        LEFT JOIN stock_balance_sheet b ON i.ts_code = b.ts_code AND i.end_date = b.end_date
        LEFT JOIN stock_cash_flow c ON i.ts_code = c.ts_code AND i.end_date = c.end_date
        WHERE {where_clause}
        ORDER BY i.ts_code, i.end_date
        """
        
        try:
            df = pd.read_sql(query, self.connection)
            
            # 转换数值列的数据类型
            numeric_columns = [
                # 利润表数值字段
                'total_revenue', 'revenue', 'int_income', 'prem_earned', 'comm_income',
                'n_commis_income', 'n_oth_income', 'n_oth_b_income', 'prem_income',
                'out_prem', 'une_prem_reser', 'reins_income', 'n_sec_tb_income',
                'n_sec_uw_income', 'n_asset_mg_income', 'oth_b_income', 'fv_value_chg_gain',
                'invest_income', 'ass_invest_income', 'forex_gain', 'total_cogs',
                'oper_cost', 'int_exp', 'comm_exp', 'biz_tax_surchg', 'sell_exp',
                'admin_exp', 'fin_exp', 'assets_impair_loss', 'prem_refund',
                'compens_payout', 'reser_insur_liab', 'div_payt', 'reins_exp',
                'oper_exp', 'compens_payout_refu', 'insur_reser_refu', 'reins_cost_refund',
                'other_bus_cost', 'operate_profit', 'non_oper_income', 'non_oper_exp',
                'nca_disploss', 'total_profit', 'income_tax', 'n_income', 'n_income_attr_p',
                'minority_gain', 'oth_compr_income', 't_compr_income', 'compr_inc_attr_p',
                'compr_inc_attr_m_s', 'ebit', 'ebitda', 'insurance_exp', 'undist_profit',
                'distable_profit', 'rd_exp', 'fin_exp_int_exp', 'fin_exp_int_inc',
                'basic_eps', 'diluted_eps', 'continued_net_profit',
                
                # 资产负债表数值字段
                'total_share', 'cap_rese', 'undistr_porfit', 'surplus_rese', 'special_rese',
                'money_cap', 'trad_asset', 'notes_receiv', 'accounts_receiv', 'oth_receiv',
                'prepayment', 'div_receiv', 'int_receiv', 'inventories', 'amor_exp',
                'nca_within_1y', 'sett_rsrv', 'loanto_oth_bank_fi', 'premium_receiv',
                'reinsur_receiv', 'reinsur_res_receiv', 'pur_resale_fa', 'oth_cur_assets',
                'total_cur_assets', 'fa_avail_for_sale', 'htm_invest', 'lt_eqt_invest',
                'invest_real_estate', 'time_deposits', 'oth_assets', 'lt_rec', 'fix_assets',
                'cip', 'const_materials', 'fixed_assets_disp', 'produc_bio_assets',
                'oil_and_gas_assets', 'intan_assets', 'r_and_d', 'goodwill', 'lt_amor_exp',
                'defer_tax_assets', 'decr_in_disbur', 'oth_nca', 'total_nca',
                'cash_reser_cb', 'depos_in_oth_bfi', 'prec_metals', 'deriv_assets',
                'rr_reins_une_prem', 'rr_reins_outstd_cla', 'rr_reins_lins_liab',
                'rr_reins_lthins_liab', 'refund_depos', 'ph_pledge_loans', 'refund_cap_depos',
                'indep_acct_assets', 'client_depos', 'client_prov', 'transac_seat_fee',
                'invest_as_receiv', 'total_assets', 'lt_borr', 'st_borr', 'cb_borr',
                'depos_ib_deposits', 'loan_oth_bank', 'trading_fl', 'notes_payable',
                'acct_payable', 'adv_receipts', 'sold_for_repur_fa', 'comm_payable',
                'payroll_payable', 'taxes_payable', 'int_payable', 'div_payable',
                'oth_payable', 'acc_exp', 'deferred_inc', 'st_bonds_payable',
                'payable_to_reinsurer', 'rsrv_insur_cont', 'acting_trading_sec',
                'acting_uw_sec', 'non_cur_liab_due_1y', 'oth_cur_liab', 'total_cur_liab',
                'bond_payable', 'lt_payable', 'specific_payables', 'estimated_liab',
                'defer_tax_liab', 'defer_inc_non_cur_liab', 'oth_ncl', 'total_ncl',
                'depos_oth_bfi', 'deriv_liab', 'depos', 'agency_bus_liab', 'oth_liab',
                'prem_receiv_adva', 'depos_received', 'ph_invest', 'reser_une_prem',
                'reser_outstd_claims', 'reser_lins_liab', 'reser_lthins_liab',
                'indept_acc_liab', 'pledge_borr', 'indem_payable', 'policy_div_payable',
                'total_liab', 'treasury_share', 'ordin_risk_reser', 'forex_differ',
                'invest_loss_unconf', 'minority_int', 'total_hldr_eqy_exc_min_int',
                'total_hldr_eqy_inc_min_int', 'total_liab_hldr_eqy', 'lt_payroll_payable',
                'oth_comp_income', 'oth_eqt_tools', 'oth_eqt_tools_p_shr', 'lending_funds',
                'acc_receivable', 'st_fin_payable', 'payables', 'hfs_assets', 'hfs_sales',
                'cost_fin_assets', 'fair_value_fin_assets', 'contract_assets', 'contract_liab',
                'accounts_receiv_bill', 'accounts_pay', 'oth_rcv_total', 'fix_assets_total',
                'cip_total', 'oth_pay_total', 'long_pay_total', 'debt_invest', 'oth_debt_invest',
                
                # 现金流量表数值字段
                'net_profit', 'finan_exp', 'c_fr_sale_sg', 'recp_tax_rends', 'n_depos_incr_fi',
                'n_incr_loans_cb', 'n_inc_borr_oth_fi', 'prem_fr_orig_contr', 'n_incr_insured_dep',
                'n_reinsur_prem', 'n_incr_disp_tfa', 'ifc_cash_incr', 'n_incr_disp_faas',
                'n_incr_loans_oth_bank', 'n_cap_incr_repur', 'c_fr_oth_operate_a',
                'c_inf_fr_operate_a', 'c_paid_goods_s', 'c_paid_to_for_empl', 'c_paid_for_taxes',
                'n_incr_clt_loan_adv', 'n_incr_dep_cbob', 'c_pay_claims_orig_inco',
                'pay_handling_chrg', 'pay_comm_insur_plcy', 'oth_cash_pay_oper_act',
                'st_cash_out_act', 'n_cashflow_act', 'oth_recp_ral_inv_act',
                'c_disp_withdrwl_invest', 'c_recp_return_invest', 'n_recp_disp_fiolta',
                'n_recp_disp_sobu', 'stot_inflows_inv_act', 'c_pay_acq_const_fiolta',
                'c_paid_invest', 'n_disp_subs_oth_biz', 'oth_pay_ral_inv_act',
                'n_incr_pledge_loan', 'stot_out_inv_act', 'n_cashflow_inv_act',
                'c_recp_borrow', 'proc_issue_bonds', 'oth_cash_recp_ral_fnc_act',
                'stot_cash_in_fnc_act', 'free_cashflow', 'c_prepay_amt_borr',
                'c_pay_dist_dpcp_int_exp', 'incl_dvd_profit_paid_sc_ms', 'oth_cashpay_ral_fnc_act',
                'stot_cashout_fnc_act', 'n_cash_flows_fnc_act', 'eff_fx_flu_cash',
                'n_incr_cash_cash_equ', 'c_cash_equ_beg_period', 'c_cash_equ_end_period',
                'c_recp_cap_contrib', 'incl_cash_rec_saims', 'uncon_invest_loss',
                'prov_depr_assets', 'depr_fa_coga_dpba', 'amort_intang_assets',
                'lt_amort_deferred_exp', 'decr_deferred_exp', 'incr_acc_exp',
                'loss_disp_fiolta', 'loss_scr_fa', 'loss_fv_chg', 'invest_loss',
                'decr_def_inc_tax_assets', 'incr_def_inc_tax_liab', 'decr_inventories',
                'decr_oper_payable', 'incr_oper_payable', 'others', 'im_net_cashflow_oper_act',
                'conv_debt_into_cap', 'conv_copbonds_due_within_1y', 'fa_fnc_leases',
                'im_n_incr_cash_equ', 'net_dism_capital_add', 'net_cash_rece_sec',
                'credit_impa_loss', 'use_right_asset_dep', 'oth_loss_asset',
                'end_bal_cash', 'beg_bal_cash', 'end_bal_cash_equ', 'beg_bal_cash_equ'
            ]
            
            # 转换数值列，处理空值和非数值
            for col in numeric_columns:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce')
            
            # 填充空值为0（或根据业务需求调整）
            df[numeric_columns] = df[numeric_columns].fillna(0)
            
            print(f"✅ 成功获取 {len(df)} 条综合财务数据")
            print(f"🔄 已转换 {len([col for col in numeric_columns if col in df.columns])} 个数值字段的数据类型")
            return df
        except Exception as e:
            print(f"❌ 获取综合财务数据失败: {e}")
            return None

    def safe_divide(self, numerator, denominator, default=0):
        """安全除法，避免除零错误"""
        return np.where(denominator != 0, numerator / denominator, default)
    
    def calculate_profitability_factors(self, financial_data):
        """计算盈利能力因子"""
        print("\n💎 计算盈利能力因子...")
        
        df = financial_data.copy()
        
        try:
            # 基础盈利指标
            df['gross_profit_margin'] = self.safe_divide(df['revenue'] - df['oper_cost'], df['revenue']) * 100  # 毛利率
            df['operating_profit_margin'] = self.safe_divide(df['operate_profit'], df['revenue']) * 100  # 营业利润率
            df['net_profit_margin'] = self.safe_divide(df['n_income_attr_p'], df['revenue']) * 100  # 净利润率
            df['ebit_margin'] = self.safe_divide(df['ebit'], df['revenue']) * 100  # EBIT利润率
            df['ebitda_margin'] = self.safe_divide(df['ebitda'], df['revenue']) * 100  # EBITDA利润率
            
            # 费用控制能力
            df['expense_ratio'] = self.safe_divide(df['sell_exp'] + df['admin_exp'], df['revenue']) * 100  # 期间费用率
            df['selling_expense_ratio'] = self.safe_divide(df['sell_exp'], df['revenue']) * 100  # 销售费用率
            df['admin_expense_ratio'] = self.safe_divide(df['admin_exp'], df['revenue']) * 100  # 管理费用率
            df['rd_expense_ratio'] = self.safe_divide(df['rd_exp'], df['revenue']) * 100  # 研发费用率
            df['finance_expense_ratio'] = self.safe_divide(df['fin_exp'], df['revenue']) * 100  # 财务费用率
            
            # 投资收益能力
            df['investment_income_ratio'] = self.safe_divide(df['invest_income'], df['revenue']) * 100  # 投资收益率
            df['fair_value_gain_ratio'] = self.safe_divide(df['fv_value_chg_gain'], df['revenue']) * 100  # 公允价值变动收益率
            df['non_operating_income_ratio'] = self.safe_divide(df['non_oper_income'], df['revenue']) * 100  # 营业外收入比例
            
            # 税收效率
            df['effective_tax_rate'] = self.safe_divide(df['income_tax'], df['total_profit']) * 100  # 实际税率
            df['tax_burden'] = self.safe_divide(df['income_tax'], df['revenue']) * 100  # 税收负担率
            
            # 股东回报
            df['earnings_per_share'] = df['basic_eps']  # 基本每股收益
            df['diluted_earnings_per_share'] = df['diluted_eps']  # 稀释每股收益
            
            # 盈利质量
            df['core_profit_ratio'] = self.safe_divide(df['operate_profit'], df['n_income_attr_p'])  # 核心利润比例
            df['minority_profit_ratio'] = self.safe_divide(df['minority_gain'], df['n_income']) * 100  # 少数股东损益比例
            
            print(f"✅ 成功计算 {len(df)} 条盈利能力因子")
            return df
            
        except Exception as e:
            print(f"❌ 计算盈利能力因子失败: {e}")
            return df

    def calculate_solvency_factors(self, financial_data):
        """计算偿债能力因子"""
        print("\n🏦 计算偿债能力因子...")
        
        df = financial_data.copy()
        
        try:
            # 短期偿债能力
            df['current_ratio'] = self.safe_divide(df['total_cur_assets'], df['total_cur_liab'])  # 流动比率
            df['quick_ratio'] = self.safe_divide(df['total_cur_assets'] - df['inventories'], df['total_cur_liab'])  # 速动比率
            df['cash_ratio'] = self.safe_divide(df['money_cap'], df['total_cur_liab'])  # 现金比率
            df['super_quick_ratio'] = self.safe_divide(df['money_cap'] + df['trad_asset'], df['total_cur_liab'])  # 超速动比率
            
            # 长期偿债能力
            df['debt_to_equity'] = self.safe_divide(df['total_liab'], df['total_hldr_eqy_inc_min_int'])  # 资产负债率
            df['debt_to_assets'] = self.safe_divide(df['total_liab'], df['total_assets'])  # 负债总资产比
            df['equity_ratio'] = self.safe_divide(df['total_hldr_eqy_inc_min_int'], df['total_assets'])  # 股东权益比率
            df['long_debt_to_equity'] = self.safe_divide(df['lt_borr'] + df['bond_payable'], df['total_hldr_eqy_inc_min_int'])  # 长期负债权益比
            
            # 债务结构
            df['short_debt_ratio'] = self.safe_divide(df['st_borr'], df['total_liab'])  # 短期债务比例
            df['long_debt_ratio'] = self.safe_divide(df['lt_borr'], df['total_liab'])  # 长期债务比例
            df['interest_bearing_debt'] = df['st_borr'] + df['lt_borr']  # 有息债务
            df['interest_bearing_debt_ratio'] = self.safe_divide(df['interest_bearing_debt'], df['total_assets'])  # 有息债务比率
            
            # 利息保障能力
            df['interest_coverage'] = self.safe_divide(df['ebit'], df['fin_exp_int_exp']) # 利息保障倍数
            df['ebitda_interest_coverage'] = self.safe_divide(df['ebitda'], df['fin_exp_int_exp'])  # EBITDA利息保障倍数
            df['cashflow_interest_coverage'] = self.safe_divide(df['n_cashflow_act'], df['fin_exp_int_exp'])  # 现金流利息保障倍数
            
            # 或有负债风险
            df['contingent_liability_ratio'] = self.safe_divide(df['notes_payable'] + df['st_bonds_payable'], df['total_liab'])  # 或有负债比例
            df['financial_leverage'] = self.safe_divide(df['total_assets'], df['total_hldr_eqy_inc_min_int'])  # 财务杠杆
            
            print(f"✅ 成功计算 {len(df)} 条偿债能力因子")
            return df
            
        except Exception as e:
            print(f"❌ 计算偿债能力因子失败: {e}")
            return df

    def calculate_operational_efficiency_factors(self, financial_data):
        """计算营运能力因子"""
        print("\n⚡ 计算营运能力因子...")
        
        df = financial_data.copy()
        
        try:
            # 资产周转能力
            df['total_asset_turnover'] = self.safe_divide(df['revenue'], df['total_assets'])  # 总资产周转率
            df['fixed_asset_turnover'] = self.safe_divide(df['revenue'], df['fix_assets'])  # 固定资产周转率
            df['current_asset_turnover'] = self.safe_divide(df['revenue'], df['total_cur_assets'])  # 流动资产周转率
            df['working_capital_turnover'] = self.safe_divide(df['revenue'], df['total_cur_assets'] - df['total_cur_liab'])  # 营运资本周转率
            
            # 应收账款管理
            df['receivables_turnover'] = self.safe_divide(df['revenue'], df['accounts_receiv'])  # 应收账款周转率
            df['receivables_days'] = self.safe_divide(365, df['receivables_turnover'])  # 应收账款周转天数
            df['receivables_ratio'] = self.safe_divide(df['accounts_receiv'], df['revenue']) * 100  # 应收账款占收入比
            df['bad_debt_ratio'] = self.safe_divide(df['assets_impair_loss'], df['accounts_receiv']) * 100  # 坏账比例
            
            # 存货管理
            df['inventory_turnover'] = self.safe_divide(df['oper_cost'], df['inventories'])  # 存货周转率
            df['inventory_days'] = self.safe_divide(365, df['inventory_turnover'])  # 存货周转天数
            df['inventory_ratio'] = self.safe_divide(df['inventories'], df['total_cur_assets']) * 100  # 存货占流动资产比
            
            # 应付账款管理
            df['payables_turnover'] = self.safe_divide(df['oper_cost'], df['acct_payable'])  # 应付账款周转率
            df['payables_days'] = self.safe_divide(365, df['payables_turnover'])  # 应付账款周转天数
            df['payables_ratio'] = self.safe_divide(df['acct_payable'], df['oper_cost']) * 100  # 应付账款占成本比
            
            # 现金转换周期
            df['cash_conversion_cycle'] = df['receivables_days'] + df['inventory_days'] - df['payables_days']  # 现金转换周期
            
            # 无形资产管理
            df['intangible_asset_ratio'] = self.safe_divide(df['intan_assets'], df['total_assets']) * 100  # 无形资产比例
            df['goodwill_ratio'] = self.safe_divide(df['goodwill'], df['total_assets']) * 100  # 商誉比例
            df['rd_asset_ratio'] = self.safe_divide(df['r_and_d'], df['total_assets']) * 100  # 研发资产比例
            
            # 资本密集度
            df['capital_intensity'] = self.safe_divide(df['fix_assets'], df['revenue'])  # 资本密集度
            df['asset_intensity'] = self.safe_divide(df['total_assets'], df['revenue'])  # 资产密集度
            
            print(f"✅ 成功计算 {len(df)} 条营运能力因子")
            return df
            
        except Exception as e:
            print(f"❌ 计算营运能力因子失败: {e}")
            return df

    def calculate_cashflow_factors(self, financial_data):
        """计算现金流因子"""
        print("\n💰 计算现金流因子...")
        
        df = financial_data.copy()
        
        try:
            # 现金流基本比率
            df['operating_cashflow_ratio'] = self.safe_divide(df['n_cashflow_act'], df['revenue']) * 100  # 经营现金流比率
            df['free_cashflow_ratio'] = self.safe_divide(df['free_cashflow'], df['revenue']) * 100  # 自由现金流比率
            df['cashflow_coverage_ratio'] = self.safe_divide(df['n_cashflow_act'], df['total_cur_liab'])  # 现金流量覆盖比率
            
            # 现金流质量
            df['operating_cf_to_net_income'] = self.safe_divide(df['n_cashflow_act'], df['n_income_attr_p'])  # 经营现金流与净利润比
            df['free_cf_to_net_income'] = self.safe_divide(df['free_cashflow'], df['n_income_attr_p'])  # 自由现金流与净利润比
            df['accruals_ratio'] = self.safe_divide(df['n_income_attr_p'] - df['n_cashflow_act'], df['total_assets']) * 100  # 应计项目比率
            
            # 现金管理能力
            df['cash_to_assets'] = self.safe_divide(df['money_cap'], df['total_assets']) * 100  # 现金资产比
            df['cash_to_current_liab'] = self.safe_divide(df['money_cap'], df['total_cur_liab'])  # 现金流动负债比
            df['cash_growth_rate'] = self.safe_divide(df['c_cash_equ_end_period'] - df['c_cash_equ_beg_period'], df['c_cash_equ_beg_period']) * 100  # 现金增长率
            
            # 投资现金流分析
            df['capex_ratio'] = self.safe_divide(df['c_pay_acq_const_fiolta'], df['revenue']) * 100  # 资本支出比率
            df['capex_to_operating_cf'] = self.safe_divide(df['c_pay_acq_const_fiolta'], df['n_cashflow_act'])  # 资本支出与经营现金流比
            df['investment_intensity'] = self.safe_divide(df['c_paid_invest'], df['total_assets']) * 100  # 投资强度
            
            # 筹资现金流分析
            df['debt_financing_ratio'] = self.safe_divide(df['c_recp_borrow'], df['stot_cash_in_fnc_act']) * 100  # 债务筹资比例
            df['equity_financing_ratio'] = self.safe_divide(df['c_recp_cap_contrib'], df['stot_cash_in_fnc_act']) * 100  # 股权筹资比例
            df['dividend_payout_ratio'] = self.safe_divide(df['c_pay_dist_dpcp_int_exp'], df['n_income_attr_p']) * 100  # 股利支付率
            
            # 现金流稳定性
            df['operating_cf_variability'] = df.groupby('ts_code')['n_cashflow_act'].rolling(4).std().reset_index(0, drop=True)  # 经营现金流变异性
            df['free_cf_variability'] = df.groupby('ts_code')['free_cashflow'].rolling(4).std().reset_index(0, drop=True)  # 自由现金流变异性
            
            # 现金流预测能力
            df['cf_prediction_ability'] = self.safe_divide(df['n_cashflow_act'], df.groupby('ts_code')['n_cashflow_act'].shift(1))  # 现金流预测能力
            
            # 营运资本变化
            df['working_capital_change'] = (df['total_cur_assets'] - df['total_cur_liab']) - df.groupby('ts_code')['total_cur_assets'].shift(1) + df.groupby('ts_code')['total_cur_liab'].shift(1)
            df['working_capital_change_ratio'] = self.safe_divide(df['working_capital_change'], df['revenue']) * 100  # 营运资本变化率
            
            print(f"✅ 成功计算 {len(df)} 条现金流因子")
            return df
            
        except Exception as e:
            print(f"❌ 计算现金流因子失败: {e}")
            return df

    def calculate_growth_factors(self, financial_data):
        """计算成长能力因子"""
        print("\n📈 计算成长能力因子...")
        
        df = financial_data.copy()
        df = df.sort_values(['ts_code', 'end_date'])
        
        try:
            # 收入增长
            df['revenue_growth_yoy'] = df.groupby('ts_code')['revenue'].pct_change(4) * 100  # 同比收入增长率
            df['revenue_growth_qoq'] = df.groupby('ts_code')['revenue'].pct_change(1) * 100  # 环比收入增长率
            df['revenue_cagr_3y'] = (df.groupby('ts_code')['revenue'].transform(lambda x: (x / x.shift(12)) ** (1/3) - 1)) * 100  # 3年收入复合增长率
            
            # 利润增长
            df['net_profit_growth_yoy'] = df.groupby('ts_code')['n_income_attr_p'].pct_change(4) * 100  # 同比净利润增长率
            df['operating_profit_growth_yoy'] = df.groupby('ts_code')['operate_profit'].pct_change(4) * 100  # 同比营业利润增长率
            df['ebit_growth_yoy'] = df.groupby('ts_code')['ebit'].pct_change(4) * 100  # 同比EBIT增长率
            df['ebitda_growth_yoy'] = df.groupby('ts_code')['ebitda'].pct_change(4) * 100  # 同比EBITDA增长率
            
            # 资产增长
            df['total_assets_growth_yoy'] = df.groupby('ts_code')['total_assets'].pct_change(4) * 100  # 同比总资产增长率
            df['fixed_assets_growth_yoy'] = df.groupby('ts_code')['fix_assets'].pct_change(4) * 100  # 同比固定资产增长率
            df['net_assets_growth_yoy'] = df.groupby('ts_code')['total_hldr_eqy_inc_min_int'].pct_change(4) * 100  # 同比净资产增长率
            
            # 每股指标增长
            df['eps_growth_yoy'] = df.groupby('ts_code')['basic_eps'].pct_change(4) * 100  # 同比每股收益增长率
            df['book_value_per_share_growth'] = df.groupby('ts_code')['total_hldr_eqy_inc_min_int'].pct_change(4) * 100  # 每股净资产增长率
            
            # 现金流增长
            df['operating_cf_growth_yoy'] = df.groupby('ts_code')['n_cashflow_act'].pct_change(4) * 100  # 同比经营现金流增长率
            df['free_cf_growth_yoy'] = df.groupby('ts_code')['free_cashflow'].pct_change(4) * 100  # 同比自由现金流增长率
            
            # 研发增长
            df['rd_growth_yoy'] = df.groupby('ts_code')['rd_exp'].pct_change(4) * 100  # 同比研发支出增长率
            
            # 研发强度变化 - 修复DataFrame赋值错误
            current_rd_intensity = self.safe_divide(df['rd_exp'], df['revenue'])
            previous_rd_intensity = self.safe_divide(df.groupby('ts_code')['rd_exp'].shift(4), df.groupby('ts_code')['revenue'].shift(4))
            df['rd_intensity_change'] = current_rd_intensity - previous_rd_intensity  # 研发强度变化
            
            # 成长质量
            df['sustainable_growth_rate'] = self.safe_divide(df['n_income_attr_p'], df['total_hldr_eqy_inc_min_int']) * (1 - 0.3)  # 可持续增长率（假设分红率30%）
            df['revenue_profit_growth_match'] = abs(df['revenue_growth_yoy'] - df['net_profit_growth_yoy'])  # 收入利润增长匹配度
            df['asset_profit_growth_match'] = abs(df['total_assets_growth_yoy'] - df['net_profit_growth_yoy'])  # 资产利润增长匹配度
            
            # 增长趋势
            df['revenue_growth_trend'] = df.groupby('ts_code')['revenue_growth_yoy'].rolling(4).apply(lambda x: np.polyfit(range(len(x)), x, 1)[0]).reset_index(0, drop=True)  # 收入增长趋势
            df['profit_growth_trend'] = df.groupby('ts_code')['net_profit_growth_yoy'].rolling(4).apply(lambda x: np.polyfit(range(len(x)), x, 1)[0]).reset_index(0, drop=True)  # 利润增长趋势
            
            # 增长稳定性
            df['revenue_growth_stability'] = df.groupby('ts_code')['revenue_growth_yoy'].rolling(8).std().reset_index(0, drop=True)  # 收入增长稳定性
            df['profit_growth_stability'] = df.groupby('ts_code')['net_profit_growth_yoy'].rolling(8).std().reset_index(0, drop=True)  # 利润增长稳定性
            
            print(f"✅ 成功计算 {len(df)} 条成长能力因子")
            return df
            
        except Exception as e:
            print(f"❌ 计算成长能力因子失败: {e}")
            return df

    def calculate_comprehensive_financial_factors(self, ts_code=None, start_date=None, end_date=None):
        """计算全面的财务因子"""
        print("\n🚀 计算全面的财务因子...")
        print("=" * 80)
        
        # 获取综合财务数据
        financial_data = self.get_comprehensive_financial_data(ts_code, start_date, end_date)
        
        if financial_data is None or financial_data.empty:
            print("❌ 未获取到财务数据")
            return None
        
        # 计算各类因子
        print("\n📊 开始计算各类财务因子...")
        
        # 盈利能力因子
        financial_data = self.calculate_profitability_factors(financial_data)
        
        # 偿债能力因子
        financial_data = self.calculate_solvency_factors(financial_data)
        
        # 营运能力因子
        financial_data = self.calculate_operational_efficiency_factors(financial_data)
        
        # 现金流因子
        financial_data = self.calculate_cashflow_factors(financial_data)
        
        # 成长能力因子
        financial_data = self.calculate_growth_factors(financial_data)
        
        print(f"\n✅ 全面财务因子计算完成！共计算 {len(financial_data)} 条记录")
        return financial_data

    def generate_financial_report(self, ts_code, start_date="2020-12-31", end_date="2023-12-31"):
        """生成财务因子报告"""
        print(f"\n📊 生成股票 {ts_code} 的财务因子报告")
        print(f"📅 时间范围: {start_date} 至 {end_date}")
        print("=" * 80)
        
        # 计算全面财务因子
        financial_factors = self.calculate_comprehensive_financial_factors(ts_code, start_date, end_date)
        
        if financial_factors is None or financial_factors.empty:
            print("❌ 未能生成财务因子数据")
            return None
        
        # 选择关键因子进行展示
        key_factors = [
            'ts_code', 'end_date',
            # 盈利能力
            'gross_profit_margin', 'operating_profit_margin', 'net_profit_margin',
            'expense_ratio', 'rd_expense_ratio',
            # 偿债能力
            'current_ratio', 'debt_to_equity', 'interest_coverage',
            # 营运能力
            'total_asset_turnover', 'receivables_turnover', 'inventory_turnover',
            'cash_conversion_cycle',
            # 现金流
            'operating_cashflow_ratio', 'free_cashflow_ratio', 'operating_cf_to_net_income',
            # 成长能力
            'revenue_growth_yoy', 'net_profit_growth_yoy', 'eps_growth_yoy'
        ]
        
        # 过滤存在的因子
        available_factors = [factor for factor in key_factors if factor in financial_factors.columns]
        
        report_data = financial_factors[available_factors].copy()
        
        print("\n📈 财务因子数据概览:")
        print(report_data.describe())
        
        print("\n📊 最新财务因子值:")
        if not report_data.empty:
            latest_data = report_data.sort_values('end_date').tail(1)
            for col in available_factors[2:]:  # 跳过ts_code和end_date
                if col in latest_data.columns:
                    value = latest_data[col].iloc[0] if not latest_data[col].isna().iloc[0] else 'N/A'
                    if isinstance(value, (int, float)) and value != 'N/A':
                        print(f"{col}: {value:.4f}")
                    else:
                        print(f"{col}: {value}")
        
        print("\n📋 因子说明:")
        factor_descriptions = {
            'gross_profit_margin': '毛利率 - 反映产品盈利能力',
            'operating_profit_margin': '营业利润率 - 反映主营业务盈利能力',
            'net_profit_margin': '净利润率 - 反映整体盈利能力',
            'current_ratio': '流动比率 - 反映短期偿债能力',
            'debt_to_equity': '资产负债率 - 反映财务杠杆水平',
            'total_asset_turnover': '总资产周转率 - 反映资产运营效率',
            'operating_cashflow_ratio': '经营现金流比率 - 反映现金创造能力',
            'revenue_growth_yoy': '收入同比增长率 - 反映业务成长能力'
        }
        
        for factor, desc in factor_descriptions.items():
            if factor in available_factors:
                print(f"  {factor}: {desc}")
        
        return financial_factors

def main():
    """主函数 - 演示增强版财务因子计算"""
    print("🚀 增强版财务因子计算工具")
    print("=" * 80)
    
    # 初始化财务因子计算器
    factor_calculator = EnhancedFinancialFactors()
    
    try:
        # 设置测试参数
        sample_stock = "000001.SZ"  # 平安银行
        start_date = "2020-12-31"
        end_date = "2023-12-31"
        
        print(f"📊 分析股票: {sample_stock}")
        print(f"📅 时间范围: {start_date} 至 {end_date}")
        
        # 生成财务因子报告
        financial_report = factor_calculator.generate_financial_report(sample_stock, start_date, end_date)
        
        if financial_report is not None:
            print("\n✅ 财务因子计算完成!")
            print("\n💡 使用建议:")
            print("1. 盈利能力因子用于评估公司盈利质量")
            print("2. 偿债能力因子用于评估财务风险")
            print("3. 营运能力因子用于评估管理效率")
            print("4. 现金流因子用于评估现金创造能力")
            print("5. 成长能力因子用于评估发展潜力")
            print("6. 综合分析多个维度的因子可以全面评估公司财务状况")
        
    except Exception as e:
        print(f"❌ 程序执行出错: {e}")
        
    finally:
        factor_calculator.close()

if __name__ == "__main__":
    main() 