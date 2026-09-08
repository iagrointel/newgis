"""Leitura de GeoPackage no esquema TEKSI (item L4-05-e-gas-e-esgoto).

TEKSI é o modelo de dados aberto de rede de esgoto (https://teksi.github.io/wastewater/), em PostGIS. O que o
projeto entrega para trabalho em campo e para troca é a MESMA estrutura num GeoPackage: as camadas são as duas
views de trabalho do modelo, `vw_tww_wastewater_structure` (estruturas: poço de visita, estrutura especial,
ponto de lançamento) e `vw_tww_reach` (trechos), com as colunas prefixadas por tabela de origem (`co_` da
tampa, `ma_` do poço, `wn_` do nó, `ss_` da estrutura especial, `dp_` do lançamento, `rp_from_`/`rp_to_` dos
pontos de extremidade do trecho).

O de-para coluna → atributo NÃO está escrito aqui: ele é lido do pacote de ativos `esgoto-teksi`, onde cada
atributo declara `origem.camada` e `origem.coluna`. Assim existe um lugar só com o mapeamento, o documento
`docs/PACOTE_REDE.md` o publica sozinho, e código e dado não podem divergir.

GeoPackage é SQLite: a leitura usa o `sqlite3` da biblioteca padrão, em modo somente leitura, sem dependência
nova e sem GDAL. A geometria vem no envelope binário do padrão OGC (cabeçalho `GP` + WKB), decodificado aqui
para as coordenadas que a rota de edição de feições já aceita.

ponytail: o importador não adivinha subtipo. `ws_type` diz a espécie (poço, estrutura especial, lançamento) e é
essa que decide o grupo; o TIPO dentro do grupo entra sempre como o primeiro do grupo, porque separar poço de
visita de poço de queda depende de listas de valor do TEKSI que não foram conferidas contra dado real. Cada
feição assim entra com um aviso contado, nunca com um palpite silencioso."""

import sqlite3
import struct
from pathlib import Path

CAMADA_ESTRUTURA = "vw_tww_wastewater_structure"
CAMADA_TRECHO = "vw_tww_reach"
COLUNA_ESPECIE = "ws_type"
# espécie declarada pela view do TEKSI -> (grupo do pacote, código do tipo padrão do grupo)
ESPECIE_PARA_GRUPO = {
    "manhole": ("poco_de_visita", 1),
    "special_structure": ("estrutura_especial", 2),
    "discharge_point": ("ponto_de_lancamento", 1),
}
GRUPO_TRECHO = ("coletor", 1)
TAMANHO_MAX_BYTES = 8 * 1024 * 1024
FEICOES_MAX = 20_000


class ErroTeksi(Exception):
    """Arquivo recusado. `codigo` é curto e vira o código de erro da API."""

    def __init__(self, codigo: str, mensagem: str):
        self.codigo = codigo
        self.mensagem = mensagem
        super().__init__(mensagem)


def mapa_do_pacote(doc: dict) -> dict[str, dict[str, list[tuple[str, str]]]]:
    """{camada: {coluna: [(grupo, código do atributo), ...]}} lido das origens declaradas no pacote."""
    mapa: dict[str, dict[str, list[tuple[str, str]]]] = {}
    for a in doc.get("atributos", []):
        origem = a.get("origem") or {}
        camada, coluna = origem.get("camada"), origem.get("coluna")
        if not camada or not coluna:
            continue
        mapa.setdefault(camada, {}).setdefault(coluna, []).append((a["grupo"], a["codigo"]))
    return mapa


def _geometria(blob: bytes) -> tuple[str, list]:
    """Envelope GeoPackage (`GP`) + WKB → ('Point', [x, y]) ou ('LineString', [[x, y], ...])."""
    if not isinstance(blob, (bytes, bytearray)) or len(blob) < 8 or bytes(blob[:2]) != b"GP":
        raise ErroTeksi("geometria_invalida", "a geometria não está no envelope binário do GeoPackage")
    flags = blob[3]
    envelope = (flags >> 1) & 0x07
    tamanho_envelope = {0: 0, 1: 32, 2: 48, 3: 48, 4: 64}.get(envelope)
    if tamanho_envelope is None:
        raise ErroTeksi("geometria_invalida", "o cabeçalho da geometria declara um envelope inválido")
    wkb = blob[8 + tamanho_envelope:]
    return _wkb(wkb)


