"""Documento de construtor (item L5-05-documento-versoes; ADR 0011): grafo de nós com ULID por nó em cima do
mecanismo genérico de versão de L0-03 (`plat.item_versao`, sha256, publicar). Cobre: nó sem ULID / ULID repetido
/ ligação pendente → 422 `grafo_invalido`; sha256_canonico reproduzível fora do banco (`sha256sum`); rascunho ×
publicado nunca se confundem; ULID de nó nunca se repete entre versões; migração de esquema na leitura
(esquema_versao antiga → corpo migrado + evento); RLS cruzado; corrupção direta na linha de versão aparece em
`/api/itens/{id}/integridade`."""

import hashlib
import json
import os
import subprocess
import sys
import time

import psycopg2
import pytest

from tests.api.catalogo.conftest import titulo_zt
from tests.api.test_rls import contexto, ids_por_slug

ITEM = "L5-05-documento-versoes"
# `sudo -u postgres psql` (abaixo) fala direto com o Postgres, fora da conexão da aplicação — por isso NÃO
# passa pelo `CursorSchemaAmbiente` que reescreve `plat.` para o schema da trilha/homologação (achado desta
# verificação: o literal `plat.item_versao` sempre mirava o schema de PRODUÇÃO, então em qualquer base
# isolada (trilha/homologação) a adulteração caía numa linha que não existia e o teste falhava sempre,
# não só às vezes). `PLAT_SCHEMA` é a MESMA variável que `app/schema_ambiente.py` lê.
SCHEMA_SQL = os.environ.get("PLAT_SCHEMA") or "plat"


def _no(tipo="widget"):
    from app.catalogo.documento import gerar_ulid

    return gerar_ulid(), tipo


def _corpo(nos=(), ligacoes=()):
    ns = [{"id": nid, "tipo": t} for nid, t in nos]
    ls = list(ligacoes)
    corpo = {"nos": ns}
    if ls:
        corpo["ligacoes"] = ls
    return corpo


def test_grafo_valido_cria_e_versao_traz_sha256_canonico(sessao_a, itens_a):
    a, b = _no("mapa"), _no("texto")
    corpo = _corpo([a, b], [{"origem": a[0], "alvo": b[0], "tipo": "filtra"}])
    it = itens_a.criar("app", dados={"tipo": "app", "esquema_versao": 2, "corpo": corpo})
    assert it["dados"]["corpo"]["nos"][0]["id"] == a[0]
    v = sessao_a.get(f"/api/itens/{it['id']}/versoes/1").json()
    assert len(v["sha256"]) == 64 and len(v["sha256_canonico"]) == 64 and v["sha256"] != v["sha256_canonico"]


def test_sha256_canonico_reproduz_fora_do_banco_com_sha256sum(tmp_path, sessao_a, itens_a):
    """Portão: sha256 igual ao calculado fora (`sha256sum` do corpo canônico) — reproduz com o comando que o
    docstring de `documento.corpo_canonico` documenta, byte a byte, sem tocar o banco de novo."""
    a = _no("mapa")
    corpo = _corpo([a])
    it = itens_a.criar("painel", dados={"tipo": "painel", "esquema_versao": 2, "corpo": corpo})
    v = sessao_a.get(f"/api/itens/{it['id']}/versoes/1").json()

    arquivo = tmp_path / "corpo.json"
    arquivo.write_text(json.dumps(v["corpo"]["dados"]["corpo"]), encoding="utf-8")
    comando = (
        "import json,sys; sys.stdout.write(json.dumps(json.load(sys.stdin), sort_keys=True, "
        "ensure_ascii=False, separators=(',',':')))"
    )
    saida = subprocess.run(
        [sys.executable, "-c", comando], stdin=arquivo.open("rb"), capture_output=True, check=True
    ).stdout
    fora = hashlib.sha256(saida).hexdigest()
    assert fora == v["sha256_canonico"], (fora, v["sha256_canonico"])


