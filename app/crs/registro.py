"""Registro de CRS: lista curada brasileira PRIMEIRO, seguida do restante do banco EPSG geodésico/
projetado embutido no PROJ desta máquina (pyproj 3.7.2, PROJ 9.4.0) — item L2-17-crs-transformacoes.

Não lê `spatial_ref_sys` do Postgres para MONTAR a lista (o pyproj já embute o mesmo banco EPSG que
alimenta aquela tabela, sem gastar uma conexão do pool de 2 desta trilha para uma consulta que não muda
por inquilino); `app/ingestao/rotas.py` continua conferindo `spatial_ref_sys` na hora de gravar o SRID
de uma camada nova — este módulo só serve consulta/transformação, nunca escreve SRID de camada."""

from dataclasses import dataclass
from functools import lru_cache

from pyproj import CRS
from pyproj.database import query_crs_info
from pyproj.enums import PJType

from app.crs.curada import CODIGOS_CURADOS, CURADA

# Restringe a lista "geral" (fora da curada) a Geographic 2D / Projected — evita poluir com Compound,
# Vertical, Geocentric (que não fazem sentido no seletor de mapa 2D deste item).
_TIPOS_SUPORTADOS = {PJType.GEOGRAPHIC_2D_CRS, PJType.PROJECTED_CRS}


@dataclass(frozen=True)
class DescritorCRS:
    epsg: int
    nome: str
    tipo: str
    area_nome: str
    bounds: tuple[float, float, float, float] | None  # (oeste, sul, leste, norte) em graus
    curada: bool
    motivo_curada: str | None


def _descrever(epsg: int, motivo_curada: str | None) -> DescritorCRS | None:
    try:
        crs = CRS.from_epsg(epsg)
    except Exception:
        return None
    au = crs.area_of_use
    return DescritorCRS(
        epsg=epsg,
        nome=crs.name,
        tipo=crs.type_name,
        area_nome=au.name if au else "",
        bounds=(au.west, au.south, au.east, au.north) if au else None,
        curada=motivo_curada is not None,
        motivo_curada=motivo_curada,
    )


@lru_cache(maxsize=1)
def listar() -> tuple[DescritorCRS, ...]:
    """Curada primeiro (na ordem declarada em curada.CURADA), depois o resto do banco EPSG (ordenado
    por código) — a cláusula do portão "lista curada aparece primeiro nos seletores" é isto: a ORDEM
    desta tupla é a ordem que a rota devolve e que o seletor do navegador respeita sem reordenar."""
    motivo_por_epsg = {e.epsg: e.motivo for e in CURADA}
    curadas = tuple(d for d in (_descrever(e.epsg, e.motivo) for e in CURADA) if d is not None)
    gerais: set[int] = set()
    for r in query_crs_info(auth_name="EPSG"):
        try:
            codigo = int(r.code)
        except ValueError:
            continue
        if codigo in CODIGOS_CURADOS:
            continue
        if r.deprecated or r.type not in _TIPOS_SUPORTADOS:
            continue
        # alguns códigos do proj.db aparecem em mais de uma linha (mesmo CRS, área de uso registrada
        # em duas faixas — achado nesta rodada: 16 códigos, nenhum do Brasil); `set` dedupe por código,
        # e `_descrever` sempre lê o `CRS.from_epsg` canônico, então a linha duplicada não muda o resultado.
        gerais.add(codigo)
    descritas_gerais = tuple(
        d for d in (_descrever(c, motivo_por_epsg.get(c)) for c in sorted(gerais)) if d is not None
    )
    return curadas + descritas_gerais


def obter(epsg: int) -> DescritorCRS | None:
    for d in listar():
        if d.epsg == epsg:
            return d
    # pode existir no PROJ sem estar na lista geral pré-computada (tipo fora de _TIPOS_SUPORTADOS,
    # p.ex. alguém pede um Geocentric por engano) — devolve mesmo assim, sem marcar curada, para a
    # rota poder responder 422 com o nome certo em vez de "CRS inexistente" quando na verdade existe
    # mas não é suportado por este serviço 2D.
    return _descrever(epsg, None)


def proj4(epsg: int) -> str | None:
    try:
        return CRS.from_epsg(epsg).to_proj4()
    except Exception:
        return None
