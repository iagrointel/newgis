"""Inventário de Portal/AGOL de ponta a ponta (item L2-08-a-leitor-portal-inventario), contra o servidor de
mentira de `tests/migracao/portal_falso.py`.

⛔ O que ESTE arquivo NÃO prova: nada contra um Portal real. A credencial do portal do parceiro é a decisão
D20 do dono, ainda em aberto, e nenhuma organização pública de terceiro foi usada sem autorização —
`tests/migracao/PORTAL_DE_TESTE.md` registra a pendência com todas as letras. O que se prova aqui é o leitor
e o modelo de dado contra respostas no formato público documentado.
"""

import contextlib
import time
import uuid

import psycopg2
import pytest

from app import db
from app.jobs.registro import FalhaDefinitiva
from app.migracao import inventario as motor
from app.migracao import tarefas as tarefas_migracao
from app.migracao.portal import ClientePortal, ErroRede
from app.schema_ambiente import CursorSchemaAmbiente
from tests.api.conftest import PREFIXO_TESTE
from tests.api.test_rls import ids_por_slug
from tests.jobs_sessao import contexto as contexto_de_teste
from tests.migracao.portal_falso import PortalFalso, acervo

ITEM = "L2-08-a-leitor-portal-inventario"
TOKEN = "tok-de-teste-9f3a2b7c4d1e"     # string improvável: serve de agulha na busca por credencial em log
MINIMO_DO_PORTAO = 50


class CtxFalso:
    """O que a tarefa recebe do worker, sem worker: cursor no inquilino do job e log em `plat.job_log` (o
    mesmo destino do `ContextoJob` real — sem isso, a cláusula 'token nunca aparece em log' não teria onde
    ser conferida). `progresso` não escreve: `plat.job_progresso` exige o job em `rodando` neste worker."""

    def __init__(self, tenant_id: int, usuario_id: int, job_id: str):
        self.job_id = uuid.UUID(str(job_id))
        self.tenant_id = tenant_id
        self._ctx = db.Contexto(tenant_id, usuario_id, "worker")
        self.progressos: list[tuple[int, str]] = []

    def db(self):
        return db.db(self._ctx)

    def log(self, nivel: str, mensagem: str) -> None:
        with self.db() as cur:
            cur.execute("INSERT INTO plat.job_log(job_id, tenant_id, nivel, mensagem) "
                        "VALUES (%s, %s, %s, left(%s, 4000))",
                        (str(self.job_id), self.tenant_id, nivel, str(mensagem)))

    def progresso(self, pct: int, mensagem: str = "") -> None:
        self.progressos.append((pct, mensagem))

    def verificar(self) -> None:
        return None


def _conexao_direta(env):
    return psycopg2.connect(env["PLAT_DSN"], cursor_factory=CursorSchemaAmbiente)


@contextlib.contextmanager
def _cursor(env, tenant_id: int | None = None, usuario_id: int = 0):
    """Cursor como `plat_app` (nunca como postgres — regra da casa). Com `tenant_id`, entra no contexto do
    inquilino: sem isso a RLS esconde TODA linha e a busca por credencial/dado pessoal daria zero por
    ausência de permissão, não por ausência do dado — um teste que passa sem provar nada."""
    con = _conexao_direta(env)
    try:
        with con.cursor() as cur:
            if tenant_id is not None:
                contexto_de_teste(cur, tenant_id, usuario_id, "admin")
            else:
                cur.execute("SET search_path = plat, public")
            yield cur
    finally:
        con.rollback()
        con.close()


@pytest.fixture
def portal():
    with PortalFalso(token_exigido=TOKEN, token_emitido=TOKEN) as p:
        yield p


@pytest.fixture
def limpar(sessao_a):
    """(conexoes, inventarios) apagados no fim, mesmo se a asserção falhar no meio."""
    conexoes, inventarios = [], []
    yield conexoes, inventarios
    for i in inventarios:
        sessao_a.delete(f"/api/migracao/inventarios/{i}")
    for c in conexoes:
        sessao_a.delete(f"/api/conexoes/{c}")


