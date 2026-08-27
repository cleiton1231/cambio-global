"""
Mecanismo de Conversão Cambial, Arbitragem e Paridade de Poder de Compra (PPP).

Responsabilidades:
- Executar conversão entre moedas fiduciárias diretas e cruzadas.
- Executar conversão híbrida (Fiat <-> Cripto, Cripto <-> Cripto).
- Calcular equivalência de Paridade de Poder de Compra (PPP) ajustada pelo Banco Mundial.
- Garantir precisão numérica estrita com Decimal.
"""

import asyncio
from decimal import Decimal, getcontext
from typing import Any, Dict, List, Optional, Tuple

from src.api.coincap import CoinCapClient
from src.api.frankfurter import FrankfurterClient
from src.api.world_bank import WorldBankClient
from src.match import CurrencyMatcher, get_matcher
from src.models import (
    AssetType,
    BasketItemResult,
    BasketResult,
    ConversionResult,
    ExchangeRate,
    InvalidExchangeRateError,
    PPPResult,
    UnsupportedPPPAssetError,
)


# Define a precisão aritmética padrão
getcontext().prec = 28


class CurrencyConverter:
    """Núcleo de cálculo de conversão cambial e Paridade de Poder de Compra (PPP)."""

    def __init__(
        self,
        matcher: Optional[CurrencyMatcher] = None,
        frankfurter: Optional[FrankfurterClient] = None,
        coincap: Optional[CoinCapClient] = None,
        world_bank: Optional[WorldBankClient] = None,
    ) -> None:
        self.matcher = matcher or get_matcher()
        self.frankfurter = frankfurter or FrankfurterClient()
        self.coincap = coincap or CoinCapClient()
        self.world_bank = world_bank or WorldBankClient()

    async def convert(
        self,
        amount: Decimal,
        from_currency: str,
        to_currency: str,
    ) -> ConversionResult:
        """
        Converte uma quantia monetária entre duas moedas (Fiat ou Cripto).
        """
        if amount <= 0:
            raise ValueError(f"A quantia a ser convertida deve ser maior que zero. Recebido: {amount}")

        from_info = self.matcher.match_strict(from_currency)
        to_info = self.matcher.match_strict(to_currency)

        # 1. Mesma moeda
        if from_info.code == to_info.code:
            return ConversionResult(
                amount_from=amount,
                currency_from=from_info.code,
                amount_to=amount,
                currency_to=to_info.code,
                rate=Decimal("1.0"),
                source="identity",
            )

        # 2. Conversão Fiat <-> Fiat
        if from_info.asset_type == AssetType.FIAT and to_info.asset_type == AssetType.FIAT:
            rate_obj = await self.frankfurter.get_rate(from_info.code, to_info.code)
            rate_val = rate_obj.rate
            if rate_val <= 0:
                raise InvalidExchangeRateError(f"Taxa inválida recebida para {from_info.code}->{to_info.code}")

            amount_to = amount * rate_val
            return ConversionResult(
                amount_from=amount,
                currency_from=from_info.code,
                amount_to=amount_to,
                currency_to=to_info.code,
                rate=rate_val,
                source="frankfurter",
            )

        # 3. Conversão Cripto <-> Cripto
        if from_info.asset_type == AssetType.CRYPTO and to_info.asset_type == AssetType.CRYPTO:
            rate_from_usd = await self.coincap.get_rate_in_usd(from_info.code)
            rate_to_usd = await self.coincap.get_rate_in_usd(to_info.code)

            if rate_to_usd.rate <= 0:
                raise InvalidExchangeRateError(f"Taxa USD para {to_info.code} inválida.")

            rate_val = rate_from_usd.rate / rate_to_usd.rate
            amount_to = amount * rate_val
            return ConversionResult(
                amount_from=amount,
                currency_from=from_info.code,
                amount_to=amount_to,
                currency_to=to_info.code,
                rate=rate_val,
                source="coincap_cross",
            )

        # 4. Conversão Cripto -> Fiat
        if from_info.asset_type == AssetType.CRYPTO and to_info.asset_type == AssetType.FIAT:
            crypto_rate_usd = await self.coincap.get_rate_in_usd(from_info.code)

            if to_info.code == "USD":
                rate_val = crypto_rate_usd.rate
                source = "coincap"
            else:
                fiat_usd_rate = await self.frankfurter.get_rate("USD", to_info.code)
                rate_val = crypto_rate_usd.rate * fiat_usd_rate.rate
                source = "coincap_frankfurter"

            amount_to = amount * rate_val
            return ConversionResult(
                amount_from=amount,
                currency_from=from_info.code,
                amount_to=amount_to,
                currency_to=to_info.code,
                rate=rate_val,
                source=source,
            )

        # 5. Conversão Fiat -> Cripto
        if from_info.asset_type == AssetType.FIAT and to_info.asset_type == AssetType.CRYPTO:
            crypto_rate_usd = await self.coincap.get_rate_in_usd(to_info.code)
            if crypto_rate_usd.rate <= 0:
                raise InvalidExchangeRateError(f"Taxa USD para cripto {to_info.code} inválida.")

            if from_info.code == "USD":
                rate_val = Decimal("1.0") / crypto_rate_usd.rate
                source = "coincap"
            else:
                fiat_to_usd = await self.frankfurter.get_rate(from_info.code, "USD")
                rate_val = fiat_to_usd.rate / crypto_rate_usd.rate
                source = "frankfurter_coincap"

            amount_to = amount * rate_val
            return ConversionResult(
                amount_from=amount,
                currency_from=from_info.code,
                amount_to=amount_to,
                currency_to=to_info.code,
                rate=rate_val,
                source=source,
            )

        raise ValueError(f"Combinação de conversão não suportada: {from_info.code} -> {to_info.code}")

    async def convert_with_ppp(
        self,
        amount: Decimal,
        from_query: str,
        to_query: str,
        country_from: Optional[str] = None,
        country_to: Optional[str] = None,
    ) -> Tuple[ConversionResult, PPPResult]:
        """
        Executa a conversão nominal e calcula a Paridade de Poder de Compra (PPP).
        """
        from_info = self.matcher.match_strict(from_query)
        to_info = self.matcher.match_strict(to_query)

        if from_info.asset_type == AssetType.CRYPTO:
            raise UnsupportedPPPAssetError(from_info.code)
        if to_info.asset_type == AssetType.CRYPTO:
            raise UnsupportedPPPAssetError(to_info.code)

        c_from = (country_from or from_info.default_country_code)
        c_to = (country_to or to_info.default_country_code)

        if not c_from or not c_to:
            raise ValueError(
                f"Código de país não configurado para PPP entre {from_info.code} e {to_info.code}. "
                "Informe explicitamente country_from e country_to."
            )

        # 1. Conversão nominal de mercado
        nominal_conversion = await self.convert(amount, from_query, to_query)

        # 2. Obtenção dos fatores PPP do Banco Mundial (PA.NUS.PPP)
        ppp_data_from = await self.world_bank.get_ppp_conversion_factor(c_from)
        ppp_data_to = await self.world_bank.get_ppp_conversion_factor(c_to)

        if not ppp_data_from:
            raise ValueError(f"Fator PPP do Banco Mundial não encontrado para o país '{c_from}'.")
        if not ppp_data_to:
            raise ValueError(f"Fator PPP do Banco Mundial não encontrado para o país '{c_to}'.")

        ppp_factor_from: Decimal = ppp_data_from["value"]
        ppp_factor_to: Decimal = ppp_data_to["value"]
        ref_year: int = max(ppp_data_from.get("year", 0), ppp_data_to.get("year", 0))

        if ppp_factor_from <= 0:
            raise InvalidExchangeRateError(f"Fator PPP inválido para {c_from}: {ppp_factor_from}")

        # Taxa de Câmbio PPP: PPP_to / PPP_from
        # Exemplo: USA PPP = 1.00 USD/$, BRA PPP = 2.50 BRL/$
        # 1 USD equivale em poder de compra doméstico a (2.50 / 1.00) = 2.50 BRL
        ppp_rate = ppp_factor_to / ppp_factor_from

        # Poder de Compra Equivalente: amount * ppp_rate
        ppp_equivalent_amount = amount * ppp_rate

        # Razão do Nível de Preços (PLR = Nominal Rate / PPP Rate)
        if ppp_rate > 0:
            price_level_ratio = nominal_conversion.rate / ppp_rate
        else:
            price_level_ratio = Decimal("0")

        ppp_result = PPPResult(
            country_from=c_from,
            country_to=c_to,
            currency_from=from_info.code,
            currency_to=to_info.code,
            ppp_factor_from=ppp_factor_from,
            ppp_factor_to=ppp_factor_to,
            nominal_rate=nominal_conversion.rate,
            ppp_rate=ppp_rate,
            price_level_ratio=price_level_ratio,
            nominal_amount_to=nominal_conversion.amount_to,
            ppp_equivalent_amount=ppp_equivalent_amount,
            year=ref_year,
        )

        return nominal_conversion, ppp_result

    async def convert_basket(
        self,
        amount: Decimal,
        from_currency: str,
        target_currencies: List[str],
        concurrency_limit: int = 5,
    ) -> BasketResult:
        """
        Converte uma quantia da moeda base simultaneamente para uma lista de moedas alvo.
        Utiliza semáforo de concorrência e tolera falhas parciais (return_exceptions).
        """
        if amount <= 0:
            raise ValueError(f"A quantia a ser convertida deve ser maior que zero. Recebido: {amount}")

        if not target_currencies:
            raise ValueError("A lista de moedas de destino não pode estar vazia.")

        from_info = self.matcher.match_strict(from_currency)
        sem = asyncio.Semaphore(concurrency_limit)

        async def _convert_single(target_raw: str) -> BasketItemResult:
            async with sem:
                try:
                    target_info = self.matcher.match_strict(target_raw)
                    conv_res = await self.convert(amount, from_info.code, target_info.code)
                    return BasketItemResult(
                        currency_to=target_info.code,
                        amount_to=conv_res.amount_to,
                        rate=conv_res.rate,
                        is_stale=conv_res.is_stale,
                        error=None,
                    )
                except Exception as e:
                    return BasketItemResult(
                        currency_to=target_raw.strip().upper(),
                        amount_to=None,
                        rate=None,
                        is_stale=False,
                        error=str(e),
                    )

        tasks = [_convert_single(t) for t in target_currencies]
        results: List[BasketItemResult] = await asyncio.gather(*tasks)

        return BasketResult(
            amount_from=amount,
            currency_from=from_info.code,
            items=results,
        )

