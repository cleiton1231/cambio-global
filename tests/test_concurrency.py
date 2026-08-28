"""
Testes de Concorrência, Integridade Inter-Processos e Isolamento de Cache (tests/test_concurrency.py).
"""

from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from pathlib import Path
import pytest

from src.cache import MemoryCache
from src.models import ConversionRecord
from src.storage import StorageManager


def test_cache_deepcopy_mutation_isolation():
    """Garante que alterar dados retornados pelo cache não envenene o estado interno (Anti-Cache Poisoning)."""
    cache = MemoryCache()
    original_data = {"rates": {"BRL": Decimal("5.00"), "EUR": Decimal("0.90")}}

    cache.set("rates_usd", original_data, ttl_seconds=60)

    # Leitura 1
    retrieved_1, is_stale = cache.get("rates_usd")
    assert retrieved_1["rates"]["BRL"] == Decimal("5.00")

    # Modificação maliciosa ou acidental na referência retornada
    retrieved_1["rates"]["BRL"] = Decimal("999.99")
    retrieved_1["rates"]["NOVA_MOEDA"] = Decimal("1.23")

    # Leitura 2 deve continuar com o valor original inalterado
    retrieved_2, is_stale_2 = cache.get("rates_usd")
    assert retrieved_2["rates"]["BRL"] == Decimal("5.00")
    assert "NOVA_MOEDA" not in retrieved_2["rates"]


def test_cache_concurrent_access():
    """Testa múltiplos leitores e escritores simultâneos no MemoryCache."""
    cache = MemoryCache()

    def worker(worker_id: int):
        for i in range(50):
            key = f"key_{i % 5}"
            cache.set(key, {"id": worker_id, "val": i}, ttl_seconds=10)
            res = cache.get(key)
            assert res is not None

    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(worker, w) for w in range(8)]
        for f in futures:
            f.result()

    metrics = cache.metrics
    assert metrics["sets"] == 8 * 50
    assert metrics["hits"] > 0


def test_storage_concurrent_writes(tmp_path: Path):
    """Garante que gravações concorrentes no StorageManager não percam registros (Atomicidade)."""
    storage = StorageManager(data_dir=tmp_path)

    total_records = 40

    def write_record(idx: int):
        rec = ConversionRecord(
            id=f"rec_{idx}",
            timestamp="2026-08-28T12:00:00Z",
            from_currency="USD",
            to_currency="BRL",
            amount_from=100.0 + idx,
            amount_to=500.0 + idx,
            rate=5.0,
        )
        storage.save_conversion_record(rec)

    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(write_record, i) for i in range(total_records)]
        for f in futures:
            f.result()

    history = storage.get_history(limit=100)
    assert len(history) == total_records
    # Todos os IDs devem estar presentes
    history_ids = {r.id for r in history}
    expected_ids = {f"rec_{i}" for i in range(total_records)}
    assert history_ids == expected_ids