def test_no_sem_ulid_e_ulid_repetido_e_ligacao_pendente_sao_recusados(sessao_a, itens_a):
    a, b = _no(), _no()
    # dois nós com o mesmo id
    r = sessao_a.post(
        "/api/itens",
        json={
            "tipo": "app",
            "titulo": titulo_zt("app-dup"),
            "dados": {"tipo": "app", "esquema_versao": 2, "corpo": _corpo([a, (a[0], "outro_tipo")])},
        },
    )
    assert r.status_code == 422 and r.json()["erro"] == "grafo_invalido"
    assert any(d["regra"] == "id_duplicado" for d in r.json()["detalhe"])

    # ligação para id que não existe em nos
    r = sessao_a.post(
        "/api/itens",
        json={
            "tipo": "app",
            "titulo": titulo_zt("app-pendente"),
            "dados": {
                "tipo": "app",
                "esquema_versao": 2,
                "corpo": _corpo([a], [{"origem": a[0], "alvo": b[0]}]),
            },
        },
    )
    assert r.status_code == 422 and r.json()["erro"] == "grafo_invalido"
    assert any(d["regra"] == "referencia_pendente" for d in r.json()["detalhe"])

    # id que não é ULID (json schema, antes mesmo do validador de grafo)
    r = sessao_a.post(
        "/api/itens",
        json={
            "tipo": "app",
            "titulo": titulo_zt("app-naoulid"),
            "dados": {"tipo": "app", "esquema_versao": 2, "corpo": {"nos": [{"id": "nao-ulid", "tipo": "x"}]}},
        },
    )
    assert r.status_code == 422 and r.json()["erro"] == "dados_invalidos"

    # o mesmo vale no PUT (não só na criação)
    it = itens_a.criar("app", dados={"tipo": "app", "esquema_versao": 2, "corpo": _corpo([a])})
    r = sessao_a.put(
        f"/api/itens/{it['id']}",
        json={"dados": {"tipo": "app", "esquema_versao": 2, "corpo": _corpo([a, (a[0], "y")])}},
    )
    assert r.status_code == 422 and r.json()["erro"] == "grafo_invalido"


def test_rascunho_nao_muda_publicado_ate_publicar_explicitamente(sessao_a, itens_a):
    a = _no()
    it = itens_a.criar("app", dados={"tipo": "app", "esquema_versao": 2, "corpo": _corpo([a])})
    iid = it["id"]
    r = sessao_a.post(f"/api/itens/{iid}/versoes/1/publicar")
    assert r.status_code == 200 and r.json()["versao_publicada"] == 1

    b = _no()
    r = sessao_a.put(
        f"/api/itens/{iid}", json={"dados": {"tipo": "app", "esquema_versao": 2, "corpo": _corpo([a, b])}}
    )
    assert r.status_code == 200 and r.json()["versao_atual"] == 2 and r.json()["versao_publicada"] == 1

    publicada = sessao_a.get(f"/api/itens/{iid}/versoes/1").json()
    assert len(publicada["corpo"]["dados"]["corpo"]["nos"]) == 1  # rascunho (v2) não vazou pra versão publicada

    r = sessao_a.post(f"/api/itens/{iid}/versoes/2/publicar")
    assert r.status_code == 200 and r.json()["versao_publicada"] == 2
    ainda_le_v1 = sessao_a.get(f"/api/itens/{iid}/versoes/1").json()
    assert len(ainda_le_v1["corpo"]["dados"]["corpo"]["nos"]) == 1  # versão anterior continua legível


