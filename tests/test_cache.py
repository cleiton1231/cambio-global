"""
Testes Unitários do Sistema de Cache em Memória com TTL e Stale-While-Revalidate.

Cobre:
- Gravação e recuperação de valores dentro do TTL.
- Expiração por TTL (Fresh vs Stale).
- Recuperação em modo Stale dentro da janela max_stale.
- Invalidação e limpeza do cache.
- Métricas e estatísticas (hits, misses, stale_hits, sets, size).
"""

import time
import pytest

from src.cache import MemoryCache


@pytest.fixture
def cache() -> MemoryCache:
    """Retorna uma nova instância isolada de MemoryCache."""
    return MemoryCache()


def test_cache_set_and_get_fresh(cache: MemoryCache):
    """Testa gravação e leitura de entrada fresca."""
    cache.set("test_key", {"rate": 5.50}, ttl_seconds=10.0)
    
    result = cache.get("test_key")
    assert result is not None
    data, is_stale = result
    assert data == {"rate": 5.50}
    assert is_stale is False

    stats = cache.get_stats()
    assert stats["hits"] == 1
    assert stats["misses"] == 0
    assert stats["size"] == 1


def test_cache_miss(cache: MemoryCache):
    """Testa tentativa de recuperação de chave inexistente."""
    result = cache.get("non_existent_key")
    assert result is None

    stats = cache.get_stats()
    assert stats["misses"] == 1
    assert stats["hits"] == 0


def test_cache_ttl_expiration_and_stale_retrieval(cache: MemoryCache):
    """Testa comportamento quando o TTL expira mas ainda está dentro de max_stale."""
    # TTL de 0.05 segundos, max_stale de 0.5 segundos
    cache.set("stale_key", "old_value", ttl_seconds=0.05, max_stale_seconds=0.5)

    time.sleep(0.08)  # Aguarda expirar TTL

    # Sem allow_stale -> deve retornar None
    assert cache.get("stale_key", allow_stale=False) is None

    # Com allow_stale -> deve retornar valor com is_stale=True
    stale_res = cache.get("stale_key", allow_stale=True)
    assert stale_res is not None
    data, is_stale = stale_res
    assert data == "old_value"
    assert is_stale is True

    stats = cache.get_stats()
    assert stats["stale_hits"] == 1


def test_cache_max_stale_expiration(cache: MemoryCache):
    """Testa remoção automática quando expira além do max_stale."""
    cache.set("expired_key", "value", ttl_seconds=0.02, max_stale_seconds=0.04)

    time.sleep(0.08)  # Aguarda expirar TTL + max_stale

    assert cache.get("expired_key", allow_stale=True) is None
    assert cache.get_stats()["size"] == 0


def test_cache_invalidation_and_clear(cache: MemoryCache):
    """Testa invalidação individual e limpeza global do cache."""
    cache.set("k1", "v1", ttl_seconds=60)
    cache.set("k2", "v2", ttl_seconds=60)
    assert cache.get_stats()["size"] == 2

    assert cache.invalidate("k1") is True
    assert cache.invalidate("k1") is False
    assert cache.get("k1") is None
    assert cache.get("k2") is not None

    cache.clear()
    assert cache.get_stats()["size"] == 0
    assert cache.get("k2") is None
