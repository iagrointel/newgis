"""Regressão do CONSERTO do item L4-01-a-pacote-de-ativos (turno 3, 06/09/2026).

Origem: adversário independente em `wt/advl4` (commit 2dacdeb, contra o sha 838cbd8), 6 `xfail(strict=True)`
achados A1-A4 (`handoffs/T3/ataque-L4-portal-ADVERSARIO.md` § 1) e 6 ataques que já resistiam. Este arquivo é
a MESMA bateria trazida para o item, com os achados corrigidos virando teste normal (nunca se afrouxa uma
asserção para fazer passar — cada `# CONSERTADO` acima de um teste aponta o commit/arquivo do conserto).
Prova completa em `handoffs/T3/L4-01-a-CONSERTO.md`."""

import copy
import json
import os
import re
import socket
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path

import httpx
import psycopg2
import psycopg2.errors
import pytest

from app.rede_utilidades import instalados
from app.rede_utilidades import pacote as pacote_mod
from app.schema_ambiente import CursorSchemaAmbiente
from tests.api.conftest import PREFIXO_TESTE, credenciais
from tests.api.test_rls import contexto, ids_por_slug

ITEM = "L4-01-a-pacote-de-ativos"
TABELAS = ("rede", "rede_dominio", "rede_tier", "rede_categoria", "rede_terminal_config", "rede_grupo",
           "rede_tipo", "rede_tipo_categoria", "rede_atributo", "rede_regra")
FILHAS = TABELAS[1:]
ROOT = Path(__file__).resolve().parents[2]


# ----------------------------------------------------------------------------------------- apoio

@pytest.fixture
def limpar_redes(sessao_a, sessao_b):
    criadas = []
    yield criadas
    for sessao, rid in criadas:
        sessao.delete(f"/api/rede/{rid}")


def _criar(sessao, sufixo, disciplina="agua"):
    r = sessao.post("/api/rede", json={"nome": f"{PREFIXO_TESTE}-adv-{sufixo}-{uuid.uuid4().hex[:6]}",
                                        "disciplina": disciplina})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _importar(sessao, rid, bruto: bytes):
    return sessao.post(f"/api/rede/{rid}/pacote", content=bruto, headers={"Content-Type": "application/json"})


def _rede_com_pacote(sessao, limpar, sufixo, codigo="agua-epanet"):
    rid = _criar(sessao, sufixo, "agua" if codigo == "agua-epanet" else "eletrica")
    limpar.append((sessao, rid))
    assert _importar(sessao, rid, instalados.bruto(codigo)).status_code == 201
    return rid


def _doc(codigo="agua-epanet") -> dict:
    return pacote_mod.ler(instalados.bruto(codigo))


def _bytes(doc: dict) -> bytes:
    return (json.dumps(doc, ensure_ascii=False, indent=1) + "\n").encode("utf-8")


def _conexao(env):
    return psycopg2.connect(env["PLAT_DSN"], cursor_factory=CursorSchemaAmbiente)


def _admins(con) -> dict:
    """{slug: (tenant_id, usuario_id)} dos admins semeados — a política de INSERT exige usuário do inquilino,
    então o contexto precisa de um usuario_id real, não 0."""
    saida = {}
    with con.cursor() as cur:
        for slug in ("demo", "demo2"):
            cur.execute("SELECT tenant_id, usuario_id FROM plat.auth_login(%s, 'admin')", (slug,))
            r = cur.fetchone()
            saida[slug] = (r["tenant_id"], r["usuario_id"])
    return saida


# ----------------------------------------------------------------------------------------- cruzado A→B

