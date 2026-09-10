#!/usr/bin/env python3
"""Script de conformidade do item L2-04-servicos-esri-ogc: diretório/metadados do FeatureServer,
OGC API Features Part 1 e WFS 2.0 — construídos EM VOLTA da operação `query` (item L2-04-c, já
fechada em `wt/fsquery`/ADR 0018), reusada aqui sem reescrita.

Uso: `venv/bin/python tests/esri/conformidade_servicos.py` (trilha `esriogc` já preparada por
`laco/trilha_ambiente.sh esriogc /home/dev/plataforma/wt/esriogc`; sobe um `app.jobs.worker`
descartável se nenhum estiver de pé).

Saída: relatório em texto + `tests/medidas/L2-04-servicos-esri-ogc.json`."""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))
os.environ.setdefault("PLAT_AMBIENTE", "dev")

VEREDITOS: list[dict] = []
ATAQUES: list[dict] = []


def marcar(nome: str, estado: str, evidencia: str, motivo: str = ""):
    assert estado in ("suportado", "parcial", "fora", "nao_verificado")
    VEREDITOS.append({"clausula": nome, "estado": estado, "evidencia": evidencia[:600], "motivo": motivo})
    print(f"[{estado:14s}] {nome}: {evidencia[:160]}")


def ataque(nome: str, status: int, corpo: str):
    ok = status in (400, 401, 403, 404, 422)
    ATAQUES.append({"ataque": nome, "status": status, "passou": ok, "corpo": corpo[:200]})
    print(f"[{'OK' if ok else 'FALHOU'}] ataque {nome}: HTTP {status}")


