"""
Módulo de Cache em Memória com TTL e Stale-While-Revalidate.

Responsabilidades:
- Cache em memória thread-safe para requisições HTTP externas.
- Suporte a TTL (Time-To-Live) estrito e janela de tolerância para Stale Cache.
- Degradação graciosa em caso de indisponibilidade de APIs de terceiros.
- Rastreamento de métricas de hit/miss/stale.
- Isolamento total de referências (Anti-Cache Poisoning) com cópias profundas (copy.deepcopy).
- Pruning automático de entradas expiradas além de max_stale.
"""

import copy
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
        self.data = copy.deepcopy(data)
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
    """Gerenciador de cache em memória thread-safe com isolamento de mutação."""

    def __init__(self) -> None:
        self._entries: Dict[str, CachedEntry] = {}
        self._lock = threading.RLock()
        self._hits = 0
        self._misses = 0
        self._stale_hits = 0
        self._sets = 0

    def get(self, key: str, allow_stale: bool = False) -> Optional[Tuple[Any, bool]]:
        """
        Recupera um valor do cache com cópia isolada e despejo de expirados.
        Retorna uma tupla (data, is_stale) ou None se não encontrado/expirado.
        """
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                self._misses += 1
                return None

            if entry.is_fresh():
                self._hits += 1
                return copy.deepcopy(entry.data), False

            if allow_stale and entry.is_valid_stale():
                self._stale_hits += 1
                return copy.deepcopy(entry.data), True

            # Se expirou além da tolerância stale, realiza o eviction
            if not entry.is_valid_stale():
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
        """Armazena um valor no cache com isolamento profundo."""
        with self._lock:
            self._entries[key] = CachedEntry(
                data=data,
                ttl_seconds=ttl_seconds,
                max_stale_seconds=max_stale_seconds,
            )
            self._sets += 1

    def invalidate(self, key: str) -> bool:
        """Invalida uma chave específica do cache."""
        with self._lock:
            if key in self._entries:
                del self._entries[key]
                return True
            return False

    def clear(self) -> None:
        """Limpa todo o conteúdo do cache."""
        with self._lock:
            self._entries.clear()

    def get_stats(self) -> Dict[str, Any]:
        """Retorna as estatísticas operacionais do cache (compatibilidade)."""
        return self.metrics

    @property
    def metrics(self) -> Dict[str, Any]:
        """Retorna as métricas operacionais de desempenho do cache."""
        with self._lock:
            total_lookups = self._hits + self._stale_hits + self._misses
            hit_ratio = (
                (self._hits + self._stale_hits) / total_lookups
                if total_lookups > 0
                else 0.0
            )
            return {
                "size": len(self._entries),
                "hits": self._hits,
                "stale_hits": self._stale_hits,
                "misses": self._misses,
                "sets": self._sets,
                "hit_ratio": round(hit_ratio, 4),
            }
