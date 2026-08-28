"""
Web API REST FastAPI com Swagger OpenAPI para o Câmbio Global.

Rotas disponibilizadas:
- GET /api/health: Health check do serviço.
- GET /api/currencies: Lista de moedas fiduciárias e criptoativos disponíveis.
- GET /api/search: Autocomplete e busca de moedas.
- GET /api/rates: Cotações atuais para uma moeda base.
- GET /api/crypto: Principais criptoativos da CoinCap.
- GET /api/trend: Análise de tendências históricas e sparklines.
- POST /api/convert: Conversão cambial nominal (Fiat e Cripto).
- POST /api/basket: Conversão concorrente de cesta de moedas.
- POST /api/simulate: Simulação de custos reais, IOF, spread e VET (BACEN).
- POST /api/salary: Calculadora de salário internacional e relocation (PPP).
- POST /api/report: Geração e exportação de relatório executivo (Markdown/HTML).
- POST /api/ppp: Análise de Paridade de Poder de Compra (PPP).
- GET /api/history: Histórico recente de conversões.
- GET /api/favorites / POST /api/favorites / DELETE /api/favorites: Favoritos.
"""

from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional
import uuid
from datetime import datetime, timezone
from pydantic import BaseModel, Field

from src.api.coincap import CoinCapClient
from src.api.frankfurter import FrankfurterClient
from src.api.world_bank import WorldBankClient
from src.converter import CurrencyConverter
from src.costs import CostSimulator
from src.match import get_matcher
from src.models import (
    AssetType,
    CambioGlobalError,
    ConversionRecord,
    CurrencyNotFoundError,
    FinancialReportData,
    OperationType,
    UnsupportedPPPAssetError,
)
from src.reporter import FinancialReportGenerator
from src.salary import InternationalSalaryCalculator
from src.storage import StorageManager
from src.trend import CurrencyTrendAnalyzer

# ============================================================================
# Schemas Pydantic para Requisições e Respostas
# ============================================================================

class ConvertRequest(BaseModel):
    amount: float = Field(..., gt=0, description="Quantia monetária a converter (> 0)")
    from_currency: str = Field(..., description="Moeda ou símbolo de origem (ex: USD, R$, BTC)")
    to_currency: str = Field(..., description="Moeda ou símbolo de destino (ex: BRL, EUR, ETH)")


class BasketRequest(BaseModel):
    amount: float = Field(..., gt=0, description="Quantia monetária a converter (> 0)")
    from_currency: str = Field(..., description="Moeda base de origem (ex: USD, EUR)")
    targets: Optional[List[str]] = Field(None, description="Lista de moedas alvo (opcional; usa favoritos se omitido)")


class CostSimulateRequest(BaseModel):
    amount: float = Field(..., gt=0, description="Quantia monetária negociada (> 0)")
    from_currency: str = Field(..., description="Moeda de origem (ex: BRL, USD)")
    to_currency: str = Field(..., description="Moeda de destino (ex: USD, EUR)")
    profile_key: Optional[str] = Field("global_account", description="Perfil de custo (global_account, credit_card, investment, inbound_salary, crypto_p2p)")
    custom_iof: Optional[float] = Field(None, ge=0, description="Alíquota customizada de IOF em %")
    custom_spread: Optional[float] = Field(None, ge=0, description="Spread customizado em %")
    custom_fee: Optional[float] = Field(None, ge=0, description="Tarifa fixa bancária")
    operation_type: Optional[str] = Field(None, description="Direção: outbound ou inbound")


class SalaryRequest(BaseModel):
    base_salary: float = Field(..., gt=0, description="Salário base atual (> 0)")
    base_currency: str = Field(..., description="Moeda de origem do salário (ex: USD, EUR)")
    target_currency: str = Field(..., description="Moeda de destino (ex: BRL, EUR)")
    country_from: Optional[str] = Field(None, description="Código ISO-3 opcional do país de origem (ex: USA, BRA)")
    country_to: Optional[str] = Field(None, description="Código ISO-3 opcional do país de destino (ex: PRT, DEU)")


