#!/usr/bin/env python3
"""Matriz de conformidade VIVA dos serviços Esri/OGC desta plataforma (item L2-04-j).

O documento `docs/PARIDADE.md` tinha, até aqui, uma seção escrita à mão por item. Escrita à mão, ela
envelhece: a seção do item L2-04-servicos-esri-ogc ainda dizia que `applyEdits` estava fora, quando o
item da edição já o tinha construído. Este script existe para que a lista de serviços do documento
deixe de ser texto e passe a ser saída de medida.

Regra que este arquivo implementa (e que o adversário confere): **linha marcada `suportado` sem uma
prova que passou nesta rodada não é `suportado`** — vira `refutado`. Uma prova é uma das duas:

  pytest  — um nó de teste nomeado (`arquivo::funcao`), executado nesta rodada.
  script  — uma chave de veredito de `conformidade_query.py`/`conformidade_servicos.py`, os dois
            roteiros de sonda que já existiam nos itens irmãos e que fazem pedidos reais ao serviço.

Linha sem prova executável fica `nao_medido`, com o motivo escrito. `nao_medido` NUNCA é `suportado`.

Uso:
    venv/bin/python tests/esri/conformidade.py            # roda tudo e grava tests/esri/conformidade.json
    venv/bin/python tests/esri/conformidade.py --sem-scripts   # só os nós pytest (mais rápido)
    venv/bin/python tests/esri/conformidade.py --secao         # imprime a seção do PARIDADE.md
    venv/bin/python tests/esri/conformidade.py --conferir      # reprova se o PARIDADE.md divergir

`make conformidade` chama a primeira forma; `make check` confere a última por
`tests/unit/test_conformidade_matriz.py`, que não toca o banco."""

from __future__ import annotations

import argparse
import datetime
import json
import os
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
SAIDA = RAIZ / "tests" / "esri" / "conformidade.json"
PARIDADE = RAIZ / "docs" / "PARIDADE.md"
INICIO = "<!-- INICIO matriz-de-conformidade (gerado por tests/esri/conformidade.py; nao editar a mao) -->"
FIM = "<!-- FIM matriz-de-conformidade -->"

ESTADOS = ("suportado", "parcial", "fora", "nao_medido", "refutado")
# ordem de força: quando declaração e medida discordam, vale a mais conservadora das duas
RANQUE = {"suportado": 3, "parcial": 2, "fora": 1}

FONTES = {
    "query": ("https://developers.arcgis.com/rest/services-reference/enterprise/"
              "query-feature-service-layer/", "2026-09-06"),
    "feature_service": ("https://developers.arcgis.com/rest/services-reference/enterprise/"
                        "feature-service/", "2026-09-07"),
    "arcgis_python": ("https://developers.arcgis.com/python/latest/api-reference/arcgis.gis.toc.html",
                      "2026-09-07"),
    "ogc_features": ("https://docs.ogc.org/is/17-069r4/17-069r4.html", "2026-09-07"),
    "map_service": ("https://developers.arcgis.com/rest/services-reference/enterprise/map-service/",
                    "2026-09-08"),
    "export_map": ("https://developers.arcgis.com/rest/services-reference/enterprise/export-map/",
                   "2026-09-08"),
    "identify": ("https://developers.arcgis.com/rest/services-reference/enterprise/identify-map-service/",
                 "2026-09-08"),
    "legend": ("https://developers.arcgis.com/rest/services-reference/enterprise/legend-map-service/",
               "2026-09-08"),
    "find": ("https://developers.arcgis.com/rest/services-reference/enterprise/find/", "2026-09-08"),
    "geometry_service": ("https://developers.arcgis.com/rest/services-reference/enterprise/geometry-service/",
                         "2026-09-08"),
    "project": ("https://developers.arcgis.com/rest/services-reference/enterprise/project/", "2026-09-08"),
    "buffer": ("https://developers.arcgis.com/rest/services-reference/enterprise/buffer/", "2026-09-08"),
    "areas_lengths": ("https://developers.arcgis.com/rest/services-reference/enterprise/areas-and-lengths/",
                      "2026-09-08"),
}

# Os 45 parâmetros da operação `query`, na ordem da tabela "Request parameters" da doc Esri (acesso em
# 2026-09-06). A lista é DECLARADA aqui para que o adversário possa procurar um parâmetro da doc que
# esteja faltando na matriz: `tests/unit/test_conformidade_matriz.py` reprova se algum não virar linha.
PARAMETROS_QUERY_DOC = (
    "where", "objectIds", "geometry", "geometryType", "inSR", "spatialRel", "relationParam", "time",
    "distance", "units", "outFields", "returnGeometry", "maxAllowableOffset", "geometryPrecision",
    "outSR", "defaultSR", "havingClause", "gdbVersion", "returnDistinctValues", "returnIdsOnly",
    "returnCountOnly", "returnExtentOnly", "orderByFields", "groupByFieldsForStatistics",
    "outStatistics", "returnZ", "returnM", "multipatchOption", "resultOffset", "resultRecordCount",
    "quantizationParameters", "returnCentroid", "resultType", "historicMoment", "returnTrueCurves",
    "sqlFormat", "returnExceededLimitFeatures", "datumTransformation", "timeReferenceUnknownClient",
    "returnEnvelope", "fullText", "returnUniqueIdsOnly", "uniqueIds", "resultPaginationToken", "f",
)

