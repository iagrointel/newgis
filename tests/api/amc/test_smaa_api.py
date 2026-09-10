"""O SMAA-2 simplificado (item L3-02-c) pela API: registro do tipo de job, contrato dos parâmetros e
criação do trabalho pelo inquilino demo. O cálculo em si tem prova de resposta conhecida em
tests/unit/test_amc_smaa.py; aqui o que se prova é que ele está exposto e que o contrato recusa
entrada inválida antes de enfileirar."""

import pytest

TRES_UNIDADES = [[100.0, 0.0], [0.0, 100.0], [49.0, 49.0]]
PARAMETROS = {
    "fatores": TRES_UNIDADES,
    "pesos_base": [0.5, 0.5],
    "ids_fatores": ["acesso", "declividade"],
    "n_sorteios": 200,
    "semente": 7,
    "posicoes": 3,
    "topo": 3,
}


def test_tipo_smaa_esta_registrado_com_o_recorte_da_tabela(sessao_a):
    r = sessao_a.get("/api/jobs/tipos")
    assert r.status_code == 200, r.text
    tipos = {t["nome"]: t for t in r.json()}
    assert "amc.smaa" in tipos, sorted(tipos)
    t = tipos["amc.smaa"]
    props = t["parametros_schema"]["properties"]
    for campo in ("fatores", "pesos_base", "ids_fatores", "semente", "posicoes", "topo", "combinador"):
        assert campo in props, campo
    assert props["posicoes"]["default"] == 20 and props["topo"]["default"] == 20
    assert t["perfil_minimo"] == "editor" and t["pesado"] is True
    assert "aceitabilidade" in t["descricao"] and "vetor central" in t["descricao"]


def test_criacao_do_job_smaa(sessao_a):
    r = sessao_a.post("/api/jobs", json={"tipo": "amc.smaa", "parametros": PARAMETROS})
    assert r.status_code == 201, r.text
    job = r.json()
    assert job["tipo"] == "amc.smaa" and job["estado"] in ("pendente", "executando", "concluido")
    lido = sessao_a.get(f"/api/jobs/{job['id']}")
    assert lido.status_code == 200 and lido.json()["id"] == job["id"]
    sessao_a.post(f"/api/jobs/{job['id']}/cancelar")


@pytest.mark.parametrize(
    "troca,campo",
    [
        ({"posicoes": 0}, "posicoes"),
        ({"topo": 0}, "topo"),
        ({"n_sorteios": 0}, "n_sorteios"),
        ({"fatores": [[1.0, 2.0], [3.0]]}, "fatores"),
        ({"pesos_base": []}, "pesos_base"),
    ],
)
def test_parametros_invalidos_sao_recusados_antes_de_enfileirar(sessao_a, troca, campo):
    r = sessao_a.post("/api/jobs", json={"tipo": "amc.smaa", "parametros": {**PARAMETROS, **troca}})
    assert r.status_code == 422, r.text
    corpo = r.json()
    assert corpo["erro"] == "parametros_invalidos"
    assert any(d["campo"].startswith(campo) for d in corpo["detalhe"]), corpo["detalhe"]


def test_sem_sessao_nao_cria_job_smaa(cliente):
    r = cliente.post("/api/jobs", json={"tipo": "amc.smaa", "parametros": PARAMETROS})
    assert r.status_code == 401 and r.json()["erro"] == "nao_autenticado"
