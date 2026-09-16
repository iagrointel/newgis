"""Adversário de linha L4 (rede de utilidades, parte 1) — duas suposições TRANSVERSAIS que a linha
inteira assume e que caem ao vivo, independentes uma da outra, cada uma sozinha o bastante para
derrubar os 16 itens sob ataque neste turno (`laco/handoffs/T9/linha-L4-laudo-adversario-1.md`).

ACHADO 1 — `POST /api/rede` (e `GET`) nunca escreve nem devolve `tolerancia_m`, mas o modelo de
resposta `Rede` exige o campo. Toda rede criada pela API quebra a resposta com
`fastapi.exceptions.ResponseValidationError` (a linha comete a escrita — `RETURNING id` já rodou e o
`with db.db(...)` já fechou/commitou antes da serialização falhar — mas o cliente nunca recebe corpo
nem o `id`). `git log -p -S tolerancia_m -- app/rede_utilidades/rotas.py` mostra que este arquivo já
teve as três linhas certas (`r.tolerancia_m` no SELECT, `"tolerancia_m": float(r["tolerancia_m"])` no
`_json`, `corpo.tolerancia_m` no INSERT) em pontos do histórico — não é uma lacuna que nunca existiu,
é uma regressão que uma fusão (a árvore tem oito commits "Ponto de salvamento da bancada topo" no
mesmo segundo, 06/09 19:52:51, que tornam bisect linha-a-linha inconclusivo) apagou de volta para a
versão sem o campo, enquanto `app/rede_utilidades/modelos.py` seguiu em frente exigindo-o
(`Rede.tolerancia_m: float`, sem default, desde 07-10/09). Isto derruba toda cláusula que abre com
"criar 1 rede" nos 14 itens desta linha que usam a API padrão (todo item que reusa `_criar_rede` de
`tests/api/test_rede_tracado.py`, direta ou indiretamente).

ACHADO 2 — o vocabulário de `plat.rede_regra.tipo` divergiu entre o BANCO e a APLICAÇÃO. A migração
`db/migracoes/20260906T2058_rede_regras_conectividade.sql` trocou a CHECK CONSTRAINT para
`('juncao_juncao', 'juncao_aresta', 'aresta_juncao_aresta', 'contencao', 'estrutura')` — confirmado ao
vivo (`pg_get_constraintdef` na trilha `uniao`) — mas os CINCO pacotes de ativos
(`app/rede_utilidades/pacotes/{eletrica-br,gas-br,agua-epanet,esgoto-teksi,transmissao-matpower}.json`)
continuam declarando regras com o vocabulário ANTIGO (`conectividade_no_trecho`,
`conectividade_entre_nos`, ...), e `app/rede_utilidades/deposito.py` grava `r["tipo"]` do pacote
verbatim, sem tradução nenhuma. `app/rede_utilidades/esquema.py:TIPOS_REGRA` e
`app/rede_utilidades/topologia.py:TIPOS_REGRA_CONECTIVIDADE` também citam só o vocabulário antigo — a
divergência não é um arquivo esquecido, é a aplicação inteira apontando para um vocabulário que o
banco não aceita mais. Resultado: a PRIMEIRA importação de QUALQUER pacote, em QUALQUER rede nova,
falha com `CheckViolation` — reproduzido ao vivo rodando o arquivo OFICIAL do item pai:
`set -a; source laco/var/trilha/uniao.env; set +a; bash laco/roda_teste.sh
tests/api/test_rede_modelo.py -q` → as 6 cláusulas de `test_rede_modelo.py` (item
L4-01-modelo-rede) erram na fixture com
`psycopg2.errors.CheckViolation: new row for relation "rede_regra" violates check constraint
"rede_regra_tipo_check"`. Isto derruba os 2 itens que criam a rede por SQL direto (contornando o
Achado 1) e, para os outros 14, é a SEGUNDA parede: mesmo que alguém conserte o Achado 1, a chamada a
`POST /api/rede/{id}/pacote` (que os testes oficiais chamam de `_importar_eletrica`) esbarra neste
mesmo `CheckViolation` em seguida — os dois achados juntos, não um substituindo o outro, é que
derrubam os 16 itens deste turno.

Reprodução mínima e independente dos arquivos oficiais, cada teste isolando UM achado (não os dois
juntos, para não confundir causa): o teste do Achado 1 usa só a API (não instala pacote nenhum); o do
Achado 2 cria a rede por SQL direto (contorna o Achado 1 de propósito) e importa o pacote pela MESMA
rota HTTP que os 14 itens usam (`POST /api/rede/{id}/pacote`), não por chamada direta a
`deposito.importar`, para provar que o problema aparece pela porta da frente.

Não conserta nada aqui (regra da casa); cada achado só documenta o xfail(strict=True). Nomes de
inquilino/rede são fictícios (`zt-adv-l4-*`), nunca o nome de uma distribuidora real."""