# Roteiros de sonda que já existiam nos itens irmãos; cada um grava um JSON com um veredito por chave.
SCRIPTS = {
    "query": (RAIZ / "tests" / "esri" / "conformidade_query.py",
              RAIZ / "tests" / "medidas" / "L2-04-c-featureserver-query.json", "vereditos", "parametro"),
    "servicos": (RAIZ / "tests" / "esri" / "conformidade_servicos.py",
                 RAIZ / "tests" / "medidas" / "L2-04-servicos-esri-ogc.json", "clausulas", "clausula"),
}


def _linha(familia, item, nome, estado, fonte, provas=(), observacao=""):
    assert estado in ESTADOS, estado
    return {"familia": familia, "item": item, "linha": nome, "estado_declarado": estado,
            "fonte": fonte, "provas": list(provas), "observacao": observacao}


def _pytest(no: str) -> dict:
    return {"tipo": "pytest", "referencia": no}


def _script(qual: str, chave: str) -> dict:
    return {"tipo": "script", "referencia": f"{qual}#{chave}"}


D = "tests/api/test_diretorio_esri.py"
E = "tests/api/test_featureserver_edicao.py"
A = "tests/api/test_edicao_historico_anexos.py"
V = "tests/api/test_vector_tile_server.py"
G = "tests/api/test_ogc_features_crs_cql2.py"
C = "tests/api/test_conformidade_clientes.py"
M = "tests/api/test_mapserver_esri.py"
MU = "tests/unit/test_mapserver_desenho.py"


