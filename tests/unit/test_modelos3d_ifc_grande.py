"""IFC grande: tempo e memória do leitor (refutação declarada do item L2-09-c).

O adversário do item carrega um IFC de 50 MB e mede tempo e RAM do job. Este teste faz a mesma medida
com um arquivo SINTÉTICO do mesmo tamanho e da mesma forma do arquivo aberto (malha tesselada, um
elemento por conjunto de propriedades), e grava o número com a carga da máquina ao lado. Sintético
porque não existe IFC aberto de 50 MB no repositório e baixar um a cada rodada de teste tornaria a suíte
dependente de rede.

O teto de memória do tipo de job é `limites.MODELO3D_MEMORIA_MB`; se a medida passar dele, o número
publicado é este, e o conserto é ler o arquivo por partes — não é fingir que coube.

Marcado `lento`: não entra na rodada rápida.
"""

import resource
import time

import pytest

from app import limites
from app.modelos3d import ifc, montagem

pytestmark = pytest.mark.lento

ITEM = "L2-09-c-modelos-gltf-ifc-3dtiles"
ALVO_BYTES = 50 * 1024 * 1024


def _ifc_sintetico(alvo_bytes: int) -> tuple[str, int]:
    """IFC4 válido com N elementos de malha tesselada, até passar do tamanho pedido."""
    cabecalho = (
        "ISO-10303-21;\nHEADER;\nFILE_DESCRIPTION((''),'2;1');\n"
        "FILE_NAME('sintetico.ifc','2026-09-08T00:00:00',(''),(''),'plat/testes','plat','');\n"
        "FILE_SCHEMA(('IFC4'));\nENDSEC;\nDATA;\n"
        "#1=IFCPERSON('p','p',$,$,$,$,$,$);\n#2=IFCORGANIZATION($,'plat',$,$,$);\n"
        "#3=IFCPERSONANDORGANIZATION(#1,#2,$);\n#4=IFCAPPLICATION(#2,'1','plat','plat');\n"
        "#5=IFCOWNERHISTORY(#3,#4,$,.ADDED.,0,#3,#4,0);\n"
        "#6=IFCSIUNIT(*,.LENGTHUNIT.,.MILLI.,.METRE.);\n#7=IFCUNITASSIGNMENT((#6));\n"
        "#8=IFCCARTESIANPOINT((0.,0.,0.));\n#9=IFCAXIS2PLACEMENT3D(#8,$,$);\n"
        "#10=IFCLOCALPLACEMENT($,#9);\n"
        "#11=IFCGEOMETRICREPRESENTATIONCONTEXT($,'Model',3,1.E-5,#9,$);\n"
    )
    partes = [cabecalho]
    tamanho = len(cabecalho)
    proximo = 100
    n = 0
    while tamanho < alvo_bytes:
        base = proximo
        x = (n % 60) * 5000.0
        y = (n // 60) * 5000.0
        pontos = ",".join(
            f"({x + dx:.1f},{y + dy:.1f},{dz:.1f})"
            for dx, dy, dz in [(0, 0, 0), (4000, 0, 0), (4000, 3000, 0), (0, 3000, 0),
                               (0, 0, 2800), (4000, 0, 2800), (4000, 3000, 2800), (0, 3000, 2800)])
        faces = "(1,2,3),(1,3,4),(5,7,6),(5,8,7),(1,5,6),(1,6,2),(4,3,7),(4,7,8),(1,4,8),(1,8,5),(2,6,7),(2,7,3)"
        bloco = (
            f"#{base}=IFCCARTESIANPOINTLIST3D(({pontos}));\n"
            f"#{base + 1}=IFCTRIANGULATEDFACESET(#{base},$,.T.,({faces}),$);\n"
            f"#{base + 2}=IFCSHAPEREPRESENTATION(#11,'Body','Tessellation',(#{base + 1}));\n"
            f"#{base + 3}=IFCPRODUCTDEFINITIONSHAPE($,$,(#{base + 2}));\n"
            f"#{base + 4}=IFCWALL('{n:022d}',#5,'parede {n}','sintetica','solidwall',#10,#{base + 3},$,$);\n"
            f"#{base + 5}=IFCPROPERTYSINGLEVALUE('Carga',$,IFCLABEL('valor {n}'),$);\n"
            f"#{base + 6}=IFCPROPERTYSET('{n:022d}',#5,'Pset_WallCommon',$,(#{base + 5}));\n"
            f"#{base + 7}=IFCRELDEFINESBYPROPERTIES('{n + 1:022d}',#5,$,$,(#{base + 4}),#{base + 6});\n"
        )
        partes.append(bloco)
        tamanho += len(bloco)
        proximo += 10
        n += 1
    partes.append("ENDSEC;\nEND-ISO-10303-21;\n")
    return "".join(partes), n


def test_ifc_de_cinquenta_megabytes_tempo_e_memoria(medida):
    texto, esperados = _ifc_sintetico(ALVO_BYTES)
    dados = texto.encode("utf-8")
    assert len(dados) >= ALVO_BYTES
    import os

    carga = os.getloadavg()[0]
    antes = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    t0 = time.perf_counter()
    modelo = ifc.carregar(dados, max_bytes=limites.MODELO3D_ARQUIVO_BYTES)
    t_leitura = time.perf_counter() - t0
    t1 = time.perf_counter()
    glb_bytes, resumo = montagem.montar(modelo.elementos, "sintetico")
    t_montagem = time.perf_counter() - t1
    pico_mb = round((resource.getrusage(resource.RUSAGE_SELF).ru_maxrss - antes) / 1024, 1)

    assert len(modelo.elementos) == esperados
    assert resumo["elementos_com_forma"] == esperados
    medida(ITEM)("ifc_50mb_tempo_e_memoria", {
        "bytes_do_arquivo": len(dados), "elementos": esperados,
        "segundos_leitura": round(t_leitura, 2), "segundos_montagem": round(t_montagem, 2),
        "pico_de_memoria_mb": pico_mb, "teto_do_job_mb": limites.MODELO3D_MEMORIA_MB,
        "bytes_do_glb": len(glb_bytes), "carga_1min": round(carga, 2),
    }, "medida", "venv/bin/pytest tests/unit/test_modelos3d_ifc_grande.py -m lento")
    assert t_leitura + t_montagem < limites.MODELO3D_TIMEOUT_S
