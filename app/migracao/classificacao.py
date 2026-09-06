"""Classificação prévia de um item de Portal/AGOL em `migra` / `migra_parcial` / `nao_migra`
(item L2-08-a-leitor-portal-inventario; a tabela é o insumo do relatório de migração, item L2-08-d).

O que a tabela responde é UMA pergunta: "quando a ferramenta de migração rodar, este item vira o quê aqui
dentro?". A resposta nunca é um palpite do modelo de linguagem: cada linha aponta para o item desta casa que
faz o trabalho (L2-08-b clonagem de camada hospedada, L2-08-c conversão de web map, L6-02 conexão externa,
L0-04 ingestão de arquivo) ou nomeia o recurso Esri que não tem equivalente aqui.

Três regras que valem para a tabela inteira:

1. **Tipo que não consta é `desconhecido`, nunca `nao_migra`.** O catálogo de tipos da Esri cresce a cada
   versão; dizer "não migra" sobre um tipo que ninguém leu é afirmar mais do que se mediu. `desconhecido`
   aparece no relatório como linha a decidir a mão, e a contagem de desconhecidos é publicada junto.

2. **`typeKeywords` decide o que o `type` não decide.** "Feature Service" é o mesmo `type` para uma camada
   hospedada no AGOL (que a L2-08-b clona) e para um serviço publicado num ArcGIS Server do cliente (que
   entra só como conexão referenciada, sem cópia do dado). Quem separa os dois é a palavra-chave
   "Hosted Service", declarada pelo próprio portal.

3. **`migra_parcial` sempre traz o motivo do que fica de fora**, na mesma linha — nunca um rótulo solto.

Fontes do vocabulário de tipos (lidas em setembro de 2026):
  https://developers.arcgis.com/rest/users-groups-and-items/items-and-item-types/
  https://developers.arcgis.com/rest/users-groups-and-items/item/
"""

from dataclasses import dataclass

MIGRA = "migra"
MIGRA_PARCIAL = "migra_parcial"
NAO_MIGRA = "nao_migra"
DESCONHECIDO = "desconhecido"
CLASSES = (MIGRA, MIGRA_PARCIAL, NAO_MIGRA, DESCONHECIDO)


@dataclass(frozen=True)
class Decisao:
    classe: str
    motivo: str


