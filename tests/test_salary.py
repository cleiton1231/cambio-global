"""
Testes Unitários da Calculadora de Salário Internacional e Relocation (src/salary.py).
"""

from decimal import Decimal
import pytest
from unittest.mock import AsyncMock

from src.models import (
    ConversionResult,
    SalaryEquivalencyResult,
    UnsupportedPPPAssetError,
)
from src.salary import InternationalSalaryCalculator


@pytest.fixture
def mock_dependencies():
    """Mock do conversor e do cliente do Banco Mundial."""
    converter = AsyncMock()
    world_bank = AsyncMock()

    # Taxa comercial USD -> BRL = 5.00
    converter.convert.return_value = ConversionResult(
        amount_from=Decimal("5000.00"),
        currency_from="USD",
        amount_to=Decimal("25000.00"),
        currency_to="BRL",
        rate=Decimal("5.00"),
    )

    async def mock_ppp(country_code: str):
        if country_code == "USA":
            return {"country_id": "USA", "year": 2023, "value": Decimal("1.00")}
        elif country_code == "BRA":
            return {"country_id": "BRA", "year": 2023, "value": Decimal("2.50")}
        elif country_code == "PRT":
            return {"country_id": "PRT", "year": 2023, "value": Decimal("0.60")}
        elif country_code == "DEU":
            return {"country_id": "DEU", "year": 2023, "value": Decimal("0.80")}
        return None

    world_bank.get_ppp_conversion_factor.side_effect = mock_ppp
    return converter, world_bank


@pytest.mark.asyncio
async def test_calculate_salary_equivalency_usd_to_brl(mock_dependencies):
    """Testa cálculo de equivalência salarial USA ($5.000) -> Brasil (BRL)."""
    converter, world_bank = mock_dependencies
    calc = InternationalSalaryCalculator(converter=converter, world_bank=world_bank)

    result = await calc.calculate_salary_equivalency(
        base_salary=Decimal("5000.00"),
        base_currency="USD",
        target_currency="BRL",
    )

    assert isinstance(result, SalaryEquivalencyResult)
    assert result.country_from == "USA"
    assert result.country_to == "BRA"
    assert result.nominal_converted_salary == Decimal("25000.00")
    # Salário PPP: 5000 * (2.50 / 1.00) = 12.500 BRL
    assert result.ppp_equivalent_salary == Decimal("12500.00")
    # Ganho real: (25000 - 12500) / 12500 * 100 = +100%
    assert result.purchasing_power_diff_pct == Decimal("100.0")
    assert "ganho real de +100.0%" in result.verdict


@pytest.mark.asyncio
async def test_calculate_salary_with_explicit_country_override(mock_dependencies):
    """Testa desambiguação de país (ex: EUR em Portugal vs Alemanha)."""
    converter, world_bank = mock_dependencies
    converter.convert.return_value = ConversionResult(
        amount_from=Decimal("5000.00"),
        currency_from="USD",
        amount_to=Decimal("4500.00"),
        currency_to="EUR",
        rate=Decimal("0.90"),
    )

    calc = InternationalSalaryCalculator(converter=converter, world_bank=world_bank)

    # Simulação para Portugal (PRT: PPP=0.60)
    result_pt = await calc.calculate_salary_equivalency(
        base_salary=Decimal("5000.00"),
        base_currency="USD",
        target_currency="EUR",
        country_to="PRT",
    )
    assert result_pt.country_to == "PRT"
    # PPP Salário em Portugal: 5000 * 0.60 = 3.000 EUR
    assert result_pt.ppp_equivalent_salary == Decimal("3000.00")

    # Simulação para Alemanha (DEU: PPP=0.80)
    result_de = await calc.calculate_salary_equivalency(
        base_salary=Decimal("5000.00"),
        base_currency="USD",
        target_currency="EUR",
        country_to="DEU",
    )
    assert result_de.country_to == "DEU"
    # PPP Salário na Alemanha: 5000 * 0.80 = 4.000 EUR
    assert result_de.ppp_equivalent_salary == Decimal("4000.00")


@pytest.mark.asyncio
async def test_salary_rejects_crypto():
    """Garante que a calculadora de salários rejeite criptoativos."""
    calc = InternationalSalaryCalculator()

    with pytest.raises(UnsupportedPPPAssetError):
        await calc.calculate_salary_equivalency(
            base_salary=Decimal("1.0"),
            base_currency="BTC",
            target_currency="USD",
        )


@pytest.mark.asyncio
async def test_salary_invalid_amount():
    """Garante rejeição de quantia salarial zerada ou negativa."""
    calc = InternationalSalaryCalculator()

    with pytest.raises(ValueError, match="maior que zero"):
        await calc.calculate_salary_equivalency(
            base_salary=Decimal("0"),
            base_currency="USD",
            target_currency="BRL",
        )
