"""Rede simples (item L4-18-rede-simples-trace-network): o equivalente de disciplina ao Trace Network da
Esri — hidrografia, ferrovia, drenagem. Rede SEM pacote de ativos, SEM regra de negócio e SEM terminal de
dispositivo: só junções e trechos, com direção de fluxo declarada por ATRIBUTO do trecho
(digitalizada/contra/indeterminada) e os atributos de rede que o inquilino escolher.

Decisão de construção (evita duplicar a linha L4 inteira): a rede simples reusa as feições
(`plat.rede_feicao_ponto`/`rede_feicao_linha`), a topologia derivada de L4-01-b e os traçados de L4-02. Para
isso ela recebe, na criação, um CATÁLOGO MÍNIMO interno — 1 domínio, 1 tier, 2 grupos (junção/trecho), 2
tipos, 1 configuração de terminal com um único terminal e NENHUM caminho válido. As consequências desse
"nenhum caminho válido" são exatamente as que se quer numa rede simples:

  * o traçado conectado (`tracado.py`) não acrescenta aresta virtual nenhuma — não há dispositivo a
    atravessar, então a rede é só a topologia dos trechos;
  * a junção tem UM terminal, logo `topologia._resolver_uniao` a funde direto com as pontas de trecho
    coincidentes (nunca cai no ramo de dispositivo multi-terminal);
  * `subrede` e `isolados` continuam existindo, mas sem categoria `transformacao` nem `fonte` no catálogo
    mínimo eles não separam nada — é por isso que a rede simples só ANUNCIA conectado, montante, jusante e
    caminho mais curto (ver docs/rede/REDE_SIMPLES.md, seção de paridade).

O catálogo mínimo NÃO é um pacote de ativos: enquanto `plat.rede.modo = 'simples'`, as colunas
`plat.rede.pacote_*` ficam nulas e `GET /api/rede/{id}/pacote` devolve 404. `promover()` é que carimba o
pacote mínimo — o MESMO documento, agora passado pelo validador do pacote, com sha256 e bytes — e muda o modo
para 'utilidades'."""

import hashlib
import json
import re

from app.erros import ErroAPI
from app.rede_utilidades import deposito
from app.rede_utilidades import pacote as pacote_mod

DIRECOES = ("digitalizada", "contra", "indeterminada")
DIRECAO_PADRAO = "digitalizada"
CAMPO_DIRECAO_INTERNO = "direcao_fluxo"  # chave gravada em rede_feicao_linha.atributos
NOME_SQL = re.compile(r"^[a-z][a-z0-9_]{0,62}$")
FEICOES_MAX = 200_000  # teto por camada: acima disso a carga vira trabalho de importação, não de uma chamada
TIPOS_DADO_ATRIBUTO = ("texto", "inteiro", "real", "data", "booleano")
# geometria declarada da camada (o vocabulário do tipo `camada_vetorial`) aceita em cada papel. "Geometry"
# (mista) entra nos dois: a carga filtra por `GeometryType` feição a feição.
GEOMETRIA_ACEITA = {"linha": ("LineString", "MultiLineString", "Geometry"),
                    "ponto": ("Point", "MultiPoint", "Geometry")}