from __future__ import annotations

import uuid

import pytest

from app.rede_utilidades import instalados
from app.rede_utilidades import pacote as pacote_mod
from tests.api.test_rls import contexto, ids_por_slug


@pytest.mark.xfail(
    strict=True,
    reason=(
        "ACHADO 1 (adversário L4, turno 9): POST /api/rede quebra a resposta com "
        "ResponseValidationError porque app/rede_utilidades/rotas.py (SQL_BASE, _json, criar) nunca "
        "leu/escreveu/devolveu tolerancia_m, enquanto app/rede_utilidades/modelos.py:Rede exige o "
        "campo sem default desde 07-10/09. A rede É criada (o INSERT roda e comita antes da "
        "serialização falhar) mas o chamador nunca recebe o id nem status 201 — reproduzido com "
        "TestClient real contra o app vivo da trilha uniao, sem depender de nenhum arquivo oficial do "
        "item. Derruba a cláusula 'criar 1 rede' de todo item de L4 que cria rede pela API padrão."
    ),
)
def test_l4_adv1_criar_rede_via_api_falta_tolerancia_m(sessao_a):
    nome = f"zt-adv-l4-transversal-{uuid.uuid4().hex[:10]}"
    r = sessao_a.post("/api/rede", json={"nome": nome, "disciplina": "eletrica"})
    assert r.status_code == 201, r.text
    corpo = r.json()
    assert "tolerancia_m" in corpo, corpo
    sessao_a.delete(f"/api/rede/{corpo['id']}")


@pytest.mark.xfail(
    strict=True,
    reason=(
        "ACHADO 2 (adversário L4, turno 9): POST /api/rede/{id}/pacote falha com 422 "
        "(restricao=rede_regra_tipo_check) na PRIMEIRA importação de QUALQUER pacote de ativos "
        "(eletrica-br testado aqui; os outros 4 pacotes usam o mesmo vocabulário antigo e caem "
        "igual), porque a migração 20260906T2058_rede_regras_conectividade.sql trocou a CHECK "
        "CONSTRAINT do banco para o vocabulário novo (juncao_juncao/juncao_aresta/...) sem que os "
        "arquivos de pacote nem app/rede_utilidades/deposito.py fossem atualizados — deposito.py grava "
        "r['tipo'] do JSON verbatim, sem tradução. A rede é criada por SQL direto (contorna o Achado "
        "1 de propósito, para isolar este achado) e o pacote é importado pela MESMA rota HTTP que os "
        "14 itens irmãos usam. Derruba a cláusula 'instalar o pacote' de toda a linha."
    ),
)
def test_l4_adv1_instalar_pacote_vocabulario_regra_divergente(sessao_a, conexao_plat_app):
    con = conexao_plat_app
    ids = ids_por_slug(con)
    tenant_id = ids["demo"]
    with con.cursor() as cur:
        contexto(con, tenant_id)
        cur.execute(
            "SELECT id FROM plat.usuario WHERE tenant_id = %s AND ativo ORDER BY id LIMIT 1", (tenant_id,)
        )
        usuario_id = cur.fetchone()["id"]
        contexto(con, tenant_id, usuario_id)
        nome = f"zt-adv-l4-vocabulario-{uuid.uuid4().hex[:10]}"
        cur.execute(
            "INSERT INTO plat.rede (tenant_id, nome, disciplina, tolerancia_m, dono_id) "
            "VALUES (%s, %s, 'eletrica', 0.05, %s) RETURNING id",
            (tenant_id, nome, usuario_id),
        )
        rede_id = str(cur.fetchone()["id"])
    con.commit()

    bruto = instalados.bruto("eletrica-br")
    doc = pacote_mod.ler(bruto)  # confere que o pacote em si é válido — o problema é só o vocabulário
    assert any(r["tipo"] == "conectividade_no_trecho" for r in doc["regras"]), (
        "pré-condição do achado: o pacote eletrica-br declara o vocabulário antigo; se isto falhar, "
        "o pacote já foi corrigido e este xfail deixou de fazer sentido"
    )

    r = sessao_a.post(f"/api/rede/{rede_id}/pacote", content=bruto, headers={"Content-Type": "application/json"})
    assert r.status_code == 201, r.text

    sessao_a.delete(f"/api/rede/{rede_id}")