# tipo Esri (exato, como o portal devolve em `type`) -> decisão padrão
TABELA: dict[str, Decisao] = {
    # --- dado hospedado: clonado com esquema e feições (item L2-08-b)
    "Feature Service": Decisao(MIGRA, "camada hospedada clonada com esquema e feições (L2-08-b)"),
    "Table": Decisao(MIGRA, "tabela hospedada clonada (L2-08-b)"),
    "Feature Collection": Decisao(MIGRA, "feições embutidas no próprio item viram camada (L2-08-b)"),
    "Feature Collection Template": Decisao(MIGRA, "modelo de feições vira esquema de camada vazia (L2-08-b)"),
    # --- arquivo: entra pela ingestão do L0-04
    "CSV": Decisao(MIGRA, "arquivo carregado pela ingestão (L0-04)"),
    "GeoJson": Decisao(MIGRA, "arquivo carregado pela ingestão (L0-04)"),
    "Shapefile": Decisao(MIGRA, "arquivo carregado pela ingestão (L0-04)"),
    "File Geodatabase": Decisao(MIGRA, "lida pelo OpenFileGDB do GDAL na ingestão (L0-04)"),
    "GeoPackage": Decisao(MIGRA, "arquivo carregado pela ingestão (L0-04)"),
    "KML": Decisao(MIGRA, "arquivo carregado pela ingestão (L0-04)"),
    "KML Collection": Decisao(MIGRA, "arquivo carregado pela ingestão (L0-04)"),
    "Microsoft Excel": Decisao(MIGRA_PARCIAL, "tabela migra; fórmula, formatação e macro não"),
    # --- serviço de terceiro: entra como conexão referenciada (L6-02), sem cópia do dado
    "Map Service": Decisao(MIGRA, "serviço referenciado como conexão externa (L6-02-d)"),
    "Image Service": Decisao(MIGRA, "serviço referenciado como conexão externa (L6-02-d)"),
    "Vector Tile Service": Decisao(MIGRA, "serviço referenciado como conexão externa (L6-02)"),
    "Scene Service": Decisao(MIGRA_PARCIAL, "cena 3D referenciada; sem equivalente de edição 3D aqui"),
    "WMS": Decisao(MIGRA, "conexão externa WMS (L6-02)"),
    "WMTS": Decisao(MIGRA, "conexão externa WMTS (L6-02)"),
    "WFS": Decisao(MIGRA, "conexão externa WFS (L6-02)"),
    "OGCFeatureServer": Decisao(MIGRA, "conexão externa OGC API Features (L6-02)"),
    "Geodata Service": Decisao(NAO_MIGRA, "serviço de réplica do ArcGIS Server, sem equivalente aqui"),
    "Geometry Service": Decisao(NAO_MIGRA, "serviço de geometria do ArcGIS Server, sem equivalente aqui"),
    "Geoprocessing Service": Decisao(NAO_MIGRA, "geoprocessamento publicado do ArcGIS Server, sem equivalente"),
    "Geocoding Service": Decisao(MIGRA_PARCIAL, "o geocodificador da casa (L2-11-b) substitui o serviço; "
                                                "o locator do cliente em si não é copiado"),
    # --- documento
    "Web Map": Decisao(MIGRA_PARCIAL, "camadas, ordem, escala e estilo simples convertidos (L2-08-c); "
                                      "janela pop-up com Arcade e basemap Esri ficam de fora"),
    "Web Scene": Decisao(MIGRA_PARCIAL, "cena 3D lida como referência; sem editor 3D equivalente"),
    "Dashboard": Decisao(MIGRA_PARCIAL, "indicador e gráfico simples remontados a mão; "
                                        "ações entre elementos e Arcade não têm equivalente"),
    "Web Mapping Application": Decisao(MIGRA_PARCIAL, "depende do modelo: mapa e camadas migram, "
                                                     "a configuração do aplicativo não"),
    "Form": Decisao(MIGRA_PARCIAL, "formulário Survey123 exportado como XLSForm (L2-08-d) e importado "
                                   "pelo L5-03-e; lógica avançada e aparência não"),
    "Operation View": Decisao(NAO_MIGRA, "Operations Dashboard clássico, descontinuado pela própria Esri"),
    # --- o que NÃO tem equivalente (a lista que o relatório do L2-08-d publica)
    "Web Experience": Decisao(NAO_MIGRA, "Experience Builder não tem equivalente aqui"),
    "Web Experience Template": Decisao(NAO_MIGRA, "modelo de Experience Builder, sem equivalente"),
    "StoryMap": Decisao(NAO_MIGRA, "ArcGIS StoryMaps não tem equivalente aqui"),
    "StoryMap Theme": Decisao(NAO_MIGRA, "tema de StoryMaps, sem equivalente"),
    "Hub Site Application": Decisao(NAO_MIGRA, "ArcGIS Hub não tem equivalente aqui"),
    "Hub Page": Decisao(NAO_MIGRA, "ArcGIS Hub não tem equivalente aqui"),
    "Hub Initiative": Decisao(NAO_MIGRA, "ArcGIS Hub não tem equivalente aqui"),
    "Hub Event": Decisao(NAO_MIGRA, "ArcGIS Hub não tem equivalente aqui"),
    "Notebook": Decisao(NAO_MIGRA, "ArcGIS Notebooks não tem equivalente aqui"),
    "Workflow": Decisao(NAO_MIGRA, "Workflow Manager não tem equivalente aqui"),
    "Insights Workbook": Decisao(NAO_MIGRA, "ArcGIS Insights não tem equivalente aqui"),
    "Insights Page": Decisao(NAO_MIGRA, "ArcGIS Insights não tem equivalente aqui"),
    "Insights Model": Decisao(NAO_MIGRA, "ArcGIS Insights não tem equivalente aqui"),
    "Insights Theme": Decisao(NAO_MIGRA, "ArcGIS Insights não tem equivalente aqui"),
    "Knowledge Graph": Decisao(NAO_MIGRA, "ArcGIS Knowledge não tem equivalente aqui"),
    "Knowledge Studio Project": Decisao(NAO_MIGRA, "ArcGIS Knowledge não tem equivalente aqui"),
    "Indoors Map Configuration": Decisao(NAO_MIGRA, "ArcGIS Indoors não tem equivalente aqui"),
    "Pro Map": Decisao(NAO_MIGRA, "documento do ArcGIS Pro, sem leitor aqui"),
    "Pro Project": Decisao(NAO_MIGRA, "projeto do ArcGIS Pro, sem leitor aqui"),
    "Project Package": Decisao(NAO_MIGRA, "pacote do ArcGIS Pro, sem leitor aqui"),
    "Map Package": Decisao(NAO_MIGRA, "pacote do ArcGIS Desktop, sem leitor aqui"),
    "Layer Package": Decisao(NAO_MIGRA, "pacote de camada do ArcGIS Desktop, sem leitor aqui"),
    "Layout": Decisao(NAO_MIGRA, "layout de impressão do ArcGIS Pro, sem leitor aqui"),
    "Geoprocessing Package": Decisao(NAO_MIGRA, "pacote de geoprocessamento, sem leitor aqui"),
    "Rule Package": Decisao(NAO_MIGRA, "regra CityEngine, sem leitor aqui"),
    "Code Attachment": Decisao(NAO_MIGRA, "anexo de código de aplicativo Esri, sem equivalente"),
    "Application": Decisao(NAO_MIGRA, "aplicativo registrado no portal, sem equivalente"),
}

