"""
Submódulo de clientes de API públicas externas (Zero Auth).

Exporta os clientes HTTP para Frankfurter, CoinCap e Banco Mundial.
"""

from src.api.base import BaseAPIClient
from src.api.coincap import CoinCapClient
from src.api.frankfurter import FrankfurterClient
from src.api.world_bank import WorldBankClient

__all__ = [
    "BaseAPIClient",
    "FrankfurterClient",
    "CoinCapClient",
    "WorldBankClient",
]
