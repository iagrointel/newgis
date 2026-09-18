"""Continuidade DEC/FEC por conjunto e por alimentador (item L4-10-continuidade-dec-fec).

Cláusulas do portão provadas aqui:

1. "importar os parquets de continuidade para `plat.rede_continuidade` (job, contagem = arquivo)" —
   `test_importa_com_a_contagem_conferida_contra_o_arquivo` importa o dado aberto real da ANEEL e compara,
   arquivo por arquivo, quantas linhas o arquivo tinha no recorte e quantas foram gravadas; o job existe e
   é o mesmo caminho (`test_job_usa_o_mesmo_caminho_da_rota`);
2. "para a cooperativa de teste, DEC/FEC por CONJ aparecem na ficha do conjunto e do alimentador (via UCs)"
   — `test_ficha_do_conjunto_e_do_alimentador_na_cooperativa_de_teste`, sobre as 27.587 unidades
   consumidoras e os 5.481 transformadores reais do ativo da casa;
3. "'dentro do limite' / 'acima do limite' calculado com o limite do ano e a fonte" —
   `test_situacao_usa_o_limite_do_ano_e_diz_de_que_arquivo_veio`;
4. "DIC/FIC médio por trafo a partir de UCBT" — `test_dic_fic_medio_por_trafo`;
5. "painel com série 2020-2025" — `test_painel_traz_a_serie_de_2020_a_2025`;
6. "⛔ frase 'transgressão' nunca aparece" — varredura no `tests/unit/test_rede_continuidade_regras.py` e, aqui,
   sobre o corpo das respostas (`test_nenhuma_resposta_usa_a_palavra_proibida`);
7. a refutação do adversário: `test_refutacao_tres_conjuntos_contra_o_arquivo_da_aneel` reconta três
   conjuntos direto do parquet, em Python puro, sem passar pelo produto; e
   `test_refutacao_conjunto_sem_par_no_arquivo_sai_como_sem_dado` planta um conjunto que a ANEEL não tem e
   exige "sem dado", nunca zero.
"""

# ruff: noqa: F811  (fixtures importadas de módulo irmão: padrão do pytest neste repositório)
from __future__ import annotations

import datetime
import json
import os
import time
from collections import defaultdict
from pathlib import Path

import pytest

from app.rede_utilidades import continuidade, deposito, instalados
from app.rede_utilidades import pacote as pacote_mod
from tests.api.test_rls import contexto, ids_por_slug

MEDIDAS = Path("tests/medidas/L4-10-continuidade-dec-fec.json")
ANO_DE = 2020
ANO_ATE = 2025
# conjunto que não existe no cadastro da agência: é a semente da refutação
CONJUNTO_FANTASMA = 999999999


def _raiz() -> Path:
    caminho = os.environ.get("PLAT_ANEEL_CONTINUIDADE_RAIZ", "").strip()
    if not caminho or not Path(caminho).is_dir():
        pytest.skip("sem PLAT_ANEEL_CONTINUIDADE_RAIZ: o dado aberto de continuidade da ANEEL não está "
                    "nesta máquina")
    return Path(caminho)


def _parquet_apurado(raiz: Path) -> Path:
    arquivos = sorted(raiz.glob(continuidade.PADRAO_APURADO))
    if not arquivos:
        pytest.skip(f"nenhum arquivo {continuidade.PADRAO_APURADO} em {raiz}")
    return arquivos[0]


def _carga_maquina() -> dict:
    livre = None
    try:
        with open("/proc/meminfo") as f:
            for linha in f:
                if linha.startswith("MemAvailable"):
                    livre = round(int(linha.split()[1]) / 1024 / 1024, 2)
    except OSError:
        pass
    return {"carga_1min": round(os.getloadavg()[0], 2), "ram_livre_gb": livre,
            "medido_em": time.strftime("%Y-%m-%dT%H:%M:%S")}


# o comando que reproduz TODAS as medidas deste arquivo (vai dentro de cada bloco, como nos vizinhos)
COMANDO_MEDIDA = (
    "PLAT_ANEEL_CONTINUIDADE_RAIZ=<pasta do dado aberto da ANEEL> "
    "PLAT_REDE_REFERENCIA_ESQUEMA=<schema da cooperativa> PLAT_GRAVAR_MEDIDAS=1 "
    "bash laco/roda_teste.sh tests/api/test_rede_continuidade.py"
)