def matriz() -> list[dict]:
    """A matriz declarada. Estado aqui é o que se AFIRMA; o estado final sai da prova que rodou."""
    linhas: list[dict] = []

    # --- operação query: os 45 parâmetros da doc, cada um provado pelo roteiro de sonda do item L2-04-c
    for parametro in PARAMETROS_QUERY_DOC:
        linhas.append(_linha("query", "L2-04-c-featureserver-query", f"query · {parametro}",
                             "suportado", "query", [_script("query", parametro)]))

    # --- diretório, descritores e metadados (L2-04-b e L2-04-servicos-esri-ogc)
    linhas += [
        _linha("diretorio", "L2-04-b-featureserver-catalogo-metadados", "rest/info com authInfo",
               "suportado", "feature_service",
               [_pytest(f"{D}::test_rest_info_traz_authinfo_apontando_para_generate_token")]),
        _linha("diretorio", "L2-04-b-featureserver-catalogo-metadados", "rest/services (catálogo de pastas e serviços)",
               "suportado", "feature_service", [_pytest(f"{D}::test_catalogo_lista_a_camada_e_a_pasta")]),
        _linha("diretorio", "L2-04-b-featureserver-catalogo-metadados",
               "generateToken (token curto por usuário e senha)",
               "suportado", "feature_service",
               [_pytest(f"{D}::test_generate_token_devolve_token_de_leitura_com_validade_de_ate_24h"),
                _pytest(f"{D}::test_generate_token_com_senha_errada_nao_gera")]),
        _linha("diretorio", "L2-04-b-featureserver-catalogo-metadados", "descritor do serviço FeatureServer",
               "suportado", "feature_service",
               [_pytest(f"{D}::test_descritor_do_servico_tem_as_chaves_obrigatorias"),
                _script("servicos", "featureserver_descritor_servico")]),
        _linha("diretorio", "L2-04-b-featureserver-catalogo-metadados", "descritor da camada (campos, tipos, índices)",
               "suportado", "feature_service",
               [_pytest(f"{D}::test_descritor_da_camada_tem_campos_tipos_e_indices_do_banco"),
                _script("servicos", "featureserver_descritor_camada")]),
        _linha("diretorio", "L2-04-b-featureserver-catalogo-metadados", "FeatureServer/layers",
               "suportado", "feature_service", [_pytest(f"{D}::test_layers_devolve_o_mesmo_descritor_da_camada")]),
        _linha("diretorio", "L2-04-b-featureserver-catalogo-metadados", "info/itemInfo e info/metadata",
               "suportado", "feature_service", [_pytest(f"{D}::test_item_info_e_metadata_vem_do_catalogo")]),
        _linha("diretorio", "L2-04-b-featureserver-catalogo-metadados", "formatos f=json, pjson, html e jsonp",
               "suportado", "feature_service",
               [_pytest(f"{D}::test_pjson_e_html_e_jsonp_respondem_e_nunca_500"),
                _pytest(f"{D}::test_formato_desconhecido_e_400")]),
        _linha("diretorio", "L2-04-b-featureserver-catalogo-metadados",
               "drawingInfo (renderer a partir do estilo da camada)",
               "suportado", "feature_service",
               [_pytest(f"{D}::test_estilo_da_camada_vira_renderer_unique_value"),
                _pytest(f"{D}::test_camada_sem_estilo_tem_renderer_simples_declarado")]),
        _linha("diretorio", "L2-04-b-featureserver-catalogo-metadados",
               "camada de outro inquilino ausente do diretório",
               "suportado", "feature_service",
               [_pytest(f"{D}::test_camada_de_b_ausente_no_diretorio_de_a"),
                _pytest(f"{D}::test_token_invalido_ou_revogado_nao_abre_o_diretorio")]),
    ]

    # --- edição compatível Esri (L2-04-d)
    linhas += [
        _linha("edicao", "L2-04-d-featureserver-edicao-anexos", "applyEdits da camada (adds, updates, deletes)",
               "suportado", "feature_service", [_pytest(f"{E}::test_apply_edits_devolve_os_tres_vetores")]),
        _linha("edicao", "L2-04-d-featureserver-edicao-anexos", "applyEdits do serviço (várias camadas num lote)",
               "suportado", "feature_service", [_pytest(f"{E}::test_apply_edits_do_servico"),
                                                _pytest(f"{E}::test_apply_edits_do_servico_com_camada_inexistente")]),
        _linha("edicao", "L2-04-d-featureserver-edicao-anexos", "rollbackOnFailure",
               "suportado", "feature_service", [_pytest(f"{E}::test_rollback_on_failure_nao_deixa_nada"),
                                                _pytest(f"{E}::test_sem_rollback_a_parte_boa_fica")]),
        _linha("edicao", "L2-04-d-featureserver-edicao-anexos", "useGlobalIds",
               "suportado", "feature_service", [_pytest(f"{E}::test_use_global_ids_atualiza_por_globalid"),
                                                _pytest(f"{E}::test_use_global_ids_com_id_desconhecido_e_404_na_posicao")]),
        _linha("edicao", "L2-04-d-featureserver-edicao-anexos", "addFeatures e updateFeatures separados",
               "suportado", "feature_service", [_pytest(f"{E}::test_add_e_update_features_separados")]),
        _linha("edicao", "L2-04-d-featureserver-edicao-anexos", "deleteFeatures (por objectIds e por where)",
               "suportado", "feature_service", [_pytest(f"{E}::test_delete_features_por_where"),
                                                _pytest(f"{E}::test_delete_features_where_malicioso_e_400")]),
        _linha("edicao", "L2-04-d-featureserver-edicao-anexos", "calculate (por expressão e por valor)",
               "suportado", "feature_service", [_pytest(f"{E}::test_calculate_por_expressao_e_por_valor"),
                                                _pytest(f"{E}::test_calculate_com_nome_desconhecido_e_400")]),
        _linha("edicao", "L2-04-d-featureserver-edicao-anexos", "escrita exige escopo (token só de leitura recebe 403)",
               "suportado", "feature_service", [_pytest(f"{E}::test_token_so_leitura_recebe_403_com_corpo_esri"),
                                                _pytest(f"{E}::test_token_de_edicao_escreve_pelo_mesmo_caminho")]),
        _linha("edicao", "L2-04-d-featureserver-edicao-anexos", "spatialReference declarada na geometria de entrada",
               "suportado", "feature_service",
               [_pytest(f"{E}::test_geometria_em_metros_sem_spatial_reference_e_recusada"),
                _pytest(f"{E}::test_spatial_reference_declarada_e_reprojetada")]),
        _linha("edicao", "L2-04-d-featureserver-edicao-anexos", "objectId de outro inquilino nunca entra",
               "suportado", "feature_service", [_pytest(f"{E}::test_objectid_de_outro_inquilino_nao_entra")]),
        _linha("edicao", "L2-04-d-featureserver-edicao-anexos", "histórico registra a origem FeatureServer",
               "suportado", "feature_service", [_pytest(f"{E}::test_historico_registra_origem_featureserver")]),
        _linha("anexos", "L2-04-d-featureserver-edicao-anexos", "addAttachment (multipart) e leitura com sha256 igual",
               "suportado",
                      "feature_service", [_pytest(f"{E}::test_add_attachment_multipart_e_leitura_com_sha256_igual")]),
        _linha("anexos", "L2-04-d-featureserver-edicao-anexos", "updateAttachment mantém o identificador",
               "suportado", "feature_service", [_pytest(f"{E}::test_update_attachment_mantem_o_mesmo_identificador")]),
        _linha("anexos", "L2-04-d-featureserver-edicao-anexos", "uploads/upload em dois tempos e anexo por uploadId",
               "suportado", "feature_service", [_pytest(f"{E}::test_upload_em_dois_tempos_e_anexo_por_upload_id")]),
        _linha("anexos", "L2-04-d-featureserver-edicao-anexos", "anexo em base64 dentro do applyEdits",
               "suportado", "feature_service", [_pytest(f"{E}::test_anexo_base64_dentro_do_apply_edits")]),
        _linha("anexos", "L2-04-d-featureserver-edicao-anexos", "attachments (listagem) e deleteAttachments",
               "suportado", "feature_service", [_pytest(f"{A}::test_anexo_enviado_e_listado"),
                                                _pytest(f"{A}::test_anexo_apagado_some_da_listagem")]),
        _linha("anexos", "L2-04-d-featureserver-edicao-anexos", "anexo de feição de outro inquilino é 404",
               "suportado", "feature_service", [_pytest(f"{A}::test_anexo_de_feicao_de_outro_inquilino_e_404")]),
        _linha("relacionamento", "L2-10-b-relacionamentos", "queryRelatedRecords",
               "fora", "feature_service", [],
               "não existe rota queryRelatedRecords neste repositório; relationships é declarado vazio no "
               "descritor da camada. O item que constrói relacionamento ainda não foi feito"),
    ]

    # --- OGC API Features (Part 1 + CRS + CQL2), WFS 2.0
    linhas += [
        _linha("ogc_features", "L2-04-servicos-esri-ogc", "pouso, conformance e collections",
               "suportado", "ogc_features", [_script("servicos", "ogc_features_pouso"),
                                             _script("servicos", "ogc_features_conformance"),
                                             _script("servicos", "ogc_features_collections")]),
        _linha("ogc_features", "L2-04-servicos-esri-ogc", "items com limit, item único e bbox",
               "suportado", "ogc_features", [_script("servicos", "ogc_features_items_limit"),
                                             _script("servicos", "ogc_features_item_um"),
                                             _script("servicos", "ogc_features_bbox")]),
        _linha("ogc_features", "L2-04-g-ogc-api-features-crs-cql2", "Part 2 CRS (crs, storageCrs, bbox-crs)",
               "suportado", "ogc_features", [_pytest(f"{G}::test_crs_31982_bate_com_st_transform"),
                                             _pytest(f"{G}::test_crs_epsg_curto_e_crs84_sao_aceitos"),
                                             _pytest(f"{G}::test_storage_crs_na_colecao"),
                                             _pytest(f"{G}::test_crs_invalido_e_400")]),
        _linha("ogc_features", "L2-04-g-ogc-api-features-crs-cql2", "Part 3 filtro CQL2 (texto e JSON)",
               "suportado", "ogc_features", [_pytest(f"{G}::test_filter_cql2_text_e_cql2_json_mesma_contagem"),
                                             _pytest(f"{G}::test_filter_bate_com_sql_escrito_a_mao"),
                                             _pytest(f"{G}::test_filter_in_like_between"),
                                             _pytest(f"{G}::test_filter_espacial_s_dwithin")]),
        _linha("ogc_features", "L2-04-g-ogc-api-features-crs-cql2", "queryables e conformance declaram CRS e CQL2",
               "suportado", "ogc_features", [_pytest(f"{G}::test_queryables_lista_campos_da_camada"),
                                             _pytest(f"{G}::test_conformance_declara_crs_e_cql2")]),
        _linha("ogc_features", "L2-04-g-ogc-api-features-crs-cql2", "Part 4 transações (POST, PUT, PATCH, DELETE)",
               "suportado", "ogc_features", [_pytest(f"{G}::test_post_cria_feicao_e_devolve_location_e_etag"),
                                             _pytest(f"{G}::test_put_substitui_com_if_match_correto"),
                                             _pytest(f"{G}::test_put_com_if_match_desatualizado_e_412"),
                                             _pytest(f"{G}::test_patch_atualiza_parcial"),
                                             _pytest(f"{G}::test_delete_apaga_feicao")]),
        _linha("ogc_features", "L2-04-g-ogc-api-features-crs-cql2", "coleção de outro inquilino ausente",
               "suportado", "ogc_features", [_pytest(f"{G}::test_colecao_de_b_ausente_para_token_de_a")]),
        _linha("wfs", "L2-04-servicos-esri-ogc", "GetCapabilities 2.0.0 lido por cliente OGC de terceiros",
               "suportado", "ogc_features", [_script("servicos", "wfs_getcapabilities"),
                                             _pytest(f"{C}::test_owslib_le_o_getcapabilities_do_nosso_wfs_2_0")]),
        _linha("wfs", "L2-04-servicos-esri-ogc", "GetFeature com OUTPUTFORMAT=application/json",
               "suportado", "ogc_features", [_script("servicos", "wfs_getfeature_json"),
                                             _pytest(f"{C}::test_owslib_faz_getfeature_e_devolve_as_feicoes_da_camada")]),
        _linha("wfs", "L2-04-servicos-esri-ogc", "GetFeature em GML 3.2",
               "parcial", "ogc_features", [_script("servicos", "wfs_getfeature_gml")],
               "GML escrito à mão, não validado contra o XSD de referência do OGC; Multi* vira o tipo "
               "simples do primeiro membro"),
        _linha("wfs", "L2-04-servicos-esri-ogc", "DescribeFeatureType",
               "parcial", "ogc_features", [_script("servicos", "wfs_describefeaturetype")],
               "XSD mínimo, suficiente para os campos aparecerem no cliente, não validado contra o XSD do OGC"),
        _linha("wfs", "L2-04-h-wfs-2-gml", "Filter Encoding 2.0 no parâmetro FILTER e WFS-T",
               "fora", "ogc_features", [], "não implementado; o item próprio de WFS 2.0/GML ainda não foi feito"),
    ]

    # --- tiles vetoriais (L2-04-e) e exportação por URL
    linhas += [
        _linha("tiles", "L2-04-e-vector-tile-server-tilejson", "TileJSON 3.0.0 válido contra o esquema oficial",
               "suportado", "feature_service", [_pytest(f"{V}::test_tilejson_valido_contra_o_esquema_3_0")]),
        _linha("tiles", "L2-04-e-vector-tile-server-tilejson", "VectorTileServer: descritor com tileInfo",
               "suportado", "feature_service",
                      [_pytest(f"{V}::test_descritor_vector_tile_server_tem_tileinfo_web_mercator_512")]),
        _linha("tiles", "L2-04-e-vector-tile-server-tilejson",
               "tile Esri (z/y/x) e tile MapLibre (z/x/y) byte a byte iguais",
               "suportado", "feature_service", [_pytest(f"{V}::test_tile_esri_e_maplibre_sao_byte_a_byte_iguais")]),
        _linha("tiles", "L2-04-e-vector-tile-server-tilejson",
               "estilo raiz aprovado no validador oficial da style spec",
               "suportado",
                      "feature_service", [_pytest(f"{V}::test_root_style_passa_no_validador_oficial_da_style_spec"),
                                                _pytest(f"{V}::test_root_style_reprova_com_o_validador_quando_corrompido")]),
        _linha("tiles", "L2-04-e-vector-tile-server-tilejson", "sprites e fontes com content-type correto",
               "suportado", "feature_service", [_pytest(f"{V}::test_sprites_e_fontes_200_com_content_type_correto")]),
        _linha("tiles", "L2-04-e-vector-tile-server-tilejson", "exportação por URL: geojson, kml, csv, fgb e gpkg",
               "suportado", "feature_service", [_pytest(f"{V}::test_geojson_export_reflete_where_e_bbox"),
                                                _pytest(f"{V}::test_kml_de_10_mil_feicoes_abre_com_ogrinfo"),
                                                _pytest(f"{V}::test_csv_export_com_geometria_multi"),
                                                _pytest(f"{V}::test_fgb_e_gpkg_abrem_com_ogrinfo")]),
        _linha("tiles", "L2-04-e-vector-tile-server-tilejson", "token revogado fecha todas as rotas de tile",
               "suportado", "feature_service", [_pytest(f"{V}::test_token_revogado_401_em_todas_as_rotas")]),
    ]

    # --- MapServer e GeometryServer (L2-04-f): o bloco que até 07/09 estava na lista dos AUSENTES
    F = "L2-04-f-mapserver-identify-legend-geometryserver"
    linhas += [
        _linha("mapserver", F, "descritor do MapServer (layers, spatialReference, initialExtent, capabilities)",
               "suportado", "map_service", [_pytest(f"{M}::test_mapserver_lista_as_camadas_do_documento")]),
        _linha("mapserver", F, "MapServer/layers e MapServer/{id} com os metadados do FeatureServer",
               "suportado", "map_service",
               [_pytest(f"{M}::test_layers_e_camada_trazem_os_metadados_do_featureserver"),
                _pytest(f"{M}::test_camada_inexistente_no_mapserver_e_404")]),
        _linha("mapserver", F, "export (bbox, size, dpi, format, transparent, f=json e f=image)",
               "suportado", "export_map",
               [_pytest(f"{M}::test_export_1024x768_devolve_imagem_do_tamanho_pedido"),
                _pytest(f"{M}::test_export_f_json_traz_href_extensao_e_a_mesma_imagem"),
                _pytest(f"{M}::test_export_nos_formatos_de_imagem_declarados"),
                _pytest(f"{M}::test_export_em_pdf")]),
        _linha("mapserver", F, "export desenha com o símbolo do estilo (mesmo drawingInfo do FeatureServer)",
               "suportado", "export_map",
               [_pytest(f"{M}::test_export_desenha_a_cor_que_o_drawing_info_declara"),
                _pytest(f"{MU}::test_desenho_de_poligono_pinta_a_cor_do_simbolo"),
                _pytest(f"{MU}::test_camada_zero_desenha_por_cima")]),
        _linha("mapserver", F, "export: layers show/hide/include/exclude e layerDefs",
               "suportado", "export_map",
               [_pytest(f"{M}::test_layer_defs_valido_filtra_o_que_e_desenhado"),
                _pytest(f"{M}::test_layer_defs_para_camada_inexistente_e_400"),
                _pytest(f"{MU}::test_selecao_de_camadas"),
                _pytest(f"{MU}::test_layer_defs_nas_duas_formas")]),
        _linha("mapserver", F, "export: teto de tamanho declarado e layerDefs com SQL injetado recusado",
               "suportado", "export_map",
               [_pytest(f"{M}::test_export_de_8000x8000_e_recusado_com_o_limite_declarado"),
                _pytest(f"{M}::test_layer_defs_com_sql_injetado_e_400"),
                _pytest(f"{M}::test_export_recusa_pedido_malformado_sem_500")]),
        _linha("mapserver", F, "export: parâmetro time",
               "fora", "export_map", [_pytest(f"{M}::test_export_com_time_declara_por_que_recusa")],
               "nenhuma camada declara timeInfo nesta implementação (o descritor já diz timeInfo=null); "
               "o pedido com time volta 422 com o motivo, em vez de ser ignorado em silêncio"),
        _linha("mapserver", F, "identify (geometry, tolerance em pixels, layers, mapExtent, imageDisplay)",
               "suportado", "identify",
               [_pytest(f"{M}::test_identify_em_tres_camadas_bate_com_a_consulta_espacial_direta"),
                _pytest(f"{M}::test_identify_com_tolerancia_zero_responde_sem_erro"),
                _pytest(f"{M}::test_identify_top_olha_so_a_primeira_camada"),
                _pytest(f"{M}::test_identify_devolve_geometria_esri_quando_pedido")]),
        _linha("mapserver", F, "find (searchText, searchFields, contains)",
               "suportado", "find", [_pytest(f"{M}::test_find_acha_pelo_texto_e_declara_o_campo"),
                                     _pytest(f"{M}::test_find_com_campo_inexistente_e_400")]),
        _linha("mapserver", F, "legend (uma amostra PNG por classe do estilo)",
               "suportado", "legend", [_pytest(f"{M}::test_legend_devolve_uma_imagem_por_classe_do_estilo"),
                                       _pytest(f"{M}::test_legend_f_image_devolve_png"),
                                       _pytest(f"{MU}::test_amostra_de_legenda_usa_a_cor_da_classe")]),
        _linha("mapserver", F, "generateKml",
               "parcial", "map_service",
               [_pytest(f"{M}::test_generate_kml_devolve_documento_com_uma_pasta_por_camada")],
               "KML sem KMZ e sem <Style> por classe: uma pasta por camada com as feições em WGS 84"),
        _linha("mapserver", F, "MapServer de outro inquilino é 404 e sem token nada abre",
               "suportado", "map_service",
               [_pytest(f"{M}::test_mapa_de_outro_inquilino_nao_abre_pelo_token_de_a"),
                _pytest(f"{M}::test_sem_token_valido_nada_do_mapserver_abre")]),
        _linha("mapserver", F, "QGIS e ArcGIS Pro adicionam o MapServer e desenham",
               "nao_medido", "map_service", [],
               "nem QGIS nem ArcGIS Pro existem nesta máquina (sem ambiente gráfico); a cláusula do portão "
               "que os pede fica declarada como não medida, nunca como aprovada"),
        _linha("geometria", F, "GeometryServer: project (igual a ST_Transform)",
               "suportado", "project", [_pytest(f"{M}::test_project_de_100_pontos_bate_com_st_transform")]),
        _linha("geometria", F, "GeometryServer: buffer geodésico (igual a ST_Buffer sobre geography)",
               "suportado", "buffer", [_pytest(f"{M}::test_buffer_geodesico_de_1km_tem_area_de_st_buffer_geografico"),
                                       _pytest(f"{M}::test_buffer_com_distancia_negativa_e_400")]),
        _linha("geometria", F, "GeometryServer: areasAndLengths, lengths e distance",
               "suportado", "areas_lengths",
               [_pytest(f"{M}::test_areas_and_lengths_geodesico_bate_com_postgis"),
                _pytest(f"{M}::test_lengths_e_distance")]),
        _linha("geometria", F, "GeometryServer: union, intersect, difference, convexHull e simplify",
               "suportado", "geometry_service",
               [_pytest(f"{M}::test_union_intersect_difference_convex_hull_e_simplify")]),
        _linha("geometria", F, "GeometryServer: teto de lote e pedido malformado sem 500",
               "suportado", "geometry_service",
               [_pytest(f"{M}::test_lote_de_geometrias_acima_do_teto_e_recusado"),
                _pytest(f"{M}::test_geometry_server_recusa_pedido_malformado_sem_500"),
                _pytest(f"{M}::test_geometry_server_descritor")]),
    ]

    # --- serviços Esri que este repositório NÃO tem (a matriz existe para dizer isso com a mesma clareza)
    linhas += [
        _linha("ausente", "L2-04-i-wms-wmts-sld", "WMS, WMTS e SLD",
               "fora", "feature_service", [_pytest(f"{C}::test_nao_existe_rota_wms_neste_repositorio")],
               "medido: GET /wms/{item} devolve 404 e o OpenAPI não tem caminho WMS/WMTS"),
        _linha("ausente", "L2-04-k-sync-replicas-esri", "createReplica, syncReplica e extractChanges",
               "fora", "feature_service", [], "não implementado; item ainda não feito"),
    ]

    # --- clientes
    linhas += [
        _linha("cliente", "L2-04-j-conformidade-clientes-e-paridade", "owslib (WFS 2.0): GetCapabilities e GetFeature",
               "suportado", "ogc_features", [_pytest(f"{C}::test_owslib_le_o_getcapabilities_do_nosso_wfs_2_0"),
                                             _pytest(f"{C}::test_owslib_faz_getfeature_e_devolve_as_feicoes_da_camada")]),
        _linha("cliente", "L2-04-j-conformidade-clientes-e-paridade", "owslib (WMS)",
               "fora", "ogc_features", [_pytest(f"{C}::test_nao_existe_rota_wms_neste_repositorio")],
               "não há o que o cliente WMS possa ler: a rota não existe"),
        _linha("cliente", "L2-04-j-conformidade-clientes-e-paridade",
               "cliente HTTP puro: FeatureServer e OGC API Features",
               "suportado", "feature_service", [_pytest(f"{C}::test_featureserver_responde_ao_cliente_http_puro"),
                                                _pytest(f"{C}::test_ogc_api_features_responde_ao_cliente_http_puro")]),
        _linha("cliente", "L2-04-j-conformidade-clientes-e-paridade",
               "QGIS: ArcGIS REST, OGC API Features, WFS, WMS, WMTS e tile vetorial",
               "nao_medido", "feature_service", [_pytest(f"{C}::test_clientes_ausentes_sao_medidos_nao_presumidos")],
               "QGIS não está instalado nesta máquina (medido: qgis e qgis_process ausentes do PATH) e a "
               "imagem oficial em contêiner não cabe no orçamento de disco desta trilha (raiz a 93 % de uso). "
               "Seis tipos de serviço ficam sem medida por cliente gráfico"),
        _linha("cliente", "L2-04-j-conformidade-clientes-e-paridade", "cliente Python arcgis: FeatureLayer.query()",
               "nao_medido", "arcgis_python", [_pytest(f"{C}::test_clientes_ausentes_sao_medidos_nao_presumidos")],
               "pacote arcgis ausente da venv (medido) e não instalado: a árvore de dependências dele passa "
               "de 1 GB, acima do que esta trilha pode gastar em disco"),
        _linha("cliente", "L2-04-j-conformidade-clientes-e-paridade", "ArcGIS Pro e ArcGIS Online reais",
               "nao_medido", "feature_service", [],
               "exige licença e credencial de parceiro: o protocolo de teste está escrito em "
               "docs/TESTE_PARCEIRO_PRO_AGOL.md e o resultado fica pendente até haver evidência (decisão D20)"),
        _linha("cliente", "L2-04-j-conformidade-clientes-e-paridade", "OGC teamengine (suíte oficial de conformidade)",
               "nao_medido", "ogc_features", [],
               "a suíte roda em contêiner que não está nesta máquina e não cabe no orçamento de disco; sem "
               "ela, a conformidade OGC afirmada aqui é a do nosso teste, não a do certificador"),
    ]
    return linhas