def _preparar(sessao_a, env, portal, limpar, com_token: bool = True):
    """Conexão esri_rest apontando para o portal de mentira + inventário criado pela rota. Devolve
    (inventario_id, job_id, tenant_id, usuario_id)."""
    conexoes, inventarios = limpar
    r = sessao_a.post("/api/conexoes", json={
        "tipo": "esri_rest", "nome": f"{PREFIXO_TESTE}-portal-{uuid.uuid4().hex[:6]}",
        "url": portal.base, "credencial": TOKEN if com_token else None,
    })
    assert r.status_code == 201, r.text
    conexao_id = r.json()["id"]
    conexoes.append(conexao_id)

    r = sessao_a.post("/api/migracao/inventarios", json={"conexao_id": conexao_id})
    assert r.status_code == 201, r.text
    cartao = r.json()
    inventarios.append(cartao["id"])
    eu = sessao_a.get("/api/eu").json()
    con = _conexao_direta(env)
    try:
        tenant_id = ids_por_slug(con)[eu["inquilino"]["slug"]]
    finally:
        con.rollback()
        con.close()

    return cartao["id"], cartao["job_id"], tenant_id, eu["id"]


def _rodar(inventario_id, job_id, tenant_id, usuario_id):
    ctx = CtxFalso(tenant_id, usuario_id, job_id)
    return ctx, tarefas_migracao.migracao_inventariar(ctx, inventario_id=inventario_id)


# --------------------------------------------------------------------- cláusula 1: >= 50 itens conferidos
def test_inventario_lista_itens_tipos_contagens_e_dependencias(sessao_a, env, portal, limpar, medida):
    inv, job, tenant, usuario = _preparar(sessao_a, env, portal, limpar)
    inicio = time.monotonic()
    _, totais = _rodar(inv, job, tenant, usuario)
    segundos = time.monotonic() - inicio

    gravado = acervo()
    assert totais["itens"] == len(gravado["itens"]) >= MINIMO_DO_PORTAO
    assert totais["grupos"] == len(gravado["grupos"])
    assert totais["usuarios"] == len(gravado["usuarios"])

    r = sessao_a.get(f"/api/migracao/inventarios/{inv}")
    assert r.status_code == 200, r.text
    detalhe = r.json()
    assert detalhe["estado"] == "concluido"
    assert detalhe["portal_nome"] == gravado["self"]["name"]

    # --- amostra conferida contra o JSON gravado, item a item: tipo, dono, tamanho, contagem por camada
    esperados = {i["id"]: i for i in gravado["itens"]}
    r = sessao_a.get(f"/api/migracao/inventarios/{inv}/itens?limite=500")
    lidos = {i["item_esri_id"]: i for i in r.json()["itens"]}
    assert set(lidos) == set(esperados)
    conferidos = 0
    for item_id, esperado in esperados.items():
        lido = lidos[item_id]
        assert lido["tipo"] == esperado["type"]
        assert lido["dono_login"] == esperado["owner"]
        assert lido["tamanho_bytes"] == esperado["size"]
        assert lido["num_visualizacoes"] == esperado["numViews"]
        if esperado["url"]:
            chave = esperado["url"]
            servico = gravado["servicos"][chave]
            soma = sum(servico["contagens"].values())
            assert lido["contagem_total"] == soma, (item_id, esperado["type"])
            assert len(lido["camadas"]) == len(servico["layers"]) + len(servico["tables"])
            conferidos += 1
    assert conferidos >= 15  # os serviços do acervo, todos com contagem batida contra o JSON

    # --- dependência: todo web map aponta para as camadas que o documento declara
    web_maps = [i for i in lidos.values() if i["tipo"] == "Web Map"]
    assert len(web_maps) >= 5
    for wm in web_maps:
        alvos = {d["alvo"] for d in wm["dependencias"]}
        documento = gravado["dados"][wm["item_esri_id"]]
        assert alvos == {c["itemId"] for c in documento["operationalLayers"]}
    # --- aplicativo -> web map
    apps = [i for i in lidos.values() if i["tipo"] in ("Dashboard", "Web Mapping Application")]
    assert apps and all(a["dependencias"] for a in apps)

    # --- classificação prévia (tabela do L2-08-d)
    classes = detalhe["por_classificacao"]
    assert classes["migra"] > 0 and classes["nao_migra"] > 0
    assert classes["desconhecido"] == 1  # o tipo "Quantum Widget" do acervo, nunca chutado como nao_migra
    parciais = [i for i in lidos.values() if i["classificacao"] == "migra_parcial"]
    assert all(i["classificacao_motivo"] for i in parciais)

    gravar = medida(ITEM)
    gravar("itens_inventariados", totais["itens"], "itens",
           "tarefa migracao.inventariar contra tests/migracao/portal_falso.py")
    gravar("pedidos_http_do_inventario", totais["pedidos_http"], "pedidos", "mesma execução")
    gravar("segundos_do_inventario", round(segundos, 2), "s", "mesma execução")
    gravar("feicoes_contadas", totais["feicoes"], "feições", "query returnCountOnly=true por camada")


