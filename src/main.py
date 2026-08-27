"""
Ponto de Entrada CLI, Comandos de Console e Menu Interativo do Câmbio Global.

Responsabilidades:
- Parsear argumentos de linha de comando (CLI) para conversões diretas, cestas e tendências.
- Fornecer menu interativo rico com navegação por teclado e Rich Console.
- Orquestrar integração assíncrona entre Matcher, Converter, Trend Analyzer, APIs e Storage.
- Executar servidor web FastAPI quando requisitado (--web).
"""

import argparse
import asyncio
from datetime import datetime, timezone
from decimal import Decimal
import sys
import uuid
from typing import List, Optional

from rich.console import Console
from rich.prompt import Prompt

from src.api.coincap import CoinCapClient
from src.api.frankfurter import FrankfurterClient
from src.api.world_bank import WorldBankClient
from src.converter import CurrencyConverter
from src.match import get_matcher
from src.models import (
    CambioGlobalError,
    ConversionRecord,
)
from src.storage import StorageManager
from src.trend import CurrencyTrendAnalyzer
from src.ui.views import TerminalViews


class CambioGlobalCLI:
    """Controlador principal da interface de linha de comando."""

    def __init__(self) -> None:
        self.console = Console()
        self.views = TerminalViews(console=self.console)
        self.matcher = get_matcher()
        self.frankfurter = FrankfurterClient()
        self.coincap = CoinCapClient()
        self.world_bank = WorldBankClient()
        self.converter = CurrencyConverter(
            matcher=self.matcher,
            frankfurter=self.frankfurter,
            coincap=self.coincap,
            world_bank=self.world_bank,
        )
        self.trend_analyzer = CurrencyTrendAnalyzer(
            matcher=self.matcher,
            frankfurter=self.frankfurter,
            coincap=self.coincap,
        )
        self.storage = StorageManager()

    async def execute_conversion(
        self,
        amount_str: str,
        from_curr: str,
        to_curr: str,
        with_ppp: bool = False,
    ) -> None:
        """Executa e renderiza uma conversão de moeda."""
        try:
            amount = Decimal(amount_str.replace(",", "."))
            if with_ppp:
                conv_res, ppp_res = await self.converter.convert_with_ppp(
                    amount=amount,
                    from_query=from_curr,
                    to_query=to_curr,
                )
                self.views.render_conversion_result(conv_res, ppp_res)
                
                # Salva no histórico
                rec = ConversionRecord(
                    id=str(uuid.uuid4())[:8],
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    from_currency=conv_res.currency_from,
                    to_currency=conv_res.currency_to,
                    amount_from=float(conv_res.amount_from),
                    amount_to=float(conv_res.amount_to),
                    rate=float(conv_res.rate),
                    ppp_equivalent=float(ppp_res.ppp_equivalent_amount),
                    country_from=ppp_res.country_from,
                    country_to=ppp_res.country_to,
                )
                self.storage.save_conversion_record(rec)
            else:
                conv_res = await self.converter.convert(
                    amount=amount,
                    from_currency=from_curr,
                    to_currency=to_curr,
                )
                self.views.render_conversion_result(conv_res)

                # Salva no histórico
                rec = ConversionRecord(
                    id=str(uuid.uuid4())[:8],
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    from_currency=conv_res.currency_from,
                    to_currency=conv_res.currency_to,
                    amount_from=float(conv_res.amount_from),
                    amount_to=float(conv_res.amount_to),
                    rate=float(conv_res.rate),
                )
                self.storage.save_conversion_record(rec)

        except (ValueError, CambioGlobalError) as err:
            self.views.render_error(str(err))
        except Exception as err:
            self.views.render_error(f"Erro inesperado durante a conversão: {str(err)}")

    async def execute_basket(
        self,
        amount_str: str,
        from_curr: str,
        targets: Optional[List[str]] = None,
    ) -> None:
        """Executa e renderiza a conversão para uma cesta de moedas."""
        try:
            amount = Decimal(amount_str.replace(",", "."))
            if not targets:
                # Usa favoritos ou lista padrão
                favs = self.storage.get_favorites()
                targets = favs if favs else ["BRL", "EUR", "GBP", "JPY", "BTC", "ETH"]

            with self.console.status("[cyan]Calculando conversões da cesta concorrentemente..."):
                basket_res = await self.converter.convert_basket(
                    amount=amount,
                    from_currency=from_curr,
                    target_currencies=targets,
                )
            self.views.render_basket_result(basket_res)
        except Exception as err:
            self.views.render_error(f"Erro ao processar cesta: {str(err)}")

    async def show_trend(
        self,
        from_curr: str,
        to_curr: str,
        days: int = 30,
    ) -> None:
        """Executa e renderiza a análise de tendência e sparklines."""
        try:
            with self.console.status(f"[cyan]Analisando série histórica de {from_curr}/{to_curr} ({days} dias)..."):
                trend_res = await self.trend_analyzer.analyze_trend(
                    from_currency=from_curr,
                    to_currency=to_curr,
                    days=days,
                )
            self.views.render_trend_analysis(trend_res)
        except Exception as err:
            self.views.render_error(f"Erro ao analisar tendência: {str(err)}")

    async def show_rates(self, base_currency: str = "USD") -> None:
        """Exibe cotações fiat atualizadas."""
        try:
            with self.console.status(f"[cyan]Buscando cotações em relação a {base_currency}..."):
                rates_data = await self.frankfurter.get_latest_rates(base=base_currency)
                self.views.render_rates_table(base_currency, rates_data.get("rates", {}))
        except Exception as err:
            self.views.render_error(f"Não foi possível obter cotações: {str(err)}")

    async def show_crypto(self, limit: int = 15) -> None:
        """Exibe os principais criptoativos da CoinCap."""
        try:
            with self.console.status("[cyan]Buscando criptoativos em tempo real..."):
                assets = await self.coincap.get_assets(limit=limit)
                self.views.render_crypto_table(assets)
        except Exception as err:
            self.views.render_error(f"Não foi possível obter dados cripto: {str(err)}")

    def show_history(self, limit: int = 20) -> None:
        """Exibe o histórico de conversões recentes."""
        history = self.storage.get_history(limit=limit)
        self.views.render_history_table(history)

    def show_favorites(self) -> None:
        """Exibe as moedas favoritas salvas."""
        favs = self.storage.get_favorites()
        self.views.render_favorites(favs)

    def add_favorite(self, code: str) -> None:
        """Adiciona uma moeda aos favoritos."""
        info = self.matcher.match(code)
        if not info:
            self.views.render_error(f"Moeda '{code}' não reconhecida.")
            return
        if self.storage.save_favorite(info.code):
            self.views.render_success(f"Moeda {info.code} ({info.name}) adicionada aos favoritos!")
        else:
            self.views.render_error(f"Moeda {info.code} já está nos favoritos.")

    async def interactive_menu(self) -> None:
        """Menu interativo principal no terminal."""
        while True:
            self.views.render_welcome()
            self.console.print("\n[bold cyan]Opções Disponíveis:[/bold cyan]")
            self.console.print("  [1] Converter Moedas (Fiat, Cripto ou PPP)")
            self.console.print("  [2] Cesta de Moedas Multi-Ativo (Basket)")
            self.console.print("  [3] Análise de Tendência & Sparklines (Histórico)")
            self.console.print("  [4] Cotações Oficiais Fiat (Frankfurter / BCE)")
            self.console.print("  [5] Criptoativos em Tempo Real (CoinCap)")
            self.console.print("  [6] Ver Histórico de Conversões")
            self.console.print("  [7] Moedas Favoritas")
            self.console.print("  [8] Iniciar Servidor Web & Dashboard SPA")
            self.console.print("  [0] Sair")

            choice = Prompt.ask("\nEscolha uma opção", choices=["1", "2", "3", "4", "5", "6", "7", "8", "0"], default="1")

            if choice == "0":
                self.console.print("[green]Até logo![/green]")
                break
            elif choice == "1":
                amount_str = Prompt.ask("Digite o valor", default="100")
                from_c = Prompt.ask("Moeda/Símbolo de Origem (ex: USD, R$, BTC)", default="USD")
                to_c = Prompt.ask("Moeda/Símbolo de Destino (ex: BRL, EUR, ETH)", default="BRL")
                calc_ppp = Prompt.ask("Calcular Paridade de Poder de Compra (PPP)? (s/n)", default="n").lower() == "s"
                await self.execute_conversion(amount_str, from_c, to_c, with_ppp=calc_ppp)
                Prompt.ask("\nPressione Enter para continuar...")
            elif choice == "2":
                amount_str = Prompt.ask("Digite o valor base", default="100")
                from_c = Prompt.ask("Moeda de Origem (ex: USD)", default="USD")
                targets_raw = Prompt.ask("Moedas de destino separadas por espaço (Enter para favoritos/padrão)", default="")
                targets = targets_raw.split() if targets_raw.strip() else None
                await self.execute_basket(amount_str, from_c, targets)
                Prompt.ask("\nPressione Enter para continuar...")
            elif choice == "3":
                from_c = Prompt.ask("Moeda de Origem (ex: USD)", default="USD")
                to_c = Prompt.ask("Moeda de Destino (ex: BRL)", default="BRL")
                days = int(Prompt.ask("Quantidade de dias (ex: 7, 30, 90)", default="30"))
                await self.show_trend(from_c, to_c, days=days)
                Prompt.ask("\nPressione Enter para continuar...")
            elif choice == "4":
                base = Prompt.ask("Moeda base para cotações", default="USD")
                await self.show_rates(base)
                Prompt.ask("\nPressione Enter para continuar...")
            elif choice == "5":
                limit = int(Prompt.ask("Quantidade de criptoativos", default="15"))
                await self.show_crypto(limit)
                Prompt.ask("\nPressione Enter para continuar...")
            elif choice == "6":
                self.show_history()
                Prompt.ask("\nPressione Enter para continuar...")
            elif choice == "7":
                self.show_favorites()
                sub = Prompt.ask("Deseja adicionar favorita? (Digite o código ou 'n')", default="n")
                if sub.lower() != "n":
                    self.add_favorite(sub)
                Prompt.ask("\nPressione Enter para continuar...")
            elif choice == "8":
                start_web_server()
                break