# ------------------------------------------------------------------ execução das provas
def _rodar_scripts(quais: list[str]) -> dict[str, dict[str, dict]]:
    """Roda cada roteiro de sonda e devolve {qual: {chave: veredito}}."""
    resultado: dict[str, dict[str, dict]] = {}
    for qual in quais:
        script, saida, campo, chave = SCRIPTS[qual]
        proc = subprocess.run([sys.executable, str(script)], cwd=str(RAIZ), capture_output=True, timeout=1800)
        if proc.returncode != 0:
            print(f"[aviso] {script.name} saiu com código {proc.returncode}; os vereditos dele ficam sem prova",
                  file=sys.stderr)
            print(proc.stderr.decode("utf-8", "replace")[-1500:], file=sys.stderr)
            resultado[qual] = {}
            continue
        dados = json.loads(saida.read_text(encoding="utf-8"))
        resultado[qual] = {v[chave]: v for v in dados[campo]}
    return resultado


def _rodar_pytest(nos: list[str]) -> dict[str, str]:
    """Roda os nós de teste numa rodada só e devolve {nodeid: passou|falhou|nao_executado}."""
    if not nos:
        return {}
    relatorio = RAIZ / ".conformidade_junit.xml"
    cmd = [str(RAIZ / "venv" / "bin" / "pytest"), *nos, "-q", "-p", "no:cacheprovider",
           f"--junit-xml={relatorio}"]
    subprocess.run(cmd, cwd=str(RAIZ), timeout=3600, check=False)
    if not relatorio.exists():
        return {}
    fora: dict[str, str] = {}
    for caso in ET.parse(relatorio).getroot().iter("testcase"):
        # o junit-xml do pytest não traz o caminho do arquivo: traz `classname` no formato
        # `tests.api.test_x` (módulo pontuado). Reconstituir o nodeid é trocar ponto por barra e
        # devolver o sufixo .py — sem isso TODA linha provada por pytest caía em "não executado".
        arquivo = (caso.get("file") or "").strip()
        if not arquivo:
            arquivo = caso.get("classname", "").replace(".", "/") + ".py"
        nodeid = f"{arquivo}::{caso.get('name')}"
        ruim = any(caso.find(t) is not None for t in ("failure", "error"))
        pulado = caso.find("skipped") is not None
        fora[nodeid] = "falhou" if ruim else ("pulado" if pulado else "passou")
    relatorio.unlink()
    return fora


