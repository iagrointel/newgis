"""TRAVA da classe "função privilegiada sem dimensão de inquilino" (varredura das 102 funções SECURITY
DEFINER do schema `plat`, 06/09/2026 — `laco/handoffs/T3/VARREDURA-funcoes-privilegiadas.md`, ADR 0018).

Dois adversários independentes acharam o MESMO defeito em grupos diferentes:
`plat.item_versoes_compactar` apagou versão de item de OUTRO inquilino (laudo G2, achados G2-1/G2-2) e
`plat.evento_expurgar(-1)` derrubou a partição do mês e zerou a auditoria de todos os inquilinos (laudo
G4, achado G4-10). Um terceiro achou a causa da outra metade: migração que cria função e não revoga de
PUBLIC (laudo G1). Dois achados iguais em grupos diferentes é classe, não caso.

Este arquivo não reencena os ataques (isso está em `test_funcoes_seguras.py` e nos arquivos dos
adversários): ele varre `pg_proc` e `db/migracoes/` e reprova FUNÇÃO NOVA que repita a classe.

Para acrescentar qualquer nome às listas abaixo é obrigatório escrever a justificativa na mesma
entrada: lista sem justificativa é lista que cresce sozinha."""

import re
from pathlib import Path

import psycopg2
import pytest

from tests.api.test_rls import contexto, ids_por_slug

RAIZ = Path(__file__).resolve().parents[2]
MIGRACOES = RAIZ / "db" / "migracoes"

# ---------------------------------------------------------------------------- exceções declaradas

# EXECUTE para PUBLIC. Hoje: nenhuma justificada. `iagro_sat` é um banco COMPARTILHADO com outros
# projetos da casa, cada um com o seu papel — PUBLIC aqui quer dizer "todo papel do banco", não
# "usuário anônimo da web" (esse chega pelo papel plat_app, como qualquer outro).
PUBLICO_JUSTIFICADO: dict[str, str] = {}

# SECURITY DEFINER que recebe o inquilino por argumento e não o compara com o contexto.
# Só entra função que roda ANTES de existir contexto de inquilino, e o motivo fica escrito aqui.
SEM_COMPARACAO_JUSTIFICADO: dict[str, str] = {
    "auth_login": "resolve (slug, login) para autenticar: roda antes de haver sessão,"
                  " logo não há contexto a comparar",
    "log_registrar": "já compara à mão (levanta contexto_de_outro_inquilino) e precisa gravar"
                     " acesso anônimo, sem contexto",
    "tenant_permite_publico": "lê uma bandeira booleana de configuração; o caminho anônimo de"
                              " compartilhamento a chama sem contexto, por item de outro inquilino",
    "cota_jobs_dia": "lê um número de configuração; quem chama é o worker (plat_worker), que roda sem contexto",
    "cota_jobs_simultaneos": "idem: plat.job_pegar a chama dentro do worker, por inquilino do job",
    "jobs_no_dia": "conta job do inquilino do argumento; EXECUTE só para plat_worker, que roda sem contexto",
    "inquilino_do_argumento": "É a própria guarda desta trava (ver ADR 0018)",
}

# Dívida LEGADA da regra "quem cria função revoga de PUBLIC no mesmo arquivo": as migrações `NNN_` estão
# fechadas e são imutáveis (ADR 0014), então cada entrada aponta o arquivo que PAGOU a dívida depois.
# Este dicionário é congelado: o teste reprova tanto quem entra quanto quem sai sem consertar.
DIVIDA_LEGADA: dict[str, str] = {
    "001_fundacao.sql": "pago por 003_identidade_acesso.sql (REVOKE ON ALL FUNCTIONS FROM PUBLIC)",
    "002_identidade.sql": "pago por 003_identidade_acesso.sql (REVOKE ON ALL FUNCTIONS)",
    "004_jobs.sql": "pago por 013_jobs_execute_reafirma.sql (REVOKE por função, PUBLIC e plat_app)",
    "022_arquivos.sql": "pago por 024_arquivos_revoke_public.sql (REVOKE por função)",
    "029_ingestao_vetor.sql": "pago por 033_ingestao_funcoes_privilegios.sql (REVOKE por função)",
    "030_conexao.sql": "esquecido: pago por 20260906T1601_funcoes_privilegiadas_isolamento.sql",
    "046_upload_retomavel.sql": "esquecido: pago por 20260906T1601_funcoes_privilegiadas_isolamento.sql",
    "047_smtp_convites_redefinicao.sql": "esquecido: pago por 048_smtp_convites_correcoes.sql"
                                         " e por 049_convite_resolver_config.sql",
}

