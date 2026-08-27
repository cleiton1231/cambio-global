# 🚀 Câmbio Global (Fiat, Cripto & Poder de Compra)

Sistema completo para consulta, conversão e análise financeira integrando moedas fiduciárias tradicionais, criptoativos em tempo real e indicadores de Paridade de Poder de Compra (PPP) do Banco Mundial.

---

## 🌟 Funcionalidades

- **Moedas Fiduciárias (Fiat)**: Cotações oficiais e séries históricas via API Frankfurter (BCE).
- **Criptoativos**: Cotações em tempo real e volumes de mercado via CoinCap.
- **Paridade de Poder de Compra (PPP)**: Análise comparativa do custo de vida e poder de compra via Banco Mundial.
- **Motor de Resolução Inteligente**: Matching flexível por símbolo (ex: `$`, `R$`, `€`), código ISO (ex: `USD`, `BRL`) ou nome (ex: `Bitcoin`, `Dólar`).
- **Terminal CLI Rico**: Interface com tabelas formatadas, painéis e gráficos com `Rich`.
- **API REST & Web SPA**: Endpoints FastAPI com documentação OpenAPI/Swagger e painel web interativo.
- **Zero Auth**: Todas as fontes públicas dispensam chaves de autenticação proprietárias para inicialização rápida.

---

## 📁 Estrutura do Projeto

```text
cambio-global/
├── GEMINI.md              # Governança e diretrizes do projeto
├── README.md              # Documentação principal
├── requirements.txt       # Dependências do projeto
├── pyproject.toml         # Configuração de build e ferramentas Python
├── pytest.ini             # Configurações do Pytest
├── .gitignore             # Arquivos ignorados pelo Git
├── .env.example           # Modelo de variáveis de ambiente
├── src/
│   ├── __init__.py
│   ├── api/
│   │   ├── __init__.py
│   │   ├── frankfurter.py # Cotações oficiais de moedas fiduciárias e séries temporais (Zero Auth)
│   │   ├── coincap.py     # Cotações de criptoativos em tempo real (Zero Auth)
│   │   └── world_bank.py  # Indicadores de Paridade de Poder de Compra (PPP) e PIB (Zero Auth)
│   ├── match.py           # Motor crítico de matching e normalização de moedas, símbolos e tickers
│   ├── converter.py       # Mecanismo de conversão, arbitragem e paridade de poder de compra
│   ├── storage.py         # Histórico de conversões, moedas favoritas e exportadores JSON/CSV
│   ├── ui/
│   │   ├── __init__.py
│   │   └── views.py       # Renderização visual no terminal com Rich
│   ├── web/
│   │   ├── __init__.py
│   │   ├── app.py         # Web API REST FastAPI com Swagger OpenAPI
│   │   └── static/
│   │       └── index.html # Dashboard Web SPA moderno e interativo
│   └── main.py            # Ponto de entrada CLI, comandos de console e menu interativo
└── tests/
    ├── __init__.py
    ├── test_match.py      # Testes unitários do motor de matching (símbolos, ISO, nomes e criptos)
    ├── test_api.py        # Testes de integração de APIs com mocks
    ├── test_converter.py  # Testes de conversão cambial e cálculo PPP
    ├── test_storage.py    # Testes de persistência e variáveis de ambiente
    ├── test_web_api.py    # Testes de rotas FastAPI com TestClient
    └── test_security.py   # Testes de segurança STRIDE e OWASP Top 10
```

---

## ⚡ Instalação e Uso

### 1. Requisitos
- Python 3.10+

### 2. Instalação
```bash
pip install -r requirements.txt
```

### 3. Execução
```bash
# Executar a CLI
python -m src.main

# Executar os testes
pytest
```