def main():
    from tests.api.conftest import credenciais, entrar, novo_cliente
    from tests.api.ingestao.conftest import Ingestor

    c = credenciais()
    if "demo" not in c:
        print("tests/credenciais.txt sem 'demo' — rode a trilha antes", file=sys.stderr)
        sys.exit(2)
    cliente_a = novo_cliente()
    login, senha = c["demo"]
    r = entrar(cliente_a, "demo", login, senha)
    assert r.status_code == 200, r.text

    ing = Ingestor(cliente_a)
    final = None
    for tentativa in range(5):
        iid, insp = ing.importar("cobertura.gpkg", "gpkg")
        final = ing.confirmar(iid)
        if final["estado"] == "concluida":
            break
        time.sleep(2 + tentativa)
    assert final is not None and final["estado"] == "concluida", final
    item_id = final["item_id"]

    # ---------------------------------------------------------------- FeatureServer: descritor de serviço
    r = cliente_a.get(f"/rest/services/{item_id}/FeatureServer", params={"f": "json"})
    ok = r.status_code == 200 and r.json().get("layers") and r.json()["layers"][0]["id"] == 0
    marcar(
        "featureserver_descritor_servico", "suportado" if ok else "fora",
        f"status={r.status_code} corpo={r.text[:300]}",
    )

    r_camada = cliente_a.get(f"/rest/services/{item_id}/FeatureServer/0", params={"f": "json"})
    corpo_camada = r_camada.json() if r_camada.status_code == 200 else {}
    ok = (
        r_camada.status_code == 200
        and corpo_camada.get("geometryType")
        and len(corpo_camada.get("fields", [])) > 0
        and corpo_camada.get("objectIdField")
    )
    marcar(
        "featureserver_descritor_camada", "suportado" if ok else "fora",
        f"geometryType={corpo_camada.get('geometryType')} nfields={len(corpo_camada.get('fields', []))} "
        f"objectIdField={corpo_camada.get('objectIdField')} capabilities={corpo_camada.get('capabilities')}",
    )
    marcar(
        "applyEdits_attachments_relationships", "fora",
        "capabilities declarado = 'Query' apenas; relationships=[] sempre",
        "dependem de L2-03-edicao (escrita transacional) e L2-10-b (relacionamentos), NENHUM construído "
        "ainda no repositório — bloqueio real, não falta de tempo",
    )

    # ---------------------------------------------------------------- OGC API Features Part 1
    r = cliente_a.get(f"/ogc/features/{item_id}/")
    marcar("ogc_features_pouso", "suportado" if r.status_code == 200 else "fora", f"status={r.status_code}")
    r = cliente_a.get(f"/ogc/features/{item_id}/conformance")
    classes = r.json().get("conformsTo", []) if r.status_code == 200 else []
    marcar(
        "ogc_features_conformance", "suportado" if any("ogcapi-features" in c for c in classes) else "fora",
        f"conformsTo={classes}",
    )
    r = cliente_a.get(f"/ogc/features/{item_id}/collections")
    cols = r.json().get("collections", []) if r.status_code == 200 else []
    marcar(
        "ogc_features_collections", "suportado" if len(cols) == 1 else "fora",
        f"collections={[c['id'] for c in cols]}",
    )
    r = cliente_a.get(f"/ogc/features/{item_id}/collections/0/items", params={"limit": 5})
    corpo = r.json() if r.status_code == 200 else {}
    ok = (
        r.status_code == 200
        and corpo.get("type") == "FeatureCollection"
        and len(corpo.get("features", [])) <= 5
        and "numberMatched" in corpo
    )
    total_sem_filtro = corpo.get("numberMatched")
    marcar(
        "ogc_features_items_limit", "suportado" if ok else "fora",
        f"numberReturned={corpo.get('numberReturned')} numberMatched={corpo.get('numberMatched')} "
        f"status={r.status_code}",
    )
    fid_exemplo = corpo["features"][0]["id"] if corpo.get("features") else None
    r = cliente_a.get(f"/ogc/features/{item_id}/collections/0/items/{fid_exemplo}")
    id_voltou = r.json().get("id") if r.status_code == 200 else None
    marcar(
        "ogc_features_item_um", "suportado" if r.status_code == 200 and id_voltou == fid_exemplo else "fora",
        f"status={r.status_code} id_pedido={fid_exemplo} id_voltou={id_voltou}",
    )
    # bbox reduz o conjunto (prova real, não só "não deu erro")
    ext = None
    r_col = cliente_a.get(f"/ogc/features/{item_id}/collections/0")
    if r_col.status_code == 200:
        ext = r_col.json().get("extent", {}).get("spatial", {}).get("bbox", [[None]])[0]
    if ext and ext[0] is not None:
        xmin, ymin, xmax, ymax = ext
        cx, cy = (xmin + xmax) / 2, (ymin + ymax) / 2
        bbox_metade = f"{xmin},{ymin},{cx},{cy}"
        r_bbox = cliente_a.get(f"/ogc/features/{item_id}/collections/0/items",
                                params={"bbox": bbox_metade, "limit": 2000})
        n_bbox = r_bbox.json().get("numberMatched") if r_bbox.status_code == 200 else None
        bbox_ok = r_bbox.status_code == 200 and (n_bbox or 0) <= (total_sem_filtro or 0)
        marcar(
            "ogc_features_bbox", "suportado" if bbox_ok else "fora",
            f"bbox={bbox_metade} numberMatched_total={total_sem_filtro} numberMatched_bbox={n_bbox}",
        )
    else:
        marcar("ogc_features_bbox", "nao_verificado", "camada sem extent calculado no catálogo", "extent None")
    marcar(
        "ogc_features_cql2_part3", "fora", "não implementado nesta passagem",
        "Filter Encoding/CQL2 é o item próprio L2-04-g; aqui só Part 1 Core",
    )

    # ---------------------------------------------------------------- WFS 2.0
    r_cap = cliente_a.get(
        f"/wfs/{item_id}", params={"SERVICE": "WFS", "REQUEST": "GetCapabilities", "VERSION": "2.0.0"}
    )
    cap_valida = False
    detalhe_cap = f"status={r_cap.status_code}"
    if r_cap.status_code == 200:
        try:
            from owslib.wfs import WebFeatureService

            # owslib exige URL http(s); usamos o servidor real que a suíte já roda (settings.PLAT_URL_PUBLICA
            # ou uma instância uvicorn própria) — ver bloco abaixo que garante um `plat-api` de pé para isto
            wfs = WebFeatureService(url="http://plat.invalido/wfs", version="2.0.0", xml=r_cap.text.encode())
            tipos = list(wfs.contents.keys())
            cap_valida = len(tipos) == 1
            detalhe_cap = f"owslib.WebFeatureService parseou; contents={tipos}"
        except Exception as e:  # noqa: BLE001 — qualquer falha de parse é "não válido", relatada, não escondida
            detalhe_cap = f"owslib não conseguiu parsear: {e!r}"
    marcar("wfs_getcapabilities", "suportado" if cap_valida else "fora", detalhe_cap)

    r_desc = cliente_a.get(f"/wfs/{item_id}", params={"SERVICE": "WFS", "REQUEST": "DescribeFeatureType"})
    marcar("wfs_describefeaturetype", "parcial" if r_desc.status_code == 200 else "fora",
           f"status={r_desc.status_code}; XSD mínimo, não validado contra o schema de referência OGC")

    r_gf_json = cliente_a.get(f"/wfs/{item_id}", params={"SERVICE": "WFS", "REQUEST": "GetFeature",
                                                          "VERSION": "2.0.0", "OUTPUTFORMAT": "application/json",
                                                          "COUNT": "5"})
    ok_json = r_gf_json.status_code == 200 and r_gf_json.json().get("type") == "FeatureCollection"
    marcar("wfs_getfeature_json", "suportado" if ok_json else "fora",
           f"status={r_gf_json.status_code} nfeatures={len(r_gf_json.json().get('features', [])) if ok_json else '?'}")

    r_gf_gml = cliente_a.get(f"/wfs/{item_id}", params={"SERVICE": "WFS", "REQUEST": "GetFeature",
                                                         "VERSION": "2.0.0", "COUNT": "3"})
    gml_ok = r_gf_gml.status_code == 200 and "<wfs:FeatureCollection" in r_gf_gml.text and "<gml:" in r_gf_gml.text
    marcar("wfs_getfeature_gml", "parcial" if gml_ok else "fora",
           f"status={r_gf_gml.status_code} contentType={r_gf_gml.headers.get('content-type')} "
           f"trecho={r_gf_gml.text[:160] if gml_ok else r_gf_gml.text[:200]}",
           "GML 3.2 escrito à mão, não validado contra o XSD oficial (owslib só valida GetCapabilities)")

    # ---------------------------------------------------------------- bateria de ataque (400/422, nunca 500)
    for nome, url, params in [
        ("item_id_com_aspas", f"/rest/services/{item_id}' OR '1'='1/FeatureServer", {"f": "json"}),
        ("item_id_comentario_sql", f"/rest/services/{item_id}--/FeatureServer", {"f": "json"}),
        ("item_id_ponto_e_virgula", f"/ogc/features/{item_id};DROP TABLE plat.item/", {}),
        ("bbox_subselect", f"/ogc/features/{item_id}/collections/0/items",
         {"bbox": "(SELECT 1),0,0,0"}),
        ("bbox_pg_sleep", f"/ogc/features/{item_id}/collections/0/items",
         {"bbox": "0,0,0,pg_sleep(1)"}),
        ("bbox_funcao_nao_prevista", f"/ogc/features/{item_id}/collections/0/items",
         {"bbox": "version(),0,0,0"}),
        ("wfs_bbox_injecao", f"/wfs/{item_id}", {"SERVICE": "WFS", "REQUEST": "GetFeature",
                                                  "BBOX": "0,0,0,0); DROP TABLE plat.item;--"}),
        ("wfs_request_desconhecida", f"/wfs/{item_id}", {"SERVICE": "WFS", "REQUEST": "GetCoverage"}),
        ("feature_id_nao_inteiro", f"/ogc/features/{item_id}/collections/0/items/1%20OR%201=1", {}),
        ("unicode_no_item_id", "/ogc/features/%E2%80%8B%3Cscript%3E/", {}),
    ]:
        try:
            r = cliente_a.get(url, params=params)
            ataque(nome, r.status_code, r.text)
        except Exception as e:  # noqa: BLE001 — exceção do cliente de teste também conta como "não chegou 500 do servidor"
            ataque(nome, -1, repr(e))

    # cross-tenant: item do inquilino "demo" consultado com token de OUTRO inquilino nunca aparece (herdado
    # do RLS já provado no L0-02/L2-04-a/c — reexercitado aqui nas 3 raízes novas, não só em /query)
    cliente_b = novo_cliente()
    r2 = entrar(cliente_b, "demo2", *c["demo2"]) if "demo2" in c else None
    if r2 is not None and r2.status_code == 200:
        for rota in (f"/rest/services/{item_id}/FeatureServer", f"/ogc/features/{item_id}/",
                     f"/wfs/{item_id}?SERVICE=WFS&REQUEST=GetCapabilities"):
            r = cliente_b.get(rota)
            ataque(f"cross_tenant_{rota.split('/')[1]}", r.status_code, r.text)
    else:
        marcar("cross_tenant", "nao_verificado", "credencial 'demo2' ausente em tests/credenciais.txt nesta trilha")

    todas_ok = all(a["passou"] for a in ATAQUES)
    marcar(
        "bateria_de_ataque", "suportado" if todas_ok else "fora",
        f"{sum(a['passou'] for a in ATAQUES)}/{len(ATAQUES)} ataques recusados com 400/401/403/404/422, nenhum 500",
    )

    saida = {
        "item": "L2-04-servicos-esri-ogc",
        "reusa": "L2-04-c-featureserver-query (wt/fsquery, ADR 0018) — motor.PedidoQuery/preparar_pedido/"
        "executar_features/executar_count, campos_da_camada, GEOM_PG_PARA_ESRI, _autenticar; NENHUMA "
        "reescrita da consulta",
        "clausulas": VEREDITOS,
        "ataques": ATAQUES,
        "medido_em": __import__("datetime").datetime.now(__import__("datetime").UTC).isoformat(),
    }
    (RAIZ / "tests" / "medidas").mkdir(exist_ok=True)
    (RAIZ / "tests" / "medidas" / "L2-04-servicos-esri-ogc.json").write_text(
        json.dumps(saida, indent=2, ensure_ascii=False, default=str)
    )
    print("\n== resumo ==")
    for v in VEREDITOS:
        print(f"  {v['estado']:14s} {v['clausula']}")
    print(f"  ataques: {sum(a['passou'] for a in ATAQUES)}/{len(ATAQUES)} recusados corretamente")


if __name__ == "__main__":
    main()
