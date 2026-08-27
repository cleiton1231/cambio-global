"""
Testes Unitários Exaustivos do Motor de Matching e Resolução de Moedas (src/match.py).

Garante conformidade com as regras críticas do GEMINI.md:
- Determinismo absoluto e sem adivinhações cegas.
- Resolução de símbolos monetários ($, R$, €, £, ¥, ₿, Ξ).
- Resolução de códigos ISO 4217 (BRL, USD, EUR, GBP, JPY, etc.).
- Resolução de nomes populares e variações plurais em português e inglês (dólar, real, reais, euros, iene).
- Resolução de tickers e nomes de criptoativos (BTC, ETH, SOL, bitcoin, ethereum).
- Tratamento de ruídos, espaços e maiúsculas/minúsculas.
- Precedência de fiat vs. stablecoin (USD vs USDT).
- Tratamento de entradas desconhecidas e ambíguas.
"""

import pytest
from src.models import (
    AssetType,
    CurrencyInfo,
    CurrencyNotFoundError,
    AmbiguousCurrencyError,
)
from src.match import CurrencyMatcher, get_matcher


@pytest.fixture
def matcher() -> CurrencyMatcher:
    """Retorna uma instância limpa do motor de matching."""
    return get_matcher()


# ============================================================================
# 1. Testes de Códigos ISO 4217 e Tickers Cripto (Exatos e Case-Insensitive)
# ============================================================================

@pytest.mark.unit
@pytest.mark.parametrize("query,expected_code,expected_type", [
    ("USD", "USD", AssetType.FIAT),
    ("usd", "USD", AssetType.FIAT),
    ("Usd", "USD", AssetType.FIAT),
    ("BRL", "BRL", AssetType.FIAT),
    ("brl", "BRL", AssetType.FIAT),
    ("EUR", "EUR", AssetType.FIAT),
    ("eur", "EUR", AssetType.FIAT),
    ("GBP", "GBP", AssetType.FIAT),
    ("JPY", "JPY", AssetType.FIAT),
    ("CAD", "CAD", AssetType.FIAT),
    ("AUD", "AUD", AssetType.FIAT),
    ("CHF", "CHF", AssetType.FIAT),
    ("CNY", "CNY", AssetType.FIAT),
    ("ARS", "ARS", AssetType.FIAT),
    ("BTC", "BTC", AssetType.CRYPTO),
    ("btc", "BTC", AssetType.CRYPTO),
    ("ETH", "ETH", AssetType.CRYPTO),
    ("eth", "ETH", AssetType.CRYPTO),
    ("SOL", "SOL", AssetType.CRYPTO),
    ("sol", "SOL", AssetType.CRYPTO),
    ("USDT", "USDT", AssetType.CRYPTO),
    ("BNB", "BNB", AssetType.CRYPTO),
])
def test_match_exact_codes(matcher: CurrencyMatcher, query: str, expected_code: str, expected_type: AssetType):
    """Testa identificação exata de códigos ISO e tickers de cripto."""
    info = matcher.match(query)
    assert isinstance(info, CurrencyInfo)
    assert info.code == expected_code
    assert info.asset_type == expected_type


# ============================================================================
# 2. Testes de Símbolos Monetários
# ============================================================================

@pytest.mark.unit
@pytest.mark.parametrize("symbol,expected_code", [
    ("R$", "BRL"),
    ("r$", "BRL"),
    ("$", "USD"),
    ("US$", "USD"),
    ("€", "EUR"),
    ("£", "GBP"),
    ("¥", "JPY"),
    ("₿", "BTC"),
    ("Ξ", "ETH"),
])
def test_match_symbols(matcher: CurrencyMatcher, symbol: str, expected_code: str):
    """Testa identificação determinística de símbolos monetários."""
    info = matcher.match(symbol)
    assert isinstance(info, CurrencyInfo)
    assert info.code == expected_code


# ============================================================================
# 3. Testes de Nomes Populares e Variações Multilíngues (PT / EN / Plurais)
# ============================================================================