class ReportRequest(BaseModel):
    title: str = Field("Relatório Financeiro Executivo", description="Título do documento")
    amount: float = Field(1000.0, gt=0, description="Quantia de referência")
    from_currency: str = Field("USD", description="Moeda de origem")
    to_currency: str = Field("BRL", description="Moeda de destino")
    format: str = Field("html", description="Formato de saída: html ou md")
    notes: Optional[str] = Field(None, description="Notas executivas opcionais")


class PPPRequest(BaseModel):
    amount: float = Field(..., gt=0, description="Quantia monetária a converter (> 0)")
    from_currency: str = Field(..., description="Moeda fiduciária de origem (ex: USD, BRL)")
    to_currency: str = Field(..., description="Moeda fiduciária de destino (ex: BRL, EUR)")
    country_from: Optional[str] = Field(None, description="Código ISO-3 opcional do país de origem (ex: USA, BRA)")
    country_to: Optional[str] = Field(None, description="Código ISO-3 opcional do país de destino (ex: DEU, FRA)")


class FavoriteRequest(BaseModel):
    currency_code: str = Field(..., description="Código ou símbolo da moeda (ex: USD, BTC)")


# ============================================================================
# Instâncias de Serviços Compartilhados
# ============================================================================

matcher = get_matcher()
frankfurter_client = FrankfurterClient()
coincap_client = CoinCapClient()
world_bank_client = WorldBankClient()
converter = CurrencyConverter(
    matcher=matcher,
    frankfurter=frankfurter_client,
    coincap=coincap_client,
    world_bank=world_bank_client,
)
cost_simulator = CostSimulator(
    converter=converter,
    matcher=matcher,
)
salary_calculator = InternationalSalaryCalculator(
    converter=converter,
    world_bank=world_bank_client,
    matcher=matcher,
)
trend_analyzer = CurrencyTrendAnalyzer(
    matcher=matcher,
    frankfurter=frankfurter_client,
    coincap=coincap_client,
)
storage = StorageManager()
reporter = FinancialReportGenerator(storage=storage)

STATIC_DIR = Path(__file__).parent / "static"
STATIC_DIR.mkdir(parents=True, exist_ok=True)


# ============================================================================
# Funções de Controlador das Rotas (Reutilizáveis e Testáveis)
# ============================================================================

async def handle_health_check() -> Dict[str, str]:
    return {"status": "ok", "service": "cambio-global", "version": "0.2.0"}


async def handle_list_currencies(asset_type: Optional[str] = None) -> List[Dict[str, Any]]:
    currencies = matcher.currencies
    if asset_type:
        type_clean = asset_type.lower()
        currencies = [c for c in currencies if c.asset_type.value == type_clean]
    return [c.to_dict() for c in currencies]


async def handle_search_currencies(q: str, limit: int = 5) -> List[Dict[str, Any]]:
    results = matcher.search(q, limit=limit)
    return [r.to_dict() for r in results]


async def handle_get_rates(base: str = "USD") -> Dict[str, Any]:
    return await frankfurter_client.get_latest_rates(base=base.upper())


async def handle_get_crypto(limit: int = 20) -> List[Dict[str, Any]]:
    return await coincap_client.get_assets(limit=limit)


async def handle_trend(from_currency: str, to_currency: str, days: int = 30) -> Dict[str, Any]:
    res = await trend_analyzer.analyze_trend(from_currency, to_currency, days=days)
    return res.to_dict()


async def handle_convert(req: ConvertRequest) -> Dict[str, Any]:
    amount_dec = Decimal(str(req.amount))
    result = await converter.convert(amount_dec, req.from_currency, req.to_currency)

    rec = ConversionRecord(
        id=str(uuid.uuid4())[:8],
        timestamp=datetime.now(timezone.utc).isoformat(),
        from_currency=result.currency_from,
        to_currency=result.currency_to,
        amount_from=float(result.amount_from),
        amount_to=float(result.amount_to),
        rate=float(result.rate),
    )
    storage.save_conversion_record(rec)
    return result.to_dict()


