"""Cliente do OSRM isolado de teste do item L2-11-c-rota-matriz-isocrona (`plat-osrm-guarulhos`,
127.0.0.1:5010 por padrão — `PLAT_OSRM_URL`). Nunca aponta para os OSRM de outras frentes da casa
(5000-5003): a URL é fixa em `app.settings`, nunca aceita URL do chamador (sem SSRF possível aqui —
diferente do L1-02, que valida URL de terceiro; este cliente só fala com o OSRM próprio do item)."""

import json
import logging
from pathlib import Path

import httpx

from app import limites
from app.erros import ErroAPI
from app.settings import settings

log = logging.getLogger("plat.rede.osrm")
RAIZ = Path(__file__).resolve().parents[2]
# procedência do grafo: arquivo, sha256, data de extração e versão do OSRM (osrm/proveniencia.json, escrito
# quando o recorte foi construído). É a "versão do grafo OSM" que toda resposta e toda camada derivada carrega.
PROVENIENCIA = json.loads((RAIZ / "osrm" / "proveniencia.json").read_text(encoding="utf-8"))

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


def rota_por_pontos(pontos: list[list[float]], perfil: str) -> dict:
    """Rota na ORDEM dada, com 2 ou mais pontos (cada par vira uma perna em `legs`)."""
    osrm_perfil = _perfil_ou_422(perfil)
    coords = ";".join(_coord(p) for p in pontos)
    return _chamar(
        f"/route/v1/{osrm_perfil}/{coords}",
        {"overview": "full", "geometries": "geojson", "steps": "true", "alternatives": "false"},
    )


def rota(origem: list[float], destino: list[float], perfil: str) -> dict:
    return rota_por_pontos([origem, destino], perfil)


def viagem(pontos: list[list[float]], perfil: str, fechar_ciclo: bool = False) -> dict:
    """Serviço /trip do OSRM: ordem de visita por heurística (inserção do mais distante) sobre a ordem dada.
    `fechar_ciclo` falso fixa a primeira parada como início e a última como fim (doc OSRM v5.24, trip service)."""
    osrm_perfil = _perfil_ou_422(perfil)
    coords = ";".join(_coord(p) for p in pontos)
    params = {"overview": "full", "geometries": "geojson", "steps": "true",
              "roundtrip": "true" if fechar_ciclo else "false"}
    if not fechar_ciclo:
        params.update({"source": "first", "destination": "last"})
    return _chamar(f"/trip/v1/{osrm_perfil}/{coords}", params)


def mais_proximo(ponto: list[float], perfil: str) -> dict:
    """Serviço /nearest: o ponto da REDE mais próximo da coordenada dada (é o `snap` do OSRM)."""
    osrm_perfil = _perfil_ou_422(perfil)
    return _chamar(f"/nearest/v1/{osrm_perfil}/{_coord(ponto)}", {"number": 1})


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


def matriz_grande(origens: list[list[float]], destinos: list[list[float]], perfil: str) -> dict:
    """Matriz N×M maior que o teto de uma chamada só (`--max-table-size` do OSRM, espelhado em
    PLAT_ROTA_MATRIZ_MAX): parte em blocos, chama o MESMO serviço `/table` bloco a bloco e remonta.
    Devolve {"durations": [[...]], "distances": [[...]], "chamadas": n}. Célula sem rota fica None."""
    teto = max(int(settings.PLAT_ROTA_MATRIZ_MAX), 1)
    n, m = len(origens), len(destinos)
    # blocos que respeitam o teto SEM desperdiçar chamada: com 1 origem o bloco é 1×teto (o caso da isócrona);
    # com N e M grandes, o bloco fica quadrado (lado = raiz do teto)
    lado_o = min(n, max(int(teto ** 0.5), 1))
    lado_d = min(m, max(teto // lado_o, 1))
    duracoes = [[None] * m for _ in range(n)]
    distancias = [[None] * m for _ in range(n)]
    chamadas = 0
    for i0 in range(0, n, lado_o):
        for j0 in range(0, m, lado_d):
            bloco_o = origens[i0:i0 + lado_o]
            bloco_d = destinos[j0:j0 + lado_d]
            r = matriz(bloco_o, bloco_d, perfil)
            chamadas += 1
            for i, linha in enumerate(r.get("durations") or []):
                for j, v in enumerate(linha):
                    duracoes[i0 + i][j0 + j] = v
            for i, linha in enumerate(r.get("distances") or []):
                for j, v in enumerate(linha):
                    distancias[i0 + i][j0 + j] = v
    return {"durations": duracoes, "distances": distancias, "chamadas": chamadas}
