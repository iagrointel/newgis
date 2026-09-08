"""Documentos de exemplo do motor multicritério, usados pelos testes de unidade e de API (itens L3-01-a/b).

O modelo abaixo é sintético e não cita cliente nem parceiro: dois fatores (um raster, um vetorial), uma restrição
por precaução, pesos declarados. Serve para provar forma e proveniência — não é um modelo recomendado para nada.
"""

import copy

# área de estudo pequena, em Goiás (zona UTM 22S, EPSG:31982), longe de divisa de zona: ~0,01° ≈ 1 km
AREA_PEQUENA = {
    "type": "Polygon",
    "coordinates": [[[-49.30, -16.70], [-49.29, -16.70], [-49.29, -16.69], [-49.30, -16.69], [-49.30, -16.70]]],
}


def area_retangulo(lon0: float, lat0: float, dlon: float, dlat: float) -> dict:
    return {"type": "Polygon", "coordinates": [[[lon0, lat0], [lon0 + dlon, lat0], [lon0 + dlon, lat0 + dlat],
                                                [lon0, lat0 + dlat], [lon0, lat0]]]}


def modelo_valido() -> dict:
    return copy.deepcopy({
        "esquema": "amc_modelo.v1",
        "nome": "modelo de teste interno",
        "descricao": "dois fatores e uma restrição; pesos escolhidos pelo usuário, não medidos",
        "combinador": {"tipo": "soma_ponderada_normalizada"},
        "dado_ausente": "excluir_fator",
        "fatores": [
            {
                "id": "declividade",
                "nome": "declividade média",
                "criterio": "terreno mais plano é melhor",
                "fonte": "modelo digital de elevação de teste",
                "unidade": "%",
                "direcao": "menor_melhor",
                "base": "engenharia",
                "camada": {"tipo": "item", "id": "00000000-0000-0000-0000-000000000001", "banda": 1},
                "extrator": {"tipo": "raster_media"},
                "transformacao": {"tipo": "linear", "minimo": 0, "maximo": 30, "direcao": "decrescente"},
                "peso": 3.0,
            },
            {
                "id": "dist_via",
                "nome": "distância à via pavimentada",
                "criterio": "quanto mais perto da via, melhor",
                "fonte": "malha viária de teste",
                "unidade": "m",
                "direcao": "menor_melhor",
                "base": "engenharia",
                "camada": {"tipo": "item", "id": "00000000-0000-0000-0000-000000000002"},
                "extrator": {"tipo": "linha_distancia_mais_proxima"},
                "transformacao": {"tipo": "degraus", "bandas": [{"ate": 500, "nota": 100}, {"ate": 2000, "nota": 60},
                                                                {"ate": 10000, "nota": 20}], "acima": 0},
                "peso": 1.5,
            },
        ],
        "restricoes": [
            {
                "id": "area_alagavel",
                "nome": "área alagável",
                "base": "precaucao",
                "fonte": "camada de teste",
                "camada": {"tipo": "item", "id": "00000000-0000-0000-0000-000000000003"},
                "buffer_m": 30,
                "regra": {"tipo": "intersecta"},
                "motivo": "vetado por precaução: unidade sobre área alagável",
            }
        ],
    })


