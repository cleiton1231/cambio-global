"""
Testes Unitários do Motor de Conversão Cambial e PPP (src/converter.py).

Valida:
- Precisão matemática com Decimal em conversões Fiat-Fiat, Cripto-USD, Cripto-Fiat e Cripto-Cripto.
- Tratamento de mesma moeda (rate = 1.0).
- Cálculo exato de Paridade de Poder de Compra (PPP), taxa teórica e Razão de Nível de Preços (PLR).
- Rejeição de criptoativos em cálculos de PPP com UnsupportedPPPAssetError.
- Tratamento de erros para valores negativos/zero e taxas inválidas.
"""

from decimal import Decimal
import pytest
from unittest.mock import AsyncMock

from src.converter import CurrencyConverter
from src.match import CurrencyMatcher
from src.models import (
    AssetType,
    ConversionResult,
    ExchangeRate,
    InvalidExchangeRateError,
    PPPResult,
    UnsupportedPPPAssetError,
)


@pytest.fixture
def mock_clients():
    """Cria mocks assíncronos para os 3 clientes de API."""
    frankfurter = AsyncMock()
    coincap = AsyncMock()
    world_bank = AsyncMock()
    return frankfurter, coincap, world_bank


@pytest.fixture
def converter(mock_clients) -> CurrencyConverter:
    """Instancia o CurrencyConverter com clientes mockados e matcher real."""
    frankfurter, coincap, world_bank = mock_clients
    matcher = CurrencyMatcher()
    return CurrencyConverter(
        matcher=matcher,
        frankfurter=frankfurter,
        coincap=coincap,
        world_bank=world_bank,
    )


# ============================================================================
# 1. Testes de Conversão Direta e Cruzada (Fiat e Cripto)
# ============================================================================

@pytest.mark.asyncio
async def test_convert_same_currency(converter: CurrencyConverter):
    """Testa conversão quando origem e destino são a mesma moeda."""
    res = await converter.convert(Decimal("100.00"), "USD", "USD")
    assert isinstance(res, ConversionResult)
    assert res.amount_from == Decimal("100.00")
    assert res.amount_to == Decimal("100.00")
    assert res.rate == Decimal("1.0")


@pytest.mark.asyncio
async def test_convert_fiat_to_fiat(converter: CurrencyConverter, mock_clients):
    """Testa conversão de Fiat para Fiat via Frankfurter."""
    frankfurter, _, _ = mock_clients
    frankfurter.get_rate.return_value = ExchangeRate(
        base_currency="USD",
        target_currency="BRL",
        rate=Decimal("5.50"),
        source="frankfurter",
    )

    res = await converter.convert(Decimal("100.00"), "USD", "BRL")
    assert res.currency_from == "USD"
    assert res.currency_to == "BRL"
    assert res.rate == Decimal("5.50")
    assert res.amount_to == Decimal("550.00")


@pytest.mark.asyncio
async def test_convert_crypto_to_usd(converter: CurrencyConverter, mock_clients):
    """Testa conversão de Cripto para USD via CoinCap."""
    _, coincap, _ = mock_clients
    coincap.get_rate_in_usd.return_value = ExchangeRate(
        base_currency="BTC",
        target_currency="USD",
        rate=Decimal("90000.00"),
        source="coincap",
    )

    res = await converter.convert(Decimal("0.5"), "BTC", "USD")
    assert res.currency_from == "BTC"
    assert res.currency_to == "USD"
    assert res.rate == Decimal("90000.00")
    assert res.amount_to == Decimal("45000.00")


@pytest.mark.asyncio
async def test_convert_crypto_to_fiat_cross(converter: CurrencyConverter, mock_clients):
    """Testa conversão de Cripto para Fiat não-USD (BTC -> BRL)."""
    frankfurter, coincap, _ = mock_clients
    coincap.get_rate_in_usd.return_value = ExchangeRate(
        base_currency="BTC",
        target_currency="USD",
        rate=Decimal("100000.00"),
        source="coincap",
    )
    frankfurter.get_rate.return_value = ExchangeRate(
        base_currency="USD",
        target_currency="BRL",
        rate=Decimal("5.00"),
        source="frankfurter",
    )

    res = await converter.convert(Decimal("2.0"), "BTC", "reais")
    assert res.currency_from == "BTC"
    assert res.currency_to == "BRL"
    assert res.rate == Decimal("500000.00")
    assert res.amount_to == Decimal("1000000.00")