# --------------------------------------------------------------------- cláusula 2: token nunca em log
def test_token_nunca_aparece_em_log_nem_em_coluna_de_texto(sessao_a, env, portal, limpar):
    inv, job, tenant, usuario = _preparar(sessao_a, env, portal, limpar)
    ctx, _ = _rodar(inv, job, tenant, usuario)
    ctx.log("INFO", "linha de log deste teste, para provar que o log existe e é lido")

    assert portal.tokens_na_query == [], "o leitor mandou o token na query (tinha de ser cabeçalho)"

    achados = []
    with _cursor(env, tenant, usuario) as cur:
        # toda coluna de texto de toda tabela do schema, menos a que existe para guardar a credencial
        # CIFRADA (plat.conexao.credencial_cifrada) — que não contém o token em claro por construção
        cur.execute(
            "SELECT table_name, column_name FROM information_schema.columns "
            "WHERE table_schema = current_schema() AND data_type IN ('text', 'character varying', 'jsonb') "
            "AND NOT (table_name = 'conexao' AND column_name = 'credencial_cifrada') "
            "ORDER BY table_name, column_name"
        )
        colunas = [(r["table_name"], r["column_name"]) for r in cur.fetchall()]
        assert len(colunas) > 100, "a varredura tem de olhar o schema inteiro, não duas tabelas"
        for tabela, coluna in colunas:
            cur.execute(
                f'SELECT count(*) AS n FROM plat."{tabela}" WHERE "{coluna}"::text LIKE %s',  # noqa: S608
                (f"%{TOKEN}%",),
            )
            n = int(cur.fetchone()["n"])
            if n:
                achados.append((tabela, coluna, n))
        # o log do job existe mesmo (senão a busca acima seria vazia por não haver o que buscar)
        cur.execute("SELECT count(*) AS n FROM plat.job_log WHERE job_id = %s", (str(job),))
        assert int(cur.fetchone()["n"]) > 0
    assert achados == [], achados


