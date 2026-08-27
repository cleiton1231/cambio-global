"""
Motor Estatístico de Análise de Tendências Cambiais e Gerador de Sparklines.

Responsabilidades:
- Gerar visualizações Sparkline Unicode ( ▂▃▄▅▆▇█) seguras contra divisão por zero.
- Analisar séries temporais históricas diárias (últimos 7, 30, 90 dias) para Fiat e Cripto.
- Calcular métricas de variação percentual, mínima, máxima e média.
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import List, Optional

from src.api.coincap import CoinCapClient
from src.api.frankfurter import FrankfurterClient
from src.match import CurrencyMatcher, get_matcher
from src.models import (
    AssetType,
    CurrencyNotFoundError,
    TrendAnalysis,
    TrendPoint,
)

SPARK_BLOCKS = [" ", "▂", "▃", "▄", "▅", "▆", "▇", "█"]


def generate_sparkline(values: List[Decimal]) -> str:
    """
    Gera uma linha sparkline em caracteres Unicode para uma série de valores decimais.
    Possui proteção contra divisão por zero em séries flat e tratamento de borda.
    """
    if not values:
        return ""

    if len(values) == 1:
        return SPARK_BLOCKS[3]

    min_val = min(values)
    max_val = max(values)

    # Proteção de divisão por zero para séries constantes / flat
    if min_val == max_val:
        return SPARK_BLOCKS[3] * len(values)

    span = max_val - min_val
    num_blocks = len(SPARK_BLOCKS) - 1

    chars: List[str] = []
    for val in values:
        ratio = float((val - min_val) / span)
        idx = min(num_blocks, max(0, int(round(ratio * num_blocks))))
        chars.append(SPARK_BLOCKS[idx])

    return "".join(chars)


class CurrencyTrendAnalyzer:
    """Analisador de séries temporais e tendências de câmbio."""

    def __init__(
        self,
        matcher: Optional[CurrencyMatcher] = None,
        frankfurter: Optional[FrankfurterClient] = None,
        coincap: Optional[CoinCapClient] = None,
    ) -> None:
        self.matcher = matcher or get_matcher()
        self.frankfurter = frankfurter or FrankfurterClient()
        self.coincap = coincap or CoinCapClient()

    async def analyze_trend(
        self,
        from_currency: str,
        to_currency: str,
        days: int = 30,
    ) -> TrendAnalysis:
        """
        Analisa a tendência cambial e gera métricas e sparklines para o período.
        """
        if days < 2:
            raise ValueError(f"O período em dias deve ser de no mínimo 2. Informado: {days}")

        from_info = self.matcher.match_strict(from_currency)
        to_info = self.matcher.match_strict(to_currency)

        points: List[TrendPoint] = []

        # 1. Caso Fiat <-> Fiat (via Frankfurter)
        if from_info.asset_type == AssetType.FIAT and to_info.asset_type == AssetType.FIAT:
            end_d = datetime.now(timezone.utc).date()
            start_d = end_d - timedelta(days=days)

            data = await self.frankfurter.get_historical_rates(
                start_date=start_d.isoformat(),
                end_date=end_d.isoformat(),
                base=from_info.code,
                symbols=[to_info.code],
            )

            rates_map = data.get("rates", {})
            for d_str in sorted(rates_map.keys()):
                entry = rates_map[d_str]
                if to_info.code in entry:
                    points.append(TrendPoint(date=d_str, rate=Decimal(str(entry[to_info.code]))))

        # 2. Caso Cripto -> USD (via CoinCap)
        elif from_info.asset_type == AssetType.CRYPTO and to_info.code == "USD":
            raw_history = await self.coincap.get_historical_rates(from_info.code, interval="d1")
            selected_entries = raw_history[-days:] if len(raw_history) >= days else raw_history
            for entry in selected_entries:
                t_ms = entry.get("time", 0)
                d_str = datetime.fromtimestamp(t_ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
                price_dec = Decimal(str(entry.get("priceUsd", "0")))
                points.append(TrendPoint(date=d_str, rate=price_dec))

        # 3. Caso Cripto -> Outro Fiat (ex: BTC -> BRL)
        elif from_info.asset_type == AssetType.CRYPTO and to_info.asset_type == AssetType.FIAT:
            raw_history = await self.coincap.get_historical_rates(from_info.code, interval="d1")
            selected_entries = raw_history[-days:] if len(raw_history) >= days else raw_history
            
            # Obtém taxa atual USD -> Fiat para conversão aproximada
            usd_fiat = await self.frankfurter.get_rate("USD", to_info.code)

            for entry in selected_entries:
                t_ms = entry.get("time", 0)
                d_str = datetime.fromtimestamp(t_ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
                price_usd = Decimal(str(entry.get("priceUsd", "0")))
                price_fiat = price_usd * usd_fiat.rate
                points.append(TrendPoint(date=d_str, rate=price_fiat))

        if not points:
            raise ValueError(f"Não foram encontrados dados históricos suficientes para {from_info.code}/{to_info.code}.")

        rates = [p.rate for p in points]
        start_rate = rates[0]
        end_rate = rates[-1]
        min_rate = min(rates)
        max_rate = max(rates)
        avg_rate = sum(rates) / len(rates)

        if start_rate > 0:
            change_pct = ((end_rate - start_rate) / start_rate) * Decimal("100")
        else:
            change_pct = Decimal("0")

        sparkline = generate_sparkline(rates)

        return TrendAnalysis(
            base_currency=from_info.code,
            target_currency=to_info.code,
            days=days,
            points=points,
            start_rate=start_rate,
            end_rate=end_rate,
            min_rate=min_rate,
            max_rate=max_rate,
            avg_rate=avg_rate,
            change_pct=change_pct,
            sparkline=sparkline,
        )
