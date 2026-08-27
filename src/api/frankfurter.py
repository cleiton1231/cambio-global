"""
Módulo de Integração com a API Frankfurter (Zero Auth).

Responsabilidades:
- Obter cotações oficiais e atualizadas de moedas fiduciárias baseadas no Banco Central Europeu (BCE).
- Consultar séries temporais históricas para análise cambial.
- Listar moedas fiduciárias suportadas oficialmente.
"""

from decimal import Decimal
from typing import Any, Dict, List, Optional
import httpx

from src.api.base import BaseAPIClient
from src.models import ExchangeRate


class FrankfurterClient(BaseAPIClient):
    """Cliente HTTP para comunicação com a API Frankfurter (BCE)."""

    def __init__(
        self,
        base_url: str = "https://api.frankfurter.app",
        timeout: float = 10.0,
        client: Optional[httpx.AsyncClient] = None,
    ) -> None:
        super().__init__(
            base_url=base_url,
            service_name="Frankfurter",
            timeout=timeout,
            client=client,
        )

    async def get_latest_rates(
        self,
        base: str = "EUR",
        symbols: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Obtém as cotações mais recentes para a moeda base informada.
        Retorna dicionário contendo 'amount', 'base', 'date' e 'rates'.
        """
        params: Dict[str, Any] = {"base": base.upper()}
        if symbols:
            params["symbols"] = ",".join(s.upper() for s in symbols)

        data = await self._request("latest", params=params)
        return data

    async def get_rate(self, from_currency: str, to_currency: str) -> ExchangeRate:
        """
        Obtém a taxa de câmbio pontual entre duas moedas fiduciárias.
        """
        from_curr = from_currency.upper()
        to_curr = to_currency.upper()

        if from_curr == to_curr:
            return ExchangeRate(
                base_currency=from_curr,
                target_currency=to_curr,
                rate=Decimal("1.0"),
                source="frankfurter",
            )

        data = await self.get_latest_rates(base=from_curr, symbols=[to_curr])
        rates = data.get("rates", {})
        if to_curr not in rates:
            raise ValueError(f"Taxa para {to_curr} não encontrada na resposta do Frankfurter.")

        return ExchangeRate(
            base_currency=from_curr,
            target_currency=to_curr,
            rate=Decimal(str(rates[to_curr])),
            source="frankfurter",
        )

    async def get_historical_rates(
        self,
        start_date: str,
        end_date: str,
        base: str = "EUR",
        symbols: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Obtém séries temporais de taxas de câmbio para um intervalo de datas (YYYY-MM-DD..YYYY-MM-DD).
        """
        params: Dict[str, Any] = {"base": base.upper()}
        if symbols:
            params["symbols"] = ",".join(s.upper() for s in symbols)

        endpoint = f"{start_date}..{end_date}"
        return await self._request(endpoint, params=params)

    async def get_currencies(self) -> Dict[str, str]:
        """
        Retorna o dicionário de códigos ISO e nomes das moedas suportadas pelo Frankfurter.
        """
        return await self._request("currencies")
