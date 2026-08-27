"""
Módulo de Integração com a API CoinCap v2 (Zero Auth).

Responsabilidades:
- Obter cotações em tempo real de criptoativos em USD.
- Consultar ranking e volume de mercado de criptomoedas.
- Listar taxas de conversão de ativos relativas ao USD.
"""

from decimal import Decimal
from typing import Any, Dict, List, Optional
import httpx

from src.api.base import BaseAPIClient
from src.models import ExchangeRate


class CoinCapClient(BaseAPIClient):
    """Cliente HTTP para comunicação com a API CoinCap v2."""

    def __init__(
        self,
        base_url: str = "https://api.coincap.io/v2",
        timeout: float = 10.0,
        client: Optional[httpx.AsyncClient] = None,
    ) -> None:
        super().__init__(
            base_url=base_url,
            service_name="CoinCap",
            timeout=timeout,
            client=client,
        )

        # Mapeamento estático de Ticker -> Asset ID para CoinCap
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

    async def get_asset(self, asset_id_or_ticker: str) -> Dict[str, Any]:
        """
        Obtém detalhes em tempo real de um criptoativo específico (ex: 'bitcoin' ou 'BTC').
        """
        key = asset_id_or_ticker.upper()
        asset_id = self._ticker_to_id.get(key, asset_id_or_ticker.lower())

        data = await self._request(f"assets/{asset_id}")
        return data.get("data", {})

    async def get_assets(self, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Obtém a lista com ranking e cotações dos principais criptoativos.
        """
        params = {"limit": min(limit, 2000)}
        data = await self._request("assets", params=params)
        return data.get("data", [])

    async def get_rate_in_usd(self, ticker: str) -> ExchangeRate:
        """
        Obtém a cotação pontual de um criptoativo em USD (preço USD por 1 unidade da cripto).
        """
        data = await self.get_asset(ticker)
        price_usd_str = data.get("priceUsd")
        if not price_usd_str:
            raise ValueError(f"Preço em USD não encontrado para {ticker} na CoinCap.")

        return ExchangeRate(
            base_currency=ticker.upper(),
            target_currency="USD",
            rate=Decimal(str(price_usd_str)),
            source="coincap",
        )

    async def get_rates(self) -> List[Dict[str, Any]]:
        """
        Obtém a lista completa de taxas relativas ao USD providas pela CoinCap.
        """
        data = await self._request("rates")
        return data.get("data", [])
