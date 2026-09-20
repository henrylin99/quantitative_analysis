import pandas as pd

from db_utils import DatabaseUtils
from parquet_writer import save_single_parquet

# Tushare 的 stock_company 按交易所分次查询，必须覆盖沪深北三市：
# 只拉 SSE 会让深市/北市股票（如 000001.SZ）的公司信息永远缺失
EXCHANGES = ("SSE", "SZSE", "BSE")

FIELDS = "ts_code,exchange,chairman,manager,secretary,reg_capital,setup_date,province"


def main():
    pro = DatabaseUtils.init_tushare_api()

    frames = []
    for exchange in EXCHANGES:
        try:
            part = pro.stock_company(exchange=exchange, fields=FIELDS)
        except Exception as exc:
            print(f"[stock_company] 下载 exchange={exchange} 失败: {exc}")
            continue
        if part is not None and not part.empty:
            print(f"[stock_company] exchange={exchange}: {len(part)} 条")
            frames.append(part)

    if not frames:
        print("[stock_company] 没有获取到公司资料，跳过写入。")
        return

    df = pd.concat(frames, ignore_index=True).drop_duplicates(subset="ts_code", keep="first")
    save_single_parquet(df, "stock_company.parquet")
    print(f"[stock_company] 完成，共写入 {len(df)} 条记录")


if __name__ == "__main__":
    main()
