"""Bancada de camadas EDITÁVEIS do item L2-03-edicao, na base da TRILHA (nunca produção).

Cria, no inquilino `demo`, duas camadas pequenas com `edicao.habilitada=true`:

  1. `edicao-pontos` (Point): campo `nome` (obrigatório), `categoria` (domínio A/B/C), `ativo` (bool).
     5 pontos de partida perto de Guarulhos, para caber na mesma área que o e2e do L2-01-mapa-web usa.
  2. `edicao-linhas` (LineString): campo `nome`, sem regra — usada nos testes de dividir/unir.

Idempotente: `criar` apaga a bancada anterior (mesma marca) antes de recriar.

Uso: set -a; source <env da trilha>; set +a; venv/bin/python scripts/edicao_demo_camadas.py criar|apagar
"""
import json
import os
import secrets
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import psycopg2  # noqa: E402

DSN = os.environ["PLAT_DSN"]
MARCA = "edicao-l2-03"


def _hex16():
    return secrets.token_hex(8)


def _contexto(cur, slug):
    cur.execute("SELECT usuario_id, tenant_id FROM plat.auth_login(%s, 'admin')", (slug,))
    r = cur.fetchone()
    assert r, f"admin de {slug} não semeado"
    cur.execute("SELECT set_config('plat.tenant_id', %s, false)", (str(r["tenant_id"]),))
    cur.execute("SELECT set_config('plat.usuario_id', %s, false)", (str(r["usuario_id"]),))
    cur.execute("SELECT set_config('plat.login', 'admin', false)")
    return r


def _publicar(cur, adm, titulo, tabela, tipo, campos, edicao, regras_campo=None, simbologia=None):
    esquema = "d_demo"
    cur.execute("SELECT plat.camada_preparar(%s, %s, 4326, %s, %s)", (esquema, tabela, tipo, adm["usuario_id"]))
    cur.execute(f'SELECT ST_Extent(geom)::text AS e, count(*) AS n FROM "{esquema}"."{tabela}"')
    r = cur.fetchone()
    caixa = r["e"] or ""
    nums = [float(v) for v in caixa.replace("BOX(", "").replace(")", "").replace(",", " ").split()] if caixa else []
    dados = {"schema": esquema, "tabela": tabela, "geometria": tipo, "srid": 4326, "campos": campos,
             "fonte": "hospedada", "marca": MARCA, "n_feicoes": r["n"],
             "extensao": nums if len(nums) == 4 else None, "edicao": edicao}
    if regras_campo:
        dados["regras_campo"] = regras_campo
    if simbologia:
        dados["simbologia"] = simbologia
    cur.execute("INSERT INTO plat.item(tenant_id, tipo, titulo, dono_id, criado_por, dados) "
                "VALUES (%s, 'camada_vetorial', %s, %s, %s, %s::jsonb) RETURNING id",
                (adm["tenant_id"], titulo, adm["usuario_id"], adm["usuario_id"], json.dumps(dados)))
    item = cur.fetchone()["id"]
    cur.execute("SELECT plat.camada_tile_garantir(%s, %s, %s) AS f", (esquema, tabela, item))
    return {"item": str(item), "tabela": tabela, "funcao": cur.fetchone()["f"], "n": r["n"], "titulo": titulo}


