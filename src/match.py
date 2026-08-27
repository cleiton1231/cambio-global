"""
Motor Crítico de Matching e Normalização de Moedas, Símbolos e Tickers.

Implementa a resolução determinística de moedas fiduciárias e criptoativos
conforme especificado na governança (GEMINI.md).
"""

import re
import unicodedata
from typing import Dict, List, Optional

from src.models import (
    AssetType,
    CurrencyInfo,
    CurrencyNotFoundError,
    AmbiguousCurrencyError,
)


# ============================================================================
# Base de Dados Canônica de Moedas e Criptoativos
# ============================================================================

CANONICAL_CURRENCIES: List[CurrencyInfo] = [
    # --- Moedas Fiduciárias (ISO 4217) ---
    CurrencyInfo(
        code="BRL",
        name="Real Brasileiro",
        name_en="Brazilian Real",
        symbol="R$",
        asset_type=AssetType.FIAT,
        decimals=2,
        default_country_code="BRA",
        aliases=["real", "reais", "brl", "r$", "brazilian real", "real do brasil"]
    ),
    CurrencyInfo(
        code="USD",
        name="Dólar Americano",
        name_en="US Dollar",
        symbol="$",
        asset_type=AssetType.FIAT,
        decimals=2,
        default_country_code="USA",
        aliases=["dolar", "dolares", "dólar", "dólares", "dolar americano", "dólar americano", "dollar", "dollars", "us dollar", "usd", "$", "us$", "dolar dos eua"]
    ),
    CurrencyInfo(
        code="EUR",
        name="Euro",
        name_en="Euro",
        symbol="€",
        asset_type=AssetType.FIAT,
        decimals=2,
        default_country_code="DEU",  # Principal economia do bloco Euro
        aliases=["euro", "euros", "eur", "€", "european euro"]
    ),
    CurrencyInfo(
        code="GBP",
        name="Libra Esterlina",
        name_en="British Pound",
        symbol="£",
        asset_type=AssetType.FIAT,
        decimals=2,
        default_country_code="GBR",
        aliases=["libra", "libras", "libra esterlina", "pound", "pounds", "british pound", "gbp", "£", "sterling"]
    ),
    CurrencyInfo(
        code="JPY",
        name="Iene Japonês",
        name_en="Japanese Yen",
        symbol="¥",
        asset_type=AssetType.FIAT,
        decimals=0,
        default_country_code="JPN",
        aliases=["iene", "ienes", "yen", "yens", "japanese yen", "jpy", "¥"]
    ),
    CurrencyInfo(
        code="CAD",
        name="Dólar Canadense",
        name_en="Canadian Dollar",
        symbol="C$",
        asset_type=AssetType.FIAT,
        decimals=2,
        default_country_code="CAN",
        aliases=["dolar canadense", "dólar canadense", "canadian dollar", "cad", "c$"]
    ),
    CurrencyInfo(
        code="AUD",
        name="Dólar Australiano",
        name_en="Australian Dollar",
        symbol="A$",
        asset_type=AssetType.FIAT,
        decimals=2,
        default_country_code="AUS",
        aliases=["dolar australiano", "dólar australiano", "australian dollar", "aud", "a$"]
    ),
    CurrencyInfo(
        code="CHF",
        name="Franco Suíço",
        name_en="Swiss Franc",
        symbol="CHF",
        asset_type=AssetType.FIAT,
        decimals=2,
        default_country_code="CHE",
        aliases=["franco", "francos", "franco suico", "franco suíço", "swiss franc", "chf"]
    ),
    CurrencyInfo(
        code="CNY",
        name="Yuan Chinês",
        name_en="Chinese Yuan",
        symbol="¥",
        asset_type=AssetType.FIAT,
        decimals=2,
        default_country_code="CHN",
        aliases=["yuan", "yuan chines", "yuan chinês", "chinese yuan", "renminbi", "cny", "rmb"]
    ),
    CurrencyInfo(
        code="ARS",
        name="Peso Argentino",
        name_en="Argentine Peso",
        symbol="$",
        asset_type=AssetType.FIAT,
        decimals=2,
        default_country_code="ARG",
        aliases=["peso argentino", "pesos argentinos", "argentine peso", "ars"]
    ),
    CurrencyInfo(
        code="CLP",
        name="Peso Chileno",
        name_en="Chilean Peso",
        symbol="$",
        asset_type=AssetType.FIAT,
        decimals=0,
        default_country_code="CHL",
        aliases=["peso chileno", "pesos chilenos", "chilean peso", "clp"]
    ),
    CurrencyInfo(
        code="MXN",
        name="Peso Mexicano",
        name_en="Mexican Peso",
        symbol="$",
        asset_type=AssetType.FIAT,
        decimals=2,
        default_country_code="MEX",
        aliases=["peso mexicano", "pesos mexicanos", "mexican peso", "mxn"]
    ),
    CurrencyInfo(
        code="SEK",
        name="Coroa Sueca",
        name_en="Swedish Krona",
        symbol="kr",
        asset_type=AssetType.FIAT,
        decimals=2,
        default_country_code="SWE",
        aliases=["coroa sueca", "coroas suecas", "swedish krona", "sek", "kr"]
    ),
    CurrencyInfo(
        code="NOK",
        name="Coroa Norueguesa",
        name_en="Norwegian Krone",
        symbol="kr",
        asset_type=AssetType.FIAT,
        decimals=2,
        default_country_code="NOR",
        aliases=["coroa norueguesa", "norwegian krone", "nok"]
    ),
    CurrencyInfo(
        code="DKK",
        name="Coroa Dinamarquesa",
        name_en="Danish Krone",
        symbol="kr",
        asset_type=AssetType.FIAT,
        decimals=2,
        default_country_code="DNK",
        aliases=["coroa dinamarquesa", "danish krone", "dkk"]
    ),
    CurrencyInfo(
        code="INR",
        name="Rúpia Indiana",
        name_en="Indian Rupee",
        symbol="₹",
        asset_type=AssetType.FIAT,
        decimals=2,
        default_country_code="IND",
        aliases=["rupia", "rupias", "rupia indiana", "indian rupee", "inr", "₹"]
    ),
    CurrencyInfo(
        code="KRW",
        name="Won Sul-Coreano",
        name_en="South Korean Won",
        symbol="₩",
        asset_type=AssetType.FIAT,
        decimals=0,
        default_country_code="KOR",
        aliases=["won", "won sul coreano", "south korean won", "krw", "₩"]
    ),
    CurrencyInfo(
        code="TRY",
        name="Lira Turca",
        name_en="Turkish Lira",
        symbol="₺",
        asset_type=AssetType.FIAT,
        decimals=2,
        default_country_code="TUR",
        aliases=["lira", "liras", "lira turca", "turkish lira", "try", "₺"]
    ),
    CurrencyInfo(
        code="NZD",
        name="Dólar Neozelandês",
        name_en="New Zealand Dollar",
        symbol="NZ$",
        asset_type=AssetType.FIAT,
        decimals=2,
        default_country_code="NZL",
        aliases=["dolar neozelandes", "dólar neozelandês", "new zealand dollar", "nzd", "nz$"]
    ),
    CurrencyInfo(
        code="ZAR",
        name="Rand Sul-Africano",
        name_en="South African Rand",
        symbol="R",
        asset_type=AssetType.FIAT,
        decimals=2,
        default_country_code="ZAF",
        aliases=["rand", "rand sul africano", "south african rand", "zar"]
    ),
    CurrencyInfo(
        code="SGD",
        name="Dólar de Singapura",
        name_en="Singapore Dollar",
        symbol="S$",
        asset_type=AssetType.FIAT,
        decimals=2,
        default_country_code="SGP",
        aliases=["dolar de singapura", "dólar de singapura", "singapore dollar", "sgd", "s$"]
    ),
    CurrencyInfo(
        code="HKD",
        name="Dólar de Hong Kong",
        name_en="Hong Kong Dollar",
        symbol="HK$",
        asset_type=AssetType.FIAT,
        decimals=2,
        default_country_code="HKG",
        aliases=["dolar de hong kong", "dólar de hong kong", "hong kong dollar", "hkd", "hk$"]
    ),
    CurrencyInfo(
        code="PLN",
        name="Zloty Polonês",
        name_en="Polish Zloty",
        symbol="zł",
        asset_type=AssetType.FIAT,
        decimals=2,
        default_country_code="POL",
        aliases=["zloty", "zloty polones", "zloty polonês", "polish zloty", "pln", "zł"]
    ),
    CurrencyInfo(
        code="ILS",
        name="Novo Shekel Israelense",
        name_en="Israeli New Shekel",
        symbol="₪",
        asset_type=AssetType.FIAT,
        decimals=2,
        default_country_code="ISR",
        aliases=["shekel", "novo shekel", "israeli shekel", "ils", "₪"]
    ),

    # --- Criptoativos ---
    CurrencyInfo(
        code="BTC",
        name="Bitcoin",
        name_en="Bitcoin",
        symbol="₿",
        asset_type=AssetType.CRYPTO,
        decimals=8,
        default_country_code=None,
        aliases=["bitcoin", "bitcoins", "btc", "₿"]
    ),
    CurrencyInfo(
        code="ETH",
        name="Ethereum",
        name_en="Ethereum",
        symbol="Ξ",
        asset_type=AssetType.CRYPTO,
        decimals=8,
        default_country_code=None,
        aliases=["ethereum", "ether", "eth", "Ξ"]
    ),
    CurrencyInfo(
        code="SOL",
        name="Solana",
        name_en="Solana",
        symbol="SOL",
        asset_type=AssetType.CRYPTO,
        decimals=8,
        default_country_code=None,
        aliases=["solana", "sol"]
    ),
    CurrencyInfo(
        code="USDT",
        name="Tether USD",
        name_en="Tether USD",
        symbol="USDT",
        asset_type=AssetType.CRYPTO,
        decimals=2,
        default_country_code=None,
        aliases=["tether", "usdt", "tether usd"]
    ),
    CurrencyInfo(
        code="BNB",
        name="BNB / Binance Coin",
        name_en="Binance Coin",
        symbol="BNB",
        asset_type=AssetType.CRYPTO,
        decimals=8,
        default_country_code=None,
        aliases=["binance coin", "bnb"]
    ),
    CurrencyInfo(
        code="XRP",
        name="XRP / Ripple",
        name_en="XRP",
        symbol="XRP",
        asset_type=AssetType.CRYPTO,
        decimals=6,
        default_country_code=None,
        aliases=["ripple", "xrp"]
    ),
    CurrencyInfo(
        code="ADA",
        name="Cardano",
        name_en="Cardano",
        symbol="ADA",
        asset_type=AssetType.CRYPTO,
        decimals=6,
        default_country_code=None,
        aliases=["cardano", "ada"]
    ),
    CurrencyInfo(
        code="DOGE",
        name="Dogecoin",
        name_en="Dogecoin",
        symbol="Ð",
        asset_type=AssetType.CRYPTO,
        decimals=4,
        default_country_code=None,
        aliases=["dogecoin", "doge", "Ð"]
    ),
    CurrencyInfo(
        code="DOT",
        name="Polkadot",
        name_en="Polkadot",
        symbol="DOT",
        asset_type=AssetType.CRYPTO,
        decimals=6,
        default_country_code=None,
        aliases=["polkadot", "dot"]
    ),
    CurrencyInfo(
        code="AVAX",
        name="Avalanche",
        name_en="Avalanche",
        symbol="AVAX",
        asset_type=AssetType.CRYPTO,
        decimals=8,
        default_country_code=None,
        aliases=["avalanche", "avax"]
    ),
    CurrencyInfo(
        code="LINK",
        name="Chainlink",
        name_en="Chainlink",
        symbol="LINK",
        asset_type=AssetType.CRYPTO,
        decimals=6,
        default_country_code=None,
        aliases=["chainlink", "link"]
    ),
]


