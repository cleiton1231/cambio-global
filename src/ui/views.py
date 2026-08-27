"""
Renderização Visual no Terminal com a biblioteca Rich.

Responsabilidades:
- Exibir tabelas estilizadas de taxas de câmbio (Fiat e Cripto).
- Renderizar painéis comparativos de conversão nominal vs. Paridade de Poder de Compra (PPP).
- Exibir histórico, favoritos, spinners e mensagens de erro amigáveis sem stack traces.
"""

from decimal import Decimal
from typing import Any, Dict, List, Optional
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from src.models import ConversionRecord, ConversionResult, PPPResult


class TerminalViews:
    """Gerador de componentes visuais para o terminal utilizando Rich."""

    def __init__(self, console: Optional[Console] = None) -> None:
        self.console = console or Console()

    def render_welcome(self) -> None:
        """Renderiza o banner principal da aplicação."""
        banner_text = Text()
        banner_text.append("💱 CÂMBIO GLOBAL 🪙\n", style="bold cyan")
        banner_text.append("Fiat, Criptoativos & Paridade de Poder de Compra (PPP)\n", style="bold yellow")
        banner_text.append("─" * 55 + "\n", style="dim")
        banner_text.append("• Frankfurter API (BCE): Cotações Oficiais Fiat\n", style="green")
        banner_text.append("• CoinCap API: Criptoativos em Tempo Real\n", style="green")
        banner_text.append("• World Bank API: Indicadores Macroeconômicos & PPP\n", style="green")
        banner_text.append("• Zero Autenticação • Resiliência • Precisão Decimal\n", style="italic dim")

        self.console.print(Panel(banner_text, border_style="cyan", expand=False))

    def render_conversion_result(
        self,
        conversion: ConversionResult,
        ppp: Optional[PPPResult] = None,
    ) -> None:
        """Renderiza o painel formatado com o resultado da conversão e PPP."""
        table = Table(show_header=False, box=None, padding=(0, 2))
        table.add_column("Chave", style="bold white")
        table.add_column("Valor", style="bold yellow")

        table.add_row(
            "Origem:",
            f"{conversion.amount_from:,.2f} {conversion.currency_from}"
        )
        table.add_row(
            "Destino (Nominal):",
            f"[bold green]{conversion.amount_to:,.2f} {conversion.currency_to}[/bold green]"
        )
        table.add_row(
            "Taxa de Mercado:",
            f"1 {conversion.currency_from} = {conversion.rate:,.6f} {conversion.currency_to}"
        )
        table.add_row("Fonte da Cotação:", f"[italic]{conversion.source}[/italic]")

        if ppp:
            table.add_row("─" * 20, "─" * 30)
            table.add_row(
                "🌍 Equivalente PPP:",
                f"[bold magenta]{ppp.ppp_equivalent_amount:,.2f} {ppp.currency_to}[/bold magenta]"
            )
            table.add_row(
                "Taxa Teórica PPP:",
                f"1 {ppp.currency_from} = {ppp.ppp_rate:,.4f} {ppp.currency_to} (Ano Ref: {ppp.year})"
            )
            
            # Análise do Nível de Preços
            plr = ppp.price_level_ratio
            if plr > 1:
                cost_desc = f"[red]Destino {((plr - 1) * 100):.1f}% mais CARO em termos reais[/red]"
            elif plr < 1:
                cost_desc = f"[green]Destino {((1 - plr) * 100):.1f}% mais BARATO em termos reais[/green]"
            else:
                cost_desc = "[cyan]Poder de compra equiparado[/cyan]"

            table.add_row("Índice de Preços (PLR):", f"{plr:.2f} ({cost_desc})")

        title = " Resultado da Conversão Cambial "
        self.console.print(Panel(table, title=title, border_style="green", expand=False))

    def render_rates_table(self, base_currency: str, rates: Dict[str, Any]) -> None:
        """Renderiza a tabela de cotações fiduciárias."""
        table = Table(title=f"📈 Cotações em Relação a {base_currency.upper()} (Frankfurter/BCE)")
        table.add_column("Moeda", style="bold cyan")
        table.add_column("Taxa de Câmbio", justify="right", style="green")

        for curr, rate in sorted(rates.items()):
            table.add_row(curr, f"{Decimal(str(rate)):,.4f}")

        self.console.print(table)

    def render_crypto_table(self, assets: List[Dict[str, Any]]) -> None:
        """Renderiza a tabela com ranking e cotações de criptoativos."""
        table = Table(title="🪙 Principais Criptoativos em Tempo Real (CoinCap)")
        table.add_column("Rank", justify="center", style="dim")
        table.add_column("Ticker", style="bold yellow")
        table.add_column("Nome", style="white")
        table.add_column("Preço (USD)", justify="right", style="bold green")
        table.add_column("Variação 24h", justify="right")

        for asset in assets:
            rank = str(asset.get("rank", "-"))
            symbol = asset.get("symbol", "")
            name = asset.get("name", "")
            price = float(asset.get("priceUsd", 0.0))
            change = float(asset.get("changePercent24Hr", 0.0))

            change_style = "bold green" if change >= 0 else "bold red"
            change_str = f"[{change_style}]{change:+.2f}%[/{change_style}]"

            table.add_row(rank, symbol, name, f"${price:,.2f}", change_str)

        self.console.print(table)

    def render_history_table(self, history: List[ConversionRecord]) -> None:
        """Renderiza o histórico de conversões recentes."""
        if not history:
            self.console.print("[yellow]Nenhum registro no histórico de conversões.[/yellow]")
            return

        table = Table(title="📜 Histórico Recente de Conversões")
        table.add_column("Data/Hora", style="dim")
        table.add_column("De", style="cyan")
        table.add_column("Para", style="cyan")
        table.add_column("Quantia Original", justify="right")
        table.add_column("Convertido (Nominal)", justify="right", style="bold green")
        table.add_column("PPP Equivalente", justify="right", style="magenta")

        for rec in history:
            ppp_str = f"{rec.ppp_equivalent:,.2f}" if rec.ppp_equivalent else "-"
            table.add_row(
                rec.timestamp[:19].replace("T", " "),
                rec.from_currency,
                rec.to_currency,
                f"{rec.amount_from:,.2f}",
                f"{rec.amount_to:,.2f}",
                ppp_str,
            )

        self.console.print(table)

    def render_favorites(self, favorites: List[str]) -> None:
        """Exibe as moedas favoritas cadastradas."""
        if not favorites:
            self.console.print("[yellow]Nenhuma moeda favorita cadastrada.[/yellow]")
            return

        fav_str = " • ".join(f"[bold cyan]{fav}[/bold cyan]" for fav in favorites)
        self.console.print(Panel(fav_str, title="⭐ Moedas Favoritas", border_style="yellow", expand=False))

    def render_error(self, message: str) -> None:
        """Renderiza mensagem de erro destacada e segura."""
        self.console.print(Panel(f"[bold red]❌ Erro:[/bold red] {message}", border_style="red", expand=False))

    def render_success(self, message: str) -> None:
        """Renderiza mensagem de sucesso."""
        self.console.print(Panel(f"[bold green]✔[/bold green] {message}", border_style="green", expand=False))
