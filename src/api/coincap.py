"""
Cliente para a API da CoinCap (v2).

Responsabilidades:
- Buscar cotações em tempo real de criptoativos e stablecoins (Zero Auth).
- Buscar ranking de criptoativos por market cap.
- Buscar séries históricas de preços diários para gráficos de tendência.
- Sanitização de IDs e proteção contra priceUsd nulo ou inválido.
"""

from decimal import Decimal
import re
from typing import Any, Dict, List, Optional
import httpx

from src.api.base import BaseAPIClient
from src.models import ExchangeRate


class CoinCapClient(BaseAPIClient):
    """Cliente para a API CoinCap v2 (Cotações de criptoativos em tempo real)."""

    _ASSET_REGEX = re.compile(r"^[A-Za-z0-9_-]{1,50}$")

    def __init__(
        self,
        base_url: str = "https://api.coincap.io/v2",
        timeout: float = 10.0,
        ttl_seconds: float = 30.0,  # 30s TTL para cripto
        max_stale_seconds: float = 3600.0,  # 1h tolerância stale
        client: Optional[httpx.AsyncClient] = None,
    ) -> None:
        super().__init__(
            base_url=base_url,
            service_name="CoinCap",
            timeout=timeout,
            ttl_seconds=ttl_seconds,
            max_stale_seconds=max_stale_seconds,
            client=client,
        )

        # Mapeamento de tickers comuns para slugs canônicos da CoinCap
        self._ticker_to_id = {
            "BTC": "bitcoin",
            "ETH": "ethereum",
            "SOL": "solana",
            "USDT": "tether",
            "BNB": "binance-coin",
            "XRP": "xrp",
            "ADA": "cardano",
            "DOGE": "dogecoin",
            "DOT": "polkadot",
            "AVAX": "avalanche",
            "LINK": "chainlink",
        }

    def _resolve_asset_id(self, asset_id_or_ticker: str) -> str:
        """Resolve ticker para o ID canônico da CoinCap com sanitização."""
        clean = str(asset_id_or_ticker).strip()
        key = clean.upper()
        resolved = self._ticker_to_id.get(key, clean.lower())
        if not self._ASSET_REGEX.match(resolved):
            raise ValueError(f"Identificador de criptoativo inválido: '{asset_id_or_ticker}'")
        return resolved

    async def get_asset(self, asset_id_or_ticker: str) -> Dict[str, Any]:
        """
        Obtém detalhes em tempo real de um criptoativo específico (ex: 'bitcoin' ou 'BTC').
        """
        asset_id = self._resolve_asset_id(asset_id_or_ticker)
        data = await self._request(f"assets/{asset_id}")
        return data.get("data", {}) if isinstance(data, dict) else {}

    async def get_assets(self, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Obtém a lista com ranking e cotações dos principais criptoativos.
        """
        params = {"limit": max(1, min(limit, 2000))}
        data = await self._request("assets", params=params)
        return data.get("data", []) if isinstance(data, dict) else []

    async def get_historical_rates(
        self,
        asset_id_or_ticker: str,
        interval: str = "d1",
        start_ms: Optional[int] = None,
        end_ms: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Obtém a série histórica de preços diários de um criptoativo.
        Endpoint: /assets/{id}/history?interval=d1
        """
        asset_id = self._resolve_asset_id(asset_id_or_ticker)
        params: Dict[str, Any] = {"interval": interval}
        if start_ms is not None:
            params["start"] = int(start_ms)
        if end_ms is not None:
            params["end"] = int(end_ms)

        data = await self._request(f"assets/{asset_id}/history", params=params)
        return data.get("data", []) if isinstance(data, dict) else []

    async def get_rate_usd(self, asset_id_or_ticker: str) -> Decimal:
        """
        Atalho para obter diretamente o preço em USD (Decimal) de um criptoativo.
        """
        rate_obj = await self.get_rate_in_usd(asset_id_or_ticker)
        return rate_obj.rate

    async def get_rate_in_usd(self, asset_id_or_ticker: str) -> ExchangeRate:
        """
        Obtém a cotação de um criptoativo em USD estruturada como ExchangeRate.
        """
        asset_data = await self.get_asset(asset_id_or_ticker)
        price_str = asset_data.get("priceUsd")
        if not price_str or not str(price_str).strip():
            raise ValueError(f"Preço indisponível para o ativo '{asset_id_or_ticker}' na CoinCap.")

        try:
            val = Decimal(str(price_str))
            if val <= 0:
                raise ValueError(f"Preço inválido (<= 0) para o ativo '{asset_id_or_ticker}'.")

            symbol = asset_data.get("symbol", asset_id_or_ticker).upper()
            return ExchangeRate(
                base_currency=symbol,
                target_currency="USD",
                rate=val,
                source="coincap",
                is_stale=self.last_response_stale,
            )
        except Exception as e:
            raise ValueError(f"Falha ao processar cotação cripto: {str(e)}")