def _wkb(wkb: bytes) -> tuple[str, list]:
    if len(wkb) < 5:
        raise ErroTeksi("geometria_invalida", "geometria vazia dentro do GeoPackage")
    ordem = "<" if wkb[0] == 1 else ">"
    (tipo,) = struct.unpack_from(ordem + "I", wkb, 1)
    tem_srid = bool(tipo & 0x20000000)
    base = tipo & 0xFFFF
    dimensoes = 3 if 1000 <= base < 2000 else 4 if 2000 <= base < 4000 else 2
    geometria = base % 1000
    pos = 5 + (4 if tem_srid else 0)
    if geometria == 1:
        coords = struct.unpack_from(ordem + "d" * dimensoes, wkb, pos)
        return "Point", [coords[0], coords[1]]
    if geometria == 2:
        (n,) = struct.unpack_from(ordem + "I", wkb, pos)
        pos += 4
        pontos = []
        for _ in range(n):
            coords = struct.unpack_from(ordem + "d" * dimensoes, wkb, pos)
            pos += 8 * dimensoes
            pontos.append([coords[0], coords[1]])
        return "LineString", pontos
    raise ErroTeksi("geometria_nao_suportada",
                    f"a camada traz geometria de tipo {geometria}; só ponto e linha entram na rede")


def _colunas(con: sqlite3.Connection, tabela: str) -> list[str]:
    return [r[1] for r in con.execute(f'PRAGMA table_info("{tabela}")')]


def _coluna_de_geometria(con: sqlite3.Connection, tabela: str) -> str:
    linha = con.execute(
        "SELECT column_name FROM gpkg_geometry_columns WHERE lower(table_name) = lower(?)", (tabela,)
    ).fetchone()
    if linha is None:
        raise ErroTeksi("camada_sem_geometria",
                        f"a camada {tabela} não está registrada em gpkg_geometry_columns")
    return linha[0]


def _feicao(atributos_linha: dict, mapa_camada: dict, grupo: str, tipo_codigo: int,
            geometria: tuple[str, list]) -> dict:
    atributos: dict = {}
    for coluna, valor in atributos_linha.items():
        if valor is None:
            continue
        for grupo_alvo, codigo in mapa_camada.get(coluna, ()):
            if grupo_alvo == grupo:
                atributos[codigo] = valor
    forma, coords = geometria
    if forma == "Point":
        geom = {"x": coords[0], "y": coords[1]}
    else:
        geom = {"paths": [coords]}
    return {"attributes": {"grupo": grupo, "tipo_codigo": tipo_codigo, "atributos": atributos},
            "geometry": geom}


