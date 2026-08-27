"""
Testes Unitários da Interface CLI e Views (src/ui/views.py e src/main.py).
"""

from decimal import Decimal
from unittest.mock import AsyncMock, patch
import pytest

from src.main import main
from src.models import (
    ConversionRecord,
    ConversionResult,
    PPPResult,
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

    # Rates
    views.render_rates_table("USD", {"BRL": 5.5, "EUR": 0.92})

    # Crypto
    views.render_crypto_table([{"rank": "1", "symbol": "BTC", "name": "Bitcoin", "priceUsd": "95000", "changePercent24Hr": "2.5"}])

    # History
    views.render_history_table([ConversionRecord("1", "2026-08-27T17:00:00Z", "USD", "BRL", 100, 500, 5.0, 250)])

    # Favorites
    views.render_favorites(["USD", "BTC"])

    # Error & Success
    views.render_error("Mensagem de teste")
    views.render_success("Sucesso no teste")


def test_cli_help_flag():
    """Testa execução de main com flag --help."""
    with pytest.raises(SystemExit) as exc_info:
        main(["--help"])
    assert exc_info.value.code == 0