def test_cruzado_a_b_nas_dez_tabelas_por_api_e_por_plat_app(sessao_a, sessao_b, limpar_redes, env):
    """Leitura e escrita cruzada nas 10 tabelas: pela API (4 rotas) e como `plat_app` no contexto de B
    (SELECT, UPDATE, DELETE e INSERT com o tenant_id de A). Tudo tem de dar zero ou recusa."""
    rid_a = _rede_com_pacote(sessao_a, limpar_redes, "cruz")
    assert sessao_b.get(f"/api/rede/{rid_a}").status_code == 404
    assert sessao_b.get(f"/api/rede/{rid_a}/pacote").status_code == 404
    assert _importar(sessao_b, rid_a, instalados.bruto("eletrica-br")).status_code == 404
    assert sessao_b.delete(f"/api/rede/{rid_a}").status_code == 404

    con = _conexao(env)
    try:
        ids = ids_por_slug(con)
        adm = _admins(con)
        contexto(con, *adm["demo2"], login="admin")
        with con.cursor() as cur:
            for t in TABELAS:
                col = "id" if t == "rede" else "rede_id"
                cur.execute(f"SELECT count(*) AS n FROM plat.{t} WHERE {col} = %s::uuid", (rid_a,))  # noqa: S608
                assert cur.fetchone()["n"] == 0, f"{t}: B lê linha de A"
                if t == "rede":
                    cur.execute("UPDATE plat.rede SET descricao = 'x' WHERE id = %s::uuid", (rid_a,))
                else:
                    cur.execute(f"UPDATE plat.{t} SET tenant_id = tenant_id WHERE rede_id = %s::uuid",  # noqa: S608
                                (rid_a,))
                assert cur.rowcount == 0, f"{t}: B altera linha de A"
                cur.execute(f"DELETE FROM plat.{t} WHERE {col} = %s::uuid", (rid_a,))  # noqa: S608
                assert cur.rowcount == 0, f"{t}: B apaga linha de A"
            # INSERT carimbado com o tenant de A, a partir do contexto de B
            with pytest.raises(psycopg2.errors.InsufficientPrivilege):
                cur.execute(
                    "INSERT INTO plat.rede_dominio(tenant_id, rede_id, codigo, nome, tipo, disciplina, ordem) "
                    "VALUES (%s, %s::uuid, 'zadv', 'z', 'dominio', 'agua', 1)", (ids["demo"], rid_a),
                )
    finally:
        con.rollback()
        con.close()
    # e a rede de A continua inteira
    assert sessao_a.get(f"/api/rede/{rid_a}/pacote").content == instalados.bruto("agua-epanet")


# CONSERTADO (turno 3): migração 20260906T1815_rede_fk_por_inquilino.sql — toda FK das 10 tabelas da rede
# virou composta (tenant_id, id); a trava fica em tests/api/test_fk_composta_por_inquilino.py.
def test_fk_de_b_nao_alcanca_linha_de_a_como_plat_app(sessao_a, sessao_b, limpar_redes, env):
    rid_a = _rede_com_pacote(sessao_a, limpar_redes, "fk-a")
    rid_b = _rede_com_pacote(sessao_b, limpar_redes, "fk-b")
    con = _conexao(env)
    try:
        ids = ids_por_slug(con)
        adm = _admins(con)
        contexto(con, *adm["demo"], login="admin")
        with con.cursor() as cur:
            cur.execute("SELECT id FROM plat.rede_tipo WHERE rede_id = %s::uuid LIMIT 1", (rid_a,))
            tipo_a = cur.fetchone()["id"]
            cur.execute("SELECT id FROM plat.rede_dominio WHERE rede_id = %s::uuid LIMIT 1", (rid_a,))
            dominio_a = cur.fetchone()["id"]
        con.rollback()
        contexto(con, *adm["demo2"], login="admin")
        with con.cursor() as cur:
            cur.execute("SELECT id FROM plat.rede_categoria WHERE rede_id = %s::uuid LIMIT 1", (rid_b,))
            categoria_b = cur.fetchone()["id"]
            # uuid inventado: a FK recusa (comportamento esperado)
            with pytest.raises(psycopg2.errors.ForeignKeyViolation):
                cur.execute(
                    "INSERT INTO plat.rede_tipo_categoria(tenant_id, rede_id, tipo_id, categoria_id) "
                    "VALUES (%s, %s::uuid, %s::uuid, %s)", (ids["demo2"], rid_b, str(uuid.uuid4()), categoria_b),
                )
        con.rollback()
        contexto(con, *adm["demo2"], login="admin")
        with con.cursor() as cur:
            # uuid de A: a FK TINHA de recusar igual — se aceita, B provou que o id existe em A
            with pytest.raises(psycopg2.errors.ForeignKeyViolation):
                cur.execute(
                    "INSERT INTO plat.rede_tipo_categoria(tenant_id, rede_id, tipo_id, categoria_id) "
                    "VALUES (%s, %s::uuid, %s, %s)", (ids["demo2"], rid_b, tipo_a, categoria_b),
                )
        con.rollback()
        contexto(con, *adm["demo2"], login="admin")
        with con.cursor() as cur:
            with pytest.raises(psycopg2.errors.ForeignKeyViolation):
                cur.execute(
                    "INSERT INTO plat.rede_grupo(tenant_id, rede_id, dominio_id, codigo, nome, geometria) "
                    "VALUES (%s, %s::uuid, %s, 'zadv-grupo', 'z', 'ponto')", (ids["demo2"], rid_b, dominio_a),
                )
    finally:
        con.rollback()
        con.close()


