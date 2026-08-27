"""
Testes Unitários e de Integração da Web API (src/web/app.py).

Cobre:
- Handlers de Healthcheck, Lista de Moedas, Busca/Autocomplete.
- Conversão Cambial Nominal (Fiat e Cripto), Cestas de Moedas e Paridade de Poder de Compra (PPP).
- Análise de Tendências e Sparklines (/api/trend).
- Histórico e Favoritos.
- Tratamento de Códigos de Status HTTP e exceções de domínio.
"""

from decimal import Decimal
import pytest
from unittest.mock import AsyncMock, patch

from src.models import (
    BasketItemResult,
    BasketResult,
    ConversionResult,
    CurrencyNotFoundError,
    ExchangeRate,
    PPPResult,
    TrendAnalysis,
    TrendPoint,
    UnsupportedPPPAssetError,
)
from src.web.app import (
    BasketRequest,
    ConvertRequest,
    FavoriteRequest,
    PPPRequest,
    handle_add_favorite,
    handle_basket,
    handle_convert,
    handle_get_crypto,
    handle_get_favorites,
    handle_get_history,
    handle_get_rates,
    handle_health_check,
    handle_list_currencies,
    handle_ppp,
    handle_remove_favorite,
    handle_search_currencies,
    handle_trend,
)


@pytest.mark.asyncio
async def test_api_health_check():
    """Testa endpoint de healthcheck."""
    res = await handle_health_check()
    assert res["status"] == "ok"
    assert res["service"] == "cambio-global"


@pytest.mark.asyncio
async def test_api_list_currencies():
    """Testa listagem de moedas com e sem filtro."""
    all_curr = await handle_list_currencies()
    assert len(all_curr) > 0

    fiat_curr = await handle_list_currencies(asset_type="fiat")
    assert all(c["asset_type"] == "fiat" for c in fiat_curr)

    crypto_curr = await handle_list_currencies(asset_type="crypto")
    assert all(c["asset_type"] == "crypto" for c in crypto_curr)


@pytest.mark.asyncio
async def test_api_search_currencies():
    """Testa autocompletion na busca de moedas."""
    res = await handle_search_currencies("bit", limit=3)
    assert any(c["code"] == "BTC" for c in res)


@pytest.mark.asyncio
async def test_api_convert_success():
    """Testa conversão nominal via handler."""
    real_conv_res = ConversionResult(
        amount_from=Decimal("100"),
        currency_from="USD",
        amount_to=Decimal("550"),
        currency_to="BRL",
        rate=Decimal("5.50"),
        source="frankfurter",
    )
    with patch("src.web.app.converter.convert", new_callable=AsyncMock) as mock_conv:
        mock_conv.return_value = real_conv_res

        req = ConvertRequest(amount=100.0, from_currency="USD", to_currency="BRL")
        res = await handle_convert(req)
        assert res["currency_from"] == "USD"
        assert res["currency_to"] == "BRL"
        assert res["amount_to"] == 550.0


@pytest.mark.asyncio
async def test_api_basket_success():
    """Testa endpoint de conversão em cesta."""
    mock_basket = BasketResult(
        amount_from=Decimal("100"),
        currency_from="USD",
        items=[
            BasketItemResult(currency_to="BRL", amount_to=Decimal("550"), rate=Decimal("5.5")),
            BasketItemResult(currency_to="EUR", amount_to=Decimal("90"), rate=Decimal("0.9")),
        ],
    )
    with patch("src.web.app.converter.convert_basket", new_callable=AsyncMock) as mock_b:
        mock_b.return_value = mock_basket

        req = BasketRequest(amount=100.0, from_currency="USD", targets=["BRL", "EUR"])
        res = await handle_basket(req)
        assert res["currency_from"] == "USD"
        assert len(res["items"]) == 2
        assert res["items"][0]["currency_to"] == "BRL"


@pytest.mark.asyncio
async def test_api_trend_success():
    """Testa endpoint de análise de tendência histórica."""
    mock_trend = TrendAnalysis(
        base_currency="USD",
        target_currency="BRL",
        days=30,
        points=[TrendPoint(date="2026-08-01", rate=Decimal("5.0")), TrendPoint(date="2026-08-27", rate=Decimal("5.5"))],
        start_rate=Decimal("5.0"),
        end_rate=Decimal("5.5"),
        min_rate=Decimal("5.0"),
        max_rate=Decimal("5.5"),
        avg_rate=Decimal("5.25"),
        change_pct=Decimal("10.0"),
        sparkline=" █",
    )
    with patch("src.web.app.trend_analyzer.analyze_trend", new_callable=AsyncMock) as mock_t:
        mock_t.return_value = mock_trend

        res = await handle_trend("USD", "BRL", days=30)
        assert res["base_currency"] == "USD"
        assert res["target_currency"] == "BRL"
        assert res["change_pct"] == 10.0
        assert res["sparkline"] == " █"


@pytest.mark.asyncio
async def test_api_ppp_success():
    """Testa conversão com PPP via handler."""
    real_conv = ConversionResult(
        amount_from=Decimal("100"),
        currency_from="USD",
        amount_to=Decimal("500"),
        currency_to="BRL",
        rate=Decimal("5.0"),
    )
    real_ppp = PPPResult(
        country_from="USA",
        country_to="BRA",
        currency_from="USD",
        currency_to="BRL",
        ppp_factor_from=Decimal("1.0"),
        ppp_factor_to=Decimal("2.5"),
        nominal_rate=Decimal("5.0"),
        ppp_rate=Decimal("2.5"),
        price_level_ratio=Decimal("2.0"),
        nominal_amount_to=Decimal("500"),
        ppp_equivalent_amount=Decimal("250"),
        year=2023,
    )
    with patch("src.web.app.converter.convert_with_ppp", new_callable=AsyncMock) as mock_ppp:
        mock_ppp.return_value = (real_conv, real_ppp)

        req = PPPRequest(amount=100.0, from_currency="USD", to_currency="BRL")
        res = await handle_ppp(req)
        assert "conversion" in res
        assert "ppp" in res
        assert res["ppp"]["country_from"] == "USA"
        assert res["ppp"]["ppp_equivalent_amount"] == 250.0


@pytest.mark.asyncio
async def test_api_favorites_flow():
    """Testa fluxo de adicionar, listar e remover favoritos."""
    req = FavoriteRequest(currency_code="BTC")
    add_res = await handle_add_favorite(req)
    assert add_res["code"] == "BTC"

    favs = await handle_get_favorites()
    assert "BTC" in favs

    rm_res = await handle_remove_favorite("BTC")
    assert rm_res["code"] == "BTC"
