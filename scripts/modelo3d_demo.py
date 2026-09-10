"""Bancada dos modelos 3D (item L2-09-c-modelos-gltf-ifc-3dtiles) na base da TRILHA, nunca em produção.

Cria, no inquilino `demo`:

  1. `modelo-caixa (L2-09-c)` — GLB de uma CAIXA de dimensões declaradas (12 x 8 x 20 m), gerado na hora
     pelo mesmo `app/modelos3d/glb.py` que a aplicação lê. Dimensão conhecida ao milímetro é o que faz o
     portão do item ("aparece na posição e escala corretas, com folga de 0,5 m") ser uma MEDIDA.
  2. `modelo-casa (L2-09-c)` — o IFC aberto da buildingSMART (CC BY 4.0, `tests/dados/`), convertido:
     elementos na tabela, glTF no armazenamento e árvore OGC 3D Tiles gerada.
  3. `cena-modelos (L2-09-c)` — o item do tipo `cena` que aponta para os dois, um como glTF posicionado
     e outro como tileset.

Uso:  set -a; source <env da trilha>; set +a
      venv/bin/python scripts/modelo3d_demo.py criar|apagar
Idempotente: `criar` apaga a bancada anterior (mesmo título) antes de recriar.
"""
import json
import os
import secrets
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import psycopg2  # noqa: E402

DSN = os.environ["PLAT_DSN"]
TITULO_CENA = "cena-modelos (L2-09-c)"
NOME_CAIXA = "modelo-caixa (L2-09-c)"
NOME_CASA = "modelo-casa (L2-09-c)"
_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
# Altura ZERO de propósito: a cena da bancada abre com o terreno DESLIGADO, e sem terreno o MapLibre
# desenha o solo na cota zero. Pôr aqui a altitude elipsoidal real do ponto (760 m) deixaria o modelo
# 760 m no ar, fora do campo de visão a zoom 18 — a tela ficaria vazia sem erro nenhum. A altitude do
# ponto continua sendo medida pelos testes de unidade e de API, que não dependem de tela.
ALTURA_CENA_M = 0.0


def _ulid() -> str:
    return secrets.choice("01234567") + "".join(secrets.choice(_CROCKFORD) for _ in range(25))


def _contexto(cur, slug="demo"):
    cur.execute("SELECT usuario_id, tenant_id FROM plat.auth_login(%s, 'admin')", (slug,))
    r = cur.fetchone()
    assert r, f"admin de {slug} não semeado"
    cur.execute("SELECT set_config('plat.tenant_id', %s, false)", (str(r["tenant_id"]),))
    cur.execute("SELECT set_config('plat.usuario_id', %s, false)", (str(r["usuario_id"]),))
    cur.execute("SELECT set_config('plat.login', 'admin', false)")
    return r


class _Ctx:
    """Contexto mínimo de job: a bancada roda a conversão aqui, sem depender do trabalhador da máquina."""

    def __init__(self, tenant_id, usuario_id):
        from app import db as banco
        self.tenant_id = tenant_id
        self.usuario_id = usuario_id
        self._banco = banco
        self._ctx = banco.Contexto(tenant_id, usuario_id, "worker")

    def db(self):
        return self._banco.db(self._ctx)

    def progresso(self, pct, mensagem=""):
        return None

    def entrada(self, item_id, sha256, descricao=""):
        return None


def criar():
    from app import objetos
    from app.modelos3d import servico, tarefas
    from app.schema_ambiente import CursorSchemaAmbiente
    from tests.apoio_modelos3d import IFC_ABERTO, LAT, LON, glb_caixa

    con = psycopg2.connect(DSN, cursor_factory=CursorSchemaAmbiente)
    con.autocommit = False
    saida, t0 = {}, time.perf_counter()
    try:
        with con.cursor() as cur:
            adm = _contexto(cur)
            cur.execute("DELETE FROM plat.modelo3d WHERE nome IN (%s, %s)", (NOME_CAIXA, NOME_CASA))
            # DELETE, não marcação de apagado: a política de escrita de `plat.item` recusa a linha
            # marcada (WITH CHECK), e a bancada não é conteúdo de usuário para ir à lixeira
            cur.execute("DELETE FROM plat.item WHERE titulo = %s", (TITULO_CENA,))
            entradas = {
                NOME_CAIXA: ("gltf", glb_caixa(nome="caixa-da-bancada"), "model/gltf-binary"),
                NOME_CASA: ("ifc", IFC_ABERTO.read_bytes(), "application/octet-stream"),
            }
            ids = {}
            for nome, (origem, dados, tipo) in entradas.items():
                gravado = objetos.guardar(cur, "modelo3d", dados, tipo, usuario_id=adm["usuario_id"])
                modelo = servico.criar(cur, adm["usuario_id"], adm["tenant_id"], {
                    "nome": nome, "origem": origem, "arquivo_sha256": gravado["sha256"],
                    "lon": LON, "lat": LAT, "altura_m": ALTURA_CENA_M, "rotacao_graus": 0.0,
                    "escala": 1.0,
                })
                ids[nome] = modelo["id"]
        con.commit()

        ctx = _Ctx(adm["tenant_id"], adm["usuario_id"])
        for nome, mid in ids.items():
            tarefas.modelo3d_converter(ctx, mid, gerar_tileset=False)
            tarefas.modelo3d_tileset(ctx, mid)
            saida[nome] = mid

        corpo = {
            "camera": {"centro": [LON, LAT], "zoom": 18, "inclinacao": 60, "rotacao": 0},
            "terreno": {"ligado": False},
            "iluminacao": {"modo": "fixa", "azimute": 135.0, "elevacao": 50.0, "intensidade": 0.4},
            "camadas": [], "slides": [],
            "modelos": [
                {"id": _ulid(), "modelo_id": ids[NOME_CASA], "titulo": NOME_CASA, "modo": "gltf"},
                {"id": _ulid(), "modelo_id": ids[NOME_CAIXA], "titulo": NOME_CAIXA, "modo": "tileset",
                 "visivel": False},
            ],
        }
        with con.cursor() as cur:
            _contexto(cur)
            cur.execute(
                "INSERT INTO plat.item(tenant_id, tipo, titulo, dados, dono_id) "
                "VALUES (%s, 'cena', %s, %s::jsonb, %s) RETURNING id",
                (adm["tenant_id"], TITULO_CENA,
                 json.dumps({"esquema_versao": 1, "corpo": corpo}, ensure_ascii=False), adm["usuario_id"]))
            saida["cena"] = str(cur.fetchone()["id"])
        con.commit()
    finally:
        con.close()
    saida["segundos"] = round(time.perf_counter() - t0, 2)
    print(json.dumps(saida, ensure_ascii=False, indent=1))


def apagar():
    from app.schema_ambiente import CursorSchemaAmbiente
    con = psycopg2.connect(DSN, cursor_factory=CursorSchemaAmbiente)
    try:
        with con.cursor() as cur:
            _contexto(cur)
            cur.execute("DELETE FROM plat.modelo3d WHERE nome IN (%s, %s)", (NOME_CAIXA, NOME_CASA))
            cur.execute("DELETE FROM plat.item WHERE titulo = %s", (TITULO_CENA,))
        con.commit()
    finally:
        con.close()
    print("bancada dos modelos 3D apagada")


if __name__ == "__main__":
    acao = sys.argv[1] if len(sys.argv) > 1 else "criar"
    if acao == "criar":
        criar()
    elif acao == "apagar":
        apagar()
    else:
        print(__doc__)
        sys.exit(2)