# ---------------------------------------------------------------------------- varredura de pg_proc

ARG_INQUILINO = re.compile(r"\b(p_tenant|p_tenant_id|p_inquilino|p_inquilino_id)\b")
# o `plat.` do prefixo é opcional porque a mesma suíte roda contra o schema de homologação e contra o schema
# de cada trilha (`plat_thomolog`, `plat_tsecdef`, ...): o corpo gravado no catálogo leva o nome reescrito
COMPARA_INQUILINO = re.compile(
    r"(?:\bplat[a-z0-9_]*\.)?(?:tenant_atual\(\)|inquilino_do_argumento|inquilino_do_slug"
    r"|so_manutencao|contexto_confere|plataforma_operador)"
    r"|current_setting\(\s*'plat\.tenant"
)


def _funcoes(cur) -> list[dict]:
    """Todas as funções do schema (o cursor da suíte reescreve `plat` para o schema do ambiente)."""
    cur.execute("""
        SELECT p.proname, p.prosecdef, p.prosrc, pg_get_function_arguments(p.oid) AS args,
               coalesce(array_to_string(p.proacl, ' '), '(padrao: PUBLIC)') AS acl,
               (p.proacl IS NULL
                OR EXISTS (SELECT 1 FROM unnest(p.proacl) a WHERE a::text LIKE '=%')) AS publico
        FROM pg_proc p WHERE p.pronamespace = 'plat'::regnamespace ORDER BY p.proname""")
    return cur.fetchall()


def test_definidor_de_seguranca_com_inquilino_no_argumento_compara_o_contexto(conexao_plat_app):
    """Trava 1. SECURITY DEFINER roda como o dono, FORA da RLS: se o alvo vem por argumento, quem
    compara com `plat.tenant_atual()` é a própria função. Foi a falta disto que deixou
    `item_versoes_compactar` apagar versão de item de outro inquilino."""
    with conexao_plat_app.cursor() as cur:
        funcoes = _funcoes(cur)
    assert len(funcoes) >= 100, f"varredura pequena demais ({len(funcoes)} funções): schema errado?"
    faltando = []
    for f in funcoes:
        if not f["prosecdef"] or not ARG_INQUILINO.search(f["args"] or ""):
            continue
        if COMPARA_INQUILINO.search(f["prosrc"] or ""):
            continue
        if f["proname"] in SEM_COMPARACAO_JUSTIFICADO:
            assert SEM_COMPARACAO_JUSTIFICADO[f["proname"]].strip(), f["proname"]
            continue
        faltando.append(f"{f['proname']}({f['args']})")
    assert faltando == [], (
        "função SECURITY DEFINER recebe o inquilino por argumento e não compara com o contexto. "
        "Use `plat.inquilino_do_argumento(p_tenant)` na cláusula que escolhe a linha (ou "
        "`plat.so_manutencao(...)`, se for expurgo global), ou declare a exceção com justificativa em "
        f"SEM_COMPARACAO_JUSTIFICADO: {faltando}"
    )


