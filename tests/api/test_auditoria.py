"""Trilha de auditoria de negócio (item L7-20), cláusula por cláusula do portão de pronto.

  1. toda rota de escrita do OpenAPI gera linha  -> test_toda_rota_de_escrita_do_openapi_esta_coberta
                                                    + test_rotas_de_escrita_exercidas_deixam_linha
  2. UPDATE/DELETE como plat_app falha           -> test_update_delete_e_truncate_como_plat_app_falham
  3. retenção configurável + expurgo por pg_cron -> test_retencao_por_inquilino_com_piso
                                                    + test_expurgo_apaga_so_o_que_passou_da_retencao
                                                    + test_cron_nome_sai_do_schema_e_agendar_e_idempotente
  4. exportação bate com contagem                -> test_exportacao_bate_com_a_contagem_da_tabela
  5. refutação (adversário apaga a trilha)       -> test_adversario_nao_apaga_a_propria_trilha

A prova de que a linha existe usa o cabeçalho `X-Req-Id` da resposta: cada requisição carrega o seu
identificador, e a linha de auditoria guarda o mesmo — não é preciso adivinhar qual linha é de qual chamada.
"""

import json
import secrets
import subprocess
import time

import pytest

from tests.api.conftest import arquivo_openapi
from tests.api.eventos_esperados import EVENTOS_POR_ROTA

ITEM = "L7-20-trilha-auditoria"
LINHAS_EXPURGO = 5000  # linhas sintéticas do teste de expurgo; grande o bastante para medir, pequeno para durar


def _janela(minutos: int = 30) -> dict:
    import datetime

    ate = datetime.datetime.now(datetime.UTC) + datetime.timedelta(minutes=1)
    desde = ate - datetime.timedelta(minutes=minutos + 1)
    return {"desde": desde.isoformat(), "ate": ate.isoformat()}


def _janela_fechada(minutos: int = 30) -> dict:
    """Janela que termina AGORA: linha gravada depois desta chamada não entra na contagem."""
    import datetime

    ate = datetime.datetime.now(datetime.UTC)
    return {"desde": (ate - datetime.timedelta(minutes=minutos)).isoformat(), "ate": ate.isoformat()}


def _linhas_por_req(sessao, req_ids: list[str]) -> dict[str, list[dict]]:
    """Todas as linhas da janela recente, agrupadas por req_id (uma consulta só)."""
    r = sessao.get("/api/auditoria", params={**_janela(), "limite": 1000})
    assert r.status_code == 200, r.text
    por_req: dict[str, list[dict]] = {rid: [] for rid in req_ids}
    for linha in r.json()["itens"]:
        if linha["req_id"] in por_req:
            por_req[linha["req_id"]].append(linha)
    return por_req


def _psql(sql: str, schema: str) -> str:
    """psql como postgres: só para o que é NEGADO a plat_app de propósito (semear linha antiga, expurgar).

    O `env` vai por `sudo ... env VAR=...`, não pelo `env=` do subprocess: o sudo limpa o ambiente
    (`env_reset`), e sem isso o PGOPTIONS some, o search_path fica em `public` e o erro que volta é
    "relation auditoria does not exist" — que parecia falta de sudo e virava skip silencioso.
    """
    cmd = ["sudo", "-n", "-u", "postgres", "env", f"PGOPTIONS=-c search_path={schema},public",
           "psql", "-d", "iagro_sat", "-X", "-A", "-t", "-v", "ON_ERROR_STOP=1", "-c", sql]
    try:
        saida = subprocess.run(cmd, capture_output=True, text=True, check=False)
    except OSError as e:  # sem sudo/psql nesta máquina
        pytest.skip(f"sudo/psql indisponível: {e}")
    if saida.returncode != 0:
        erro = saida.stderr.strip()
        if "sudo:" in erro and "password" in erro:
            pytest.skip(f"sudo sem senha indisponível para postgres: {erro[:120]}")
        pytest.fail(f"psql falhou ({saida.returncode}) em {sql[:80]!r}: {erro[:400]}")
    return saida.stdout.strip()


