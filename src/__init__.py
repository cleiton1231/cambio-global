"""
Pacote principal do Câmbio Global.

Módulos disponíveis:
- api: Clientes HTTP para Frankfurter, CoinCap e World Bank (Zero Auth).
- match: Motor de resolução e matching de moedas, símbolos e tickers.
- converter: Lógica de conversão financeira, taxas cruzadas e paridade PPP.
- storage: Gerenciamento de histórico e moedas favoritas com exportação.
- ui: Renderização CLI em terminal com Rich.
- web: API REST FastAPI e Dashboard Web SPA.
- main: Ponto de entrada CLI e menu interativo.
"""

__version__ = "0.1.0"
