from app.extensions import db
from sqlalchemy import Column, String, DECIMAL

class StockIncomeStatement(db.Model):
    """利润表数据表"""
    __tablename__ = 'stock_income_statement'
    
    ts_code = Column(String(20), primary_key=True, comment='TS股票代码')
    end_date = Column(String(8), primary_key=True, comment='报告期')
    ann_date = Column(String(8), comment='公告日期')
    f_ann_date = Column(String(8), comment='实际公告日期')
    report_type = Column(String(10), comment='报告类型')
    comp_type = Column(String(10), comment='公司类型')
    end_type = Column(String(10), comment='报告期类型')
    basic_eps = Column(DECIMAL(10, 4), comment='基本每股收益')
    diluted_eps = Column(DECIMAL(10, 4), comment='稀释每股收益')
    total_revenue = Column(DECIMAL(20, 4), comment='营业总收入')
    revenue = Column(DECIMAL(20, 4), comment='营业收入')
    int_income = Column(DECIMAL(20, 4), comment='利息收入')
    prem_earned = Column(DECIMAL(20, 4), comment='已赚保费')
    comm_income = Column(DECIMAL(20, 4), comment='手续费及佣金收入')
    n_commis_income = Column(DECIMAL(20, 4), comment='手续费及佣金净收入')
    n_oth_income = Column(DECIMAL(20, 4), comment='其他经营净收益')
    n_oth_b_income = Column(DECIMAL(20, 4), comment='加:其他业务净收益')
    prem_income = Column(DECIMAL(20, 4), comment='保险业务收入')
    out_prem = Column(DECIMAL(20, 4), comment='减:分出保费')
    une_prem_reser = Column(DECIMAL(20, 4), comment='提取未到期责任准备金')
    reins_income = Column(DECIMAL(20, 4), comment='其中:分保费收入')
    n_sec_tb_income = Column(DECIMAL(20, 4), comment='代理买卖证券业务净收入')
    n_sec_uw_income = Column(DECIMAL(20, 4), comment='证券承销业务净收入')
    n_asset_mg_income = Column(DECIMAL(20, 4), comment='受托客户资产管理业务净收入')
    oth_b_income = Column(DECIMAL(20, 4), comment='其他业务收入')
    fv_value_chg_gain = Column(DECIMAL(20, 4), comment='加:公允价值变动净收益')
    invest_income = Column(DECIMAL(20, 4), comment='加:投资净收益')
    ass_invest_income = Column(DECIMAL(20, 4), comment='其中:对联营企业和合营企业的投资收益')
    forex_gain = Column(DECIMAL(20, 4), comment='加:汇兑净收益')
    total_cogs = Column(DECIMAL(20, 4), comment='营业总成本')
    oper_cost = Column(DECIMAL(20, 4), comment='减:营业成本')
    int_exp = Column(DECIMAL(20, 4), comment='减:利息支出')
    comm_exp = Column(DECIMAL(20, 4), comment='减:手续费及佣金支出')
    biz_tax_surchg = Column(DECIMAL(20, 4), comment='减:营业税金及附加')
    sell_exp = Column(DECIMAL(20, 4), comment='减:销售费用')
    admin_exp = Column(DECIMAL(20, 4), comment='减:管理费用')
    fin_exp = Column(DECIMAL(20, 4), comment='减:财务费用')
    assets_impair_loss = Column(DECIMAL(20, 4), comment='减:资产减值损失')
    prem_refund = Column(DECIMAL(20, 4), comment='退保金')
    compens_payout = Column(DECIMAL(20, 4), comment='赔付总支出')
    reser_insur_liab = Column(DECIMAL(20, 4), comment='提取保险责任准备金')
    div_payt = Column(DECIMAL(20, 4), comment='保户红利支出')
    reins_exp = Column(DECIMAL(20, 4), comment='分保费用')
    oper_exp = Column(DECIMAL(20, 4), comment='营业支出')
    compens_payout_refu = Column(DECIMAL(20, 4), comment='减:摊回赔付支出')
    insur_reser_refu = Column(DECIMAL(20, 4), comment='减:摊回保险责任准备金')
    reins_cost_refund = Column(DECIMAL(20, 4), comment='减:摊回分保费用')
    other_bus_cost = Column(DECIMAL(20, 4), comment='其他业务成本')
    operate_profit = Column(DECIMAL(20, 4), comment='营业利润')
    non_oper_income = Column(DECIMAL(20, 4), comment='加:营业外收入')
    non_oper_exp = Column(DECIMAL(20, 4), comment='减:营业外支出')
    nca_disploss = Column(DECIMAL(20, 4), comment='其中:减:非流动资产处置净损失')
    total_profit = Column(DECIMAL(20, 4), comment='利润总额')
    income_tax = Column(DECIMAL(20, 4), comment='所得税费用')
    n_income = Column(DECIMAL(20, 4), comment='净利润')
    n_income_attr_p = Column(DECIMAL(20, 4), comment='归属于母公司所有者的净利润')
    minority_gain = Column(DECIMAL(20, 4), comment='少数股东损益')
    oth_compr_income = Column(DECIMAL(20, 4), comment='其他综合收益')
    t_compr_income = Column(DECIMAL(20, 4), comment='综合收益总额')
    compr_inc_attr_p = Column(DECIMAL(20, 4), comment='归属于母公司所有者的综合收益总额')
    compr_inc_attr_m_s = Column(DECIMAL(20, 4), comment='归属于少数股东的综合收益总额')
    ebit = Column(DECIMAL(20, 4), comment='息税前利润')
    ebitda = Column(DECIMAL(20, 4), comment='息税折旧摊销前利润')
    insurance_exp = Column(DECIMAL(20, 4), comment='保险业务支出')
    undist_profit = Column(DECIMAL(20, 4), comment='年初未分配利润')
    distable_profit = Column(DECIMAL(20, 4), comment='可分配利润')
    rd_exp = Column(DECIMAL(20, 4), comment='研发费用')
    fin_exp_int_exp = Column(DECIMAL(20, 4), comment='财务费用:利息费用')
    fin_exp_int_inc = Column(DECIMAL(20, 4), comment='财务费用:利息收入')
    transfer_surplus_rese = Column(DECIMAL(20, 4), comment='转入盈余公积')
    transfer_housing_imprest = Column(DECIMAL(20, 4), comment='转入住房周转金')
    transfer_oth = Column(DECIMAL(20, 4), comment='转入其他')
    adj_lossgain = Column(DECIMAL(20, 4), comment='调整以前年度损益')
    withdra_legal_surplus = Column(DECIMAL(20, 4), comment='提取法定盈余公积')
    withdra_legal_pubfund = Column(DECIMAL(20, 4), comment='提取法定公益金')
    withdra_biz_devfund = Column(DECIMAL(20, 4), comment='提取企业发展基金')
    withdra_rese_fund = Column(DECIMAL(20, 4), comment='提取储备基金')
    withdra_oth_ersu = Column(DECIMAL(20, 4), comment='提取其他')
    workers_welfare = Column(DECIMAL(20, 4), comment='职工奖金福利')
    distr_profit_shrhder = Column(DECIMAL(20, 4), comment='可供股东分配的利润')
    prfshare_payable_dvd = Column(DECIMAL(20, 4), comment='应付优先股股利')
    comshare_payable_dvd = Column(DECIMAL(20, 4), comment='应付普通股股利')
    capit_comstock_div = Column(DECIMAL(20, 4), comment='转作股本的普通股股利')
    continued_net_profit = Column(DECIMAL(20, 4), comment='持续经营净利润')
    update_flag = Column(String(1), comment='更新标识')
    
    def to_dict(self):
        """转换为字典"""
        return {
            'ts_code': self.ts_code,
            'end_date': self.end_date,
            'ann_date': self.ann_date,
            'f_ann_date': self.f_ann_date,
            'report_type': self.report_type,
            'comp_type': self.comp_type,
            'end_type': self.end_type,
            'basic_eps': float(self.basic_eps) if self.basic_eps else None,
            'diluted_eps': float(self.diluted_eps) if self.diluted_eps else None,
            'total_revenue': float(self.total_revenue) if self.total_revenue else None,
            'revenue': float(self.revenue) if self.revenue else None,
            'n_income_attr_p': float(self.n_income_attr_p) if self.n_income_attr_p else None,
            'operate_profit': float(self.operate_profit) if self.operate_profit else None,
            'total_profit': float(self.total_profit) if self.total_profit else None,
            'n_income': float(self.n_income) if self.n_income else None,
        }
    
    def __repr__(self):
        return f'<StockIncomeStatement {self.ts_code} {self.end_date}>' 