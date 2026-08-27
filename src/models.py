"""
Modelos canônicos de dados e exceções de domínio do Câmbio Global.

Contém definições de tipos, enums, dataclasses/schemas e hierarquia de exceções
utilizadas de ponta a ponta por todos os módulos do sistema.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Optional


# ============================================================================
# Enums e Tipos Canônicos
# ============================================================================

class AssetType(str, Enum):
    """Classificação do tipo de ativo financeiro."""
    FIAT = "fiat"
    CRYPTO = "crypto"


# ============================================================================
# Hierarquia de Exceções de Domínio
# ============================================================================

class CambioGlobalError(Exception):
    """Exceção base para todos os erros do sistema Câmbio Global."""
    pass


class CurrencyNotFoundError(CambioGlobalError):
    """Lançada quando uma moeda ou símbolo não pode ser identificada."""
    def __init__(self, query: str) -> None:
        super().__init__(f"Moeda ou símbolo não encontrado para a consulta: '{query}'")
        self.query = query


class AmbiguousCurrencyError(CambioGlobalError):
    """Lançada quando uma consulta de moeda resulta em múltiplos matches conflitantes."""
    def __init__(self, query: str, candidates: List[str]) -> None:
        cands_str = ", ".join(candidates)
        super().__init__(f"Consulta ambígua '{query}'. Candidatos possíveis: {cands_str}")
        self.query = query
        self.candidates = candidates


class UnsupportedPPPAssetError(CambioGlobalError):
    """Lançada ao tentar calcular PPP em ativos sem jurisdição nacional (ex: criptoativos)."""
    def __init__(self, asset_code: str) -> None:
        super().__init__(
            f"Ativo '{asset_code}' não possui índice de Paridade de Poder de Compra (PPP). "
            "PPP é aplicável apenas a economias nacionais e moedas fiduciárias registradas no Banco Mundial."
        )
        self.asset_code = asset_code


class InvalidExchangeRateError(CambioGlobalError):
    """Lançada quando a taxa de câmbio é inválida (<= 0 ou nula)."""
    def __init__(self, message: str = "Taxa de câmbio inválida ou menor/igual a zero.") -> None:
        super().__init__(message)


class APIError(CambioGlobalError):
    """Exceção base para erros em integrações com APIs externas."""
    def __init__(self, service: str, message: str, status_code: Optional[int] = None) -> None:
        self.service = service
        self.status_code = status_code
        super().__init__(f"[{service}] {message} (Status: {status_code})")


class APIConnectionError(APIError):
    """Erro de conectividade, timeout ou falha de rede ao acessar API externa."""
    def __init__(self, service: str, message: str = "Falha de conexão ou timeout ao acessar o serviço externo.") -> None:
        super().__init__(service=service, message=message, status_code=None)


class APIRateLimitError(APIError):
    """Erro de limite de requisições (HTTP 429) excedido."""
    def __init__(self, service: str) -> None:
        super().__init__(service=service, message="Limite de requisições excedido. Tente novamente mais tarde.", status_code=429)


class APIResponseError(APIError):
    """Erro de resposta inesperada ou status 4xx/5xx retornado pela API."""
    pass


# ============================================================================
# Modelos de Dados (Dataclasses Tipadas)
# ============================================================================

@dataclass
class CurrencyInfo:
    """Informações cadastrais e metadados de uma moeda ou criptoativo."""
    code: str                               # Código canônico (ex: BRL, USD, BTC)
    name: str                               # Nome oficial em português (ex: Real Brasileiro, Bitcoin)
    name_en: str                            # Nome oficial em inglês (ex: Brazilian Real, Bitcoin)
    symbol: str                             # Símbolo usual (ex: R$, $, ₿)
    asset_type: AssetType                   # Tipo de ativo: FIAT ou CRYPTO
    decimals: int = 2                       # Quantidade padrão de casas decimais para exibição
    default_country_code: Optional[str] = None  # Código ISO-3 do país principal (ex: BRA, USA, DEU)
    aliases: List[str] = field(default_factory=list)  # Sinônimos, plurais e variações para matching

    def to_dict(self) -> Dict[str, Any]:
        """Converte a instância para dicionário serializável."""
        return {
            "code": self.code,
            "name": self.name,
            "name_en": self.name_en,
            "symbol": self.symbol,
            "asset_type": self.asset_type.value,
            "decimals": self.decimals,
            "default_country_code": self.default_country_code,
            "aliases": self.aliases,
        }


@dataclass
class ExchangeRate:
    """Representação de uma taxa de câmbio pontual entre dois ativos."""
    base_currency: str
    target_currency: str
    rate: Decimal
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    source: str = "frankfurter"
    is_stale: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "base_currency": self.base_currency,
            "target_currency": self.target_currency,
            "rate": float(self.rate),
            "timestamp": self.timestamp.isoformat(),
            "source": self.source,
            "is_stale": self.is_stale,
        }


@dataclass
class ConversionResult:
    """Resultado completo de uma conversão de valores entre duas moedas."""
    amount_from: Decimal
    currency_from: str
    amount_to: Decimal
    currency_to: str
    rate: Decimal
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    source: str = "direct"
    is_stale: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "amount_from": float(self.amount_from),
            "currency_from": self.currency_from,
            "amount_to": float(self.amount_to),
            "currency_to": self.currency_to,
            "rate": float(self.rate),
            "timestamp": self.timestamp.isoformat(),
            "source": self.source,
            "is_stale": self.is_stale,
        }


@dataclass
class PPPResult:
    """Resultado da análise comparativa de Paridade de Poder de Compra."""
    country_from: str                       # Código ISO-3 do país de origem
    country_to: str                         # Código ISO-3 do país de destino
    currency_from: str                      # Moeda de origem
    currency_to: str                        # Moeda de destino
    ppp_factor_from: Decimal                # Fator PPP do país de origem (Banco Mundial)
    ppp_factor_to: Decimal                  # Fator PPP do país de destino (Banco Mundial)
    nominal_rate: Decimal                   # Taxa de câmbio nominal de mercado
    ppp_rate: Decimal                       # Taxa teórica de câmbio em PPP
    price_level_ratio: Decimal              # Razão do nível de preços relativo (PLR = PPP / Nominal)
    nominal_amount_to: Decimal              # Valor convertido nominalmente
    ppp_equivalent_amount: Decimal          # Poder de compra equivalente no destino
    year: int                               # Ano de referência do indicador do Banco Mundial

    def to_dict(self) -> Dict[str, Any]:
        return {
            "country_from": self.country_from,
            "country_to": self.country_to,
            "currency_from": self.currency_from,
            "currency_to": self.currency_to,
            "ppp_factor_from": float(self.ppp_factor_from),
            "ppp_factor_to": float(self.ppp_factor_to),
            "nominal_rate": float(self.nominal_rate),
            "ppp_rate": float(self.ppp_rate),
            "price_level_ratio": float(self.price_level_ratio),
            "nominal_amount_to": float(self.nominal_amount_to),
            "ppp_equivalent_amount": float(self.ppp_equivalent_amount),
            "year": self.year,
        }


@dataclass
class ConversionRecord:
    """Registro histórico de conversão para persistência em arquivo."""
    id: str
    timestamp: str
    from_currency: str
    to_currency: str
    amount_from: float
    amount_to: float
    rate: float
    ppp_equivalent: Optional[float] = None
    country_from: Optional[str] = None
    country_to: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "timestamp": self.timestamp,
            "from_currency": self.from_currency,
            "to_currency": self.to_currency,
            "amount_from": self.amount_from,
            "amount_to": self.amount_to,
            "rate": self.rate,
            "ppp_equivalent": self.ppp_equivalent,
            "country_from": self.country_from,
            "country_to": self.country_to,
        }


# ============================================================================
# Modelos para Séries Temporais e Tendências (Item 2)
# ============================================================================

@dataclass
class TrendPoint:
    """Ponto de uma série temporal de cotações."""
    date: str
    rate: Decimal

    def to_dict(self) -> Dict[str, Any]:
        return {
            "date": self.date,
            "rate": float(self.rate),
        }


@dataclass
class TrendAnalysis:
    """Resultado da análise de tendência cambial e volatilidade."""
    base_currency: str
    target_currency: str
    days: int
    points: List[TrendPoint]
    start_rate: Decimal
    end_rate: Decimal
    min_rate: Decimal
    max_rate: Decimal
    avg_rate: Decimal
    change_pct: Decimal
    sparkline: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "base_currency": self.base_currency,
            "target_currency": self.target_currency,
            "days": self.days,
            "points": [p.to_dict() for p in self.points],
            "start_rate": float(self.start_rate),
            "end_rate": float(self.end_rate),
            "min_rate": float(self.min_rate),
            "max_rate": float(self.max_rate),
            "avg_rate": float(self.avg_rate),
            "change_pct": float(self.change_pct),
            "sparkline": self.sparkline,
        }


# ============================================================================
# Modelos para Cesta de Moedas / Basket Converter (Item 3)
# ============================================================================

@dataclass
class BasketItemResult:
    """Resultado da conversão de um item individual dentro de uma cesta."""
    currency_to: str
    amount_to: Optional[Decimal] = None
    rate: Optional[Decimal] = None
    is_stale: bool = False
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "currency_to": self.currency_to,
            "amount_to": float(self.amount_to) if self.amount_to is not None else None,
            "rate": float(self.rate) if self.rate is not None else None,
            "is_stale": self.is_stale,
            "error": self.error,
        }


@dataclass
class BasketResult:
    """Resultado agregado de conversão de cesta de moedas."""
    amount_from: Decimal
    currency_from: str
    items: List[BasketItemResult]
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "amount_from": float(self.amount_from),
            "currency_from": self.currency_from,
            "items": [item.to_dict() for item in self.items],
            "timestamp": self.timestamp.isoformat(),
        }
