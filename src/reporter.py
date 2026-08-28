"""
Gerador de Relatórios Financeiros Executivos (Markdown & HTML / Print-to-PDF).

Responsabilidades:
- Consolidar conversões cambiais, simulação de custos (VET) e análise de poder de compra/salário.
- Gerar documentos em Markdown GFM limpo e estruturado.
- Gerar documentos executivos em HTML5 auto-contidos com estilização CSS pronta para impressão/PDF (@media print).
- Sanitização estrita de saída com html.escape() (Defesa contra XSS e HTML Injection - OWASP A03).
"""

from datetime import datetime, timezone
from decimal import Decimal
import html
from pathlib import Path
from typing import Optional

from src.models import FinancialReportData
from src.storage import StorageManager


class FinancialReportGenerator:
    """Gerador e exportador de relatórios financeiros consolidados."""

    def __init__(self, storage: Optional[StorageManager] = None) -> None:
        self.storage = storage or StorageManager()

    def generate_markdown(self, data: FinancialReportData) -> str:
        """Gera o relatório formatado em Markdown (GitHub Flavored Markdown)."""
        lines = []
        lines.append(f"# 📑 {data.title}")
        lines.append(f"**Data de Emissão:** {data.created_at.strftime('%Y-%m-%d %H:%M:%S UTC')}")
        lines.append(f"**Sistema:** Câmbio Global • Fontes: Frankfurter (BCE), CoinCap, Banco Mundial (Zero-Auth)")
        lines.append("\n---\n")

        # 1. Resumo de Conversões
        if data.conversions:
            lines.append("## 💱 1. Resumo das Conversões Cambiais\n")
            lines.append("| Origem | Destino (Nominal) | Taxa Comercial | Fonte | Status |")
            lines.append("| :--- | :--- | :--- | :--- | :--- |")
            for c in data.conversions:
                stale_str = "*(Stale Cache)*" if c.is_stale else "OK"
                lines.append(
                    f"| {c.amount_from:,.2f} {c.currency_from} | "
                    f"**{c.amount_to:,.2f} {c.currency_to}** | "
                    f"1 {c.currency_from} = {c.rate:,.6f} {c.currency_to} | "
                    f"{c.source} | {stale_str} |"
                )
            lines.append("")

        # 2. Simulação de Custos e VET (BACEN)
        if data.cost_simulation:
            cs = data.cost_simulation
            lines.append("## 💳 2. Detalhamento de Custos Efetivos e VET (BACEN)\n")
            lines.append(f"**Perfil Aplicado:** {cs.profile_name} ({cs.operation_type.value.upper()})\n")
            lines.append("| Item Financeiro | Valor Apurado |")
            lines.append("| :--- | :--- |")
            lines.append(f"| **Quantia Bruta Negociada:** | {cs.amount_from:,.2f} {cs.currency_from} |")
            lines.append(f"| **Taxa de Mercado Pura:** | {cs.commercial_rate:,.6f} |")
            lines.append(f"| **Spread Cambial:** | {cs.spread_pct:.2f}% (R$ {cs.spread_amount:,.6f}/un) |")
            lines.append(f"| **Taxa Efetiva com Spread:** | {cs.effective_rate:,.6f} |")
            lines.append(f"| **IOF Recolhido:** | {cs.iof_pct:.2f}% ({cs.iof_amount:,.2f}) |")
            if cs.fixed_fee > 0:
                lines.append(f"| **Tarifa Fixa Bancária:** | {cs.fixed_fee:,.2f} |")
            lines.append(f"| **Montante Líquido Final:** | **{cs.net_amount_to:,.2f} {cs.currency_to}** |")
            lines.append(f"| **Custo Total Efetivo:** | {cs.total_cost_from:,.2f} {cs.currency_from} |")
            lines.append(f"| **VET (Valor Efetivo Total):** | **{cs.vet:,.6f}** |")
            lines.append("")

        # 3. Análise de Salário e Poder de Compra (PPP)
        if data.salary_analysis:
            sa = data.salary_analysis
            lines.append("## 🌍 3. Análise de Salário Internacional e Poder de Compra (PPP)\n")
            lines.append(f"- **Salário de Origem:** {sa.base_salary:,.2f} {sa.base_currency} ({sa.country_from})")
            lines.append(f"- **Salário Nominal Convertido:** {sa.nominal_converted_salary:,.2f} {sa.target_currency}")
            lines.append(f"- **Salário Equivalente PPP (Banco Mundial {sa.year}):** **{sa.ppp_equivalent_salary:,.2f} {sa.target_currency}** ({sa.country_to})")
            diff_sign = "+" if sa.purchasing_power_diff_pct >= 0 else ""
            lines.append(f"- **Variação Real do Poder de Compra:** `{diff_sign}{sa.purchasing_power_diff_pct:.1f}%`")
            lines.append(f"- **Índice do Nível de Preços (PLR):** `{sa.price_level_ratio:.2f}`")
            lines.append(f"\n> **Veredito:** {sa.verdict}\n")

        # 4. Observações
        if data.notes:
            lines.append("## 📝 4. Observações Executivas\n")
            lines.append(data.notes.strip())
            lines.append("")

        return "\n".join(lines)

    def generate_html(self, data: FinancialReportData) -> str:
        """Gera documento HTML5 auto-contido com CSS print-ready e sanitização estrita."""
        # Sanitização de todos os campos de texto do usuário contra XSS/HTML Injection
        safe_title = html.escape(data.title)
        safe_notes = html.escape(data.notes) if data.notes else ""
        date_str = data.created_at.strftime('%Y-%m-%d %H:%M:%S UTC')

        # Seções HTML
        conversions_html = ""
        if data.conversions:
            rows = ""
            for c in data.conversions:
                stale_badge = "<span class='badge badge-stale'>Stale Cache</span>" if c.is_stale else "<span class='badge badge-ok'>OK</span>"
                rows += f"""
                <tr>
                    <td>{html.escape(f"{c.amount_from:,.2f} {c.currency_from}")}</td>
                    <td><strong>{html.escape(f"{c.amount_to:,.2f} {c.currency_to}")}</strong></td>
                    <td>{c.rate:,.6f}</td>
                    <td>{html.escape(c.source)}</td>
                    <td>{stale_badge}</td>
                </tr>
                """
            conversions_html = f"""
            <section class="section">
                <h2>💱 1. Resumo das Conversões Cambiais</h2>
                <table>
                    <thead>
                        <tr>
                            <th>Origem</th>
                            <th>Destino (Nominal)</th>
                            <th>Taxa Comercial</th>
                            <th>Fonte</th>
                            <th>Status</th>
                        </tr>
                    </thead>
                    <tbody>{rows}</tbody>
                </table>
            </section>
            """

        costs_html = ""
        if data.cost_simulation:
            cs = data.cost_simulation
            safe_prof = html.escape(cs.profile_name)
            costs_html = f"""
            <section class="section">
                <h2>💳 2. Custos Efetivos e VET (BACEN)</h2>
                <p><strong>Perfil:</strong> {safe_prof} ({cs.operation_type.value.upper()})</p>
                <table>
                    <tbody>
                        <tr><td>Quantia Bruta Negociada</td><td><strong>{cs.amount_from:,.2f} {html.escape(cs.currency_from)}</strong></td></tr>
                        <tr><td>Taxa Comercial de Mercado</td><td>{cs.commercial_rate:,.6f}</td></tr>
                        <tr><td>Spread Cambial</td><td>{cs.spread_pct:.2f}% ({cs.spread_amount:,.6f}/un)</td></tr>
                        <tr><td>Taxa Efetiva com Spread</td><td>{cs.effective_rate:,.6f}</td></tr>
                        <tr><td>IOF Recolhido</td><td>{cs.iof_pct:.2f}% ({cs.iof_amount:,.2f})</td></tr>
                        <tr><td>Montante Líquido Final</td><td><strong style="color: #10b981;">{cs.net_amount_to:,.2f} {html.escape(cs.currency_to)}</strong></td></tr>
                        <tr><td>Custo Total Efetivo</td><td>{cs.total_cost_from:,.2f} {html.escape(cs.currency_from)}</td></tr>
                        <tr class="highlight-row"><td><strong>Valor Efetivo Total (VET)</strong></td><td><strong>{cs.vet:,.6f}</strong></td></tr>
                    </tbody>
                </table>
            </section>
            """

        salary_html = ""
        if data.salary_analysis:
            sa = data.salary_analysis
            diff_class = "positive" if sa.purchasing_power_diff_pct >= 0 else "negative"
            diff_sign = "+" if sa.purchasing_power_diff_pct >= 0 else ""
            salary_html = f"""
            <section class="section">
                <h2>🌍 3. Salário Internacional e Poder de Compra (PPP)</h2>
                <div class="card-grid">
                    <div class="card">
                        <div class="card-label">Salário Base ({html.escape(sa.country_from)})</div>
                        <div class="card-val">{sa.base_salary:,.2f} {html.escape(sa.base_currency)}</div>
                    </div>
                    <div class="card">
                        <div class="card-label">Salário Nominal ({html.escape(sa.country_to)})</div>
                        <div class="card-val">{sa.nominal_converted_salary:,.2f} {html.escape(sa.target_currency)}</div>
                    </div>
                    <div class="card">
                        <div class="card-label">Equivalente PPP (Banco Mundial)</div>
                        <div class="card-val" style="color: #38bdf8;">{sa.ppp_equivalent_salary:,.2f} {html.escape(sa.target_currency)}</div>
                    </div>
                    <div class="card">
                        <div class="card-label">Variação Real</div>
                        <div class="card-val {diff_class}">{diff_sign}{sa.purchasing_power_diff_pct:.1f}%</div>
                    </div>
                </div>
                <div class="callout">
                    <strong>Veredito:</strong> {html.escape(sa.verdict)}
                </div>
            </section>
            """

        notes_html = ""
        if safe_notes:
            notes_html = f"""
            <section class="section">
                <h2>📝 4. Observações Executivas</h2>
                <p style="white-space: pre-wrap; color: #475569;">{safe_notes}</p>
            </section>
            """

        return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <title>{safe_title}</title>
    <style>
        body {{
            font-family: system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            color: #1e293b;
            background: #ffffff;
            line-height: 1.5;
            padding: 2.5rem;
            max-width: 900px;
            margin: 0 auto;
        }}
        header {{
            border-bottom: 2px solid #e2e8f0;
            padding-bottom: 1.5rem;
            margin-bottom: 2rem;
        }}
        h1 {{ color: #0f172a; margin: 0 0 0.5rem 0; font-size: 1.8rem; }}
        .meta {{ color: #64748b; font-size: 0.85rem; }}
        .section {{ margin-bottom: 2.5rem; }}
        h2 {{ color: #0f172a; font-size: 1.25rem; border-bottom: 1px solid #e2e8f0; padding-bottom: 0.5rem; margin-bottom: 1rem; }}
        table {{ width: 100%; border-collapse: collapse; margin-top: 0.75rem; font-size: 0.9rem; }}
        th, td {{ padding: 0.6rem 0.8rem; text-align: left; border-bottom: 1px solid #e2e8f0; }}
        th {{ background: #f8fafc; font-weight: 600; color: #475569; }}
        .highlight-row {{ background: #f1f5f9; font-weight: bold; }}
        .badge {{ padding: 0.2rem 0.5rem; border-radius: 4px; font-size: 0.75rem; font-weight: 600; }}
        .badge-ok {{ background: #dcfce7; color: #166534; }}
        .badge-stale {{ background: #fef9c3; color: #854d0e; }}
        .card-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 1rem; margin-bottom: 1rem; }}
        .card {{ background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 1rem; }}
        .card-label {{ font-size: 0.75rem; color: #64748b; margin-bottom: 0.25rem; }}
        .card-val {{ font-size: 1.1rem; font-weight: bold; }}
        .positive {{ color: #16a34a; }}
        .negative {{ color: #dc2626; }}
        .callout {{ background: #f0fdf4; border-left: 4px solid #16a34a; padding: 0.9rem; border-radius: 4px; font-size: 0.9rem; }}
        @media print {{
            body {{ padding: 0; max-width: 100%; }}
            .section {{ page-break-inside: avoid; }}
        }}
    </style>
</head>
<body>
    <header>
        <h1>📑 {safe_title}</h1>
        <div class="meta">
            <span><strong>Emissão:</strong> {date_str}</span> • 
            <span><strong>Sistema:</strong> Câmbio Global (Zero-Auth / BACEN)</span>
        </div>
    </header>
    <main>
        {conversions_html}
        {costs_html}
        {salary_html}
        {notes_html}
    </main>
</body>
</html>"""

    def export_report_file(
        self,
        data: FinancialReportData,
        filename_or_path: str,
        fmt: str = "md",
    ) -> Path:
        """Exporta o relatório consolidado para arquivo físico de forma segura."""
        if fmt.lower() in ("html", "htm"):
            content = self.generate_html(data)
        else:
            content = self.generate_markdown(data)

        return self.storage.export_report_text(filename_or_path, content)