# --------------------------------------------------------------------- cláusula 3: retomada após corte
def test_job_retoma_depois_de_corte_de_rede_no_meio(sessao_a, env, portal, limpar, medida):
    inv, job, tenant, usuario = _preparar(sessao_a, env, portal, limpar)
    # corta a conexão no 30º pedido: já leu portals/self, a primeira página e parte dos itens
    portal.configurar(falhar_apos=30)
    with pytest.raises(ErroRede):
        _rodar(inv, job, tenant, usuario)

    with _cursor(env, tenant, usuario) as cur:
        cur.execute("SELECT estado, retomada FROM plat.migracao_inventario WHERE id = %s::uuid", (inv,))
        parcial = cur.fetchone()
        cur.execute("SELECT count(*) AS n FROM plat.migracao_item WHERE inventario_id = %s::uuid", (inv,))
        itens_parciais = int(cur.fetchone()["n"])
    assert parcial["estado"] == "rodando"          # nunca "falhou": erro de rede é para tentar de novo
    assert 0 < itens_parciais < len(acervo()["itens"])
    assert parcial["retomada"]["fase"] == "itens"  # o ponto onde parou está gravado

    pedidos_ate_o_corte = portal.pedidos
    portal.configurar(falhar_apos=None)
    _, totais = _rodar(inv, job, tenant, usuario)
    pedidos_na_retomada = portal.pedidos - pedidos_ate_o_corte

    assert totais["itens"] == len(acervo()["itens"])
    # a retomada custou MENOS pedidos do que um inventário do zero: os itens já gravados não foram relidos
    inv2, job2, _, _ = _preparar(sessao_a, env, portal, limpar)
    antes = portal.pedidos
    _rodar(inv2, job2, tenant, usuario)
    do_zero = portal.pedidos - antes
    assert pedidos_na_retomada < do_zero, (pedidos_na_retomada, do_zero)

    gravar = medida(ITEM)
    gravar("pedidos_do_zero", do_zero, "pedidos", "inventário completo do portal de mentira")
    gravar("pedidos_na_retomada", pedidos_na_retomada, "pedidos",
           "segunda tentativa depois de corte de rede no 30º pedido")


# --------------------------------------------------------------------- cláusula 4: relatório CSV
def test_relatorio_csv_sai_com_uma_linha_por_item(sessao_a, env, portal, limpar):
    inv, job, tenant, usuario = _preparar(sessao_a, env, portal, limpar)
    _rodar(inv, job, tenant, usuario)
    r = sessao_a.get(f"/api/migracao/inventarios/{inv}/relatorio.csv")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    assert "attachment" in r.headers["content-disposition"]
    corpo = r.content
    assert corpo.startswith(b"\xef\xbb\xbf")        # BOM: o destinatário abre no Excel em português
    linhas = corpo.decode("utf-8-sig").strip().split("\r\n")
    assert len(linhas) == len(acervo()["itens"]) + 1
    assert linhas[0].startswith("id do item no portal;título;tipo Esri;classificação")
    assert TOKEN not in corpo.decode("utf-8-sig")


# --------------------------------------------------------------------- refutação: LGPD
def test_nenhum_dado_pessoal_de_usuario_e_gravado(sessao_a, env, portal, limpar):
    """O portal de mentira DEVOLVE e-mail e nome completo (como um portal de verdade devolve). Nada disso
    pode ser encontrado no banco depois — e a tabela nem tem coluna onde caberia."""
    inv, job, tenant, usuario = _preparar(sessao_a, env, portal, limpar)
    _rodar(inv, job, tenant, usuario)

    agulhas = ["@exemplo.invalido", "Nome Completo", "descrição pessoal"]
    with _cursor(env, tenant, usuario) as cur:
        cur.execute("SELECT column_name FROM information_schema.columns WHERE table_schema = "
                    "current_schema() AND table_name = 'migracao_usuario'")
        colunas = {r["column_name"] for r in cur.fetchall()}
        assert colunas, "tabela plat.migracao_usuario não encontrada"
        assert not (colunas & {"email", "e_mail", "nome", "nome_completo", "telefone", "descricao"}), colunas
        for tabela in ("migracao_usuario", "migracao_grupo", "migracao_item", "migracao_inventario"):
            cur.execute(f"SELECT count(*) AS n FROM plat.{tabela} WHERE inventario_id::text = %s "  # noqa: S608
                        if tabela != "migracao_inventario" else
                        f"SELECT count(*) AS n FROM plat.{tabela} WHERE id::text = %s", (inv,))  # noqa: S608
            assert int(cur.fetchone()["n"]) > 0, f"{tabela} vazia: a busca por dado pessoal não provaria nada"
            for agulha in agulhas:
                cur.execute(
                    f"SELECT count(*) AS n FROM plat.{tabela} t WHERE t::text LIKE %s",  # noqa: S608
                    (f"%{agulha}%",),
                )
                assert int(cur.fetchone()["n"]) == 0, (tabela, agulha)
        cur.execute("SELECT login FROM plat.migracao_usuario WHERE inventario_id = %s::uuid", (inv,))
        logins = {r["login"] for r in cur.fetchall()}
        assert logins == {u["username"] for u in acervo()["usuarios"]}
        cur.execute("SELECT membros FROM plat.migracao_grupo WHERE inventario_id = %s::uuid", (inv,))
        for linha in cur.fetchall():
            assert linha["membros"] and all(isinstance(m, str) for m in linha["membros"])
            assert all("@" not in m for m in linha["membros"])