def modelo_cinco_fatores() -> dict:
    """Cinco fatores — dois de raster, dois de polígono e um de ponto — mais uma restrição, como o portão do
    item L3-01-g-tela-motor exige. Sintético e sem nome de cliente: prova a FORMA (cinco extratores de três
    geometrias diferentes num modelo só) e serve de entrada para a tela do motor. As camadas ficam com id
    marcador que o teste troca por itens reais do catálogo antes de gravar."""
    m = modelo_valido()
    base = m["fatores"][0]
    quinto = [
        {**copy.deepcopy(base), "id": "declividade", "nome": "declividade média",
         "camada": {"tipo": "item", "id": "00000000-0000-0000-0000-000000000001", "banda": 1},
         "extrator": {"tipo": "raster_media"},
         "transformacao": {"tipo": "linear", "minimo": 0, "maximo": 30, "direcao": "decrescente"},
         "unidade": "%", "direcao": "menor_melhor", "peso": 3.0},
        {**copy.deepcopy(base), "id": "altitude", "nome": "altitude mediana",
         "criterio": "cota mais alta afasta a unidade da várzea",
         "fonte": "modelo digital de elevação de teste", "unidade": "m", "direcao": "maior_melhor",
         "camada": {"tipo": "item", "id": "00000000-0000-0000-0000-000000000004", "banda": 1},
         "extrator": {"tipo": "raster_mediana"},
         "transformacao": {"tipo": "linear", "minimo": 500, "maximo": 900, "direcao": "crescente"},
         "peso": 1.0},
        {**copy.deepcopy(base), "id": "uso_urbano", "nome": "fração de uso urbano",
         "criterio": "mais mancha urbana em volta, mais infraestrutura",
         "fonte": "uso e cobertura de teste", "unidade": "fração", "direcao": "maior_melhor",
         "camada": {"tipo": "item", "id": "00000000-0000-0000-0000-000000000005"},
         "extrator": {"tipo": "poligono_fracao_area"},
         "transformacao": {"tipo": "linear", "minimo": 0, "maximo": 1, "direcao": "crescente"},
         "peso": 2.0},
        {**copy.deepcopy(base), "id": "restricao_amb", "nome": "fração em área de restrição ambiental",
         "criterio": "quanto menos área restrita, melhor",
         "fonte": "camada ambiental de teste", "unidade": "fração", "direcao": "menor_melhor",
         "camada": {"tipo": "item", "id": "00000000-0000-0000-0000-000000000006"},
         "extrator": {"tipo": "poligono_fracao_area"},
         "transformacao": {"tipo": "linear", "minimo": 0, "maximo": 1, "direcao": "decrescente"},
         "peso": 2.5},
        {**copy.deepcopy(base), "id": "dist_acesso", "nome": "distância ao ponto de acesso mais próximo",
         "criterio": "quanto mais perto do acesso, melhor",
         "fonte": "pontos de acesso de teste", "unidade": "m", "direcao": "menor_melhor",
         "camada": {"tipo": "item", "id": "00000000-0000-0000-0000-000000000007"},
         "extrator": {"tipo": "ponto_distancia_mais_proximo"},
         "transformacao": {"tipo": "degraus",
                           "bandas": [{"ate": 500, "nota": 100}, {"ate": 2000, "nota": 60},
                                      {"ate": 10000, "nota": 20}], "acima": 0},
         "peso": 1.5},
    ]
    m["fatores"] = quinto
    m["nome"] = "modelo de teste interno com cinco fatores"
    return m


def modelo_sem_camada_externa() -> dict:
    """O mesmo modelo sem NENHUMA camada: serve para provar a forma do documento sem depender do catálogo."""
    m = modelo_valido()
    m["fatores"] = m["fatores"][:1]
    m["restricoes"] = []
    return m


# ---------------------------------------------------------------- inválidos, um por cláusula do portão
def peso_negativo() -> dict:
    m = modelo_valido()
    m["fatores"][0]["peso"] = -1.0
    return m


def fator_sem_transformacao() -> dict:
    m = modelo_valido()
    del m["fatores"][0]["transformacao"]
    return m


def soma_de_pesos_zero() -> dict:
    m = modelo_valido()
    for f in m["fatores"]:
        f["peso"] = 0.0
    return m


def fator_duplicado() -> dict:
    m = modelo_valido()
    m["fatores"][1]["id"] = m["fatores"][0]["id"]
    return m


INVALIDOS = {
    "peso_negativo": (peso_negativo, "fatores[].peso >= 0"),
    "fator_sem_transformacao": (fator_sem_transformacao, "fatores[].transformacao"),
    "soma_de_pesos_zero": (soma_de_pesos_zero, "soma(fatores[].peso) > 0"),
    "fator_duplicado": (fator_duplicado, "fatores[].id único"),
}
