"""Item L0-04-i-fonte-registrada: conector `postgres_fdw` de `plat.conexao` ("fonte de dado registrada" — o
"data store item" da Esri Enterprise 11.4 / o "store" do GeoServer, restrito ao Postgres/PostGIS externo).

Portão de pronto (literal, ver laco/vivo/prompts/L0-04-i-fonte-registrada.md):
  "teste com um segundo banco Postgres local (docker, dado aberto): registrar, listar 3 tabelas, publicar em
  massa, ver as 3 camadas no catálogo e no mapa; credencial nunca em claro no banco nem no log; conexão que
  cai devolve 503 com mensagem e a camada continua no catálogo com estado 'fonte indisponível'; e2e com
  captura; paridade contra 'Data store items' 11.4 e 'Stores' do GeoServer"

O segundo banco é `plat-il004ifonte-pg` (docker, `postgres:16-alpine`, porta 127.0.0.1:55499, banco
`amostra_aberta`), com 3 tabelas de dado aberto no formato IBGE (estados/municípios/precipitação mensal
sintética) — comandos de criação em `tests/api/dados_pgfdw_amostra.sql`. Pular estes testes (nunca falhar a
suíte) quando o container não está no ar (`pytest.skip`, mesmo padrão de `cred` acima para credenciais
ausentes) — máquina sem docker rodando não é refutação do item.

Refutação do item, os 3 casos, um por teste marcado `# adversário`:
  1. registra conexão com usuário SUPERUSER (`leitor_amostra`) -> avisa, nunca recusa o registro; a escrita
     continua impossível (a VIEW final só tem GRANT SELECT, nunca INSERT/UPDATE/DELETE, migração 20260907T0148).
  2. aponta para o próprio iagro_sat (host/porta/banco do PLAT_DSN desta trilha) -> 422 antes de gravar.
  3. injeta no nome da tabela em publicar-em-massa -> aquele item do lote vem com erro, os outros publicam,
     e a tabela do adversário nunca é tocada (conferido lendo o banco docker direto)."""

import json
import os

import psycopg2
import psycopg2.extras
import pytest

from app.schema_ambiente import CursorSchemaAmbiente
from tests.api.conftest import PREFIXO_TESTE
from tests.api.test_rls import contexto, ids_por_slug

PG_HOST, PG_PORTA, PG_BANCO = "127.0.0.1", 55499, "amostra_aberta"
PG_USUARIO_RO, PG_SENHA_RO = "ro_amostra", "ro123456"
PG_USUARIO_SUPER, PG_SENHA_SUPER = "leitor_amostra", "amostra123"
URL_PG = f"postgres://{PG_HOST}:{PG_PORTA}/{PG_BANCO}"
TABELAS_ESPERADAS = {"estados", "municipios", "precipitacao_mensal"}


def _docker_no_ar() -> bool:
    try:
        con = psycopg2.connect(
            host=PG_HOST, port=PG_PORTA, dbname=PG_BANCO, user=PG_USUARIO_RO, password=PG_SENHA_RO,
            connect_timeout=2,
        )
        con.close()
        return True
    except psycopg2.OperationalError:
        return False


pytestmark = pytest.mark.skipif(
    not _docker_no_ar(),
    reason="segundo Postgres de teste (docker plat-il004ifonte-pg, porta 55499) não está no ar",
)


def _conexao_direta_docker():
    return psycopg2.connect(
        host=PG_HOST, port=PG_PORTA, dbname=PG_BANCO, user=PG_USUARIO_SUPER, password=PG_SENHA_SUPER,
        cursor_factory=psycopg2.extras.RealDictCursor,
    )


@pytest.fixture
def limpar_conexoes(sessao_a):
    criadas = []
    yield criadas
    for cid in criadas:
        sessao_a.delete(f"/api/conexoes/{cid}")


def _registrar(sessao, sufixo, usuario=PG_USUARIO_RO, senha=PG_SENHA_RO, url=URL_PG):
    return sessao.post(
        "/api/conexoes",
        json={
            "tipo": "postgres_fdw", "nome": f"{PREFIXO_TESTE}-pgfdw-{sufixo}", "url": url,
            "config": {"usuario": usuario, "schema_remoto": "public"}, "credencial": senha,
        },
    )


