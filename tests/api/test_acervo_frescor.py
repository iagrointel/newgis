"""Verificação periódica de frescor do acervo (item L6-01-h-frescor-verificacao; migração
20260906T1617_acervo_frescor.sql; job `app/acervo/tarefas.py`; rotas `app/acervo/rotas_frescor.py`).

Portão, cláusula por cláusula, e o teste que prova cada uma:
  a) "job cobre as camadas expostas em ≤ 30 min"  → test_job_cobre_as_camadas_expostas_dentro_do_prazo
  b) "aviso aparece para uma fonte forçada a vencida (teste)" → test_endpoint_derrubado_acende_o_aviso
     (é também a refutação exigida: "adversário derruba um endpoint na fixture e confere o aviso")
  c) "histórico de 12 verificações por camada" → test_historico_mantem_doze_verificacoes_por_camada

O job roda aqui pelo `ContextoJob` de verdade, contra uma linha de `plat.job` de verdade em estado `rodando`
(o `ctx.progresso` chama `plat.job_progresso`, que exige isso) — nada de contexto de mentira: o que se está a
medir é o tempo e o efeito no banco, e os dois só valem com o caminho real.
"""

import os
import subprocess
import time
import uuid

import psycopg2
import pytest

pytestmark = pytest.mark.lento

ITEM = "L6-01-h-frescor-verificacao"
PLATAFORMA = "plataforma"


# ---------------------------------------------------------------- apoio
def _schema() -> str:
    return os.environ.get("PLAT_SCHEMA", "plat")


def _sql(texto: str) -> str:
    """A suíte roda contra o schema do AMBIENTE (base por trilha, homologação ou produção): o SQL cru é escrito
    com `plat.` e reescrito aqui pela MESMA função do app — nunca por um replace ingênuo, que trocaria também
    a chave de configuração `plat.tenant_id` dentro de `set_config`/`current_setting` (GUC de sessão, não é
    objeto de schema) e faria o contexto de inquilino sumir sem erro nenhum."""
    from app.schema_ambiente import reescrever_schema

    return reescrever_schema(texto, schema=_schema(),
                             schema_trabalho=os.environ.get("PLAT_SCHEMA_TRABALHO", "plat_trabalho"))


def _psql(sql: str, tenant_slug: str | None = None, esperar_erro: bool = False) -> tuple[list[list[str]], str]:
    """Roda SQL como `postgres` (o usuário do teste é `dev` e não tem entrada em pg_hba para este banco; é o
    mesmo caminho que `tests/api/test_acervo_camada.py` já usa para chamar scripts/acervo_sync.py).
    `tenant_slug` define `plat.tenant_id` da SESSÃO antes do resto — é assim que se entra no contexto do
    inquilino técnico para chamar as funções SECURITY DEFINER."""
    prefixo = ""
    if tenant_slug:
        prefixo = _sql(f"SELECT set_config('plat.tenant_id', "
                       f"(SELECT id::text FROM plat.tenant WHERE slug = '{tenant_slug}'), false); ")
    r = subprocess.run(
        ["sudo", "-u", "postgres", "psql", "-d", "iagro_sat", "-X", "-At", "-F", "|", "-q",
         "-v", "ON_ERROR_STOP=1", "-c", prefixo + _sql(sql)],
        capture_output=True, text=True, timeout=1200,
    )
    if esperar_erro:
        assert r.returncode != 0, f"esperava erro e o comando passou: {sql}\n{r.stdout}"
        return [], r.stderr
    assert r.returncode == 0, f"{sql}\n{r.stderr}"
    linhas = [linha.split("|") for linha in r.stdout.strip().splitlines() if linha != ""]
    if tenant_slug and linhas:
        linhas = linhas[1:]  # a primeira linha é o retorno do set_config
    return linhas, r.stderr


def _um(sql: str, tenant_slug: str | None = None) -> str:
    linhas, _ = _psql(sql, tenant_slug)
    assert linhas, sql
    return linhas[0][0]


