"""
Ponto de Entrada CLI, Comandos de Console e Menu Interativo do Câmbio Global.

Responsabilidades:
- Parsear argumentos de linha de comando (CLI) para conversões diretas, cestas, tendências, custos (VET), salários (PPP) e relatórios.
- Fornecer menu interativo rico com navegação por teclado e Rich Console.
- Orquestrar integração assíncrona entre Matcher, Converter, CostSimulator, SalaryCalculator, TrendAnalyzer, Reporter e Storage.
- Executar servidor web FastAPI quando requisitado (--web).
"""

import argparse
import asyncio
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
import sys
import uuid
from typing import List, Optional

from rich.console import Console
from rich.prompt import Prompt

from src.api.coincap import CoinCapClient
from src.api.frankfurter import FrankfurterClient
from src.api.world_bank import WorldBankClient
from src.converter import CurrencyConverter
from src.costs import CostSimulator
from src.match import get_matcher
from src.models import (
    CambioGlobalError,
    ConversionRecord,
    FinancialReportData,
    OperationType,
)
from src.reporter import FinancialReportGenerator
from src.salary import InternationalSalaryCalculator
from src.storage import StorageManager
from src.trend import CurrencyTrendAnalyzer
from src.ui.views import TerminalViews


def parse_safe_decimal(
    val_str: str,
    param_name: str = "Valor",
    min_val: Optional[Decimal] = None,
    max_val: Optional[Decimal] = Decimal("1e18"),
) -> Decimal:
    """Valida e converte string para Decimal de forma estrita, rejeitando NaN, Infinity e overflow."""
    if not val_str:
        raise ValueError(f"{param_name} não pode ser vazio.")

    clean_str = str(val_str).strip().replace(",", ".")
    lower_str = clean_str.lower()
    if lower_str in ("nan", "snan", "inf", "-inf", "+inf", "infinity", "-infinity", "+infinity"):
        raise ValueError(f"{param_name} inválido: valores não-finitos (NaN/Infinity) são proibidos.")

    try:
        val = Decimal(clean_str)
    except Exception:
        raise ValueError(f"{param_name} inválido: '{val_str}' não é um número decimal válido.")

    if not val.is_finite():
        raise ValueError(f"{param_name} inválido: número não-finito.")

    if min_val is not None and val < min_val:
        raise ValueError(f"{param_name} deve ser maior ou igual a {min_val}.")

    if max_val is not None and val > max_val:
        raise ValueError(f"{param_name} excede o limite máximo permitido ({max_val}).")

    return val


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
        self.cost_simulator = CostSimulator(
            converter=self.converter,
            matcher=self.matcher,
        )
        self.salary_calculator = InternationalSalaryCalculator(
            converter=self.converter,
            world_bank=self.world_bank,
            matcher=self.matcher,
        )
        self.trend_analyzer = CurrencyTrendAnalyzer(
            matcher=self.matcher,
            frankfurter=self.frankfurter,
            coincap=self.coincap,
        )
        self.storage = StorageManager()
        self.reporter = FinancialReportGenerator(storage=self.storage)

    async def execute_conversion(
        self,
        amount_str: str,
        from_curr: str,
        to_curr: str,
        with_ppp: bool = False,
    ) -> None:
        """Executa e renderiza uma conversão de moeda."""
        try:
            amount = parse_safe_decimal(amount_str, "Quantia a converter", min_val=Decimal("0.000000000000000001"))
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

    async def execute_simulation(
        self,
        amount_str: str,
        from_curr: str,
        to_curr: str,
        profile: str = "global_account",
        iof_str: Optional[str] = None,
        spread_str: Optional[str] = None,
        fee_str: Optional[str] = None,
        is_inbound: bool = False,
    ) -> None:
        """Executa simulação de custos, IOF, spread e VET."""
        try:
            amount = parse_safe_decimal(amount_str, "Quantia da simulação", min_val=Decimal("0.01"))
            iof = parse_safe_decimal(iof_str, "IOF", min_val=Decimal("0")) if iof_str else None
            spread = parse_safe_decimal(spread_str, "Spread", min_val=Decimal("0")) if spread_str else None
            fee = parse_safe_decimal(fee_str, "Tarifa fixa", min_val=Decimal("0")) if fee_str else None
            op_type = OperationType.INBOUND if is_inbound else None

            sim_res = await self.cost_simulator.simulate(
                amount=amount,
                from_currency=from_curr,
                to_currency=to_curr,
                profile_key=profile,
                custom_iof=iof,
                custom_spread=spread,
                custom_fee=fee,
                operation_type=op_type,
            )
            self.views.render_cost_simulation(sim_res)
        except Exception as err:
            self.views.render_error(f"Erro ao simular custos: {str(err)}")

    async def execute_salary(
        self,
        amount_str: str,
        base_curr: str,
        target_curr: str,
        country_from: Optional[str] = None,
        country_to: Optional[str] = None,
    ) -> None:
        """Executa cálculo de salário internacional e relocation."""
        try:
            amount = parse_safe_decimal(amount_str, "Salário base", min_val=Decimal("0.01"))
            sal_res = await self.salary_calculator.calculate_salary_equivalency(
                base_salary=amount,
                base_currency=base_curr,
                target_currency=target_curr,
                country_from=country_from,
                country_to=country_to,
            )
            self.views.render_salary_equivalency(sal_res)
        except Exception as err:
            self.views.render_error(f"Erro ao calcular salário internacional: {str(err)}")

    async def generate_report_file(
        self,
        filename: str,
        fmt: str = "md",
        amount_str: str = "1000",
        from_curr: str = "USD",
        to_curr: str = "BRL",
        title: str = "Relatório Executivo Financeiro",
    ) -> None:
        """Gera e exporta relatório executivo completo."""
        try:
            amount = parse_safe_decimal(amount_str, "Quantia do relatório", min_val=Decimal("0.01"))
            conv_res = await self.converter.convert(amount, from_curr, to_curr)
            sim_res = await self.cost_simulator.simulate(amount, from_curr, to_curr, profile_key="global_account")
            sal_res = None
            try:
                sal_res = await self.salary_calculator.calculate_salary_equivalency(amount, from_curr, to_curr)
            except Exception:
                pass

            data = FinancialReportData(
                title=title,
                created_at=datetime.now(timezone.utc),
                conversions=[conv_res],
                cost_simulation=sim_res,
                salary_analysis=sal_res,
                notes="Relatório gerado via Câmbio Global CLI.",
            )

            out_path = self.reporter.export_report_file(data, filename, fmt=fmt)
            self.views.render_success(f"Relatório ({fmt.upper()}) exportado com sucesso para: {out_path}")
        except Exception as err:
            self.views.render_error(f"Erro ao gerar relatório: {str(err)}")

    async def execute_basket(
        self,
        amount_str: str,
        from_curr: str,
        targets: Optional[List[str]] = None,
    ) -> None:
        """Executa e renderiza a conversão para uma cesta de moedas."""
        try:
            amount = parse_safe_decimal(amount_str, "Quantia da cesta", min_val=Decimal("0.000000000000000001"))
            if not targets:
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
            self.console.print("  [2] Simulador de Custos Reais (IOF, Spread & VET)")
            self.console.print("  [3] Calculadora de Salário Internacional & Relocation")
            self.console.print("  [4] Cesta de Moedas Multi-Ativo (Basket)")
            self.console.print("  [5] Análise de Tendência & Sparklines (Histórico)")
            self.console.print("  [6] Exportar Relatório Executivo (Markdown/HTML)")
            self.console.print("  [7] Cotações Oficiais Fiat (Frankfurter / BCE)")
            self.console.print("  [8] Criptoativos em Tempo Real (CoinCap)")
            self.console.print("  [9] Histórico & Favoritos")
            self.console.print("  [10] Iniciar Servidor Web & Dashboard SPA")
            self.console.print("  [0] Sair")

            choice = Prompt.ask("\nEscolha uma opção", choices=["1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "0"], default="1")

            if choice == "0":
                self.console.print("[green]Até logo![/green]")
                break
            elif choice == "1":
                amount_str = Prompt.ask("Digite o valor", default="100")
                from_c = Prompt.ask("Moeda de Origem (ex: USD, R$, BTC)", default="USD")
                to_c = Prompt.ask("Moeda de Destino (ex: BRL, EUR, ETH)", default="BRL")
                calc_ppp = Prompt.ask("Calcular Paridade de Poder de Compra (PPP)? (s/n)", default="n").lower() == "s"
                await self.execute_conversion(amount_str, from_c, to_c, with_ppp=calc_ppp)
                Prompt.ask("\nPressione Enter para continuar...")
            elif choice == "2":
                amount_str = Prompt.ask("Quantia a negociar", default="1000")
                from_c = Prompt.ask("Moeda de Origem", default="BRL")
                to_c = Prompt.ask("Moeda de Destino", default="USD")
                self.console.print("[dim]Perfis: global_account, credit_card, investment, inbound_salary, crypto_p2p[/dim]")
                prof = Prompt.ask("Perfil de Custo", default="global_account")
                await self.execute_simulation(amount_str, from_c, to_c, profile=prof)
                Prompt.ask("\nPressione Enter para continuar...")
            elif choice == "3":
                amount_str = Prompt.ask("Salário Base", default="5000")
                from_c = Prompt.ask("Moeda Atual", default="USD")
                to_c = Prompt.ask("Moeda Destino", default="BRL")
                await self.execute_salary(amount_str, from_c, to_c)
                Prompt.ask("\nPressione Enter para continuar...")
            elif choice == "4":
                amount_str = Prompt.ask("Digite o valor base", default="100")
                from_c = Prompt.ask("Moeda de Origem (ex: USD)", default="USD")
                targets_raw = Prompt.ask("Moedas de destino separadas por espaço (Enter para favoritos/padrão)", default="")
                targets = targets_raw.split() if targets_raw.strip() else None
                await self.execute_basket(amount_str, from_c, targets)
                Prompt.ask("\nPressione Enter para continuar...")
            elif choice == "5":
                from_c = Prompt.ask("Moeda de Origem (ex: USD)", default="USD")
                to_c = Prompt.ask("Moeda de Destino (ex: BRL)", default="BRL")
                days = int(Prompt.ask("Quantidade de dias (ex: 7, 30, 90)", default="30"))
                await self.show_trend(from_c, to_c, days=days)
                Prompt.ask("\nPressione Enter para continuar...")
            elif choice == "6":
                filename = Prompt.ask("Nome do arquivo de saída (ex: relatorio.html ou relatorio.md)", default="relatorio_financeiro.html")
                fmt = "html" if filename.endswith(".html") else "md"
                await self.generate_report_file(filename, fmt=fmt)
                Prompt.ask("\nPressione Enter para continuar...")
            elif choice == "7":
                base = Prompt.ask("Moeda base para cotações", default="USD")
                await self.show_rates(base)
                Prompt.ask("\nPressione Enter para continuar...")
            elif choice == "8":
                limit = int(Prompt.ask("Quantidade de criptoativos", default="15"))
                await self.show_crypto(limit)
                Prompt.ask("\nPressione Enter para continuar...")
            elif choice == "9":
                self.show_history()
                self.show_favorites()
                Prompt.ask("\nPressione Enter para continuar...")
            elif choice == "10":
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
        description="Câmbio Global - Conversor de Moedas Fiat, Criptoativos, VET, Salários e Relatórios"
    )
    parser.add_argument("--convert", nargs=3, metavar=("AMOUNT", "FROM", "TO"), help="Converte um valor entre duas moedas")
    parser.add_argument("--ppp", action="store_true", help="Inclui análise de Paridade de Poder de Compra (PPP) do Banco Mundial")
    parser.add_argument("--simulate", nargs=3, metavar=("AMOUNT", "FROM", "TO"), help="Simula custos e VET: AMOUNT FROM TO")
    parser.add_argument("--profile", default="global_account", help="Perfil da simulação (global_account, credit_card, investment, inbound_salary)")
    parser.add_argument("--iof", help="Alíquota customizada de IOF em %% (ex: 1.1)")
    parser.add_argument("--spread", help="Spread customizado em %% (ex: 1.5)")
    parser.add_argument("--fee", help="Tarifa fixa bancária em moeda de origem (ex: 10.0)")
    parser.add_argument("--inbound", action="store_true", help="Declara operação como recebimento de remessa do exterior (Inbound)")

    parser.add_argument("--salary", nargs=3, metavar=("AMOUNT", "BASE", "TARGET"), help="Calcula salário equivalente: AMOUNT BASE TARGET")
    parser.add_argument("--country-from", help="Código ISO-3 opcional do país de origem (ex: USA, BRA)")
    parser.add_argument("--country-to", help="Código ISO-3 opcional do país de destino (ex: PRT, DEU)")

    parser.add_argument("--basket", nargs="+", metavar="ITEM", help="Converte valor para uma cesta de moedas: AMOUNT BASE [TARGETS...]")
    parser.add_argument("--trend", nargs="+", metavar="ARG", help="Analisa tendência histórica: FROM TO [DAYS]")

    parser.add_argument("--report-md", metavar="FILE", help="Gera relatório executivo em Markdown")
    parser.add_argument("--report-html", metavar="FILE", help="Gera relatório executivo em HTML (pronto para PDF)")

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

    if parsed.simulate:
        amount_s, from_c, to_c = parsed.simulate
        asyncio.run(
            cli.execute_simulation(
                amount_s, from_c, to_c,
                profile=parsed.profile,
                iof_str=parsed.iof,
                spread_str=parsed.spread,
                fee_str=parsed.fee,
                is_inbound=parsed.inbound,
            )
        )
        return 0

    if parsed.salary:
        amount_s, base_c, target_c = parsed.salary
        asyncio.run(
            cli.execute_salary(
                amount_s, base_c, target_c,
                country_from=parsed.country_from,
                country_to=parsed.country_to,
            )
        )
        return 0

    if parsed.report_md:
        asyncio.run(cli.generate_report_file(parsed.report_md, fmt="md"))
        return 0

    if parsed.report_html:
        asyncio.run(cli.generate_report_file(parsed.report_html, fmt="html"))
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
