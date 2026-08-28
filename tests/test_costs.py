"""
Testes Unitários do Simulador de Custos Reais, IOF, Spread e VET (src/costs.py).
"""

from decimal import Decimal
import pytest
from unittest.mock import AsyncMock

from src.costs import CostSimulator, DEFAULT_PROFILES
from src.models import (
    ConversionResult,
    CostSimulationResult,
    OperationType,
)


@pytest.fixture
def mock_converter():
    """Mock do conversor cambial retornando cotações determinísticas."""
    converter = AsyncMock()

    async def mock_convert(amount, from_currency, to_currency):
        # Taxa padrão BRL -> USD = 0.20 (1 BRL = 0.20 USD)
        if from_currency == "BRL" and to_currency == "USD":
            rate = Decimal("0.20")
        # Taxa padrão USD -> BRL = 5.00 (1 USD = 5.00 BRL)
        elif from_currency == "USD" and to_currency == "BRL":
            rate = Decimal("5.00")
        else:
            rate = Decimal("1.00")

        return ConversionResult(
            amount_from=amount,
            currency_from=from_currency,
            amount_to=amount * rate,
            currency_to=to_currency,
            rate=rate,
        )

    converter.convert.side_effect = mock_convert
    return converter


@pytest.mark.asyncio
async def test_simulate_outbound_global_account(mock_converter):
    """Testa simulação de compra/envio para o exterior com perfil Conta Global (Wise)."""
    simulator = CostSimulator(converter=mock_converter)

    # 1.000 BRL -> USD (Taxa comercial 0.20)
    result = await simulator.simulate(
        amount=Decimal("1000.00"),
        from_currency="BRL",
        to_currency="USD",
        profile_key="global_account",
    )

    assert isinstance(result, CostSimulationResult)
    assert result.operation_type == OperationType.OUTBOUND
    assert result.commercial_rate == Decimal("0.20")
    assert result.iof_pct == Decimal("1.10")
    assert result.spread_pct == Decimal("1.50")

    # Spread: 0.20 * (1 - 0.015) = 0.1970
    assert result.effective_rate == Decimal("0.1970")
    # Líquido entregue: 1000 * 0.1970 = 197.00 USD
    assert result.net_amount_to == Decimal("197.00")
    # IOF: 1000 * 0.011 = 11.00 BRL
    assert result.iof_amount == Decimal("11.00")
    # Custo Total: 1000 + 11.00 = 1011.00 BRL
    assert result.total_cost_from == Decimal("1011.00")
    # VET = 1011.00 / 197.00 ≈ 5.131979...
    assert round(result.vet, 4) == round(Decimal("1011.00") / Decimal("197.00"), 4)


@pytest.mark.asyncio
async def test_simulate_inbound_salary(mock_converter):
    """Testa simulação de recebimento de salário do exterior (Inbound)."""
    simulator = CostSimulator(converter=mock_converter)

    # Recebimento de $1.000 USD convertido em BRL (Taxa comercial 5.00)
    result = await simulator.simulate(
        amount=Decimal("1000.00"),
        from_currency="USD",
        to_currency="BRL",
        profile_key="inbound_salary",
    )

    assert result.operation_type == OperationType.INBOUND
    assert result.commercial_rate == Decimal("5.00")
    assert result.spread_pct == Decimal("1.20")
    assert result.iof_pct == Decimal("0.38")

    # Taxa efetiva com spread: 5.00 * (1 - 0.012) = 4.94 BRL/USD
    assert result.effective_rate == Decimal("4.9400")
    # Valor bruto: 1000 * 4.94 = 4940.00 BRL
    # IOF descontado: 4940 * 0.0038 = 18.772 BRL
    # Líquido em BRL: 4940 - 18.772 = 4921.228 BRL
    assert result.net_amount_to == Decimal("4921.228")
    # VET = 4921.228 / 1000 = 4.921228 BRL por USD
    assert result.vet == Decimal("4.921228")


@pytest.mark.asyncio
async def test_simulate_custom_parameters(mock_converter):
    """Testa perfil personalizado com taxas customizadas."""
    simulator = CostSimulator(converter=mock_converter)

    result = await simulator.simulate(
        amount=Decimal("500.00"),
        from_currency="BRL",
        to_currency="USD",
        profile_key="custom",
        custom_iof=Decimal("2.00"),
        custom_spread=Decimal("2.50"),
        custom_fee=Decimal("15.00"),
    )

    assert result.profile_name == "Personalizado"
    assert result.iof_pct == Decimal("2.00")
    assert result.spread_pct == Decimal("2.50")
    assert result.fixed_fee == Decimal("15.00")
    assert result.iof_amount == Decimal("10.00")  # 500 * 2%
    assert result.total_cost_from == Decimal("525.00")  # 500 + 10 + 15


@pytest.mark.asyncio
async def test_simulate_invalid_inputs(mock_converter):
    """Testa rejeição de quantias negativas ou taxas inválidas."""
    simulator = CostSimulator(converter=mock_converter)

    with pytest.raises(ValueError, match="maior que zero"):
        await simulator.simulate(Decimal("0"), "BRL", "USD")

    with pytest.raises(ValueError, match="não podem ser negativas"):
        await simulator.simulate(
            Decimal("100"), "BRL", "USD", custom_iof=Decimal("-1.0")
        )
