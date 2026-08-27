"""
Módulo de Cache em Memória com TTL e Stale-While-Revalidate.

Responsabilidades:
- Cache em memória thread-safe para requisições HTTP externas.
- Suporte a TTL (Time-To-Live) estrito e janela de tolerância para Stale Cache.
- Degradação graciosa em caso de indisponibilidade de APIs de terceiros.
- Rastreamento de métricas de hit/miss/stale.
"""

import threading
import time
from typing import Any, Dict, Optional, Tuple


class CachedEntry:
    """Entrada individual de cache com metadados temporais."""

    def __init__(
        self,
        data: Any,
        ttl_seconds: float,
        max_stale_seconds: float = 0.0,
    ) -> None:
        now = time.time()
        self.data = data
        self.cached_at = now
        self.expires_at = now + ttl_seconds
        self.max_stale_until = now + ttl_seconds + max_stale_seconds

    def is_fresh(self) -> bool:
        """Verifica se a entrada ainda está dentro do TTL válido."""
        return time.time() <= self.expires_at

    def is_valid_stale(self) -> bool:
        """Verifica se a entrada expirou mas ainda está dentro da janela de tolerância stale."""
        now = time.time()
        return self.expires_at < now <= self.max_stale_until


class MemoryCache:
    """Gerenciador de cache em memória thread-safe."""

    def __init__(self) -> None:
        self._entries: Dict[str, CachedEntry] = {}
        self._lock = threading.RLock()
        self._hits = 0
        self._misses = 0
        self._stale_hits = 0
        self._sets = 0

    def get(self, key: str, allow_stale: bool = False) -> Optional[Tuple[Any, bool]]:
        """
        Recupera um valor do cache.
        Retorna uma tupla (data, is_stale) ou None se não encontrado/expirado.
        """
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                self._misses += 1
                return None

            if entry.is_fresh():
                self._hits += 1
                return entry.data, False

            if allow_stale and entry.is_valid_stale():
                self._stale_hits += 1
                return entry.data, True

            # Se expirou completamente além da janela de stale, remove
            now = time.time()
            if now > entry.max_stale_until:
                del self._entries[key]

            self._misses += 1
            return None


    def set(
        self,
        key: str,
        data: Any,
        ttl_seconds: float,
        max_stale_seconds: float = 0.0,
    ) -> None:
        """Armazena um valor no cache com TTL e janela de stale configurados."""
        with self._lock:
            self._entries[key] = CachedEntry(
                data=data,
                ttl_seconds=ttl_seconds,
                max_stale_seconds=max_stale_seconds,
            )
            self._sets += 1

    def invalidate(self, key: str) -> bool:
        """Remove uma chave específica do cache."""
        with self._lock:
            if key in self._entries:
                del self._entries[key]
                return True
            return False

    def clear(self) -> None:
        """Limpa todas as entradas e zera os contadores do cache."""
        with self._lock:
            self._entries.clear()
            self._hits = 0
            self._misses = 0
            self._stale_hits = 0
            self._sets = 0

    def get_stats(self) -> Dict[str, int]:
        """Retorna métricas de performance do cache."""
        with self._lock:
            return {
                "hits": self._hits,
                "misses": self._misses,
                "stale_hits": self._stale_hits,
                "sets": self._sets,
                "size": len(self._entries),
            }


# Instância global singleton do cache
_GLOBAL_CACHE: Optional[MemoryCache] = None


def get_cache() -> MemoryCache:
    """Retorna a instância singleton do MemoryCache."""
    global _GLOBAL_CACHE
    if _GLOBAL_CACHE is None:
        _GLOBAL_CACHE = MemoryCache()
    return _GLOBAL_CACHE
