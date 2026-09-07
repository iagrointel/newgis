"""Job `inquilino.exportar` (item L0-06-d-exportar-inquilino): monta o pacote completo (ver `motor.py`) e
publica o arquivo na pasta do admin que pediu. Mesmas invariantes do irmão `exportacao.gerar`
(app/exportacao/tarefas.py): nada em memória além do catálogo (pequeno), falha não deixa lixo no disco."""

from __future__ import annotations

import datetime
import json
import time
import uuid
from pathlib import Path

import psycopg2
import psycopg2.extras
from pydantic import BaseModel

from app import limites, objetos
from app.exportacao_inquilino import motor
from app.jobs.registro import Cancelado, FalhaDefinitiva, tarefa

CLASSE_OBJETO = "exportacao_inquilino"


class GerarParametros(BaseModel):
    exportacao_id: uuid.UUID


def _jsonb(valor):
    return psycopg2.extras.Json(valor, dumps=lambda v: json.dumps(v, ensure_ascii=False, default=str))


def _marcar_falha(ctx, exportacao_id: str, erro: str) -> None:
    with ctx.db() as cur:
        cur.execute(
            "UPDATE plat.exportacao_inquilino SET estado = %s, erro = %s, concluido_em = now() "
            "WHERE id = %s::uuid AND estado NOT IN ('pronta','falhou','cancelada','expirada')",
            ("cancelada" if "cancel" in erro.lower() else "falhou", erro[:2000], exportacao_id),
        )