def ler_geopackage(caminho: str | Path, doc_pacote: dict) -> dict:
    """Lê as duas camadas TEKSI do GeoPackage e devolve as feições no vocabulário do pacote `esgoto-teksi`,
    já no formato do `applyEdits` das camadas de rede (`adds`). Não escreve nada."""
    mapa = mapa_do_pacote(doc_pacote)
    caminho = Path(caminho)
    try:
        con = sqlite3.connect(f"file:{caminho}?mode=ro", uri=True)
    except sqlite3.Error as e:
        raise ErroTeksi("arquivo_ilegivel", f"não foi possível abrir o arquivo: {e}") from e
    try:
        try:
            tabelas = {r[0] for r in con.execute("SELECT table_name FROM gpkg_contents")}
        except sqlite3.Error as e:
            raise ErroTeksi("nao_e_geopackage",
                            "o arquivo não tem a tabela gpkg_contents: não é um GeoPackage") from e
        presentes = {t for t in (CAMADA_ESTRUTURA, CAMADA_TRECHO) if t in tabelas}
        if not presentes:
            raise ErroTeksi("camadas_teksi_ausentes",
                            f"o GeoPackage não traz nenhuma das camadas do TEKSI ({CAMADA_ESTRUTURA}, "
                            f"{CAMADA_TRECHO}); as camadas encontradas foram: "
                            f"{', '.join(sorted(tabelas)) or '(nenhuma)'}")
        pontos: list[dict] = []
        linhas: list[dict] = []
        avisos: list[dict] = []
        contagens = {"estruturas_lidas": 0, "trechos_lidos": 0, "ignoradas": 0}

        if CAMADA_ESTRUTURA in presentes:
            colunas = _colunas(con, CAMADA_ESTRUTURA)
            if COLUNA_ESPECIE not in colunas:
                raise ErroTeksi("coluna_ausente",
                                f"a camada {CAMADA_ESTRUTURA} não traz a coluna {COLUNA_ESPECIE}, que é a que "
                                f"diz a espécie da estrutura")
            geom_col = _coluna_de_geometria(con, CAMADA_ESTRUTURA)
            mapa_camada = mapa.get(CAMADA_ESTRUTURA, {})
            especies_sem_correspondencia: dict[str, int] = {}
            for linha in con.execute(f'SELECT * FROM "{CAMADA_ESTRUTURA}"'):
                registro = dict(zip(colunas, linha, strict=True))
                especie = registro.get(COLUNA_ESPECIE)
                alvo = ESPECIE_PARA_GRUPO.get(especie)
                if alvo is None:
                    especies_sem_correspondencia[str(especie)] = \
                        especies_sem_correspondencia.get(str(especie), 0) + 1
                    contagens["ignoradas"] += 1
                    continue
                grupo, tipo_codigo = alvo
                pontos.append(_feicao(registro, mapa_camada, grupo, tipo_codigo,
                                      _geometria(registro.get(geom_col))))
                contagens["estruturas_lidas"] += 1
                _limite(len(pontos) + len(linhas))
            for especie, n in sorted(especies_sem_correspondencia.items()):
                avisos.append({"aviso": "especie_sem_correspondencia", "valor": especie, "feicoes": n,
                               "mensagem": f"{n} estrutura(s) com ws_type {especie!r} ficaram de fora: o "
                                           f"pacote esgoto-teksi não tem grupo para essa espécie"})

        if CAMADA_TRECHO in presentes:
            colunas = _colunas(con, CAMADA_TRECHO)
            geom_col = _coluna_de_geometria(con, CAMADA_TRECHO)
            mapa_camada = mapa.get(CAMADA_TRECHO, {})
            grupo, tipo_codigo = GRUPO_TRECHO
            for linha in con.execute(f'SELECT * FROM "{CAMADA_TRECHO}"'):
                registro = dict(zip(colunas, linha, strict=True))
                linhas.append(_feicao(registro, mapa_camada, grupo, tipo_codigo,
                                      _geometria(registro.get(geom_col))))
                contagens["trechos_lidos"] += 1
                _limite(len(pontos) + len(linhas))
    finally:
        con.close()

    if contagens["estruturas_lidas"]:
        avisos.append({"aviso": "tipo_padrao_do_grupo", "valor": None,
                       "feicoes": contagens["estruturas_lidas"],
                       "mensagem": "toda estrutura entrou com o primeiro tipo do seu grupo; o subtipo do TEKSI "
                                   "(poço de queda, extravasor, elevatória) depende de listas de valor ainda "
                                   "não conferidas contra dado real"})
    if contagens["trechos_lidos"]:
        avisos.append({"aviso": "tipo_padrao_do_grupo", "valor": None, "feicoes": contagens["trechos_lidos"],
                       "mensagem": "todo trecho entrou como coletor de rede; a função hierárquica do TEKSI "
                                   "distingue tronco, interceptor e emissário por lista de valor ainda não "
                                   "conferida contra dado real"})
    return {"pontos": pontos, "linhas": linhas, "avisos": avisos, "contagens": contagens}


def _limite(quantas: int) -> None:
    if quantas > FEICOES_MAX:
        raise ErroTeksi("feicoes_demais",
                        f"o GeoPackage traz mais de {FEICOES_MAX} feições nas camadas do TEKSI; parta o "
                        f"arquivo por bacia")
