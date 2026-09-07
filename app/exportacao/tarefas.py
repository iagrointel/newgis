"""Job `exportacao.gerar` (item L0-04-h-exportar; ADR 0018): lê a camada sob a RLS do inquilino, escreve o
arquivo no diretório de trabalho do job, converte o que o GDAL não faz, envia ao Garage em partes e publica um
item `arquivo` na pasta do usuário com validade de 7 dias.

Invariantes (as mesmas do `ingestao.carregar`, que é o irmão deste job):
- nada do pedido do cliente entra em texto de SQL (ver `app/exportacao/motor.py`);
- falha ou cancelamento em qualquer passo não deixa arquivo temporário nem item pela metade;
- o arquivo NUNCA é lido inteiro em memória: `ogr2ogr` escreve no disco, `objetos.guardar_arquivo` lê em
  blocos de 8 MiB e a entrega (`GET .../baixar`) devolve em blocos de 1 MiB;
- a contagem de feições que vai para o relatório é lida do ARQUIVO GERADO, não do banco.
"""

from __future__ import annotations

import datetime
import json
import uuid
from pathlib import Path

import psycopg2
import psycopg2.extras
from pydantic import BaseModel

from app import limites, objetos
from app.consulta import where_ast
from app.consulta.cql2 import colunas_da_camada
from app.exportacao import csv_saida, motor
from app.exportacao.formatos import obter as formato_de
from app.jobs.registro import Cancelado, FalhaDefinitiva, tarefa
from app.mapa import pacote as pacote_mod

CLASSE_OBJETO = "exportacao"


class GerarParametros(BaseModel):
    exportacao_id: uuid.UUID


def _jsonb(valor):
    return psycopg2.extras.Json(valor, dumps=lambda v: json.dumps(v, ensure_ascii=False, default=str))


def _marcar_falha(ctx, exportacao_id: str, erro: str) -> None:
    with ctx.db() as cur:
        cur.execute(
            "UPDATE plat.exportacao SET estado = %s, erro = %s, concluido_em = now() "
            "WHERE id = %s::uuid AND estado NOT IN ('pronta','falhou','cancelada','expirada')",
            ("cancelada" if "cancel" in erro.lower() else "falhou", erro[:2000], exportacao_id),
        )


def pacote_gerar(ctx, mapa: dict, p: dict, trabalho, gerados: list) -> tuple:
    """Escreve o pacote do mapa (item L2-01-l): um GeoPackage com as camadas CITADAS, o manifesto e os
    estilos (MapLibre e SLD). Devolve `(zip, feicoes, ms, avisos, relatorio)`.

    O GeoPackage recebe uma tabela por camada citada, com `-append` a partir da segunda: um arquivo só,
    lido pelo destino numa passada. Camada citada que não existe mais (ou que é de outro inquilino, e
    portanto não existe daqui) não vira tabela vazia — entra no relatório como `ausente`, e o manifesto
    não a lista. Melhor um pacote menor e verdadeiro que um pacote completo e mentiroso."""
    corpo = (mapa["dados"] or {}).get("corpo") or {}
    citadas = pacote_mod.camadas_citadas(corpo)
    gpkg = Path(trabalho) / "pacote_dados.gpkg"
    gerados.append(gpkg)
    conninfo = motor.conninfo_pg(ctx.tenant_id, ctx.usuario_id)
    entradas: list[dict] = []
    ausentes: list[str] = []
    total = 0
    ms = 0
    avisos: list[str] = []
    for camada_id in citadas:
        ctx.verificar()
        with ctx.db() as cur:
            cur.execute("SELECT id, titulo, dados FROM plat.item WHERE id = %s::uuid "
                        "AND tipo = 'camada_vetorial' AND apagado_em IS NULL", (camada_id,))
            camada = cur.fetchone()
        if camada is None:
            ausentes.append(camada_id)
            continue
        dados = camada["dados"] or {}
        if dados.get("fonte") != "hospedada" or not dados.get("schema") or not dados.get("tabela"):
            ausentes.append(camada_id)
            continue
        entrada = pacote_mod.entrada_de_camada(len(entradas) + 1, camada, dados)
        campos = [c["nome"] for c in dados.get("campos") or []]
        with ctx.db() as cur:
            sql = motor.montar_select(
                cur, schema=dados["schema"], tabela=dados["tabela"], campos=campos, coluna_geom="geom",
                where=None, bbox=None, srid_tabela=int(dados.get("srid") or 4326),
                colunas_brancas=motor.colunas_permitidas(dados.get("campos") or []),
            )
        argv = ["ogr2ogr", "-f", "GPKG", str(gpkg), conninfo, "-sql", sql,
                "-nln", entrada["tabela_no_pacote"]]
        if gpkg.exists():
            argv.append("-append")
        ctx.progresso(10 + int(60 * len(entradas) / max(1, len(citadas))),
                      f"empacotando {camada['titulo']}")
        (r, ms_camada) = motor.cronometrar(ctx.subprocesso, argv)
        ms += ms_camada
        avisos.extend([ln.strip() for ln in (r.stderr or "").splitlines() if ln.strip()][:5])
        if r.returncode != 0:
            raise FalhaDefinitiva(f"ogr2ogr falhou ao empacotar {camada['titulo']!r}: "
                                  f"{(avisos[-1] if avisos else 'sem detalhe')[:300]}")
        n = motor.contar_feicoes(gpkg, formato_de("gpkg"), ctx.subprocesso)
        entrada["feicoes"] = (n or 0) - total
        total = n or total
        entradas.append(entrada)
    if not entradas:
        raise FalhaDefinitiva("nenhuma camada citada pelo mapa pôde ser empacotada")
    man = pacote_mod.manifesto(
        {"titulo": mapa["titulo"], "descricao": mapa.get("descricao"), "corpo": corpo},
        entradas, datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
    )
    final = Path(trabalho) / motor.nome_arquivo_seguro(p.get("nome") or mapa["titulo"], ".zip")
    ctx.progresso(72, "escrevendo o pacote")
    pacote_mod.escrever(final, man, gpkg)
    gerados.append(final)
    relatorio = {"camadas": [{"titulo": e["titulo"], "tabela_no_pacote": e["tabela_no_pacote"],
                              "feicoes": e["feicoes"]} for e in entradas],
                 "camadas_ausentes": ausentes, "versao_pacote": pacote_mod.VERSAO_PACOTE}
    return final, total, ms, avisos[:20], relatorio