# --------------------------------------------------------------------- refutação: URL que não é Portal
def test_url_que_nao_e_portal_da_erro_nomeado_e_nunca_500(sessao_a, env, limpar):
    with PortalFalso(nao_e_portal=True) as falso:
        inv, job, tenant, usuario = _preparar(sessao_a, env, falso, limpar, com_token=False)
        with pytest.raises(FalhaDefinitiva) as exc:
            _rodar(inv, job, tenant, usuario)
        assert "nao_e_portal" in str(exc.value)
        r = sessao_a.get(f"/api/migracao/inventarios/{inv}")
        assert r.status_code == 200
        assert r.json()["estado"] == "falhou"
        assert "nao_e_portal" in r.json()["mensagem"]


def test_conexao_que_nao_e_esri_rest_e_recusada_na_rota(sessao_a, limpar):
    conexoes, _ = limpar
    r = sessao_a.post("/api/conexoes", json={
        "tipo": "wms", "nome": f"{PREFIXO_TESTE}-wms-{uuid.uuid4().hex[:6]}",
        "url": "https://servicodados.ibge.gov.br/api/v1/localidades/estados/35",
    })
    assert r.status_code == 201, r.text
    conexoes.append(r.json()["id"])
    r2 = sessao_a.post("/api/migracao/inventarios", json={"conexao_id": r.json()["id"]})
    assert r2.status_code == 422
    assert r2.json()["erro"] == "conexao_nao_e_portal"


# --------------------------------------------------------------------- limite de uso (429) com espera
def test_limite_de_uso_do_portal_espera_e_termina(sessao_a, env, limpar):
    """429 nos 3 primeiros pedidos: o leitor espera o `Retry-After` e conclui, sem perder item nenhum. Três é
    o número que a espera do leitor aguenta antes de desistir (TENTATIVAS_429 = 1 tentativa + 3 esperas) — o
    teste fica no limite de propósito, para provar que a última espera ainda serve."""
    with PortalFalso(limite_ate=3) as falso:
        inv, job, tenant, usuario = _preparar(sessao_a, env, falso, limpar, com_token=False)
        esperas = []
        cliente = ClientePortal(base=falso.base, pausa=esperas.append)
        execucao = motor.Inventario(cliente, CtxFalso(tenant, usuario, job).db, inv, tenant)
        totais = execucao.executar()
    assert totais["itens"] == len(acervo()["itens"])
    assert cliente.esperas_429 == 3 and len(esperas) == 3
    assert esperas == [0.0] * 3  # Retry-After: 0 do servidor de teste, respeitado no lugar da espera padrão


# --------------------------------------------------------------------- refutação: 10 mil itens
@pytest.mark.lento
def test_portal_com_dez_mil_itens_pagina_e_termina(sessao_a, env, limpar, medida):
    with PortalFalso(itens_sinteticos=10_000) as falso:
        inv, job, tenant, usuario = _preparar(sessao_a, env, falso, limpar, com_token=False)
        inicio = time.monotonic()
        _, totais = _rodar(inv, job, tenant, usuario)
        segundos = time.monotonic() - inicio
        pedidos = falso.pedidos
    assert totais["itens"] == 10_000
    r = sessao_a.get(f"/api/migracao/inventarios/{inv}/itens?limite=1")
    assert r.json()["total"] == 10_000
    gravar = medida(ITEM)
    gravar("segundos_para_dez_mil_itens", round(segundos, 1), "s",
           "portal de mentira com itens_sinteticos=10000 (refutação do item)")
    gravar("pedidos_para_dez_mil_itens", pedidos, "pedidos", "mesma execução")
