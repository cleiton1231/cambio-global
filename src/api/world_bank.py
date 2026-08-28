"""
Cliente para a API do Banco Mundial (World Bank Indicator API).

Responsabilidades:
- Buscar indicador de Paridade de Poder de Compra (PPP): PA.NUS.PPP (PPP conversion factor, GDP).
- Buscar indicadores complementares (PIB per capita, inflação, etc.).
- Validação e sanitização estrita de código de país.
- Tratamento de mensagens de erro encapsuladas em status HTTP 200.
"""

from decimal import Decimal
import re
from typing import Any, Dict, List, Optional
import httpx

from src.api.base import BaseAPIClient


class WorldBankClient(BaseAPIClient):
    """Cliente para a API v2 do Banco Mundial (Sem autenticação)."""

    _COUNTRY_REGEX = re.compile(r"^[A-Za-z0-9_-]{2,10}$")

    def __init__(
        self,
        base_url: str = "https://api.worldbank.org/v2",
        timeout: float = 10.0,
        ttl_seconds: float = 86400.0,  # 24h para dados anuais do Banco Mundial
        max_stale_seconds: float = 604800.0,  # 7 dias tolerância stale
        client: Optional[httpx.AsyncClient] = None,
    ) -> None:
        super().__init__(
            base_url=base_url,
            service_name="WorldBank",
            timeout=timeout,
            ttl_seconds=ttl_seconds,
            max_stale_seconds=max_stale_seconds,
            client=client,
        )

    def _sanitize_country_code(self, country_code: str) -> Optional[str]:
        """Sanitiza o código do país contra injeção de rotas."""
        if not country_code or not isinstance(country_code, str):
            return None
        clean = country_code.strip().upper()
        if not self._COUNTRY_REGEX.match(clean):
            return None
        return clean

    async def get_ppp_conversion_factor(self, country_code: str) -> Optional[Dict[str, Any]]:
        """
        Obtém o fator de conversão de PPP mais recente (PA.NUS.PPP) para um país ISO-2 ou ISO-3.
        Retorna dicionário com: country, country_id, indicator, year, value (Decimal).
        """
        country = self._sanitize_country_code(country_code)
        if not country:
            return None

        params = {
            "format": "json",
            "per_page": 10,
        }
        endpoint = f"country/{country}/indicator/PA.NUS.PPP"
        data = await self._request(endpoint, params=params)

        # Validação contra resposta de erro do Banco Mundial (retornada com status 200 OK)
        if isinstance(data, list) and len(data) > 0 and isinstance(data[0], dict) and "message" in data[0]:
            return None

        if not isinstance(data, list) or len(data) < 2 or not isinstance(data[1], list):
            return None

        entries: List[Dict[str, Any]] = data[1]
        for entry in entries:
            val = entry.get("value")
            if val is not None:
                return {
                    "country": entry.get("country", {}).get("value", country),
                    "country_id": entry.get("countryiso3code", country),
                    "indicator": "PA.NUS.PPP",
                    "year": int(entry.get("date", 0)),
                    "value": Decimal(str(val)),
                }

        return None

    async def get_gdp_per_capita(self, country_code: str) -> Optional[Dict[str, Any]]:
        """
        Obtém o PIB per capita mais recente em USD correntes (NY.GDP.PCAP.CD).
        """
        country = self._sanitize_country_code(country_code)
        if not country:
            return None

        params = {
            "format": "json",
            "per_page": 10,
        }
        endpoint = f"country/{country}/indicator/NY.GDP.PCAP.CD"
        data = await self._request(endpoint, params=params)

        if isinstance(data, list) and len(data) > 0 and isinstance(data[0], dict) and "message" in data[0]:
            return None

        if not isinstance(data, list) or len(data) < 2 or not isinstance(data[1], list):
            return None

        entries: List[Dict[str, Any]] = data[1]
        for entry in entries:
            val = entry.get("value")
            if val is not None:
                return {
                    "country": entry.get("country", {}).get("value", country),
                    "country_id": entry.get("countryiso3code", country),
                    "indicator": "NY.GDP.PCAP.CD",
                    "year": int(entry.get("date", 0)),
                    "value": Decimal(str(val)),
                }

        return None