@pytest.fixture(scope="module")
def schema(env) -> str:
    return env.get("PLAT_SCHEMA") or "plat"


# ---------------------------------------------------------------- 1. cobertura do OpenAPI
def test_toda_rota_de_escrita_do_openapi_esta_coberta(conexao_plat_app, medida):
    """Percorre o OpenAPI e classifica cada rota de escrita no mecanismo que a cobre.

    Dois mecanismos, os dois no banco e os dois na MESMA transação do ato:
      * `evento`    — a rota registra evento de domínio e a trigger `evento_auditoria` grava a linha;
      * `cobertura` — `app/db.py` chama `plat.auditoria_cobrir()` no fim de toda transação de escrita, que
                      grava a linha quando aquele req_id ainda não deixou nenhuma.
    O segundo não depende de a rota lembrar de nada, e é por isso que a cobertura é 100% e não uma lista
    curada. O teste confere que os dois mecanismos EXISTEM no banco e no código, não só que estão declarados.
    """
    from pathlib import Path

    spec = arquivo_openapi()
    escrita = sorted(
        (m.upper(), c) for c, ms in spec["paths"].items() for m in ms
        if m.upper() in ("POST", "PUT", "DELETE", "PATCH")
    )
    por_evento = [r for r in escrita if EVENTOS_POR_ROTA.get(r)]
    por_cobertura = [r for r in escrita if not EVENTOS_POR_ROTA.get(r)]
    assert len(por_evento) + len(por_cobertura) == len(escrita)

    # mecanismo (a): a trigger existe e está na tabela-mãe dos eventos
    with conexao_plat_app.cursor() as cur:
        # o tgrelid tem de ser a tabela-mãe DESTE schema: `relname = 'evento'` sozinho casa a tabela de
        # qualquer schema da máquina (produção e as outras trilhas), e a contagem daria mais de um.
        cur.execute(
            "SELECT count(*) AS n FROM pg_trigger t WHERE NOT t.tgisinternal "
            "AND t.tgname = 'evento_auditoria' AND t.tgrelid = to_regclass('plat.evento')"
        )
        assert cur.fetchone()["n"] == 1, "trigger evento_auditoria ausente na tabela-mãe plat.evento"
        # mecanismo (b): a função de cobertura existe e é executável pela role da aplicação
        cur.execute("SELECT plat.auditoria_cobrir() AS id")
        assert cur.fetchone() is not None

    # mecanismo (b), lado do código: o choke point é app/db.py, e nenhuma rota abre conexão por fora
    raiz = Path(__file__).resolve().parents[2]
    fonte_db = (raiz / "app" / "db.py").read_text(encoding="utf-8")
    assert "auditoria.cobrir(cur)" in fonte_db, "app/db.py deixou de chamar auditoria.cobrir"
    # app/db.py e app/jobs/worker.py: os dois donos de conexão do produto. app/jobs/eventos.py abre a sua
    # só para o LISTEN do SSE (não faz INSERT/UPDATE em nome de requisição), por isso está na lista.
    DONOS_DE_CONEXAO = {"db.py", "worker.py", "eventos.py"}
    fora = [
        p.relative_to(raiz).as_posix()
        for p in (raiz / "app").rglob("*.py")
        if "psycopg2.connect(" in p.read_text(encoding="utf-8") and p.name not in DONOS_DE_CONEXAO
    ]
    assert fora == [], f"módulo abre conexão fora de app/db.py e escaparia da auditoria: {fora}"

    gravar = medida(ITEM)
    gravar("rotas_de_escrita_do_openapi", len(escrita), "rotas",
           "docs/openapi.json: POST/PUT/PATCH/DELETE")
    gravar("rotas_de_escrita_cobertas", len(escrita), "rotas",
           "evento (trigger em plat.evento) + cobertura (plat.auditoria_cobrir em app/db.py)")
    gravar("rotas_cobertas_por_evento", len(por_evento), "rotas", "EVENTOS_POR_ROTA com lista não vazia")
    gravar("rotas_cobertas_por_cobertura", len(por_cobertura), "rotas", "EVENTOS_POR_ROTA vazia ou ausente")