def doc_minimo(disciplina: str, nome: str) -> dict:
    """O catálogo mínimo, na forma do pacote de ativos (`app/rede_utilidades/esquema.py`). É a ÚNICA
    descrição desse catálogo no produto: a criação da rede simples o grava (e depois zera as colunas de
    pacote) e `promover` grava o mesmo documento como pacote de verdade."""
    return {
        "esquema": "plat.rede.pacote",
        "esquema_versao": pacote_mod.versao_do_esquema(),
        "pacote": {
            "codigo": "rede-simples",
            "nome": f"Catálogo mínimo da rede simples {nome}"[:200],
            "versao": "1.0.0",
            "disciplina": disciplina,
            "descricao": "Catálogo mínimo gerado pela plataforma ao promover uma rede simples: junções e "
                         "trechos, sem dispositivo, sem categoria e sem terminal de manobra.",
        },
        "dominios": [{"codigo": "rede", "nome": "Rede", "tipo": "dominio", "disciplina": disciplina,
                      "ordem": 1}],
        "tiers": [{"codigo": "unico", "dominio": "rede", "nome": "Único", "ordem": 1,
                   "tipo": "hierarquico"}],
        "categorias": [],
        "terminais": [{
            "codigo": "juncao-simples", "nome": "Junção de um terminal",
            "terminais": [{"id": 1, "nome": "único", "montante": False}],
            "caminhos_validos": [],
        }],
        "grupos": [
            {"codigo": "juncao", "dominio": "rede", "nome": "Junções", "geometria": "ponto",
             "camadas_fonte": []},
            {"codigo": "trecho", "dominio": "rede", "nome": "Trechos", "geometria": "linha",
             "camadas_fonte": []},
        ],
        "tipos": [
            {"codigo": 1, "grupo": "juncao", "chave": "juncao", "nome": "Junção", "tier": "unico",
             "categorias": [], "terminal": "juncao-simples", "codigos_fonte": []},
            {"codigo": 1, "grupo": "trecho", "chave": "trecho", "nome": "Trecho", "tier": "unico",
             "categorias": [], "terminal": "juncao-simples", "codigos_fonte": []},
        ],
        "atributos": [{
            "codigo": CAMPO_DIRECAO_INTERNO, "grupo": "trecho", "tipo": 1, "nome": "Direção de fluxo",
            "tipo_dado": "texto", "unidade": None, "obrigatorio": True,
        }],
        "regras": [{
            "tipo": "conectividade_no_trecho", "de": "juncao/1", "para": "trecho/1",
            "descricao": "uma junção conecta a ponta de um trecho coincidente dentro da tolerância da rede",
        }],
    }


def _tipo_id(cur, rede_id: str, grupo: str) -> str:
    cur.execute(
        "SELECT tp.id FROM plat.rede_tipo tp JOIN plat.rede_grupo g ON g.id = tp.grupo_id "
        "WHERE tp.rede_id = %s::uuid AND g.codigo = %s AND tp.codigo = 1",
        (rede_id, grupo),
    )
    r = cur.fetchone()
    if r is None:
        raise ErroAPI(409, "catalogo_minimo_ausente",
                      "esta rede não tem o catálogo mínimo da rede simples")
    return str(r["id"])


def instalar_catalogo_minimo(cur, tenant_id: int, rede_id: str, usuario_id: int, disciplina: str,
                             nome: str) -> dict:
    """Grava o catálogo mínimo e ZERA as colunas de pacote: a rede simples tem catálogo, não tem pacote."""
    doc = doc_minimo(disciplina, nome)
    contagens = deposito.importar(cur, tenant_id, rede_id, doc, usuario_id, "0" * 64, 0)
    cur.execute(
        "UPDATE plat.rede SET pacote_codigo = NULL, pacote_nome = NULL, pacote_descricao = NULL, "
        "pacote_versao = NULL, pacote_esquema_versao = NULL, pacote_fonte = NULL, pacote_sha256 = NULL, "
        "pacote_bytes = NULL, importado_em = NULL, importado_por = NULL, modo = 'simples' "
        "WHERE id = %s::uuid",
        (rede_id,),
    )
    return contagens