def test_nenhuma_funcao_do_schema_com_execute_para_public(conexao_plat_app):
    """Trava 2. Mesma asserção de `test_funcoes_seguras.py`, aqui com a lista de exceções explícita:
    quem precisar de PUBLIC escreve por quê, em vez de a lista crescer no silêncio."""
    with conexao_plat_app.cursor() as cur:
        funcoes = _funcoes(cur)
    sobrando = [
        f"{f['proname']} :: {f['acl']}"
        for f in funcoes
        if f["publico"] and not (PUBLICO_JUSTIFICADO.get(f["proname"]) or "").strip()
    ]
    assert sobrando == [], (
        "função do schema com EXECUTE para PUBLIC num banco compartilhado com outros projetos da casa: "
        f"REVOKE EXECUTE ... FROM PUBLIC na migração, ou justifique em PUBLICO_JUSTIFICADO: {sobrando}"
    )


# ---------------------------------------------------------------------------- varredura das migrações

_CRIA = re.compile(r"CREATE\s+(?:OR\s+REPLACE\s+)?FUNCTION\s+plat\.([a-z0-9_]+)", re.I)
_REVOGA = re.compile(r"REVOKE\s+(?:EXECUTE|ALL)\s+ON\s+FUNCTION\s+plat\.([a-z0-9_]+)[^;]*FROM[^;]*PUBLIC", re.I | re.S)
_REVOGA_TODAS = re.compile(r"REVOKE\s+EXECUTE\s+ON\s+ALL\s+FUNCTIONS[^;]*FROM[^;]*PUBLIC", re.I | re.S)
_REVOGA_EM_LACO = re.compile(r"format\(\s*'REVOKE[^']*FROM[^']*PUBLIC", re.I)
_LITERAL = re.compile(r"'plat\.([a-z0-9_]+)\s*\(")
_LEGADO = re.compile(r"^\d{3}_")


def _sem_comentario(sql: str) -> str:
    return "\n".join(linha for linha in sql.splitlines() if not linha.lstrip().startswith("--"))


def _ordem(caminho: Path) -> tuple[str, str]:
    """Mesma ordem do aplicador (ADR 0014): legado `NNN_` antes de carimbo de tempo."""
    return ("0", caminho.name) if _LEGADO.match(caminho.name) else ("1", caminho.name)


def _debito_por_arquivo() -> dict[str, list[str]]:
    """{arquivo: funções criadas ALI PELA PRIMEIRA VEZ e não revogadas de PUBLIC no mesmo arquivo}."""
    vistas: set[str] = set()
    debito: dict[str, list[str]] = {}
    for arq in sorted(MIGRACOES.glob("*.sql"), key=_ordem):
        sql = _sem_comentario(arq.read_text(encoding="utf-8"))
        criadas = set(_CRIA.findall(sql))
        novas = criadas - vistas
        vistas |= criadas
        if not novas:
            continue
        revogadas = set(_REVOGA.findall(sql))
        if _REVOGA_TODAS.search(sql):
            revogadas |= criadas
        if _REVOGA_EM_LACO.search(sql):
            revogadas |= set(_LITERAL.findall(sql))
        falta = sorted(novas - revogadas)
        if falta:
            debito[arq.name] = falta
    return debito


def test_migracao_nova_revoga_do_publico_a_funcao_que_cria():
    """Trava 3, a causa medida (laudo G1). A 047 criou seis funções de convite/redefinição e não revogou
    de PUBLIC; num banco compartilhado isso deixou seis SECURITY DEFINER executáveis por todo papel, e
    ninguém viu porque as duas asserções que guardavam a regra já estavam vermelhas. A regra passa a ser
    verificada no ARQUIVO: quem cria função em `plat` revoga de PUBLIC no MESMO arquivo. As migrações
    `NNN_` estão fechadas (ADR 0014) e a dívida delas está congelada em DIVIDA_LEGADA, cada uma com o
    arquivo que a pagou."""
    debito = _debito_por_arquivo()
    novas = {a: f for a, f in debito.items() if not _LEGADO.match(a)}
    assert novas == {}, (
        "migração nova cria função em plat sem REVOKE EXECUTE ... FROM PUBLIC no mesmo arquivo "
        f"(ADR 0018): {novas}"
    )
    legado = {a for a in debito if _LEGADO.match(a)}
    assert legado == set(DIVIDA_LEGADA), (
        "a dívida legada mudou. Entrou arquivo novo na lista (não deveria: `NNN_` está fechado) ou saiu "
        f"sem alguém atualizar DIVIDA_LEGADA. medido={sorted(legado)} declarado={sorted(DIVIDA_LEGADA)}"
    )
    for arq, quem_pagou in DIVIDA_LEGADA.items():
        assert quem_pagou.strip(), f"{arq} sem o arquivo que paga a dívida"


