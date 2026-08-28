"""
Cliente HTTP base assíncrono para integrações de API públicas (Zero Auth).

Responsabilidades:
- Pool de conexões assíncrono com httpx.AsyncClient.
- Timeout padrão configurável (10s).
- Cache transparente em memória com TTL e Stale-While-Revalidate.
- Tratamento defensivo de exceções e conversão em exceções de domínio.
- Blindagem estrita contra SSRF, desvios de protocolo e Path Traversal.
"""

import asyncio
from typing import Any, Dict, Optional
import httpx

from src.cache import MemoryCache, get_cache
from src.models import (
    APIConnectionError,
    APIRateLimitError,
    APIResponseError,
)


class BaseAPIClient:
    """Cliente base para APIs externas com resiliência, Zero Auth e Cache TTL."""

    def __init__(
        self,
        base_url: str,
        service_name: str,
        timeout: float = 10.0,
        max_retries: int = 2,
        ttl_seconds: float = 3600.0,
        max_stale_seconds: float = 86400.0,
        client: Optional[httpx.AsyncClient] = None,
        cache: Optional[MemoryCache] = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.service_name = service_name
        self.timeout = timeout
        self.max_retries = max_retries
        self.ttl_seconds = ttl_seconds
        self.max_stale_seconds = max_stale_seconds
        self._client = client
        self.cache = cache or get_cache()
        self.last_response_stale = False

    async def _get_client(self) -> httpx.AsyncClient:
        """Obtém ou cria o cliente HTTP assíncrono com pool de conexões."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=self.timeout,
                headers={"User-Agent": "CambioGlobal/0.2.0 (Open-Source Finance CLI & API)"},
            )
        return self._client

    async def close(self) -> None:
        """Fecha as conexões ativas do cliente HTTP."""
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()

    def _generate_cache_key(
        self,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Gera chave determinística e padronizada para o cache."""
        clean_endpoint = endpoint.strip("/").lower()
        params_str = ""
        if params:
            sorted_items = sorted((str(k), str(v)) for k, v in params.items())
            params_str = "?" + "&".join(f"{k}={v}" for k, v in sorted_items)
        return f"{self.service_name.lower()}:{clean_endpoint}{params_str}"

    async def _request(
        self,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
    ) -> Any:
        """
        Executa requisição HTTP GET com cache TTL, retries e blindagem anti-SSRF.
        """
        self.last_response_stale = False
        cache_key = self._generate_cache_key(endpoint, params)

        # 1. Verifica cache fresco
        cached = self.cache.get(cache_key, allow_stale=False)
        if cached is not None:
            data, is_stale = cached
            self.last_response_stale = is_stale
            return data

        # 2. Blindagem Anti-SSRF e Path Traversal no endpoint
        clean_endpoint = str(endpoint).strip().lstrip("/")
        if "://" in clean_endpoint or clean_endpoint.startswith("//") or clean_endpoint.startswith("\\\\"):
            raise APIConnectionError(
                service=self.service_name,
                message=f"Tentativa de desvio de rota ou SSRF detectada no endpoint: '{endpoint}'",
            )

        parts = clean_endpoint.split("/")
        if ".." in parts:
            raise APIConnectionError(
                service=self.service_name,
                message=f"Tentativa de path traversal detectada no endpoint: '{endpoint}'",
            )

        url = f"{self.base_url}/{clean_endpoint}" if clean_endpoint else self.base_url

        # Validação do Host de Destino
        base_host = httpx.URL(self.base_url).host
        target_host = httpx.URL(url).host
        if target_host != base_host:
            raise APIConnectionError(
                service=self.service_name,
                message=f"Desvio de host não autorizado ({target_host} != {base_host})",
            )

        owns_client = self._client is None or self._client.is_closed
        client = await self._get_client()

        try:
            for attempt in range(self.max_retries + 1):
                try:
                    response = await client.get(url, params=params)

                    if response.status_code == 429:
                        # Em rate limit, tenta stale cache se disponível
                        stale_cached = self.cache.get(cache_key, allow_stale=True)
                        if stale_cached is not None:
                            data, _ = stale_cached
                            self.last_response_stale = True
                            return data
                        raise APIRateLimitError(service=self.service_name)

                    if response.status_code >= 500:
                        # Em erro de servidor, tenta stale cache
                        stale_cached = self.cache.get(cache_key, allow_stale=True)
                        if stale_cached is not None:
                            data, _ = stale_cached
                            self.last_response_stale = True
                            return data
                        raise APIResponseError(
                            service=self.service_name,
                            message=f"Erro 5xx no serviço {self.service_name}: {response.status_code}",
                            status_code=response.status_code,
                        )

                    if response.status_code >= 400:
                        # Erros 4xx de cliente (ex: 404) NÃO usam stale cache
                        raise APIResponseError(
                            service=self.service_name,
                            message=f"Falha na requisição: {response.text[:200]}",
                            status_code=response.status_code,
                        )

                    try:
                        data = response.json()
                        # Grava resposta no cache com os TTLs configurados
                        self.cache.set(
                            cache_key,
                            data,
                            ttl_seconds=self.ttl_seconds,
                            max_stale_seconds=self.max_stale_seconds,
                        )
                        return data
                    except Exception as e:
                        raise APIResponseError(
                            service=self.service_name,
                            message=f"Corpo de resposta JSON inválido: {str(e)}",
                            status_code=response.status_code,
                        )

                except (httpx.RequestError, httpx.TimeoutException) as exc:
                    if attempt == self.max_retries:
                        # Esgotou retries: tenta servir stale cache antes de explodir
                        stale_cached = self.cache.get(cache_key, allow_stale=True)
                        if stale_cached is not None:
                            data, _ = stale_cached
                            self.last_response_stale = True
                            return data
                        raise APIConnectionError(service=self.service_name, message=str(exc))
                    await asyncio.sleep(0.15 * (2**attempt))
        finally:
            if owns_client and self._client is not None:
                await self.close()