# ----------------------------------------------------------------------------------------- seção repetida

def _texto_com_secao_repetida(doc: dict, secao: str, primeira: list, segunda: list) -> bytes:
    """Serializa o pacote com a chave `secao` DUAS vezes: `primeira` vem antes, `segunda` depois."""
    resto = {k: v for k, v in doc.items() if k != secao}
    partes = json.dumps(resto, ensure_ascii=False, indent=1)[:-2]  # tira "\n}"
    p1 = json.dumps(primeira, ensure_ascii=False, indent=1)
    p2 = json.dumps(segunda, ensure_ascii=False, indent=1)
    return (partes + f',\n "{secao}": ' + p1 + f',\n "{secao}": ' + p2 + "\n}\n").encode("utf-8")


# CONSERTADO (turno 3): app/rede_utilidades/localizador.chaves_repetidas + pacote._chave_repetida.
def test_secao_repetida_e_recusada(sessao_a, limpar_redes):
    rid = _criar(sessao_a, "secao-rep")
    limpar_redes.append((sessao_a, rid))
    doc = _doc()
    quebrada = copy.deepcopy(doc["tiers"])
    quebrada[0]["dominio"] = "dominio-que-so-existe-na-primeira-secao"
    bruto = _texto_com_secao_repetida(doc, "tiers", quebrada, doc["tiers"])
    assert bruto.count(b'"tiers":') == 2
    r = _importar(sessao_a, rid, bruto)
    assert r.status_code == 422, f"pacote com 'tiers' duas vezes entrou: {r.status_code} {r.text[:200]}"


# CONSERTADO (turno 3): localizador reconstrói um mapa de offsets (última ocorrência de cada chave
# sobrescreve, como json.loads) em vez de buscar do zero a cada chamada.
def test_linha_apontada_e_da_secao_que_foi_validada(sessao_a, limpar_redes):
    rid = _criar(sessao_a, "secao-linha")
    limpar_redes.append((sessao_a, rid))
    doc = _doc()
    quebrada = copy.deepcopy(doc["tiers"])
    quebrada[0]["dominio"] = "dominio-inventado-na-segunda"
    bruto = _texto_com_secao_repetida(doc, "tiers", doc["tiers"], quebrada)
    r = _importar(sessao_a, rid, bruto)
    assert r.status_code == 422, r.text[:200]
    problemas = [p for p in r.json()["detalhe"] if p["erro"] == "dominio_inexistente"]
    assert problemas, r.json()["detalhe"][:3]
    linha = bruto.decode("utf-8").splitlines()[problemas[0]["linha"] - 1]
    assert "dominio-inventado-na-segunda" in linha, f"linha apontada: {linha!r}"


# ----------------------------------------------------------------------------------------- 500 por dado válido

# CONSERTADO (turno 3): pacote._procurar_nul recusa com 422 antes de a string chegar ao psycopg2.
@pytest.mark.parametrize("onde", ["nome_texto", "codigos_fonte_jsonb"])
def test_nul_no_pacote_e_recusado_com_422(sessao_a, limpar_redes, onde):
    rid = _criar(sessao_a, f"nul-{onde}")
    limpar_redes.append((sessao_a, rid))
    doc = _doc()
    if onde == "nome_texto":
        doc["tipos"][0]["nome"] = "Bomba\u0000escondida"
    else:
        doc["tipos"][0]["codigos_fonte"] = ["A\u0000B"]
    try:
        r = _importar(sessao_a, rid, _bytes(doc))
        status = r.status_code
    except Exception as e:  # noqa: BLE001 — o TestClient relança a exceção do servidor: é o 500
        status = f"500 ({type(e).__name__}: {str(e)[:80]})"
    assert status == 422, f"esperava 422 pacote_invalido, veio {status}"
    assert sessao_a.get(f"/api/rede/{rid}/pacote").status_code == 404


