"""
Módulo de Integração com a API do Banco Mundial v2 (Zero Auth).

Responsabilidades:
- Obter fatores de conversão de Paridade de Poder de Compra (PPP - PA.NUS.PPP).
- Consultar indicadores macroeconômicos (PIB per capita - NY.GDP.PCAP.CD).
- Tratar defasagem histórica anual e selecionar o ano mais recente não-nulo.
"""

from decimal import Decimal
from typing import Any, Dict, List, Optional
import httpx

from src.api.base import BaseAPIClient


class WorldBankClient(BaseAPIClient):
    """Cliente HTTP para comunicação com a API do Banco Mundial v2."""

    def __init__(
        self,
        base_url: str = "https://api.worldbank.org/v2",
        timeout: float = 10.0,
        client: Optional[httpx.AsyncClient] = None,
    ) -> None:
        super().__init__(
            base_url=base_url,
            service_name="WorldBank",
            timeout=timeout,
            client=client,
        )

    async def get_ppp_conversion_factor(self, country_code: str) -> Optional[Dict[str, Any]]:
        """
        Obtém o fator de conversão de PPP mais recente (PA.NUS.PPP) para um país ISO-2 ou ISO-3.
        Retorna dicionário com: country, country_id, indicator, year, value (Decimal).
        """
        country = country_code.upper()
        params = {
            "format": "json",
            "per_page": 10,
        }
        endpoint = f"country/{country}/indicator/PA.NUS.PPP"
        data = await self._request(endpoint, params=params)

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
        country = country_code.upper()
        params = {
            "format": "json",
            "per_page": 10,
        }
        endpoint = f"country/{country}/indicator/NY.GDP.PCAP.CD"
        data = await self._request(endpoint, params=params)

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