def test_rotas_de_escrita_exercidas_deixam_linha(sessao_a, usuarios_a, medida):
    """Exercita rotas de escrita de verdade, pelos DOIS mecanismos, e confere linha a linha pelo X-Req-Id."""
    sufixo = secrets.token_hex(3)
    u, _ = usuarios_a.criar("visualizador")
    req_ids, respostas = {}, {}

    def chamar(nome, metodo, caminho, corpo=None):
        r = sessao_a.request(metodo, caminho, json=corpo if corpo is not None else {})
        assert r.status_code < 400, (nome, r.status_code, r.text)  # 4xx não abre transação: nada a auditar
        assert "x-req-id" in {k.lower() for k in r.headers}, (nome, dict(r.headers))
        req_ids[nome] = r.headers["X-Req-Id"]
        respostas[nome] = r
        return r

    chamar("usuarios/papel", "PUT", f"/api/usuarios/{u['id']}", {"perfil": "editor"})
    pasta = chamar("pastas/criar", "POST", "/api/pastas", {"nome": f"zt-aud-{sufixo}"})
    chamar("2fa_iniciar_sem_evento", "POST", "/api/eu/2fa/iniciar")
    item = chamar("itens/adicionar", "POST", "/api/itens",
                  {"tipo": "mapa", "titulo": f"zt aud {sufixo}", "dados": {"esquema_versao": 1, "corpo": {}}})
    item_id = item.json()["id"]
    chamar("favoritos/adicionar", "PUT", f"/api/favoritos/{item_id}")
    chamar("compartilhamento/alterar", "PUT", f"/api/itens/{item_id}/compartilhamento",
           {"acesso": "inquilino"})

    por_req = _linhas_por_req(sessao_a, list(req_ids.values()))
    sem_linha = [nome for nome, rid in req_ids.items() if not por_req.get(rid)]
    # limpeza antes de qualquer assert, para não deixar resíduo quando o teste falha
    sessao_a.delete(f"/api/itens/{item_id}")
    sessao_a.delete(f"/api/pastas/{pasta.json()['id']}")
    assert sem_linha == [], f"requisição de escrita sem linha de auditoria: {sem_linha}"

    papel = por_req[req_ids["usuarios/papel"]]
    acoes = {linha["acao"] for linha in papel}
    assert "usuarios/papel" in acoes, acoes
    mudanca = next(linha for linha in papel if linha["acao"] == "usuarios/papel")
    assert mudanca["antes"] == {"perfil": "visualizador", "papel_id": None}, mudanca["antes"]
    assert mudanca["depois"] == {"perfil": "editor", "papel_id": None}, mudanca["depois"]
    assert mudanca["ator_login"] and mudanca["ip"] and mudanca["req_id"], mudanca
    assert mudanca["origem"] == "evento"

    sem_evento = por_req[req_ids["2fa_iniciar_sem_evento"]]
    assert [linha["origem"] for linha in sem_evento] == ["cobertura"], sem_evento
    assert sem_evento[0]["rota"] == "/api/eu/2fa/iniciar", sem_evento[0]

    gravar = medida(ITEM)
    gravar("rotas_exercidas_com_linha", len(req_ids), "rotas",
           "pytest tests/api/test_auditoria.py::test_rotas_de_escrita_exercidas_deixam_linha")