# ----------------------------------------------------------------------------------------- semântica da ida e volta

def test_numero_3_0_e_codigo_01_entram_e_saem_normalizados(sessao_a, limpar_redes):
    """Não é achado, é fronteira medida: `ordem: 3.0` e `de: "grupo/01"` passam no esquema e voltam como `3` e
    `grupo/1`. A ida e volta é canônica, como o handoff admite; fica registrado que a normalização é silenciosa
    (o evento grava o sha256 do arquivo ENVIADO, que nunca mais bate com a exportação)."""
    rid = _criar(sessao_a, "norm")
    limpar_redes.append((sessao_a, rid))
    doc = _doc()
    doc["tiers"][0]["ordem"] = float(doc["tiers"][0]["ordem"])
    regra = doc["regras"][0]
    g, _, c = regra["de"].partition("/")
    regra["de"] = f"{g}/0{c}"
    bruto = _bytes(doc)
    r = _importar(sessao_a, rid, bruto)
    assert r.status_code == 201, r.text
    volta = json.loads(sessao_a.get(f"/api/rede/{rid}/pacote").content)
    assert isinstance(volta["tiers"][0]["ordem"], int)
    assert all(not re.search(r"/0\d", x["de"]) for x in volta["regras"])
    assert r.json()["sha256"] != sessao_a.get(f"/api/rede/{rid}/pacote").headers["ETag"].strip('"')


def test_codigo_de_pacote_igual_em_dois_inquilinos_e_em_duas_redes_nao_colide(sessao_a, sessao_b, limpar_redes):
    a1 = _rede_com_pacote(sessao_a, limpar_redes, "col-a1")
    a2 = _rede_com_pacote(sessao_a, limpar_redes, "col-a2")
    b1 = _rede_com_pacote(sessao_b, limpar_redes, "col-b1")
    for sessao, rid in ((sessao_a, a1), (sessao_a, a2), (sessao_b, b1)):
        assert sessao.get(f"/api/rede/{rid}/pacote").content == instalados.bruto("agua-epanet")


# ----------------------------------------------------------------------------------------- privilégio nas rotas

def test_toda_rota_de_escrita_de_rede_exige_rede_editar_no_openapi_e_na_pratica(sessao_a, usuarios_a, limpar_redes):
    from app.main import app

    esquema = app.openapi()
    escritas = [(c, m) for c, ops in esquema["paths"].items() if c.startswith("/api/rede")
                for m in ops if m in ("post", "put", "patch", "delete")]
    # 4 rotas do catálogo e da importação (POST /api/rede, DELETE /api/rede/{id}, POST .../pacote,
    # POST .../importar-bdgd), 5 da topologia derivada e da edição (POST .../feicoes/{pontos,linhas},
    # os dois applyEdits e .../topologia/habilitar), 1 de traçado, 2 de rede simples (POST
    # /api/rede/simples e .../promover) e 4 de controlador de subrede. O número cresce a cada item novo
    # da linha L4 que escreva rede — o que a asserção abaixo protege é que TODA rota nova venha com
    # x-privilegio=rede.editar, não a contagem exata.
    assert len(escritas) == 25, escritas
    # POST /api/rede/{rede_id}/tracar é CONSULTA com verbo de escrita: manda os pontos de partida no corpo
    # e não grava nada na rede, por isso pede leitura (rls:visibilidade) e não rede.editar. O mesmo vale
    # para exportar o resultado e repetir um traçado do histórico (item L4-02-f). Salvar o resultado como
    # camada é a única que foge das duas: não escreve na rede, escreve no CATÁLOGO, e por isso pede o
    # privilégio do catálogo (conteudo.criar) — dar-lhe rede.editar deixaria criar item de catálogo a quem
    # não pode criar item de catálogo.
    excecoes = {
        ("/api/rede/{rede_id}/tracar", "post"): "rls:visibilidade",
        ("/api/rede/{rede_id}/tracar/exportar", "post"): "rls:visibilidade",
        ("/api/rede/{rede_id}/tracados/{execucao_id}/repetir", "post"): "rls:visibilidade",
        ("/api/rede/{rede_id}/tracar/camada", "post"): "conteudo.criar",
    }
    for c, m in escritas:
        esperado = excecoes.get((c, m), "rede.editar")
        assert esquema["paths"][c][m].get("x-privilegio") == esperado, (c, m)
    rid = _rede_com_pacote(sessao_a, limpar_redes, "priv")
    visual, _, _ = usuarios_a.sessao("visualizador")
    assert visual.get(f"/api/rede/{rid}").status_code == 200
    assert visual.post("/api/rede", json={"nome": "zadv-x", "disciplina": "agua"}).status_code == 403
    assert _importar(visual, rid, instalados.bruto("agua-epanet")).status_code == 403
    assert visual.delete(f"/api/rede/{rid}").status_code == 403


