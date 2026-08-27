"""
Cliente HTTP base assíncrono para integrações de API públicas (Zero Auth).

Responsabilidades:
- Pool de conexões assíncrono com httpx.AsyncClient.
- Timeout padrão configurável (10s).
- Tratamento defensivo de exceções e conversão em exceções de domínio do Câmbio Global.
- Retries com backoff para erros de rede transitórios.
"""

import asyncio
from typing import Any, Dict, Optional
import httpx

from src.models import (
    APIConnectionError,
    APIRateLimitError,
    APIResponseError,
)


class BaseAPIClient:
    """Cliente base para APIs externas com resiliência e Zero Auth."""

    def __init__(
        self,
        base_url: str,
        service_name: str,
        timeout: float = 10.0,
        max_retries: int = 2,
        client: Optional[httpx.AsyncClient] = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.service_name = service_name
        self.timeout = timeout
        self.max_retries = max_retries
        self._client = client
        self._default_headers = {
            "User-Agent": "CambioGlobal/0.1.0 (Financial Assistant; Zero-Auth Client)",
            "Accept": "application/json",
        }

    async def _get_client(self) -> httpx.AsyncClient:
        """Retorna o cliente HTTP assíncrono."""
        if self._client is not None and not self._client.is_closed:
            return self._client
        return httpx.AsyncClient(
            timeout=httpx.Timeout(self.timeout),
            headers=self._default_headers,
            follow_redirects=True,
        )

    async def _request(
        self,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
    ) -> Any:
        """
        Executa requisição HTTP GET com retries e tratamento de erros.
        """
        clean_endpoint = endpoint.lstrip("/")
        url = f"{self.base_url}/{clean_endpoint}" if clean_endpoint else self.base_url

        owns_client = self._client is None or self._client.is_closed
        client = await self._get_client()

        try:
            for attempt in range(self.max_retries + 1):
                try:
                    response = await client.get(url, params=params)
                    
                    if response.status_code == 429:
                        raise APIRateLimitError(service=self.service_name)
                    
                    if response.status_code >= 400:
                        raise APIResponseError(
                            service=self.service_name,
                            message=f"Falha na requisição: {response.text[:200]}",
                            status_code=response.status_code,
                        )

                    try:
                        return response.json()
                    except Exception as e:
                        raise APIResponseError(
                            service=self.service_name,
                            message=f"Resposta JSON malformada da API: {str(e)}",
                            status_code=response.status_code,
                        )

                except (httpx.ConnectError, httpx.TimeoutException, httpx.NetworkError) as net_err:
                    if attempt < self.max_retries:
                        await asyncio.sleep(0.5 * (2 ** attempt))
                        continue
                    raise APIConnectionError(
                        service=self.service_name,
                        message=f"Erro de conexão com {self.service_name}: {str(net_err)}",
                    ) from None

        finally:
            if owns_client and not client.is_closed:
                await client.aclose()
