"""Unitários do manual gerado (item L7-04-a-manual-capturas-geradas).

Exercem o gerador (docs/gerar_manual.py) e as cláusulas estruturais do portão que vivem no git:
uma seção por tela do e2e, captura citada pelo próprio e2e, data-ajuda em toda tela e toda chave
com seção, captura de versão antiga reprova, JSON do painel de ajuda atualizado, site noindex e
nenhum nome de cliente. O e2e do painel (abrir, busca com 20 perguntas, 3 idiomas) está em
tests/e2e/test_ajuda_contexto.py."""

import importlib.util
import json
import re
import struct
import zlib
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
GERADOR = RAIZ / "docs" / "gerar_manual.py"


def _png_1x1() -> bytes:
    """PNG 1x1 transparente construído em runtime (weasyprint embute a imagem no PDF do teste)."""
    def pedaco(tipo: bytes, dados: bytes) -> bytes:
        return struct.pack(">I", len(dados)) + tipo + dados + struct.pack(">I", zlib.crc32(tipo + dados) & 0xFFFFFFFF)

    cabeca = struct.pack(">IIBBBBB", 1, 1, 8, 6, 0, 0, 0)
    imagem = zlib.compress(b"\x00\x00\x00\x00\x00")
    return (b"\x89PNG\r\n\x1a\n" + pedaco(b"IHDR", cabeca)
            + pedaco(b"IDAT", imagem) + pedaco(b"IEND", b""))


PNG_1X1 = _png_1x1()

NOMES_DE_CLIENTE = [
    "CBRE", "Novaterra", "novaterrageo", "iAgroSat", "iAgroIntel", "CENTELHA",
    "Novaterra Geoprocessamento", "Corp360", "Corporate Gestao",
]


def gerador():
    spec = importlib.util.spec_from_file_location("gerar_manual_l704a", GERADOR)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def secoes_reais():
    return gerador().carregar_secoes()


def telas(secoes):
    return [s for s in secoes if s["classe"] == "tela"]


def test_uma_secao_por_tela_e_campos_obrigatorios():
    secoes = secoes_reais()
    assert len(telas(secoes)) >= 10, "o manual precisa cobrir as telas do e2e"
    for s in secoes:
        assert s["titulo_en"] and s["titulo_es"], s["arquivo"]
        assert s["resumo_en"] and s["resumo_es"], s["arquivo"]
        assert s["palavras"] and s["palavras_en"] and s["palavras_es"], s["arquivo"]


def _itens_do_e2e(e2e, texto: str) -> list[str]:
    """Prefixos reais das capturas: o ITEM declarado no e2e ou no apoio que ele importa, e o
    prefixo fixo de um capturar() próprio do apoio (f"PREFIXO_{nome}.png", caso do catálogo)."""
    textos = [texto]
    itens = re.findall(r'^ITEM\s*=\s*"([^"]+)"', texto, re.M)
    for m in re.finditer(r"^from tests\.e2e\.(apoio\w*) import", texto, re.M):
        apoio = RAIZ / "tests" / "e2e" / f"{m.group(1)}.py"
        if apoio.is_file():
            t_apoio = apoio.read_text(encoding="utf-8")
            textos.append(t_apoio)
            itens += re.findall(r'^ITEM\s*=\s*"([^"]+)"', t_apoio, re.M)
    for t in textos:
        itens += re.findall(r'f"([A-Za-z0-9._-]+)_\{nome\}\.png"', t)
    return sorted(set(itens))


def test_toda_tela_do_e2e_tem_secao_e2e_existente_e_captura_citada():
    mod = gerador()
    for s in telas(secoes_reais()):
        e2e = RAIZ / s["e2e"]
        assert e2e.is_file(), f"{s['arquivo']}: e2e ausente {s['e2e']}"
        texto = e2e.read_text(encoding="utf-8")
        # e2e_captura: trecho literal que o e2e usa para gravar (Tela.capturar("x") ou "{ITEM}_x.png")
        assert s["e2e_captura"] in texto, f"{s['arquivo']}: {e2e.name} não contém {s['e2e_captura']!r}"
        # captura: nome final do arquivo; com ITEM (direto ou em apoio), casa com um dos prefixos
        itens = _itens_do_e2e(e2e, texto)
        if itens:
            assert any(s["captura"].startswith(f"{i}_") for i in itens), (
                f"{s['arquivo']}: captura {s['captura']!r} não casa com ITEM de {e2e.name}: {itens}"
            )
        else:
            assert s["captura"] in texto, f"{s['arquivo']}: {e2e.name} não produz {s['captura']}"
        pagina = RAIZ / "web" / s["pagina"]
        assert pagina.is_file(), f"{s['arquivo']}: página ausente {s['pagina']}"
        assert f'data-ajuda="{s["id"]}"' in pagina.read_text(encoding="utf-8"), (
            f"{s['arquivo']}: {s['pagina']} sem data-ajuda"
        )
        assert re.fullmatch(r"/[^\s]*", s["caminho"]), s["arquivo"]
    # o validador do gerador (mesma cláusula, pelo caminho do produto) também passa
    mod.validar(secoes_reais())


def test_toda_chave_de_ajuda_tem_secao():
    secoes = secoes_reais()
    ids = {s["id"] for s in secoes}
    sem_secao = []
    for pagina in RAIZ.joinpath("web").rglob("*.html"):
        for m in re.finditer(r'data-ajuda="([^"]+)"', pagina.read_text(encoding="utf-8")):
            if m.group(1) not in ids:
                sem_secao.append(f"{pagina.relative_to(RAIZ)}:{m.group(1)}")
    assert sem_secao == [], sem_secao