def test_ulid_de_no_nunca_se_repete_entre_versoes(sessao_a, itens_a):
    """Editar o documento várias vezes nunca reusa um id de nó já visto em nenhuma versão anterior — cada
    edição neste teste gera nós NOVOS (nunca reaproveita `_no()` de uma rodada anterior)."""
    todos_vistos: set[str] = set()
    nos_atuais = []
    it = None
    for _ in range(5):
        novo = _no()
        assert novo[0] not in todos_vistos
        todos_vistos.add(novo[0])
        nos_atuais.append(novo)
        corpo = {"tipo": "painel", "esquema_versao": 2, "corpo": _corpo(nos_atuais)}
        if it is None:
            it = itens_a.criar("painel", dados=corpo)
        else:
            r = sessao_a.put(f"/api/itens/{it['id']}", json={"dados": corpo})
            assert r.status_code == 200
    lista = sessao_a.get(f"/api/itens/{it['id']}/versoes?limite=10").json()
    assert lista["total"] == 5
    ids_por_versao = []
    for v in lista["itens"]:
        detalhe = sessao_a.get(f"/api/itens/{it['id']}/versoes/{v['versao']}").json()
        nos = detalhe["corpo"]["dados"]["corpo"]["nos"]
        assert len(nos) == len({n["id"] for n in nos})  # nenhuma versão, sozinha, repete um id de nó
        ids_por_versao.extend(n["id"] for n in nos)
    # cada edição SOMA um nó (v1=1, v2=2, ..., v5=5): 15 aparições no total, mas só 5 ids DISTINTOS — nenhum
    # id foi reaproveitado para um nó diferente do que era antes em nenhuma versão
    assert len(ids_por_versao) == 1 + 2 + 3 + 4 + 5 == 15
    assert set(ids_por_versao) == todos_vistos and len(todos_vistos) == 5


def test_migracao_de_esquema_na_leitura_com_evento(sessao_a, itens_a, conexao_plat_app):
    """Documento gravado com esquema_versao=1 (`corpo:{}`, a forma que existia antes de 028_documento_grafo.sql
    e que os 1.573/1.571 itens semeados em demo ainda têm) chega pela API JÁ migrado para v2, com `nos`/`ligacoes`
    default, e o evento `itens/esquema_migrado` fica registrado — nunca é gravado de volta em `plat.item.dados`."""
    it = itens_a.criar("painel", dados={"tipo": "painel", "esquema_versao": 1, "corpo": {}})
    iid = it["id"]
    ids = ids_por_slug(conexao_plat_app)
    with conexao_plat_app.cursor() as cur:
        cur.execute("SELECT usuario_id FROM plat.auth_login('demo', 'admin')")
        adm = cur.fetchone()["usuario_id"]
    contexto(conexao_plat_app, ids["demo"], usuario_id=adm, login="admin")
    with conexao_plat_app.cursor() as cur:
        # simula o dado legado direto no banco (fora da API, que já bloquearia esquema_versao:1 sem migração
        # aplicada na ESCRITA — a migração deste item é só na LEITURA)
        cur.execute(
            "UPDATE plat.item SET dados = %s::jsonb WHERE id = %s::uuid",
            (json.dumps({"tipo": "painel", "esquema_versao": 1, "corpo": {}}), iid),
        )
    conexao_plat_app.commit()

    r = sessao_a.get(f"/api/itens/{iid}")
    assert r.status_code == 200
    dados = r.json()["dados"]
    assert dados["esquema_versao"] == 2 and dados["corpo"] == {"nos": [], "ligacoes": []}

    contexto(conexao_plat_app, ids["demo"], usuario_id=adm, login="admin")  # SET LOCAL não sobrevive ao commit acima
    with conexao_plat_app.cursor() as cur:
        cur.execute(
            "SELECT dados FROM plat.item WHERE id = %s::uuid", (iid,)
        )
        ainda_1 = cur.fetchone()["dados"]
    assert ainda_1["esquema_versao"] == 1  # a migração NÃO gravou de volta no banco

    with conexao_plat_app.cursor() as cur:
        cur.execute(
            "SELECT propriedades FROM plat.evento WHERE alvo_id = %s AND tipo = 'itens/esquema_migrado' "
            "ORDER BY em DESC LIMIT 1",
            (iid,),
        )
        evento = cur.fetchone()
    assert evento is not None and evento["propriedades"]["de"] == 1 and evento["propriedades"]["para"] == 2