# ------------------------------------------------------------------------------ servidor real (laço de eventos)

def _porta_livre() -> int:
    ocupadas = set()
    try:
        saida = subprocess.run(["ss", "-ltnH"], capture_output=True, text=True, timeout=5).stdout
        ocupadas = {int(li.split()[3].rsplit(":", 1)[1]) for li in saida.splitlines() if li.strip()}
    except Exception:  # noqa: BLE001
        pass
    for p in range(8190, 8250):
        if p in ocupadas:
            continue
        with socket.socket() as s:
            try:
                s.bind(("127.0.0.1", p))
                return p
            except OSError:
                continue
    raise RuntimeError("sem porta livre")


@pytest.fixture(scope="module")
def servidor_real(env):
    """uvicorn da própria trilha (nunca o plat-api de produção), morto pelo PID ao fim."""
    porta = _porta_livre()
    ambiente = dict(os.environ)
    ambiente.setdefault("PLAT_GIT_SHA", subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(ROOT), capture_output=True,
                                                       text=True, timeout=10).stdout.strip() or "0" * 40)
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(porta),
         "--log-level", "warning"],
        cwd=str(ROOT), env=ambiente, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    base = f"http://127.0.0.1:{porta}"
    try:
        for _ in range(240):
            try:
                # 503 = saúde degradada (worker/garage da trilha não sobem); o que importa é que responde
                if httpx.get(base + "/saude", timeout=2).status_code < 600:
                    break
            except httpx.HTTPError:
                pass
            time.sleep(0.5)
        else:
            raise RuntimeError("uvicorn da trilha não subiu")
        yield base
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()


def _sessao_http(base: str, slug: str = "demo") -> httpx.Client:
    login, senha = credenciais()[slug]
    c = httpx.Client(base_url=base, timeout=120)
    r = c.post("/api/login", json={"inquilino": slug, "login": login, "senha": senha})
    assert r.status_code == 200 and r.json().get("ok"), r.text
    return c


def _pacote_com_n_problemas(n: int) -> bytes:
    doc = _doc()
    base = doc["tipos"][0]
    doc["tipos"] = [dict(base, codigo=i + 1, chave=f"t{i}", grupo="grupo-inexistente") for i in range(n)]
    return _bytes(doc)


# CONSERTADO (turno 3): validação/gravação foram para run_in_threadpool + localizador linear +
# FOR UPDATE na rede para serializar importações concorrentes (a concorrência ficou REAL; sem a trava,
# duas importações na mesma rede podiam colidir em DeadlockDetected -> 500, ver
# test_importacoes_concorrentes_na_mesma_rede_nunca_dao_500).
def test_pacote_ruim_nao_segura_o_servidor_para_os_outros(servidor_real, limpar_redes, medida):
    c = _sessao_http(servidor_real)
    r = c.post("/api/rede", json={"nome": f"{PREFIXO_TESTE}-adv-laco-{uuid.uuid4().hex[:6]}", "disciplina": "agua"})
    assert r.status_code == 201, r.text
    rid = r.json()["id"]
    bruto = _pacote_com_n_problemas(4000)
    resultado: dict = {}

    def importar():
        t = time.monotonic()
        try:
            resp = c.post(f"/api/rede/{rid}/pacote", content=bruto, headers={"Content-Type": "application/json"},
                          timeout=600)
            resultado["status"] = resp.status_code
        except Exception as e:  # noqa: BLE001
            resultado["status"] = repr(e)
        resultado["segundos"] = time.monotonic() - t

    th = threading.Thread(target=importar)
    th.start()
    time.sleep(0.5)
    latencias = []
    while th.is_alive() and len(latencias) < 200:
        t = time.monotonic()
        try:
            httpx.get(servidor_real + "/saude", timeout=120)
        except httpx.HTTPError:
            pass
        latencias.append(time.monotonic() - t)
    th.join(timeout=600)
    c.delete(f"/api/rede/{rid}")
    gravar = medida(ITEM + "-adversario")
    gravar("bytes_do_pacote_ruim", len(bruto), "bytes", "4000 tipos com grupo inexistente")
    gravar("segundos_da_recusa_422", round(resultado.get("segundos", 0), 1), "s", "POST /api/rede/{id}/pacote")
    gravar("pior_latencia_de_saude_durante_a_recusa", round(max(latencias), 2), "s", "GET /saude concorrente")
    assert resultado.get("status") == 422, resultado
    assert max(latencias) < 2.0, f"/saude levou {max(latencias):.1f} s enquanto um pacote era recusado"