def _contexto_job(tipo: str = "acervo.frescor_verificar"):
    """Cria uma linha de job em `rodando` (como postgres, no inquilino técnico) e devolve o ContextoJob que a
    tarefa recebe de verdade — `ctx.progresso` chama `plat.job_progresso`, que exige job rodando neste worker."""
    from pathlib import Path as _Path

    from app.jobs.contexto_job import ContextoJob

    jid = str(uuid.uuid4())
    tenant = int(_um("SELECT id FROM plat.tenant WHERE slug = 'plataforma'"))
    # o gatilho `plat.job_transicao` (006) exige que o job NASÇA pendente e que a ida para `rodando` passe pelo
    # worker: por isso o INSERT é pendente e o UPDATE roda com `plat.via_worker` ligado, exatamente como o
    # worker de verdade faz. Sem isto o teste estaria furando a própria trava que a casa criou em T2.
    _psql(f"INSERT INTO plat.job(id, tenant_id, usuario_id, tipo, parametros, pesado, memoria_mb, timeout_s, "
          f"max_tentativas) VALUES ('{jid}'::uuid, {tenant}, NULL, '{tipo}', '{{}}'::jsonb, false, 256, 2400, 1); "
          f"SELECT plat.via_worker_ligar(); "
          f"UPDATE plat.job SET estado = 'rodando', worker = 'teste-t4fres', iniciado_em = now() "
          f"WHERE id = '{jid}'::uuid")
    dir_trabalho = _Path("/tmp") / f"plat-teste-{jid}"
    dir_trabalho.mkdir(parents=True, exist_ok=True)
    return ContextoJob({"id": jid, "tenant_id": tenant, "tipo": tipo}, dir_trabalho, "teste-t4fres"), jid


def _limpar_job(jid: str) -> None:
    _psql(f"UPDATE plat.job SET estado = 'concluido', terminado_em = now() WHERE id = '{jid}'::uuid")


def _camadas_expostas() -> int:
    return int(_um("SELECT count(*) FROM plat.acervo_camada WHERE estado = 'exposta'"))


@pytest.fixture(scope="module")
def registro_populado():
    """O registro de camadas (`plat.acervo_camada`, item L6-01-a) tem de estar populado nesta base — quem o
    escreve é `scripts/acervo_sync.py`, rodando como postgres. Sem ele não há o que verificar, e o teste diz
    isso em vez de passar vazio."""
    n = _camadas_expostas()
    if n == 0:
        pytest.skip("plat.acervo_camada sem camada exposta nesta base; rode "
                    "`sudo -u postgres python3 scripts/acervo_sync.py --schema $PLAT_SCHEMA --limite 120`")
    return n


# ---------------------------------------------------------------- a) prazo de 30 min
def test_job_cobre_as_camadas_expostas_dentro_do_prazo(env, registro_populado, medida):
    """Portão: 'job cobre as camadas expostas em ≤ 30 min'. Roda SEM teste de rede (limite_endpoints=0): o
    prazo do portão é do trabalho de banco, e misturar latência de órgão público nesta medida transformaria o
    número numa medida da internet. O teste HTTP tem medida própria, mais abaixo."""
    from app.acervo.tarefas import acervo_frescor_verificar

    expostas = _camadas_expostas()
    ctx, jid = _contexto_job()
    try:
        inicio = time.monotonic()
        r = acervo_frescor_verificar(ctx, limite_endpoints=0, intervalo_dias=0)
        duracao = time.monotonic() - inicio
    finally:
        _limpar_job(jid)

    assert r["camadas_candidatas"] == expostas, (r, expostas)
    assert r["camadas_verificadas"] == expostas, "o prazo interno cortou antes de cobrir todas as expostas"
    assert duracao <= 1800, f"{duracao / 60:.1f} min > 30 min"

    gravar = medida(ITEM)
    gravar("camadas_expostas", expostas, "camadas",
           "SELECT count(*) FROM plat.acervo_camada WHERE estado = 'exposta'")
    gravar("camadas_cobertas_pelo_job", r["camadas_verificadas"], "camadas",
           "retorno de acervo.frescor_verificar (tests/api/test_acervo_frescor.py)")
    gravar("duracao_do_job_min", round(duracao / 60, 2), "min",
           "time.monotonic() em volta de acervo_frescor_verificar(limite_endpoints=0, intervalo_dias=0)")
    gravar("camadas_nao_contadas_no_prazo", r["camadas_nao_contadas"], "camadas",
           "contagem_estado <> 'contado' na rodada (COUNT(*) que estourou 25 s), nunca zero por omissão")
    gravar("camadas_com_variacao_acima_de_5pct", r["mudancas"], "camadas",
           "mudanca_relevante = true na rodada (|variacao_pct| > 5 contra a verificação anterior)")


