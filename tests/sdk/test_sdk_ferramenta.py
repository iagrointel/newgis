"""SDK × ferramenta por job: `pla.ferramentas.buffer` cria o job, o worker desta suíte executa e o
resultado vira item `ferramenta_resultado` do catálogo com procedência (cláusula do portão). Os
erros de parâmetro são 422 tipados já na criação; job que falha levanta `FalhaJob` com o motivo.
A medida da cláusula fica em tests/medidas/L2-16-a-sdk-python-geo.json com PLAT_GRAVAR_MEDIDAS=1."""

import datetime
import os
import time

import pytest
from plat_geo import ErroValidacao, FalhaJob, NaoEncontrado

from tests.sdk.conftest import PREFIXO

PONTO = {"type": "Point", "coordinates": [220000.0, 7450000.0]}  # srid 31983 (SIRGAS 2000 UTM 23S)


def _ram_livre_gb() -> float:
    with open("/proc/meminfo", encoding="ascii") as arq:
        for linha in arq:
            if linha.startswith("MemAvailable:"):
                return int(linha.split()[1]) / 1024 / 1024
    return float("nan")


CARGA_MAXIMA = 8.0  # 12 núcleos; acima disso número de tempo é da disputa, não do produto


def test_buffer_devolve_item_com_procedencia(pla, medida):
    carga_1min = os.getloadavg()[0]
    contexto = (f"carga_1min={carga_1min:.2f}, ram_livre_gb={_ram_livre_gb():.2f}, "
                f"medido_em={datetime.datetime.now(datetime.UTC).strftime('%Y-%m-%dT%H:%M:%SZ')}")
    t0 = time.monotonic()
    r = pla.ferramentas.buffer(PONTO, 100.0, titulo=f"{PREFIXO}buffer-100m")
    decorrido_s = time.monotonic() - t0
    assert r["buffer"]["type"] == "Polygon"
    assert 30000 < r["area_m2"] < 32000  # círculo de 100 m (aproximação do polígono fica por dentro)
    assert r["srid"] == 31983 and r["item_id"]

    item = pla.catalogo.abrir(r["item_id"])
    assert item["tipo"] == "ferramenta_resultado"
    dados = item["dados"]
    assert dados["ferramenta"] == "ferramentas.buffer"
    assert dados["parametros"] == {"distancia_m": 100.0, "srid": 31983}
    assert dados["resultado"]["buffer"]["type"] == "Polygon"
    assert dados["job_id"] and len(dados["procedencia"]["sha256_geometria_entrada"]) == 64
    assert "shapely" in dados["procedencia"]["biblioteca"]

    # a procedência do JOB (montada pelo worker) também é alcançável pelo SDK
    job = pla.jobs.obter(dados["job_id"])
    assert job["proveniencia"]["tipo"] == "ferramentas.buffer"
    assert job["resultado"]["item_id"] == r["item_id"]

    if carga_1min > CARGA_MAXIMA:
        # regra da casa (cláusula de desempenho, 07/09): sob disputa o número não prova nada;
        # a cláusula FUNCIONAL (procedência) já foi provada acima e não depende do relógio
        return
    m = medida("L2-16-a-sdk-python-geo")
    m("ferramenta_buffer_fim_a_fim_s", round(decorrido_s, 3), "s",
      "pla.ferramentas.buffer(PONTO, 100.0) — criação do job, espera e leitura do item; " + contexto)


def test_srid_geografico_e_422_tipado(pla):
    """Refutação do item: gravar buffer em grau não tem unidade — a API recusa na criação do job."""
    with pytest.raises(ErroValidacao) as erro:
        pla.ferramentas.buffer({"type": "Point", "coordinates": [-46.6, -23.5]}, 100.0, srid=4326)
    assert erro.value.status == 422


def test_distancia_acima_do_teto_e_422_tipado(pla):
    with pytest.raises(ErroValidacao) as erro:
        pla.ferramentas.buffer(PONTO, 1.0e6)  # 1000 km > teto de 100 km (app/limites.py)
    assert erro.value.status == 422


def test_geometria_vazia_vira_falha_job_tipada(pla):
    with pytest.raises(FalhaJob) as erro:
        pla.ferramentas.executar("ferramentas.buffer", {"geometria": {"type": "Polygon",
                                                                      "coordinates": []},
                                                        "distancia_m": 10.0}, timeout_s=120)
    assert not erro.value.cancelado
    assert erro.value.job["estado"] == "falhou"
    assert "vazia" in (erro.value.job.get("erro") or "")


def test_cancelar_job_nao_explode(pla):
    from plat_geo import Conflito

    job = pla.jobs.criar("ferramentas.buffer", {"geometria": PONTO, "distancia_m": 1.0})
    try:
        saida = pla.jobs.cancelar(job["id"])
        assert saida["estado"] in ("cancelado", "pendente", "rodando")
    except Conflito:
        # o worker desta suíte pode ter concluído o job entre o criar e o cancelar: 409 tipado
        pass
    except NaoEncontrado:
        pytest.fail("job recém-criado não foi encontrado pelo próprio inquilino")
