"""Provas do conserto do grupo G4 (laudo `laco/handoffs/T3/ataque-g4-ADVERSARIO.md`).

Os testes do adversário (`tests/api/test_g4_adversario.py`) afirmam o comportamento correto e mudaram de
`xfail(strict=True)` para teste comum conforme cada defeito caiu. Este arquivo cobre o que o ataque não podia
medir de fora: o ciclo completo do apagar (linha, objeto e evento), a permissão de banco depois do conserto e o
caminho legítimo do teto de cota (a plataforma sobe, o inquilino usa, o inquilino não passa).
"""

import base64
import io
import os
import secrets
import subprocess

import pytest
from PIL import Image

from tests.api.conftest import PREFIXO_TESTE, entrar, novo_cliente

SCHEMA = os.environ.get("PLAT_SCHEMA", "plat")


def _psql(sql: str) -> str:
    saida = subprocess.run(
        ["sudo", "-u", "postgres", "psql", "-d", "iagro_sat", "-X", "-A", "-t", "-c",
         sql.replace("plat.", SCHEMA + ".")],
        capture_output=True, text=True, timeout=60,
    )
    assert saida.returncode == 0, saida.stderr
    return saida.stdout.strip()


def _png(cor: tuple) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (64, 64), cor).save(buf, format="PNG")
    return buf.getvalue()


def _logo_novo(sessao_a) -> str:
    cor = (secrets.randbelow(200) + 30, secrets.randbelow(200) + 30, secrets.randbelow(200) + 30)
    r = sessao_a.post("/api/org/logo", json={"conteudo": base64.b64encode(_png(cor)).decode()})
    assert r.status_code == 200, r.text
    return r.json()["logo"]


@pytest.fixture(scope="module")
def visualizador(sessao_a):
    login = f"{PREFIXO_TESTE}{secrets.token_hex(4)}"
    r = sessao_a.post(
        "/api/usuarios",
        json={"login": login, "nome": "G4 conserto visualizador", "perfil": "visualizador",
              "papel_id": None, "email": None},
    )
    assert r.status_code == 201, r.text
    u, temporaria = r.json()["usuario"], r.json()["senha_temporaria"]
    c = novo_cliente()
    assert entrar(c, "demo", login, temporaria).status_code == 200
    senha = "Senha-definitiva-1" + secrets.token_hex(3)
    assert c.put("/api/eu/senha", json={"atual": temporaria, "nova": senha}).status_code == 204
    yield c
    sessao_a.delete(f"/api/usuarios/{u['id']}")


# ---------------------------------------------------------------- achado 1: privilégio e dono nos arquivos
def test_visualizador_nao_le_nem_apaga_e_o_dono_continua_podendo(sessao_a, visualizador):
    sha = _logo_novo(sessao_a)
    assert visualizador.get(f"/api/arquivos/{sha}?classe=org_logo").status_code == 403
    assert visualizador.delete(f"/api/arquivos/{sha}?classe=org_logo").status_code == 403
    # o dono (quem gravou o logotipo) continua lendo e apagando: o conserto não fechou a porta certa
    assert sessao_a.get(f"/api/arquivos/{sha}?classe=org_logo").status_code == 200
    assert sessao_a.delete(f"/api/arquivos/{sha}?classe=org_logo").status_code == 204


def test_ciclo_completo_do_apagar_linha_objeto_e_evento(sessao_a):
    """Achados G4-08 e G4-09 no mesmo ciclo: 204, evento novo, linha marcada como apagada, e a varredura de
    órfãos NÃO acusa a exclusão legítima."""
    sha = _logo_novo(sessao_a)
    vivas_antes = _psql(f"SELECT count(*) FROM plat.arquivo WHERE sha256='{sha}' AND apagado_em IS NULL")
    assert vivas_antes == "1", vivas_antes
    antes = sessao_a.get("/api/eventos?limite=1").json()["total"]
    assert sessao_a.delete(f"/api/arquivos/{sha}?classe=org_logo").status_code == 204
    depois = sessao_a.get("/api/eventos?limite=1").json()["total"]
    assert depois > antes, f"nenhum evento novo ({antes} -> {depois})"
    tipos = [e["tipo"] for e in sessao_a.get("/api/eventos?limite=5").json()["itens"]]
    assert "arquivos/apagar" in tipos, tipos
    vivas_depois = _psql(f"SELECT count(*) FROM plat.arquivo WHERE sha256='{sha}' AND apagado_em IS NULL")
    assert vivas_depois == "0", f"linha continuou viva depois do apagar: {vivas_depois}"
    varredura = sessao_a.get("/api/arquivos/_varredura").json()
    assert [o for o in varredura["sem_objeto"] if o["sha256"] == sha] == [], varredura


# ---------------------------------------------------------------- achado 2: expurgo do rastro
def test_expurgo_de_rastro_valida_argumento_e_filtra_inquilino():
    for f in ("evento_expurgar(int)", "log_expurgar(int)"):
        assert _psql(f"SELECT has_function_privilege('{SCHEMA}_app', '{SCHEMA}.{f}', 'EXECUTE')") == "f", f
    for f in ("evento_expurgar_inquilino(int, int)", "log_expurgar_inquilino(int, int)"):
        assert _psql(f"SELECT has_function_privilege('{SCHEMA}_app', '{SCHEMA}.{f}', 'EXECUTE')") == "f", f
    # argumento inválido levanta em vez de derrubar a partição do mês corrente
    for arg in ("-1", "0", "NULL"):
        saida = subprocess.run(
            ["sudo", "-u", "postgres", "psql", "-d", "iagro_sat", "-X", "-A", "-t",
             "-c", f"SELECT {SCHEMA}.evento_expurgar({arg})"],
            capture_output=True, text=True, timeout=60,
        )
        assert saida.returncode != 0 and "meses_invalido" in saida.stderr, (arg, saida.stdout, saida.stderr)
    # a partição do mês corrente continua de pé
    corrente = _psql(
        "SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
        f"WHERE n.nspname='{SCHEMA}' AND c.relname = 'evento_y' || to_char(now(),'YYYY') || 'm' || to_char(now(),'MM')"
    )
    assert corrente == "1", corrente


