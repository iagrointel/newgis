"""Leitura de linhas de DXF ASCII (o fluxo "copiar linhas de CAD" do parcel fabric) e importação
delas para `plat.parcela_linha` — a entrada do fluxo build (construir parcelas a partir de linhas).

Escopo declarado (paridade §12): este leitor entende DXF ASCII com entidades LINE e LWPOLYLINE,
que é o que uma planta vetorial simples carrega. DXF BINÁRIO e DWG ficam FORA: conversão é fase
externa (o handoff L0-04 mediu que os conversores de linha de comando geram arquivo que nem o
GDAL nem o ezdxf reabrem — a casa não depõe sobre binário que não lê). O dado de teste é a planta
de teste da casa (corpus aberto de projeto, arquivo A-01 de planta baixa); nenhuma planta de
cliente passa por aqui.

A entidade LWPOLYLINE fechada (flag 70 = 1) é quebrada em segmentos — o modelo da casa só tem
linha reta de dois pontos (a paridade §3 marca arco como fase de desenho). Camada (código 8) vai
na descrição do registro sintético, não na linha — `parcela_linha` não tem campo de atributo
livre, e inventar coluna por formato é o caminho para tabela de importador.

Coordenada: o DXF de planta não tem CRS declarado. A malha da casa é SIRGAS 2000 UTM 22S (SRID
31982); o importador aceita as coordenadas do arquivo COMO ESTÃO (a planta importa em coordenada
local) — quem precisa de georreferência reposiciona antes ou depois, com os pontos fixos da malha.
Isso é declarado, não corrigido às escondidas.
"""

import math
from pathlib import Path

from app import limites
from app.erros import ErroAPI
from app.parcelas import modelo

TOLERANCIA = 1e-6  # mesma deduplicação por coordenada do import de lotes (importar.py)


def ler(texto: str) -> list[dict]:
    """Lê o texto de um DXF ASCII e devolve os segmentos: [{camada, [(x,y),(x,y)]}, ...].
    Levanta 422 em arquivo sem seção ENTITIES ou sem linha nenhuma — arquivo vazio não é dado."""
    linhas_texto = texto.splitlines()
    pares = [(linhas_texto[i].strip(), linhas_texto[i + 1].strip())
             for i in range(0, len(linhas_texto) - 1, 2)]
    # DXF é uma sequência de pares (código, valor): "0 SECTION" seguido de "2 ENTITIES" abre a
    # seção de entidades; "0 ENDSEC" a fecha. Blocos (BLOCK) têm as suas entidades dentro da
    # seção BLOCKS e não passam por aqui — só a seção ENTITIES de verdade abre.
    inicio = None
    fim = None
    for i in range(len(pares) - 1):
        if pares[i] == ("0", "SECTION") and pares[i + 1][0] == "2" and pares[i + 1][1].upper() == "ENTITIES":
            inicio = i + 2
            break
    if inicio is None:
        raise ErroAPI(422, "valor_invalido", "DXF sem seção ENTITIES")
    for j in range(inicio, len(pares)):
        if pares[j] == ("0", "ENDSEC"):
            fim = j
            break
    fatia = pares[inicio: fim if fim is not None else len(pares)]

    segmentos: list[dict] = []
    i = 0
    while i < len(fatia):
        codigo, valor = fatia[i]
        if codigo == "0" and valor == "LINE":
            camada = ""
            pontos: dict[int, float] = {}
            j = i + 1
            while j < len(fatia) and fatia[j][0] != "0":
                c, v = fatia[j]
                if c == "8":
                    camada = v
                elif c in ("10", "11", "20", "21"):
                    pontos[int(c)] = float(v)
                j += 1
            if 10 in pontos and 20 in pontos and 11 in pontos and 21 in pontos:
                seg = [(pontos[10], pontos[20]), (pontos[11], pontos[21])]
                if not _curto(seg):
                    segmentos.append({"camada": camada, "pontos": seg})
            i = j
        elif codigo == "0" and valor == "LWPOLYLINE":
            camada = ""
            fechada = False
            vertices: list[tuple[float, float]] = []
            j = i + 1
            while j < len(fatia) and fatia[j][0] != "0":
                c, v = fatia[j]
                if c == "8":
                    camada = v
                elif c == "70":
                    fechada = (int(v) & 1) == 1
                elif c in ("10", "20"):
                    if c == "10":
                        vertices.append((float(v), 0.0))
                    else:
                        x, _ = vertices[-1]
                        vertices[-1] = (x, float(v))
                j += 1
            if len(vertices) >= 2:
                if fechada and vertices[0] != vertices[-1]:
                    vertices.append(vertices[0])
                for k in range(len(vertices) - 1):
                    seg = [vertices[k], vertices[k + 1]]
                    if not _curto(seg):
                        segmentos.append({"camada": camada, "pontos": seg})
            i = j
        else:
            i += 1  # entidade não-LINE: anda um par e continua procurando o próximo "0"
    if not segmentos:
        raise ErroAPI(422, "valor_invalido", "DXF sem linha (LINE/LWPOLYLINE) aproveitável")
    if len(segmentos) > limites.PARCELA_DXF_LINHAS_MAX:
        raise ErroAPI(422, "regras_demais",
                      f"o teto são {limites.PARCELA_DXF_LINHAS_MAX} linhas por rodada de DXF")
    return segmentos