# ---------------------------------------------------------------- b) aviso / refutação
def _camada_exposta_com_endpoint() -> tuple[str, str, str] | None:
    linhas, _ = _psql("SELECT c.acervo_camada_id, c.fonte_id, e.url FROM plat.acervo_camada c "
                      "JOIN plat.acervo_endpoint e ON e.fonte_id = c.fonte_id "
                      "WHERE c.estado = 'exposta' LIMIT 1")
    return tuple(linhas[0]) if linhas else None


def _camada_exposta() -> tuple[str, str]:
    linhas, _ = _psql("SELECT acervo_camada_id, fonte_id FROM plat.acervo_camada WHERE estado = 'exposta' "
                      "ORDER BY acervo_camada_id LIMIT 1")
    return tuple(linhas[0])


def _registrar_endpoint(fonte_id: str, url: str, respondeu: bool) -> None:
    estado = "true" if respondeu else "false"
    status = "NULL" if respondeu else "503"
    msg = "ok" if respondeu else "derrubado pela fixture do teste"
    _psql(f"SELECT plat.acervo_frescor_registrar_endpoint(NULL, $q${fonte_id}$q$, $q${url}$q$, {estado}, "
          f"{status}, $q${msg}$q$, 5, 12)", tenant_slug=PLATAFORMA)


def test_endpoint_derrubado_acende_o_aviso(env, registro_populado, sessao_a):
    """Portão: 'aviso aparece para uma fonte forçada a vencida (teste)'. É também a refutação exigida do item:
    o endereço é derrubado NA FIXTURE (uma verificação HTTP que não respondeu, gravada na tabela da
    plataforma — `acervo.endpoint`, que é da casa, não é tocada), e o aviso tem de aparecer na ficha e na
    lista que o mapa consome. Depois o endereço volta a responder e o aviso tem de SUMIR: aviso que nunca
    apaga não é aviso, é enfeite."""
    alvo = _camada_exposta_com_endpoint()
    if alvo is None:
        pytest.skip("nenhuma camada exposta tem endereço confirmado em acervo.endpoint nesta base")
    camada_id, fonte_id, url = alvo
    _registrar_endpoint(fonte_id, url, respondeu=False)

    r = sessao_a.get(f"/api/acervo/camadas?fonte_id={fonte_id}")
    assert r.status_code == 200, r.text
    linha = next(i for i in r.json()["itens"] if i["acervo_camada_id"] == camada_id)
    assert linha["verificacao_vencida"] is True, linha
    assert linha["motivo_vencida"] == "endpoint_morto", linha
    assert linha["endpoints_mortos"] >= 1, linha

    # a ficha da fonte mostra o mesmo aviso, agregado das camadas expostas dela
    f = sessao_a.get(f"/api/acervo/{fonte_id}")
    assert f.status_code == 200, f.text
    assert f.json()["verificacao_vencida"] is True, f.json()
    assert f.json()["motivo_vencida"] == "endpoint_morto"
    assert f.json()["camadas_vencidas"] >= 1

    # o filtro que a tela usa ("só as com verificação vencida") traz a camada
    v = sessao_a.get("/api/acervo/camadas?vencida=true&limite=200")
    assert v.status_code == 200
    assert any(i["acervo_camada_id"] == camada_id for i in v.json()["itens"])

    # o endereço volta a responder: o aviso por endpoint morto tem de apagar
    _registrar_endpoint(fonte_id, url, respondeu=True)
    r2 = sessao_a.get(f"/api/acervo/camadas?fonte_id={fonte_id}")
    linha2 = next(i for i in r2.json()["itens"] if i["acervo_camada_id"] == camada_id)
    assert linha2["endpoints_mortos"] == 0, linha2
    assert linha2["motivo_vencida"] != "endpoint_morto", linha2