def test_captura_de_versao_antiga_reprova(tmp_path, monkeypatch):
    mod = gerador()
    secoes = secoes_reais()
    primeira = telas(secoes)[0]
    capturas = tmp_path / "capturas"
    capturas.mkdir()
    (capturas / f"{primeira['id']}@0.0.1.png").write_bytes(PNG_1X1)
    monkeypatch.setattr(mod, "DIR_CAPTURAS", capturas)
    velhas = mod.desatualizadas("0.1.0", secoes)
    assert velhas == [f"{primeira['id']}@0.0.1.png"], "captura de versão antiga tem de reprovar"
    assert mod.desatualizadas("0.0.1", secoes) == [], "versão igual não reprova"


def _base_tmp(tmp_path, monkeypatch, mod, versao="9.9.9"):
    """docs/ e capturas e web/dados falsos com captura da versão de teste para todas as telas."""
    docs_manual = tmp_path / "docs" / "manual"
    docs_manual.mkdir(parents=True)
    capturas = tmp_path / "capturas"
    capturas.mkdir()
    web_dados = tmp_path / "web" / "dados"
    web_dados.mkdir(parents=True)
    secoes = secoes_reais()
    for s in telas(secoes):
        (capturas / f"{s['id']}@{versao}.png").write_bytes(PNG_1X1)
    monkeypatch.setattr(mod, "DIR_MANUAL", docs_manual)
    monkeypatch.setattr(mod, "DIR_CAPTURAS", capturas)
    monkeypatch.setattr(mod, "DIR_WEB_DADOS", web_dados)
    monkeypatch.setattr(mod, "versao_atual", lambda: versao)
    return secoes


def test_montar_produz_html_noindex_json_e_pdf(tmp_path, monkeypatch):
    mod = gerador()
    secoes = _base_tmp(tmp_path, monkeypatch, mod)
    mod.montar(secoes, com_pdf=True)
    sitio = tmp_path / "docs" / "manual" / "index.html"
    html = sitio.read_text(encoding="utf-8")
    assert 'name="robots" content="noindex, nofollow"' in html
    for s in secoes:
        assert f'id="{s["id"]}"' in html, f"seção {s['id']} ausente do site"
    # captura copiada ao lado do site e nomeada <tela>@<versao>
    assert (tmp_path / "docs" / "manual" / "capturas" / f"{telas(secoes)[0]['id']}@9.9.9.png").is_file()
    manual_json = json.loads((tmp_path / "web" / "dados" / "manual.json").read_text(encoding="utf-8"))
    assert manual_json["versao"] == "9.9.9"
    assert {s["id"] for s in manual_json["secoes"]} == {s["id"] for s in secoes}
    pdf = tmp_path / "docs" / "manual" / "manual.pdf"
    assert pdf.is_file() and pdf.read_bytes()[:5] == b"%PDF-", "PDF não gerado"


def test_montar_reprova_secao_sem_captura_da_versao_atual(tmp_path, monkeypatch):
    mod = gerador()
    secoes = _base_tmp(tmp_path, monkeypatch, mod)
    # tira a captura base de uma tela: montar tem de reprovar (e não sair 0)
    primeira = telas(secoes)[0]
    (mod.DIR_CAPTURAS / f"{primeira['id']}@9.9.9.png").unlink()
    with pytest.raises(SystemExit, match="capturas base ausentes"):
        mod.montar(secoes, com_pdf=False)


def test_manual_json_commitado_esta_atualizado(tmp_path, monkeypatch):
    """o JSON que o painel de ajuda carrega é GERADO: se alguém edita um md e não regenera, reprova."""
    mod = gerador()
    web_dados = tmp_path / "dados"
    web_dados.mkdir()
    monkeypatch.setattr(mod, "DIR_WEB_DADOS", web_dados)
    mod.montar_json(mod.versao_atual(), secoes_reais())
    gerado = (web_dados / "manual.json").read_text(encoding="utf-8")
    commitado = (RAIZ / "web" / "dados" / "manual.json")
    assert commitado.is_file(), "web/dados/manual.json ausente: rode make manual (ou --so-json) e commit"
    assert gerado == commitado.read_text(encoding="utf-8"), (
        "web/dados/manual.json diverge de docs/manual: regenere com o gerador e commit"
    )


def test_site_do_manual_sem_nome_de_cliente():
    """a cláusula do portão, pelo caminho da suíte: nada de nome de cliente/parceiro nos textos do manual."""
    alvos = list((RAIZ / "docs" / "manual").glob("*.md"))
    alvos.append(RAIZ / "web" / "dados" / "manual.json")
    assert len(alvos) > 10
    for caminho in alvos:
        texto = caminho.read_text(encoding="utf-8")
        for nome in NOMES_DE_CLIENTE:
            assert not re.search(rf"\b{re.escape(nome)}\b", texto), f"{caminho.name} cita {nome}"


def test_rota_manual_noindex_e_404_sem_artefato(cliente, monkeypatch, tmp_path):
    from app import paginas

    fake = tmp_path / "raiz"
    (fake / "docs" / "manual").mkdir(parents=True)
    (fake / "docs" / "manual" / "index.html").write_text(
        "<!doctype html><html lang=\"pt-BR\"><head><meta name=\"robots\" content=\"noindex, nofollow\">"
        "<title>Manual do plat</title></head><body>ok</body></html>", encoding="utf-8"
    )
    monkeypatch.setattr(paginas, "ROOT", fake)
    r = cliente.get("/manual")
    assert r.status_code == 200
    assert r.headers["x-robots-tag"] == "noindex, nofollow"
    assert r.headers["cache-control"] == "no-store"
    assert "noindex" in r.text
    (fake / "docs" / "manual" / "index.html").unlink()
    r = cliente.get("/manual")
    assert r.status_code == 404