@pytest.mark.asyncio
async def test_convert_crypto_to_crypto(converter: CurrencyConverter, mock_clients):
    """Testa conversão entre dois criptoativos (ETH -> BTC)."""
    _, coincap, _ = mock_clients
    
    async def mock_get_rate(ticker: str):
        if ticker.upper() == "ETH":
            return ExchangeRate("ETH", "USD", Decimal("3000.00"), source="coincap")
        elif ticker.upper() == "BTC":
            return ExchangeRate("BTC", "USD", Decimal("60000.00"), source="coincap")
        raise ValueError("Unknown")

    coincap.get_rate_in_usd.side_effect = mock_get_rate

    res = await converter.convert(Decimal("10.0"), "ETH", "BTC")
    assert res.currency_from == "ETH"
    assert res.currency_to == "BTC"
    assert res.rate == Decimal("0.05")
    assert res.amount_to == Decimal("0.50")


# ============================================================================
# 2. Testes de Paridade de Poder de Compra (PPP)
# ============================================================================

@pytest.mark.asyncio
async def test_convert_with_ppp_success(converter: CurrencyConverter, mock_clients):
    """Testa cálculo de Paridade de Poder de Compra entre dois países e moedas fiduciárias."""
    frankfurter, _, world_bank = mock_clients

    # Taxa nominal de mercado: 1 USD = 5.00 BRL
    frankfurter.get_rate.return_value = ExchangeRate(
        base_currency="USD",
        target_currency="BRL",
        rate=Decimal("5.00"),
        source="frankfurter",
    )

    # Fatores PPP: USA = 1.00 USD/Intl$, BRA = 2.50 BRL/Intl$
    async def mock_ppp(country_code: str):
        if country_code == "USA":
            return {"country_id": "USA", "year": 2023, "value": Decimal("1.00")}
        elif country_code == "BRA":
            return {"country_id": "BRA", "year": 2023, "value": Decimal("2.50")}
        return None

    world_bank.get_ppp_conversion_factor.side_effect = mock_ppp

    conv_res, ppp_res = await converter.convert_with_ppp(
        amount=Decimal("1000.00"),
        from_query="USD",
        to_query="BRL",
    )

    assert isinstance(conv_res, ConversionResult)
    assert conv_res.amount_to == Decimal("5000.00")  # Nominal

    assert isinstance(ppp_res, PPPResult)
    assert ppp_res.country_from == "USA"
    assert ppp_res.country_to == "BRA"
    # PPP Rate: PPP_BRA / PPP_USA = 2.50 / 1.00 = 2.50
    assert ppp_res.ppp_rate == Decimal("2.50")
    # Equivalente PPP: 1000 USD tem poder de compra equivalente a 2500 BRL no Brasil
    assert ppp_res.ppp_equivalent_amount == Decimal("2500.00")
    # Price Level Ratio: Nominal (5.00) / PPP (2.50) = 2.00
    assert ppp_res.price_level_ratio == Decimal("2.00")


@pytest.mark.asyncio
async def test_convert_with_ppp_rejects_crypto(converter: CurrencyConverter):
    """Garante que tentativa de cálculo de PPP em Criptoativos levante UnsupportedPPPAssetError."""
    with pytest.raises(UnsupportedPPPAssetError):
        await converter.convert_with_ppp(
            amount=Decimal("1.0"),
            from_query="BTC",
            to_query="USD",
        )


# ============================================================================
# 3. Testes de Erros e Validações Numéricas
# ============================================================================

@pytest.mark.asyncio
async def test_convert_invalid_amount(converter: CurrencyConverter):
    """Testa rejeição de quantias negativas ou zeradas."""
    with pytest.raises(ValueError):
        await converter.convert(Decimal("0"), "USD", "BRL")

    with pytest.raises(ValueError):
        await converter.convert(Decimal("-50.0"), "USD", "BRL")
