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


def test_bj_codes_map_to_tdx_market_2():
    # 北交所：TDX market=2（920/43/83/87 开头），2026-10-11 实测可取 bars
    assert any_style_code_to_tdx("920025.BJ") == (2, "920025")
    assert any_style_code_to_tdx("bj.832000") == (2, "832000")
    assert any_style_code_to_tdx("430047") == (2, "430047")
    assert any_style_code_to_tdx("920002") == (2, "920002")
    assert bs_style_code_to_tdx("bj.920025") == (2, "920025")
    assert tdx_market_code_to_bs_style(2, "920025") == "bj.920025"


def test_bare_digits_market_routing():
    assert any_style_code_to_tdx("600000") == (1, "600000")
    assert any_style_code_to_tdx("000001") == (0, "000001")
    assert any_style_code_to_tdx("300502") == (0, "300502")
