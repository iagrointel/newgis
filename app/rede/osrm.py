"""Cliente do OSRM isolado de teste do item L2-11-c-rota-matriz-isocrona (`plat-osrm-guarulhos`,
127.0.0.1:5010 por padrão — `PLAT_OSRM_URL`). Nunca aponta para os OSRM de outras frentes da casa
(5000-5003): a URL é fixa em `app.settings`, nunca aceita URL do chamador (sem SSRF possível aqui —
diferente do L1-02, que valida URL de terceiro; este cliente só fala com o OSRM próprio do item)."""

import logging

import httpx

from app import limites
from app.erros import ErroAPI
from app.settings import settings

log = logging.getLogger("plat.rede.osrm")

PERFIL_OSRM = {"carro": "driving"}  # só carro tem grafo carregado nesta instância de teste (D-osrm-perfis)
_TIMEOUT = httpx.Timeout(connect=1.0, read=8.0, write=2.0, pool=2.0)


def _cliente() -> httpx.Client:
    return httpx.Client(base_url=settings.PLAT_OSRM_URL, timeout=_TIMEOUT)


def _coord(p: list[float]) -> str:
    return f"{p[0]:.7f},{p[1]:.7f}"


def _perfil_ou_422(perfil: str) -> str:
    if perfil not in limites.ROTA_PERFIS:
        raise ErroAPI(
            422,
            "perfil_invalido",
            f"perfil {perfil!r} não disponível nesta instância de teste (só {limites.ROTA_PERFIS})",
            {"perfis_disponiveis": list(limites.ROTA_PERFIS)},
        )
    return PERFIL_OSRM[perfil]


def _chamar(path: str, params: dict) -> dict:
    try:
        with _cliente() as c:
            r = c.get(path, params=params)
    except httpx.ConnectError as e:
        raise ErroAPI(503, "osrm_indisponivel", "serviço de rota (OSRM) fora do ar") from e
    except httpx.TimeoutException as e:
        raise ErroAPI(503, "osrm_indisponivel", "serviço de rota (OSRM) não respondeu a tempo") from e
    if r.status_code != 200:
        raise ErroAPI(502, "osrm_erro", f"OSRM devolveu HTTP {r.status_code}", {"corpo": r.text[:500]})
    corpo = r.json()
    codigo = corpo.get("code")
    if codigo != "Ok":
        # NoRoute, NoSegment, NotFound, InvalidOptions... (doc OSRM v5.24): erro do PEDIDO, não do serviço
        raise ErroAPI(422, "sem_rota", corpo.get("message") or f"OSRM: {codigo}", {"codigo_osrm": codigo})
    return corpo


def rota(origem: list[float], destino: list[float], perfil: str) -> dict:
    osrm_perfil = _perfil_ou_422(perfil)
    coords = f"{_coord(origem)};{_coord(destino)}"
    return _chamar(
        f"/route/v1/{osrm_perfil}/{coords}",
        {"overview": "full", "geometries": "geojson", "steps": "true", "alternatives": "false"},
    )


def matriz(origens: list[list[float]], destinos: list[list[float]], perfil: str) -> dict:
    osrm_perfil = _perfil_ou_422(perfil)
    n, m = len(origens), len(destinos)
    todos = origens + destinos
    coords = ";".join(_coord(p) for p in todos)
    fontes = ";".join(str(i) for i in range(n))
    alvos = ";".join(str(n + j) for j in range(m))
    return _chamar(
        f"/table/v1/{osrm_perfil}/{coords}",
        {"sources": fontes, "destinations": alvos, "annotations": "duration,distance"},
    )


def tabela_1_para_n(origem: list[float], destinos: list[list[float]], perfil: str) -> dict:
    """1 fonte × N destinos (usado pela grade da isócrona; caminho mais barato que `matriz` genérico)."""
    return matriz([origem], destinos, perfil)
