from db_utils import DatabaseUtils
from parquet_job_helpers import get_stock_codes
from parquet_writer import save_partitioned_parquet


FIELDS = [
    "ts_code",
    "ann_date",
    "f_ann_date",
    "end_date",
    "report_type",
    "comp_type",
    "end_type",
    "basic_eps",
    "diluted_eps",
    "total_revenue",
    "revenue",
    "int_income",
    "prem_earned",
    "comm_income",
    "n_commis_income",
    "n_oth_income",
    "n_oth_b_income",
    "prem_income",
    "out_prem",
    "une_prem_reser",
    "reins_income",
    "n_sec_tb_income",
    "n_sec_uw_income",
    "n_asset_mg_income",
    "oth_b_income",
    "fv_value_chg_gain",
    "invest_income",
    "ass_invest_income",
    "forex_gain",
    "total_cogs",
    "oper_cost",
    "int_exp",
    "comm_exp",
    "biz_tax_surchg",
    "sell_exp",
    "admin_exp",
    "fin_exp",
    "assets_impair_loss",
    "prem_refund",
    "compens_payout",
    "reser_insur_liab",
    "div_payt",
    "reins_exp",
    "oper_exp",
    "compens_payout_refu",
    "insur_reser_refu",
    "reins_cost_refund",
    "other_bus_cost",
    "operate_profit",
    "non_oper_income",
    "non_oper_exp",
    "nca_disploss",
    "total_profit",
    "income_tax",
    "n_income",
    "n_income_attr_p",
    "minority_gain",
    "oth_compr_income",
    "t_compr_income",
    "compr_inc_attr_p",
    "compr_inc_attr_m_s",
    "ebit",
    "ebitda",
    "insurance_exp",
    "undist_profit",
    "distable_profit",
    "rd_exp",
    "fin_exp_int_exp",
    "fin_exp_int_inc",
    "transfer_surplus_rese",
    "transfer_housing_imprest",
    "transfer_oth",
    "adj_lossgain",
    "withdra_legal_surplus",
    "withdra_legal_pubfund",
    "withdra_biz_devfund",
    "withdra_rese_fund",
    "withdra_oth_ersu",
    "workers_welfare",
    "distr_profit_shrhder",
    "prfshare_payable_dvd",
    "comshare_payable_dvd",
    "capit_comstock_div",
    "continued_net_profit",
    "update_flag",
]


def main():
    pro = DatabaseUtils.init_tushare_api()
    stock_codes = get_stock_codes()
    frames = []

    for ts_code in stock_codes:
        df = pro.income(
            ts_code=ts_code,
            ann_date="",
            f_ann_date="",
            start_date=20200101,
            end_date=20250430,
            period="",
            report_type="",
            comp_type="",
            is_calc="",
            limit="",
            offset="",
            fields=FIELDS,
        )
        if df is not None and not df.empty:
            frames.append(df)

    if frames:
        import pandas as pd

        combined = pd.concat(frames, ignore_index=True)
        combined["end_date"] = combined["end_date"].astype(str)
        total_saved = save_partitioned_parquet(combined, "end_date", "income_statement")
        print(f"[income_statement] 完成，写入={total_saved}")


if __name__ == "__main__":
    main()
