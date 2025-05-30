from app.extensions import db
from datetime import datetime

class StockBusiness(db.Model):
    """股票业务大宽表模型"""
    __tablename__ = 'stock_business'
    
    # 主键
    ts_code = db.Column(db.String(20), primary_key=True, comment='TS股票代码')
    trade_date = db.Column(db.Date, primary_key=True, comment='交易日期')
    
    # 基本信息
    stock_name = db.Column(db.String(100), comment='股票名称')
    
    # 日线基本数据
    daily_close = db.Column(db.Numeric(10, 2), comment='当日收盘价')
    turnover_rate = db.Column(db.Numeric(10, 2), comment='换手率（%）')
    turnover_rate_f = db.Column(db.Numeric(10, 2), comment='换手率（自由流通股）')
    volume_ratio = db.Column(db.Numeric(10, 2), comment='量比')
    pe = db.Column(db.Numeric(10, 2), comment='市盈率（总市值/净利润， 亏损的PE为空）')
    pe_ttm = db.Column(db.Numeric(10, 2), comment='市盈率（TTM，亏损的PE为空）')
    pb = db.Column(db.Numeric(10, 2), comment='市净率（总市值/净资产）')
    ps = db.Column(db.Numeric(10, 2), comment='市销率')
    ps_ttm = db.Column(db.Numeric(10, 2), comment='市销率（TTM）')
    dv_ratio = db.Column(db.Numeric(10, 2), comment='股息率 （%）')
    dv_ttm = db.Column(db.Numeric(10, 2), comment='股息率（TTM）（%）')
    total_share = db.Column(db.Numeric(20, 2), comment='总股本 （万股）')
    float_share = db.Column(db.Numeric(20, 2), comment='流通股本 （万股）')
    free_share = db.Column(db.Numeric(20, 2), comment='自由流通股本 （万）')
    total_mv = db.Column(db.Numeric(20, 2), comment='总市值 （万元）')
    circ_mv = db.Column(db.Numeric(20, 2), comment='流通市值（万元）')
    
    # 技术因子数据
    factor_open = db.Column(db.Numeric(10, 2), comment='开盘价')
    factor_high = db.Column(db.Numeric(10, 2), comment='最高价')
    factor_low = db.Column(db.Numeric(10, 2), comment='最低价')
    factor_pre_close = db.Column(db.Numeric(10, 2), comment='昨收价')
    factor_change = db.Column(db.Numeric(10, 2), comment='涨跌额')
    factor_pct_change = db.Column(db.Numeric(10, 2), comment='涨跌幅')
    factor_vol = db.Column(db.Numeric(20, 2), comment='成交量')
    factor_amount = db.Column(db.Numeric(20, 2), comment='成交额')
    factor_adj_factor = db.Column(db.Numeric(10, 2), comment='复权因子')
    factor_open_hfq = db.Column(db.Numeric(10, 2), comment='后复权开盘价')
    factor_open_qfq = db.Column(db.Numeric(10, 2), comment='前复权开盘价')
    factor_close_hfq = db.Column(db.Numeric(10, 2), comment='后复权收盘价')
    factor_close_qfq = db.Column(db.Numeric(10, 2), comment='前复权收盘价')
    factor_high_hfq = db.Column(db.Numeric(10, 2), comment='后复权最高价')
    factor_high_qfq = db.Column(db.Numeric(10, 2), comment='前复权最高价')
    factor_low_hfq = db.Column(db.Numeric(10, 2), comment='后复权最低价')
    factor_low_qfq = db.Column(db.Numeric(10, 2), comment='前复权最低价')
    factor_pre_close_hfq = db.Column(db.Numeric(10, 2), comment='后复权昨收价')
    factor_pre_close_qfq = db.Column(db.Numeric(10, 2), comment='前复权昨收价')
    factor_macd_dif = db.Column(db.Numeric(10, 2), comment='MACD DIF值')
    factor_macd_dea = db.Column(db.Numeric(10, 2), comment='MACD DEA值')
    factor_macd = db.Column(db.Numeric(10, 2), comment='MACD值')
    factor_kdj_k = db.Column(db.Numeric(10, 2), comment='KDJ K值')
    factor_kdj_d = db.Column(db.Numeric(10, 2), comment='KDJ D值')
    factor_kdj_j = db.Column(db.Numeric(10, 2), comment='KDJ J值')
    factor_rsi_6 = db.Column(db.Numeric(10, 2), comment='RSI 6日')
    factor_rsi_12 = db.Column(db.Numeric(10, 2), comment='RSI 12日')
    factor_rsi_24 = db.Column(db.Numeric(10, 2), comment='RSI 24日')
    factor_boll_upper = db.Column(db.Numeric(10, 2), comment='布林上轨')
    factor_boll_mid = db.Column(db.Numeric(10, 2), comment='布林中轨')
    factor_boll_lower = db.Column(db.Numeric(10, 2), comment='布林下轨')
    factor_cci = db.Column(db.Numeric(10, 2), comment='CCI指标')
    
    # 资金流向数据
    moneyflow_pct_change = db.Column(db.Numeric(10, 2), comment='涨跌幅')
    moneyflow_latest = db.Column(db.Numeric(10, 2), comment='最新价')
    moneyflow_net_amount = db.Column(db.Numeric(20, 2), comment='净流入额')
    moneyflow_net_d5_amount = db.Column(db.Numeric(20, 2), comment='5日净流入额')
    moneyflow_buy_lg_amount = db.Column(db.Numeric(20, 2), comment='大单买入额')
    moneyflow_buy_lg_amount_rate = db.Column(db.Numeric(10, 2), comment='大单买入额占比')
    moneyflow_buy_md_amount = db.Column(db.Numeric(20, 2), comment='中单买入额')
    moneyflow_buy_md_amount_rate = db.Column(db.Numeric(10, 2), comment='中单买入额占比')
    moneyflow_buy_sm_amount = db.Column(db.Numeric(20, 2), comment='小单买入额')
    moneyflow_buy_sm_amount_rate = db.Column(db.Numeric(10, 2), comment='小单买入额占比')
    
    # 均线数据
    ma5 = db.Column(db.Numeric(10, 3), comment='5日移动平均线')
    ma10 = db.Column(db.Numeric(10, 3), comment='10日移动平均线')
    ma20 = db.Column(db.Numeric(10, 3), comment='20日移动平均线')
    ma30 = db.Column(db.Numeric(10, 3), comment='30日移动平均线')
    ma60 = db.Column(db.Numeric(10, 3), comment='60日移动平均线')
    ma120 = db.Column(db.Numeric(10, 3), comment='120日移动平均线')
    
    def to_dict(self):
        """转换为字典"""
        return {
            'ts_code': self.ts_code,
            'trade_date': self.trade_date.strftime('%Y-%m-%d') if self.trade_date else None,
            'stock_name': self.stock_name,
            
            # 基本数据
            'daily_close': float(self.daily_close) if self.daily_close else None,
            'turnover_rate': float(self.turnover_rate) if self.turnover_rate else None,
            'turnover_rate_f': float(self.turnover_rate_f) if self.turnover_rate_f else None,
            'volume_ratio': float(self.volume_ratio) if self.volume_ratio else None,
            'pe': float(self.pe) if self.pe else None,
            'pe_ttm': float(self.pe_ttm) if self.pe_ttm else None,
            'pb': float(self.pb) if self.pb else None,
            'ps': float(self.ps) if self.ps else None,
            'ps_ttm': float(self.ps_ttm) if self.ps_ttm else None,
            'dv_ratio': float(self.dv_ratio) if self.dv_ratio else None,
            'dv_ttm': float(self.dv_ttm) if self.dv_ttm else None,
            'total_share': float(self.total_share) if self.total_share else None,
            'float_share': float(self.float_share) if self.float_share else None,
            'free_share': float(self.free_share) if self.free_share else None,
            'total_mv': float(self.total_mv) if self.total_mv else None,
            'circ_mv': float(self.circ_mv) if self.circ_mv else None,
            
            # 技术因子
            'factor_open': float(self.factor_open) if self.factor_open else None,
            'factor_high': float(self.factor_high) if self.factor_high else None,
            'factor_low': float(self.factor_low) if self.factor_low else None,
            'factor_pre_close': float(self.factor_pre_close) if self.factor_pre_close else None,
            'factor_change': float(self.factor_change) if self.factor_change else None,
            'factor_pct_change': float(self.factor_pct_change) if self.factor_pct_change else None,
            'factor_vol': float(self.factor_vol) if self.factor_vol else None,
            'factor_amount': float(self.factor_amount) if self.factor_amount else None,
            'factor_adj_factor': float(self.factor_adj_factor) if self.factor_adj_factor else None,
            'factor_open_hfq': float(self.factor_open_hfq) if self.factor_open_hfq else None,
            'factor_open_qfq': float(self.factor_open_qfq) if self.factor_open_qfq else None,
            'factor_close_hfq': float(self.factor_close_hfq) if self.factor_close_hfq else None,
            'factor_close_qfq': float(self.factor_close_qfq) if self.factor_close_qfq else None,
            'factor_high_hfq': float(self.factor_high_hfq) if self.factor_high_hfq else None,
            'factor_high_qfq': float(self.factor_high_qfq) if self.factor_high_qfq else None,
            'factor_low_hfq': float(self.factor_low_hfq) if self.factor_low_hfq else None,
            'factor_low_qfq': float(self.factor_low_qfq) if self.factor_low_qfq else None,
            'factor_pre_close_hfq': float(self.factor_pre_close_hfq) if self.factor_pre_close_hfq else None,
            'factor_pre_close_qfq': float(self.factor_pre_close_qfq) if self.factor_pre_close_qfq else None,
            'factor_macd_dif': float(self.factor_macd_dif) if self.factor_macd_dif else None,
            'factor_macd_dea': float(self.factor_macd_dea) if self.factor_macd_dea else None,
            'factor_macd': float(self.factor_macd) if self.factor_macd else None,
            'factor_kdj_k': float(self.factor_kdj_k) if self.factor_kdj_k else None,
            'factor_kdj_d': float(self.factor_kdj_d) if self.factor_kdj_d else None,
            'factor_kdj_j': float(self.factor_kdj_j) if self.factor_kdj_j else None,
            'factor_rsi_6': float(self.factor_rsi_6) if self.factor_rsi_6 else None,
            'factor_rsi_12': float(self.factor_rsi_12) if self.factor_rsi_12 else None,
            'factor_rsi_24': float(self.factor_rsi_24) if self.factor_rsi_24 else None,
            'factor_boll_upper': float(self.factor_boll_upper) if self.factor_boll_upper else None,
            'factor_boll_mid': float(self.factor_boll_mid) if self.factor_boll_mid else None,
            'factor_boll_lower': float(self.factor_boll_lower) if self.factor_boll_lower else None,
            'factor_cci': float(self.factor_cci) if self.factor_cci else None,
            
            # 资金流向
            'moneyflow_pct_change': float(self.moneyflow_pct_change) if self.moneyflow_pct_change else None,
            'moneyflow_latest': float(self.moneyflow_latest) if self.moneyflow_latest else None,
            'moneyflow_net_amount': float(self.moneyflow_net_amount) if self.moneyflow_net_amount else None,
            'moneyflow_net_d5_amount': float(self.moneyflow_net_d5_amount) if self.moneyflow_net_d5_amount else None,
            'moneyflow_buy_lg_amount': float(self.moneyflow_buy_lg_amount) if self.moneyflow_buy_lg_amount else None,
            'moneyflow_buy_lg_amount_rate': float(self.moneyflow_buy_lg_amount_rate) if self.moneyflow_buy_lg_amount_rate else None,
            'moneyflow_buy_md_amount': float(self.moneyflow_buy_md_amount) if self.moneyflow_buy_md_amount else None,
            'moneyflow_buy_md_amount_rate': float(self.moneyflow_buy_md_amount_rate) if self.moneyflow_buy_md_amount_rate else None,
            'moneyflow_buy_sm_amount': float(self.moneyflow_buy_sm_amount) if self.moneyflow_buy_sm_amount else None,
            'moneyflow_buy_sm_amount_rate': float(self.moneyflow_buy_sm_amount_rate) if self.moneyflow_buy_sm_amount_rate else None,
            
            # 均线
            'ma5': float(self.ma5) if self.ma5 else None,
            'ma10': float(self.ma10) if self.ma10 else None,
            'ma20': float(self.ma20) if self.ma20 else None,
            'ma30': float(self.ma30) if self.ma30 else None,
            'ma60': float(self.ma60) if self.ma60 else None,
            'ma120': float(self.ma120) if self.ma120 else None,
        }
    
    def __repr__(self):
        return f'<StockBusiness {self.ts_code} {self.trade_date}>' 