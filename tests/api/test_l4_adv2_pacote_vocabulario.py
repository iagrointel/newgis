"""Adversário da linha L4 rede de utilidades (rodada 2) — achado TRANSVERSAL.

Instalar QUALQUER um dos 5 pacotes de ativos de rede (eletrica-br, agua-epanet, esgoto-teksi, gas-br,
transmissao-matpower) numa rede NOVA falha com `psycopg2.errors.CheckViolation` na hora de gravar as
regras de conectividade.

Causa raiz (lida em `db/migracoes/20260906T2058_rede_regras_conectividade.sql`, item
L4-03-a-regras-de-conectividade): essa migração trocou o vocabulário de `plat.rede_regra.tipo`
(`conectividade_no_trecho`/`conectividade_entre_nos`/`fixacao_estrutural`/`contencao` ->
`juncao_juncao`/`juncao_aresta`/`aresta_juncao_aresta`/`contencao`/`estrutura`) e até TRADUZIU as
linhas já gravadas com um `UPDATE ... CASE`. O que ela não fez foi atualizar os 5 arquivos
`app/rede_utilidades/pacotes/*.json`, que continuam declarando o vocabulário ANTIGO nas suas seções
`"regras"` — e `app/rede_utilidades/deposito.py::importar` grava `r["tipo"]` verbatim do JSON, sem
nenhuma tradução. Conferido ao vivo (`SELECT pg_get_constraintdef(...) WHERE conname =
'rede_regra_tipo_check'` na trilha `uniao`): a constraint ATIVA hoje só aceita o vocabulário NOVO.

Isso derruba a suposição-base que a linha inteira compartilha ("o pacote instala e o resto do motor —
categorias, isolamento, traçado, regras de atributo, telemetria — roda em cima dele"), para os 5
domínios de uma vez: qualquer item que precise de uma rede NOVA com pacote instalado (a esmagadora
maioria dos itens desta linha) está, neste exato estado do repositório, quebrado na primeira chamada.
Itens marcados ENTREGUE cujo "última nota do ledger" cita suítes verdes que criam rede + instalam
pacote não foram reexecutados depois da migração de vocabulário — mesmo padrão do achado #2 da rodada
2 do adversário de L2 ("a evidência commitada reprova o próprio portão").

Reprodução:
    set -a; source /home/dev/plataforma/laco/var/trilha/uniao.env; set +a
    bash /home/dev/plataforma/laco/roda_teste.sh tests/api/test_l4_adv2_pacote_vocabulario.py -q
"""

import hashlib
import json
from pathlib import Path

import pytest

from app.rede_utilidades import deposito, instalados
from app.rede_utilidades import pacote as pacote_mod
from tests.api.test_rls import contexto, ids_por_slug

PACOTES_DIR = Path(__file__).resolve().parents[2] / "app" / "rede_utilidades" / "pacotes"
DOMINIOS = ["eletrica-br", "agua-epanet", "esgoto-teksi", "gas-br", "transmissao-matpower"]
VOCABULARIO_ANTIGO = {"conectividade_no_trecho", "conectividade_entre_nos", "fixacao_estrutural"}


# ---------------------------------------------------------------------- checagem estática (sem banco,
# sem trilha — sempre reproduzível mesmo com a base sob disputa de outros agentes)
def test_pacotes_de_ativos_ja_usam_o_vocabulario_novo_de_conectividade():
    """Estático: os 5 arquivos de pacote deveriam ter sido migrados junto com
    `20260906T2058_rede_regras_conectividade.sql` (que traduziu as linhas já gravadas no banco com um
    `UPDATE ... CASE`); a fonte dos pacotes ficou para trás."""
    ofensores = {}
    for arquivo in sorted(PACOTES_DIR.glob("*.json")):
        doc = json.loads(arquivo.read_text(encoding="utf-8"))
        tipos_usados = {r["tipo"] for r in doc.get("regras", [])}
        antigos = tipos_usados & VOCABULARIO_ANTIGO
        if antigos:
            ofensores[arquivo.name] = sorted(antigos)
    assert not ofensores, (
        f"pacotes ainda no vocabulário anterior à migração 20260906T2058 (item L4-03-a): {ofensores}"
    )


def _instalar_e_descartar(con, codigo_pacote: str, sufixo: str) -> None:
    ids = ids_por_slug(con)
    tenant_id = ids["demo"]
    with con.cursor() as cur:
        contexto(con, tenant_id)
        cur.execute(
            "SELECT id FROM plat.usuario WHERE tenant_id = %s AND ativo ORDER BY id LIMIT 1", (tenant_id,)
        )
        usuario_id = cur.fetchone()["id"]
        contexto(con, tenant_id, usuario_id)
        cur.execute(
            "INSERT INTO plat.rede (tenant_id, nome, disciplina, tolerancia_m, dono_id) "
            "VALUES (%s, %s, 'eletrica', 0.05, %s) RETURNING id",
            (tenant_id, f"zt-adv2-vocab-{sufixo}", usuario_id),
        )
        rede_id = cur.fetchone()["id"]
        bruto = instalados.bruto(codigo_pacote)
        assert bruto is not None, f"pacote {codigo_pacote!r} não está entre os instalados"
        doc = pacote_mod.ler(bruto)
        deposito.importar(
            cur, tenant_id, rede_id, doc, usuario_id, hashlib.sha256(bruto).hexdigest(), len(bruto)
        )
    con.rollback()  # só queríamos ver se o INSERT das regras passa; não deixa rastro na trilha


@pytest.mark.parametrize("codigo_pacote", DOMINIOS)
def test_instalar_pacote_em_rede_nova_nao_viola_check_de_conectividade(conexao_plat_app, codigo_pacote):
    """CONSERTADO (turno f2fixrede): os 5 pacotes foram convertidos para o vocabulário novo de
    `plat.rede_regra.tipo` (o da migração 20260906T2058) e reescritos na forma canônica; deixa de
    ser xfail e vira teste normal da cláusula."""
    _instalar_e_descartar(conexao_plat_app, codigo_pacote, codigo_pacote.replace("-", "_"))