# ---------------------------------------------------------------- 2. imutabilidade
def test_update_delete_e_truncate_como_plat_app_falham(conexao_plat_app, medida):
    """A role da aplicação não altera, não apaga e não trunca — nem pondo a marca de expurgo na transação."""
    import psycopg2

    tentativas = [
        ("UPDATE", "UPDATE plat.auditoria SET acao = 'forjado'"),
        ("DELETE", "DELETE FROM plat.auditoria"),
        ("TRUNCATE", "TRUNCATE plat.auditoria"),
        ("INSERT", "INSERT INTO plat.auditoria(tenant_id, acao) VALUES (1, 'forjado')"),
        ("DELETE com a marca posta",
         "SELECT set_config('plat.auditoria_expurgo', '1', true); DELETE FROM plat.auditoria"),
    ]
    barradas = []
    for nome, sql in tentativas:
        with conexao_plat_app.cursor() as cur:
            with pytest.raises((psycopg2.errors.InsufficientPrivilege, psycopg2.errors.RaiseException)):
                cur.execute(sql)
        conexao_plat_app.rollback()
        barradas.append(nome)
    assert barradas == [n for n, _ in tentativas]
    medida(ITEM)("tentativas_de_escrita_barradas", len(barradas), "tentativas",
                 "pytest tests/api/test_auditoria.py::test_update_delete_e_truncate_como_plat_app_falham")


def test_funcoes_de_expurgo_e_de_cron_negadas_a_plat_app(conexao_plat_app):
    """A migração 001 dá EXECUTE por DEFAULT PRIVILEGES a toda função nova; estas precisam de REVOKE explícito.

    Sem o REVOKE, `SELECT plat.auditoria_expurgar()` roda como plat_app — medido nesta trilha antes da
    correção — e a aplicação apagaria a trilha que deveria guardar.
    """
    import psycopg2

    negadas = [
        "SELECT plat.auditoria_expurgar()",
        "SELECT plat.auditoria_registrar('forjado', 'x', '1', NULL, NULL, 'aplicacao', 1, 1)",
        "SELECT plat.auditoria_cron_agendar()",
        "SELECT plat.auditoria_cron_desagendar()",
    ]
    for sql in negadas:
        with conexao_plat_app.cursor() as cur:
            with pytest.raises(psycopg2.errors.InsufficientPrivilege):
                cur.execute(sql)
        conexao_plat_app.rollback()


def test_inquilino_b_nao_ve_a_trilha_de_a(sessao_a, sessao_b, usuarios_a):
    """RLS: a linha é escrita pela APLICAÇÃO, não pelo usuário — é o lugar clássico de vazar o inquilino."""
    u, _ = usuarios_a.criar("visualizador")
    r = sessao_a.put(f"/api/usuarios/{u['id']}", json={"perfil": "editor"})
    rid = r.headers["X-Req-Id"]
    de_a = sessao_a.get("/api/auditoria", params={**_janela(), "limite": 1000}).json()["itens"]
    de_b = sessao_b.get("/api/auditoria", params={**_janela(), "limite": 1000}).json()["itens"]
    assert any(linha["req_id"] == rid for linha in de_a), "a trilha de A não tem o ato de A"
    assert not any(linha["req_id"] == rid for linha in de_b), "a trilha de B mostrou um ato de A"


