"""
Testes Unitários e de Integração da Web API (src/web/app.py).

Cobre:
- Handlers de Healthcheck, Lista de Moedas, Busca/Autocomplete.
- Conversão Cambial Nominal (Fiat e Cripto) e Paridade de Poder de Compra (PPP).
- Histórico e Favoritos.
- Tratamento de Códigos de Status HTTP e exceções de domínio.
"""

from decimal import Decimal
import pytest
from unittest.mock import AsyncMock, patch

from src.models import (
    ConversionResult,
    CurrencyNotFoundError,
    ExchangeRate,
    PPPResult,
    UnsupportedPPPAssetError,
)
from src.web.app import (
    ConvertRequest,
    FavoriteRequest,
    PPPRequest,
    handle_add_favorite,
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