def _curto(seg: list[tuple[float, float]]) -> bool:
    (x1, y1), (x2, y2) = seg
    return abs(x1 - x2) < TOLERANCIA and abs(y1 - y2) < TOLERANCIA


def ler_arquivo(caminho: str | Path) -> list[dict]:
    """Lê o arquivo do disco (ASCII; Latin-1 primeiro porque é o padrão de quem exportou CAD
    antigo, UTF-8 na volta — os nomes de camada que importam são ASCII nos dois)."""
    dados = Path(caminho).read_bytes()
    try:
        texto = dados.decode("utf-8")
    except UnicodeDecodeError:
        texto = dados.decode("latin-1")
    return ler(texto)


def importar(cur, tenant_id: int, *, segmentos: list[dict], registro_id, origem="derivada") -> dict:
    """Cria pontos (deduplicados por coordenada) e linhas a partir dos segmentos. O rumo e a
    distância são CALCULADOS da geometria (origem derivada: a precisão fica NULA — ausência
    declarada, não inferência). Devolve contagens."""
    if origem not in modelo.ORIGENS:
        raise ErroAPI(422, "tipo_invalido", f"origem precisa ser uma de: {', '.join(modelo.ORIGENS)}")
    chaves: dict[tuple[float, float], str] = {}
    pontos = 0
    linha_ids: list[str] = []

    def _ponto(x: float, y: float) -> str:
        nonlocal pontos
        chave = (round(x, 6), round(y, 6))
        if chave not in chaves:
            p = modelo.criar_ponto(cur, tenant_id, x=x, y=y, origem=origem, registro_id=registro_id)
            chaves[chave] = str(p["id"])
            pontos += 1
        return chaves[chave]

    for seg in segmentos:
        (x1, y1), (x2, y2) = seg["pontos"]
        de = _ponto(x1, y1)
        para = _ponto(x2, y2)
        if de == para:
            continue
        dist = math.hypot(x2 - x1, y2 - y1)
        rumo = math.degrees(math.atan2(x2 - x1, y2 - y1)) % 360.0  # azimute: 0 = norte = +Y
        ln = modelo.criar_linha(cur, tenant_id, de_ponto_id=de, para_ponto_id=para,
                                rumo_graus=round(rumo, 9), distancia_m=round(dist, 9),
                                tipo_cogo="reta", origem=origem, registro_id=registro_id)
        linha_ids.append(str(ln["id"]))
    return {"pontos": pontos, "linhas": len(linha_ids), "linha_ids": linha_ids}
