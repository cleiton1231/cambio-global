"""
Testes Unitários do Motor de Tendências e Sparklines (src/trend.py).

Cobre:
- Geração de sparklines Unicode com proteção contra divisão por zero em séries flat.
- Casos extremos: lista vazia, único ponto, série com 2 pontos.
- Análise de tendências Fiat-Fiat e Cripto-USD com cálculo correto de métricas.
- Tratamento de parâmetros inválidos.
"""

from decimal import Decimal
import pytest
from unittest.mock import AsyncMock

from src.match import CurrencyMatcher
from src.models import ExchangeRate, TrendAnalysis
from src.trend import CurrencyTrendAnalyzer, generate_sparkline


# ============================================================================
# 1. Testes do Gerador de Sparklines
# ============================================================================

def test_sparkline_empty_and_single_point():
    """Testa geração de sparkline com entradas mínimas."""
    assert generate_sparkline([]) == ""
    assert generate_sparkline([Decimal("10.0")]) == "▄"


def test_sparkline_flat_series_zero_division_guard():
    """Garante que séries com valores constantes não disparem divisão por zero."""
    flat_series = [Decimal("5.0"), Decimal("5.0"), Decimal("5.0"), Decimal("5.0")]
    spark = generate_sparkline(flat_series)
    assert spark == "▄▄▄▄"
    assert len(spark) == 4


def test_sparkline_rising_and_falling():
    """Testa renderização de séries estritamente crescentes e decrescentes."""
    rising = [Decimal(str(i)) for i in range(1, 9)]
    spark_rising = generate_sparkline(rising)
    assert spark_rising == " ▂▃▄▅▆▇█"

    falling = [Decimal(str(i)) for i in range(8, 0, -1)]
    spark_falling = generate_sparkline(falling)
    assert spark_falling == "█▇▆▅▄▃▂ "


# ============================================================================
# 2. Testes do CurrencyTrendAnalyzer
# ============================================================================

@pytest.mark.asyncio
async def test_analyze_trend_fiat_to_fiat():
    """Testa análise de série histórica entre duas moedas fiduciárias."""
    mock_frankfurter = AsyncMock()
    mock_coincap = AsyncMock()
    matcher = CurrencyMatcher()

    mock_frankfurter.get_historical_rates.return_value = {
        "amount": 1.0,
        "base": "USD",
        "start_date": "2026-08-01",
        "end_date": "2026-08-27",
        "rates": {
            "2026-08-01": {"BRL": 5.00},
            "2026-08-10": {"BRL": 5.25},
            "2026-08-20": {"BRL": 4.90},
            "2026-08-27": {"BRL": 5.50},
        }
    }

    analyzer = CurrencyTrendAnalyzer(
        matcher=matcher,
        frankfurter=mock_frankfurter,
        coincap=mock_coincap,
    )

    result = await analyzer.analyze_trend("USD", "BRL", days=30)
    assert isinstance(result, TrendAnalysis)
    assert result.base_currency == "USD"
    assert result.target_currency == "BRL"
    assert result.start_rate == Decimal("5.00")
    assert result.end_rate == Decimal("5.50")
    assert result.min_rate == Decimal("4.90")
    assert result.max_rate == Decimal("5.50")
    assert result.change_pct == Decimal("10.0")  # (5.50 - 5.00) / 5.00 * 100 = 10%
    assert len(result.sparkline) == 4


@pytest.mark.asyncio
async def test_analyze_trend_crypto_to_usd():
    """Testa análise de série histórica de criptoativo em USD."""
    mock_frankfurter = AsyncMock()
    mock_coincap = AsyncMock()
    matcher = CurrencyMatcher()

    mock_coincap.get_historical_rates.return_value = [
        {"time": 1700000000000, "priceUsd": "90000.0"},
        {"time": 1700086400000, "priceUsd": "95000.0"},
        {"time": 1700172800000, "priceUsd": "100000.0"},
    ]

    analyzer = CurrencyTrendAnalyzer(
        matcher=matcher,
        frankfurter=mock_frankfurter,
        coincap=mock_coincap,
    )

    result = await analyzer.analyze_trend("BTC", "USD", days=30)
    assert result.base_currency == "BTC"
    assert result.target_currency == "USD"
    assert result.start_rate == Decimal("90000.0")
    assert result.end_rate == Decimal("100000.0")
    assert len(result.points) == 3


@pytest.mark.asyncio
async def test_analyze_trend_invalid_days():
    """Testa rejeição de período em dias inferior a 2."""
    analyzer = CurrencyTrendAnalyzer()
    with pytest.raises(ValueError, match="período em dias deve ser de no mínimo 2"):
        await analyzer.analyze_trend("USD", "BRL", days=1)
