"""
Testes Unitários da Interface CLI e Views (src/ui/views.py e src/main.py).
"""

from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock, patch
import pytest

from src.main import main
from src.models import (
    BasketItemResult,
    BasketResult,
    ConversionRecord,
    ConversionResult,
    CostSimulationResult,
    OperationType,
    PPPResult,
    SalaryEquivalencyResult,
    TrendAnalysis,
    TrendPoint,
)
from src.ui.views import TerminalViews


def test_terminal_views_render():
    """Testa execução dos métodos de renderização sem disparar exceções."""
    views = TerminalViews()

    # Welcome
    views.render_welcome()

    # Conversion
    conv = ConversionResult(
        amount_from=Decimal("100"),
        currency_from="USD",
        amount_to=Decimal("500"),
        currency_to="BRL",
        rate=Decimal("5.0"),
        is_stale=True,
    )
    ppp = PPPResult(
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
    views.render_conversion_result(conv, ppp)

    # Cost Simulation
    sim = CostSimulationResult(
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
        fixed_fee=Decimal("10.00"),
        net_amount_to=Decimal("197.00"),
        total_cost_from=Decimal("1021.00"),
        vet=Decimal("5.182"),
        profile_name="Conta Global",
    )
    views.render_cost_simulation(sim)

    # Salary Equivalency
    sal = SalaryEquivalencyResult(
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
    views.render_salary_equivalency(sal)

    # Trend
    trend = TrendAnalysis(
        base_currency="USD",
        target_currency="BRL",
        days=30,
        points=[TrendPoint("2026-08-01", Decimal("5.0")), TrendPoint("2026-08-27", Decimal("5.5"))],
        start_rate=Decimal("5.0"),
        end_rate=Decimal("5.5"),
        min_rate=Decimal("4.9"),
        max_rate=Decimal("5.6"),
        avg_rate=Decimal("5.25"),
        change_pct=Decimal("10.0"),
        sparkline=" █",
    )
    views.render_trend_analysis(trend)

    # Basket
    basket = BasketResult(
        amount_from=Decimal("100"),
        currency_from="USD",
        items=[
            BasketItemResult("BRL", Decimal("550"), Decimal("5.5"), False, None),
            BasketItemResult("ERR", None, None, False, "Erro mock"),
        ],
    )
    views.render_basket_result(basket)

    # Rates & Crypto
    views.render_rates_table("USD", {"BRL": 5.5, "EUR": 0.92})
    views.render_crypto_table([{"rank": "1", "symbol": "BTC", "name": "Bitcoin", "priceUsd": "95000", "changePercent24Hr": "2.5"}])

    # History & Favorites
    views.render_history_table([ConversionRecord("1", "2026-08-27T17:00:00Z", "USD", "BRL", 100, 500, 5.0, 250)])
    views.render_history_table([])
    views.render_favorites(["USD", "BTC"])
    views.render_favorites([])

    # Error & Success
    views.render_error("Mensagem de teste")
    views.render_success("Sucesso no teste")


def test_cli_help_flag():
    """Testa execução de main com flag --help."""
    with pytest.raises(SystemExit) as exc_info:
        main(["--help"])
    assert exc_info.value.code == 0


def test_cli_flags_execution():
    """Testa execução de comandos via CLI."""
    with patch("src.main.CambioGlobalCLI.execute_conversion", new_callable=AsyncMock) as mock_exec:
        exit_code = main(["--convert", "100", "USD", "BRL"])
        assert exit_code == 0
        mock_exec.assert_called_once_with("100", "USD", "BRL", with_ppp=False)

    with patch("src.main.CambioGlobalCLI.execute_simulation", new_callable=AsyncMock) as mock_sim:
        exit_code = main(["--simulate", "1000", "BRL", "USD", "--profile", "global_account"])
        assert exit_code == 0
        mock_sim.assert_called_once_with("1000", "BRL", "USD", profile="global_account", iof_str=None, spread_str=None, fee_str=None, is_inbound=False)

    with patch("src.main.CambioGlobalCLI.execute_salary", new_callable=AsyncMock) as mock_sal:
        exit_code = main(["--salary", "5000", "USD", "BRL"])
        assert exit_code == 0
        mock_sal.assert_called_once_with("5000", "USD", "BRL", country_from=None, country_to=None)

    with patch("src.main.CambioGlobalCLI.generate_report_file", new_callable=AsyncMock) as mock_rep:
        exit_code = main(["--report-md", "relatorio.md"])
        assert exit_code == 0
        mock_rep.assert_called_once_with("relatorio.md", fmt="md")

        exit_code = main(["--report-html", "relatorio.html"])
        assert exit_code == 0
        mock_rep.assert_called_with("relatorio.html", fmt="html")

    with patch("src.main.CambioGlobalCLI.execute_basket", new_callable=AsyncMock) as mock_basket:
        exit_code = main(["--basket", "100", "USD", "BRL", "EUR"])
        assert exit_code == 0
        mock_basket.assert_called_once_with("100", "USD", ["BRL", "EUR"])

    with patch("src.main.CambioGlobalCLI.show_trend", new_callable=AsyncMock) as mock_trend:
        exit_code = main(["--trend", "USD", "BRL", "30"])
        assert exit_code == 0
        mock_trend.assert_called_once_with("USD", "BRL", days=30)

    exit_code = main(["--fav", "list"])
    assert exit_code == 0