def _veredito_da_prova(prova: dict, pytest_saida: dict[str, str], scripts_saida: dict) -> tuple[str, str]:
    if prova["tipo"] == "pytest":
        estado = pytest_saida.get(prova["referencia"], "nao_executado")
        return estado, f"pytest {prova['referencia']}"
    qual, chave = prova["referencia"].split("#", 1)
    veredito = scripts_saida.get(qual, {}).get(chave)
    if veredito is None:
        return "nao_executado", f"{SCRIPTS[qual][0].name} sem veredito para {chave}"
    estado = veredito.get("estado", "")
    evid = veredito.get("evidencia", "")[:200]
    # A sonda RODOU: ela é a prova. O veredito dela ("suportado"/"parcial"/"fora") é o que a linha
    # herda — um parâmetro que a doc Esri lista e que esta implementação não tem é `fora`, não
    # refutação. Refutação é prova que quebrou, não capacidade que a casa nunca prometeu.
    if estado in ("suportado", "parcial", "fora"):
        return f"passou:{estado}", f"{SCRIPTS[qual][0].name}#{chave} = {estado}: {evid}"
    return "falhou", f"{SCRIPTS[qual][0].name}#{chave} = {estado or 'sem estado'}: {evid}"


def executar(com_scripts: bool = True) -> dict:
    linhas = matriz()
    nos = sorted({p["referencia"] for li in linhas for p in li["provas"] if p["tipo"] == "pytest"})
    pytest_saida = _rodar_pytest(nos)
    scripts_saida = _rodar_scripts(list(SCRIPTS)) if com_scripts else {}

    for li in linhas:
        provas: list[dict] = []
        medidos: list[str] = []
        for prova in li["provas"]:
            estado, evidencia = _veredito_da_prova(prova, pytest_saida, scripts_saida)
            if estado.startswith("passou:"):
                medidos.append(estado.split(":", 1)[1])
                estado = "passou"
            provas.append({**prova, "resultado": estado, "evidencia": evidencia})
        li["provas"] = provas
        passaram = [p for p in provas if p["resultado"] == "passou"]
        falharam = [p for p in provas if p["resultado"] == "falhou"]
        if falharam:
            li["estado"] = "refutado"
        elif passaram:
            # o estado final é o mais conservador entre o declarado e o que a sonda mediu
            candidatos = [li["estado_declarado"], *medidos]
            li["estado"] = min(candidatos, key=lambda e: RANQUE.get(e, 0))
        elif li["estado_declarado"] in ("suportado", "parcial"):
            # afirmação sem prova executada: a regra deste item é que isso NÃO passa por suportado
            li["estado"] = "nao_medido"
            li["observacao"] = (li["observacao"] + " | " if li["observacao"] else "") + \
                "nenhuma prova desta linha rodou nesta execução"
        else:
            li["estado"] = li["estado_declarado"]

    versao = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(RAIZ), capture_output=True,
                            text=True).stdout.strip() or os.environ.get("PLAT_GIT_SHA", "")
    contagem = {e: sum(1 for li in linhas if li["estado"] == e) for e in ESTADOS}
    return {
        "item": "L2-04-j-conformidade-clientes-e-paridade",
        "gerado_em": datetime.datetime.now(datetime.UTC).isoformat(timespec="seconds"),
        "versao_do_repositorio": versao,
        "gerado_por": "tests/esri/conformidade.py",
        "regra": "linha 'suportado' sem prova que passou nesta rodada vira 'nao_medido'; "
                 "prova que falhou vira 'refutado'",
        "fontes": {k: {"url": u, "acesso_em": d} for k, (u, d) in FONTES.items()},
        "parametros_query_da_doc": len(PARAMETROS_QUERY_DOC),
        "scripts_executados": bool(com_scripts),
        "contagem": contagem,
        "total": len(linhas),
        "linhas": linhas,
    }