def promover(cur, tenant_id: int, rede_id: str, usuario_id: int) -> dict:
    """'Promover a rede de utilidades': carimba o PACOTE MÍNIMO (o catálogo que a rede já usava, exportado
    das tabelas, posto na forma canônica e validado pelo mesmo `pacote.ler` de qualquer pacote) e muda o modo
    para 'utilidades'.

    ⛔ Por que NÃO se reimporta o documento aqui: `deposito.importar` apaga o catálogo antes de gravar, e as
    feições da rede (`rede_feicao_ponto`/`rede_feicao_linha`) têm chave estrangeira para `rede_tipo` com
    ON DELETE CASCADE — reimportar levaria junto TODAS as feições e a topologia da rede (medido: a rede
    ficava vazia depois de promovida). O catálogo já é exatamente o que o pacote descreve; promover é
    carimbar a procedência, não recarregar."""
    cur.execute("SELECT nome, disciplina, modo FROM plat.rede WHERE id = %s::uuid FOR UPDATE", (rede_id,))
    r = cur.fetchone()
    if r is None:
        raise ErroAPI(404, "rede_inexistente", "rede inexistente")
    if r["modo"] != "simples":
        raise ErroAPI(409, "rede_nao_e_simples", "só uma rede simples pode ser promovida a rede de utilidades")
    meta = doc_minimo(r["disciplina"], r["nome"])["pacote"]
    cur.execute(
        "UPDATE plat.rede SET pacote_codigo = %s, pacote_nome = %s, pacote_descricao = %s, "
        "pacote_versao = %s, pacote_esquema_versao = %s, pacote_sha256 = %s, pacote_bytes = 0, "
        "importado_em = now(), importado_por = %s, modo = 'utilidades' WHERE id = %s::uuid",
        (meta["codigo"], meta["nome"], meta["descricao"], meta["versao"], pacote_mod.versao_do_esquema(),
         "0" * 64, usuario_id, rede_id),
    )
    doc = deposito.exportar(cur, rede_id)  # o catálogo REAL da rede, reconstruído das tabelas
    bruto = pacote_mod.canonizar(doc)
    pacote_mod.ler(bruto)  # o pacote mínimo passa pelo MESMO validador de qualquer pacote; erro sobe como 422
    sha = hashlib.sha256(bruto).hexdigest()
    cur.execute("UPDATE plat.rede SET pacote_sha256 = %s, pacote_bytes = %s WHERE id = %s::uuid",
                (sha, len(bruto), rede_id))
    contagens = {secao: len(doc[secao]) for secao in pacote_mod.SECOES}
    return {"rede_id": rede_id, "modo": "utilidades", "codigo": meta["codigo"], "versao": meta["versao"],
            "sha256": sha, "bytes": len(bruto), "contagens": contagens}


# --- carga a partir de duas camadas do inquilino ----------------------------------------------------------

def _camada(cur, item_id: str | None, geometria_esperada: str) -> dict | None:
    """A camada vetorial do inquilino (`plat.item` tipo `camada_vetorial`): schema, tabela e campos. `None`
    quando o pedido não trouxe a camada (a de pontos é opcional: uma rede simples pode ser só de trechos)."""
    if item_id is None:
        return None
    cur.execute("SELECT tipo, titulo, dados FROM plat.item WHERE id = %s::uuid", (item_id,))
    r = cur.fetchone()
    if r is None:
        raise ErroAPI(404, "camada_inexistente", f"a camada {item_id} não existe neste inquilino")
    if r["tipo"] != "camada_vetorial":
        raise ErroAPI(422, "item_nao_e_camada", f"o item {item_id} é do tipo {r['tipo']}, não camada_vetorial")
    dados = r["dados"] or {}
    schema, tabela = dados.get("schema"), dados.get("tabela")
    if not schema or not tabela or not NOME_SQL.match(schema) or not NOME_SQL.match(tabela):
        raise ErroAPI(422, "camada_sem_tabela", f"a camada {r['titulo']!r} não aponta para uma tabela válida")
    geometria = dados.get("geometria")
    if geometria not in GEOMETRIA_ACEITA[geometria_esperada]:
        raise ErroAPI(422, "geometria_incompativel",
                      f"a camada {r['titulo']!r} é de geometria {geometria!r}; no papel de "
                      f"{geometria_esperada} só entram {GEOMETRIA_ACEITA[geometria_esperada]}")
    campos = [c for c in (dados.get("campos") or []) if NOME_SQL.match(str(c.get("nome", "")))]
    return {"id": item_id, "titulo": r["titulo"], "schema": schema, "tabela": tabela,
            "campos": campos, "geometria": geometria_esperada}


