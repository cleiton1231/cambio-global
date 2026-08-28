"""
Calculadora de Salário Internacional, Relocation e Paridade de Poder de Compra (PPP).

Responsabilidades:
- Calcular a equivalência salarial entre países para manter o mesmo padrão de vida.
- Cruzar cotações de mercado (BCE/Frankfurter) com fatores PPP oficiais do Banco Mundial.
- Suporte à especificação de países específicos para moedas compartilhadas (ex: EUR em Portugal vs. Alemanha).
- Rejeição estrita de criptoativos (sem jurisdição macroeconômica).
"""

from decimal import Decimal
from typing import Optional

from src.api.frankfurter import FrankfurterClient
from src.api.world_bank import WorldBankClient
from src.converter import CurrencyConverter
from src.match import CurrencyMatcher, get_matcher
from src.models import (
    AssetType,
    SalaryEquivalencyResult,
    UnsupportedPPPAssetError,
)


class InternationalSalaryCalculator:
    """Calculadora de poder de compra e equivalência salarial internacional."""

    def __init__(
        self,
        converter: Optional[CurrencyConverter] = None,
        world_bank: Optional[WorldBankClient] = None,
        matcher: Optional[CurrencyMatcher] = None,
    ) -> None:
        self.converter = converter or CurrencyConverter()
        self.world_bank = world_bank or WorldBankClient()
        self.matcher = matcher or get_matcher()

    async def calculate_salary_equivalency(
        self,
        base_salary: Decimal,
        base_currency: str,
        target_currency: str,
        country_from: Optional[str] = None,
        country_to: Optional[str] = None,
    ) -> SalaryEquivalencyResult:
        """
        Calcula o salário equivalente e a variação real de poder de compra entre dois países.
        """
        if base_salary <= 0:
            raise ValueError(f"O salário base deve ser maior que zero. Informado: {base_salary}")

        from_info = self.matcher.match_strict(base_currency)
        to_info = self.matcher.match_strict(target_currency)

        # Rejeição de criptoativos em cálculos de salário PPP
        if from_info.asset_type == AssetType.CRYPTO:
            raise UnsupportedPPPAssetError(from_info.code)
        if to_info.asset_type == AssetType.CRYPTO:
            raise UnsupportedPPPAssetError(to_info.code)

        # Resolução de país (explícito ou padrão da moeda)
        c_from = (country_from.upper().strip() if country_from else from_info.default_country_code)
        c_to = (country_to.upper().strip() if country_to else to_info.default_country_code)

        if not c_from or not c_to:
            raise ValueError(
                f"Código ISO-3 de país não identificado para {from_info.code} ou {to_info.code}. "
                "Especifique country_from e country_to explicitamente."
            )

        # Busca fatores de conversão PPP do Banco Mundial
        ppp_from_data = await self.world_bank.get_ppp_conversion_factor(c_from)
        if not ppp_from_data:
            raise ValueError(f"Fator PPP do Banco Mundial não encontrado para o país '{c_from}'.")

        ppp_to_data = await self.world_bank.get_ppp_conversion_factor(c_to)
        if not ppp_to_data:
            raise ValueError(f"Fator PPP do Banco Mundial não encontrado para o país '{c_to}'.")

        ppp_factor_from = Decimal(str(ppp_from_data["value"]))
        ppp_factor_to = Decimal(str(ppp_to_data["value"]))
        ref_year = min(ppp_from_data.get("year", 2023), ppp_to_data.get("year", 2023))

        if ppp_factor_from <= 0:
            raise ValueError(f"Fator PPP inválido (<= 0) para o país '{c_from}'.")
        if ppp_factor_to <= 0:
            raise ValueError(f"Fator PPP inválido (<= 0) para o país '{c_to}'.")


        # Conversão nominal de mercado
        conv_res = await self.converter.convert(
            amount=base_salary,
            from_currency=from_info.code,
            to_currency=to_info.code,
        )

        nominal_converted_salary = conv_res.amount_to

        # Salário Teórico Equivalente pelo PPP: BaseSalary * (PPP_to / PPP_from)
        ppp_rate = ppp_factor_to / ppp_factor_from
        ppp_equivalent_salary = base_salary * ppp_rate

        # Índice do Nível de Preços (PLR = Nominal Rate / PPP Rate)
        plr = conv_res.rate / ppp_rate if ppp_rate > 0 else Decimal("1.0")

        # Diferença Percentual de Poder de Compra
        if ppp_equivalent_salary > 0:
            diff_pct = ((nominal_converted_salary - ppp_equivalent_salary) / ppp_equivalent_salary) * Decimal("100")
        else:
            diff_pct = Decimal("0")

        # Geração do Veredito Amigável
        if diff_pct >= 0:
            verdict = (
                f"Para manter o estilo de vida de {base_salary:,.2f} {from_info.code} em {c_from}, "
                f"você precisa de {ppp_equivalent_salary:,.2f} {to_info.code} em {c_to}. "
                f"No câmbio comercial ({nominal_converted_salary:,.2f} {to_info.code}), você terá um ganho real de +{diff_pct:.1f}% no poder de compra."
            )
        else:
            verdict = (
                f"O custo de vida em {c_to} é mais elevado. Para manter o mesmo padrão de {base_salary:,.2f} {from_info.code} em {c_from}, "
                f"seria necessário {ppp_equivalent_salary:,.2f} {to_info.code} (contra {nominal_converted_salary:,.2f} {to_info.code} no câmbio comercial, "
                f"déficit real de {abs(diff_pct):.1f}%)."
            )

        return SalaryEquivalencyResult(
            base_salary=base_salary,
            base_currency=from_info.code,
            target_currency=to_info.code,
            country_from=c_from,
            country_to=c_to,
            nominal_converted_salary=nominal_converted_salary,
            ppp_equivalent_salary=ppp_equivalent_salary,
            purchasing_power_diff_pct=diff_pct,
            price_level_ratio=plr,
            verdict=verdict,
            year=ref_year,
        )