# ------------------------------------------------------------------ seção do docs/PARIDADE.md
SIMBOLO = {"suportado": "sim", "parcial": "parcial", "fora": "não", "nao_medido": "não medido",
           "refutado": "REFUTADO"}
TITULO_FAMILIA = {
    "query": "Operação `query` do FeatureServer",
    "diretorio": "Diretório, descritores e metadados",
    "edicao": "Edição compatível Esri",
    "anexos": "Anexos",
    "relacionamento": "Relacionamentos",
    "ogc_features": "OGC API Features",
    "wfs": "WFS 2.0",
    "tiles": "Tiles vetoriais e exportação",
    "ausente": "Serviços Esri que esta plataforma ainda não tem",
    "cliente": "Clientes",
}


def secao(dados: dict) -> str:
    c = dados["contagem"]
    linhas_md = [
        INICIO,
        "",
        "## Matriz de conformidade dos serviços (item L2-04-j)",
        "",
        f"Gerada por `tests/esri/conformidade.py` em {dados['gerado_em']}, sobre a versão "
        f"`{dados['versao_do_repositorio'][:12]}` do repositório. "
        f"{dados['total']} linhas: {c['suportado']} suportadas, {c['parcial']} parciais, "
        f"{c['fora']} fora, {c['nao_medido']} não medidas, {c['refutado']} refutadas.",
        "",
        "Regra desta tabela: **uma linha só fica `sim` se a prova nomeada ao lado passou na mesma "
        "execução que gerou a tabela**. Prova que falha derruba a linha para REFUTADO; linha sem prova "
        "executada cai para `não medido`. `não medido` nunca é o mesmo que `sim`.",
        "",
    ]
    for familia, titulo in TITULO_FAMILIA.items():
        do_grupo = [li for li in dados["linhas"] if li["familia"] == familia]
        if not do_grupo:
            continue
        linhas_md += [f"### {titulo}", "", "| linha | estado | prova | item |", "|---|---|---|---|"]
        for li in do_grupo:
            provas = "; ".join(f"`{p['referencia']}`" for p in li["provas"]) or "—"
            obs = f" <br> {li['observacao']}" if li["observacao"] else ""
            linhas_md.append(f"| {li['linha']}{obs} | {SIMBOLO[li['estado']]} | {provas} | `{li['item']}` |")
        linhas_md.append("")
    linhas_md += [
        "Fontes das listas de parâmetros e operações, com a data em que foram lidas:",
        "",
    ]
    for nome, f in dados["fontes"].items():
        linhas_md.append(f"- `{nome}`: {f['url']} (acesso em {f['acesso_em']})")
    linhas_md += [
        "",
        "ArcGIS Pro e ArcGIS Online não são testados por esta máquina: o protocolo para o parceiro "
        "rodar está em `docs/TESTE_PARCEIRO_PRO_AGOL.md` e o resultado segue **pendente** até haver "
        "evidência devolvida.",
        "",
        FIM,
    ]
    return "\n".join(linhas_md)