@pytest.mark.parametrize("arquivo", sorted(MIGRACOES.glob("*.sql"), key=_ordem), ids=lambda p: p.name)
def test_migracao_que_concede_execucao_tambem_revoga_do_publico(arquivo: Path):
    """Trava 3b. `GRANT EXECUTE ... TO plat_app` sem o `REVOKE ... FROM PUBLIC` ao lado dá a impressão de
    que a permissão foi fechada quando não foi: plat_app ganha o que já tinha por PUBLIC."""
    sql = _sem_comentario(arquivo.read_text(encoding="utf-8"))
    concedidas = set(re.findall(r"GRANT\s+EXECUTE\s+ON\s+FUNCTION\s+plat\.([a-z0-9_]+)", sql, re.I))
    if not concedidas:
        pytest.skip("migração sem GRANT EXECUTE por função")
    revogadas = set(_REVOGA.findall(sql))
    if _REVOGA_TODAS.search(sql):
        revogadas |= concedidas
    if _REVOGA_EM_LACO.search(sql):
        revogadas |= set(_LITERAL.findall(sql))
    falta = sorted(concedidas - revogadas)
    if _LEGADO.match(arquivo.name):
        pytest.skip(f"legado fechado (ADR 0014); dívida em DIVIDA_LEGADA: {falta}")
    assert falta == [], (
        f"{arquivo.name}: GRANT EXECUTE sem o REVOKE ... FROM PUBLIC da mesma função {falta} (ADR 0018)"
    )


# ---------------------------------------------------------------------------- os dois ataques medidos

def test_guarda_de_inquilino_recusa_alvo_de_outro_inquilino(conexao_plat_app):
    """Reencena, no nível do banco, o que os dois laudos mediram: a mesma chamada que antes passava agora
    levanta `contexto_de_outro_inquilino`. Cobre os três caminhos da guarda (por id, por slug, expurgo
    global) e o piso de argumento."""
    ids = ids_por_slug(conexao_plat_app)
    contexto(conexao_plat_app, ids["demo"], usuario_id=0)
    casos = [
        ("SELECT plat.inquilino_do_argumento(%s)", (ids["demo2"],), "contexto_de_outro_inquilino"),
        ("SELECT * FROM plat.arquivo_bucket_por_tenant(%s)", (ids["demo2"],), "contexto_de_outro_inquilino"),
        ("SELECT plat.catalogo_uso(%s)", (ids["demo2"],), "contexto_de_outro_inquilino"),
        ("SELECT plat.usuarios_ativos(%s)", (ids["demo2"],), "contexto_de_outro_inquilino"),
        ("SELECT plat.cota_usuarios(%s)", (ids["demo2"],), "contexto_de_outro_inquilino"),
        ("SELECT * FROM plat.arquivo_bucket_resolver(%s)", ("demo2",), "contexto_de_outro_inquilino"),
        ("SELECT * FROM plat.provedor_ldap_de(%s)", ("demo2",), "contexto_de_outro_inquilino"),
        ("SELECT plat.inquilino_do_argumento(%s)", (None,), "inquilino_argumento_nulo"),
    ]
    for sql, args, esperado in casos:
        with conexao_plat_app.cursor() as cur:
            with pytest.raises(psycopg2.errors.RaiseException, match=esperado):
                cur.execute(sql, args)
        conexao_plat_app.rollback()
        contexto(conexao_plat_app, ids["demo"], usuario_id=0)


