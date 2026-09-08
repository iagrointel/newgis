"""Rotas `/api/amc/criterios-feicao` (item L3-06-criterios-de-feicao): avaliação multicritério quando a unidade
de análise é a FEIÇÃO DO USUÁRIO (um imóvel, uma loja, um lote), e não a célula de uma grade.

Sem tabela `plat.*` própria e sem estado, pelo mesmo motivo de `app/amc/rotas_similaridade.py`: o pedido traz as
feições (com os atributos delas) e as camadas de apoio, e a API devolve valores brutos, favorabilidades, nota,
ranque, histogramas e a matriz de correlação na hora. Por isso não há RLS aqui — não se lê nem se grava linha de
inquilino nenhuma. Privilégio `analise.amc`, o mesmo do resto do motor multicritério.

Teto: `limites.AMC_CRITERIOS_FEICAO_MAX` feições por pedido (é o que responde em segundos e o que a tela mostra).
Acima disso a API recusa com `acima_do_sincrono` e manda para o caminho de LOTE que já existe — gravar um conjunto
de unidades (`POST /api/amc/conjuntos`) e rodar `POST /api/amc/execucoes`, que é job (`amc.executar`). A recusa é
explícita: a lista nunca é cortada em silêncio.

O CRS de trabalho é escolhido pela zona UTM SIRGAS 2000 do centróide das feições (`app.amc.crs`, decisão A7) — o
mesmo critério do conjunto de unidades. Raio, distância e contenção são medidos nesse plano, nunca em graus.
"""

from typing import Any, Literal

from fastapi import APIRouter, Query
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field, field_validator

from app import limites
from app.amc import criterios_feicao as motor
from app.amc import crs as mod_crs
from app.auth.sessao import autenticado
from app.erros import ErroAPI

router = APIRouter(prefix="/api/amc", tags=["amc"])
X = {"x-auth": "S/T", "x-privilegio": "analise.amc"}


class PedidoCriteriosFeicao(BaseModel):
    feicoes: list[dict[str, Any]] = Field(
        ..., min_length=1,
        description="Feições do usuário em GeoJSON (EPSG:4326), cada uma com 'geometry', 'properties' e um id "
                    "estável em 'id' ou em properties.id.",
    )
    criterios: list[dict[str, Any]] = Field(
        ..., min_length=1,
        description="Critérios sobre a feição: tipo (atributo, contagem_raio, contagem_dentro, "
                    "distancia_mais_proxima), influência (positiva, inversa, ideal), peso e, quando for o caso, "
                    "campo, camada, raio_m, alvo/alcance, minimo/maximo e faixa_inclusao.",
    )
    camadas: dict[str, list[dict[str, Any]]] = Field(
        default_factory=dict,
        description="{nome: [Feature, ...]} — as camadas de apoio citadas pelos critérios de raio, contenção e "
                    "distância (tipicamente pontos).",
    )
    combinador: str = "soma_ponderada"
    politica_ausente: str = "excluir"
    srid_trabalho: int | None = Field(
        None, description="CRS métrico de trabalho; omitido = zona UTM SIRGAS 2000 do centróide das feições.",
    )

    @field_validator("feicoes")
    @classmethod
    def _v_feicoes(cls, v):
        if len(v) > limites.AMC_CRITERIOS_FEICAO_MAX:
            raise ValueError(
                f"{len(v)} feições passam do teto de {limites.AMC_CRITERIOS_FEICAO_MAX} da avaliação síncrona; "
                f"para um lote maior, grave um conjunto de unidades (POST /api/amc/conjuntos) e rode "
                f"POST /api/amc/execucoes, que é job")
        return v

    @field_validator("camadas")
    @classmethod
    def _v_camadas(cls, v):
        for nome, feicoes in v.items():
            if len(feicoes) > limites.AMC_CRITERIO_CAMADA_PONTOS_MAX:
                raise ValueError(f"a camada {nome!r} tem {len(feicoes)} feições e passa do teto de "
                                 f"{limites.AMC_CRITERIO_CAMADA_PONTOS_MAX} por pedido")
        return v