def test_expurgo_por_inquilino_nao_alcanca_o_vizinho(sessao_a, sessao_b):
    """A função com filtro apaga LINHA do inquilino pedido e nunca partição — o rastro do vizinho fica."""
    tid_a = _psql("SELECT id FROM plat.tenant WHERE slug='demo'")
    total_b_antes = _psql(f"SELECT count(*) FROM plat.evento WHERE tenant_id <> {tid_a}")
    # 1200 meses = nada a apagar; o que se prova aqui é o filtro e a validação, não a destruição
    n = _psql(f"SELECT plat.evento_expurgar_inquilino({tid_a}, 1200)")
    assert n == "0", n
    total_b_depois = _psql(f"SELECT count(*) FROM plat.evento WHERE tenant_id <> {tid_a}")
    assert total_b_antes == total_b_depois


# ---------------------------------------------------------------- achado 3: teto de cota
def test_inquilino_nao_passa_do_teto_e_a_plataforma_e_quem_move(sessao_a, sessao_plat):
    org = sessao_a.get("/api/org").json()
    corpo = {
        "nome": org["nome"], "cor": org["cor"], "idioma_padrao": org["idioma_padrao"],
        "centro": org["mapa"]["centro"], "zoom": org["mapa"]["zoom"], "basemap": org["mapa"]["basemap"],
        "srid_padrao": org["mapa"]["srid_padrao"], "cota_bytes": org["armazenamento"]["cota_bytes"],
        "cota_usuarios": org["usuarios"]["cota"], "auth": dict(org["auth"]),
    }
    teto_bytes = org["armazenamento"]["cota_bytes_teto"]
    teto_usuarios = org["usuarios"]["cota_teto"]
    tid = int(_psql("SELECT id FROM plat.tenant WHERE slug='demo'"))
    try:
        # 1. acima do teto do inquilino = 422 com o teto no detalhe
        r = sessao_a.put("/api/org", json={**corpo, "cota_bytes": teto_bytes + 1})
        assert r.status_code == 422 and r.json()["erro"] == "cota_acima_do_teto", r.text
        r = sessao_a.put("/api/org", json={**corpo, "cota_usuarios": teto_usuarios + 1})
        assert r.status_code == 422 and r.json()["erro"] == "cota_acima_do_teto", r.text
        # 2. acima do teto ABSOLUTO da instalação nem chega ao banco (validação de esquema)
        r = sessao_a.put("/api/org", json={**corpo, "cota_bytes": 9_000_000_000_000_000_000})
        assert r.status_code == 422 and r.json()["erro"] == "validacao", r.text
        # 3. a cota do bucket do Garage NÃO subiu
        assert _psql(f"SELECT cota_bytes FROM plat.tenant WHERE id={tid}") == str(org["armazenamento"]["cota_bytes"])
        # 4. a plataforma sobe o teto; aí sim o inquilino usa o espaço novo
        novo_teto = teto_bytes + 1024 * 1024 * 1024
        r = sessao_plat.put(
            f"/api/plataforma/inquilinos/{tid}/cotas",
            json={"cota_bytes_teto": novo_teto, "cota_usuarios_teto": teto_usuarios},
        )
        assert r.status_code == 200, r.text
        assert r.json()["cota_bytes_teto"] == novo_teto
        assert sessao_a.put("/api/org", json={**corpo, "cota_bytes": novo_teto}).status_code == 200
        # 5. o admin do inquilino NÃO alcança a rota que move o teto
        r = sessao_a.put(
            f"/api/plataforma/inquilinos/{tid}/cotas",
            json={"cota_bytes_teto": 1024 ** 4, "cota_usuarios_teto": 100},
        )
        assert r.status_code == 404, r.text
    finally:
        sessao_plat.put(
            f"/api/plataforma/inquilinos/{tid}/cotas",
            json={"cota_bytes_teto": teto_bytes, "cota_usuarios_teto": teto_usuarios},
        )
        sessao_a.put("/api/org", json=corpo)


def test_gatilho_do_banco_recusa_cota_acima_do_teto():
    """Defesa em profundidade: mesmo por SQL direto, sem passar pela rota, a cota não passa do teto."""
    saida = subprocess.run(
        ["sudo", "-u", "postgres", "psql", "-d", "iagro_sat", "-X", "-A", "-t",
         "-c", f"UPDATE {SCHEMA}.tenant SET cota_bytes = 9000000000000000000 WHERE slug='demo'"],
        capture_output=True, text=True, timeout=60,
    )
    assert saida.returncode != 0 and "cota_acima_do_teto" in saida.stderr, saida.stderr
    saida = subprocess.run(
        ["sudo", "-u", "postgres", "psql", "-d", "iagro_sat", "-X", "-A", "-t",
         "-c", f"UPDATE {SCHEMA}.tenant SET cota_bytes_teto = 9000000000000000000 WHERE slug='demo'"],
        capture_output=True, text=True, timeout=60,
    )
    assert saida.returncode != 0 and "teto_e_da_plataforma" in saida.stderr, saida.stderr
