#!/usr/bin/env python3
"""Gera `tests/migracao/respostas/portal.json` — o acervo de respostas gravadas que o servidor de mentira
(`tests/migracao/portal_falso.py`) devolve no lugar de um Portal/AGOL real.

FORMATO: copiado da referência pública do ArcGIS REST API (nomes de campo, tipos, unidades), lida em
setembro de 2026:
  https://developers.arcgis.com/rest/users-groups-and-items/portal-self/    (organização)
  https://developers.arcgis.com/rest/users-groups-and-items/search/         (results, total, start, num, nextStart)
  https://developers.arcgis.com/rest/users-groups-and-items/item/           (id, owner, type, typeKeywords, size,
                                                                            created/modified em milissegundos)
  https://developers.arcgis.com/rest/users-groups-and-items/item-data/      (documento do web map)
  https://developers.arcgis.com/rest/users-groups-and-items/item-resources/ (resources)
  https://developers.arcgis.com/rest/users-groups-and-items/related-items/  (relatedItems)
  https://developers.arcgis.com/rest/services-reference/enterprise/query-feature-service-layer/ (returnCountOnly)

CONTEÚDO: inventado, de uma organização fictícia ("SIG de teste interno"). Nenhum dado, nome, URL ou
credencial de cliente ou parceiro aparece aqui. O acervo é gerado de forma determinística (sem sorteio) para
que o mesmo comando produza sempre o mesmo arquivo e a conferência à mão continue valendo.

Uma coisa deliberada: `portals/<id>/users` e `community/groups/<id>/users` DEVOLVEM `email`, `fullName`,
`firstName` e `lastName`, como um portal de verdade devolve. É assim que o teste de LGPD prova alguma coisa:
o dado pessoal CHEGA ao leitor e mesmo assim não pode ser encontrado em lugar nenhum do banco depois.

Uso: venv/bin/python tests/migracao/respostas/gerar.py
"""

import hashlib
import json
from pathlib import Path

AQUI = Path(__file__).resolve().parent
ORG_ID = "0" * 31 + "1"
BASE_SERVICO = "https://sig-de-teste-interno.invalido/server/rest/services"
EPOCA = 1_700_000_000_000  # ms; base fixa para created/modified (nada de "agora": arquivo tem de ser estável)


def ident(semente: str) -> str:
    """Id de item no formato do portal: 32 hexadecimais. Determinístico a partir do nome."""
    return hashlib.sha256(semente.encode("utf-8")).hexdigest()[:32]


# (tipo, quantos, palavras-chave, tem serviço)
RECEITA = [
    ("Feature Service", 12, ["ArcGIS Server", "Data", "Feature Access", "Feature Service", "Hosted Service"], True),
    ("Feature Service", 3, ["ArcGIS Server", "Data", "Feature Access", "Feature Service"], True),
    ("Table", 2, ["ArcGIS Server", "Data", "Feature Access", "Table", "Hosted Service"], True),
    ("Map Service", 2, ["ArcGIS Server", "Data", "Map Service"], True),
    ("Image Service", 2, ["ArcGIS Server", "Data", "Image Service"], False),
    ("Vector Tile Service", 2, ["ArcGIS Server", "Data", "Vector Tile Service", "Hosted Service"], False),
    ("WMS", 2, ["Data", "Service", "OGC", "WMS"], False),
    ("Web Map", 8, ["ArcGIS Online", "Explorer Web Map", "Map", "Web Map"], False),
    ("Dashboard", 4, ["Dashboard", "Operations Dashboard"], False),
    ("Web Mapping Application", 3, ["JavaScript", "Map", "Online Map", "Web Map"], False),
    ("Web Experience", 2, ["EXB Experience", "JavaScript", "Web Experience"], False),
    ("StoryMap", 2, ["arcgis-storymaps", "StoryMap", "Web Application"], False),
    ("Notebook", 2, ["Notebook", "Python"], False),
    ("Form", 2, ["Form", "Survey123", "xForm"], False),
    ("CSV", 3, ["CSV"], False),
    ("Shapefile", 2, ["Shapefile"], False),
    ("File Geodatabase", 2, ["FGDB", "File Geodatabase"], False),
    ("Insights Workbook", 1, ["Insights", "Workbook"], False),
    ("Workflow", 1, ["Workflow Manager"], False),
    ("Hub Site Application", 1, ["Hub", "Hub Site", "OpenData"], False),
    ("Quantum Widget", 1, ["Tipo que a tabela desta casa não conhece"], False),
]
DONOS = ["ana.tec", "bruno.gis", "carla.campo", "diego.dados"]


