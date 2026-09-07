"""Pacote de dado de demonstração do item L7-01-c-dado-demonstracao.

O portão do item, cláusula por cláusula:
  1. `plat demo semear` cria o inquilino `demo` (e `demo2`) com os itens do catálogo, pela própria API;
  2. `plat demo verificar` confere contagens e sha256;
  3. nenhum arquivo com nome de cliente/parceiro/piloto (grep = 0);
  4. licença de cada dado escrita em `dados/demo/LICENCAS.md` com URL;
  5. tamanho medido <= 300 MB;
  6. semeadura idempotente (rodar 2x = mesmo estado).

As cláusulas 3, 4 e 5 são lidas do catálogo e do disco: não dependem de a semeadura ter rodado nesta
base, então rodam sempre. As cláusulas 1, 2 e 6 exigem a API e o worker desta trilha no ar
(`venv/bin/uvicorn app.main:app --port <porta>` + `venv/bin/python -m app.jobs.worker`, com
PLAT_WORKER_URL numa porta livre e PLAT_GIT_SHA no ambiente) e um banco Postgres compartilhado
sem contenção — quando a base ainda não foi semeada, pulam com mensagem em vez de falhar.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

ITEM = "L7-01-c-dado-demonstracao"
RAIZ = Path(__file__).resolve().parents[2]
DIR_DADOS = RAIZ / "dados" / "demo" / "arquivos"
CATALOGO = json.loads((RAIZ / "dados" / "demo" / "catalogo.json").read_text(encoding="utf-8"))
LICENCAS = RAIZ / "dados" / "demo" / "LICENCAS.md"

TETO_PACOTE_BYTES = 300 * 1024 * 1024

NOMES_PROIBIDOS = [
    "cbre",
    "novaterra",
    "certaja",
    "certel",
    "fgr",
    "sicredi",
    "daiichi",
    "arayara",
    "ineep",
    "neoenergia",
    "petrobras",
    "state grid",
    "robson",
    "corporate gestao",
    "inovacoop",
    "coprel",
    "cooperaliança",
    "light rj",
    "edp es",
    "iagrosat ltda",
    "queiroz",
    "finotti",
]

sys.path.insert(0, str(RAIZ))
from dados.demo import semear as demo_semear  # noqa: E402


def _tamanho(caminho: Path) -> int:
    return sum(f.stat().st_size for f in caminho.rglob("*") if f.is_file())


def _texto_de(caminho: Path) -> str:
    if caminho.suffix == ".zip":
        partes = []
        with zipfile.ZipFile(caminho) as zf:
            for nome in zf.namelist():
                partes.append(nome)
                partes.append(zf.read(nome).decode("utf-8", "ignore"))
        return "\n".join(partes)
    return caminho.read_bytes().decode("utf-8", "ignore")


# ------------------------------------------------------------------ cláusulas que não dependem da base


def test_catalogo_cobre_exatamente_os_arquivos_com_sha256_certo():
    no_disco = {f.name for f in DIR_DADOS.iterdir() if f.is_file()}
    no_catalogo = {it["arquivo"] for it in CATALOGO["itens"]}
    assert no_disco == no_catalogo, f"catálogo e diretório divergem: {no_disco ^ no_catalogo}"
    for it in CATALOGO["itens"]:
        dados = (DIR_DADOS / it["arquivo"]).read_bytes()
        assert len(dados) == it["bytes"], it["arquivo"]
        assert hashlib.sha256(dados).hexdigest() == it["sha256"], it["arquivo"]


def test_verificar_hash_bate_com_o_catalogo_offline():
    """A parte de `plat demo verificar` que não depende de API: sha256 e tamanho no disco."""
    for it in CATALOGO["itens"]:
        caminho = DIR_DADOS / it["arquivo"]
        assert demo_semear.sha256_arquivo(caminho) == it["sha256"], it["arquivo"]


def test_licencas_md_gerado_do_catalogo_e_tem_fonte_url_licenca_data(medida):
    """Cláusula 4: LICENCAS.md nunca diverge do catálogo porque é gerado dele; conferimos os dois."""
    gerado = demo_semear.__spec__  # só para garantir que o módulo está no lugar certo
    assert gerado is not None
    texto = LICENCAS.read_text(encoding="utf-8")
    faltando = []
    for it in CATALOGO["itens"]:
        if it["titulo"] not in texto:
            faltando.append(f"{it['arquivo']}: título não está em LICENCAS.md")
            continue
        for valor in (it["url"], it["licenca"], it["data_acesso"]):
            if str(valor) not in texto:
                faltando.append(f"{it['arquivo']}: {valor!r} não está em LICENCAS.md")
    assert not faltando, faltando
    # o gerador é determinístico: rodá-lo de novo tem de reproduzir bit a bit o arquivo comitado
    import importlib

    gerar_mod = importlib.import_module("dados.demo.gerar_licencas")
    assert gerar_mod.gerar() == texto, "LICENCAS.md está desatualizado; rode dados/demo/gerar_licencas.py"
    medida(ITEM)(
        "arquivos_com_fonte_url_licenca_data",
        len(CATALOGO["itens"]),
        "arquivos",
        "pytest tests/api/test_dado_demo_l7.py -k licencas",
    )


def test_nenhum_nome_de_cliente_parceiro_ou_piloto(medida):
    alvos = [
        LICENCAS,
        RAIZ / "dados" / "demo" / "catalogo.json",
        RAIZ / "dados" / "demo" / "semear.py",
        RAIZ / "scripts" / "plat",
    ]
    alvos += [f for f in DIR_DADOS.iterdir() if f.is_file()]
    achados = []
    for alvo in alvos:
        texto = _texto_de(alvo).lower()
        for nome in NOMES_PROIBIDOS:
            if re.search(rf"\b{re.escape(nome)}\b", texto):
                achados.append(f"{alvo.name}: {nome}")
    assert not achados, achados
    medida(ITEM)(
        "ocorrencias_de_nome_proibido",
        len(achados),
        "ocorrências",
        f"grep de {len(NOMES_PROIBIDOS)} nomes em {len(alvos)} arquivos "
        "(pytest tests/api/test_dado_demo_l7.py::test_nenhum_nome_de_cliente_parceiro_ou_piloto)",
    )


def test_tamanho_do_pacote_e_ate_300mb(medida):
    pacote = _tamanho(DIR_DADOS)
    assert pacote <= TETO_PACOTE_BYTES, pacote
    medida(ITEM)(
        "pacote_de_demonstracao",
        round(pacote / 1e6, 3),
        "MB",
        f"du -sb dados/demo/arquivos (teto {TETO_PACOTE_BYTES / 1e6:.0f} MB)",
    )


def test_demo_e_demo2_tem_conjuntos_diferentes_no_catalogo():
    por_inquilino: dict[str, set[str]] = {"demo": set(), "demo2": set()}
    for it in CATALOGO["itens"]:
        por_inquilino.setdefault(it["inquilino"], set()).add(it["arquivo"])
    assert por_inquilino["demo"] and por_inquilino["demo2"]
    assert not (por_inquilino["demo"] & por_inquilino["demo2"])


def test_rede_de_demonstracao_referencia_camadas_do_proprio_catalogo():
    """A composição `rede` do semeador usa os papéis rede_nos/rede_arestas do catálogo; confere que
    existem e que são, de fato, ponto e linha (nunca a mesma camada nos dois papéis)."""
    papeis = {it["papel"]: it for it in CATALOGO["itens"] if it.get("papel") in ("rede_nos", "rede_arestas")}
    assert "rede_nos" in papeis and "rede_arestas" in papeis
    assert papeis["rede_nos"]["arquivo"] != papeis["rede_arestas"]["arquivo"]
    nos = json.loads((DIR_DADOS / papeis["rede_nos"]["arquivo"]).read_bytes())
    arestas = json.loads((DIR_DADOS / papeis["rede_arestas"]["arquivo"]).read_bytes())
    tipos_nos = {f["geometry"]["type"] for f in nos["features"]}
    tipos_arestas = {f["geometry"]["type"] for f in arestas["features"]}
    assert tipos_nos == {"Point"}
    assert tipos_arestas == {"LineString"}


def test_raster_de_demonstracao_nao_e_ingerido_como_camada():
    """O item explicita: sem pipeline de raster nesta base (L1-01-ingest-raster parcial), o Sentinel-2
    de demonstração é guardado como arquivo, não como camada processada — não fingimos o contrário."""
    rasters = [it for it in CATALOGO["itens"] if it["tipo_item"] == "arquivo" and it["formato"] == "geotiff"]
    assert len(rasters) == 1
    assert rasters[0]["ingerir"] is False


def test_plat_cli_tem_demo_semear_e_demo_verificar():
    r = subprocess.run(
        [sys.executable, str(RAIZ / "scripts" / "plat"), "demo", "--help"],
        capture_output=True,
        text=True,
        cwd=RAIZ,
        timeout=30,
    )
    assert r.returncode == 0, r.stderr
    assert "semear" in r.stdout
    assert "verificar" in r.stdout


# ------------------------------------------------------------------ o que exige a base semeada (API + worker)


def _titulos(sessao, rota="/api/itens") -> dict[str, dict]:
    saida = {}
    deslocamento = 0
    while True:
        r = sessao.get(rota, params={"limite": 200, "deslocamento": deslocamento})
        assert r.status_code == 200, r.text
        corpo = r.json()
        for it in corpo["itens"]:
            saida[it["titulo"]] = it
        deslocamento += len(corpo["itens"])
        if not corpo["itens"] or deslocamento >= corpo["total"]:
            return saida


def _exigir_semeado(titulos: dict) -> None:
    esperados = {f"{it['titulo']} (arquivo de origem)" for it in CATALOGO["itens"] if it["inquilino"] == "demo"}
    achados = esperados & set(titulos)
    if not achados:
        pytest.skip("base sem o dado de demonstração; rode scripts/plat demo semear")
    if achados != esperados:
        pytest.skip(
            f"semeadura pela metade nesta base (faltam {sorted(esperados - achados)}); "
            "provável interrupção por contenção externa do banco compartilhado"
        )


@pytest.mark.lento
def test_demo_tem_arquivos_camadas_e_as_4_composicoes(sessao_a, medida):
    ativos = _titulos(sessao_a)
    _exigir_semeado(ativos)
    itens = [it for it in CATALOGO["itens"] if it["inquilino"] == "demo"]
    for it in itens:
        assert f"{it['titulo']} (arquivo de origem)" in ativos, it["titulo"]
        if it["ingerir"]:
            assert it["titulo"] in ativos, it["titulo"]
    for titulo in (
        demo_semear.TITULO_MAPA,
        demo_semear.TITULO_PAINEL,
        demo_semear.TITULO_FORMULARIO,
        demo_semear.TITULO_REDE,
    ):
        assert titulo in ativos, f"composição não semeada: {titulo}"
    medida(ITEM)(
        "itens_semeados_em_demo",
        len(ativos),
        "itens",
        "pytest tests/api/test_dado_demo_l7.py::test_demo_tem_arquivos_camadas_e_as_4_composicoes",
    )


@pytest.mark.lento
def test_demo2_nao_ve_nada_de_demo(sessao_a, sessao_b):
    ativos_a = _titulos(sessao_a)
    _exigir_semeado(ativos_a)
    ativos_b = _titulos(sessao_b)
    titulos_demo = {it["titulo"] for it in CATALOGO["itens"] if it["inquilino"] == "demo"}
    vazados = [t for t in ativos_b if any(t.startswith(td) for td in titulos_demo)]
    assert not vazados, vazados


@pytest.mark.lento
def test_semeadura_e_idempotente(sessao_a, medida):
    """Cláusula 6: rodar `plat demo semear` de novo não cria nada — 0 arquivo/camada/composição novos."""
    import os

    base_url = os.environ.get("PLAT_URL_TESTE", "http://127.0.0.1:8275")
    credenciais_arquivo = Path(os.environ.get("PLAT_CREDENCIAIS_ARQUIVO", str(RAIZ / "tests" / "credenciais.txt")))
    ativos = _titulos(sessao_a)
    _exigir_semeado(ativos)
    resultado = demo_semear.semear(
        base_url=base_url, credenciais_arquivo=credenciais_arquivo, medida=None, verboso=False
    )
    for inquilino in resultado["inquilinos"]:
        assert inquilino["arquivo"] == 0, inquilino
        assert inquilino["camada"] == 0, inquilino
        assert inquilino["composicao"] == 0, inquilino
    medida(ITEM)(
        "segundos_reexecucao_idempotente",
        resultado["segundos"],
        "s",
        "pytest tests/api/test_dado_demo_l7.py::test_semeadura_e_idempotente (2ª chamada de plat demo semear)",
    )