@tarefa(
    nome="inquilino.exportar",
    descricao="Exporta o inquilino inteiro (GeoPackage + catálogo JSON + arquivos + manifesto sha256)",
    parametros=GerarParametros,
    pesado=True,
    memoria_mb=limites.EXPORTACAO_MEMORIA_MB,
    timeout_s=limites.EXPORTACAO_INQUILINO_TIMEOUT_S,
    tentativas=1,
    chave=lambda p: f"exportacao_inquilino:{p.get('exportacao_id')}",
    perfil_minimo="admin",
    ferramentas=("gdal",),
)
def inquilino_exportar(ctx, exportacao_id: uuid.UUID) -> dict:
    eid = str(exportacao_id)
    trabalho = Path(ctx.dir_trabalho)
    inicio = time.monotonic()
    try:
        with ctx.db() as cur:
            cur.execute("SELECT * FROM plat.exportacao_inquilino WHERE id = %s::uuid", (eid,))
            exp = cur.fetchone()
            if exp is None:
                raise FalhaDefinitiva("exportação inexistente")
            if exp["estado"] != "pendente":
                raise FalhaDefinitiva(f"exportação em estado {exp['estado']!r}; esperava 'pendente'")
            cur.execute("UPDATE plat.exportacao_inquilino SET estado = 'gerando' WHERE id = %s::uuid", (eid,))

        ctx.progresso(5, "lendo o catálogo do inquilino")
        with ctx.db() as cur:
            catalogo = motor.montar_catalogo(cur, ctx.tenant_id)

        from app.exportacao import motor as motor_camada
        with ctx.db() as cur:
            estimativa = motor.estimar_bytes(cur, catalogo)["bytes"]
        # o pacote é escrito duas vezes no disco de trabalho (componentes soltos + zip final), daí o dobro
        motor_camada.exigir_disco(trabalho, 2 * estimativa)

        ctx.progresso(20, "gerando o GeoPackage das camadas hospedadas")
        caminho_gpkg = trabalho / "dados.gpkg"
        with ctx.db() as cur:
            camadas = motor.gerar_gpkg(cur, ctx.tenant_id, catalogo, caminho_gpkg, ctx.subprocesso)
        n_camadas = len(camadas)
        ctx.verificar()

        ctx.progresso(50, "compactando os arquivos do inquilino")
        caminho_arquivos = trabalho / "arquivos.zip"
        n_arquivos = motor.gerar_arquivos_zip(catalogo, caminho_arquivos, objetos.ler_stream)

        ctx.progresso(65, "escrevendo o catálogo")
        caminho_catalogo = trabalho / "catalogo.json"
        texto_catalogo = json.dumps(catalogo, ensure_ascii=False, indent=2)
        caminho_catalogo.write_text(texto_catalogo, encoding="utf-8")
        sha_catalogo = motor.sha256_bytes(texto_catalogo.encode("utf-8"))

        ctx.progresso(80, "escrevendo o manifesto")
        caminho_manifesto = trabalho / "manifesto.json"
        manifesto = motor.montar_manifesto(
            {"dados.gpkg": caminho_gpkg, "catalogo.json": caminho_catalogo, "arquivos.zip": caminho_arquivos},
            sha_catalogo,
        )
        caminho_manifesto.write_text(json.dumps(manifesto, ensure_ascii=False, indent=2), encoding="utf-8")

        ctx.progresso(88, "empacotando")
        caminho_pacote = trabalho / "inquilino_exportado.zip"
        motor.empacotar(caminho_pacote, {
            "dados.gpkg": caminho_gpkg, "catalogo.json": caminho_catalogo,
            "arquivos.zip": caminho_arquivos, "manifesto.json": caminho_manifesto,
        })
        bytes_pacote = caminho_pacote.stat().st_size

        ctx.progresso(92, f"enviando {bytes_pacote // 1024} KB ao armazenamento")
        with ctx.db() as cur:
            objeto = objetos.guardar_arquivo(
                cur, CLASSE_OBJETO, caminho_pacote, "application/zip", usuario_id=ctx.usuario_id,
                extensao=".zip",
            )
        nome_arquivo = "inquilino_exportado.zip"
        validade = datetime.timedelta(days=limites.EXPORTACAO_VALIDADE_DIAS)
        item_dados = {
            "chave": objeto["chave"], "sha256": objeto["sha256"], "bytes": objeto["bytes"],
            "content_type": "application/zip", "nome_original": nome_arquivo,
        }
        with ctx.db() as cur:
            cur.execute(
                "INSERT INTO plat.item(tenant_id, tipo, titulo, dono_id, dados, tamanho_bytes, "
                "criado_por, modificado_por) VALUES (%s, 'arquivo', %s, %s, %s, %s, %s, %s) RETURNING id",
                (ctx.tenant_id, nome_arquivo, ctx.usuario_id, _jsonb(item_dados), objeto["bytes"],
                 ctx.usuario_id, ctx.usuario_id),
            )
            arquivo_item_id = str(cur.fetchone()["id"])
            cur.execute(
                "UPDATE plat.exportacao_inquilino SET estado = 'pronta', arquivo_item_id = %s::uuid, "
                "chave = %s, sha256 = %s, bytes = %s, n_itens = %s, n_camadas = %s, n_arquivos = %s, "
                "duracao_ms = %s, concluido_em = now(), expira_em = now() + %s WHERE id = %s::uuid",
                (arquivo_item_id, objeto["chave"], objeto["sha256"], objeto["bytes"], len(catalogo["itens"]),
                 n_camadas, n_arquivos, int((time.monotonic() - inicio) * 1000),
                 validade, eid),
            )
            cur.execute(
                "SELECT plat.evento_registrar('inquilino/exportar', 'inquilino', NULL, %s::jsonb, NULL, NULL)",
                (json.dumps({"exportacao_id": eid, "bytes": objeto["bytes"], "n_camadas": n_camadas,
                             "n_arquivos": n_arquivos, "job_id": str(ctx.job_id)}, default=str),),
            )
        ctx.progresso(100, "concluído")
        return {
            "exportacao_id": eid, "arquivo_item_id": arquivo_item_id, "n_itens": len(catalogo["itens"]),
            "n_camadas": n_camadas, "n_arquivos": n_arquivos, "bytes": objeto["bytes"],
            "sha256": objeto["sha256"], "sha256_catalogo": sha_catalogo,
        }
    except Cancelado:
        _marcar_falha(ctx, eid, "cancelamento solicitado")
        raise
    except FalhaDefinitiva as e:
        _marcar_falha(ctx, eid, str(e))
        raise
    except (psycopg2.Error, motor.ErroExportacaoInquilino, OSError) as e:
        _marcar_falha(ctx, eid, str(e)[:500])
        raise FalhaDefinitiva(str(e)[:500]) from e