def criar():
    from app.schema_ambiente import CursorSchemaAmbiente
    con = psycopg2.connect(DSN, cursor_factory=CursorSchemaAmbiente)
    con.autocommit = False
    saida = {}
    try:
        with con.cursor() as cur:
            adm = _contexto(cur, "demo")

            t = "c_" + _hex16()
            # `ordem`/`calc` (item L2-03-f): campo numérico de entrada e campo alvo para "calcular campo" no e2e
            cur.execute(f'CREATE TABLE "d_demo"."{t}" (fid bigserial PRIMARY KEY, nome text, categoria text, '
                        f'ativo boolean, ordem integer, calc double precision, geom geometry(Point, 4326))')
            cur.execute(
                f'INSERT INTO "d_demo"."{t}" (nome, categoria, ativo, ordem, geom) VALUES '
                "('ponto um', 'A', true, 1, ST_SetSRID(ST_MakePoint(-46.533, -23.462), 4326)), "
                "('ponto dois', 'B', false, 2, ST_SetSRID(ST_MakePoint(-46.528, -23.458), 4326)), "
                "('ponto tres', 'C', true, 3, ST_SetSRID(ST_MakePoint(-46.520, -23.470), 4326))"
            )
            cur.execute(f'CREATE INDEX ON "d_demo"."{t}" USING gist(geom)')
            saida["pontos"] = _publicar(
                cur, adm, "edicao-pontos (L2-03, editável)", t, "Point",
                [{"nome": "nome", "tipo": "text"}, {"nome": "categoria", "tipo": "text"},
                 {"nome": "ativo", "tipo": "boolean"}, {"nome": "ordem", "tipo": "integer"},
                 {"nome": "calc", "tipo": "double precision"}],
                edicao={"habilitada": True},
                regras_campo={"nome": {"obrigatorio": True}, "categoria": {"dominio_valores": ["A", "B", "C"]}},
                simbologia={"tipo": "simples", "cor": "#d9822b"},
            )

            t2 = "c_" + _hex16()
            cur.execute(f'CREATE TABLE "d_demo"."{t2}" (fid bigserial PRIMARY KEY, nome text, '
                        f'geom geometry(LineString, 4326))')
            cur.execute(
                f'INSERT INTO "d_demo"."{t2}" (nome, geom) VALUES '
                "('trecho um', ST_SetSRID(ST_MakeLine(ST_MakePoint(-46.560, -23.480), "
                "ST_MakePoint(-46.500, -23.480)), 4326))"
            )
            cur.execute(f'CREATE INDEX ON "d_demo"."{t2}" USING gist(geom)')
            saida["linhas"] = _publicar(
                cur, adm, "edicao-linhas (L2-03, editável)", t2, "LineString",
                [{"nome": "nome", "tipo": "text"}], edicao={"habilitada": True},
                simbologia={"tipo": "simples", "cor": "#2b7fd9"},
            )
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()
    print(json.dumps(saida, ensure_ascii=False, indent=2))


def apagar():
    # DELETE cru em plat.item não basta (achado do e2e do L2-03-edicao): a linha sobrevive em silêncio —
    # mesmo padrão de scripts/mapa_demo_camadas.py, item precisa ir para a lixeira e ser expurgado.
    from app.schema_ambiente import CursorSchemaAmbiente
    con = psycopg2.connect(DSN, cursor_factory=CursorSchemaAmbiente)
    con.autocommit = False
    try:
        with con.cursor() as cur:
            _contexto(cur, "demo")
            cur.execute("SELECT id, dados->>'schema' AS esquema, dados->>'tabela' AS tabela FROM plat.item "
                        "WHERE dados->>'marca' = %s AND apagado_em IS NULL", (MARCA,))
            linhas = cur.fetchall()
            for r in linhas:
                cur.execute("SELECT plat.item_lixeira(%s::uuid, true)", (r["id"],))
                cur.execute("SELECT plat.item_expurgar(%s::uuid)", (r["id"],))
                cur.execute("SELECT plat.camada_tile_apagar(%s, %s)", (r["esquema"], r["tabela"]))
                cur.execute(f'DROP TABLE IF EXISTS "{r["esquema"]}"."{r["tabela"]}" CASCADE')
            print(f"apagadas {len(linhas)} camada(s)")
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


if __name__ == "__main__":
    acao = sys.argv[1] if len(sys.argv) > 1 else ""
    if acao == "criar":
        criar()
    elif acao == "apagar":
        apagar()
    else:
        print(__doc__)
        sys.exit(2)
