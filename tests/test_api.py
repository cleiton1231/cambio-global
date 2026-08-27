"""
Testes de Integração com Mocks Isolados para as APIs Públicas (Zero Auth).

Cobre:
- FrankfurterClient (cotações fiat, pares, séries temporais e moedas).
- CoinCapClient (criptoativos, taxas USD, ranking).
- WorldBankClient (fator PPP, PIB per capita, seleção de ano mais recente).
- Resiliência e tratamento de erros defensivo (429, 500, timeouts).
"""

from decimal import Decimal
import json
import httpx
import pytest

from src.api.base import BaseAPIClient
from src.api.frankfurter import FrankfurterClient
from src.api.coincap import CoinCapClient
from src.api.world_bank import WorldBankClient
from src.models import (
    APIConnectionError,
    APIRateLimitError,
    APIResponseError,
    ExchangeRate,
)


# ============================================================================
# 1. Testes do FrankfurterClient
# ============================================================================

@pytest.mark.asyncio
async def test_frankfurter_get_latest_rates():
    """Testa obtenção de cotações mais recentes com Frankfurter."""
    mock_data = {
        "amount": 1.0,
        "base": "USD",
        "date": "2026-08-27",
        "rates": {"BRL": 5.42, "EUR": 0.92, "JPY": 155.0}
    }

    def handler(request: httpx.Request) -> httpx.Response:
        assert "base=USD" in str(request.url)
        return httpx.Response(200, json=mock_data)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as mock_http:
        client = FrankfurterClient(client=mock_http)
        result = await client.get_latest_rates(base="USD", symbols=["BRL", "EUR"])
        assert result["base"] == "USD"
        assert result["rates"]["BRL"] == 5.42


@pytest.mark.asyncio
async def test_frankfurter_get_rate():
    """Testa cálculo de taxa pontual entre duas moedas."""
    mock_data = {
        "amount": 1.0,
        "base": "USD",
        "date": "2026-08-27",
        "rates": {"BRL": 5.50}
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=mock_data)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as mock_http:
        client = FrankfurterClient(client=mock_http)
        
        # Teste de mesma moeda (retorna 1.0 sem requisição)
        same_rate = await client.get_rate("USD", "USD")
        assert same_rate.rate == Decimal("1.0")

        # Teste de moedas distintas
        rate = await client.get_rate("USD", "BRL")
        assert isinstance(rate, ExchangeRate)
        assert rate.base_currency == "USD"
        assert rate.target_currency == "BRL"
        assert rate.rate == Decimal("5.50")


@pytest.mark.asyncio
async def test_frankfurter_get_currencies():
    """Testa listagem de moedas suportadas pelo Frankfurter."""
    mock_data = {"BRL": "Brazilian Real", "USD": "United States Dollar"}

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=mock_data)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as mock_http:
        client = FrankfurterClient(client=mock_http)
        currencies = await client.get_currencies()
        assert "BRL" in currencies
        assert currencies["BRL"] == "Brazilian Real"


# ============================================================================
# 2. Testes do CoinCapClient
# ============================================================================

@pytest.mark.asyncio
async def test_coincap_get_asset():
    """Testa consulta de dados de um criptoativo específico."""
    mock_data = {
        "data": {
            "id": "bitcoin",
            "rank": "1",
            "symbol": "BTC",
            "name": "Bitcoin",
            "priceUsd": "95000.50",
            "changePercent24Hr": "2.45"
        }
    }

    def handler(request: httpx.Request) -> httpx.Response:
        assert "/assets/bitcoin" in str(request.url)
        return httpx.Response(200, json=mock_data)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as mock_http:
        client = CoinCapClient(client=mock_http)
        asset = await client.get_asset("BTC")
        assert asset["symbol"] == "BTC"
        assert asset["priceUsd"] == "95000.50"


@pytest.mark.asyncio
async def test_coincap_get_rate_in_usd():
    """Testa obtenção da cotação de cripto em USD."""
    mock_data = {
        "data": {
            "id": "ethereum",
            "symbol": "ETH",
            "priceUsd": "3500.25"
        }
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=mock_data)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as mock_http:
        client = CoinCapClient(client=mock_http)
        rate = await client.get_rate_in_usd("ETH")
        assert rate.base_currency == "ETH"
        assert rate.target_currency == "USD"
        assert rate.rate == Decimal("3500.25")


# ============================================================================
# 3. Testes do WorldBankClient
# ============================================================================

@pytest.mark.asyncio
async def test_world_bank_get_ppp_conversion_factor():
    """Testa recuperação do fator PPP selecionando o ano mais recente não-nulo."""
    mock_data = [
        {"page": 1, "pages": 1, "per_page": 10, "total": 2},
        [
            {"indicator": {"id": "PA.NUS.PPP"}, "country": {"value": "Brazil"}, "countryiso3code": "BRA", "date": "2024", "value": None},
            {"indicator": {"id": "PA.NUS.PPP"}, "country": {"value": "Brazil"}, "countryiso3code": "BRA", "date": "2023", "value": 2.85},
            {"indicator": {"id": "PA.NUS.PPP"}, "country": {"value": "Brazil"}, "countryiso3code": "BRA", "date": "2022", "value": 2.70},
        ]
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        assert "/country/BRA/indicator/PA.NUS.PPP" in str(request.url)
        return httpx.Response(200, json=mock_data)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as mock_http:
        client = WorldBankClient(client=mock_http)
        ppp = await client.get_ppp_conversion_factor("BRA")
        assert ppp is not None
        assert ppp["country_id"] == "BRA"
        assert ppp["year"] == 2023  # Selecionou o ano mais recente não-nulo
        assert ppp["value"] == Decimal("2.85")


@pytest.mark.asyncio
async def test_world_bank_get_gdp_per_capita():
    """Testa recuperação do PIB per capita."""
    mock_data = [
        {"page": 1},
        [
            {"country": {"value": "Brazil"}, "countryiso3code": "BRA", "date": "2023", "value": 10200.50}
        ]
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=mock_data)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as mock_http:
        client = WorldBankClient(client=mock_http)
        gdp = await client.get_gdp_per_capita("BRA")
        assert gdp is not None
        assert gdp["value"] == Decimal("10200.50")


# ============================================================================
# 4. Testes de Resiliência, Timeouts e Tratamento de Erros
# ============================================================================

@pytest.mark.asyncio
async def test_api_rate_limit_error_429():
    """Garante que HTTP 429 dispare APIRateLimitError."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, text="Too Many Requests")

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as mock_http:
        client = FrankfurterClient(client=mock_http)
        with pytest.raises(APIRateLimitError):
            await client.get_latest_rates()


@pytest.mark.asyncio
async def test_api_server_error_500():
    """Garante que HTTP 500 dispare APIResponseError defensivo."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="Internal Server Error")

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as mock_http:
        client = CoinCapClient(client=mock_http)
        with pytest.raises(APIResponseError) as exc_info:
            await client.get_assets()
        assert exc_info.value.status_code == 500


@pytest.mark.asyncio
async def test_api_connection_error():
    """Garante que falhas de rede disparem APIConnectionError após retries."""
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("Connection refused")

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as mock_http:
        client = FrankfurterClient(client=mock_http, timeout=1.0)
        client.max_retries = 1
        with pytest.raises(APIConnectionError):
            await client.get_latest_rates()
