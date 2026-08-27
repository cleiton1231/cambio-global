"""
Histórico de Conversões, Moedas Favoritas e Exportadores JSON/CSV.

Responsabilidades:
- Armazenar histórico de conversões e moedas favoritas localmente de forma atômica.
- Exportar registros históricos para JSON e CSV.
- Garantir segurança estrita contra Path Traversal e corrupção de arquivos.
"""

import csv
import json
from pathlib import Path
import tempfile
from typing import Any, Dict, List, Optional

from src.models import ConversionRecord


class StorageManager:
    """Gerenciador de persistência local em JSON com proteção contra Path Traversal."""

    def __init__(self, data_dir: Optional[Path] = None) -> None:
        self.data_dir = (data_dir or Path("./data")).resolve()
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.history_file = self.data_dir / "history.json"
        self.favorites_file = self.data_dir / "favorites.json"

    def _resolve_safe_path(self, target_filename_or_path: str) -> Path:
        """
        Valida e resolve o caminho do arquivo garantindo que permaneça
        estritamente dentro do data_dir autorizado.
        """
        target = Path(target_filename_or_path)
        # Se for nome simples ou relativo, resolve dentro de data_dir
        if not target.is_absolute():
            resolved = (self.data_dir / target).resolve()
        else:
            resolved = target.resolve()

        # Verifica se o caminho resolvido é filho do data_dir
        try:
            resolved.relative_to(self.data_dir)
        except ValueError:
            raise ValueError(
                f"Caminho de arquivo inválido ou fora do diretório permitido: '{target_filename_or_path}'"
            )

        return resolved

    def _atomic_write_json(self, file_path: Path, data: Any) -> None:
        """Escreve dados em JSON de forma atômica utilizando arquivo temporário."""
        parent = file_path.parent
        parent.mkdir(parents=True, exist_ok=True)

        with tempfile.NamedTemporaryFile("w", dir=parent, delete=False, encoding="utf-8") as tmp:
            json.dump(data, tmp, indent=2, ensure_ascii=False)
            tmp_path = Path(tmp.name)

        tmp_path.replace(file_path)

    def _read_json(self, file_path: Path, default: Any) -> Any:
        """Lê arquivo JSON retornando o valor default caso não exista ou esteja corrompido."""
        if not file_path.exists():
            return default
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return default

    # ========================================================================
    # Histórico de Conversões
    # ========================================================================

    def save_conversion_record(self, record: ConversionRecord) -> None:
        """Salva um registro no histórico de conversões."""
        records: List[Dict[str, Any]] = self._read_json(self.history_file, [])
        records.append(record.to_dict())
        self._atomic_write_json(self.history_file, records)

    def get_history(self, limit: int = 50) -> List[ConversionRecord]:
        """
        Retorna o histórico de conversões ordenado do mais recente para o mais antigo.
        """
        raw_records: List[Dict[str, Any]] = self._read_json(self.history_file, [])
        records = [
            ConversionRecord(
                id=r.get("id", ""),
                timestamp=r.get("timestamp", ""),
                from_currency=r.get("from_currency", ""),
                to_currency=r.get("to_currency", ""),
                amount_from=float(r.get("amount_from", 0.0)),
                amount_to=float(r.get("amount_to", 0.0)),
                rate=float(r.get("rate", 0.0)),
                ppp_equivalent=r.get("ppp_equivalent"),
                country_from=r.get("country_from"),
                country_to=r.get("country_to"),
            )
            for r in reversed(raw_records)
        ]
        return records[:limit]

    def clear_history(self) -> None:
        """Limpa o histórico de conversões."""
        self._atomic_write_json(self.history_file, [])

    # ========================================================================
    # Moedas Favoritas
    # ========================================================================

    def get_favorites(self) -> List[str]:
        """Retorna a lista de moedas favoritas salvas."""
        return self._read_json(self.favorites_file, [])

    def save_favorite(self, currency_code: str) -> bool:
        """
        Adiciona uma moeda à lista de favoritas (se ainda não existir).
        Retorna True se adicionada, False se já existia.
        """
        favs: List[str] = self.get_favorites()
        code_upper = currency_code.strip().upper()
        if code_upper in favs:
            return False

        favs.append(code_upper)
        self._atomic_write_json(self.favorites_file, favs)
        return True

    def remove_favorite(self, currency_code: str) -> bool:
        """
        Remove uma moeda da lista de favoritas.
        Retorna True se removida, False se não existia.
        """
        favs: List[str] = self.get_favorites()
        code_upper = currency_code.strip().upper()
        if code_upper not in favs:
            return False

        favs.remove(code_upper)
        self._atomic_write_json(self.favorites_file, favs)
        return True

    # ========================================================================
    # Exportação Segura (CSV / JSON)
    # ========================================================================

    def export_history_json(self, filename_or_path: str = "history_export.json") -> Path:
        """Exporta o histórico completo para arquivo JSON seguro."""
        safe_path = self._resolve_safe_path(filename_or_path)
        history = self._read_json(self.history_file, [])
        self._atomic_write_json(safe_path, history)
        return safe_path

    def export_history_csv(self, filename_or_path: str = "history_export.csv") -> Path:
        """Exporta o histórico completo para arquivo CSV seguro."""
        safe_path = self._resolve_safe_path(filename_or_path)
        history = self._read_json(self.history_file, [])

        fieldnames = [
            "id", "timestamp", "from_currency", "to_currency",
            "amount_from", "amount_to", "rate", "ppp_equivalent",
            "country_from", "country_to"
        ]

        parent = safe_path.parent
        parent.mkdir(parents=True, exist_ok=True)

        with tempfile.NamedTemporaryFile("w", dir=parent, delete=False, encoding="utf-8", newline="") as tmp:
            writer = csv.DictWriter(tmp, fieldnames=fieldnames)
            writer.writeheader()
            for row in history:
                filtered_row = {k: row.get(k, "") for k in fieldnames}
                writer.writerow(filtered_row)
            tmp_path = Path(tmp.name)

        tmp_path.replace(safe_path)
        return safe_path
