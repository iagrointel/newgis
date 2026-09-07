"""Prova de que a exportação de um inquilino NUNCA traz linha de outro (exigência do gerente para este item,
acima do portão: "exportação mexe com dado de cliente").

O teste ataca a mesma pergunta por três caminhos, do mais externo ao mais interno — porque cada um deles
falharia por um motivo diferente se o isolamento fosse frouxo:

1. **Pela API.** O administrador do inquilino A pede a exportação do item do inquilino B: 404 (a RLS de
   `plat.item` esconde o item alheio; 403 já seria vazamento, porque confirmaria que o item existe).
2. **Pelo job, com o pedido FORJADO.** A linha de `plat.exportacao` é inserida À MÃO no inquilino A apontando
   para o item do inquilino B (é o que um atacante faria se conseguisse escrever no banco pela aplicação, ou
   o que um bug de programação faria sozinho) e o job é executado. O job tem de falhar dizendo que a camada
   não existe — porque ele relê o item sob a RLS do inquilino DO JOB e nunca aceita schema/tabela do pedido.
3. **Pelo ogr2ogr, que é quem de fato lê a tabela.** O `ogr2ogr` abre conexão própria, fora do pool da
   aplicação; a única coisa que o mantém dentro do inquilino é o `options='-c plat.tenant_id=N'` da string de
   conexão. O teste roda o MESMO comando três vezes sobre a tabela do inquilino B: com o contexto de B (traz
   as 1.000 linhas), com o contexto de A (traz 0) e sem contexto nenhum (traz 0). É o PostgreSQL, não o nosso
   código, que faz o corte.

E, por fim, confere o conteúdo: o arquivo exportado por A tem exatamente as 100 mil feições de A e nenhuma
linha cujo nome comece com o prefixo das feições de B.
"""

from __future__ import annotations

import json
import subprocess
import uuid

from app.exportacao import motor
from tests.api.exportacao.conftest import conexao, esperar_exportacao
from tests.api.exportacao.test_exportacao import baixar_para

PREFIXO_B = "OUTRO-INQUILINO"


def _conninfo_sem_contexto() -> str:
    """A MESMA string de conexão do motor, sem o `options='-c plat.tenant_id=...'` — é o que o código faria se
    alguém removesse a linha que põe o inquilino no contexto."""
    import psycopg2.extensions

    from app.settings import settings

    partes = psycopg2.extensions.parse_dsn(settings.PLAT_DSN)
    pares = " ".join(f"{k}={v}" for k, v in partes.items() if k in ("dbname", "host", "port", "user", "password"))
    return f"PG:{pares}"


def _contexto(cur, tenant_id: int, usuario_id: int) -> None:
    cur.execute(
        "SELECT set_config('plat.tenant_id', %s, true), set_config('plat.usuario_id', %s, true), "
        "set_config('plat.login', 'teste-cruzado', true)",
        (str(tenant_id), str(usuario_id)),
    )


def test_1_api_recusa_o_item_do_outro_inquilino_com_404(inquilino_a, inquilino_b, camada_a, camada_b):
    r = inquilino_a.admin.post("/api/exportacoes", json={"item_id": camada_b["item_id"], "formato": "gpkg"})
    assert r.status_code == 404, r.text
    r = inquilino_b.admin.post("/api/exportacoes", json={"item_id": camada_a["item_id"], "formato": "gpkg"})
    assert r.status_code == 404, r.text


def test_2_pedido_forjado_no_banco_falha_no_job(inquilino_a, inquilino_b, camada_a, camada_b,
                                                worker_exportacao, env):
    """Insere a exportação à mão no inquilino A apontando para a camada do inquilino B e manda o job rodar."""
    eid = str(uuid.uuid4())
    con = conexao(env)
    try:
        with con.cursor() as cur:
            _contexto(cur, inquilino_a.id, inquilino_a.admin_id)
            cur.execute(
                "INSERT INTO plat.exportacao(id, tenant_id, usuario_id, item_id, formato, parametros) "
                "VALUES (%s::uuid, %s, %s, %s::uuid, 'gpkg', %s::jsonb)",
                (eid, inquilino_a.id, inquilino_a.admin_id, camada_b["item_id"], json.dumps({})),
            )
        con.commit()
    finally:
        con.close()
    r = inquilino_a.admin.post("/api/jobs", json={"tipo": "exportacao.gerar",
                                                 "parametros": {"exportacao_id": eid}})
    assert r.status_code == 201, r.text
    final = esperar_exportacao(inquilino_a.admin, eid, timeout=180)
    assert final["estado"] == "falhou", final
    assert "não existe" in (final["erro"] or ""), final["erro"]
    assert final["bytes"] is None and final["feicoes"] is None, final


def test_3_ogr2ogr_so_ve_o_inquilino_do_contexto(inquilino_a, inquilino_b, camada_b, tmp_path):
    """A RLS vale DENTRO do ogr2ogr: mesma tabela, mesma consulta, três contextos, três resultados."""
    sql = f'SELECT fid, nome, geom FROM "{camada_b["schema"]}"."{camada_b["tabela"]}"'
    casos = {
        "dono (inquilino B)": motor.conninfo_pg(inquilino_b.id, inquilino_b.admin_id),
        "outro (inquilino A)": motor.conninfo_pg(inquilino_a.id, inquilino_a.admin_id),
        "sem contexto": _conninfo_sem_contexto(),
    }
    contagens = {}
    for rotulo, conninfo in casos.items():
        destino = tmp_path / f"{rotulo.split()[0]}.gpkg"
        r = subprocess.run(["ogr2ogr", "-f", "GPKG", str(destino), conninfo, "-sql", sql, "-nln", "camada"],
                           capture_output=True, text=True, timeout=600)
        assert r.returncode == 0, (rotulo, r.stderr[:400])
        if not destino.exists():
            contagens[rotulo] = 0
            continue
        info = subprocess.run(["ogrinfo", "-so", "-al", str(destino)], capture_output=True, text=True)
        linhas = [li for li in info.stdout.splitlines() if li.strip().startswith("Feature Count:")]
        contagens[rotulo] = int(linhas[0].split(":", 1)[1]) if linhas else 0
    assert contagens["dono (inquilino B)"] == camada_b["feicoes"], contagens
    assert contagens["outro (inquilino A)"] == 0, contagens
    assert contagens["sem contexto"] == 0, contagens


def test_4_arquivo_exportado_por_a_nao_tem_nenhuma_linha_de_b(inquilino_a, camada_a, camada_b,
                                                              worker_exportacao, tmp_path):
    """Conteúdo, não só contagem: nenhum registro do arquivo de A traz o prefixo das feições de B."""
    from tests.api.exportacao.conftest import exportar

    final = exportar(inquilino_a.admin, {"item_id": camada_a["item_id"], "formato": "csv",
                                         "nome": "zt-cruzado", "campos": ["nome"]}, timeout=600)
    assert final["estado"] == "pronta", final
    caminho = baixar_para(inquilino_a.admin, final["id"], tmp_path / "cruzado.csv")
    texto = caminho.read_text(encoding="utf-8")
    assert PREFIXO_B not in texto
    assert texto.count("\n") - 1 == camada_a["feicoes"] == final["feicoes"]
