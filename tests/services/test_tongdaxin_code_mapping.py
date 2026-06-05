from app.services.tongdaxin.code_mapping import (
    any_style_code_to_tdx,
    bs_style_code_to_tdx,
    tdx_market_code_to_bs_style,
)


def test_bs_style_code_maps_to_tdx_market_tuple():
    market, code = bs_style_code_to_tdx("sz.300502")

    assert market == 0
    assert code == "300502"


def test_tushare_style_code_maps_to_tdx_market_tuple():
    market, code = any_style_code_to_tdx("600000.SH")

    assert market == 1
    assert code == "600000"


def test_tdx_tuple_maps_back_to_bs_style_code():
    assert tdx_market_code_to_bs_style(1, "600000") == "sh.600000"