def _jsonb_atributos(cur, campos: list[dict], extra_sql: str | None) -> str:
    """`jsonb_build_object` com os campos declarados da camada (nomes conferidos contra `NOME_SQL`), mais o
    par da direção de fluxo quando houver. Sem `to_jsonb(t)`: isso arrastaria a geometria inteira para dentro
    do jsonb de cada feição."""
    partes = []
    for c in campos:
        nome = c["nome"]
        partes.append(cur.mogrify("%s", (nome,)).decode("utf-8"))
        partes.append(f't."{nome}"')
    if extra_sql:
        partes.append(cur.mogrify("%s", (CAMPO_DIRECAO_INTERNO,)).decode("utf-8"))
        partes.append(extra_sql)
    if not partes:
        return "'{}'::jsonb"
    return "jsonb_strip_nulls(jsonb_build_object(" + ", ".join(partes) + "))"


def _sql_direcao(cur, campo_direcao: str | None, mapa_direcao: dict) -> str:
    """SQL que resolve a direção de fluxo do trecho a partir do atributo declarado. Sem campo declarado,
    toda a rede é lida como DIGITALIZADA — é o mesmo padrão do Trace Network recém-criado, e fica escrito no
    documento da rede simples. Valor fora do mapa vira 'indeterminada': o traçado para nele com aviso, nunca
    escolhe um sentido por conta própria."""
    if campo_direcao is None:
        return cur.mogrify("%s", (DIRECAO_PADRAO,)).decode("utf-8")
    mapa_lit = cur.mogrify("%s::jsonb", (_json(mapa_direcao),)).decode("utf-8")
    padrao = cur.mogrify("%s", ("indeterminada",)).decode("utf-8")
    return (f'coalesce({mapa_lit} ->> lower(btrim(coalesce(t."{campo_direcao}"::text, \'\'))), {padrao})')


def _json(v) -> str:
    return json.dumps(v, ensure_ascii=False)


def _contar(cur, camada: dict) -> int:
    cur.execute(f'SELECT count(*) AS n FROM "{camada["schema"]}"."{camada["tabela"]}"')  # noqa: S608
    return int(cur.fetchone()["n"])


def carregar_camadas(cur, tenant_id: int, rede_id: str, camada_linha: dict, camada_ponto: dict | None,
                     campo_direcao: str | None, mapa_direcao: dict) -> dict:
    """Copia as feições das duas camadas do inquilino para as camadas de rede (`plat.rede_feicao_*`).
    Multiparte é explodida (`ST_Dump`) — a feição de trecho da rede é LineString simples; trecho com menos de
    2 vértices é descartado e contado. A geometria é reprojetada para 4326 (a coluna da rede é 4326)."""
    tipo_trecho = _tipo_id(cur, rede_id, "trecho")
    n_linhas = _contar(cur, camada_linha)
    if n_linhas > FEICOES_MAX:
        raise ErroAPI(422, "camada_grande_demais",
                      f"a camada de linhas tem {n_linhas} feições; o teto desta chamada é {FEICOES_MAX}")
    if campo_direcao is not None and not any(c["nome"] == campo_direcao for c in camada_linha["campos"]):
        raise ErroAPI(422, "campo_direcao_inexistente",
                      f"a camada de linhas não tem o campo {campo_direcao!r}")

    direcao_sql = _sql_direcao(cur, campo_direcao, mapa_direcao)
    atributos_sql = _jsonb_atributos(cur, camada_linha["campos"], direcao_sql)
    cur.execute(
        f"INSERT INTO plat.rede_feicao_linha(tenant_id, rede_id, tipo_id, geom, atributos) "  # noqa: S608
        f"SELECT %s, %s::uuid, %s::uuid, ST_Transform(d.geom, 4326), {atributos_sql} "
        f'FROM "{camada_linha["schema"]}"."{camada_linha["tabela"]}" t, LATERAL ST_Dump(t.geom) d '
        f"WHERE t.geom IS NOT NULL AND GeometryType(d.geom) = 'LINESTRING' AND ST_NPoints(d.geom) >= 2",
        (tenant_id, rede_id, tipo_trecho),
    )
    trechos = cur.rowcount

    pontos = 0
    if camada_ponto is not None:
        tipo_juncao = _tipo_id(cur, rede_id, "juncao")
        n_pontos = _contar(cur, camada_ponto)
        if n_pontos > FEICOES_MAX:
            raise ErroAPI(422, "camada_grande_demais",
                          f"a camada de pontos tem {n_pontos} feições; o teto desta chamada é {FEICOES_MAX}")
        atributos_ponto = _jsonb_atributos(cur, camada_ponto["campos"], None)
        cur.execute(
            f"INSERT INTO plat.rede_feicao_ponto(tenant_id, rede_id, tipo_id, geom, atributos) "  # noqa: S608
            f"SELECT %s, %s::uuid, %s::uuid, ST_Transform(d.geom, 4326), {atributos_ponto} "
            f'FROM "{camada_ponto["schema"]}"."{camada_ponto["tabela"]}" t, LATERAL ST_Dump(t.geom) d '
            f"WHERE t.geom IS NOT NULL AND GeometryType(d.geom) = 'POINT'",
            (tenant_id, rede_id, tipo_juncao),
        )
        pontos = cur.rowcount

    return {"trechos": trechos, "juncoes": pontos, "linhas_na_camada": n_linhas}


