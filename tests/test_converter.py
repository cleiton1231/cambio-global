"""
Testes Unitários do Motor de Conversão Cambial e PPP (src/converter.py).

Valida:
- Precisão matemática com Decimal em conversões Fiat-Fiat, Cripto-USD, Cripto-Fiat, Fiat-Cripto e Cripto-Cripto.
- Tratamento de mesma moeda (rate = 1.0).
- Cálculo exato de Paridade de Poder de Compra (PPP), taxa teórica e Razão de Nível de Preços (PLR).
- Rejeição de criptoativos em cálculos de PPP com UnsupportedPPPAssetError.
- Tratamento de erros para valores negativos/zero, taxas inválidas e países inexistentes.
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
async def test_convert_fiat_to_crypto_direct_usd(converter: CurrencyConverter, mock_clients):
    """Testa conversão de USD direto para Cripto (USD -> BTC)."""
    _, coincap, _ = mock_clients
    coincap.get_rate_in_usd.return_value = ExchangeRate(
        base_currency="BTC",
        target_currency="USD",
        rate=Decimal("50000.00"),
        source="coincap",
    )

    res = await converter.convert(Decimal("100000.00"), "USD", "BTC")
    assert res.currency_from == "USD"
    assert res.currency_to == "BTC"
    assert res.rate == Decimal("0.00002")
    assert res.amount_to == Decimal("2.0")


@pytest.mark.asyncio
async def test_convert_fiat_to_crypto_cross_non_usd(converter: CurrencyConverter, mock_clients):
    """Testa conversão de Fiat não-USD para Cripto (BRL -> BTC)."""
    frankfurter, coincap, _ = mock_clients
    frankfurter.get_rate.return_value = ExchangeRate(
        base_currency="BRL",
        target_currency="USD",
        rate=Decimal("0.20"),
        source="frankfurter",
    )
    coincap.get_rate_in_usd.return_value = ExchangeRate(
        base_currency="BTC",
        target_currency="USD",
        rate=Decimal("100000.00"),
        source="coincap",
    )

    res = await converter.convert(Decimal("500000.00"), "BRL", "BTC")
    assert res.currency_from == "BRL"
    assert res.currency_to == "BTC"
    assert res.rate == Decimal("0.000002")
    assert res.amount_to == Decimal("1.0")


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
    assert ppp_res.ppp_rate == Decimal("2.50")
    assert ppp_res.ppp_equivalent_amount == Decimal("2500.00")
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

    with pytest.raises(UnsupportedPPPAssetError):
        await converter.convert_with_ppp(
            amount=Decimal("100.0"),
            from_query="USD",
            to_query="ETH",
        )


@pytest.mark.asyncio
async def test_convert_with_ppp_missing_country_factor(converter: CurrencyConverter, mock_clients):
    """Testa tratamento de erro quando o Banco Mundial não possui dados para o país."""
    frankfurter, _, world_bank = mock_clients
    frankfurter.get_rate.return_value = ExchangeRate("USD", "BRL", Decimal("5.0"))
    world_bank.get_ppp_conversion_factor.return_value = None

    with pytest.raises(ValueError, match="Fator PPP do Banco Mundial não encontrado"):
        await converter.convert_with_ppp(
            amount=Decimal("100.0"),
            from_query="USD",
            to_query="BRL",
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


@pytest.mark.asyncio
async def test_convert_invalid_rate_zero(converter: CurrencyConverter, mock_clients):
    """Testa detecção de taxa zerada ou negativa."""
    frankfurter, _, _ = mock_clients
    frankfurter.get_rate.return_value = ExchangeRate("USD", "BRL", Decimal("0.0"))

    with pytest.raises(InvalidExchangeRateError):
        await converter.convert(Decimal("100"), "USD", "BRL")


# ============================================================================
# 4. Testes de Cesta de Moedas (Basket Converter)
# ============================================================================

@pytest.mark.asyncio
async def test_convert_basket_success(converter: CurrencyConverter, mock_clients):
    """Testa conversão simultânea para múltiplas moedas."""
    frankfurter, coincap, _ = mock_clients

    async def mock_frank_rate(base, target):
        rates = {"BRL": Decimal("5.50"), "EUR": Decimal("0.90")}
        return ExchangeRate(base, target, rates.get(target, Decimal("1.0")))

    frankfurter.get_rate.side_effect = mock_frank_rate
    coincap.get_rate_in_usd.return_value = ExchangeRate("BTC", "USD", Decimal("100000.00"))

    basket_res = await converter.convert_basket(
        amount=Decimal("100.00"),
        from_currency="USD",
        target_currencies=["BRL", "EUR", "BTC"],
    )

    assert basket_res.currency_from == "USD"
    assert basket_res.amount_from == Decimal("100.00")
    assert len(basket_res.items) == 3

    item_map = {item.currency_to: item for item in basket_res.items}
    assert item_map["BRL"].amount_to == Decimal("550.00")
    assert item_map["BRL"].error is None

    assert item_map["EUR"].amount_to == Decimal("90.00")
    assert item_map["EUR"].error is None

    assert item_map["BTC"].amount_to == Decimal("0.001")
    assert item_map["BTC"].error is None


@pytest.mark.asyncio
async def test_convert_basket_partial_failure(converter: CurrencyConverter, mock_clients):
    """Garante que falha em um item da cesta não aborte os outros válidos."""
    frankfurter, _, _ = mock_clients
    frankfurter.get_rate.return_value = ExchangeRate("USD", "BRL", Decimal("5.00"))

    basket_res = await converter.convert_basket(
        amount=Decimal("10.00"),
        from_currency="USD",
        target_currencies=["BRL", "INVALID_COIN_XYZ"],
    )

    assert len(basket_res.items) == 2
    item_map = {item.currency_to: item for item in basket_res.items}

    # BRL teve sucesso
    assert item_map["BRL"].amount_to == Decimal("50.00")
    assert item_map["BRL"].error is None

    # INVALID falhou graciosamente com mensagem de erro registrada
    assert item_map["INVALID_COIN_XYZ"].amount_to is None
    assert item_map["INVALID_COIN_XYZ"].error is not None