def construir() -> dict:
    itens = []
    servicos = {}
    dados = {}
    contador = 0
    servicos_hospedados = []
    for r, (tipo, quantos, palavras, tem_servico) in enumerate(RECEITA):
        for n in range(quantos):
            contador += 1
            # o índice da receita entra no nome: 'Feature Service' aparece duas vezes (hospedado e não
            # hospedado) e sem ele os dois blocos gerariam o MESMO id de item e a mesma URL de serviço
            nome = f"{tipo.lower().replace(' ', '_')}_r{r}_{n + 1}"
            item_id = ident(nome)
            url = None
            if tem_servico:
                sufixo = "FeatureServer" if tipo in ("Feature Service", "Table") else "MapServer"
                url = f"{BASE_SERVICO}/{nome}/{sufixo}"
                camadas = []
                tabelas = []
                for c in range((n % 3) + 1):
                    camadas.append({"id": c, "name": f"{nome}_camada_{c}", "type": "Feature Layer",
                                    "geometryType": "esriGeometryPolygon"})
                if tipo == "Table":
                    tabelas = [{"id": 90, "name": f"{nome}_tabela", "type": "Table"}]
                    camadas = []
                servicos[url] = {
                    "currentVersion": 11.4, "serviceDescription": f"serviço {nome}",
                    "layers": camadas, "tables": tabelas,
                    # contagem determinística por camada: 1000*(c+1) + 7*n
                    "contagens": {str(c["id"]): 1000 * (c["id"] + 1) + 7 * n for c in camadas + tabelas},
                }
                if "Hosted Service" in palavras:
                    servicos_hospedados.append((item_id, url))
            itens.append({
                "id": item_id,
                "owner": DONOS[contador % len(DONOS)],
                "created": EPOCA + contador * 86_400_000,
                "modified": EPOCA + contador * 86_400_000 + 3_600_000,
                "lastViewed": EPOCA + contador * 86_400_000 + 7_200_000,
                "title": f"{tipo} de teste {n + 1}",
                "type": tipo,
                "typeKeywords": palavras,
                "description": "acervo fictício do SIG de teste interno",
                "tags": ["teste", "inventario"],
                "snippet": None,
                "url": url,
                "access": "public" if contador % 3 else "org",
                "size": 1024 * (contador * 13 % 997 + 1),
                "numViews": contador * 11,
            })

    # documentos: cada web map aponta para 3 serviços hospedados (dependência real, não inventada)
    web_maps = [i for i in itens if i["type"] == "Web Map"]
    for k, wm in enumerate(web_maps):
        camadas = servicos_hospedados[k % len(servicos_hospedados):][:3] or servicos_hospedados[:3]
        dados[wm["id"]] = {
            "operationalLayers": [
                {"id": f"camada_{j}", "layerType": "ArcGISFeatureLayer", "itemId": item_id, "url": url,
                 "title": f"camada {j}", "opacity": 1, "visibility": True}
                for j, (item_id, url) in enumerate(camadas)
            ],
            "baseMap": {"baseMapLayers": [{"id": "base", "layerType": "VectorTileLayer",
                                           "styleUrl": "https://basemaps.invalido/style.json"}],
                        "title": "Base"},
            "spatialReference": {"wkid": 4326},
            "version": "2.27",
        }
    # aplicativos apontam para o web map (app -> web map)
    for k, app in enumerate([i for i in itens if i["type"] in ("Dashboard", "Web Mapping Application")]):
        alvo = web_maps[k % len(web_maps)]["id"]
        dados[app["id"]] = {"version": 50, "widgets": [{"type": "mapWidget", "itemId": alvo}],
                            "values": {"webmap": alvo}}

    grupos = [
        {"id": ident(f"grupo_{i}"), "title": f"Grupo de teste {i}", "owner": DONOS[i % len(DONOS)],
         "access": "org", "isInvitationOnly": False}
        for i in range(1, 4)
    ]
    # membros COM dado pessoal, como um portal real devolve — o leitor tem de descartar tudo menos o login
    membros = {
        g["id"]: {
            "owner": g["owner"],
            "admins": [g["owner"]],
            "users": DONOS,
            "usersDetails": [{"username": d, "fullName": f"Nome Completo {d}", "email": f"{d}@exemplo.invalido"}
                             for d in DONOS],
        }
        for g in grupos
    }
    usuarios = [
        {"username": d, "fullName": f"Nome Completo {d}", "firstName": "Nome", "lastName": "Completo",
         "email": f"{d}@exemplo.invalido", "role": "org_publisher" if i else "org_admin",
         "userLicenseTypeId": "creatorUT", "disabled": False, "lastLogin": EPOCA + i * 3_600_000,
         "description": "descrição pessoal que não deve ser gravada"}
        for i, d in enumerate(DONOS)
    ]

    return {
        "org_id": ORG_ID,
        "self": {
            "id": ORG_ID, "name": "SIG de teste interno", "urlKey": "sig-de-teste-interno",
            "currentVersion": "11.4", "portalName": "ArcGIS Online", "isPortal": False,
            "access": "public", "user": {"username": DONOS[0], "role": "org_admin"},
        },
        "raiz": {"currentVersion": 11.4, "fullVersion": "11.4"},
        "itens": itens,
        "dados": dados,
        "servicos": servicos,
        "grupos": grupos,
        "membros": membros,
        "usuarios": usuarios,
    }


if __name__ == "__main__":
    acervo = construir()
    (AQUI / "portal.json").write_text(json.dumps(acervo, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"{len(acervo['itens'])} itens, {len(acervo['servicos'])} serviços, {len(acervo['grupos'])} grupos, "
          f"{len(acervo['usuarios'])} usuários")