@tarefa(
    nome="exportacao.gerar",
    descricao="Exporta uma camada vetorial para outro formato (ogr2ogr) e publica o arquivo na pasta do usuário",
    parametros=GerarParametros,
    pesado=True,
    memoria_mb=limites.EXPORTACAO_MEMORIA_MB,
    timeout_s=limites.EXPORTACAO_TIMEOUT_S,
    tentativas=1,
    chave=lambda p: f"exportacao:{p.get('exportacao_id')}",
    perfil_minimo="editor",
    ferramentas=("gdal",),
)
def exportacao_gerar(ctx, exportacao_id: uuid.UUID) -> dict:
    eid = str(exportacao_id)
    trabalho = Path(ctx.dir_trabalho)
    gerados: list[Path] = []
    try:
        with ctx.db() as cur:
            cur.execute("SELECT * FROM plat.exportacao WHERE id = %s::uuid", (eid,))
            exp = cur.fetchone()
            if exp is None:
                raise FalhaDefinitiva("exportação inexistente")
            if exp["estado"] != "pendente":
                raise FalhaDefinitiva(f"exportação em estado {exp['estado']!r}; esperava 'pendente'")
            tipo_origem = "mapa" if exp["formato"] == "pacote" else "camada_vetorial"
            cur.execute(
                "SELECT id, titulo, descricao, dados FROM plat.item WHERE id = %s::uuid AND tipo = %s",
                (str(exp["item_id"]), tipo_origem),
            )
            item = cur.fetchone()
            if item is None:
                # RLS: item de outro inquilino simplesmente não existe daqui — é o mesmo 'não existe' do
                # item apagado, de propósito (nunca confirmar a existência de conteúdo alheio)
                raise FalhaDefinitiva("o item de origem não existe mais")
            cur.execute("UPDATE plat.exportacao SET estado = 'gerando' WHERE id = %s::uuid", (eid,))

        p = exp["parametros"] or {}
        formato = formato_de(exp["formato"])
        if formato is None:
            raise FalhaDefinitiva(f"formato {exp['formato']!r} não suportado")
        relatorio_pacote = None
        if formato.nome == "pacote":
            nome_arquivo = motor.nome_arquivo_seguro(p.get("nome") or item["titulo"], formato.extensao)
            final, feicoes_pacote, ms_ogr, avisos, relatorio_pacote = pacote_gerar(ctx, item, p, trabalho,
                                                                                   gerados)
            relatorio_csv = None
        else:
            dados = item["dados"] or {}
            schema, tabela = dados["schema"], dados["tabela"]
            srid_tabela = int(dados.get("srid") or 4326)
            campos_item = [c["nome"] for c in dados.get("campos") or []]
            ocultos = {c for c in (p.get("campos_ocultos") or []) if isinstance(c, str)}
            # o campo oculto pela `vista_de_camada` é retirado AQUI TAMBÉM, não só na rota: a rota é quem
            # decide, o job é quem grava o arquivo, e um campo escondido nunca deve depender de um só guarda
            campos = [c for c in (p.get("campos") or campos_item) if c in campos_item and c not in ocultos]
            if formato.guarda_atributos and not campos:
                raise FalhaDefinitiva("nenhum campo selecionado para exportar")
            codificacao = (p.get("codificacao") or "UTF-8").upper()
            srid_saida = int(p.get("srid_saida") or 0) or None
            nome_arquivo = motor.nome_arquivo_seguro(p.get("nome") or item["titulo"], formato.extensao)

            # ---------------------------------------------------------------- disco antes de qualquer byte
            with ctx.db() as cur:
                cur.execute("SELECT pg_total_relation_size(%s::regclass) AS b", (f'"{schema}"."{tabela}"',))
                tamanho_tabela = int(cur.fetchone()["b"])
            estimativa = max(tamanho_tabela * limites.EXPORTACAO_FATOR_DISCO, 8 * 1024 * 1024)
            motor.exigir_disco(trabalho, estimativa)
            ctx.log("INFO", f"tabela de {tamanho_tabela // 1024} KB; estimativa de {estimativa // 1024} KB no disco "
                            f"temporário; livre agora: {motor.espaco_livre(trabalho) // (1024 * 1024)} MB")

            # ---------------------------------------------------------------- consulta
            ctx.progresso(5, "montando a consulta")
            with ctx.db() as cur:
                try:
                    sql = motor.montar_select(
                        cur, schema=schema, tabela=tabela, campos=campos, coluna_geom="geom",
                        where=p.get("where"), bbox=p.get("bbox"), srid_tabela=srid_tabela,
                        colunas_brancas=motor.colunas_permitidas(dados.get("campos") or []),
                        com_geometria=formato.guarda_geometria or formato.nome == "csv",
                        ids=p.get("ids"), filtro_cql2=p.get("filtro"),
                        colunas_cql2=colunas_da_camada(dados, ocultos),
                    )
                except where_ast.ErroWhere as e:
                    raise FalhaDefinitiva(f"filtro inválido: {e.mensagem}") from e

            # ---------------------------------------------------------------- ogr2ogr
            ctx.progresso(15, f"gerando {formato.rotulo}")
            # o nome do DIRETÓRIO importa para alguns drivers: o OpenFileGDB recusa criar uma pasta cuja
            # extensão não seja `.gdb` ("Extension of the directory should be gdb", medido em 07/09/2026),
            # e é esse mesmo nome que vai para dentro do zip
            alvo = trabalho / ((formato.caminho_interno or "saida_dir") if formato.em_diretorio
                               else f"saida{formato.extensao}")
            if formato.nome == "kmz":
                alvo = trabalho / "saida.kml"
            elif formato.nome == "geoparquet":
                alvo = trabalho / "saida_intermediaria.gpkg"
            gerados.append(alvo)
            argv = motor.argumentos_ogr2ogr(
                formato, destino=alvo, conninfo=motor.conninfo_pg(ctx.tenant_id, ctx.usuario_id), sql=sql,
                nome_camada=motor.nome_camada_seguro(Path(nome_arquivo).stem, formato),
                srid_saida=srid_saida, codificacao=codificacao, geometria=dados.get("geometria"),
            )
            (resultado, ms_ogr) = motor.cronometrar(ctx.subprocesso, argv)
            avisos = [ln.strip() for ln in (resultado.stderr or "").splitlines() if ln.strip()][:20]
            if resultado.returncode != 0:
                # as ÚLTIMAS linhas, não a última: a derradeira do ogr2ogr é sempre a genérica
                # ("Terminating translation prematurely after failed translation from sql statement"),
                # e a causa está na linha anterior (medido em 07/09/2026 com o File Geodatabase)
                raise FalhaDefinitiva(f"ogr2ogr falhou: {' | '.join(avisos[-3:])[:400] or 'sem detalhe'}")
            if not alvo.exists():
                raise FalhaDefinitiva("ogr2ogr terminou sem escrever o arquivo (consulta sem nenhuma feição?)")

            # ---------------------------------------------------------------- conversões que o GDAL não faz
            relatorio_csv = None
            final = alvo
            if formato.nome == "csv":
                ctx.progresso(55, "ajustando o CSV")
                relatorio_csv = csv_saida.reescrever(
                    alvo,
                    separador=(p.get("csv") or {}).get("separador") or ",",
                    decimal=(p.get("csv") or {}).get("decimal") or ".",
                    coluna_x=(p.get("csv") or {}).get("coluna_x"),
                    coluna_y=(p.get("csv") or {}).get("coluna_y"),
                    codificacao=codificacao,
                )
            elif formato.em_diretorio and formato.zipar:
                ctx.progresso(55, f"compactando o {formato.rotulo}")
                final = trabalho / nome_arquivo
                motor.zipar_diretorio(alvo, final, formato.caminho_interno)
                gerados.append(final)
            elif formato.nome == "kmz":
                ctx.progresso(55, "compactando o KMZ")
                final = trabalho / nome_arquivo
                motor.zipar_arquivo(alvo, final, "doc.kml")
                gerados.append(final)
            elif formato.nome == "geoparquet":
                ctx.progresso(55, "convertendo para GeoParquet")
                final = trabalho / nome_arquivo
                motor.gpkg_para_geoparquet(alvo, final, limites.EXPORTACAO_MEMORIA_MB, ctx.subprocesso)
                gerados.append(final)

        ctx.verificar()
        ctx.progresso(70, "conferindo o arquivo gerado")
        feicoes = (feicoes_pacote if formato.nome == "pacote"
                   else motor.contar_feicoes(final, formato, ctx.subprocesso))
        bytes_arquivo = motor.tamanho(final)

        # ---------------------------------------------------------------- envio ao armazenamento (em partes)
        ctx.progresso(80, f"enviando {bytes_arquivo // 1024} KB ao armazenamento")
        with ctx.db() as cur:
            objeto = objetos.guardar_arquivo(
                cur, CLASSE_OBJETO, final, formato.content_type, item_id=eid, usuario_id=ctx.usuario_id,
                extensao=formato.extensao,
            )

        # ---------------------------------------------------------------- item de arquivo + fecho
        ctx.progresso(92, "publicando o arquivo na pasta do usuário")
        validade = datetime.timedelta(days=limites.EXPORTACAO_VALIDADE_DIAS)
        item_dados = {
            "chave": objeto["chave"], "sha256": objeto["sha256"], "bytes": objeto["bytes"],
            "content_type": formato.content_type, "nome_original": nome_arquivo,
        }
        with ctx.db() as cur:
            cur.execute(
                "INSERT INTO plat.item(tenant_id, tipo, titulo, dono_id, pasta_id, dados, tamanho_bytes, "
                "criado_por, modificado_por) VALUES (%s, 'arquivo', %s, %s, %s, %s, %s, %s, %s) RETURNING id",
                (ctx.tenant_id, nome_arquivo[:250], ctx.usuario_id, p.get("pasta_id"), _jsonb(item_dados),
                 objeto["bytes"], ctx.usuario_id, ctx.usuario_id),
            )
            arquivo_item_id = str(cur.fetchone()["id"])
            cur.execute(
                "UPDATE plat.exportacao SET estado = 'pronta', arquivo_item_id = %s::uuid, chave = %s, "
                "sha256 = %s, bytes = %s, feicoes = %s, duracao_ms = %s, concluido_em = now(), "
                "expira_em = now() + %s WHERE id = %s::uuid",
                (arquivo_item_id, objeto["chave"], objeto["sha256"], objeto["bytes"], feicoes, ms_ogr,
                 validade, eid),
            )
            cur.execute(
                "SELECT plat.evento_registrar('camadas/exportar', 'item', %s, %s::jsonb, NULL, NULL)",
                (str(exp["item_id"]), json.dumps(
                    {"exportacao_id": eid, "formato": formato.nome, "feicoes": feicoes,
                     "bytes": objeto["bytes"], "job_id": str(ctx.job_id)}, default=str)),
            )
        ctx.progresso(100, "concluído")
        return {
            "exportacao_id": eid, "arquivo_item_id": arquivo_item_id, "formato": formato.nome,
            "feicoes": feicoes, "bytes": objeto["bytes"], "sha256": objeto["sha256"],
            "duracao_ogr2ogr_ms": ms_ogr, "avisos_gdal": avisos, "csv": relatorio_csv,
            "nome_arquivo": nome_arquivo, "pacote": relatorio_pacote,
        }
    except Cancelado:
        _marcar_falha(ctx, eid, "cancelamento solicitado")
        raise
    except FalhaDefinitiva as e:
        _marcar_falha(ctx, eid, str(e))
        raise
    except (psycopg2.Error, motor.ErroExportacao, OSError) as e:
        _marcar_falha(ctx, eid, str(e)[:500])
        raise FalhaDefinitiva(str(e)[:500]) from e
    finally:
        for caminho in gerados:
            motor.limpar(caminho)