def test_expurgo_global_recusa_contexto_de_inquilino_e_argumento_absurdo(conexao_plat_app):
    """G4-10: `plat.evento_expurgar(-1)` derrubava a partição do mês e zerava a auditoria de todos. Duas
    barreiras agora: contexto (só sem inquilino ou sob `plataforma`) e piso do argumento."""
    ids = ids_por_slug(conexao_plat_app)
    contexto(conexao_plat_app, ids["demo"], usuario_id=0)
    for sql in ("SELECT plat.evento_expurgar(-1)", "SELECT plat.log_expurgar(-1)",
                "SELECT plat.sessoes_expurgar()", "SELECT * FROM plat.uploads_expirar_candidatos(24)"):
        with conexao_plat_app.cursor() as cur:
            with pytest.raises(psycopg2.errors.InsufficientPrivilege):
                cur.execute(sql)
        conexao_plat_app.rollback()
        contexto(conexao_plat_app, ids["demo"], usuario_id=0)
    conexao_plat_app.rollback()
    # sem contexto de inquilino a barreira que sobra é a do argumento
    for sql in ("SELECT plat.evento_expurgar(-1)", "SELECT plat.log_expurgar(0)",
                "SELECT * FROM plat.uploads_expirar_candidatos(-5)"):
        with conexao_plat_app.cursor() as cur:
            with pytest.raises(psycopg2.errors.RaiseException, match="argumento_invalido"):
                cur.execute(sql)
        conexao_plat_app.rollback()


def test_versoes_compactar_nao_apaga_versao_de_outro_inquilino(conexao_plat_app, sessao_b):
    """G2-1/G2-2 medido: no contexto de A, a função apagou 2 linhas de `plat.item_versao` de um item de B.
    Agora devolve 0 e a contagem de versões do item de B não muda. O item é criado e editado pela API de B
    (nada de escrever direto no banco), e apagado no fim."""
    corpo = {"tipo": "mapa", "titulo": "zt-secdef alvo", "dados": {"esquema_versao": 1, "corpo": {}}}
    criado = sessao_b.post("/api/itens", json=corpo)
    assert criado.status_code == 201, criado.text
    alvo = criado.json()["id"]
    try:
        for i in range(4):
            novo = {"titulo": f"zt-secdef alvo {i}", "dados": {"esquema_versao": 1, "corpo": {"n": i}}}
            r = sessao_b.put(f"/api/itens/{alvo}", json=novo)
            assert r.status_code == 200, r.text
        ids = ids_por_slug(conexao_plat_app)
        with conexao_plat_app.cursor() as cur:   # a RLS de item_versao passa por pode_ler: precisa do usuário
            cur.execute("SELECT usuario_id FROM plat.auth_login('demo2', 'admin')")
            adm_b = cur.fetchone()["usuario_id"]
        contexto(conexao_plat_app, ids["demo2"], usuario_id=adm_b, login="admin")
        with conexao_plat_app.cursor() as cur:
            cur.execute("SELECT count(*) AS n FROM plat.item_versao WHERE item_id = %s::uuid", (alvo,))
            antes = cur.fetchone()["n"]
        assert antes >= 3, f"esperava várias versões do item de B, vi {antes}"
        conexao_plat_app.rollback()

        contexto(conexao_plat_app, ids["demo"], usuario_id=0)   # contexto do inquilino A
        with conexao_plat_app.cursor() as cur:
            cur.execute("SELECT plat.item_versoes_compactar(%s::uuid, 1) AS n", (alvo,))
            assert cur.fetchone()["n"] == 0, "A compactou versão de item de B"
        conexao_plat_app.rollback()

        contexto(conexao_plat_app, ids["demo2"], usuario_id=adm_b, login="admin")
        with conexao_plat_app.cursor() as cur:
            cur.execute("SELECT count(*) AS n FROM plat.item_versao WHERE item_id = %s::uuid", (alvo,))
            assert cur.fetchone()["n"] == antes, "a compactação feita por A mexeu nas versões de B"
        conexao_plat_app.rollback()
    finally:
        sessao_b.delete(f"/api/itens/{alvo}")