def start_web_server(host: str = "127.0.0.1", port: int = 8000) -> None:
    """Inicializa o servidor FastAPI com Uvicorn."""
    import uvicorn
    print(f"Iniciando Câmbio Global Web em http://{host}:{port} ...")
    uvicorn.run("src.web.app:app", host=host, port=port, reload=False)


def main(args: Optional[List[str]] = None) -> int:
    """Ponto de entrada do executável CLI."""
    if args is None:
        args = sys.argv[1:]

    parser = argparse.ArgumentParser(
        description="Câmbio Global - Conversor de Moedas Fiat, Criptoativos, Cestas e Análise de Tendências"
    )
    parser.add_argument("--convert", nargs=3, metavar=("AMOUNT", "FROM", "TO"), help="Converte um valor entre duas moedas")
    parser.add_argument("--ppp", action="store_true", help="Inclui análise de Paridade de Poder de Compra (PPP) do Banco Mundial")
    parser.add_argument("--basket", nargs="+", metavar="ITEM", help="Converte valor para uma cesta de moedas: AMOUNT BASE [TARGETS...]")
    parser.add_argument("--trend", nargs="+", metavar="ARG", help="Analisa tendência histórica: FROM TO [DAYS]")

    parser.add_argument("--rates", nargs="?", const="USD", metavar="BASE", help="Exibe cotações fiat atuais")
    parser.add_argument("--crypto", type=int, nargs="?", const=15, metavar="LIMIT", help="Exibe cotações de criptoativos")
    parser.add_argument("--history", type=int, nargs="?", const=20, metavar="LIMIT", help="Exibe histórico de conversões")
    parser.add_argument("--export-json", metavar="FILE", help="Exporta histórico para arquivo JSON")
    parser.add_argument("--export-csv", metavar="FILE", help="Exporta histórico para arquivo CSV")
    parser.add_argument("--fav", nargs="*", metavar="ACTION", help="Gerencia favoritos: list, add <CODE>, rm <CODE>")
    parser.add_argument("--web", action="store_true", help="Inicia o servidor web REST API e Dashboard SPA")
    parser.add_argument("--host", default="127.0.0.1", help="Host do servidor web (padrão: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8000, help="Porta do servidor web (padrão: 8000)")

    parsed = parser.parse_args(args)
    cli = CambioGlobalCLI()

    if parsed.web:
        start_web_server(host=parsed.host, port=parsed.port)
        return 0

    if parsed.convert:
        amount_s, from_c, to_c = parsed.convert
        asyncio.run(cli.execute_conversion(amount_s, from_c, to_c, with_ppp=parsed.ppp))
        return 0

    if parsed.basket:
        amount_s = parsed.basket[0]
        from_c = parsed.basket[1] if len(parsed.basket) > 1 else "USD"
        targets = parsed.basket[2:] if len(parsed.basket) > 2 else None
        asyncio.run(cli.execute_basket(amount_s, from_c, targets))
        return 0

    if parsed.trend:
        from_c = parsed.trend[0]
        to_c = parsed.trend[1] if len(parsed.trend) > 1 else "BRL"
        days = int(parsed.trend[2]) if len(parsed.trend) > 2 else 30
        asyncio.run(cli.show_trend(from_c, to_c, days=days))
        return 0

    if parsed.rates:
        asyncio.run(cli.show_rates(parsed.rates))
        return 0

    if parsed.crypto is not None:
        asyncio.run(cli.show_crypto(parsed.crypto))
        return 0

    if parsed.history is not None:
        cli.show_history(parsed.history)
        return 0

    if parsed.export_json:
        path = cli.storage.export_history_json(parsed.export_json)
        cli.views.render_success(f"Histórico exportado com sucesso para: {path}")
        return 0

    if parsed.export_csv:
        path = cli.storage.export_history_csv(parsed.export_csv)
        cli.views.render_success(f"Histórico exportado com sucesso para: {path}")
        return 0

    if parsed.fav is not None:
        if not parsed.fav or parsed.fav[0] == "list":
            cli.show_favorites()
        elif parsed.fav[0] == "add" and len(parsed.fav) > 1:
            cli.add_favorite(parsed.fav[1])
        elif parsed.fav[0] == "rm" and len(parsed.fav) > 1:
            if cli.storage.remove_favorite(parsed.fav[1]):
                cli.views.render_success(f"Moeda {parsed.fav[1]} removida dos favoritos.")
            else:
                cli.views.render_error(f"Moeda {parsed.fav[1]} não estava nos favoritos.")
        return 0

    # Se nenhum argumento foi passado, entra no menu interativo
    asyncio.run(cli.interactive_menu())
    return 0


if __name__ == "__main__":
    sys.exit(main())
