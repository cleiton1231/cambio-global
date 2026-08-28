"""
Simulador de Custos Financeiros Reais, IOF, Spread Cambial e VET (BACEN).

Responsabilidades:
- Perfis pré-definidos de mercado (Cartão Internacional, Conta Global/Wise, Investimentos, Salário do Exterior).
- Cálculo exato do Valor Efetivo Total (VET) para operações de compra (Outbound) e recebimento de remessa (Inbound).
- Precisão decimal estrita com proteção contra valores negativos e divisão por zero.
"""

from decimal import Decimal
from typing import Dict, Optional

from src.converter import CurrencyConverter
from src.match import CurrencyMatcher, get_matcher
from src.models import (
    CostSimulationResult,
    OperationType,
    TransactionProfile,
)

# ============================================================================
# Perfis Pré-configurados de Mercado
# ============================================================================

DEFAULT_PROFILES: Dict[str, TransactionProfile] = {
    "credit_card": TransactionProfile(
        name="Cartão de Crédito Internacional",
        description="Compras internacionais no cartão de crédito físico/virtual (IOF 4.38% + Spread 4.0%)",
        iof_pct=Decimal("4.38"),
        spread_pct=Decimal("4.00"),
        fixed_fee=Decimal("0.00"),
        operation_type=OperationType.OUTBOUND,
    ),
    "global_account": TransactionProfile(
        name="Conta Global / Débito (Wise, Nomad)",
        description="Envio ou conversão em conta internacional multimoeda (IOF 1.10% + Spread 1.50%)",
        iof_pct=Decimal("1.10"),
        spread_pct=Decimal("1.50"),
        fixed_fee=Decimal("0.00"),
        operation_type=OperationType.OUTBOUND,
    ),
    "investment": TransactionProfile(
        name="Remessa para Investimentos no Exterior",
        description="Transferência de patrimônio para corretoras internacionais (IOF 0.38% + Spread 1.00%)",
        iof_pct=Decimal("0.38"),
        spread_pct=Decimal("1.00"),
        fixed_fee=Decimal("0.00"),
        operation_type=OperationType.OUTBOUND,
    ),
    "inbound_salary": TransactionProfile(
        name="Recebimento de Salário / Freelance do Exterior",
        description="Recebimento de remessa de trabalho internacional convertido em BRL (IOF 0.38% + Spread 1.20%)",
        iof_pct=Decimal("0.38"),
        spread_pct=Decimal("1.20"),
        fixed_fee=Decimal("0.00"),
        operation_type=OperationType.INBOUND,
    ),
    "crypto_p2p": TransactionProfile(
        name="Cripto P2P / Balcão",
        description="Negociação direta de criptoativos e stablecoins (IOF 0.00% + Spread 0.75%)",
        iof_pct=Decimal("0.00"),
        spread_pct=Decimal("0.75"),
        fixed_fee=Decimal("0.00"),
        operation_type=OperationType.OUTBOUND,
    ),
}


class CostSimulator:
    """Motor de cálculo de custos cambiais e VET."""

    def __init__(
        self,
        converter: Optional[CurrencyConverter] = None,
        matcher: Optional[CurrencyMatcher] = None,
    ) -> None:
        self.converter = converter or CurrencyConverter()
        self.matcher = matcher or get_matcher()

    def get_profiles(self) -> Dict[str, TransactionProfile]:
        """Retorna os perfis de transação disponíveis."""
        return DEFAULT_PROFILES

    async def simulate(
        self,
        amount: Decimal,
        from_currency: str,
        to_currency: str,
        profile_key: Optional[str] = "global_account",
        custom_iof: Optional[Decimal] = None,
        custom_spread: Optional[Decimal] = None,
        custom_fee: Optional[Decimal] = None,
        operation_type: Optional[OperationType] = None,
    ) -> CostSimulationResult:
        """
        Executa a simulação completa de custos cambiais com cálculo do VET.
        """
        if amount <= 0:
            raise ValueError(f"A quantia para simulação deve ser maior que zero. Informado: {amount}")

        # 1. Resolve o perfil ou parâmetros customizados
        if profile_key and profile_key.lower() in DEFAULT_PROFILES:
            base_profile = DEFAULT_PROFILES[profile_key.lower()]
            iof_pct = custom_iof if custom_iof is not None else base_profile.iof_pct
            spread_pct = custom_spread if custom_spread is not None else base_profile.spread_pct
            fixed_fee = custom_fee if custom_fee is not None else base_profile.fixed_fee
            op_type = operation_type or base_profile.operation_type
            profile_name = base_profile.name
        else:
            iof_pct = custom_iof if custom_iof is not None else Decimal("1.10")
            spread_pct = custom_spread if custom_spread is not None else Decimal("1.50")
            fixed_fee = custom_fee if custom_fee is not None else Decimal("0.00")
            op_type = operation_type or OperationType.OUTBOUND
            profile_name = "Personalizado"

        if iof_pct < 0 or spread_pct < 0 or fixed_fee < 0:
            raise ValueError("Alíquotas de IOF, Spread e taxas fixas não podem ser negativas.")
        if iof_pct >= 100 or spread_pct >= 100:
            raise ValueError("Alíquotas de IOF e Spread devem ser estritamente menores que 100%.")


        # 2. Obtém cotação comercial pura de mercado
        from_info = self.matcher.match_strict(from_currency)
        to_info = self.matcher.match_strict(to_currency)

        conv_res = await self.converter.convert(
            amount=amount,
            from_currency=from_info.code,
            to_currency=to_info.code,
        )
        commercial_rate = conv_res.rate

        # 3. Cálculo das grandezas financeiras e VET conforme a direção
        if op_type == OperationType.INBOUND:
            # Recebimento de remessa do exterior (ex: 1.000 USD -> BRL)
            spread_factor = Decimal("1") - (spread_pct / Decimal("100"))
            effective_rate = commercial_rate * spread_factor
            spread_amount = commercial_rate - effective_rate

            gross_amount_to = amount * effective_rate
            iof_amount = gross_amount_to * (iof_pct / Decimal("100"))
            net_amount_to = max(Decimal("0"), gross_amount_to - iof_amount - fixed_fee)
            total_cost_from = amount

            # VET = Valor Líquido Recebido em BRL / Quantia em Moeda Estrangeira
            vet = net_amount_to / amount if amount > 0 else Decimal("0")

        else:
            # Compra de moeda estrangeira / Envio de recursos (Outbound)
            spread_factor = Decimal("1") - (spread_pct / Decimal("100"))
            effective_rate = commercial_rate * spread_factor
            spread_amount = commercial_rate - effective_rate

            net_amount_to = amount * effective_rate
            iof_amount = amount * (iof_pct / Decimal("100"))
            total_cost_from = amount + iof_amount + fixed_fee

            # VET = Custo Total em Moeda de Origem / Quantia Líquida Entregue no Destino
            vet = total_cost_from / net_amount_to if net_amount_to > 0 else Decimal("0")

        return CostSimulationResult(
            amount_from=amount,
            currency_from=from_info.code,
            amount_to=conv_res.amount_to,
            currency_to=to_info.code,
            operation_type=op_type,
            commercial_rate=commercial_rate,
            spread_pct=spread_pct,
            spread_amount=spread_amount,
            effective_rate=effective_rate,
            iof_pct=iof_pct,
            iof_amount=iof_amount,
            fixed_fee=fixed_fee,
            net_amount_to=net_amount_to,
            total_cost_from=total_cost_from,
            vet=vet,
            profile_name=profile_name,
        )