def _gravar_medida(chave: str, valor) -> None:
    """Grava um bloco de medida no formato dos vizinhos de tests/medidas/.

    ⛔ Só grava com PLAT_GRAVAR_MEDIDAS=1. Sem isso a suíte SUJAVA a árvore: rodar o teste reescrevia
    tests/medidas/L4-10-continuidade-dec-fec.json com carimbo de hora novo, e quem rodasse a suíte para
    conferir outra coisa encontrava o arquivo modificado. É a mesma regra da fixture `medida` de
    tests/conftest.py, e o formato daqui é o de lá: {item, gerado_em, git_sha, medidas: {nome: {valor,
    unidade, comando}}}.
    """
    if os.environ.get("PLAT_GRAVAR_MEDIDAS") != "1":
        return
    from app.versao import git_sha_curto

    MEDIDAS.parent.mkdir(parents=True, exist_ok=True)
    dados = json.loads(MEDIDAS.read_text()) if MEDIDAS.exists() else {}
    dados.setdefault("item", "L4-10-continuidade-dec-fec")
    dados["gerado_em"] = datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    dados["git_sha"] = git_sha_curto()
    dados["maquina"] = (
        "12 vCPU, 23 GB RAM; PostgreSQL 16 em iagro_sat; base própria da trilha "
        "(laco/trilha_ambiente.sh), com outras sessões da casa na mesma máquina. Dado aberto da ANEEL "
        "lido do disco local (PLAT_ANEEL_CONTINUIDADE_RAIZ); nada é baixado da agência (D21, disco)."
    )
    dados.setdefault("medidas", {})[chave] = {
        "valor": valor,
        "unidade": "contagens do bloco, com a carga da máquina no momento da medição",
        "comando": COMANDO_MEDIDA,
    }
    # o formato flat da primeira escrita (08/09) não tinha `medidas`: some com as chaves soltas
    for antiga in [k for k in dados if k not in ("item", "gerado_em", "git_sha", "medidas", "maquina")]:
        dados.pop(antiga)
    MEDIDAS.write_text(json.dumps(dados, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def _conjuntos_do_arquivo(caminho: Path, quantos: int) -> list[int]:
    """Alguns conjuntos que o arquivo realmente tem, lidos do primeiro grupo de linhas (barato)."""
    import pyarrow.parquet as pq

    arq = pq.ParquetFile(str(caminho))
    coluna = arq.read_row_group(0, columns=[continuidade.COL_CONJ])[continuidade.COL_CONJ].to_pylist()
    vistos: list[int] = []
    for c in coluna:
        if c is not None and int(c) not in vistos:
            vistos.append(int(c))
        if len(vistos) >= quantos:
            break
    if len(vistos) < quantos:
        pytest.skip("o arquivo de continuidade não traz conjuntos suficientes para a conferência")
    return vistos


def _recontar_do_parquet(caminho: Path, conjuntos: list[int]) -> dict:
    """Recontagem INDEPENDENTE: soma DEC e FEC por conjunto e ano lendo o parquet em Python puro, sem
    passar pelo produto. É contra ISTO que a ficha é conferida."""
    import pyarrow.parquet as pq

    tabela = pq.read_table(str(caminho), filters=[(continuidade.COL_CONJ, "in", conjuntos)])
    fora: dict = defaultdict(float)
    colunas = tabela.to_pydict()
    for conj, ind, ano, valor in zip(colunas[continuidade.COL_CONJ], colunas[continuidade.COL_INDICADOR],
                                     colunas[continuidade.COL_ANO], colunas[continuidade.COL_VALOR],
                                     strict=True):
        if ind in continuidade.INDICADORES and ANO_DE <= int(ano) <= ANO_ATE and valor is not None:
            fora[(int(conj), ind, int(ano))] += float(valor)
    return dict(fora)


# --------------------------------------------------------------------------- montagem da rede


class RedeDeTeste:
    """Uma `plat.rede` com o pacote `eletrica-br` e os elementos que o teste declarar.

    Não é mock: são as MESMAS tabelas que o importador BDGD preenche, com os mesmos campos de origem
    preservados em `atributos` (CONJ, CTMT, UNI_TR_MT, DIC/FIC). O que muda é a porta de entrada."""

    def __init__(self, cur, tenant_id: int, usuario_id: int, nome: str):
        import hashlib

        self.cur = cur
        self.tenant_id = tenant_id
        cur.execute(
            "INSERT INTO plat.rede (tenant_id, nome, disciplina, tolerancia_m, dono_id) "
            "VALUES (%s, %s, 'eletrica', 0.05, %s) RETURNING id",
            (tenant_id, nome, usuario_id),
        )
        self.rede_id = str(cur.fetchone()["id"])
        bruto = instalados.bruto("eletrica-br")
        deposito.importar(cur, tenant_id, self.rede_id, pacote_mod.ler(bruto), usuario_id,
                          hashlib.sha256(bruto).hexdigest(), len(bruto))
        self.tipos = {}
        for grupo in (continuidade.GRUPO_TRAFO, continuidade.GRUPO_UC):
            cur.execute(
                "SELECT t.id FROM plat.rede_tipo t JOIN plat.rede_grupo g ON g.id = t.grupo_id "
                "WHERE t.rede_id = %s::uuid AND g.codigo = %s ORDER BY t.codigo LIMIT 1",
                (self.rede_id, grupo),
            )
            self.tipos[grupo] = cur.fetchone()["id"]

    def trafo(self, codigo: str, conjunto: int, alimentador: str = "AL1") -> None:
        self.cur.execute(
            "INSERT INTO plat.rede_no (tenant_id, rede_id, papel, tipo_id, codigo_externo, geom, atributos) "
            "VALUES (%s, %s::uuid, 'dispositivo', %s::uuid, %s, "
            "        ST_SetSRID(ST_MakePoint(-51.0, -29.5), 4326), %s::jsonb)",
            (self.tenant_id, self.rede_id, self.tipos[continuidade.GRUPO_TRAFO], codigo,
             json.dumps({"COD_ID": codigo, "CONJ": str(conjunto), "CTMT": alimentador})),
        )

    def uc(self, codigo: str, conjunto: int, trafo: str, alimentador: str = "AL1",
           dic: float | None = None, fic: float | None = None) -> None:
        atributos = {"COD_ID": codigo, "CONJ": str(conjunto), "CTMT": alimentador,
                     "UNI_TR_MT": trafo}
        if dic is not None:
            atributos.update({f"DIC_{m:02d}": str(dic / 12) for m in range(1, 13)})
        if fic is not None:
            atributos.update({f"FIC_{m:02d}": str(fic / 12) for m in range(1, 13)})
        self.cur.execute(
            "INSERT INTO plat.rede_no (tenant_id, rede_id, papel, tipo_id, codigo_externo, atributos) "
            "VALUES (%s, %s::uuid, 'consumidor', %s::uuid, %s, %s::jsonb)",
            (self.tenant_id, self.rede_id, self.tipos[continuidade.GRUPO_UC], codigo,
             json.dumps(atributos)),
        )


@pytest.fixture
def inquilino(conexao_plat_app):
    con = conexao_plat_app
    tenant_id = ids_por_slug(con)["demo"]
    with con.cursor() as cur:
        contexto(con, tenant_id)
        cur.execute("SELECT id FROM plat.usuario WHERE tenant_id = %s AND ativo ORDER BY id LIMIT 1",
                    (tenant_id,))
        usuario_id = cur.fetchone()["id"]
        contexto(con, tenant_id, usuario_id)
        yield con, cur, tenant_id, usuario_id


@pytest.fixture
def rede_com_tres_conjuntos_reais(inquilino):
    """Uma rede que declara TRÊS conjuntos que o arquivo da ANEEL realmente tem, mais um conjunto que ele
    não tem — a semente da refutação. Dois alimentadores, para que a agregação por alimentador seja
    exercitada com pesos diferentes."""
    con, cur, tenant_id, usuario_id = inquilino
    raiz = _raiz()
    reais = _conjuntos_do_arquivo(_parquet_apurado(raiz), 3)
    marca = os.urandom(3).hex()
    rede = RedeDeTeste(cur, tenant_id, usuario_id, f"zt-l410-{marca}")
    # alimentador AL1: os dois primeiros conjuntos, com pesos 6 e 2
    for i in range(6):
        rede.uc(f"U-A{i}", reais[0], "T-1", "AL1", dic=10.0 + i, fic=5.0)
    for i in range(2):
        rede.uc(f"U-B{i}", reais[1], "T-1", "AL1", dic=20.0, fic=8.0)
    # alimentador AL2: o terceiro conjunto e o conjunto que a ANEEL não tem
    for i in range(4):
        rede.uc(f"U-C{i}", reais[2], "T-2", "AL2", dic=30.0, fic=12.0)
    for i in range(3):
        rede.uc(f"U-D{i}", CONJUNTO_FANTASMA, "T-2", "AL2")  # sem DIC/FIC de propósito
    rede.trafo("T-1", reais[0], "AL1")
    rede.trafo("T-2", reais[2], "AL2")
    yield con, cur, tenant_id, rede, reais, raiz


# --------------------------------------------------------------------------- cláusula 1: contagem


def test_importa_com_a_contagem_conferida_contra_o_arquivo(rede_com_tres_conjuntos_reais):
    con, cur, tenant_id, rede, reais, raiz = rede_com_tres_conjuntos_reais
    conjuntos = continuidade.conjuntos_da_rede(cur, rede.rede_id)
    assert set(conjuntos) == set(reais) | {CONJUNTO_FANTASMA}

    resultado = continuidade.importar(cur, tenant_id, raiz, conjuntos, ANO_DE, ANO_ATE)
    assert resultado["arquivos"], "nenhum arquivo de continuidade foi lido"
    for arquivo in resultado["arquivos"]:
        assert arquivo["linhas_arquivo"] == arquivo["linhas_gravadas"], arquivo
    assert resultado["conferido"] is True
    assert resultado["linhas_gravadas"] > 0

    # a conferência também fica gravada, não só no resultado do job
    cur.execute("SELECT arquivo, especie, linhas_arquivo, linhas_gravadas, sha256 "
                "FROM plat.rede_continuidade_fonte ORDER BY arquivo")
    fontes = [dict(r) for r in cur.fetchall()]
    assert fontes and all(f["linhas_arquivo"] == f["linhas_gravadas"] for f in fontes)
    assert all(len(f["sha256"]) == 64 for f in fontes)

    cur.execute("SELECT count(*) AS n FROM plat.rede_continuidade WHERE origem = 'apurado'")
    gravadas = cur.fetchone()["n"]
    assert gravadas > 0
    _gravar_medida("importacao", {
        "arquivos": [{k: a[k] for k in ("arquivo", "especie", "linhas_arquivo", "linhas_gravadas")}
                     for a in resultado["arquivos"]],
        "conjuntos_pedidos": len(conjuntos),
        "linhas_apuradas_gravadas": gravadas,
        "duracao_ms": resultado["duracao_ms"],
        **_carga_maquina(),
    })
    con.rollback()


def test_job_usa_o_mesmo_caminho_da_rota():
    """O job existe, está registrado e recusa caminho fora da raiz configurada."""
    from app.jobs.registro import REGISTRO
    from app.rede_utilidades import tarefas_continuidade

    tipo = REGISTRO["rede.importar_continuidade"]
    assert tipo.perfil_minimo == "editor"
    _raiz()
    with pytest.raises(Exception, match="fora de PLAT_ANEEL_CONTINUIDADE_RAIZ"):
        tarefas_continuidade.resolver_caminho("/etc")


# --------------------------------------------------------------------------- cláusulas 3, 5 e 7


def test_situacao_usa_o_limite_do_ano_e_diz_de_que_arquivo_veio(rede_com_tres_conjuntos_reais):
    con, cur, tenant_id, rede, reais, raiz = rede_com_tres_conjuntos_reais
    continuidade.importar(cur, tenant_id, raiz, continuidade.conjuntos_da_rede(cur, rede.rede_id),
                          ANO_DE, ANO_ATE)
    fichas = continuidade.ficha_conjuntos(cur, rede.rede_id, ANO_DE, ANO_ATE)
    assert fichas

    com_limite = 0
    for f in fichas:
        for ind, d in f["indicadores"].items():
            assert d["situacao"] in (continuidade.DENTRO, continuidade.ACIMA,
                                     continuidade.SEM_LIMITE, continuidade.SEM_DADO)
            if d["apurado"] is not None and d["limite"] is not None:
                com_limite += 1
                esperado = (continuidade.ACIMA if d["apurado"] > d["limite"] else continuidade.DENTRO)
                assert d["situacao"] == esperado, (f["conjunto_id"], f["ano"], ind, d)
                # a fonte do limite é nomeada: nenhum limite é escrito no código
                assert d["limite_arquivo"], "limite sem o arquivo de onde veio"
    assert com_limite > 0, "nenhum ano teve apurado e limite ao mesmo tempo"
    _gravar_medida("comparacao_com_limite", {"anos_conjunto_indicador_com_limite": com_limite,
                                             **_carga_maquina()})
    con.rollback()


def test_painel_traz_a_serie_de_2020_a_2025(rede_com_tres_conjuntos_reais):
    con, cur, tenant_id, rede, reais, raiz = rede_com_tres_conjuntos_reais
    continuidade.importar(cur, tenant_id, raiz, continuidade.conjuntos_da_rede(cur, rede.rede_id),
                          ANO_DE, ANO_ATE)
    painel = continuidade.painel(cur, rede.rede_id, ANO_DE, ANO_ATE)
    assert painel["anos"] == [2020, 2021, 2022, 2023, 2024, 2025]
    assert painel["total"] == 4  # os três reais e o fantasma
    assert "956/2021" in painel["limite_base_normativa"]
    for item in painel["itens"]:
        for ind in continuidade.INDICADORES:
            serie = item["series"][ind]
            assert len(serie["apurado"]) == 6
            assert len(serie["limite"]) == 6
            assert len(serie["situacao"]) == 6
    _gravar_medida("painel", {"anos": painel["anos"], "conjuntos": painel["total"],
                              **_carga_maquina()})
    con.rollback()


def test_refutacao_tres_conjuntos_contra_o_arquivo_da_aneel(rede_com_tres_conjuntos_reais):
    """A refutação exigida: três conjuntos recontados direto do parquet, em Python puro, sem passar pelo
    produto. Cada ano de cada indicador tem de bater com a ficha, na quarta casa decimal."""
    con, cur, tenant_id, rede, reais, raiz = rede_com_tres_conjuntos_reais
    continuidade.importar(cur, tenant_id, raiz, continuidade.conjuntos_da_rede(cur, rede.rede_id),
                          ANO_DE, ANO_ATE)
    independente = _recontar_do_parquet(_parquet_apurado(raiz), reais)
    fichas = {(f["conjunto_id"], f["ano"]): f for f in
              continuidade.ficha_conjuntos(cur, rede.rede_id, ANO_DE, ANO_ATE)}

    conferidos = 0
    for conj in reais:
        for ano in range(ANO_DE, ANO_ATE + 1):
            for ind in continuidade.INDICADORES:
                esperado = independente.get((conj, ind, ano))
                obtido = fichas[(conj, ano)]["indicadores"][ind]["apurado"]
                if esperado is None:
                    assert obtido is None, (conj, ano, ind, obtido)
                    continue
                assert obtido is not None, (conj, ano, ind)
                assert abs(obtido - round(esperado, 4)) < 1e-4, (conj, ano, ind, obtido, esperado)
                conferidos += 1
    assert conferidos > 0
    _gravar_medida("refutacao_recontagem_independente", {
        "conjuntos": reais, "anos": [ANO_DE, ANO_ATE], "valores_conferidos": conferidos,
        **_carga_maquina()})
    con.rollback()


def test_refutacao_conjunto_sem_par_no_arquivo_sai_como_sem_dado(rede_com_tres_conjuntos_reais):
    """A outra metade da refutação: um conjunto que a rede declara e a ANEEL não publica tem de aparecer
    na ficha como 'sem dado', com valor NULO — nunca zero, que seria continuidade perfeita."""
    con, cur, tenant_id, rede, reais, raiz = rede_com_tres_conjuntos_reais
    continuidade.importar(cur, tenant_id, raiz, continuidade.conjuntos_da_rede(cur, rede.rede_id),
                          ANO_DE, ANO_ATE)
    fichas = [f for f in continuidade.ficha_conjuntos(cur, rede.rede_id, ANO_DE, ANO_ATE)
              if f["conjunto_id"] == CONJUNTO_FANTASMA]
    assert len(fichas) == ANO_ATE - ANO_DE + 1, "o conjunto sem dado sumiu da ficha em vez de aparecer"
    for f in fichas:
        for ind, d in f["indicadores"].items():
            assert d["apurado"] is None, (f["ano"], ind, d)
            assert d["apurado"] != 0
            assert d["situacao"] == continuidade.SEM_DADO
    # e no alimentador dele, as unidades entram como "sem dado", não como zero na média
    alimentadores = {a["alimentador"]: a for a in
                     continuidade.ficha_alimentadores(cur, rede.rede_id, ANO_ATE)}
    assert alimentadores["AL2"]["indicadores"]["DEC"]["uc_sem_dado"] == 3
    _gravar_medida("refutacao_sem_dado", {
        "conjunto_fantasma": CONJUNTO_FANTASMA,
        "anos_sem_dado": len(fichas),
        "uc_sem_dado_no_alimentador": alimentadores["AL2"]["indicadores"]["DEC"]["uc_sem_dado"],
        **_carga_maquina()})
    con.rollback()


def test_alimentador_pondera_pelas_unidades_consumidoras(rede_com_tres_conjuntos_reais):
    """AL1 tem 6 UCs de um conjunto e 2 de outro: a média ponderada tem de ser exatamente a conta de
    (6·A + 2·B)/8 quando os dois conjuntos têm apurado."""
    con, cur, tenant_id, rede, reais, raiz = rede_com_tres_conjuntos_reais
    continuidade.importar(cur, tenant_id, raiz, continuidade.conjuntos_da_rede(cur, rede.rede_id),
                          ANO_DE, ANO_ATE)
    fichas = {(f["conjunto_id"], f["ano"]): f for f in
              continuidade.ficha_conjuntos(cur, rede.rede_id, ANO_DE, ANO_ATE)}
    al = {a["alimentador"]: a for a in continuidade.ficha_alimentadores(cur, rede.rede_id, ANO_ATE)}
    assert set(al) == {"AL1", "AL2"}
    assert al["AL1"]["n_uc"] == 8

    a = fichas[(reais[0], ANO_ATE)]["indicadores"]["DEC"]["apurado"]
    b = fichas[(reais[1], ANO_ATE)]["indicadores"]["DEC"]["apurado"]
    obtido = al["AL1"]["indicadores"]["DEC"]["apurado_ponderado"]
    if a is None and b is None:
        assert obtido is None
    elif a is not None and b is not None:
        assert abs(obtido - round((6 * a + 2 * b) / 8, 4)) < 1e-3
        assert al["AL1"]["indicadores"]["DEC"]["uc_com_dado"] == 8
    else:
        # só um dos dois tem apurado: a média é dele, e o outro conta como sem dado
        presente = a if a is not None else b
        peso_sem = 2 if a is not None else 6
        assert abs(obtido - round(presente, 4)) < 1e-3
        assert al["AL1"]["indicadores"]["DEC"]["uc_sem_dado"] == peso_sem
    con.rollback()


# --------------------------------------------------------------------------- cláusula 4: DIC/FIC


def test_dic_fic_medio_por_trafo(rede_com_tres_conjuntos_reais):
    """DIC e FIC vêm da própria BDGD, por unidade consumidora, e são resumidos por transformador.
    T-1 tem 8 UCs com DIC (6 com 10..15 e 2 com 20); T-2 tem 4 com DIC 30 e 3 SEM DIC nenhum."""
    con, cur, tenant_id, rede, reais, raiz = rede_com_tres_conjuntos_reais
    por_trafo = {t["trafo"]: t for t in continuidade.dic_fic_por_trafo(cur, rede.rede_id)}
    assert set(por_trafo) == {"T-1", "T-2"}

    esperado_t1 = (sum(10.0 + i for i in range(6)) + 2 * 20.0) / 8
    assert abs(por_trafo["T-1"]["dic_medio"] - esperado_t1) < 1e-6
    assert por_trafo["T-1"]["n_uc"] == 8 and por_trafo["T-1"]["n_uc_com_dic"] == 8

    # as três unidades sem DIC não entram na média, e a diferença entre n_uc e n_uc_com_dic diz isso
    assert por_trafo["T-2"]["n_uc"] == 7 and por_trafo["T-2"]["n_uc_com_dic"] == 4
    assert abs(por_trafo["T-2"]["dic_medio"] - 30.0) < 1e-6
    assert abs(por_trafo["T-2"]["fic_medio"] - 12.0) < 1e-6
    _gravar_medida("dic_fic_por_trafo", {
        "trafos": len(por_trafo),
        "T-1": {k: por_trafo["T-1"][k] for k in ("n_uc", "n_uc_com_dic", "dic_medio", "fic_medio")},
        "T-2": {k: por_trafo["T-2"][k] for k in ("n_uc", "n_uc_com_dic", "dic_medio", "fic_medio")},
        **_carga_maquina()})
    con.rollback()


# --------------------------------------------------------------------------- cláusula 6: vocabulário


def test_nenhuma_resposta_usa_a_palavra_proibida(rede_com_tres_conjuntos_reais):
    con, cur, tenant_id, rede, reais, raiz = rede_com_tres_conjuntos_reais
    continuidade.importar(cur, tenant_id, raiz, continuidade.conjuntos_da_rede(cur, rede.rede_id),
                          ANO_DE, ANO_ATE)
    corpos = [
        continuidade.ficha_conjuntos(cur, rede.rede_id, ANO_DE, ANO_ATE),
        continuidade.ficha_alimentadores(cur, rede.rede_id, ANO_ATE),
        continuidade.dic_fic_por_trafo(cur, rede.rede_id),
        continuidade.painel(cur, rede.rede_id, ANO_DE, ANO_ATE),
    ]
    texto = json.dumps(corpos, ensure_ascii=False, default=str).lower()
    assert "transgress" not in texto
    assert "infra" + "ção" not in texto and "infrator" not in texto

    # --- o PAR POSITIVO. Sem ele este teste só provaria que a palavra proibida não aparece, o que um
    # módulo que não dissesse NADA também cumpriria. O par: forçar um limite ABAIXO do apurado (dentro
    # desta transação, que termina em rollback) e exigir que a comparação diga a frase autorizada, com o
    # número e o limite do lado. No dado real destes conjuntos a situação é 'dentro do limite' — é por isso
    # que o caso de excesso precisa ser construído, e não esperado do arquivo.
    alvo = None
    for f in continuidade.ficha_conjuntos(cur, rede.rede_id, ANO_DE, ANO_ATE):
        d = f["indicadores"]["DEC"]
        if d["apurado"] is not None and d["apurado"] > 0:
            alvo = (f["conjunto_id"], f["ano"], d["apurado"])
            break
    assert alvo is not None, "nenhum conjunto real trouxe DEC apurado: o par positivo não pôde ser montado"
    conjunto_id, ano, apurado = alvo
    cur.execute(
        "UPDATE plat.rede_continuidade_limite SET valor = %(v)s "
        " WHERE conjunto_id = %(c)s AND indicador = 'DEC' AND ano = %(a)s",
        {"v": apurado / 2.0, "c": conjunto_id, "a": ano})
    assert cur.rowcount == 1, "o limite do ano do alvo não estava na base para ser rebaixado"

    fichas = {(f["conjunto_id"], f["ano"]): f for f in
              continuidade.ficha_conjuntos(cur, rede.rede_id, ANO_DE, ANO_ATE)}
    acima = fichas[(conjunto_id, ano)]["indicadores"]["DEC"]
    assert acima["situacao"] == continuidade.ACIMA == "acima do limite regulatório"
    assert acima["apurado"] == apurado and acima["limite"] == apurado / 2.0
    assert acima["limite_arquivo"], "o excesso apareceu sem dizer de que arquivo veio o limite"
    # e a frase autorizada não abre a porta para a proibida em nenhuma das quatro leituras
    depois = json.dumps([
        continuidade.ficha_conjuntos(cur, rede.rede_id, ANO_DE, ANO_ATE),
        continuidade.ficha_alimentadores(cur, rede.rede_id, ano),
        continuidade.painel(cur, rede.rede_id, ANO_DE, ANO_ATE),
    ], ensure_ascii=False, default=str)
    assert continuidade.ACIMA in depois, "o excesso existe na base e nenhuma leitura o mostra"
    assert "transgress" not in depois.lower()
    con.rollback()


# --------------------------------------------------------------------------- cláusula 2: dado real


@pytest.mark.lento
def test_ficha_do_conjunto_e_do_alimentador_na_cooperativa_de_teste(inquilino):
    """Cláusula 2 em dado REAL: as unidades consumidoras e os transformadores da cooperativa de teste,
    com o CONJ e o CTMT que o arquivo declara, a continuidade importada do dado aberto da ANEEL para
    esse conjunto, e a ficha do conjunto e a do alimentador saindo com número."""
    from tests.dados.carga_bdgd import esquema
    from tests.dados.carga_bdgd_continuidade import carregar_uc_e_trafo

    if not esquema():
        pytest.skip("sem PLAT_REDE_REFERENCIA_ESQUEMA: o arquivo BDGD da cooperativa de teste não está "
                    "nesta máquina")
    raiz = _raiz()
    con, cur, tenant_id, usuario_id = inquilino
    marca = os.urandom(3).hex()
    rede = RedeDeTeste(cur, tenant_id, usuario_id, f"zt-l410-real-{marca}")
    t0 = time.perf_counter()
    cron = carregar_uc_e_trafo(cur, tenant_id, rede.rede_id)
    conjuntos = continuidade.conjuntos_da_rede(cur, rede.rede_id)
    assert conjuntos, "o arquivo da cooperativa de teste não traz o campo CONJ"

    resultado = continuidade.importar(cur, tenant_id, raiz, conjuntos, ANO_DE, ANO_ATE)
    assert resultado["conferido"] is True

    fichas = continuidade.ficha_conjuntos(cur, rede.rede_id, ANO_DE, ANO_ATE)
    com_numero = [f for f in fichas if f["indicadores"]["DEC"]["apurado"] is not None]
    assert com_numero, "nenhum conjunto da cooperativa de teste tem DEC apurado publicado"

    alimentadores = continuidade.ficha_alimentadores(cur, rede.rede_id, ANO_ATE)
    assert alimentadores, "nenhum alimentador saiu da junção por unidade consumidora"
    com_dec = [a for a in alimentadores if a["indicadores"]["DEC"]["apurado_ponderado"] is not None]
    assert com_dec, "nenhum alimentador recebeu o DEC do conjunto"

    trafos = continuidade.dic_fic_por_trafo(cur, rede.rede_id, limite=20000)
    com_dic = [t for t in trafos if t["dic_medio"] is not None]

    _gravar_medida("cooperativa_de_teste", {
        "camadas_carregadas": cron,
        "conjuntos_declarados": len(conjuntos),
        "conjuntos_com_dec_apurado": len(com_numero),
        "alimentadores": len(alimentadores),
        "alimentadores_com_dec": len(com_dec),
        "trafos_com_uc": len(trafos),
        "trafos_com_dic_medio": len(com_dic),
        "dec_por_ano": {str(f["ano"]): f["indicadores"]["DEC"]["apurado"] for f in fichas
                        if f["conjunto_id"] == conjuntos[0]},
        "limite_por_ano": {str(f["ano"]): f["indicadores"]["DEC"]["limite"] for f in fichas
                           if f["conjunto_id"] == conjuntos[0]},
        "situacao_por_ano": {str(f["ano"]): f["indicadores"]["DEC"]["situacao"] for f in fichas
                             if f["conjunto_id"] == conjuntos[0]},
        "duracao_total_s": round(time.perf_counter() - t0, 2),
        **_carga_maquina()})
    con.rollback()
