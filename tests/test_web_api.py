"""
Testes Unitários e de Integração da Web API (src/web/app.py).

Cobre:
- Handlers de Healthcheck, Lista de Moedas, Busca/Autocomplete.
- Conversão Cambial Nominal, Cestas, Simulação de Custos / VET e Salário Internacional.
- Geração de Relatórios Executivos (/api/report).
- Histórico e Favoritos.
"""

from datetime import datetime, timezone
from decimal import Decimal
import pytest
from unittest.mock import AsyncMock, patch

from src.models import (
    BasketItemResult,
    BasketResult,
    ConversionResult,
    CostSimulationResult,
    CurrencyNotFoundError,
    ExchangeRate,
    OperationType,
    PPPResult,
    SalaryEquivalencyResult,
    TrendAnalysis,
    TrendPoint,
)
from src.web.app import (
    BasketRequest,
    ConvertRequest,
    CostSimulateRequest,
    FavoriteRequest,
    PPPRequest,
    ReportRequest,
    SalaryRequest,
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
    handle_report,
    handle_salary,
    handle_search_currencies,
    handle_simulate,
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
async def test_api_simulate_success():
    """Testa endpoint de simulação de custos e VET."""
    mock_sim = CostSimulationResult(
        amount_from=Decimal("1000"),
        currency_from="BRL",
        amount_to=Decimal("200"),
        currency_to="USD",
        operation_type=OperationType.OUTBOUND,
        commercial_rate=Decimal("0.20"),
        spread_pct=Decimal("1.50"),
        spread_amount=Decimal("0.003"),
        effective_rate=Decimal("0.197"),
        iof_pct=Decimal("1.10"),
        iof_amount=Decimal("11.00"),
        fixed_fee=Decimal("0.00"),
        net_amount_to=Decimal("197.00"),
        total_cost_from=Decimal("1011.00"),
        vet=Decimal("5.132"),
        profile_name="Conta Global",
    )
    with patch("src.web.app.cost_simulator.simulate", new_callable=AsyncMock) as mock_s:
        mock_s.return_value = mock_sim

        req = CostSimulateRequest(amount=1000.0, from_currency="BRL", to_currency="USD")
        res = await handle_simulate(req)
        assert res["vet"] == 5.132
        assert res["profile_name"] == "Conta Global"


@pytest.mark.asyncio
async def test_api_salary_success():
    """Testa endpoint de cálculo salarial internacional."""
    mock_sal = SalaryEquivalencyResult(
        base_salary=Decimal("5000"),
        base_currency="USD",
        target_currency="BRL",
        country_from="USA",
        country_to="BRA",
        nominal_converted_salary=Decimal("25000"),
        ppp_equivalent_salary=Decimal("12500"),
        purchasing_power_diff_pct=Decimal("100.0"),
        price_level_ratio=Decimal("2.0"),
        verdict="Ganho real de +100%",
        year=2023,
    )
    with patch("src.web.app.salary_calculator.calculate_salary_equivalency", new_callable=AsyncMock) as mock_sal_fn:
        mock_sal_fn.return_value = mock_sal

        req = SalaryRequest(base_salary=5000.0, base_currency="USD", target_currency="BRL")
        res = await handle_salary(req)
        assert res["nominal_converted_salary"] == 25000.0
        assert res["ppp_equivalent_salary"] == 12500.0


@pytest.mark.asyncio
async def test_api_report_success():
    """Testa endpoint de emissão de relatório financeiro."""
    with patch("src.web.app.converter.convert", new_callable=AsyncMock) as mock_c, \
         patch("src.web.app.cost_simulator.simulate", new_callable=AsyncMock) as mock_s:
        mock_c.return_value = ConversionResult(Decimal("100"), "USD", Decimal("500"), "BRL", Decimal("5.0"))
        mock_s.return_value = CostSimulationResult(
            Decimal("100"), "USD", Decimal("500"), "BRL", OperationType.OUTBOUND,
            Decimal("5.0"), Decimal("1.5"), Decimal("0.075"), Decimal("4.925"),
            Decimal("1.1"), Decimal("1.1"), Decimal("0.0"), Decimal("492.5"),
            Decimal("101.1"), Decimal("0.205"), "Teste"
        )

        req = ReportRequest(title="Relatório Teste", amount=100.0, from_currency="USD", to_currency="BRL", format="html")
        res = await handle_report(req)
        assert res["title"] == "Relatório Teste"
        assert res["format"] == "html"
        assert "<!DOCTYPE html>" in res["content"]


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