def gravar_config(cur, tenant_id: int, rede_id: str, camada_linha: dict, camada_ponto: dict | None,
                  campo_direcao: str | None, mapa_direcao: dict, atributos_rede: list[dict]) -> None:
    cur.execute(
        "INSERT INTO plat.rede_simples(rede_id, tenant_id, camada_linha_id, camada_ponto_id, campo_direcao, "
        "mapa_direcao, atributos_rede) VALUES (%s::uuid, %s, %s::uuid, %s::uuid, %s, %s::jsonb, %s::jsonb) "
        "ON CONFLICT (rede_id) DO UPDATE SET camada_linha_id = EXCLUDED.camada_linha_id, "
        "camada_ponto_id = EXCLUDED.camada_ponto_id, campo_direcao = EXCLUDED.campo_direcao, "
        "mapa_direcao = EXCLUDED.mapa_direcao, atributos_rede = EXCLUDED.atributos_rede",
        (rede_id, tenant_id, camada_linha["id"], camada_ponto["id"] if camada_ponto else None,
         campo_direcao, _json(mapa_direcao), _json(atributos_rede)),
    )


def ler_config(cur, rede_id: str) -> dict | None:
    cur.execute(
        "SELECT rede_id, camada_linha_id, camada_ponto_id, campo_direcao, mapa_direcao, atributos_rede, "
        "criado_em FROM plat.rede_simples WHERE rede_id = %s::uuid", (rede_id,),
    )
    r = cur.fetchone()
    if r is None:
        return None
    return {
        "rede_id": str(r["rede_id"]),
        "camada_linha_id": str(r["camada_linha_id"]) if r["camada_linha_id"] else None,
        "camada_ponto_id": str(r["camada_ponto_id"]) if r["camada_ponto_id"] else None,
        "campo_direcao": r["campo_direcao"], "mapa_direcao": r["mapa_direcao"],
        "atributos_rede": r["atributos_rede"], "criado_em": r["criado_em"],
    }


def conferir_atributos_rede(atributos_rede: list[dict]) -> list[dict]:
    """Atributos de rede declarados: nome do atributo (o mesmo que veio da camada), de onde vem
    (linha/ponto) e tipo de dado. É o vocabulário que o traçado pode usar como custo; declarar aqui é o que
    separa 'atributo qualquer da camada' de 'atributo DE REDE'."""
    saida = []
    for a in atributos_rede:
        nome = str(a.get("nome", ""))
        if not NOME_SQL.match(nome):
            raise ErroAPI(422, "atributo_rede_invalido", f"nome de atributo de rede inválido: {nome!r}")
        tipo_dado = a.get("tipo_dado", "texto")
        if tipo_dado not in TIPOS_DADO_ATRIBUTO:
            raise ErroAPI(422, "atributo_rede_invalido",
                          f"tipo de dado {tipo_dado!r} fora de {TIPOS_DADO_ATRIBUTO}")
        de = a.get("de", "linha")
        if de not in ("linha", "ponto"):
            raise ErroAPI(422, "atributo_rede_invalido", "o campo 'de' do atributo de rede é 'linha' ou 'ponto'")
        saida.append({"nome": nome, "tipo_dado": tipo_dado, "de": de})
    return saida