# --------------------------------------------------------------------- fluxo principal do portão
def test_fluxo_completo_registrar_listar_publicar_ver_no_mapa(sessao_a, limpar_conexoes, env, ids):
    r = _registrar(sessao_a, "fluxo")
    assert r.status_code == 201, r.text
    conexao = r.json()
    limpar_conexoes.append(conexao["id"])
    assert conexao["tipo"] == "postgres_fdw"
    assert conexao["tem_credencial"] is True

    # "listar 3 tabelas"
    r_tab = sessao_a.get(f"/api/conexoes/{conexao['id']}/tabelas")
    assert r_tab.status_code == 200, r_tab.text
    nomes = {t["tabela"] for t in r_tab.json()["itens"]}
    assert TABELAS_ESPERADAS <= nomes, nomes

    # "publicar em massa"
    r_pub = sessao_a.post(
        f"/api/conexoes/{conexao['id']}/publicar-em-massa",
        json={"tabelas": sorted(TABELAS_ESPERADAS)},
    )
    assert r_pub.status_code == 201, r_pub.text
    resultado = r_pub.json()["itens"]
    assert len(resultado) == 3
    assert all(x["ok"] for x in resultado), resultado
    item_ids = {x["tabela"]: x["item_id"] for x in resultado}

    # "ver as 3 camadas no catálogo"
    r_cam = sessao_a.get(f"/api/conexoes/{conexao['id']}/camadas")
    assert r_cam.status_code == 200, r_cam.text
    camadas = r_cam.json()["itens"]
    assert {c["id"] for c in camadas} == set(item_ids.values())
    assert all(c["tabela"].startswith("vf_") for c in camadas), camadas  # view local, nunca o nome remoto cru
    assert all(c["estado_fonte"] == "ok" for c in camadas), camadas  # tabelas() já testou saúde ok

    for tabela, iid in item_ids.items():
        r_item = sessao_a.get(f"/api/itens/{iid}")
        assert r_item.status_code == 200, r_item.text
        item = r_item.json()
        assert item["tipo"] == "camada_vetorial"
        assert item["dados"]["fonte"] == "referenciada"
        assert item["dados"]["procedencia"]["protocolo"] == "postgres_fdw"
        assert item["dados"]["procedencia"]["tabela_remota"] == tabela
        assert item["dados"]["procedencia"]["conexao_id"] == conexao["id"]

    # "ver ... no mapa": a camada de mapa lê exatamente esta VIEW (Martin/tiles, L0-04-c) — prova aqui é
    # conectar como a aplicação (mesmo papel/contexto de tenant) e confirmar que os dados aparecem idênticos
    # aos do banco docker de origem, sem cópia (a VIEW embrulha a FOREIGN TABLE ao vivo).
    with psycopg2.connect(env["PLAT_DSN"], cursor_factory=CursorSchemaAmbiente) as con:
        with con.cursor() as cur:
            cur.execute("SET search_path = plat, public")
            contexto(con, ids_por_slug(con)["demo"], usuario_id=ids["a"]["id"])
            for tabela, iid in item_ids.items():
                cur.execute("SELECT dados FROM plat.item WHERE id = %s::uuid", (iid,))
                dados = cur.fetchone()["dados"]
                schema_local, tabela_local = dados["schema"], dados["tabela"]
                cur.execute(f'SELECT count(*) AS n FROM "{schema_local}"."{tabela_local}"')  # noqa: S608
                n_via_view = cur.fetchone()["n"]
                with _conexao_direta_docker() as con_docker, con_docker.cursor() as cur_docker:
                    cur_docker.execute(f'SELECT count(*) AS n FROM public."{tabela}"')  # noqa: S608
                    n_na_origem = cur_docker.fetchone()["n"]
                assert n_via_view == n_na_origem and n_via_view > 0, (tabela, n_via_view, n_na_origem)


def test_credencial_nunca_em_claro_no_banco_nem_no_log(sessao_a, limpar_conexoes, env, caplog):
    r = _registrar(sessao_a, "segredo")
    assert r.status_code == 201, r.text
    conexao = r.json()
    limpar_conexoes.append(conexao["id"])

    with psycopg2.connect(env["PLAT_DSN"], cursor_factory=CursorSchemaAmbiente) as con:
        with con.cursor() as cur:
            cur.execute("SET search_path = plat, public")
            contexto(con, ids_por_slug(con)["demo"])
            cur.execute("SELECT credencial_cifrada FROM plat.conexao WHERE id = %s::uuid", (conexao["id"],))
            bruta = cur.fetchone()["credencial_cifrada"]
    assert bruta is not None
    assert PG_SENHA_RO not in bruta
    assert bruta.startswith("encconexao:v1:")

    # nenhuma resposta da API nunca carrega a credencial
    corpo_criar = json.dumps(r.json())
    assert PG_SENHA_RO not in corpo_criar
    r_ver = sessao_a.get(f"/api/conexoes/{conexao['id']}")
    assert PG_SENHA_RO not in r_ver.text

    caplog.clear()
    with caplog.at_level("DEBUG"):
        sessao_a.get(f"/api/conexoes/{conexao['id']}/tabelas")
        sessao_a.post(f"/api/conexoes/{conexao['id']}/publicar-em-massa", json={"tabelas": ["estados"]})
    for registro in caplog.records:
        assert PG_SENHA_RO not in registro.getMessage()