def test_camada_nunca_verificada_ja_nasce_com_aviso(env, registro_populado, sessao_a):
    """Ausência de verificação NÃO é 'em dia'. Uma camada que o job nunca visitou aparece vencida, com o
    motivo `nunca_verificada` — é a mesma regra da casa: ausência de medição nunca vira medição boa."""
    camada_id, fonte_id = _camada_exposta()
    _psql(f"DELETE FROM plat.acervo_camada_verificacao WHERE acervo_camada_id = $q${camada_id}$q$; "
          f"DELETE FROM plat.acervo_endpoint_verificacao WHERE fonte_id = $q${fonte_id}$q$")
    r = sessao_a.get(f"/api/acervo/camadas?fonte_id={fonte_id}")
    linha = next(i for i in r.json()["itens"] if i["acervo_camada_id"] == camada_id)
    assert linha["verificacao_vencida"] is True
    assert linha["motivo_vencida"] == "nunca_verificada", linha
    assert linha["nunca_verificada"] is True


# ---------------------------------------------------------------- c) histórico de 12
def _registrar_camada(camada_id: str, linhas: int | None = None, contagem: str = "contado",
                      hash_estado: str = "sem_comando") -> list[str]:
    valor = "NULL" if linhas is None else str(linhas)
    r, _ = _psql(f"SELECT variacao_pct, mudanca_relevante, historico FROM "
                 f"plat.acervo_frescor_registrar_camada(NULL, $q${camada_id}$q$, '{contagem}', {valor}, "
                 f"'{hash_estado}', NULL, NULL, 1, 12)", tenant_slug=PLATAFORMA)
    return r[0]


def test_historico_mantem_doze_verificacoes_por_camada(env, registro_populado, sessao_a, medida):
    """Portão: 'histórico de 12 verificações por camada'. Grava 15 verificações na mesma camada e confere que
    ficam exatamente 12, as mais recentes — a poda é da própria função que grava, não de um expurgo à parte
    que possa não rodar."""
    camada_id, _fonte = _camada_exposta()
    _psql(f"DELETE FROM plat.acervo_camada_verificacao WHERE acervo_camada_id = $q${camada_id}$q$")
    historico = "0"
    for n in range(15):
        historico = _registrar_camada(camada_id, 1000 + n)[2]

    linhas, _ = _psql("SELECT count(*), min(linhas_exatas), max(linhas_exatas) "
                      f"FROM plat.acervo_camada_verificacao WHERE acervo_camada_id = $q${camada_id}$q$")
    n, menor, maior = linhas[0]
    assert int(n) == 12, linhas
    assert int(historico) == 12
    assert int(maior) == 1014, linhas   # a última gravada ficou
    assert int(menor) == 1003, linhas   # as três mais antigas (1000-1002) foram podadas

    api = sessao_a.get(f"/api/acervo/camadas/{camada_id}/verificacoes")
    assert api.status_code == 200, api.text
    assert api.json()["total"] == 12
    medida(ITEM)("verificacoes_no_historico_por_camada", int(n), "verificações",
                 "15 chamadas a plat.acervo_frescor_registrar_camada(..., p_manter=12) seguidas de COUNT(*)")


# ---------------------------------------------------------------- contagem: prazo, nunca zero, nunca reltuples
def test_contagem_que_estoura_o_prazo_nao_vira_zero(env, registro_populado):
    """O portão do item nasce de um achado da casa (01/09): duas tabelas contadas por estimativa não existiam.
    Aqui o prazo é forçado a 1 ms para provar que o estouro vira ESTADO, não zero."""
    from app.acervo.tarefas import acervo_frescor_verificar

    ctx, jid = _contexto_job()
    try:
        r = acervo_frescor_verificar(ctx, limite_camadas=3, limite_endpoints=0, intervalo_dias=0,
                                     timeout_contagem_ms=1)
    finally:
        _limpar_job(jid)
    assert r["camadas_verificadas"] >= 1
    linhas, _ = _psql("SELECT contagem_estado, coalesce(linhas_exatas::text, 'NULO') "
                      f"FROM plat.acervo_camada_verificacao WHERE execucao_id = {r['execucao_id']}")
    assert linhas, r
    assert all(x[0] == "nao_contado_no_prazo" for x in linhas), linhas
    assert all(x[1] == "NULO" for x in linhas), "prazo estourado virou número: nunca"