def _centroide_e_bbox(feicoes: list[dict]):
    """Vértices, bbox e centróide das feições, para `app.amc.crs.ficha_crs` escolher a zona UTM. Quem extrai as
    coordenadas de qualquer geometria GeoJSON é o shapely (`get_coordinates`), que este módulo já carrega pela
    cadeia do extrator — não há percurso de listas aninhadas escrito à mão aqui."""
    import shapely
    from shapely.geometry import shape

    geometrias = []
    for f in feicoes:
        geom = (f.get("geometry") or None) if isinstance(f, dict) else None
        if not geom:
            continue
        try:
            geometrias.append(shape(geom))
        except (AttributeError, KeyError, TypeError, ValueError) as e:
            raise ErroAPI(422, "geometria_invalida", f"geometria que não é GeoJSON válido: {e}") from e
    coords = shapely.get_coordinates(geometrias) if geometrias else []
    if len(coords) == 0:
        raise ErroAPI(422, "feicao_sem_geometria",
                      "nenhuma feição do pedido tem coordenada: sem geometria não há CRS de trabalho a escolher")
    pontos = [(float(x), float(y)) for x, y in coords]
    xs = [p[0] for p in pontos]
    ys = [p[1] for p in pontos]
    bbox = (min(xs), min(ys), max(xs), max(ys))
    centro = ((bbox[0] + bbox[2]) / 2.0, (bbox[1] + bbox[3]) / 2.0)
    return pontos, bbox, centro


def _avaliar_ou_422(pedido: PedidoCriteriosFeicao) -> tuple[motor.Avaliacao, dict]:
    if pedido.srid_trabalho is not None:
        srid = int(pedido.srid_trabalho)
        ficha_crs = {"srid_trabalho": srid, "origem": "declarado no pedido"}
    else:
        pontos, bbox, centro = _centroide_e_bbox(pedido.feicoes)
        try:
            ficha_crs = mod_crs.ficha_crs(pontos, bbox, centro)
        except ValueError as e:
            raise ErroAPI(422, "fora_da_cobertura_utm", str(e)) from e
        ficha_crs["origem"] = "zona UTM SIRGAS 2000 do centróide das feições"
        srid = int(ficha_crs["srid_trabalho"])
    try:
        avaliacao = motor.avaliar(pedido.feicoes, pedido.criterios, srid, pedido.camadas,
                                  combinador=pedido.combinador, politica_ausente=pedido.politica_ausente)
    except motor.ErroCriterio as e:
        raise ErroAPI(422, e.codigo, e.mensagem, e.detalhe) from e
    except Exception as e:  # erro de contrato dos módulos reusados (transformação, combinação, extração)
        codigo = getattr(e, "codigo", None)
        if codigo is None:
            raise
        raise ErroAPI(422, codigo, getattr(e, "mensagem", str(e)), getattr(e, "detalhe", None)) from e
    return avaliacao, ficha_crs


@router.post("/criterios-feicao", openapi_extra=X)
def avaliar_criterios_feicao(pedido: PedidoCriteriosFeicao, auth=autenticado("analise.amc")):
    """Avalia feições do usuário contra critérios sobre a própria feição e devolve o ranque com histograma por
    critério e matriz de correlação entre critérios. `/api/amc/criterios-feicao/exportar` devolve o mesmo em CSV."""
    avaliacao, ficha_crs = _avaliar_ou_422(pedido)
    return {"crs": ficha_crs, **avaliacao.como_dicionario()}


@router.post("/criterios-feicao/exportar", openapi_extra=X)
def exportar_criterios_feicao(pedido: PedidoCriteriosFeicao, auth=autenticado("analise.amc"),
                              formato: Literal["csv"] = Query("csv")):
    """Mesmo cálculo de `/api/amc/criterios-feicao`, em CSV: uma linha por feição, na ordem do ranque, com valor
    bruto e favorabilidade de cada critério. As feições filtradas saem no fim, com o motivo do filtro."""
    avaliacao, _ = _avaliar_ou_422(pedido)
    return PlainTextResponse(avaliacao.csv(), media_type="text/csv; charset=utf-8")
