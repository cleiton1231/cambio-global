# Governança e Diretrizes do Projeto: Câmbio Global 💱🪙

## 1. Contexto do Projeto
Dashboard financeiro, CLI e Web API para conversão de moedas mundiais, criptoativos e análise de Paridade de Poder de Compra (PPP), cruzando:
- **Frankfurter API** (`https://api.frankfurter.app`): Cotações oficiais de moedas fiduciárias pelo Banco Central Europeu (BCE) com histórico diário desde 1999 (Zero Auth).
- **CoinCap API** (`https://api.coincap.io/v2`): Cotações e variações 24h de criptomoedas em tempo real (Zero Auth).
- **World Bank API** (`https://api.worldbank.org/v2`): Indicadores macroeconômicos de Paridade de Poder de Compra (PPP) e custo de vida por país (Zero Auth).

---

## 2. Regra Específica Crítica: Resolução e Matching de Moedas (`src/match.py`)
- O usuário pode digitar:
  - **Símbolos**: `R$`, `$`, `€`, `¥`, `£`, etc.
  - **Códigos ISO 4217**: `BRL`, `USD`, `EUR`, `JPY`, `GBP`, etc.
  - **Nomes populares (PT/EN)**: `dólar`, `real`, `iene`, `euro`, `peso argentino`, `libra esterlina`, `dollar`, `pound`, etc.
  - **Tickers e nomes de Criptomoedas**: `BTC`, `ETH`, `SOL`, `bitcoin`, `ethereum`, `solana`, etc.
- O algoritmo de normalização e fallback de matching em `src/match.py` é a **PARTE MAIS CRÍTICA DO PROJETO**.
- **Requisitos de Matching**:
  - Determinístico, sem adivinhações cegas.
  - Sanitização e remoção de ruídos (espaços, acentos/diacríticos, caixa alta/baixa).
  - Tabela canônica de aliases com resolução de precedência clara.
  - Obrigatoriamente coberto por testes unitários exaustivos em `tests/test_match.py` seguindo **TDD (Red-Green-Refactor)**.

---

## 3. Diretrizes de Integração e APIs
- **Zero Autenticação**: Nenhuma API externa exige chaves, tokens ou headers de autorização proprietários.
- **Timeouts e Resiliência**:
  - Toda requisição HTTP deve ter timeout explícito (10s padrão).
  - Tratar status 404, 503, rate-limits e falhas de rede de forma defensiva com fallbacks ou mensagens amigáveis, sem expor stack traces.
- **Isolamento de Testes**:
  - Testes automatizados executam offline com mocks (`respx` ou `unittest.mock`), garantindo velocidade e determinismo.

---

## 4. Filosofia de Desenvolvimento e Arquitetura
- **TDD (Test-Driven Development)**: Ciclo estrito Red -> Green -> Refactor para cada funcionalidade.
- **Segurança**:
  - Modelagem de ameaças **STRIDE** e mitigações **OWASP Top 10** (validação de entrada, prevenção de SSRF com whitelist de domínios, prevenção de Path Traversal no storage local).
- **Concorrência e Performance**:
  - FastAPI assíncrono para I/O externo e offload seguro em threadpool para processamento síncrono.
  - Precisão financeira com tipo `Decimal` para evitar imprecisões de ponto flutuante.
