"""
Testes Unitários do Gerador de Relatórios Executivos (src/reporter.py).
"""

from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
import pytest

from src.models import (
    ConversionResult,
    CostSimulationResult,
    FinancialReportData,
    OperationType,
    SalaryEquivalencyResult,
)
from src.reporter import FinancialReportGenerator
from src.storage import StorageManager


@pytest.fixture
def sample_report_data() -> FinancialReportData:
    """Fixture de dados completos para o relatório."""
    return FinancialReportData(
        title="Relatório Executivo de Câmbio & Custos",
        created_at=datetime(2026, 8, 28, 12, 0, 0, tzinfo=timezone.utc),
        conversions=[
            ConversionResult(
                amount_from=Decimal("1000.00"),
                currency_from="USD",
                amount_to=Decimal("5000.00"),
                currency_to="BRL",
                rate=Decimal("5.00"),
                source="frankfurter",
            )
        ],
        cost_simulation=CostSimulationResult(
            amount_from=Decimal("1000.00"),
            currency_from="USD",
            amount_to=Decimal("5000.00"),
            currency_to="BRL",
            operation_type=OperationType.INBOUND,
            commercial_rate=Decimal("5.00"),
            spread_pct=Decimal("1.20"),
            spread_amount=Decimal("0.06"),
            effective_rate=Decimal("4.94"),
            iof_pct=Decimal("0.38"),
            iof_amount=Decimal("18.77"),
            fixed_fee=Decimal("0.00"),
            net_amount_to=Decimal("4921.23"),
            total_cost_from=Decimal("1000.00"),
            vet=Decimal("4.92123"),
            profile_name="Recebimento de Salário / Freelance",
        ),
        salary_analysis=SalaryEquivalencyResult(
            base_salary=Decimal("5000.00"),
            base_currency="USD",
            target_currency="BRL",
            country_from="USA",
            country_to="BRA",
            nominal_converted_salary=Decimal("25000.00"),
            ppp_equivalent_salary=Decimal("12500.00"),
            purchasing_power_diff_pct=Decimal("100.0"),
            price_level_ratio=Decimal("2.0"),
            verdict="Ganho real de +100% no poder de compra.",
            year=2023,
        ),
        notes="Operação de planejamento para transição de trabalho internacional.",
    )


def test_generate_markdown(sample_report_data):
    """Testa geração de relatório no formato Markdown."""
    generator = FinancialReportGenerator()
    md = generator.generate_markdown(sample_report_data)

    assert "# 📑 Relatório Executivo de Câmbio & Custos" in md
    assert "1,000.00 USD" in md
    assert "5,000.00 BRL" in md
    assert "VET (Valor Efetivo Total)" in md
    assert "4.92123" in md
    assert "Salário Equivalente PPP" in md
    assert "Ganho real de +100%" in md



def test_generate_html(sample_report_data):
    """Testa geração de relatório em HTML5 auto-contido com CSS print-ready."""
    generator = FinancialReportGenerator()
    html_content = generator.generate_html(sample_report_data)

    assert "<!DOCTYPE html>" in html_content
    assert "<title>Relatório Executivo de Câmbio &amp; Custos</title>" in html_content
    assert "@media print" in html_content
    assert "4.921230" in html_content or "4.92123" in html_content
    assert "Ganho real de +100%" in html_content


def test_export_report_files(tmp_path: Path, sample_report_data):
    """Testa salvamento seguro de arquivos .md e .html."""
    storage = StorageManager(data_dir=tmp_path)
    generator = FinancialReportGenerator(storage=storage)

    md_path = generator.export_report_file(sample_report_data, "relatorio.md", fmt="md")
    assert md_path.exists()
    assert md_path.read_text(encoding="utf-8").startswith("# 📑")

    html_path = generator.export_report_file(sample_report_data, "relatorio.html", fmt="html")
    assert html_path.exists()
    assert "<!DOCTYPE html>" in html_path.read_text(encoding="utf-8")
