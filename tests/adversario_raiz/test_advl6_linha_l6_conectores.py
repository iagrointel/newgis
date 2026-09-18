"""Adversário de LINHA da L6 conectores (20 itens; laudo em
laco/handoffs/T9/linha-L6-laudo-adversario.md). Nada é consertado aqui — cada achado é um teste
`xfail(strict=True)`, determinístico e offline (sem rede, sem serviço externo real).

Achados desta rodada:
  - L6-02-j-bancos-externos: a "lista branca de SELECT" de `app.conexao.consulta_sql` só olha tabelas
    citadas depois de FROM/JOIN; uma função chamada na lista de projeção (fora de FROM/JOIN) nunca é
    conferida contra whitelist nenhuma, só contra o denylist fixo `FUNCOES_PROIBIDAS` — que é incompleto
    (a família `pg_ls_logdir/pg_ls_waldir/pg_ls_tmpdir/pg_ls_archive_statusdir`, funções de LISTAGEM DE
    ARQUIVO do servidor, não está nele, embora a Camada 1 do módulo prometa "sem função de ... arquivo").
  - L6-05-proveniencia-camada-externa: a sondagem automática de procedência lê `license` no JSON-raiz de
    um STAC, mas nunca o `links[].rel == "license"` que o próprio docstring do módulo promete
    ("STAC/OGC API: license/link rel=license") e que o ramo `ogc_api` do MESMO arquivo já implementa —
    uma coleção STAC que só declara a licença por link (comum quando `license` é `"various"` ou
    `"proprietary"`, ver o próprio spec STAC) fica com `licenca=None`, silenciosamente, sem aviso.
  - L6-01-a-registro / L6-01-f-lgpd (achado TRANSVERSAL — a mesma suposição furada nos dois): o próprio
    docstring de `scripts/acervo_sync.py` confessa que a lista negra de coluna é "GROSSA, só pelo NOME" e
    promete que "a checagem fina por CONTEÚDO (regex de CPF/CNPJ em amostra) é o item L6-01-f". Mas o que
    L6-01-f entregou foi uma curadoria MANUAL por FONTE inteira (`plat.acervo_lgpd.risco_pii`, 219 tabelas
    olhadas uma vez em 05-07/09), nunca o scanner automático por CONTEÚDO que o próprio código-fonte do
    L6-01-a diz que viria depois. E a barreira grossa por NOME já furada é fraca: `_COLUNA_NEGADA` faz
    correspondência EXATA (`c.lower() in _COLUNA_NEGADA`), então qualquer variação de nome real de
    cadastro público brasileiro — `cpf_titular`, `nr_cpf`, `proprietario_nome`, `nome_do_proprietario` —
    passa como coluna EXPOSTA em vez de bloqueada.
  - L6-02-k-agendamento: o teto de agendas ATIVAS por usuário (`agenda_criar`/`agenda_retomar` em
    app/jobs/servico.py) é "SELECT conta, compara, INSERT" na MESMA transação, sem `SELECT ... FOR
    UPDATE`, sem lock consultivo e sem constraint no banco — clássica corrida de checar-depois-agir. Duas
    conexões que fazem a MESMA leitura antes de qualquer uma commitar passam as duas pelo `n < cota` e as
    duas inserem: o teto "10 por usuário" não segura sob duas requisições simultâneas. Reproduzido aqui
    de forma determinística (sem depender de timing): as duas transações leem o mesmo `n`, a primeira
    insere e commita, a segunda insere e commita sem reler — nenhuma reordenação por acaso.

Rodar (na trilha do adversário, base própria):
    set -a; source /home/dev/plataforma/laco/var/trilha/uniao.env; set +a
    bash /home/dev/plataforma/laco/roda_teste.sh tests/adversario_raiz/test_advl6_linha_l6_conectores.py -q
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from unittest import mock

import psycopg2
import psycopg2.extras
import pytest

from app.conexao import consulta_sql, seguranca
from app.conexao import proveniencia as pv
from app.schema_ambiente import CursorSchemaAmbiente
from app.settings import settings
from scripts import acervo_sync

TABELAS = {"sedes_municipais"}


# CONSERTADO (17/09/2026, ramo wt/l56): `pg_ls_` entrou em FUNCOES_PROIBIDAS como FAMÍLIA.
@pytest.mark.parametrize("funcao", ["pg_ls_logdir", "pg_ls_waldir", "pg_ls_tmpdir", "pg_ls_archive_statusdir"])
def test_l6_02_j_funcao_de_arquivo_fora_do_denylist(funcao):
    sql = f"SELECT {funcao}() FROM sedes_municipais LIMIT 1"
    # o teste PASSA (xfail vira xpass=falha) só se validar() RECUSAR a consulta.
    with pytest.raises(consulta_sql.ConsultaRecusada):
        consulta_sql.validar(sql, TABELAS, "public")


# CONSERTADO (17/09/2026, ramo wt/l56): existe agora `FUNCOES_PERMITIDAS` (+ prefixo `st_`), e toda
# chamada de função da consulta, inclusive na projeção, é conferida contra ela. Par positivo em
# `test_l6_02_j_funcao_de_leitura_da_lista_branca_continua_passando`.
def test_l6_02_j_funcao_arbitraria_na_projecao_nao_e_bloqueada():
    sql = "SELECT uma_funcao_de_extensao_no_banco_do_cliente() FROM sedes_municipais LIMIT 1"
    with pytest.raises(consulta_sql.ConsultaRecusada):
        consulta_sql.validar(sql, TABELAS, "public")


def _resposta_json(doc: dict) -> seguranca.ResultadoBusca:
    corpo = json.dumps(doc).encode()
    return seguranca.ResultadoBusca(
        ok=True, status=200, mensagem="http_200", url_final="https://fixture.local/collections/teste",
        latencia_ms=1, saltos=0, corpo=corpo, content_type="application/json",
    )


# CONSERTADO (17/09/2026, ramo wt/l56): `proveniencia._licenca_declarada` lê o link `rel=license` quando
# o `license` do JSON-raiz não diz nada (ausente, "various", "proprietary"). Par positivo em
# `test_l6_05_licenca_declarada_no_json_raiz_continua_ganhando_do_link`.
def test_l6_05_stac_licenca_via_link_nao_e_lida():
    doc = {
        "id": "colecao-de-teste-interno",
        "title": "Coleção de teste interno",
        "license": "various",
        "links": [
            {"rel": "license", "href": "https://exemplo.org/licencas/cc-by-4.0", "title": "CC-BY-4.0"},
        ],
    }
    with mock.patch.object(seguranca, "buscar_seguro", return_value=_resposta_json(doc)):
        achados, _atrib, _url, _corpo = pv._sondar_json(
            "https://fixture.local/collections/colecao-de-teste-interno", "stac"
        )
    # o teste PASSA (xfail vira xpass=falha) só se a licença do link rel=license for capturada.
    assert achados["licenca"] == "CC-BY-4.0"


class _CursorColunasFalso:
    """Só o que `_colunas_da_tabela` usa: `execute` (ignorado) e `fetchall` devolvendo os nomes de coluna
    no mesmo formato de `information_schema.columns` via RealDictCursor."""

    def __init__(self, colunas: list[str]):
        self._colunas = colunas

    def execute(self, *_a, **_kw) -> None:
        pass

    def fetchall(self):
        return [{"column_name": c} for c in self._colunas]


# CONSERTADO (17/09/2026, turno de segurança): a comparação por nome INTEIRO virou comparação por TERMO
# (`scripts/acervo_sync.py::_e_pii_por_nome`), e `scripts/acervo_fdw_sync.py` passou a usar a mesma
# função em vez da lista de nomes. Deixou de ser xfail. O controle positivo — 15 colunas geográficas/
# administrativas que continuam EXPOSTAS e os 29 nomes da lista antiga que continuam bloqueados — está em
# `tests/seguranca/test_acervo_sync_coluna_pii.py`. A checagem fina por CONTEÚDO segue sendo o L6-01-f.
@pytest.mark.parametrize(
    "coluna_pii", ["cpf_titular", "nr_cpf", "proprietario_nome", "nome_do_proprietario"]
)
def test_l6_01_a_variacao_de_nome_de_coluna_pii_e_bloqueada(coluna_pii):
    cur = _CursorColunasFalso(["ogc_fid", coluna_pii, "geom"])
    expostas, bloqueadas = acervo_sync._colunas_da_tabela(cur, "public", "tabela_teste", "geom")
    # a variação tem de sair BLOQUEADA, nunca exposta.
    assert coluna_pii in bloqueadas
    assert coluna_pii not in expostas


def _psql(sql: str) -> str:
    """psql como postgres (bypassa RLS) — só para preparar/limpar o cenário, nunca para provar a corrida em
    si (a corrida é provada pelas DUAS conexões como plat_app, a mesma role que a API usa). `sql` é escrito
    com o literal 'plat.' e reescrito para o schema do ambiente (plat_tuniao na trilha), a mesma regra que
    `app/schema_ambiente.py` aplica dentro do processo da aplicação — psql não passa por lá."""
    from app.schema_ambiente import esquemas_do_ambiente, reescrever_schema

    schema, schema_trabalho = esquemas_do_ambiente()
    sql = reescrever_schema(sql, schema, schema_trabalho)
    r = subprocess.run(["sudo", "-u", "postgres", "psql", "-d", os.environ.get("PLAT_BANCO", "iagro_sat"),
                        "-X", "-q", "-tA", "-v", "ON_ERROR_STOP=1", "-c", sql],
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    return r.stdout.strip()


def _conectar_app() -> psycopg2.extensions.connection:
    con = psycopg2.connect(settings.PLAT_DSN, cursor_factory=CursorSchemaAmbiente)
    con.autocommit = False
    return con


def _contexto(cur, tenant_id: int, usuario_id: int) -> None:
    cur.execute("SELECT set_config('plat.tenant_id', %s, true), set_config('plat.usuario_id', %s, true), "
                "set_config('plat.login', 'admin', true)", (str(tenant_id), str(usuario_id)))


@pytest.mark.xfail(
    strict=True,
    reason="L6-02-k: agenda_criar/agenda_retomar fazem 'SELECT conta, compara com a cota, INSERT' na mesma "
    "transação, sem SELECT ... FOR UPDATE, sem advisory lock e sem constraint no banco. Duas transações que "
    "leem o mesmo n antes de qualquer uma commitar passam as duas pelo teto — reproduzido aqui de forma "
    "determinística (as duas leituras acontecem antes de qualquer INSERT, sem depender de timing de "
    "thread): o teto de 1 agenda ativa (cota rebaixada para o teste) não impede a segunda inserção.",
)
def test_l6_02_k_teto_de_agendas_por_usuario_tem_corrida_de_checar_e_agir():
    tenant_id, usuario_id = 1, 2  # tenant 'demo', usuário 'admin' — o mesmo par de tests/jobs_sessao.py
    existentes = int(_psql(f"SELECT plat.agendas_ativas_usuario({usuario_id})"))
    cota_nova = existentes + 1
    _psql(f"UPDATE plat.tenant SET config = config || jsonb_build_object('cota_agendas_usuario', {cota_nova}) "
          f"WHERE id = {tenant_id}")
    id1 = id2 = None
    try:
        con1, con2 = _conectar_app(), _conectar_app()
        cur1, cur2 = con1.cursor(), con2.cursor()
        _contexto(cur1, tenant_id, usuario_id)
        _contexto(cur2, tenant_id, usuario_id)

        cur1.execute("SELECT plat.cota_agendas_usuario(%s) AS cota, plat.agendas_ativas_usuario(%s) AS n",
                     (tenant_id, usuario_id))
        r1 = cur1.fetchone()
        cur2.execute("SELECT plat.cota_agendas_usuario(%s) AS cota, plat.agendas_ativas_usuario(%s) AS n",
                     (tenant_id, usuario_id))
        r2 = cur2.fetchone()
        assert r1["n"] < r1["cota"] and r2["n"] < r2["cota"], "pré-condição: as duas leituras veem espaço livre"

        selo = int(time.time() * 1000)
        cur1.execute("INSERT INTO plat.agenda(tenant_id, usuario_id, nome, tipo, parametros, cron) "
                     "VALUES (%s, %s, %s, 'prova.progresso', '{}'::jsonb, '*/15 * * * *') RETURNING id",
                     (tenant_id, usuario_id, f"zt-adv-l6-corrida-1-{selo}"))
        id1 = cur1.fetchone()["id"]
        con1.commit()  # primeira transação já commitou a agenda dela

        cur2.execute("INSERT INTO plat.agenda(tenant_id, usuario_id, nome, tipo, parametros, cron) "
                     "VALUES (%s, %s, %s, 'prova.progresso', '{}'::jsonb, '*/15 * * * *') RETURNING id",
                     (tenant_id, usuario_id, f"zt-adv-l6-corrida-2-{selo}"))
        id2 = cur2.fetchone()["id"]
        con2.commit()  # segunda transação nunca releu a cota: insere mesmo já tendo 1 a mais que o teto

        final = int(_psql(f"SELECT plat.agendas_ativas_usuario({usuario_id})"))
        # o teste PASSA (xfail vira xpass=falha) só se o banco tiver recusado a segunda inserção.
        assert final <= cota_nova, f"{final} agendas ativas com cota {cota_nova}: o teto foi contornado"
    finally:
        if id1:
            _psql(f"DELETE FROM plat.agenda WHERE id = '{id1}'")
        if id2:
            _psql(f"DELETE FROM plat.agenda WHERE id = '{id2}'")
        _psql(f"UPDATE plat.tenant SET config = config - 'cota_agendas_usuario' WHERE id = {tenant_id}")


def test_l6_02_j_funcao_de_leitura_da_lista_branca_continua_passando():
    """Par positivo da lista branca de função: fechar a projeção não pode ter fechado a consulta útil —
    agregação, texto e PostGIS (as três que o próprio item mede em tests/api/test_bancos_externos.py)
    continuam passando."""
    v = consulta_sql.validar(
        "SELECT count(*) AS n, upper(nome) AS nome, ST_AsText(geom) AS wkt FROM sedes_municipais "
        "GROUP BY nome, geom LIMIT 10",
        TABELAS, "public",
    )
    assert v.limite == 10 and v.tabelas == ["sedes_municipais"]


def test_l6_05_licenca_declarada_no_json_raiz_continua_ganhando_do_link():
    """Par positivo da leitura de licença: quando o serviço declara a licença de verdade no `license` do
    JSON-raiz, é ELA que vale — o link não passa a atropelar o valor declarado."""
    doc = {
        "id": "colecao-de-teste-interno",
        "title": "Coleção de teste interno",
        "license": "CC-BY-SA-4.0",
        "links": [{"rel": "license", "href": "https://exemplo.org/outra", "title": "OUTRA-LICENCA"}],
    }
    with mock.patch.object(seguranca, "buscar_seguro", return_value=_resposta_json(doc)):
        achados, _atrib, _url, _corpo = pv._sondar_json(
            "https://fixture.local/collections/colecao-de-teste-interno", "stac"
        )
    assert achados["licenca"] == "CC-BY-SA-4.0", achados


def test_l6_05_servico_que_nao_declara_licenca_continua_sem_licenca():
    """Par positivo 2: nada é inventado — sem `license` e sem link `rel=license`, a ficha sai com
    `licenca=None` (o campo é marcado como não registrado, nunca preenchido com padrão)."""
    doc = {"id": "sem-licenca", "title": "Sem licença", "links": [{"rel": "self", "href": "https://x.invalido"}]}
    with mock.patch.object(seguranca, "buscar_seguro", return_value=_resposta_json(doc)):
        achados, _atrib, _url, _corpo = pv._sondar_json("https://fixture.local/collections/sem-licenca", "stac")
    assert achados["licenca"] is None, achados