# ---------------------------------------------------------------- 3. retenção e expurgo
def test_retencao_por_inquilino_com_piso(sessao_a, sessao_b):
    """Retenção é POR INQUILINO (recurso partilhado com dimensão de dono) e tem piso: 90 dias.

    O piso é a resposta ao "expurgo prematuro" da refutação: nem o administrador do inquilino encolhe a
    própria trilha até apagá-la. E a mudança é ela mesma auditada.
    """
    c = sessao_a.get("/api/auditoria/config")
    assert c.status_code == 200, c.text
    padrao = c.json()
    assert padrao["padrao_dias"] == 730 and padrao["minimo_dias"] == 90, padrao
    assert padrao["job_expurgo"] and padrao["job_expurgo"].endswith("_auditoria_expurgo"), padrao

    for invalido in (1, 89, 0, -5, 4000):
        r = sessao_a.put("/api/auditoria/config", json={"retencao_dias": invalido})
        assert r.status_code == 422, (invalido, r.status_code, r.text)

    original = padrao["retencao_dias"]
    try:
        r = sessao_a.put("/api/auditoria/config", json={"retencao_dias": 400})
        assert r.status_code == 200 and r.json()["retencao_dias"] == 400, r.text
        rid = r.headers["X-Req-Id"]
        # o inquilino B não muda junto: a configuração tem dimensão de inquilino
        assert sessao_b.get("/api/auditoria/config").json()["retencao_dias"] == 730
        # a própria mudança deixou linha, com antes e depois
        linhas = _linhas_por_req(sessao_a, [rid])[rid]
        troca = next(linha for linha in linhas if linha["acao"] == "auditoria/retencao")
        assert troca["antes"] == {"retencao_dias": original} and troca["depois"] == {"retencao_dias": 400}, troca
    finally:
        sessao_a.put("/api/auditoria/config", json={"retencao_dias": original})


def test_cron_nome_sai_do_schema_e_agendar_e_idempotente(conexao_plat_app, schema, medida):
    """Regra do ADR 0031: nome do job derivado de current_schema(), agendamento idempotente.

    pg_cron é recurso GLOBAL da máquina. Um job de nome fixo agendado por uma base de teste expurgaria a
    auditoria de produção — o mesmo defeito de fila, trinco e cota sem dimensão de dono.
    """
    with conexao_plat_app.cursor() as cur:
        cur.execute("SELECT plat.auditoria_cron_nome() AS nome, plat.auditoria_cron_contar() AS n")
        r = cur.fetchone()
    nome, antes = r["nome"], r["n"]
    assert nome == f"{schema}_auditoria_expurgo", (nome, schema)
    if antes == -1:
        pytest.skip("pg_cron não instalado nesta máquina")
    assert antes == 1, f"o job deste schema deveria estar agendado uma vez, está {antes}"

    # agendar de novo NÃO cria um segundo job
    _psql("SELECT auditoria_cron_agendar()", schema)
    with conexao_plat_app.cursor() as cur:
        cur.execute("SELECT plat.auditoria_cron_contar() AS n")
        depois = cur.fetchone()["n"]
    assert depois == 1, f"agendar duas vezes criou {depois} jobs com o nome {nome}"

    # e o nome de OUTRO schema é outro: nenhum job de trilha aponta para a tabela de produção
    todos = _psql("SELECT string_agg(jobname || '=' || command, '|' ORDER BY jobname) FROM cron.job", schema)
    for par in [p for p in todos.split("|") if p.endswith(")")]:
        job, comando = par.split("=", 1)
        alvo = job.removesuffix("_auditoria_expurgo")
        assert f"{alvo}.auditoria_expurgar()" in comando, (job, comando)

    medida(ITEM)("jobs_pg_cron_com_o_nome_do_schema", depois, "jobs",
                 f"SELECT count(*) FROM cron.job WHERE jobname = '{nome}' depois de agendar duas vezes")


