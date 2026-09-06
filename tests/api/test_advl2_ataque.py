"""Ataque adversarial independente aos três itens L2 entregues em 06/09 (sessão worktrees-2).

Alvos: L2-04-a-leitor-rls-martin (stac), L2-01-a-documento-mapa (stac), L2-10-a-dominios-subtipos (garage).
Cada achado é um teste xfail(strict=True): o teste afirma o comportamento CORRETO (que hoje NÃO vale); o
xfail documenta a falha e vira xpass quando o construtor consertar. O que NÃO é achado (defesa que segurou)
é um teste normal, verde, que fixa a garantia. Nada aqui conserta o código dos alvos.

Sobe na base da trilha `advl2` (schema plat_tadvl2), nunca no `plat` de produção.
"""

from __future__ import annotations

import secrets
import time

import psycopg2
import pytest

from app.schema_ambiente import CursorSchemaAmbiente
from tests.api.test_dominios_subtipos import Camada, Inquilino, codificado  # fixtures de apoio
from tests.api.test_rls import contexto

_ULID_ALFA = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def _ulid() -> str:
    import random
    return "0" + "".join(random.choice(_ULID_ALFA) for _ in range(25))


# ------------------------------------------------------------------ apoio: dois inquilinos com camada + mapa
@pytest.fixture
def con2(env):
    c = psycopg2.connect(env["PLAT_DSN"], cursor_factory=CursorSchemaAmbiente)
    c.autocommit = False
    yield c
    c.rollback()
    c.close()


@pytest.fixture
def par(sessao_plat, con2):
    """Inquilino A e B, cada um com uma camada vetorial (campo texto 'uf') e um mapa que a referencia."""
    a = Inquilino(sessao_plat)
    b = Inquilino(sessao_plat)
    campos = [{"nome": "uf", "tipo": "text"}]
    cam_a = Camada(con2, a, campos)
    cam_b = Camada(con2, b, campos)

    def mapa(sessao, ref, cid=None):
        cid = cid or _ulid()
        r = sessao.post("/api/mapas", json={
            "titulo": "zt mapa " + secrets.token_hex(3),
            "dados": {"esquema_versao": 1, "corpo": {"camadas": [{"id": cid, "ref": ref}]}},
        })
        assert r.status_code == 201, r.text
        return r.json()["id"]

    mapa_a = mapa(a.admin, cam_a.item_id)
    mapa_b = mapa(b.admin, cam_b.item_id)
    dados = {"a": a, "b": b, "cam_a": cam_a, "cam_b": cam_b, "mapa_a": mapa_a, "mapa_b": mapa_b, "mapa": mapa}
    yield dados
    for cam in (cam_a, cam_b):
        try:
            cam.apagar()
        except Exception:
            con2.rollback()
    a.apagar()
    b.apagar()


# ================================================================== ITEM 2 — documento de mapa
def test_2_id_direto_de_outro_inquilino_404_em_todas_as_rotas(par):
    """A não pode ver o mapa de B por id direto em nenhuma rota /api/mapas."""
    a, mapa_b = par["a"], par["mapa_b"]
    for metodo, rota, kw in [
        ("get", f"/api/mapas/{mapa_b}", {}),
        ("get", f"/api/mapas/{mapa_b}/completo", {}),
        ("get", f"/api/mapas/{mapa_b}/completo?incluir_documento=true", {}),
        ("put", f"/api/mapas/{mapa_b}", {"json": {"titulo": "invadido"}}),
    ]:
        r = getattr(a.admin, metodo)(rota, **kw)
        assert r.status_code == 404, (metodo, rota, r.status_code, r.text)


def test_2_referencia_a_camada_de_outro_inquilino_404_no_salvar(par):
    """Criar/editar mapa de A referenciando a camada de B = 404 (mesma resposta de uuid inexistente)."""
    a, cam_b = par["a"], par["cam_b"]
    r = a.admin.post("/api/mapas", json={
        "titulo": "zt cruzado", "dados": {"esquema_versao": 1,
                                           "corpo": {"camadas": [{"id": _ulid(), "ref": cam_b.item_id}]}}})
    assert r.status_code == 404, r.text
    inexistente = "00000000-0000-0000-0000-000000000000"
    r2 = a.admin.post("/api/mapas", json={
        "titulo": "zt inexistente", "dados": {"esquema_versao": 1,
                                              "corpo": {"camadas": [{"id": _ulid(), "ref": inexistente}]}}})
    assert r2.status_code == 404, r2.text