@pytest.mark.unit
@pytest.mark.parametrize("query,expected_code", [
    # Português com e sem acentos / plurais
    ("real", "BRL"),
    ("reais", "BRL"),
    ("real brasileiro", "BRL"),
    ("dólar", "USD"),
    ("dolar", "USD"),
    ("dólares", "USD"),
    ("dolares", "USD"),
    ("dólar americano", "USD"),
    ("dolar americano", "USD"),
    ("euro", "EUR"),
    ("euros", "EUR"),
    ("iene", "JPY"),
    ("ienes", "JPY"),
    ("libra", "GBP"),
    ("libras", "GBP"),
    ("libra esterlina", "GBP"),
    ("peso argentino", "ARS"),
    ("pesos argentinos", "ARS"),
    ("franco suíço", "CHF"),
    ("franco suico", "CHF"),
    ("dólar canadense", "CAD"),
    ("dolar canadense", "CAD"),
    ("dólar australiano", "AUD"),
    ("dolar australiano", "AUD"),
    ("yuan chinês", "CNY"),
    ("yuan", "CNY"),
    # Inglês
    ("brazilian real", "BRL"),
    ("us dollar", "USD"),
    ("dollar", "USD"),
    ("dollars", "USD"),
    ("british pound", "GBP"),
    ("pound", "GBP"),
    ("pounds", "GBP"),
    ("japanese yen", "JPY"),
    ("yen", "JPY"),
    ("swiss franc", "CHF"),
    ("canadian dollar", "CAD"),
    ("australian dollar", "AUD"),
    ("argentine peso", "ARS"),
    ("chinese yuan", "CNY"),
    # Criptoativos
    ("bitcoin", "BTC"),
    ("bitcoins", "BTC"),
    ("ethereum", "ETH"),
    ("ether", "ETH"),
    ("solana", "SOL"),
    ("tether", "USDT"),
    ("binance coin", "BNB"),
])
def test_match_names_and_aliases(matcher: CurrencyMatcher, query: str, expected_code: str):
    """Testa identificação por nomes, sinônimos, plurais e variações diacríticas."""
    info = matcher.match(query)
    assert isinstance(info, CurrencyInfo)
    assert info.code == expected_code


# ============================================================================
# 4. Testes com Ruídos, Espaços e Caracteres Especiais
# ============================================================================

@pytest.mark.unit
@pytest.mark.parametrize("noisy_query,expected_code", [
    ("   USD   ", "USD"),
    ("\n\t BRL \t\n", "BRL"),
    ("  $  ", "USD"),
    ("  r$  ", "BRL"),
    ("   dólar   ", "USD"),
    (" .btc. ", "BTC"),
    ("  #ETH  ", "ETH"),
])
def test_match_with_noise_and_whitespaces(matcher: CurrencyMatcher, noisy_query: str, expected_code: str):
    """Testa robustez de limpeza e sanitização de entradas com ruídos."""
    info = matcher.match(noisy_query)
    assert isinstance(info, CurrencyInfo)
    assert info.code == expected_code


# ============================================================================
# 5. Testes de Precedência Fiat vs Stablecoin / Desambiguação
# ============================================================================

@pytest.mark.unit
def test_fiat_precedence_over_stablecoin(matcher: CurrencyMatcher):
    """Garante que buscas por 'USD' ou 'dólar' resolvam para Fiat USD e não USDT."""
    usd_info = matcher.match("USD")
    assert usd_info.code == "USD"
    assert usd_info.asset_type == AssetType.FIAT

    dolar_info = matcher.match("dólar")
    assert dolar_info.code == "USD"
    assert dolar_info.asset_type == AssetType.FIAT

    usdt_info = matcher.match("USDT")
    assert usdt_info.code == "USDT"
    assert usdt_info.asset_type == AssetType.CRYPTO

    tether_info = matcher.match("tether")
    assert tether_info.code == "USDT"
    assert tether_info.asset_type == AssetType.CRYPTO


# ============================================================================
# 6. Testes de Entradas Inválidas ou Desconhecidas
# ============================================================================

@pytest.mark.unit
@pytest.mark.parametrize("invalid_query", [
    ("XYZNOTEXIST"),
    ("moeda_ficticia_123"),
    ("!@#$%^&*()_+"),
    (""),
    ("   "),
])
def test_match_invalid_queries(matcher: CurrencyMatcher, invalid_query: str):
    """Garante que entradas inválidas ou vazias retornem None ou levantem CurrencyNotFoundError."""
    # match_strict levanta exceção
    with pytest.raises(CurrencyNotFoundError):
        matcher.match_strict(invalid_query)

    # match padrão retorna None de forma graciosa
    result = matcher.match(invalid_query)
    assert result is None


# ============================================================================
# 7. Testes de Busca / Autocompletion (search)
# ============================================================================

@pytest.mark.unit
def test_search_currencies(matcher: CurrencyMatcher):
    """Testa a funcionalidade de autocompletion/busca para a UI e API."""
    results = matcher.search("dol", limit=5)
    codes = [r.code for r in results]
    assert "USD" in codes

    crypto_results = matcher.search("bit", limit=5)
    crypto_codes = [r.code for r in crypto_results]
    assert "BTC" in crypto_codes


# ============================================================================
# 8. Testes de Metadados e Códigos de País Associados
# ============================================================================

@pytest.mark.unit
def test_currency_metadata_country_codes(matcher: CurrencyMatcher):
    """Valida se as moedas principais contêm o código ISO-3 de país default para PPP."""
    brl = matcher.match("BRL")
    assert brl.default_country_code == "BRA"

    usd = matcher.match("USD")
    assert usd.default_country_code == "USA"

    eur = matcher.match("EUR")
    assert eur.default_country_code == "DEU"  # Representante padrão do bloco Euro

    gbp = matcher.match("GBP")
    assert gbp.default_country_code == "GBR"

    jpy = matcher.match("JPY")
    assert jpy.default_country_code == "JPN"

    btc = matcher.match("BTC")
    assert btc.default_country_code is None  # Criptoativo sem país soberano
