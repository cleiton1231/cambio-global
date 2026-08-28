"""
Testes Automatizados de Segurança: STRIDE, OWASP Top 10 e Robustez Adversarial (tests/test_security.py).

Verificações obrigatórias de segurança:
1. Prevenção de Path Traversal e Injeção de Bytes Nulos (StorageManager).
2. Prevenção de SSRF e Desvios de Host/Path (BaseAPIClient).
3. Prevenção de Injeção de Ponto Flutuante (NaN, sNaN, Infinity, 1e309).
4. Sanitização contra XSS e Injeção em Markdown/HTML (FinancialReportGenerator).
5. Defesas contra DoS, ReDoS e Payloads Excessivos.
6. Validação de Limites Financeiros de Borda (Spread/IOF >= 100%, Fatores PPP <= 0).
"""

from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
import pytest

from src.api.base import BaseAPIClient
from src.api.coincap import CoinCapClient
from src.api.frankfurter import FrankfurterClient
from src.api.world_bank import WorldBankClient
from src.main import parse_safe_decimal
from src.match import CurrencyMatcher
from src.models import (
    APIConnectionError,
    ConversionResult,
    CostSimulationResult,
    CurrencyNotFoundError,
    FinancialReportData,
    InvalidExchangeRateError,
    OperationType,
    SalaryEquivalencyResult,
    UnsupportedPPPAssetError,
)
from src.reporter import FinancialReportGenerator
from src.storage import StorageManager
from src.web.app import ConvertRequest, CostSimulateRequest, SalaryRequest


# ============================================================================
# 1. Prevenção contra Path Traversal e Bytes Nulos (OWASP A01)
# ============================================================================

@pytest.mark.security
def test_security_path_traversal_prevention(tmp_path: Path):
    """Garante que qualquer tentativa de Path Traversal ou byte nulo seja bloqueada no StorageManager."""
    storage = StorageManager(data_dir=tmp_path)

    malicious_paths = [
        "../../etc/passwd",
        "/etc/shadow",
        "../../.ssh/id_rsa",
        "nested/../../../../root.json",
        "..\\..\\windows\\win.ini",
        "file\x00name.json",
        "",
    ]

    for mal_path in malicious_paths:
        with pytest.raises(ValueError):
            storage.export_history_json(mal_path)

        with pytest.raises(ValueError):
            storage.export_history_csv(mal_path)


# ============================================================================
# 2. Prevenção contra SSRF e Path Injection em APIs (OWASP A10)
# ============================================================================

@pytest.mark.security
@pytest.mark.asyncio
async def test_security_ssrf_and_path_injection_defense():
    """Garante que endpoints forjados com esquemas absolutos ou travessias sejam bloqueados no BaseAPIClient."""
    client = BaseAPIClient(base_url="https://api.frankfurter.app", service_name="Frankfurter")

    malicious_endpoints = [
        "https://attacker.com/steal",
        "http://169.254.169.254/latest/meta-data",
        "//evil.com/api",
        "\\\\evil.com\\share",
        "../../etc/passwd",
        "latest/../../admin",
    ]

    for mal_endpoint in malicious_endpoints:
        with pytest.raises(APIConnectionError, match="Tentativa de desvio|Tentativa de path traversal"):
            await client._request(mal_endpoint)


# ============================================================================
# 3. Prevenção contra Injeção de Ponto Flutuante (NaN, Infinity, Overflow)
# ============================================================================

@pytest.mark.security
def test_security_parse_safe_decimal_rejections():
    """Garante que parse_safe_decimal rejeite explicitamente NaN, Infinity e overflow."""
    invalid_inputs = [
        "NaN", "nan", "snan", "+Infinity", "-Infinity", "inf", "-inf", "Infinity",
        "1e309", "abc", "", "   "
    ]

    for bad_input in invalid_inputs:
        with pytest.raises(ValueError):
            parse_safe_decimal(bad_input)


@pytest.mark.security
def test_security_pydantic_schema_decimal_validation():
    """Garante que schemas Pydantic na Web API rejeitem NaN e Infinity antes da conversão."""
    with pytest.raises(ValueError):
        ConvertRequest(amount=Decimal("NaN"), from_currency="USD", to_currency="BRL")

    with pytest.raises(ValueError):
        ConvertRequest(amount=Decimal("Infinity"), from_currency="USD", to_currency="BRL")


# ============================================================================
# 4. Sanitização contra Injeções em Markdown e XSS em HTML (OWASP A03)
# ============================================================================

@pytest.mark.security
def test_security_report_markdown_and_html_sanitization():
    """Garante que quebras de tabela Markdown e scripts HTML sejam sanitizados."""
    generator = FinancialReportGenerator()
    malicious_data = FinancialReportData(
        title="Relatório | Injetado <script>alert('xss')</script>",
        created_at=datetime(2026, 8, 28, 12, 0, 0, tzinfo=timezone.utc),
        conversions=[
            ConversionResult(
                amount_from=Decimal("100"),
                currency_from="USD | Exploit",
                amount_to=Decimal("500"),
                currency_to="BRL",
                rate=Decimal("5.0"),
                source="Frankfurter | Injection",
            )
        ],
        notes="Nota com quebra\n| e tentativa de quebrar tabela | e <img src=x onerror=alert(1)>",
    )

    # 1. Validação Markdown: pipes não podem quebrar colunas
    md_out = generator.generate_markdown(malicious_data)
    assert "\\|" in md_out
    assert "# 📑 Relatório \\| Injetado <script>alert('xss')</script>" in md_out

    # 2. Validação HTML: tags devem ser estritamente escapadas
    html_out = generator.generate_html(malicious_data)
    assert "<script>alert('xss')</script>" not in html_out
    assert "&lt;script&gt;alert(&#x27;xss&#x27;)&lt;/script&gt;" in html_out or "&lt;script&gt;alert('xss')&lt;/script&gt;" in html_out
    assert "<img src=x onerror=alert(1)>" not in html_out
    assert "&lt;img src=x onerror=alert(1)&gt;" in html_out


# ============================================================================
# 5. Limites Financeiros de Borda (Spread/IOF >= 100%)
# ============================================================================

@pytest.mark.security
@pytest.mark.asyncio
async def test_security_financial_limits_validation():
    """Garante que alíquotas abusivas (>= 100%) sejam rejeitadas."""
    from src.costs import CostSimulator
    simulator = CostSimulator()

    with pytest.raises(ValueError, match="Alíquotas de IOF e Spread devem ser estritamente menores que 100%"):
        await simulator.simulate(
            amount=Decimal("1000"),
            from_currency="BRL",
            to_currency="USD",
            custom_spread=Decimal("105.0"),
        )

    with pytest.raises(ValueError, match="Alíquotas de IOF e Spread devem ser estritamente menores que 100%"):
        await simulator.simulate(
            amount=Decimal("1000"),
            from_currency="BRL",
            to_currency="USD",
            custom_iof=Decimal("100.0"),
        )