# ============================================================================
# Funções Utilitárias de Normalização
# ============================================================================

def normalize_text(text: str) -> str:
    """
    Normaliza texto removendo acentos, convertendo para minúsculas
    e limpando espaços extras e pontuação desnecessária.
    """
    if not text:
        return ""
    # Decomposição Unicode NFKD para separar caracteres base de acentos
    nfkd = unicodedata.normalize("NFKD", text)
    without_accents = "".join(c for c in nfkd if not unicodedata.combining(c))
    
    # Preserva símbolos monetários especiais comuns
    allowed_symbols = r"[$€£¥₿Ξ₹₩₺₽₪złÐ]"
    
    # Limpa ruídos mas mantém símbolos monetários e letras/números
    cleaned = re.sub(rf"[^\w\s{allowed_symbols}]", " ", without_accents, flags=re.UNICODE)
    cleaned = re.sub(r"\s+", " ", cleaned).strip().lower()
    return cleaned


# ============================================================================
# Motor de Matching
# ============================================================================

class CurrencyMatcher:
    """Motor de resolução e mapeamento determinístico de moedas."""

    def __init__(self, currencies: Optional[List[CurrencyInfo]] = None) -> None:
        self.currencies = currencies or CANONICAL_CURRENCIES
        self._by_code: Dict[str, CurrencyInfo] = {}
        self._by_symbol: Dict[str, CurrencyInfo] = {}
        self._by_alias: Dict[str, CurrencyInfo] = {}

        self._build_indexes()

    def _build_indexes(self) -> None:
        """Constrói índices de busca rápida em memória."""
        # 1. Indexação por código ISO / Ticker
        for curr in self.currencies:
            self._by_code[curr.code.upper()] = curr

        # 2. Resolução determinística de símbolos (Precedência Canônica)
        symbol_precedence = {
            "r$": "BRL",
            "$": "USD",
            "us$": "USD",
            "€": "EUR",
            "£": "GBP",
            "¥": "JPY",
            "c$": "CAD",
            "a$": "AUD",
            "nz$": "NZD",
            "s$": "SGD",
            "hk$": "HKD",
            "kr": "SEK",
            "₹": "INR",
            "₩": "KRW",
            "₺": "TRY",
            "zł": "PLN",
            "₪": "ILS",
            "₿": "BTC",
            "Ξ": "ETH",
            "Ð": "DOGE",
        }
        for sym_str, code in symbol_precedence.items():
            if code in self._by_code:
                self._by_symbol[sym_str.lower()] = self._by_code[code]

        # 3. Indexação por aliases normalizados
        for curr in self.currencies:
            # Nome canônico
            norm_name = normalize_text(curr.name)
            norm_name_en = normalize_text(curr.name_en)
            if norm_name:
                self._by_alias[norm_name] = curr
            if norm_name_en:
                self._by_alias[norm_name_en] = curr

            # Aliases registrados
            for alias in curr.aliases:
                norm_alias = normalize_text(alias)
                if norm_alias and norm_alias not in self._by_alias:
                    self._by_alias[norm_alias] = curr

    def match(self, query: str) -> Optional[CurrencyInfo]:
        """
        Resolve uma query de moeda para seu CurrencyInfo canônico.
        Retorna None se a moeda não for identificada.
        """
        if not query or not isinstance(query, str):
            return None

        trimmed = query.strip()
        if not trimmed:
            return None

        # 1. Match Exato de Código ISO / Ticker (case-insensitive)
        upper_code = trimmed.upper()
        # Tratamento especial para limpar pontuação em volta do ticker (ex: .btc. -> BTC)
        clean_code = re.sub(r"^[^\w]+|[^\w]+$", "", upper_code)
        if clean_code in self._by_code:
            return self._by_code[clean_code]

        # 2. Match de Símbolo Direto (ex: "R$", "$", "€", "  $  ")
        lower_sym = trimmed.lower()
        if lower_sym in self._by_symbol:
            return self._by_symbol[lower_sym]

        # 3. Match de Nome Normalizado / Alias
        normalized = normalize_text(trimmed)
        if not normalized:
            return None

        if normalized in self._by_code:
            return self._by_code[normalized.upper()]

        if normalized in self._by_symbol:
            return self._by_symbol[normalized]

        if normalized in self._by_alias:
            return self._by_alias[normalized]

        # 4. Fallback de desambiguação por prefixo / palavra
        for alias_key, curr in self._by_alias.items():
            if alias_key == normalized:
                return curr

        return None

    def match_strict(self, query: str) -> CurrencyInfo:
        """
        Resolve uma query de moeda de forma estrita.
        Lança CurrencyNotFoundError se não for encontrada.
        """
        result = self.match(query)
        if result is None:
            raise CurrencyNotFoundError(query)
        return result

    def search(self, text: str, limit: int = 5) -> List[CurrencyInfo]:
        """
        Busca moedas e criptos correspondentes por prefixo ou substring
        para autocompletion na CLI e na Web UI.
        """
        if not text or not isinstance(text, str):
            return []

        norm = normalize_text(text)
        if not norm:
            return []

        matched: List[CurrencyInfo] = []
        seen_codes = set()

        # 1. Códigos que começam com o texto
        for code, curr in self._by_code.items():
            if code.lower().startswith(norm) and code not in seen_codes:
                matched.append(curr)
                seen_codes.add(code)
                if len(matched) >= limit:
                    return matched

        # 2. Nomes ou aliases que começam com o texto
        for alias_key, curr in self._by_alias.items():
            if alias_key.startswith(norm) and curr.code not in seen_codes:
                matched.append(curr)
                seen_codes.add(curr.code)
                if len(matched) >= limit:
                    return matched

        # 3. Substring nos nomes
        for alias_key, curr in self._by_alias.items():
            if norm in alias_key and curr.code not in seen_codes:
                matched.append(curr)
                seen_codes.add(curr.code)
                if len(matched) >= limit:
                    return matched

        return matched


# Instância singleton do motor de matching
_GLOBAL_MATCHER: Optional[CurrencyMatcher] = None


def get_matcher() -> CurrencyMatcher:
    """Retorna a instância singleton do CurrencyMatcher."""
    global _GLOBAL_MATCHER
    if _GLOBAL_MATCHER is None:
        _GLOBAL_MATCHER = CurrencyMatcher()
    return _GLOBAL_MATCHER
