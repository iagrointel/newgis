#!/usr/bin/env python3
"""Licença CURADA e testada por HTTP real, por fonte do acervo (item L6-01-g-licenca-curada; migração 043;
depende de L6-01-a-registro / `plat.acervo_camada`, migração 027, ENTREGUE).

    sudo -u postgres python3 scripts/acervo_licenca_sync.py [--banco iagro_sat] [--timeout 20] [--somente FONTE_ID]

Regra D17 (a mesma de `plat.acervo_ficha`/`plat.acervo_camada`): "dado público sem licença escrita" não conta.
Por isso este script NUNCA grava um tipo de licença a partir de suposição — cada linha da CURADORIA abaixo
aponta uma URL (ou endpoint de API) e uma forma de leitura (`metodo`); o script busca essa URL agora, por HTTP
de verdade, e só grava em `plat.acervo_licenca` se a resposta realmente contiver o termo esperado. Se a rede falhar, o
status mudar ou o termo sumir da página, a linha correspondente NÃO é gravada/atualizada (erro nunca é
sucesso) — e a rodada termina com código de saída 1, listando o que falhou.

Formas de leitura (campo `metodo` da curadoria, também gravado em `plat.acervo_licenca.metodo` para auditoria):
  - "html_regex": busca a URL como HTML e exige que TODAS as strings de `contem` apareçam (substring simples,
    case-insensitive) no corpo da resposta. `evidencia` = recorte literal ao redor da primeira que casar.
  - "ckan_package_show": a fonte publica um portal CKAN (`dadosabertos.<orgao>.gov.br` ou equivalente); busca
    `{base}/api/3/action/package_show?id={identificador_remoto}` e exige `license_id` == `licenca_esperada`.
    `evidencia` = license_title/license_id literais devolvidos pela API.
  - "dcat_data_json": a fonte publica um feed DCAT-US (`.../data.json`, convenção comum de portais ArcGIS Hub);
    procura o primeiro `dataset[].title` que contenha `busca_titulo` (substring, case-insensitive) E tenha
    campo `license` não vazio; `evidencia` = o texto de `license` (tags HTML removidas).

A CURADORIA (lista `CURADORIA` abaixo) é o único lugar onde um humano decidiu "esta fonte, geometricamente
registrada em plat.acervo_camada, provavelmente tem licença escrita nesta URL, deste tipo" — a partir de
pesquisa datada (handoff do item, 06-07/09/2026): 29 fontes com geometria (das 192 candidatas de
`plat.acervo_camada`) com página/API que MOSTRA um termo do vocabulário fechado. As outras 163 ficam de fora
desta rodada (WFS/GeoServer sem AccessConstraints preenchido, portal CKAN inexistente, WAF bloqueando acesso
não-navegador, ou o texto encontrado ser só o rodapé genérico "Todo o conteúdo deste site está publicado sob a
licença Creative Commons Atribuição-SemDerivações 3.0" do template `gov.br` — decidido NÃO contar como licença
de DADO, é o mesmo texto idêntico em dezenas de domínios .gov.br para o conteúdo EDITORIAL do site, não para os
arquivos geográficos; ver handoff e `decisoes_do_dono` D17 no estado.json do laço). Vocabulário fechado (sem
acento, mesmo CHECK da migração 043): CC0, CC-BY, CC-BY-SA, ODbL, dado-aberto-com-termo-do-orgao, Copernicus,
licenca-propria, nao-declarada.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime

import httpx
import psycopg2
import psycopg2.extras

TIMEOUT_PADRAO = 20.0
USER_AGENT = "plat-acervo-licenca/1.0 (+iAgroIntel; verificacao de licenca por HTTP, item L6-01-g)"

# license_id do CKAN -> tipo do vocabulário fechado desta plataforma. "other-open"/"other-pd" são os rótulos
# genéricos que os próprios portais (IBAMA, ANEEL) usam quando o publicador marcou "aberto"/"domínio público"
# sem escolher uma licença internacional nomeada — ainda É um termo escrito pelo órgão (D17), por isso vira
# 'dado-aberto-com-termo-do-orgao' e não 'nao-declarada'.
CKAN_LICENCA_PARA_TIPO = {
    "cc-by": "CC-BY",
    "cc-by-sa": "CC-BY-SA",
    "cc-zero": "CC0",
    "odc-odbl": "ODbL",
    "odc-by": "ODbL",
    "other-open": "dado-aberto-com-termo-do-orgao",
    "other-pd": "dado-aberto-com-termo-do-orgao",
}


@dataclass
class Curadoria:
    fonte_id: str
    tipo: str
    url: str
    metodo: str
    confianca: str
    identificador_remoto: str | None = None
    contem: list[str] = field(default_factory=list)          # html_regex
    licenca_esperada: str | None = None                        # ckan_package_show: license_id esperado
    busca_titulo: str | None = None                             # dcat_data_json: substring do título do dataset


CURADORIA: list[Curadoria] = [
    # --- ANEEL: portal CKAN dadosabertos.aneel.gov.br, ODbL confirmado em 5/5 pacotes amostrados (06/09) ---
    Curadoria("aneel", "ODbL", "https://dadosabertos.aneel.gov.br/api/3/action/package_show?id=agentes-do-setor-eletrico",
              "ckan_package_show", "portal-wide: ODbL confirmado em 5/5 pacotes ANEEL amostrados; correspondência "
              "de 'aneel' (agregador geral) com o pacote 'agentes-do-setor-eletrico' é por nome do órgão, não "
              "por link direto tabela→dataset.",
              identificador_remoto="agentes-do-setor-eletrico", licenca_esperada="odc-odbl"),
    Curadoria("aneel-bdgd", "ODbL", "https://dadosabertos.aneel.gov.br/api/3/action/package_show?id=base-de-dados-geografica-da-distribuidora-bdgd",
              "ckan_package_show", "correspondência exata por nome (BDGD = Base de Dados Geográfica da Distribuidora).",
              identificador_remoto="base-de-dados-geografica-da-distribuidora-bdgd", licenca_esperada="odc-odbl"),
    Curadoria("aneel-sigel", "ODbL", "https://dadosabertos.aneel.gov.br/api/3/action/package_show?id=empreendimentos-em-operacao",
              "ckan_package_show", "correspondência por nome do sistema (SIGEL cobre empreendimentos de geração "
              "em operação); não é o pacote com 'sigel' no slug (o CKAN da ANEEL não tem um pacote com esse nome).",
              identificador_remoto="empreendimentos-em-operacao", licenca_esperada="odc-odbl"),
    Curadoria("aneel-sigel-linhas-de-transmissao", "ODbL", "https://dadosabertos.aneel.gov.br/api/3/action/package_show?id=transmissao-e-distribuicao",
              "ckan_package_show", "correspondência direta por assunto (linhas de transmissão).",
              identificador_remoto="transmissao-e-distribuicao", licenca_esperada="odc-odbl"),

    # --- ANA: feed DCAT (data.json) do portal ArcGIS Hub; só as camadas BHO têm o campo `license` preenchido
    # entre as candidatas testadas (06/09) --- ver handoff: outras 7 fontes ANA com geometria ficam PENDENTES.
    Curadoria("ana-base-hidrografica-ottocodificada-bho", "licenca-propria",
              "https://dadosabertos.ana.gov.br/data.json", "dcat_data_json",
              "busca por título 'ottocodificada' no feed DCAT; 6 datasets BHO batem, todos com o MESMO texto de "
              "licença — usa o primeiro encontrado.", busca_titulo="ottocodificada"),
    Curadoria("ana-bho-base-hidrografica-ottocodificada", "licenca-propria",
              "https://dadosabertos.ana.gov.br/data.json", "dcat_data_json",
              "mesma família de dataset que ana-base-hidrografica-ottocodificada-bho (nomes trocados no acervo).",
              busca_titulo="ottocodificada"),

    # --- EPE: rodapé do próprio site (epe.gov.br), não o template genérico gov.br (texto próprio da EPE) ---
    Curadoria("epe-blocos-de-e-p", "CC-BY", "https://www.epe.gov.br/", "html_regex",
              "rodapé do site EPE, geral para todo o portal (não achado texto por-dataset separado).",
              contem=["Creative Commons Atribuição 4.0 Internacional (CC BY 4.0)"]),
    Curadoria("epe-eolica-offshore", "CC-BY", "https://www.epe.gov.br/", "html_regex",
              "rodapé do site EPE, geral para todo o portal.",
              contem=["Creative Commons Atribuição 4.0 Internacional (CC BY 4.0)"]),
    Curadoria("epe-gasodutos-planejados", "CC-BY", "https://www.epe.gov.br/", "html_regex",
              "rodapé do site EPE, geral para todo o portal.",
              contem=["Creative Commons Atribuição 4.0 Internacional (CC BY 4.0)"]),
    Curadoria("epe-linhas-de-transmissao-planejadas", "CC-BY", "https://www.epe.gov.br/", "html_regex",
              "rodapé do site EPE, geral para todo o portal.",
              contem=["Creative Commons Atribuição 4.0 Internacional (CC BY 4.0)"]),
    Curadoria("epe-polos-de-gas", "CC-BY", "https://www.epe.gov.br/", "html_regex",
              "rodapé do site EPE, geral para todo o portal.",
              contem=["Creative Commons Atribuição 4.0 Internacional (CC BY 4.0)"]),
    Curadoria("epe-subestacoes-planejadas", "CC-BY", "https://www.epe.gov.br/", "html_regex",
              "rodapé do site EPE, geral para todo o portal.",
              contem=["Creative Commons Atribuição 4.0 Internacional (CC BY 4.0)"]),

    # --- FUNAI: parágrafo específico sobre "geoprocessamento e mapas" na própria página fonte.url (não é o
    # rodapé genérico gov.br — é um texto próprio da FUNAI, achado no corpo do artigo) ---
    Curadoria("funai", "licenca-propria",
              "https://www.gov.br/funai/pt-br/atuacao/terras-indigenas/geoprocessamento-e-mapas", "html_regex",
              "URL é a própria fonte.url desta fonte no acervo; texto específico sobre geoprocessamento/mapas, "
              "não o rodapé genérico do template gov.br.",
              contem=["Licença de uso: o conteúdo dos arquivos correspondentes a geoprocessamento e mapas "
                      "poderão ser reproduzidos desde que citada a fonte"]),
    Curadoria("funai-terras-indigenas", "licenca-propria",
              "https://www.gov.br/funai/pt-br/atuacao/terras-indigenas/geoprocessamento-e-mapas", "html_regex",
              "mesma página; fonte_id distinto no acervo para a camada de terras indígenas.",
              contem=["Licença de uso: o conteúdo dos arquivos correspondentes a geoprocessamento e mapas "
                      "poderão ser reproduzidos desde que citada a fonte"]),

    # --- IBAMA: portal CKAN dadosabertos.ibama.gov.br, license_id por pacote (correspondência por nome/assunto,
    # não link direto tabela→dataset — mesmo cuidado que a casa já registra para outras minerações de URL) ---
    Curadoria("ibama-autorizacoes-de-supressao-asv-federal", "CC-BY",
              "https://dadosabertos.ibama.gov.br/api/3/action/package_show?id=supressao-de-vegetacao-nao-florestal-no-bioma-amazonia",
              "ckan_package_show", "ASV federal remete à supressão de vegetação não florestal no bioma Amazônia, "
              "regulada federalmente pelo IBAMA; é o único pacote de supressão do portal com license_id 'cc-by' "
              "(os demais são 'other-open'/'other-pd') — correspondência por assunto, não por link direto.",
              identificador_remoto="supressao-de-vegetacao-nao-florestal-no-bioma-amazonia", licenca_esperada="cc-by"),
    Curadoria("ibama-autos-de-infracao", "dado-aberto-com-termo-do-orgao",
              "https://dadosabertos.ibama.gov.br/api/3/action/package_show?id=fiscalizacao-auto-de-infracao",
              "ckan_package_show", "correspondência direta por nome.",
              identificador_remoto="fiscalizacao-auto-de-infracao", licenca_esperada="other-open"),
    Curadoria("ibama-dados-abertos", "dado-aberto-com-termo-do-orgao",
              "https://dadosabertos.ibama.gov.br/api/3/action/package_show?id=licencas-ambientais-de-atividades-e-empreendimentos-licenciados-pelo-ibama",
              "ckan_package_show", "fonte agregadora 'IBAMA dados abertos'; usa o pacote de licenças ambientais "
              "como representante do portal (mesmo license_id de outras amostras do mesmo portal).",
              identificador_remoto="licencas-ambientais-de-atividades-e-empreendimentos-licenciados-pelo-ibama",
              licenca_esperada="other-pd"),
    Curadoria("ibama-dof-documento-de-origem-florestal", "dado-aberto-com-termo-do-orgao",
              "https://dadosabertos.ibama.gov.br/api/3/action/package_show?id=dof-autorizacoes-de-exploracao-florestal",
              "ckan_package_show", "DOF = Documento de Origem Florestal; usa o pacote de autorizações de "
              "exploração florestal (mesmo license_id 'other-pd' confirmado também em dof-transportes e "
              "dof-conversoes, checado 06/09).",
              identificador_remoto="dof-autorizacoes-de-exploracao-florestal", licenca_esperada="other-pd"),
    Curadoria("ibama-sinaflor-autorizacoes-de-exploracao-supressao", "dado-aberto-com-termo-do-orgao",
              "https://dadosabertos.ibama.gov.br/api/3/action/package_show?id=sinaflor-autorizacao-de-supressao-de-vegetacao",
              "ckan_package_show", "correspondência direta por nome (SINAFLOR, autorização de supressão).",
              identificador_remoto="sinaflor-autorizacao-de-supressao-de-vegetacao", licenca_esperada="other-open"),
    Curadoria("ibama-termos-de-embargo-adipe-consulta-publica", "dado-aberto-com-termo-do-orgao",
              "https://dadosabertos.ibama.gov.br/api/3/action/package_show?id=fiscalizacao-termo-de-embargo",
              "ckan_package_show", "correspondência direta por nome (termo de embargo).",
              identificador_remoto="fiscalizacao-termo-de-embargo", licenca_esperada="other-open"),

    # --- INPE: página dedicada "Citações e Licença de Uso" do TerraBrasilis (não a home genérica) ---
    Curadoria("inpe-deter-alertas-amazonia-cerrado", "CC-BY-SA",
              "https://terrabrasilis.dpi.inpe.br/citacoes-e-licenca-de-uso/", "html_regex",
              "página própria do TerraBrasilis dedicada a citação/licença dos programas de monitoramento "
              "(DETER e PRODES são o mesmo programa guarda-chuva 'monitoramento dos biomas brasileiros').",
              contem=["creativecommons.org/licenses/by-sa/4.0"]),
    Curadoria("inpe-prodes-desmatamento-6-biomas", "CC-BY-SA",
              "https://terrabrasilis.dpi.inpe.br/citacoes-e-licenca-de-uso/", "html_regex",
              "mesma página; PRODES é o outro produto do mesmo programa.",
              contem=["creativecommons.org/licenses/by-sa/4.0"]),

    # --- MapBiomas: rodapé do site brasil.mapbiomas.org (achado 06/09: é CC BY 4.0, não CC-BY-SA 4.0 como a
    # nota antiga do acervo dizia — discrepância registrada no handoff/decisoes_do_dono) ---
    Curadoria("mapbiomas", "CC-BY", "https://brasil.mapbiomas.org/", "html_regex",
              "rodapé do site, geral para o projeto inteiro. CORRIGE a nota antiga do acervo.fonte.licenca "
              "('CC BY-SA 4.0') — o texto ao vivo diz 'CC BY 4.0'.",
              contem=["mediante referência", "CC BY 4.0"]),
    Curadoria("mapbiomas-alerta-alertas-validados", "CC-BY", "https://brasil.mapbiomas.org/", "html_regex",
              "mesmo rodapé, mesmo projeto guarda-chuva.",
              contem=["mediante referência", "CC BY 4.0"]),
    Curadoria("mapbiomas-colecoes-de-uso-e-cobertura-do-solo", "CC-BY", "https://brasil.mapbiomas.org/", "html_regex",
              "mesmo rodapé, mesmo projeto guarda-chuva.",
              contem=["mediante referência", "CC BY 4.0"]),

    # --- OSM: página oficial openstreetmap.org/copyright (canônica, não o arquivo .pbf binário da Geofabrik,
    # que não tem texto para buscar) ---
    Curadoria("openstreetmap", "ODbL", "https://www.openstreetmap.org/copyright", "html_regex",
              "página oficial de copyright/licença da OpenStreetMap Foundation.",
              contem=["Open Data Commons Open Database License", "ODbL"]),
    Curadoria("osm", "ODbL", "https://www.openstreetmap.org/copyright", "html_regex",
              "mesma fonte de dado (extrato Geofabrik de OSM), mesma licença.",
              contem=["Open Data Commons Open Database License", "ODbL"]),
    Curadoria("osrm-local", "ODbL", "https://www.openstreetmap.org/copyright", "html_regex",
              "OSRM local roteia sobre extrato OSM — licença herdada do dado-fonte (ODbL), mesma nota já "
              "registrada em acervo.fonte.licenca para este fonte_id.",
              contem=["Open Data Commons Open Database License", "ODbL"]),

    # --- Prefeitura de São Paulo: portal CKAN dados.prefeitura.sp.gov.br, CC0 confirmado (06/09) ---
    Curadoria("prefeitura-de-sao-paulo-2", "CC0",
              "https://dados.prefeitura.sp.gov.br/api/3/action/package_show?id=favelas", "ckan_package_show",
              "corresponde à nota já existente em acervo.fonte.licenca ('Creative Commons CCZero') para este "
              "fonte_id; confirma ao vivo com o pacote 'favelas' do portal CKAN da cidade.",
              identificador_remoto="favelas", licenca_esperada="cc-zero"),
]


def _log(msg: str) -> None:
    print(f"[acervo_licenca_sync] {msg}", file=sys.stderr, flush=True)


def _snippet(texto: str, agulha: str, ctx: int = 160) -> str:
    idx = texto.lower().find(agulha.lower())
    if idx < 0:
        return ""
    a, b = max(0, idx - ctx), min(len(texto), idx + len(agulha) + ctx)
    return re.sub(r"\s+", " ", texto[a:b]).strip()


def _strip_html(texto: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", texto)).strip()


@dataclass
class Resultado:
    fonte_id: str
    ok: bool
    http_status: int | None
    evidencia: str | None
    motivo_falha: str | None = None


def _verificar_html_regex(cliente: httpx.Client, c: Curadoria) -> Resultado:
    try:
        r = cliente.get(c.url)
    except httpx.HTTPError as e:
        return Resultado(c.fonte_id, False, None, None, f"erro de rede: {type(e).__name__}: {e}")
    if r.status_code != 200:
        return Resultado(c.fonte_id, False, r.status_code, None, f"HTTP {r.status_code} (esperado 200)")
    texto = r.text
    for agulha in c.contem:
        if agulha.lower() not in texto.lower():
            return Resultado(c.fonte_id, False, r.status_code, None, f"termo não encontrado na página: {agulha!r}")
    evidencia = _snippet(texto, c.contem[0])
    return Resultado(c.fonte_id, True, r.status_code, evidencia)


def _verificar_ckan(cliente: httpx.Client, c: Curadoria) -> Resultado:
    try:
        r = cliente.get(c.url)
    except httpx.HTTPError as e:
        return Resultado(c.fonte_id, False, None, None, f"erro de rede: {type(e).__name__}: {e}")
    if r.status_code != 200:
        return Resultado(c.fonte_id, False, r.status_code, None, f"HTTP {r.status_code} (esperado 200)")
    try:
        d = r.json()
    except ValueError:
        return Resultado(c.fonte_id, False, r.status_code, None, "resposta não é JSON válido")
    if not d.get("success"):
        return Resultado(c.fonte_id, False, r.status_code, None, "CKAN respondeu success=false")
    res = d.get("result", {})
    license_id = res.get("license_id")
    license_title = res.get("license_title")
    if license_id != c.licenca_esperada:
        return Resultado(c.fonte_id, False, r.status_code, None,
                          f"license_id mudou: esperado {c.licenca_esperada!r}, veio {license_id!r}")
    evidencia = f"pacote '{c.identificador_remoto}': license_id={license_id!r}, license_title={license_title!r}"
    return Resultado(c.fonte_id, True, r.status_code, evidencia)


def _verificar_dcat(cliente: httpx.Client, c: Curadoria) -> Resultado:
    try:
        r = cliente.get(c.url)
    except httpx.HTTPError as e:
        return Resultado(c.fonte_id, False, None, None, f"erro de rede: {type(e).__name__}: {e}")
    if r.status_code != 200:
        return Resultado(c.fonte_id, False, r.status_code, None, f"HTTP {r.status_code} (esperado 200)")
    try:
        d = r.json()
    except ValueError:
        return Resultado(c.fonte_id, False, r.status_code, None, "resposta não é JSON válido")
    datasets = d.get("dataset", [])
    busca = (c.busca_titulo or "").lower()
    for ds in datasets:
        titulo = (ds.get("title") or "").lower()
        licenca = (ds.get("license") or "").strip()
        if busca in titulo and licenca:
            evidencia = f"{_strip_html(licenca)} (dataset: {ds.get('title')})"
            return Resultado(c.fonte_id, True, r.status_code, evidencia)
    return Resultado(c.fonte_id, False, r.status_code, None,
                      f"nenhum dataset com título contendo {c.busca_titulo!r} e campo license não vazio")


VERIFICADORES = {
    "html_regex": _verificar_html_regex,
    "ckan_package_show": _verificar_ckan,
    "dcat_data_json": _verificar_dcat,
}

SQL_UPSERT = """
INSERT INTO plat.acervo_licenca
  (fonte_id, tipo, url_licenca, metodo, identificador_remoto, http_status, evidencia, confianca,
   verificado_em, atualizado_em)