def test_historico_nao_guarda_estimativa(env):
    """`reltuples` fica onde já estava rotulado (plat.acervo_camada.linhas_estimadas) e não entra no histórico
    de verificação: nenhuma coluna de estimativa existe nesta tabela."""
    linhas, _ = _psql("SELECT column_name FROM information_schema.columns "
                      f"WHERE table_schema = '{_schema()}' AND table_name = 'acervo_camada_verificacao'")
    colunas = {x[0] for x in linhas}
    assert colunas, "tabela plat.acervo_camada_verificacao ausente"
    assert not [c for c in colunas if "estimad" in c or "reltuple" in c], colunas


def test_contagem_gravada_bate_com_count_exato(env, registro_populado):
    """A contagem que vai para o histórico é o COUNT(*) da tabela de origem, não a estimativa do planejador."""
    from app.acervo.tarefas import acervo_frescor_verificar

    ctx, jid = _contexto_job()
    try:
        r = acervo_frescor_verificar(ctx, limite_camadas=5, limite_endpoints=0, intervalo_dias=0)
    finally:
        _limpar_job(jid)
    linhas, _ = _psql(
        "SELECT c.schema_nome, c.tabela, v.linhas_exatas FROM plat.acervo_camada_verificacao v "
        "JOIN plat.acervo_camada c ON c.acervo_camada_id = v.acervo_camada_id "
        f"WHERE v.execucao_id = {r['execucao_id']} AND v.contagem_estado = 'contado' LIMIT 1")
    if not linhas:
        pytest.skip("nenhuma camada foi contada dentro do prazo nesta rodada")
    schema_nome, tabela, gravado = linhas[0]
    real = _um(f'SELECT count(*) FROM "{schema_nome}"."{tabela}"')
    assert int(gravado) == int(real), (schema_nome, tabela, gravado, real)


# ---------------------------------------------------------------- trinco COM inquilino (lição do L0-05-d)
def test_trinco_da_rodada_tem_dimensao_de_inquilino(env):
    """A `chave` de `plat.job` é global (índice `ix_job_chave` da 004, sem tenant_id) — foi o que derrubou o
    L0-05-d. Este job usa `chave=None` e o trinco mora em `plat.acervo_frescor_execucao`, por inquilino:
    (1) uma rodada aberta de OUTRO inquilino não impede a do inquilino técnico; (2) a segunda rodada aberta do
    MESMO inquilino é recusada. É exatamente o que o adversário procura."""
    _psql("DELETE FROM plat.acervo_frescor_execucao WHERE concluida_em IS NULL")
    vizinho = _um("INSERT INTO plat.acervo_frescor_execucao(tenant_id) "
                  "SELECT id FROM plat.tenant WHERE slug <> 'plataforma' ORDER BY id LIMIT 1 RETURNING id")
    minha = _um("SELECT plat.acervo_frescor_abrir()", tenant_slug=PLATAFORMA)
    assert minha != vizinho and int(minha) > 0
    _, erro = _psql("SELECT plat.acervo_frescor_abrir()", tenant_slug=PLATAFORMA, esperar_erro=True)
    assert "ja existe uma rodada de frescor aberta neste inquilino" in erro, erro
    _psql("DELETE FROM plat.acervo_frescor_execucao WHERE concluida_em IS NULL")


def test_funcoes_de_escrita_recusam_inquilino_comum(env):
    """As funções SECURITY DEFINER só rodam no inquilino técnico `plataforma` (mesmo padrão de
    `plat.jobs_expurgar` e `plat.conexao_saude_candidatas`). Um inquilino comum não abre rodada, não grava
    verificação e não conta tabela de origem."""
    for chamada in ("plat.acervo_frescor_abrir()",
                    "plat.acervo_camada_contar('qualquer/publico.qualquer')",
                    "plat.acervo_frescor_registrar_endpoint(NULL, 'f', 'https://exemplo.invalido', true, "
                    "200, NULL, 1)",
                    "plat.acervo_frescor_candidatas('1 day'::interval, 1)"):
        _, erro = _psql(f"SELECT * FROM {chamada}" if "candidatas" in chamada else f"SELECT {chamada}",
                        tenant_slug="demo", esperar_erro=True)
        assert "inquilino tecnico plataforma" in erro, (chamada, erro)