def test_2_completo_com_camada_alheia_nao_vaza_titulo(par):
    """/completo do mapa de B, pedido pela sessão de B, resolve; pela de A é 404 (não meio-mapa)."""
    a, b, mapa_b = par["a"], par["b"], par["mapa_b"]
    assert b.admin.get(f"/api/mapas/{mapa_b}/completo").status_code == 200
    assert a.admin.get(f"/api/mapas/{mapa_b}/completo").status_code == 404


def test_2_apagar_camada_em_uso_por_mapa_da_409(par):
    """Apagar a camada que o mapa referencia = 409 (relação item->camada)."""
    a, cam_a = par["a"], par["cam_a"]
    r = a.admin.delete(f"/api/itens/{cam_a.item_id}")
    assert r.status_code == 409, r.text


def test_2_404_alheio_e_inexistente_nao_diferem_no_tempo(par):
    """O 404 de mapa de outro inquilino e o de uuid inexistente não podem ter tempo de resposta distinguível
    (canal lateral). Mede medianas de 40 chamadas cada e exige diferença < 3 ms e razão < 1.5x."""
    a, mapa_b = par["a"], par["mapa_b"]
    inexistente = "11111111-2222-3333-4444-555555555555"

    def medir(uuid_):
        ts = []
        for _ in range(40):
            t = time.perf_counter()
            a.admin.get(f"/api/mapas/{uuid_}")
            ts.append(time.perf_counter() - t)
        ts.sort()
        return ts[len(ts) // 2]

    for _ in range(8):  # aquece
        a.admin.get(f"/api/mapas/{mapa_b}")
        a.admin.get(f"/api/mapas/{inexistente}")
    m_alheio = medir(mapa_b)
    m_inex = medir(inexistente)
    dif_ms = abs(m_alheio - m_inex) * 1000
    razao = max(m_alheio, m_inex) / max(min(m_alheio, m_inex), 1e-9)
    assert dif_ms < 3.0 and razao < 1.5, f"alheio={m_alheio*1000:.3f}ms inex={m_inex*1000:.3f}ms dif={dif_ms:.3f}ms razao={razao:.2f}"


# ================================================================== ITEM 3 — domínios/subtipos
def _dominio(sessao, **corpo):
    corpo.setdefault("nome", "zt dom " + secrets.token_hex(3))
    r = sessao.post("/api/dominios", json=corpo)
    assert r.status_code == 201, r.text
    return r.json()


@pytest.mark.xfail(strict=True, raises=psycopg2.errors.SyntaxError,
                   reason="ACHADO adversario: nome de dominio com o dollar-tag fixo $corpo_gerado$ quebra a "
                   "geracao da funcao de validacao (syntax error). A API filtra $, mas a migracao declara que "
                   "mudanca por psql regenera igual. Injecao/DoS no gerador de L2-10-a.")
def test_3_injecao_dollar_tag_no_nome_do_dominio(par, con2):
    """Um domínio ligado a um campo, cujo NOME contém o dollar-tag do gerador, deve continuar regenerando e
    validando (o gerador tem de ser robusto ao texto que embute). Hoje o INSERT seguinte estoura com erro de
    sintaxe do PostgreSQL, porque o gerador embute o nome verbatim entre $corpo_gerado$...$corpo_gerado$."""
    a, cam_a = par["a"], par["cam_a"]
    d = _dominio(a.admin, tipo="codificado", tipo_campo="text",
                 valores=[{"codigo": "SP", "descricao": "x"}, {"codigo": "RJ", "descricao": "y"}])
    assert a.admin.post(f"/api/camadas/{cam_a.item_id}/dominios",
                        json={"campo": "uf", "dominio_id": d["id"]}).status_code == 201
    # nome maligno por SQL (o CHECK do banco só limita comprimento; a API é que barra o $ — e a migração diz
    # que a API não é a guarda). O AFTER trigger de plat.dominio regenera a função da camada.
    contexto(con2, a.id, usuario_id=a.admin_id, login="admin")
    with con2.cursor() as cur:
        cur.execute("UPDATE plat.dominio SET nome = %s WHERE id = %s::uuid",
                    ("regiao $corpo_gerado$ x", d["id"]))
    con2.commit()
    # Se o gerador fosse robusto, um código válido entraria e um inválido seria recusado com nome nomeado:
    contexto(con2, a.id, usuario_id=a.admin_id, login="admin")
    with con2.cursor() as cur:
        cur.execute(f"INSERT INTO {cam_a.esquema}.{cam_a.tabela} (geom, uf) "
                    f"VALUES (ST_SetSRID(ST_MakePoint(-46.5,-23.5),4326), 'SP') RETURNING fid")
        assert cur.fetchone()["fid"] > 0
    con2.rollback()


def test_3_dois_inquilinos_mesmo_nome_de_dominio_nao_colidem(par):
    """A e B podem ter domínio com o MESMO nome; cada função gerada é por item (uuid), sem colisão."""
    a, b, cam_a, cam_b = par["a"], par["b"], par["cam_a"], par["cam_b"]
    nome = "Estados " + secrets.token_hex(2)
    da = _dominio(a.admin, nome=nome, tipo="codificado", tipo_campo="text",
                  valores=[{"codigo": "SP", "descricao": "x"}])
    db = _dominio(b.admin, nome=nome, tipo="codificado", tipo_campo="text",
                  valores=[{"codigo": "RS", "descricao": "z"}])
    assert a.admin.post(f"/api/camadas/{cam_a.item_id}/dominios",
                        json={"campo": "uf", "dominio_id": da["id"]}).status_code == 201
    assert b.admin.post(f"/api/camadas/{cam_b.item_id}/dominios",
                        json={"campo": "uf", "dominio_id": db["id"]}).status_code == 201
    # cada camada valida contra o SEU domínio: 'SP' entra em A e é recusado em B (que só tem 'RS')
    assert cam_a.inserir(uf="SP") > 0
    cam_a.con.rollback()
    with pytest.raises(psycopg2.errors.RaiseException):
        cam_b.inserir(uf="SP")
    cam_b.con.rollback()


def test_3_valor_em_uso_conta_so_o_proprio_inquilino(par):
    """O 409 de 'valor em uso' de A não pode contar usos de um domínio homônimo em B. A usa 'SP', B usa 'RS';
    remover 'RS' do domínio de A tem de ser permitido (A não usa 'RS'), provando que a contagem é por
    inquilino, não global."""
    a, b, cam_a, cam_b = par["a"], par["b"], par["cam_a"], par["cam_b"]
    valores = [{"codigo": "SP", "descricao": "x"}, {"codigo": "RS", "descricao": "z"}]
    da = _dominio(a.admin, tipo="codificado", tipo_campo="text", valores=valores)
    db = _dominio(b.admin, tipo="codificado", tipo_campo="text", valores=valores)
    assert a.admin.post(f"/api/camadas/{cam_a.item_id}/dominios",
                        json={"campo": "uf", "dominio_id": da["id"]}).status_code == 201
    assert b.admin.post(f"/api/camadas/{cam_b.item_id}/dominios",
                        json={"campo": "uf", "dominio_id": db["id"]}).status_code == 201
    cam_a.inserir(uf="SP"); cam_a.con.commit()
    cam_b.inserir(uf="RS"); cam_b.con.commit()
    # A remove 'RS' (que só B usa): deve passar. Se contasse B, viria 409.
    r = a.admin.put(f"/api/dominios/{da['id']}", json={
        "nome": "zt dom " + secrets.token_hex(3), "tipo": "codificado", "tipo_campo": "text",
        "valores": [{"codigo": "SP", "descricao": "x"}]})
    assert r.status_code == 200, ("contagem vazou de outro inquilino?", r.status_code, r.text)


# ================================================================== ITEM 1 — leitor/RLS/tile por token
# Estas provas precisam do papel de leitura com LOGIN (db/leitor_instalar.sh mexe em pg_hba.conf -> sudo).
import hashlib  # noqa: E402
import json as _json  # noqa: E402
import os  # noqa: E402
import re  # noqa: E402
import subprocess  # noqa: E402


def _token_novo():
    v = "plat_" + secrets.token_urlsafe(64).replace("-", "x").replace("_", "y")[:43]
    return v, hashlib.sha256(v.encode()).hexdigest()


@pytest.fixture(scope="module")
def leitor_conn(env, tmp_path_factory):
    from tests.conftest import ROOT

    if subprocess.run(["sudo", "-n", "true"], capture_output=True).returncode != 0:
        pytest.skip("sem sudo sem senha: o instalador do papel de leitura mexe no pg_hba.conf")
    cred = tmp_path_factory.mktemp("cred_adv")
    esquema = env.get("PLAT_SCHEMA") or "plat"
    r = subprocess.run(
        ["sudo", "-n", "env", f"PLAT_SCHEMA={esquema}", f"CRED_DIR={cred}",
         f"CRED_DONO={os.environ.get('USER') or os.getlogin()}", "bash", str(ROOT / "db" / "leitor_instalar.sh"),
         re.sub(r"^.*/", "", env["PLAT_DSN"].split("?")[0])],
        capture_output=True, text=True, cwd=ROOT)
    assert r.returncode == 0, r.stderr
    dsn = (cred / "PLAT_DSN_LEITOR").read_text().strip()
    con = psycopg2.connect(dsn, cursor_factory=CursorSchemaAmbiente)
    con.autocommit = False
    yield con
    con.rollback()
    con.close()


@pytest.fixture
def camada_com_token(env, sessao_plat, con2):
    """Um inquilino com DUAS camadas (X e Y) e um token de serviço com escopo SÓ da camada X."""
    inq = Inquilino(sessao_plat)
    cam_x = Camada(con2, inq, [{"nome": "nome", "tipo": "text"}])
    cam_y = Camada(con2, inq, [{"nome": "nome", "tipo": "text"}])
    for cam in (cam_x, cam_y):
        contexto(con2, inq.id, usuario_id=inq.admin_id, login="admin")
        with con2.cursor() as cur:
            cur.execute(f"INSERT INTO {cam.esquema}.{cam.tabela} (geom, nome) "
                        f"VALUES (ST_SetSRID(ST_MakePoint(-47.9,-15.8),4326), 'a')")
            cur.execute("SELECT plat.camada_tile_garantir(%s,%s,%s::uuid)", (cam.esquema, cam.tabela, cam.item_id))
        con2.commit()
    valor, hash_ = _token_novo()
    contexto(con2, inq.id, usuario_id=inq.admin_id, login="admin")
    with con2.cursor() as cur:
        cur.execute("INSERT INTO plat.token_servico(tenant_id,usuario_id,nome,token_hash,prefixo,escopos) "
                    "VALUES (%s,%s,%s,%s,%s,%s)",
                    (inq.id, inq.admin_id, "zt-adv-" + secrets.token_hex(3), hash_, valor[:8],
                     ["camada:ler:" + cam_x.item_id]))
    con2.commit()
    dados = {"inq": inq, "cam_x": cam_x, "cam_y": cam_y, "token_x": valor}
    yield dados
    for cam in (cam_x, cam_y):
        try:
            cam.apagar()
        except Exception:
            con2.rollback()
    inq.apagar()


def test_1_token_escopo_de_camada_X_recusado_na_funcao_de_tile_de_Y(leitor_conn, camada_com_token):
    """DEFESA que segura: a função de tile de Y, chamada com o token escopado só para X, recusa com
    escopo_insuficiente (o caminho que o Martin usa está correto)."""
    c = camada_com_token
    with leitor_conn.cursor() as cur, pytest.raises(psycopg2.Error) as e:
        cur.execute(f'SELECT "{c["cam_y"].esquema}"."t_{c["cam_y"].tabela[2:]}"(0,0,0,%s::json)',
                    (_json.dumps({"token": c["token_x"]}),))
    assert "escopo_insuficiente" in str(e.value)
    leitor_conn.rollback()


@pytest.mark.xfail(strict=True, reason="ACHADO adversario (fronteira): a PROVA que a RLS do leitor exige e por "
                   "INQUILINO, nao por item. Um token escopado a UMA camada (camada:ler:<X>), depois de passar "
                   "por contexto_por_token, poe uma prova valida para o inquilino inteiro; o papel de leitura "
                   "consegue entao SELECT direto em OUTRA camada do mesmo inquilino, fora do escopo do token. "
                   "A funcao de tile barra por item (test acima); o SELECT direto, nao. Precondicao: credencial "
                   "do papel de leitura + um token estreito. O portao do item so exige isolamento por INQUILINO "
                   "(que se mantem), por isso e fronteira, nao quebra de clausula.")
def test_1_escopo_por_item_nao_e_forcado_no_select_direto(leitor_conn, camada_com_token):
    """Correto seria: um token escopado a X nao dar leitura de Y nem por SELECT direto. Hoje da (escalada de
    escopo dentro do inquilino)."""
    c = camada_com_token
    with leitor_conn.cursor() as cur:
        cur.execute("SELECT plat.contexto_por_token(%s,NULL,NULL,%s::uuid,'camada:ler') t",
                    (c["token_x"], c["cam_x"].item_id))
        cur.execute(f'SELECT count(*) n FROM "{c["cam_y"].esquema}"."{c["cam_y"].tabela}"')
        lidas = cur.fetchone()["n"]
    leitor_conn.rollback()
    assert lidas == 0, f"token de X leu {lidas} linha(s) de Y por SELECT direto (escalada de escopo)"
