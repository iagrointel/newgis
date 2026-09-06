"""O contrato comitado é o contrato de verdade (achado G4-01 do ataque adversarial ao grupo G4).

`docs/openapi.json` é lido por dois guardiões — `tests/api/test_eventos.py` (cobertura de evento) e
`tests/api/test_cruzado.py` (varredura A→B de isolamento). Enquanto ninguém comparasse o arquivo com a
aplicação viva, rota nova nascia FORA dos dois: o arquivo estava 28 rotas atrás do aplicativo, e `make openapi`
só escrevia o arquivo, sem conferir. Este teste faz a comparação e REPROVA quando os dois divergem; o conserto
é rodar `make openapi` e comitar o arquivo junto com a rota.

A comparação é de (método, caminho) — não byte a byte: a ordem das chaves e a formatação do JSON dependem da
versão do FastAPI/pydantic da máquina, e reprovar por isso seria ruído, não achado. O que importa aos dois
guardiões é o CONJUNTO de rotas.
"""

from pathlib import Path

from tests.api.conftest import arquivo_openapi

ROOT = Path(__file__).resolve().parents[2]


def rotas(spec: dict) -> set[tuple[str, str]]:
    return {
        (metodo.upper(), caminho)
        for caminho, metodos in spec["paths"].items()
        for metodo in metodos
        if metodo.upper() in ("GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS")
    }


def test_openapi_comitado_tem_as_mesmas_rotas_do_app_vivo():
    from app.main import app

    vivo = rotas(app.openapi())
    disco = rotas(arquivo_openapi())
    faltando = sorted(vivo - disco)
    sobrando = sorted(disco - vivo)
    assert faltando == [], (
        f"{len(faltando)} rota(s) da aplicação estão fora de docs/openapi.json — rode `make openapi` e comite "
        f"o arquivo: {faltando}"
    )
    assert sobrando == [], (
        f"{len(sobrando)} rota(s) de docs/openapi.json não existem mais na aplicação — rode `make openapi`: "
        f"{sobrando}"
    )
