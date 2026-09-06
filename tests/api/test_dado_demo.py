"""Conjunto de demonstração (item L0-13-dado-demonstracao).

O portão do item, cláusula por cláusula:
  1. o instalador semeia N itens (contagem fixa aqui) em <= 90 s medidos;
  2. cada arquivo tem linha em docs/DADO_DEMO.md com fonte, endereço, licença e data de acesso;
  3. nenhum nome de cliente, parceiro ou piloto no dado, no documento e no semeador (grep = 0);
  4. `demo2` tem conjunto DIFERENTE de `demo` (isolamento visível na tela);
  5. tamanho do repositório <= 3 GB, medido.

As cláusulas 2, 3, 4 (pelo catálogo) e 5 não dependem de a semeadura ter rodado nesta base. As que
dependem (contagem por inquilino e conjunto diferente NA BASE) pulam com mensagem quando a base
ainda não foi semeada, e falham se a semeadura estiver pela metade.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import zipfile
from pathlib import Path

import pytest

ITEM = "L0-13-dado-demonstracao"
RAIZ = Path(__file__).resolve().parents[2]
DIR_DADOS = RAIZ / "dados_demo" / "arquivos"
CATALOGO = json.loads((RAIZ / "dados_demo" / "catalogo.json").read_text(encoding="utf-8"))
DOC = RAIZ / "docs" / "DADO_DEMO.md"

# contagem FIXA (cláusula 1): por inquilino, um item de arquivo por arquivo do catálogo, um item de
# camada por arquivo ingerido, e mais um item na lixeira em `demo`.
ITENS_DEMO = 15
ITENS_DEMO2 = 6
SEGUNDOS_MAX = 90.0
CONJUNTO_MAX_BYTES = 50 * 1024 * 1024
REPOSITORIO_MAX_BYTES = 3 * 1024 * 1024 * 1024

# nomes que nunca podem aparecer em dado, documento ou código de demonstração (regra P7 do laço:
# cliente, parceiro e piloto). Palavra inteira, sem acento, sem diferenciar maiúscula.
NOMES_PROIBIDOS = [
    "cbre", "novaterra", "certaja", "certel", "fgr", "sicredi", "daiichi", "arayara", "ineep",
    "neoenergia", "petrobras", "state grid", "robson", "corporate gestao", "inovacoop", "coprel",
    "cooperaliança", "light rj", "edp es", "iagrosat ltda", "queiroz",
]


def _tamanho(caminho: Path) -> int:
    return sum(f.stat().st_size for f in caminho.rglob("*") if f.is_file())


def _texto_de(caminho: Path) -> str:
    """Texto pesquisável de qualquer arquivo do conjunto: o zip é aberto (o .dbf do shapefile está
    comprimido lá dentro e um grep cru não o alcançaria); o resto entra como bytes decodificados."""
    if caminho.suffix == ".zip":
        partes = []
        with zipfile.ZipFile(caminho) as zf:
            for nome in zf.namelist():
                partes.append(nome)
                partes.append(zf.read(nome).decode("utf-8", "ignore"))
        return "\n".join(partes)
    return caminho.read_bytes().decode("utf-8", "ignore")


def test_catalogo_cobre_exatamente_os_arquivos_com_sha256_certo():
    no_disco = {f.name for f in DIR_DADOS.iterdir() if f.is_file()}
    no_catalogo = {it["arquivo"] for it in CATALOGO["itens"]}
    assert no_disco == no_catalogo, f"catálogo e diretório divergem: {no_disco ^ no_catalogo}"
    for it in CATALOGO["itens"]:
        dados = (DIR_DADOS / it["arquivo"]).read_bytes()
        assert len(dados) == it["bytes"], it["arquivo"]
        assert hashlib.sha256(dados).hexdigest() == it["sha256"], it["arquivo"]


def test_cada_arquivo_tem_fonte_endereco_licenca_e_data_de_acesso_no_documento(medida):
    """Cláusula 2 do portão, lida no documento (não no catálogo): é o documento que alguém abre."""
    texto = DOC.read_text(encoding="utf-8")
    faltando = []
    for it in CATALOGO["itens"]:
        bloco = re.search(rf"^#### `{re.escape(it['arquivo'])}`$(.*?)(?=^#### |^## |\Z)",
                          texto, re.M | re.S)
        if bloco is None:
            faltando.append(f"{it['arquivo']}: sem bloco no documento")
            continue
        corpo = bloco.group(1)
        for rotulo, valor in (("Fonte", it["fonte"]), ("Endereço", it["url"]),
                              ("Licença", it["licenca"]), ("Data de acesso", it["data_acesso"])):
            linha = re.search(rf"^- {rotulo}: (.+)$", corpo, re.M)
            if linha is None or not linha.group(1).strip():
                faltando.append(f"{it['arquivo']}: sem {rotulo}")
            elif linha.group(1).strip() != str(valor).strip():
                faltando.append(f"{it['arquivo']}: {rotulo} diverge do catálogo")
    assert not faltando, faltando
    medida(ITEM)("arquivos_com_fonte_url_licenca_data", len(CATALOGO["itens"]), "arquivos",
                 "pytest tests/api/test_dado_demo.py -k documento")


def test_nenhum_nome_de_cliente_parceiro_ou_piloto(medida):
    """Cláusula 3: o grep de nomes proibidos tem de dar zero no dado, no documento e no semeador."""
    alvos = [DOC, RAIZ / "scripts" / "semear_dado_demo.py", RAIZ / "dados_demo" / "catalogo.json",
             RAIZ / "dados_demo" / "gerar_do_acervo.py"]
    alvos += [f for f in DIR_DADOS.iterdir() if f.is_file()]
    achados = []
    for alvo in alvos:
        texto = _texto_de(alvo).lower()
        for nome in NOMES_PROIBIDOS:
            if re.search(rf"\b{re.escape(nome)}\b", texto):
                achados.append(f"{alvo.name}: {nome}")
    assert not achados, achados
    medida(ITEM)("ocorrencias_de_nome_proibido", len(achados), "ocorrências",
                 f"grep de {len(NOMES_PROIBIDOS)} nomes em {len(alvos)} arquivos "
                 "(pytest tests/api/test_dado_demo.py::test_nenhum_nome_de_cliente_parceiro_ou_piloto)")


def test_tamanho_do_conjunto_e_do_repositorio(medida):
    """Cláusulas do tamanho: conjunto <= 50 MB e repositório <= 3 GB (guardrail de disco, D21)."""
    conjunto = _tamanho(DIR_DADOS)
    assert conjunto <= CONJUNTO_MAX_BYTES, conjunto
    # a árvore de trabalho (sem venv, sem var/) mais o diretório .git de verdade — num git worktree o .git
    # local é um arquivo de ponteiro, e o objeto pesado mora no --git-common-dir do repositório principal
    trabalho = sum(_tamanho(RAIZ / d) for d in ("app", "web", "db", "docs", "deploy", "osrm", "scripts", "tests"))
    trabalho += conjunto
    comum = subprocess.run(["git", "-C", str(RAIZ), "rev-parse", "--git-common-dir"],
                           capture_output=True, text=True, check=True).stdout.strip()
    caminho_git = Path(comum) if Path(comum).is_absolute() else (RAIZ / comum)
    tamanho_git = _tamanho(caminho_git)
    total = trabalho + tamanho_git
    assert total <= REPOSITORIO_MAX_BYTES, total
    medida(ITEM)("conjunto_de_demonstracao", round(conjunto / 1e6, 2), "MB", "du -sb dados_demo/arquivos")
    medida(ITEM)("repositorio_medido", round(total / 1e6, 2), "MB",
                 f"árvore de trabalho versionada mais {caminho_git} "
                 f"({round(tamanho_git / 1e6, 2)} MB); limite {REPOSITORIO_MAX_BYTES / 1e6:.0f} MB")


def test_install_chama_a_semeadura_e_so_em_ambiente_de_demonstracao():
    """Cláusula 1, parte do instalador: quem semeia é o install.sh, e só quando SEMEAR=true."""
    texto = (RAIZ / "install.sh").read_text(encoding="utf-8")
    assert "scripts/semear_dado_demo.py" in texto
    trecho = texto.split('echo "== h2b.')[1].split('echo "== h3.')[0]
    assert 'if [ "$SEMEAR" = true ]' in trecho
    assert "--base-url" in trecho and "--medida" in trecho


def test_demo_e_demo2_tem_conjuntos_diferentes_no_catalogo():
    """Cláusula 4 na origem: nenhum arquivo e nenhum título é semeado nos dois inquilinos."""
    por_inquilino = {"demo": set(), "demo2": set()}
    for it in CATALOGO["itens"]:
        por_inquilino[it["inquilino"]].add(it["arquivo"])
    assert por_inquilino["demo"] and por_inquilino["demo2"]
    assert not (por_inquilino["demo"] & por_inquilino["demo2"])
    titulos = {"demo": set(), "demo2": set()}
    for it in CATALOGO["itens"]:
        titulos[it["inquilino"]].add(it["titulo"])
    assert not (titulos["demo"] & titulos["demo2"])


# ------------------------------------------------------------------ o que exige a base semeada
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


def _exigir_semeado(titulos: dict, itens: list[dict]) -> None:
    esperados = {f"{it['titulo']} (arquivo de origem)" for it in itens}
    achados = esperados & set(titulos)
    if not achados:
        pytest.skip("base sem o dado de demonstração; rode scripts/semear_dado_demo.py (ou o install.sh)")
    assert achados == esperados, f"semeadura pela metade, faltam: {sorted(esperados - achados)}"


def test_demo_tem_a_contagem_fixa_de_itens(sessao_a, medida):
    itens = [it for it in CATALOGO["itens"] if it["inquilino"] == "demo"]
    ativos = _titulos(sessao_a)
    _exigir_semeado(ativos, itens)
    lixeira = _titulos(sessao_a, "/api/lixeira")
    do_conjunto = [t for t in list(ativos) + list(lixeira)
                   if any(t.startswith(it["titulo"]) for it in itens) or "retirada do catálogo" in t]
    assert len(do_conjunto) == ITENS_DEMO, sorted(do_conjunto)
    assert len(lixeira) >= 1, "nenhum item na lixeira"
    camadas = [t for t, v in ativos.items() if v["tipo"] == "camada_vetorial"]
    assert len(camadas) == sum(1 for it in itens if it["ingerir"])
    medida(ITEM)("itens_semeados_em_demo", len(do_conjunto), "itens",
                 f"{len(camadas)} camadas carregadas pela ingestão e {len(lixeira)} na lixeira "
                 "(pytest tests/api/test_dado_demo.py::test_demo_tem_a_contagem_fixa_de_itens)")


def test_demo2_tem_conjunto_diferente_e_nao_ve_o_de_demo(sessao_b, medida):
    """Cláusula 4 na base: o que `demo` tem não aparece em `demo2` (é o que a tela mostra)."""
    itens2 = [it for it in CATALOGO["itens"] if it["inquilino"] == "demo2"]
    ativos = _titulos(sessao_b)
    _exigir_semeado(ativos, itens2)
    assert len(ativos) == ITENS_DEMO2, sorted(ativos)
    titulos_demo = {it["titulo"] for it in CATALOGO["itens"] if it["inquilino"] == "demo"}
    vazados = [t for t in ativos if any(t.startswith(td) for td in titulos_demo)]
    assert not vazados, vazados
    medida(ITEM)("itens_semeados_em_demo2", len(ativos), "itens",
                 f"{len(vazados)} itens de demo vistos em demo2 "
                 "(pytest tests/api/test_dado_demo.py::test_demo2_tem_conjunto_diferente_e_nao_ve_o_de_demo)")


def test_cada_camada_semeada_leva_a_licenca_no_proprio_metadado(sessao_a):
    """Refutação do adversário: item de demonstração sem licença declarada. Cada item semeado carrega
    a licença em `termos_de_uso`, o órgão em `creditos` e o endereço da fonte em `url`."""
    itens = [it for it in CATALOGO["itens"] if it["inquilino"] == "demo"]
    ativos = _titulos(sessao_a)
    _exigir_semeado(ativos, itens)
    por_licenca = {it["titulo"]: it["licenca"] for it in itens}
    sem_licenca = []
    for titulo, resumo in ativos.items():
        base = titulo.replace(" (arquivo de origem)", "")
        if base not in por_licenca:
            continue
        r = sessao_a.get(f"/api/itens/{resumo['id']}")
        assert r.status_code == 200, r.text
        corpo = r.json()
        if not (corpo.get("termos_de_uso") or "").strip() or not (corpo.get("creditos") or "").strip():
            sem_licenca.append(titulo)
        elif corpo["termos_de_uso"].strip() != por_licenca[base].strip():
            sem_licenca.append(f"{titulo}: licença diferente do catálogo")
    assert not sem_licenca, sem_licenca


@pytest.mark.lento
def test_tempo_da_semeadura(medida):
    """Cláusula 1, o relógio: o instalador grava `tests/medidas/semente_dado_demo.json` a cada semeadura
    (opção --medida). O alvo do portão é 90 s para o conjunto inteiro, base vazia. Este teste lê o que a
    última semeadura mediu de verdade nesta máquina; nunca estima."""
    caminho = RAIZ / "tests" / "medidas" / "semente_dado_demo.json"
    if not caminho.exists():
        pytest.skip("sem medida de semeadura; rode scripts/semear_dado_demo.py --medida "
                    "tests/medidas/semente_dado_demo.json com a base vazia")
    dados = json.loads(caminho.read_text(encoding="utf-8"))
    criados = sum(i.get("arquivo", 0) + i.get("camada", 0) for i in dados["inquilinos"])
    if criados == 0:
        pytest.skip("a última semeadura medida não criou nada (base já semeada); meça com a base vazia")
    medida(ITEM)("segundos_da_semeadura", dados["segundos"], "s",
                 f"scripts/semear_dado_demo.py --medida (criou {criados} itens; alvo do portão: "
                 f"{SEGUNDOS_MAX:.0f} s)")
    assert dados["segundos"] <= SEGUNDOS_MAX, (
        f"semeadura levou {dados['segundos']} s (alvo {SEGUNDOS_MAX:.0f} s) criando {criados} itens"
    )