# palavras-chave de `typeKeywords` que MUDAM a decisão do `type` (regra 2 do cabeçalho)
_HOSPEDADO = "hosted service"
_UTILITY_NETWORK = "utility network"
_PARCEL = "parcel fabric"


def classificar(tipo: str, palavras_chave=(), url: str | None = None) -> Decisao:
    """Decisão para um item, dado o `type` e as `typeKeywords` que o portal declarou.

    Nunca levanta: tipo desconhecido devolve `Decisao(DESCONHECIDO, ...)` com o tipo citado no motivo, para
    que o relatório mostre exatamente o que não soube classificar."""
    palavras = {str(p).strip().lower() for p in (palavras_chave or ())}

    if _UTILITY_NETWORK in palavras:
        return Decisao(NAO_MIGRA, "rede de utilidades (Utility Network) não tem equivalente aqui")
    if _PARCEL in palavras:
        return Decisao(NAO_MIGRA, "malha de parcelas (Parcel Fabric) não tem equivalente aqui")

    if tipo in ("Feature Service", "Table") and _HOSPEDADO not in palavras:
        return Decisao(
            MIGRA_PARCIAL,
            "serviço não hospedado (sem a palavra-chave 'Hosted Service'): entra como conexão referenciada "
            "do L6-02-d, sem cópia do dado — o dado continua no ArcGIS Server do cliente",
        )

    decisao = TABELA.get(tipo)
    if decisao is not None:
        return decisao
    return Decisao(DESCONHECIDO, f"tipo {tipo!r} não consta na tabela de migração (decidir a mão)")


def resumo(linhas) -> dict[str, int]:
    """{classe: quantidade} com as quatro classes sempre presentes (zero é informação, não ausência)."""
    saida = dict.fromkeys(CLASSES, 0)
    for c in linhas:
        saida[c if c in saida else DESCONHECIDO] += 1
    return saida