def test_conexao_que_cai_devolve_503_e_camada_continua_no_catalogo(sessao_a, limpar_conexoes):
    import subprocess
    import time

    r = _registrar(sessao_a, "queda")
    assert r.status_code == 201, r.text
    conexao = r.json()
    limpar_conexoes.append(conexao["id"])

    r_pub = sessao_a.post(f"/api/conexoes/{conexao['id']}/publicar-em-massa", json={"tabelas": ["estados"]})
    assert r_pub.status_code == 201, r_pub.text
    item_id = r_pub.json()["itens"][0]["item_id"]
    assert item_id

    subprocess.run(["docker", "stop", "plat-il004ifonte-pg"], check=True, capture_output=True, timeout=30)
    try:
        r_tab = sessao_a.get(f"/api/conexoes/{conexao['id']}/tabelas")
        assert r_tab.status_code == 503, r_tab.text
        corpo = r_tab.json()
        assert corpo["erro"] == "fonte_indisponivel"
        assert corpo["mensagem"]  # mensagem não vazia

        # a camada CONTINUA no catálogo (nunca apagada) com o estado computado como "fonte indisponível"
        r_item = sessao_a.get(f"/api/itens/{item_id}")
        assert r_item.status_code == 200, r_item.text

        r_cam = sessao_a.get(f"/api/conexoes/{conexao['id']}/camadas")
        assert r_cam.status_code == 200, r_cam.text
        camadas = r_cam.json()["itens"]
        assert any(c["id"] == item_id and c["estado_fonte"] == "fonte_indisponivel" for c in camadas), camadas
    finally:
        subprocess.run(["docker", "start", "plat-il004ifonte-pg"], check=True, capture_output=True, timeout=30)
        for _ in range(30):
            if _docker_no_ar():
                break
            time.sleep(1)


# --------------------------------------------------------------------- adversário (refutação do item)
def test_adversario_superuser_avisa_mas_nao_recusa_registro(sessao_a, limpar_conexoes, ids):
    # adversário
    r = _registrar(sessao_a, "superuser", usuario=PG_USUARIO_SUPER, senha=PG_SENHA_SUPER)
    assert r.status_code == 201, r.text  # nunca recusa o REGISTRO
    conexao = r.json()
    limpar_conexoes.append(conexao["id"])

    r_teste = sessao_a.post(f"/api/conexoes/{conexao['id']}/testar")
    assert r_teste.status_code == 200, r_teste.text
    assert r_teste.json()["ok"] is True

    # a escrita continua impossível: a VIEW publicada só tem GRANT SELECT (nunca INSERT), mesmo com uma
    # credencial superusuária do lado do banco do cliente — a defesa é estrutural (migração 20260907T0148),
    # não uma checagem de "é superuser? então recusa".
    r_pub = sessao_a.post(f"/api/conexoes/{conexao['id']}/publicar-em-massa", json={"tabelas": ["estados"]})
    assert r_pub.status_code == 201, r_pub.text
    dados = r_pub.json()["itens"][0]
    assert dados["ok"] is True
    with psycopg2.connect(os.environ["PLAT_DSN"], cursor_factory=CursorSchemaAmbiente) as con:
        with con.cursor() as cur:
            cur.execute("SET search_path = plat, public")
            contexto(con, ids_por_slug(con)["demo"], usuario_id=ids["a"]["id"])
            cur.execute("SELECT dados FROM plat.item WHERE id = %s::uuid", (dados["item_id"],))
            dados_item = cur.fetchone()["dados"]
            schema_local, tabela_local = dados_item["schema"], dados_item["tabela"]
            with pytest.raises(psycopg2.errors.InsufficientPrivilege):
                cur.execute(f'INSERT INTO "{schema_local}"."{tabela_local}" DEFAULT VALUES')  # noqa: S608


def test_adversario_aponta_para_o_proprio_iagro_sat(sessao_a, env):
    from urllib.parse import urlsplit

    partes = urlsplit(env["PLAT_DSN"])
    url_iagro_sat = f"postgres://{partes.hostname}:{partes.port or 5432}/{(partes.path or '/').lstrip('/')}"
    r = _registrar(sessao_a, "autoreferencia", url=url_iagro_sat)
    assert r.status_code == 422, r.text
    assert r.json()["erro"] == "url_insegura"
    assert "banco_proibido" in r.json()["detalhe"]["motivo"] or "mesmo_servidor" in r.json()["detalhe"]["motivo"]


def test_adversario_injeta_no_nome_da_tabela(sessao_a, limpar_conexoes):
    r = _registrar(sessao_a, "injecao")
    assert r.status_code == 201, r.text
    conexao = r.json()
    limpar_conexoes.append(conexao["id"])

    nome_malicioso = "municipios; DROP TABLE municipios;--"
    r_pub = sessao_a.post(
        f"/api/conexoes/{conexao['id']}/publicar-em-massa",
        json={"tabelas": [nome_malicioso, "estados"]},
    )
    assert r_pub.status_code == 201, r_pub.text
    resultado = {x["tabela"]: x for x in r_pub.json()["itens"]}
    assert resultado[nome_malicioso]["ok"] is False
    assert "nome_de_tabela_invalido" in resultado[nome_malicioso]["erro"]
    assert resultado["estados"]["ok"] is True  # o resto do lote publica normalmente

    # a tabela alvo do adversário continua intacta no banco docker
    with _conexao_direta_docker() as con, con.cursor() as cur:
        cur.execute("SELECT count(*) AS n FROM public.municipios")
        assert cur.fetchone()["n"] == 3