async def handle_simulate(req: CostSimulateRequest) -> Dict[str, Any]:
    amount_dec = Decimal(str(req.amount))
    iof_dec = Decimal(str(req.custom_iof)) if req.custom_iof is not None else None
    spread_dec = Decimal(str(req.custom_spread)) if req.custom_spread is not None else None
    fee_dec = Decimal(str(req.custom_fee)) if req.custom_fee is not None else None
    op_type = OperationType(req.operation_type.lower()) if req.operation_type else None

    result = await cost_simulator.simulate(
        amount=amount_dec,
        from_currency=req.from_currency,
        to_currency=req.to_currency,
        profile_key=req.profile_key,
        custom_iof=iof_dec,
        custom_spread=spread_dec,
        custom_fee=fee_dec,
        operation_type=op_type,
    )
    return result.to_dict()


async def handle_salary(req: SalaryRequest) -> Dict[str, Any]:
    salary_dec = Decimal(str(req.base_salary))
    result = await salary_calculator.calculate_salary_equivalency(
        base_salary=salary_dec,
        base_currency=req.base_currency,
        target_currency=req.target_currency,
        country_from=req.country_from,
        country_to=req.country_to,
    )
    return result.to_dict()


async def handle_report(req: ReportRequest) -> Dict[str, Any]:
    amount_dec = Decimal(str(req.amount))
    conv_res = await converter.convert(amount_dec, req.from_currency, req.to_currency)
    sim_res = await cost_simulator.simulate(amount_dec, req.from_currency, req.to_currency, profile_key="global_account")
    sal_res = None
    try:
        sal_res = await salary_calculator.calculate_salary_equivalency(amount_dec, req.from_currency, req.to_currency)
    except Exception:
        pass

    data = FinancialReportData(
        title=req.title,
        created_at=datetime.now(timezone.utc),
        conversions=[conv_res],
        cost_simulation=sim_res,
        salary_analysis=sal_res,
        notes=req.notes,
    )

    if req.format.lower() in ("html", "htm"):
        content = reporter.generate_html(data)
    else:
        content = reporter.generate_markdown(data)

    return {
        "title": req.title,
        "format": req.format.lower(),
        "content": content,
    }


async def handle_basket(req: BasketRequest) -> Dict[str, Any]:
    amount_dec = Decimal(str(req.amount))
    targets = req.targets
    if not targets:
        favs = storage.get_favorites()
        targets = favs if favs else ["BRL", "EUR", "GBP", "JPY", "BTC", "ETH"]

    result = await converter.convert_basket(
        amount=amount_dec,
        from_currency=req.from_currency,
        target_currencies=targets,
    )
    return result.to_dict()


async def handle_ppp(req: PPPRequest) -> Dict[str, Any]:
    amount_dec = Decimal(str(req.amount))
    conv_res, ppp_res = await converter.convert_with_ppp(
        amount=amount_dec,
        from_query=req.from_currency,
        to_query=req.to_currency,
        country_from=req.country_from,
        country_to=req.country_to,
    )

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
    storage.save_conversion_record(rec)

    return {
        "conversion": conv_res.to_dict(),
        "ppp": ppp_res.to_dict(),
    }


async def handle_get_history(limit: int = 50) -> List[Dict[str, Any]]:
    records = storage.get_history(limit=limit)
    return [r.to_dict() for r in records]


async def handle_get_favorites() -> List[str]:
    return storage.get_favorites()


async def handle_add_favorite(req: FavoriteRequest) -> Dict[str, Any]:
    info = matcher.match(req.currency_code)
    if not info:
        raise CurrencyNotFoundError(req.currency_code)
    added = storage.save_favorite(info.code)
    return {"status": "added" if added else "already_exists", "code": info.code}


async def handle_remove_favorite(code: str) -> Dict[str, Any]:
    removed = storage.remove_favorite(code)
    if not removed:
        raise CurrencyNotFoundError(code)
    return {"status": "removed", "code": code.upper()}


# ============================================================================
# Registro de Rotas no FastAPI (se instalado)
# ============================================================================