VALUES
  (%(fonte_id)s, %(tipo)s, %(url_licenca)s, %(metodo)s, %(identificador_remoto)s, %(http_status)s,
   %(evidencia)s, %(confianca)s, %(verificado_em)s, now())
ON CONFLICT (fonte_id) DO UPDATE SET
  tipo = EXCLUDED.tipo, url_licenca = EXCLUDED.url_licenca, metodo = EXCLUDED.metodo,
  identificador_remoto = EXCLUDED.identificador_remoto, http_status = EXCLUDED.http_status,
  evidencia = EXCLUDED.evidencia, confianca = EXCLUDED.confianca, verificado_em = EXCLUDED.verificado_em,
  atualizado_em = now()
"""


def sincronizar(dsn_kwargs: dict, timeout: float, somente: str | None = None) -> dict:
    itens = [c for c in CURADORIA if somente is None or c.fonte_id == somente]
    if not itens:
        raise SystemExit(f"nenhum item da curadoria casa com --somente={somente!r}")

    conn = psycopg2.connect(cursor_factory=psycopg2.extras.RealDictCursor, **dsn_kwargs)
    conn.autocommit = False
    ok = falha = 0
    falhas: list[tuple[str, str]] = []
    try:
        with httpx.Client(timeout=timeout, follow_redirects=True, headers={"User-Agent": USER_AGENT}) as cliente:
            with conn.cursor() as cur:
                for c in itens:
                    verificador = VERIFICADORES[c.metodo]
                    res = verificador(cliente, c)
                    if not res.ok:
                        falha += 1
                        falhas.append((c.fonte_id, res.motivo_falha or "falha desconhecida"))
                        _log(f"FALHA {c.fonte_id}: {res.motivo_falha}")
                        continue
                    cur.execute(
                        SQL_UPSERT,
                        {
                            "fonte_id": c.fonte_id, "tipo": c.tipo, "url_licenca": c.url, "metodo": c.metodo,
                            "identificador_remoto": c.identificador_remoto, "http_status": res.http_status,
                            "evidencia": res.evidencia, "confianca": c.confianca,
                            "verificado_em": datetime.now(UTC),
                        },
                    )
                    ok += 1
                    _log(f"ok {c.fonte_id}: tipo={c.tipo} http={res.http_status}")
            conn.commit()
    finally:
        conn.close()
    return {"total": len(itens), "ok": ok, "falha": falha, "falhas": falhas}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--banco", default="iagro_sat")
    ap.add_argument("--timeout", type=float, default=TIMEOUT_PADRAO)
    ap.add_argument("--somente", default=None, help="roda só este fonte_id (depuração/teste)")
    args = ap.parse_args()

    stats = sincronizar({"dbname": args.banco}, args.timeout, args.somente)
    _log(f"total={stats['total']} ok={stats['ok']} falha={stats['falha']}")
    if stats["falha"]:
        for fonte_id, motivo in stats["falhas"]:
            _log(f"  pendente: {fonte_id}: {motivo}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