def test_plat_app_nao_escreve_nas_tabelas_de_verificacao(env, conexao_plat_app):
    """`plat_app` só LÊ o registro do acervo e o histórico de verificação (mesma regra de plat.acervo_camada
    na 027): quem grava é a função SECURITY DEFINER, chamada pelo job no inquilino técnico."""
    for tabela in ("acervo_camada_verificacao", "acervo_endpoint_verificacao", "acervo_frescor_execucao"):
        with conexao_plat_app.cursor() as cur, pytest.raises(psycopg2.errors.InsufficientPrivilege):
            cur.execute(f"INSERT INTO plat.{tabela} DEFAULT VALUES")
        conexao_plat_app.rollback()


# ---------------------------------------------------------------- relatório de mudanças
def test_relatorio_de_mudancas_lista_variacao_acima_de_cinco_por_cento(env, registro_populado, sessao_a):
    """Duas verificações seguidas da mesma camada, 1.020 → 1.224 linhas (+20 %), entram no relatório; uma
    variação de +2 % não entra. O limiar de 5 % é o da hipótese do item e está escrito na função que grava."""
    camada_id, _fonte = _camada_exposta()
    _psql(f"DELETE FROM plat.acervo_camada_verificacao WHERE acervo_camada_id = $q${camada_id}$q$")
    _registrar_camada(camada_id, 1000)
    pequena = _registrar_camada(camada_id, 1020)          # +2 %: não é mudança relevante
    assert pequena[1] == "f", pequena
    grande = _registrar_camada(camada_id, 1224)           # +20 %
    assert grande[1] == "t", grande
    assert float(grande[0]) == pytest.approx(20.0, abs=0.01)

    r = sessao_a.get("/api/acervo/frescor/mudancas?limite=200")
    assert r.status_code == 200, r.text
    assert r.json()["limiar_pct"] == 5.0
    assert any(i["acervo_camada_id"] == camada_id for i in r.json()["itens"]), r.json()


def test_variacao_nao_existe_sem_as_duas_contagens(env, registro_populado):
    """Uma verificação sem contagem (prazo estourado) não gera variação de 0 % nem de −100 %: gera vazio."""
    camada_id, _fonte = _camada_exposta()
    _psql(f"DELETE FROM plat.acervo_camada_verificacao WHERE acervo_camada_id = $q${camada_id}$q$")
    _registrar_camada(camada_id, 500)
    r = _registrar_camada(camada_id, None, contagem="nao_contado_no_prazo",
                          hash_estado="nao_recalculado_sem_contagem")
    assert r[0] == "", r        # variacao_pct nula
    assert r[1] == "f", r


# ---------------------------------------------------------------- teste HTTP de verdade (dezenas, não varredura)
def test_endpoints_testados_por_http_de_verdade(env, registro_populado, medida):
    """Teste HTTP real contra os endereços que a casa já confirmou, com teto de 10 por rodada — dezenas, nunca
    uma varredura em massa contra órgão público. O que se prova aqui é que o job MEDE de verdade: quantos
    endereços foram testados e quantos responderam, com o resultado gravado por endereço."""
    from app.acervo.tarefas import acervo_frescor_verificar

    ctx, jid = _contexto_job()
    try:
        r = acervo_frescor_verificar(ctx, limite_camadas=1, limite_endpoints=10, intervalo_dias=0)
    finally:
        _limpar_job(jid)
    if r["endpoints_testados"] == 0:
        pytest.skip("nenhum endereço confirmado para camada exposta nesta base")
    linhas, _ = _psql("SELECT count(*), count(*) FILTER (WHERE respondeu) "
                      f"FROM plat.acervo_endpoint_verificacao WHERE execucao_id = {r['execucao_id']}")
    assert int(linhas[0][0]) == r["endpoints_testados"]
    assert int(linhas[0][1]) == r["endpoints_responderam"]
    gravar = medida(ITEM)
    gravar("endpoints_testados_por_http", r["endpoints_testados"], "endereços",
           "acervo.frescor_verificar(limite_endpoints=10) contra os endereços confirmados de acervo.endpoint")
    gravar("endpoints_que_responderam", r["endpoints_responderam"], "endereços",
           "buscar_seguro (app/conexao/seguranca.py) com User-Agent da plataforma; resposta HTTP com ok=true")