try:
    from fastapi import FastAPI, HTTPException, Query
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import FileResponse, HTMLResponse
    from fastapi.staticfiles import StaticFiles

    app = FastAPI(
        title="Câmbio Global API",
        description="API REST para conversão cambial, VET, salários internacionais, cestas e relatórios",
        version="0.2.0",
        docs_url="/docs",
        redoc_url="/redoc",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    if STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    @app.get("/")
    async def root_index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    @app.get("/api/health")
    async def api_health() -> Dict[str, str]:
        return await handle_health_check()

    @app.get("/api/currencies")
    async def api_currencies(asset_type: Optional[str] = None) -> List[Dict[str, Any]]:
        return await handle_list_currencies(asset_type)

    @app.get("/api/search")
    async def api_search(q: str = Query(..., min_length=1), limit: int = 5) -> List[Dict[str, Any]]:
        return await handle_search_currencies(q, limit)

    @app.get("/api/rates")
    async def api_rates(base: str = "USD") -> Dict[str, Any]:
        try:
            return await handle_get_rates(base)
        except Exception as e:
            raise HTTPException(status_code=502, detail=str(e))

    @app.get("/api/crypto")
    async def api_crypto(limit: int = 20) -> List[Dict[str, Any]]:
        try:
            return await handle_get_crypto(limit)
        except Exception as e:
            raise HTTPException(status_code=502, detail=str(e))

    @app.get("/api/trend")
    async def api_trend(from_currency: str = "USD", to_currency: str = "BRL", days: int = 30) -> Dict[str, Any]:
        try:
            return await handle_trend(from_currency, to_currency, days)
        except CurrencyNotFoundError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except (ValueError, CambioGlobalError) as e:
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @app.post("/api/convert")
    async def api_convert(req: ConvertRequest) -> Dict[str, Any]:
        try:
            return await handle_convert(req)
        except CurrencyNotFoundError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except (ValueError, CambioGlobalError) as e:
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @app.post("/api/simulate")
    async def api_simulate(req: CostSimulateRequest) -> Dict[str, Any]:
        try:
            return await handle_simulate(req)
        except CurrencyNotFoundError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except (ValueError, CambioGlobalError) as e:
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @app.post("/api/salary")
    async def api_salary(req: SalaryRequest) -> Dict[str, Any]:
        try:
            return await handle_salary(req)
        except UnsupportedPPPAssetError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except CurrencyNotFoundError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except (ValueError, CambioGlobalError) as e:
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @app.post("/api/report")
    async def api_report(req: ReportRequest) -> Dict[str, Any]:
        try:
            return await handle_report(req)
        except CurrencyNotFoundError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except (ValueError, CambioGlobalError) as e:
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @app.post("/api/basket")
    async def api_basket(req: BasketRequest) -> Dict[str, Any]:
        try:
            return await handle_basket(req)
        except CurrencyNotFoundError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except (ValueError, CambioGlobalError) as e:
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @app.post("/api/ppp")
    async def api_ppp(req: PPPRequest) -> Dict[str, Any]:
        try:
            return await handle_ppp(req)
        except UnsupportedPPPAssetError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except CurrencyNotFoundError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except (ValueError, CambioGlobalError) as e:
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @app.get("/api/history")
    async def api_history(limit: int = 50) -> List[Dict[str, Any]]:
        return await handle_get_history(limit)

    @app.get("/api/favorites")
    async def api_favorites() -> List[str]:
        return await handle_get_favorites()

    @app.post("/api/favorites")
    async def api_add_fav(req: FavoriteRequest) -> Dict[str, Any]:
        try:
            return await handle_add_favorite(req)
        except CurrencyNotFoundError as e:
            raise HTTPException(status_code=404, detail=str(e))

    @app.delete("/api/favorites/{code}")
    async def api_remove_fav(code: str) -> Dict[str, Any]:
        try:
            return await handle_remove_favorite(code)
        except CurrencyNotFoundError as e:
            raise HTTPException(status_code=404, detail=str(e))

except ImportError:
    app = None