def test_expurgo_apaga_so_o_que_passou_da_retencao(conexao_plat_app, schema, medida):
    """Semeia linhas antigas (como postgres, que é quem pode) e confere que o expurgo leva só as antigas."""
    marca = f"zt-expurgo-{secrets.token_hex(3)}"
    _psql(
        "INSERT INTO auditoria(em, tenant_id, acao, origem) "
        f"SELECT now() - interval '800 days', t.id, '{marca}', 'aplicacao' "
        f"FROM tenant t, generate_series(1, {LINHAS_EXPURGO // 2}) WHERE t.slug = 'demo'",
        schema,
    )
    _psql(
        "INSERT INTO auditoria(em, tenant_id, acao, origem) "
        f"SELECT now() - interval '10 days', t.id, '{marca}', 'aplicacao' "
        f"FROM tenant t, generate_series(1, {LINHAS_EXPURGO // 2}) WHERE t.slug = 'demo'",
        schema,
    )
    antigas = int(_psql(f"SELECT count(*) FROM auditoria WHERE acao = '{marca}' AND em < now() - interval '730 days'",
                        schema))
    recentes = int(_psql(f"SELECT count(*) FROM auditoria WHERE acao = '{marca}' AND em > now() - interval '730 days'",
                         schema))
    assert antigas == LINHAS_EXPURGO // 2 and recentes == LINHAS_EXPURGO // 2, (antigas, recentes)

    inicio = time.perf_counter()
    apagadas = int(_psql("SELECT auditoria_expurgar()", schema))
    ms = round((time.perf_counter() - inicio) * 1000, 1)

    sobrou_antiga = int(_psql(f"SELECT count(*) FROM auditoria WHERE acao = '{marca}' "
                              "AND em < now() - interval '730 days'", schema))
    sobrou_recente = int(_psql(f"SELECT count(*) FROM auditoria WHERE acao = '{marca}' "
                               "AND em > now() - interval '730 days'", schema))
    _psql(f"SET plat.auditoria_expurgo = '1'; DELETE FROM auditoria WHERE acao = '{marca}'", schema)
    assert sobrou_antiga == 0, f"{sobrou_antiga} linhas passadas da retenção sobreviveram ao expurgo"
    assert sobrou_recente == LINHAS_EXPURGO // 2, f"o expurgo levou linha DENTRO da retenção ({sobrou_recente})"
    assert apagadas >= antigas, (apagadas, antigas)

    gravar = medida(ITEM)
    gravar("expurgo_linhas", apagadas, "linhas", "SELECT plat.auditoria_expurgar() com 2500 linhas de 800 dias")
    gravar("expurgo_ms", ms, "ms", f"perf_counter em volta de SELECT auditoria_expurgar() ({apagadas} linhas)")
    gravar("expurgo_linhas_dentro_da_retencao_perdidas", 0, "linhas",
           "count(*) das linhas de 10 dias depois do expurgo, contra as 2500 semeadas")


# ---------------------------------------------------------------- 4. exportação
def test_exportacao_bate_com_a_contagem_da_tabela(sessao_a, medida):
    """CSV e JSON exportam o MESMO conjunto que a tela conta, na mesma janela e com os mesmos filtros."""
    # `ate` no PASSADO imediato de propósito: cada exportação grava a sua própria linha, e se a janela
    # incluísse "agora" a segunda exportação contaria a linha da primeira e a contagem nunca fecharia.
    janela = _janela_fechada(minutos=60)
    pagina = sessao_a.get("/api/auditoria", params={**janela, "limite": 1})
    assert pagina.status_code == 200, pagina.text
    total = pagina.json()["total"]
    assert total > 0, "a janela de teste precisa ter pelo menos uma linha (a suíte já escreveu várias)"

    csv = sessao_a.get("/api/auditoria", params={**janela, "formato": "csv"})
    assert csv.status_code == 200 and csv.headers["content-type"].startswith("text/csv"), csv.headers
    linhas_csv = [linha for linha in csv.text.splitlines() if linha.strip()]
    # o cabeçalho não conta; o csv pode ter quebra de linha dentro de campo, por isso o cabeçalho X-Plat-Linhas
    declaradas_csv = int(csv.headers["X-Plat-Linhas"])
    assert declaradas_csv == total, (declaradas_csv, total)
    assert len(linhas_csv) >= total, (len(linhas_csv), total)
    assert linhas_csv[0].startswith("id,em,ator_id,ator_login,token_id,acao"), linhas_csv[0]

    jse = sessao_a.get("/api/auditoria", params={**janela, "formato": "json_export"})
    assert jse.status_code == 200, jse.text
    corpo = json.loads(jse.text)
    assert corpo["total"] == total == len(corpo["itens"]), (corpo["total"], total, len(corpo["itens"]))
    assert int(jse.headers["X-Plat-Linhas"]) == total

    # o próprio ato de exportar entra na trilha, DEPOIS do conjunto exportado (senão a contagem nunca fechava)
    exportados = {linha["id"] for linha in corpo["itens"]}
    marca = sessao_a.get("/api/auditoria", params={**_janela(), "acao": "auditoria/exportar", "limite": 10})
    assert marca.json()["total"] >= 2, marca.json()
    # as duas exportações desta rodada são as duas linhas mais novas: nasceram DEPOIS de tudo o que saiu no
    # arquivo. (Exportação de rodada anterior estar dentro do arquivo é história legítima, não erro.)
    desta_rodada = sorted(linha["id"] for linha in marca.json()["itens"])[-2:]
    assert min(desta_rodada) > max(exportados), (desta_rodada, max(exportados))
    ultima = marca.json()["itens"][0]
    assert ultima["depois"]["linhas"] == total, ultima

    medida(ITEM)("exportacao_linhas_x_contagem", total, "linhas",
                 "GET /api/auditoria?formato=csv|json_export contra plat.auditoria_contar da mesma janela")


