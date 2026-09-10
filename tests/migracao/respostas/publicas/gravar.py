"""Grava, com URL e data, uma amostra de um serviço de feições PÚBLICO da Esri para os testes do item L2-08-b
(clonagem de camadas hospedadas): a raiz do FeatureServer, a camada 0 (domínios codificados, subtipos com
`typeIdField`, relacionamento com a tabela 1, anexos), a tabela 1, duas páginas de `query` da camada 0
(resultOffset 0 e 10, 10 feições cada), a página da tabela 1 para os mesmos requestid, e os três menores anexos
de uma feição (bytes em base64). Uso: `venv/bin/python tests/migracao/respostas/publicas/gravar.py` (precisa
de rede; o JSON gravado é o que os testes leem — sem rede eles continuam a passar)."""

import base64
import datetime as dt
import json
from pathlib import Path

import httpx

URL = "https://sampleserver6.arcgisonline.com/arcgis/rest/services/ServiceRequest/FeatureServer"
DESTINO = Path(__file__).resolve().parent / "servico_publico.json"


def main() -> None:
    c = httpx.Client(timeout=60, follow_redirects=True)

    def g(caminho, **q):
        q.setdefault("f", "json")
        r = c.get(URL + caminho, params=q)
        r.raise_for_status()
        return r.json()

    raiz = g("")
    camada0, tabela1 = g("/0"), g("/1")
    p1 = g("/0/query", where="1=1", outFields="*", returnGeometry="true", resultOffset=0, resultRecordCount=10,
           orderByFields=camada0["objectIdField"])
    p2 = g("/0/query", where="1=1", outFields="*", returnGeometry="true", resultOffset=10, resultRecordCount=10,
           orderByFields=camada0["objectIdField"])
    ids = [f["attributes"]["requestid"] for f in p1["features"] + p2["features"] if f["attributes"].get("requestid")]
    where = "requestid IN (" + ",".join("'" + i.replace("'", "''") + "'" for i in ids) + ")" if ids else "1=0"
    t1 = g("/1/query", where=where, outFields="*", returnGeometry="false", resultOffset=0, resultRecordCount=1000,
           orderByFields=tabela1["objectIdField"])
    contagem0 = g("/0/query", where="1=1", returnCountOnly="true")
    anexos = {}
    for f in p1["features"]:
        oid = f["attributes"][camada0["objectIdField"]]
        info = g(f"/0/{oid}/attachments")
        if info.get("attachmentInfos"):
            menores = sorted(info["attachmentInfos"], key=lambda a: a["size"])[:3]
            anexos[str(oid)] = {"attachmentInfos": menores, "bytes": {}}
            for a in menores:
                r = c.get(f"{URL}/0/{oid}/attachments/{a['id']}")
                r.raise_for_status()
                anexos[str(oid)]["bytes"][str(a["id"])] = base64.b64encode(r.content).decode("ascii")
            break
    DESTINO.write_text(json.dumps({
        "url": URL, "gravado_em": dt.datetime.now(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "raiz": raiz, "camadas": {"0": camada0, "1": tabela1},
        "paginas": {"0": [p1, p2], "1": [t1]}, "contagens": {"0": contagem0["count"], "1": len(t1["features"])},
        "anexos": {"0": anexos},
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    print("gravado", DESTINO, "feições", len(p1["features"]) + len(p2["features"]), "relacionadas", len(t1["features"]),
          "anexos", sum(len(v["bytes"]) for v in anexos.values()))


if __name__ == "__main__":
    main()