def test_versoes_de_outro_inquilino_404_para_documento(sessao_a, itens_b):
    it = itens_b.criar("app", dados={"tipo": "app", "esquema_versao": 2, "corpo": _corpo([_no()])})
    assert sessao_a.get(f"/api/itens/{it['id']}/versoes").status_code == 404
    assert sessao_a.get(f"/api/itens/{it['id']}/versoes/1").status_code == 404
    assert sessao_a.get(f"/api/itens/{it['id']}/integridade").status_code == 404


def test_plat_app_nao_pode_editar_item_versao(conexao_plat_app):
    """Pré-condição do teste seguinte: `plat_app` (o papel da própria API) tem INSERT/UPDATE/DELETE
    REVOGADOS em `plat.item_versao` desde 011_catalogo.sql — só quem tem acesso direto ao Postgres como
    dono/superusuário (fora da aplicação) consegue adulterar uma versão. Por isso o teste de corrupção
    usa `sudo -u postgres psql`, não esta conexão."""
    with conexao_plat_app.cursor() as cur, pytest.raises(psycopg2.errors.InsufficientPrivilege):
        cur.execute("UPDATE plat.item_versao SET sha256 = 'x' WHERE false")
    conexao_plat_app.rollback()


def test_integridade_acusa_linha_de_versao_editada_direto_no_banco(sessao_a, itens_a):
    it = itens_a.criar("app", dados={"tipo": "app", "esquema_versao": 2, "corpo": _corpo([_no()])})
    iid = it["id"]
    r = sessao_a.get(f"/api/itens/{iid}/integridade").json()
    assert r == {"integro": True, "versoes": 1, "versoes_corrompidas": []}

    # adversário com acesso direto ao Postgres (fora da aplicação, plat_app não tem este privilégio — ver
    # test_plat_app_nao_pode_editar_item_versao): edita o `corpo` gravado sem tocar o `sha256` ao lado.
    tamper = subprocess.run(
        [
            "sudo",
            "-u",
            "postgres",
            "psql",
            "-d",
            "iagro_sat",
            "-v",
            "ON_ERROR_STOP=1",
            "-c",
            f"UPDATE {SCHEMA_SQL}.item_versao SET corpo = jsonb_set(corpo, '{{titulo}}', '\"adulterado\"') "
            f"WHERE item_id = '{iid}'::uuid AND versao = 1",
        ],
        capture_output=True,
        text=True,
    )
    assert tamper.returncode == 0, tamper.stderr

    r = sessao_a.get(f"/api/itens/{iid}/integridade").json()
    assert r == {"integro": False, "versoes": 1, "versoes_corrompidas": [1]}


def test_latencia_salvar_versao_de_documento_ms(sessao_a, itens_a, medida):
    it = itens_a.criar("painel", dados={"tipo": "painel", "esquema_versao": 2, "corpo": _corpo([_no()])})
    iid = it["id"]
    tempos = []
    for _i in range(30):
        corpo = {"tipo": "painel", "esquema_versao": 2, "corpo": _corpo([_no(), _no()])}
        t0 = time.perf_counter()
        r = sessao_a.put(f"/api/itens/{iid}", json={"dados": corpo})
        tempos.append((time.perf_counter() - t0) * 1000)
        assert r.status_code == 200
    tempos.sort()
    mediana = tempos[len(tempos) // 2]
    medida(ITEM)(
        "latencia_salvar_versao_ms",
        round(mediana, 3),
        "ms",
        "mediana de 30 PUT /api/itens/{id} (painel, 2 nós, TestClient in-process)",
    )
    assert mediana < 200, mediana