# ---------------------------------------------------------------- 5. refutação
def test_adversario_nao_apaga_a_propria_trilha(sessao_a, usuarios_a, conexao_plat_app, schema):
    """O adversário edita um item e tenta apagar o rastro por todos os caminhos que tem.

    (a) pela API: nenhuma rota apaga linha de auditoria;
    (b) por SQL como plat_app: sem privilégio e com trigger;
    (c) por expurgo prematuro: o piso da retenção e a negação de EXECUTE fecham os dois lados.
    """
    import psycopg2

    u, _ = usuarios_a.criar("visualizador")
    r = sessao_a.put(f"/api/usuarios/{u['id']}", json={"perfil": "editor"})
    rid = r.headers["X-Req-Id"]
    linhas = _linhas_por_req(sessao_a, [rid])[rid]
    assert linhas, "o ato do adversário não deixou linha"
    alvo = linhas[0]["id"]

    # (a) pela API: nenhuma rota de escrita de /api/auditoria existe além da configuração
    spec = arquivo_openapi()
    escrita_auditoria = {
        (m.upper(), c) for c, ms in spec["paths"].items() for m in ms
        if c.startswith("/api/auditoria") and m.upper() in ("POST", "PUT", "PATCH", "DELETE")
    }
    assert escrita_auditoria == {("PUT", "/api/auditoria/config")}, escrita_auditoria
    for metodo, caminho in (("DELETE", f"/api/auditoria/{alvo}"), ("POST", "/api/auditoria/expurgar"),
                            ("DELETE", "/api/auditoria")):
        resp = sessao_a.request(metodo, caminho, json={})
        assert resp.status_code in (404, 405), (metodo, caminho, resp.status_code)

    # (b) por SQL como plat_app
    with conexao_plat_app.cursor() as cur:
        with pytest.raises(psycopg2.errors.InsufficientPrivilege):
            cur.execute("DELETE FROM plat.auditoria WHERE id = %s", (alvo,))
    conexao_plat_app.rollback()

    # (c) expurgo prematuro: a retenção não desce do piso, e a função não é chamável pela aplicação
    assert sessao_a.put("/api/auditoria/config", json={"retencao_dias": 1}).status_code == 422
    with conexao_plat_app.cursor() as cur:
        with pytest.raises(psycopg2.errors.InsufficientPrivilege):
            cur.execute("SELECT plat.auditoria_expurgar()")
    conexao_plat_app.rollback()
    # mesmo o expurgo legítimo (como postgres) não leva a linha: ela é de hoje
    _psql("SELECT auditoria_expurgar()", schema)
    ainda = sessao_a.get("/api/auditoria", params={**_janela(), "limite": 1000}).json()["itens"]
    assert any(linha["id"] == alvo for linha in ainda), "a linha do ato sumiu depois do expurgo"
