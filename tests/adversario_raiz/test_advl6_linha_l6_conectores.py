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

Rodar (na trilha do adversário, base própria):
    set -a; source /home/dev/plataforma/laco/var/trilha/uniao.env; set +a
    bash /home/dev/plataforma/laco/roda_teste.sh tests/adversario_raiz/test_advl6_linha_l6_conectores.py -q
"""

from __future__ import annotations

import json
from unittest import mock

import pytest

from app.conexao import consulta_sql, seguranca
from app.conexao import proveniencia as pv

TABELAS = {"sedes_municipais"}


@pytest.mark.xfail(
    strict=True,
    reason="L6-02-j: FUNCOES_PROIBIDAS não cobre a família pg_ls_logdir/pg_ls_waldir/pg_ls_tmpdir/"
    "pg_ls_archive_statusdir (funções de listagem de diretório do servidor) — a Camada 1 (FORMA) do "
    "módulo promete bloquear 'função de sistema/tempo/arquivo/rede' mas só cobre os nomes citados como "
    "exemplo no comentário, não a família inteira. validar() aceita a consulta sem levantar.",
)
@pytest.mark.parametrize("funcao", ["pg_ls_logdir", "pg_ls_waldir", "pg_ls_tmpdir", "pg_ls_archive_statusdir"])
def test_l6_02_j_funcao_de_arquivo_fora_do_denylist(funcao):
    sql = f"SELECT {funcao}() FROM sedes_municipais LIMIT 1"
    # o teste PASSA (xfail vira xpass=falha) só se validar() RECUSAR a consulta.
    with pytest.raises(consulta_sql.ConsultaRecusada):
        consulta_sql.validar(sql, TABELAS, "public")


@pytest.mark.xfail(
    strict=True,
    reason="L6-02-j: a 'lista branca de SELECT' só é aplicada a identificadores depois de FROM/JOIN. "
    "Qualquer função que NÃO esteja em FUNCOES_PROIBIDAS pode ser chamada livremente na lista de "
    "projeção (fora de FROM/JOIN) — não existe allowlist de funções, só um denylist de nomes fixos. "
    "Num Postgres remoto com extensão de rede/arquivo instalada (ex. pgsql-http, dblink por outro nome, "
    "UDF do cliente), essa 'consulta só de leitura sobre a tabela dele' vira canal para qualquer função "
    "que o papel de conexão tiver EXECUTE, não só sobre as tabelas listadas na conexão.",
)
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


@pytest.mark.xfail(
    strict=True,
    reason="L6-05: o docstring de app/conexao/proveniencia.py promete 'STAC/OGC API: license/link "
    "rel=license', e o ramo ogc_api desta MESMA função já lê o link; o ramo stac só olha doc['license'] "
    "e nunca cai para links[].rel=='license'. Uma coleção STAC que declara a licença só por link (comum "
    "quando 'license' é 'various' ou 'proprietary', conforme o próprio spec STAC) fica com licenca=None "
    "em silêncio, mesmo com o serviço tendo declarado a licença do jeito padronizado.",
)
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
