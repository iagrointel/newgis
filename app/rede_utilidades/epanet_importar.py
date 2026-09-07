"""Job `rede.epanet_importar` (item L4-05-d-epanet-inp; ADR 20260907T1629): lê `plat.rede_importacao_epanet`,
faz o parse do `.inp` (`epanet_inp.ler_inp`) e grava as feições da rede (`plat.rede_feicao_ponto`/
`rede_feicao_linha`, item L4-01-b) sobre o pacote `agua-epanet` já importado na rede alvo.

Fluxo: pendente -> executando -> concluida|falhou. Nunca lê o índice de topologia (isso é outro passo,
`POST /api/rede/{id}/topologia/habilitar`, item L4-01-b) — este job só povoa as camadas.

CRS: o `.inp` do EPANET não declara sistema de coordenadas. Se todo par (X,Y) de `[COORDINATES]` cai dentro da
faixa geográfica válida (-180..180, -90..90), a coordenada é lida como WGS84 (EPSG:4326) direto. Fora disso
(coordenada PROJETADA — o caso real medido: SIRGAS 2000 / UTM 23S, `brasilia_caesb.inp`, valores ~187000/
8252000) é OBRIGATÓRIO informar `crs_epsg` (parâmetro do job/da rota): nunca se adivinha um EPSG por
"parecer" UTM — a falha é um erro claro (`ErroImportacaoEpanet`), nunca um ponto errado calado."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

import pyproj
from pydantic import BaseModel

from app.jobs.registro import FalhaDefinitiva, tarefa
from app.rede_utilidades import epanet_inp
from app.rede_utilidades.topologia import _inserir_lote

LOTE = 4000
TAMANHO_MAX_BYTES = 20 * 1024 * 1024


class ErroImportacaoEpanet(Exception):
    """Entrada recusada antes de qualquer gravação (CRS ausente, rede sem o pacote agua-epanet, .inp inválido)."""


class EpanetImportarParametros(BaseModel):
    importacao_id: uuid.UUID


def _dentro_de_wgs84(x: float, y: float) -> bool:
    return -180.0 <= x <= 180.0 and -90.0 <= y <= 90.0


@dataclass
class _Transformador:
    crs_epsg: int | None
    _t: object | None = None

    def __call__(self, x: float, y: float) -> tuple[float, float]:
        if self.crs_epsg is None:
            if not _dentro_de_wgs84(x, y):
                raise ErroImportacaoEpanet(
                    f"coordenada ({x}, {y}) fora da faixa geográfica válida (-180..180, -90..90): o .inp usa "
                    "um sistema de coordenadas PROJETADO e o parâmetro crs_epsg (código EPSG de origem) não "
                    "foi informado — nunca se adivinha a projeção"
                )
            return x, y
        if self._t is None:
            self._t = pyproj.Transformer.from_crs(self.crs_epsg, 4326, always_xy=True)
        lon, lat = self._t.transform(x, y)
        return lon, lat


def _tipos_da_rede(cur, rede_id: str) -> dict:
    cur.execute(
        "SELECT g.codigo AS grupo, tp.codigo AS tipo_codigo, tp.id FROM plat.rede_tipo tp "
        "JOIN plat.rede_grupo g ON g.id = tp.grupo_id WHERE tp.rede_id = %s::uuid",
        (rede_id,),
    )
    return {(r["grupo"], r["tipo_codigo"]): r["id"] for r in cur.fetchall()}


GRUPOS_EXIGIDOS = {
    ("no", 1), ("reservatorio_de_nivel_fixo", 1), ("reservatorio_de_nivel_variavel", 1),
    ("tubulacao", 1), ("tubulacao", 2), ("bomba", 1), ("bomba", 2),
    ("valvula", 1), ("valvula", 2), ("valvula", 3), ("valvula", 4), ("valvula", 5), ("valvula", 6),
}


def montar_feicoes(doc: epanet_inp.DocumentoEpanet, crs_epsg: int | None) -> dict:
    """Monta as listas de pontos e linhas prontas para gravar, mais os avisos e a contagem por grupo do
    ARQUIVO (para a cláusula "contagens iguais ao arquivo"). Não toca banco."""
    transformar = _Transformador(crs_epsg)
    avisos: list[str] = list(doc.avisos)
    pontos: list[dict] = []
    linhas: list[dict] = []
    coord_lonlat: dict[str, tuple[float, float] | None] = {}
    n_sem_coordenada = 0

    def posicao(node_id: str) -> tuple[float, float] | None:
        if node_id in coord_lonlat:
            return coord_lonlat[node_id]
        bruta = doc.coordinates.get(node_id)
        pos = transformar(*bruta) if bruta is not None else None
        coord_lonlat[node_id] = pos
        return pos

    for j in doc.junctions:
        pos = posicao(j["id"])
        if pos is None:
            n_sem_coordenada += 1
            avisos.append(f"nó {j['id']!r} (JUNCTIONS) sem linha em [COORDINATES]: importado sem geometria")
        bruta = doc.coordinates.get(j["id"])
        pontos.append({
            "grupo": "no", "tipo_codigo": 1, "lonlat": pos,
            "atributos": {
                "no_id": j["id"], "no_elevacao": j["elev"], "no_demanda": j.get("demand") or 0.0,
                "no_padrao_de_demanda": j.get("pattern"),
                "no_x": bruta[0] if bruta else None, "no_y": bruta[1] if bruta else None,
            },
        })
    for r in doc.reservoirs:
        pos = posicao(r["id"])
        if pos is None:
            n_sem_coordenada += 1
            avisos.append(f"nó {r['id']!r} (RESERVOIRS) sem linha em [COORDINATES]: importado sem geometria")
        bruta = doc.coordinates.get(r["id"])
        pontos.append({
            "grupo": "reservatorio_de_nivel_fixo", "tipo_codigo": 1, "lonlat": pos,
            "atributos": {
                "reservatorio_fixo_id": r["id"], "reservatorio_fixo_carga": r["head"],
                "reservatorio_fixo_padrao_de_carga": r.get("pattern"),
                "_x": bruta[0] if bruta else None, "_y": bruta[1] if bruta else None,
            },
        })
    for t in doc.tanks:
        pos = posicao(t["id"])
        if pos is None:
            n_sem_coordenada += 1
            avisos.append(f"nó {t['id']!r} (TANKS) sem linha em [COORDINATES]: importado sem geometria")
        bruta = doc.coordinates.get(t["id"])
        pontos.append({
            "grupo": "reservatorio_de_nivel_variavel", "tipo_codigo": 1, "lonlat": pos,
            "atributos": {
                "reservatorio_variavel_id": t["id"], "reservatorio_variavel_cota_de_fundo": t["elevation"],
                "reservatorio_variavel_diametro": t["diameter"],
                "reservatorio_variavel_nivel_inicial": t["init_level"],
                "reservatorio_variavel_nivel_minimo": t["min_level"],
                "reservatorio_variavel_nivel_maximo": t["max_level"],
                "reservatorio_variavel_volume_minimo": t.get("min_vol") or 0.0,
                "reservatorio_variavel_curva_de_volume": t.get("vol_curve"),
                "reservatorio_variavel_extravasa": t.get("overflow"),
                "_x": bruta[0] if bruta else None, "_y": bruta[1] if bruta else None,
            },
        })

    def _ponto_medio(n1: str, n2: str) -> tuple[float, float] | None:
        p1, p2 = doc.coordinates.get(n1), doc.coordinates.get(n2)
        if p1 is None or p2 is None:
            return None
        return transformar((p1[0] + p2[0]) / 2.0, (p1[1] + p2[1]) / 2.0)

    for b in doc.pumps:
        pos = _ponto_medio(b["node1"], b["node2"])
        tipo_codigo = 1 if b.get("head_curve") else 2
        if pos is None:
            avisos.append(f"bomba {b['id']!r}: um dos nós ({b['node1']!r}/{b['node2']!r}) sem coordenada; "
                          "importada sem geometria")
        pontos.append({
            "grupo": "bomba", "tipo_codigo": tipo_codigo, "lonlat": pos,
            "atributos": {
                "bomba_id": b["id"], "bomba_no_1": b["node1"], "bomba_no_2": b["node2"],
                "bomba_padrao_de_operacao": b.get("pattern"), "bomba_rotacao_relativa": b.get("speed"),
                "bomba_curva": b.get("head_curve"), "bomba_potencia": b.get("power"),
            },
        })
    for v in doc.valves:
        pos = _ponto_medio(v["node1"], v["node2"])
        tipo_codigo = epanet_inp.TIPO_VALVULA[v["type"]]
        if pos is None:
            avisos.append(f"válvula {v['id']!r}: um dos nós ({v['node1']!r}/{v['node2']!r}) sem coordenada; "
                          "importada sem geometria")
        pontos.append({
            "grupo": "valvula", "tipo_codigo": tipo_codigo, "lonlat": pos,
            "atributos": {
                "valvula_id": v["id"], "valvula_no_1": v["node1"], "valvula_no_2": v["node2"],
                "valvula_ajuste": v.get("setting") or 0.0, "valvula_diametro": v["diameter"],
                "valvula_perda_localizada": v.get("minor_loss") or 0.0,
            },
        })

    n_pipes_sem_geom = 0
    for p in doc.pipes:
        p1, p2 = posicao(p["node1"]), posicao(p["node2"])
        coords = None
        if p1 is not None and p2 is not None:
            meio = [transformar(x, y) for x, y in doc.vertices.get(p["id"], [])]
            coords = [p1, *meio, p2]
        else:
            n_pipes_sem_geom += 1
            avisos.append(f"trecho {p['id']!r}: um dos nós ({p['node1']!r}/{p['node2']!r}) sem coordenada; "
                          "importado sem geometria")
        linhas.append({
            "grupo": "tubulacao", "tipo_codigo": 2 if (p.get("status") or "").upper() == "CV" else 1,
            "coords": coords,
            "atributos": {
                "tubulacao_id": p["id"], "tubulacao_no_1": p["node1"], "tubulacao_no_2": p["node2"],
                "tubulacao_comprimento": p["length"], "tubulacao_diametro": p["diameter"],
                "tubulacao_rugosidade": p["roughness"], "tubulacao_perda_localizada": p.get("minor_loss") or 0.0,
                "tubulacao_situacao": p.get("status") or "Open",
            },
        })

    return {
        "pontos": pontos, "linhas": linhas, "avisos": avisos,
        "contagens_arquivo": doc.contagens(),
        "n_sem_coordenada": n_sem_coordenada, "n_pipes_sem_geometria": n_pipes_sem_geom,
        # PATTERNS/CURVES não são "ativo" do pacote agua-epanet (não têm grupo/tipo, ver ADR 20260907T1629
        # seção "curvas e padrões"); guardadas à parte para a exportação reconstruir [PATTERNS]/[CURVES].
        "patterns": dict(doc.patterns), "curves": dict(doc.curves),
    }


def gravar(cur, tenant_id: int, rede_id: str, montado: dict, lote: int = LOTE) -> dict:
    """Grava pontos e linhas montados; devolve a contagem por grupo REALMENTE inserida (comparável 1:1 contra
    `contagens_arquivo`)."""
    tipos = _tipos_da_rede(cur, rede_id)
    faltando = {(g, c) for (g, c) in GRUPOS_EXIGIDOS if (g, c) not in tipos}
    if len(faltando) == len(GRUPOS_EXIGIDOS):
        raise ErroImportacaoEpanet(
            "a rede não tem o pacote de ativos 'agua-epanet' importado (nenhum grupo/tipo esperado existe); "
            "importe o pacote primeiro (POST /api/rede/{id}/pacote)"
        )

    linhas_pontos = []
    contagem_pontos: dict[str, int] = {}
    for pt in montado["pontos"]:
        tipo_id = tipos.get((pt["grupo"], pt["tipo_codigo"]))
        if tipo_id is None:
            raise ErroImportacaoEpanet(
                f"o pacote da rede não tem o tipo {pt['tipo_codigo']} do grupo {pt['grupo']!r} "
                "(pacote agua-epanet desatualizado?)"
            )
        contagem_pontos[pt["grupo"]] = contagem_pontos.get(pt["grupo"], 0) + 1
        if pt["lonlat"] is None:
            linhas_pontos.append((tenant_id, rede_id, tipo_id, None, pt["atributos"]))
        else:
            lon, lat = pt["lonlat"]
            linhas_pontos.append((tenant_id, rede_id, tipo_id, (lon, lat), pt["atributos"]))

    import json as _json

    def _jsonb(d: dict) -> str:
        return _json.dumps(d, ensure_ascii=False, default=str)

    com_geom = [(t, r, ti, ll[0], ll[1], _jsonb(a)) for t, r, ti, ll, a in linhas_pontos if ll is not None]
    sem_geom = [(t, r, ti, _jsonb(a)) for t, r, ti, ll, a in linhas_pontos if ll is None]
    _inserir_lote(
        cur, "INSERT INTO plat.rede_feicao_ponto(tenant_id, rede_id, tipo_id, geom, atributos) VALUES ",
        com_geom, "(%s,%s::uuid,%s, ST_SetSRID(ST_MakePoint(%s,%s), 4326), %s::jsonb)", lote,
    )
    _inserir_lote(
        cur, "INSERT INTO plat.rede_feicao_ponto(tenant_id, rede_id, tipo_id, geom, atributos) VALUES ",
        sem_geom, "(%s,%s::uuid,%s, NULL, %s::jsonb)", lote,
    )

    linhas_linha = []
    contagem_linhas: dict[str, int] = {}
    for ln in montado["linhas"]:
        tipo_id = tipos.get((ln["grupo"], ln["tipo_codigo"]))
        if tipo_id is None:
            raise ErroImportacaoEpanet(
                f"o pacote da rede não tem o tipo {ln['tipo_codigo']} do grupo {ln['grupo']!r} "
                "(pacote agua-epanet desatualizado?)"
            )
        contagem_linhas[ln["grupo"]] = contagem_linhas.get(ln["grupo"], 0) + 1
        wkt = None
        if ln["coords"]:
            wkt = "LINESTRING(" + ", ".join(f"{x} {y}" for x, y in ln["coords"]) + ")"
        linhas_linha.append((tenant_id, rede_id, tipo_id, wkt, _jsonb(ln["atributos"])))

    com_geom_l = [(t, r, ti, w, a) for t, r, ti, w, a in linhas_linha if w is not None]
    sem_geom_l = [(t, r, ti, a) for t, r, ti, w, a in linhas_linha if w is None]
    _inserir_lote(
        cur, "INSERT INTO plat.rede_feicao_linha(tenant_id, rede_id, tipo_id, geom, atributos) VALUES ",
        com_geom_l, "(%s,%s::uuid,%s, ST_SetSRID(ST_GeomFromText(%s), 4326), %s::jsonb)", lote,
    )
    _inserir_lote(
        cur, "INSERT INTO plat.rede_feicao_linha(tenant_id, rede_id, tipo_id, geom, atributos) VALUES ",
        sem_geom_l, "(%s,%s::uuid,%s, NULL, %s::jsonb)", lote,
    )

    # PATTERNS/CURVES: substitui inteiro (mesma regra do pacote — a importação seguinte é a fonte de verdade).
    cur.execute("DELETE FROM plat.rede_epanet_curva WHERE rede_id = %s::uuid", (rede_id,))
    cur.execute("DELETE FROM plat.rede_epanet_padrao WHERE rede_id = %s::uuid", (rede_id,))
    if montado.get("curves"):
        cur.executemany(
            "INSERT INTO plat.rede_epanet_curva(tenant_id, rede_id, curva_id, pontos) "
            "VALUES (%s, %s::uuid, %s, %s::jsonb)",
            [(tenant_id, rede_id, cid, _jsonb(pontos)) for cid, pontos in montado["curves"].items()],
        )
    if montado.get("patterns"):
        cur.executemany(
            "INSERT INTO plat.rede_epanet_padrao(tenant_id, rede_id, padrao_id, multiplicadores) "
            "VALUES (%s, %s::uuid, %s, %s::jsonb)",
            [(tenant_id, rede_id, pid, _jsonb(mults)) for pid, mults in montado["patterns"].items()],
        )

    return {
        "pontos": len(linhas_pontos), "linhas": len(linhas_linha),
        "pontos_por_grupo": contagem_pontos, "linhas_por_grupo": contagem_linhas,
        "pontos_sem_geometria": len(sem_geom), "linhas_sem_geometria": len(sem_geom_l),
    }


@tarefa(
    nome="rede.epanet_importar",
    descricao="Importa um arquivo EPANET .inp como feições da rede de água (item L4-05-d-epanet-inp)",
    parametros=EpanetImportarParametros,
    # pesado=False (não é subprocesso de SO nem uso de disco fora de controle, ao contrário de
    # `ingestao.carregar`/ogr2ogr): o trabalho é psycopg2 puro em lotes, e ficar fora do advisory lock global
    # "plat.job.pesado" importa de verdade aqui — esse lock é por BANCO, não por trilha/schema (achado deste
    # item, 07/09: com dezenas de trilhas rodando `plat-worker` ao mesmo tempo no mesmo `iagro_sat`, uma delas
    # segura o lock indefinidamente e um job pesado nunca sai de "pendente" nas outras).
    pesado=False,
    memoria_mb=512,
    timeout_s=1800,
    tentativas=1,
    chave=lambda p: f"epanet_importacao:{p.get('importacao_id')}",
    perfil_minimo="editor",
)
def rede_epanet_importar(ctx, importacao_id: uuid.UUID) -> dict:
    iid = str(importacao_id)
    with ctx.db() as cur:
        cur.execute("SELECT * FROM plat.rede_importacao_epanet WHERE id = %s::uuid", (iid,))
        imp = cur.fetchone()
        if imp is None:
            raise FalhaDefinitiva("importação epanet inexistente")
        if imp["estado"] not in ("pendente", "executando"):
            raise FalhaDefinitiva(f"importação em estado {imp['estado']!r}; esperava 'pendente'")
        rede_id = str(imp["rede_id"])
        bruto = bytes(imp["arquivo_bytes"]) if imp["arquivo_bytes"] is not None else None
        crs_epsg = imp["crs_epsg"]
        cur.execute("UPDATE plat.rede_importacao_epanet SET estado = 'executando' WHERE id = %s::uuid", (iid,))
    if bruto is None:
        _marcar_falha(ctx, iid, "arquivo do .inp ausente (já processado ou nunca enviado)")
        raise FalhaDefinitiva("arquivo ausente")
    try:
        ctx.progresso(5, "lendo o .inp")
        texto = bruto.decode("utf-8", errors="replace")
        doc = epanet_inp.ler_inp(texto)
        ctx.progresso(20, "montando as feições")
        montado = montar_feicoes(doc, crs_epsg)
        ctx.progresso(40, "gravando pontos e trechos")
        with ctx.db() as cur:
            gravado = gravar(cur, ctx.tenant_id, rede_id, montado)
            contagens = {
                "arquivo": montado["contagens_arquivo"],
                "gravado": {"pontos": gravado["pontos"], "linhas": gravado["linhas"],
                            "pontos_por_grupo": gravado["pontos_por_grupo"],
                            "linhas_por_grupo": gravado["linhas_por_grupo"]},
                "pontos_sem_geometria": gravado["pontos_sem_geometria"],
                "linhas_sem_geometria": gravado["linhas_sem_geometria"],
            }
            cur.execute(
                "UPDATE plat.rede_importacao_epanet SET estado = 'concluida', contagens = %s::jsonb, "
                "avisos = %s::jsonb, arquivo_bytes = NULL WHERE id = %s::uuid",
                (_dump(contagens), _dump(montado["avisos"]), iid),
            )
        ctx.progresso(100, "concluído")
        return contagens
    except ErroImportacaoEpanet as e:
        _marcar_falha(ctx, iid, str(e))
        raise FalhaDefinitiva(str(e)) from e
    except epanet_inp.ErroInp as e:
        _marcar_falha(ctx, iid, str(e))
        raise FalhaDefinitiva(str(e)) from e


def _dump(v) -> str:
    import json

    return json.dumps(v, ensure_ascii=False, default=str)


def _marcar_falha(ctx, importacao_id: str, erro: str) -> None:
    with ctx.db() as cur:
        cur.execute(
            "UPDATE plat.rede_importacao_epanet SET estado = 'falhou', erro = %s, arquivo_bytes = NULL "
            "WHERE id = %s::uuid AND estado NOT IN ('concluida','falhou')",
            (erro[:2000], importacao_id),
        )
