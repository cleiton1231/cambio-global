"""
Testes Unitários da Interface CLI e Views (src/ui/views.py e src/main.py).
"""

from decimal import Decimal
from unittest.mock import AsyncMock, patch
import pytest

from src.main import main, start_web_server
from src.models import (
    BasketItemResult,
    BasketResult,
    ConversionRecord,
    ConversionResult,
    PPPResult,
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

    # Rates
    views.render_rates_table("USD", {"BRL": 5.5, "EUR": 0.92})

    # Crypto
    views.render_crypto_table([{"rank": "1", "symbol": "BTC", "name": "Bitcoin", "priceUsd": "95000", "changePercent24Hr": "2.5"}])

    # History
    views.render_history_table([ConversionRecord("1", "2026-08-27T17:00:00Z", "USD", "BRL", 100, 500, 5.0, 250)])
    views.render_history_table([])

    # Favorites
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
    """Testa execução de comandos via CLI (convert, basket, trend, rates, history, fav)."""
    with patch("src.main.CambioGlobalCLI.execute_conversion", new_callable=AsyncMock) as mock_exec:
        exit_code = main(["--convert", "100", "USD", "BRL"])
        assert exit_code == 0
        mock_exec.assert_called_once_with("100", "USD", "BRL", with_ppp=False)

    with patch("src.main.CambioGlobalCLI.execute_basket", new_callable=AsyncMock) as mock_basket:
        exit_code = main(["--basket", "100", "USD", "BRL", "EUR"])
        assert exit_code == 0
        mock_basket.assert_called_once_with("100", "USD", ["BRL", "EUR"])

    with patch("src.main.CambioGlobalCLI.show_trend", new_callable=AsyncMock) as mock_trend:
        exit_code = main(["--trend", "USD", "BRL", "30"])
        assert exit_code == 0
        mock_trend.assert_called_once_with("USD", "BRL", days=30)

    with patch("src.main.CambioGlobalCLI.show_rates", new_callable=AsyncMock) as mock_rates:
        exit_code = main(["--rates", "EUR"])
        assert exit_code == 0
        mock_rates.assert_called_once_with("EUR")

    with patch("src.main.CambioGlobalCLI.show_crypto", new_callable=AsyncMock) as mock_crypto:
        exit_code = main(["--crypto", "10"])
        assert exit_code == 0
        mock_crypto.assert_called_once_with(10)

    exit_code = main(["--fav", "list"])
    assert exit_code == 0

    exit_code = main(["--fav", "add", "USD"])
    assert exit_code == 0

    exit_code = main(["--fav", "rm", "USD"])
    assert exit_code == 0