def test_pacote_valido_de_cem_mil_linhas_importa_e_mede_o_custo(servidor_real, medida):
    """Fronteira medida (não é achado): pacote VÁLIDO com ~100 mil linhas. Mede o tempo da importação e a
    pior latência de /saude no mesmo intervalo — o mesmo bloqueio do A4, agora sem pacote malicioso."""
    c = _sessao_http(servidor_real)
    r = c.post("/api/rede", json={"nome": f"{PREFIXO_TESTE}-adv-grande-{uuid.uuid4().hex[:6]}", "disciplina": "agua"})
    assert r.status_code == 201, r.text
    rid = r.json()["id"]
    doc = _doc()
    base = doc["atributos"][0]
    grupo = base["grupo"]
    doc["atributos"] = [dict(base, codigo=f"a{i}", grupo=grupo, tipo=None, nome=f"Atributo {i}") for i in range(10_000)]
    for a in doc["atributos"]:
        a.pop("tipo", None)
    bruto = _bytes(doc)
    assert bruto.count(b"\n") >= 100_000
    resultado: dict = {}

    def importar():
        t = time.monotonic()
        resp = c.post(f"/api/rede/{rid}/pacote", content=bruto, headers={"Content-Type": "application/json"},
                      timeout=600)
        resultado["status"], resultado["texto"] = resp.status_code, resp.text[:200]
        resultado["segundos"] = time.monotonic() - t

    th = threading.Thread(target=importar)
    th.start()
    time.sleep(0.3)
    latencias = []
    while th.is_alive() and len(latencias) < 200:
        t = time.monotonic()
        try:
            httpx.get(servidor_real + "/saude", timeout=120)
        except httpx.HTTPError:
            pass
        latencias.append(time.monotonic() - t)
    th.join(timeout=600)
    try:
        assert resultado.get("status") == 201, resultado
        volta = c.get(f"/api/rede/{rid}/pacote")
        assert volta.status_code == 200 and volta.content == pacote_mod.canonizar(pacote_mod.ler(bruto))
    finally:
        c.delete(f"/api/rede/{rid}")
    gravar = medida(ITEM + "-adversario")
    gravar("linhas_do_pacote_valido_grande", bruto.count(b"\n"), "linhas", "10 mil atributos")
    gravar("segundos_da_importacao_valida_grande", round(resultado["segundos"], 1), "s", "POST pacote")
    gravar("pior_latencia_de_saude_durante_importacao_valida", round(max(latencias), 2), "s", "GET /saude")


def test_importacoes_concorrentes_na_mesma_rede_nunca_dao_500(servidor_real):
    c = _sessao_http(servidor_real)
    r = c.post("/api/rede", json={"nome": f"{PREFIXO_TESTE}-adv-conc-{uuid.uuid4().hex[:6]}", "disciplina": "agua"})
    assert r.status_code == 201, r.text
    rid = r.json()["id"]
    pacotes = [instalados.bruto("agua-epanet"), instalados.bruto("eletrica-br")]
    estados = []

    def bater(bruto):
        cli = _sessao_http(servidor_real)
        for _ in range(3):
            resp = cli.post(f"/api/rede/{rid}/pacote", content=bruto, headers={"Content-Type": "application/json"})
            estados.append(resp.status_code)

    ths = [threading.Thread(target=bater, args=(p,)) for p in pacotes * 2]
    for t in ths:
        t.start()
    for t in ths:
        t.join(timeout=300)
    try:
        assert set(estados) <= {201, 409}, estados
        volta = c.get(f"/api/rede/{rid}/pacote")
        assert volta.status_code == 200 and volta.content in pacotes
    finally:
        c.delete(f"/api/rede/{rid}")
