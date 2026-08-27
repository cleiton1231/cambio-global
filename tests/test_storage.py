"""
Testes Unitários do Módulo de Armazenamento e Persistência (src/storage.py).

Valida:
- Gravação e leitura atômica de histórico de conversões.
- Gerenciamento de moedas favoritas (adicionar, listar, remover, duplicatas).
- Exportação segura para formatos JSON e CSV.
- Prevenção contra Path Traversal em caminhos de exportação.
"""

import csv
import json
from pathlib import Path
import pytest

from src.models import ConversionRecord
from src.storage import StorageManager


@pytest.fixture
def temp_storage(tmp_path: Path) -> StorageManager:
    """Retorna um StorageManager apontando para diretório temporário isolado."""
    return StorageManager(data_dir=tmp_path)


# ============================================================================
# 1. Testes de Histórico de Conversões
# ============================================================================

def test_save_and_get_history(temp_storage: StorageManager):
    """Testa gravação e recuperação de registros de conversão."""
    record1 = ConversionRecord(
        id="rec-1",
        timestamp="2026-08-27T17:00:00Z",
        from_currency="USD",
        to_currency="BRL",
        amount_from=100.0,
        amount_to=550.0,
        rate=5.50,
        ppp_equivalent=250.0,
    )
    record2 = ConversionRecord(
        id="rec-2",
        timestamp="2026-08-27T17:05:00Z",
        from_currency="BTC",
        to_currency="USD",
        amount_from=1.0,
        amount_to=95000.0,
        rate=95000.0,
    )

    temp_storage.save_conversion_record(record1)
    temp_storage.save_conversion_record(record2)

    history = temp_storage.get_history(limit=10)
    assert len(history) == 2
    # Mais recente primeiro
    assert history[0].id == "rec-2"
    assert history[1].id == "rec-1"


def test_history_limit(temp_storage: StorageManager):
    """Testa respeito ao limite de registros retornados."""
    for i in range(10):
        temp_storage.save_conversion_record(ConversionRecord(
            id=f"rec-{i}",
            timestamp=f"2026-08-27T17:{i:02d}:00Z",
            from_currency="USD",
            to_currency="EUR",
            amount_from=10.0,
            amount_to=9.2,
            rate=0.92,
        ))

    history = temp_storage.get_history(limit=3)
    assert len(history) == 3
    assert history[0].id == "rec-9"


# ============================================================================
# 2. Testes de Moedas Favoritas
# ============================================================================

def test_save_and_get_favorites(temp_storage: StorageManager):
    """Testa adição, desduplicação e listagem de favoritos."""
    assert temp_storage.get_favorites() == []

    assert temp_storage.save_favorite("USD") is True
    assert temp_storage.save_favorite("BRL") is True
    assert temp_storage.save_favorite("USD") is False  # Duplicata não reinserida

    favs = temp_storage.get_favorites()
    assert len(favs) == 2
    assert "USD" in favs
    assert "BRL" in favs


def test_remove_favorite(temp_storage: StorageManager):
    """Testa remoção de moeda favorita."""
    temp_storage.save_favorite("BTC")
    temp_storage.save_favorite("ETH")

    assert temp_storage.remove_favorite("BTC") is True
    assert temp_storage.remove_favorite("NOTEXIST") is False
    assert temp_storage.get_favorites() == ["ETH"]


# ============================================================================
# 3. Testes de Exportação CSV e JSON
# ============================================================================

def test_export_history_json(temp_storage: StorageManager):
    """Testa exportação do histórico para arquivo JSON estruturado."""
    temp_storage.save_conversion_record(ConversionRecord(
        id="test-1",
        timestamp="2026-08-27T17:00:00Z",
        from_currency="USD",
        to_currency="BRL",
        amount_from=50.0,
        amount_to=275.0,
        rate=5.50,
    ))

    export_path = temp_storage.export_history_json("export_test.json")
    assert export_path.exists()

    with open(export_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert len(data) == 1
    assert data[0]["id"] == "test-1"
    assert data[0]["from_currency"] == "USD"


def test_export_history_csv(temp_storage: StorageManager):
    """Testa exportação do histórico para arquivo CSV."""
    temp_storage.save_conversion_record(ConversionRecord(
        id="test-csv",
        timestamp="2026-08-27T17:00:00Z",
        from_currency="EUR",
        to_currency="GBP",
        amount_from=100.0,
        amount_to=85.0,
        rate=0.85,
    ))

    export_path = temp_storage.export_history_csv("export_test.csv")
    assert export_path.exists()

    with open(export_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    assert len(rows) == 1
    assert rows[0]["id"] == "test-csv"
    assert rows[0]["from_currency"] == "EUR"
    assert rows[0]["to_currency"] == "GBP"


# ============================================================================
# 4. Testes de Prevenção contra Path Traversal (Segurança)
# ============================================================================

def test_export_prevents_path_traversal(temp_storage: StorageManager):
    """Garante que caminhos maliciosos fora do data_dir sejam rejeitados ou sanitizados."""
    with pytest.raises(ValueError, match="Caminho de arquivo inválido ou fora do diretório permitido"):
        temp_storage.export_history_json("../../etc/passwd.json")

    with pytest.raises(ValueError, match="Caminho de arquivo inválido ou fora do diretório permitido"):
        temp_storage.export_history_csv("../../../root/leak.csv")