def _trocar_secao(texto: str, nova: str) -> str:
    if INICIO in texto and FIM in texto:
        antes = texto.split(INICIO)[0]
        depois = texto.split(FIM, 1)[1]
        return antes + nova + depois
    return texto.rstrip("\n") + "\n\n" + nova + "\n"


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--sem-scripts", action="store_true", help="não roda os roteiros de sonda (mais rápido)")
    p.add_argument("--secao", action="store_true", help="imprime a seção do PARIDADE.md a partir do JSON gravado")
    p.add_argument("--conferir", action="store_true", help="reprova se docs/PARIDADE.md divergir do JSON gravado")
    args = p.parse_args()

    if args.secao or args.conferir:
        dados = json.loads(SAIDA.read_text(encoding="utf-8"))
        nova = secao(dados)
        if args.secao:
            print(nova)
            return 0
        atual = PARIDADE.read_text(encoding="utf-8")
        if _trocar_secao(atual, nova) != atual:
            print("docs/PARIDADE.md está fora de dia com tests/esri/conformidade.json: rode `make conformidade`",
                  file=sys.stderr)
            return 1
        print("docs/PARIDADE.md em dia com a matriz")
        return 0

    dados = executar(com_scripts=not args.sem_scripts)
    SAIDA.write_text(json.dumps(dados, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    PARIDADE.write_text(_trocar_secao(PARIDADE.read_text(encoding="utf-8"), secao(dados)), encoding="utf-8")
    c = dados["contagem"]
    print(f"{dados['total']} linhas: " + " ".join(f"{k}={v}" for k, v in c.items()))
    print(f"gravado em {SAIDA} e seção regravada em {PARIDADE}")
    return 1 if c["refutado"] else 0


if __name__ == "__main__":
    sys.exit(main())
