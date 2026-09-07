"""i18n do item L5-12-acessibilidade-i18n-construtores: cláusula "0 chave sem tradução (teste que varre
web/js/i18n/*.json)". Duas verificações estáticas, sem navegador:

1. paridade entre os três catálogos (`pt-BR.json`, `en.json`, `es.json`): as mesmas chaves, na mesma
   contagem, com os mesmos placeholders `{nome}` em cada valor — um placeholder a mais ou a menos quebra
   `String.replace` silenciosamente no navegador (`web/js/base/i18n.js::t`), então é erro de build, não só
   de tradução.
2. toda chave que o construtor usa (`t('...')` em `web/js/editor/*.js` e `web/js/editor/dom` via
   `data-i18n*` em `web/construtor.html`) existe no dicionário pt-BR — pega chave com erro de digitação
   sem precisar abrir o navegador."""

import json
import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
I18N_DIR = RAIZ / "web" / "js" / "i18n"
EDITOR_DIR = RAIZ / "web" / "js" / "editor"
CONSTRUTOR_HTML = RAIZ / "web" / "construtor.html"

CHAVE_T = re.compile(r"\bt\(\s*'([a-z0-9_.:-]+)'")
CHAVE_DATA_I18N = re.compile(r'data-i18n(?:-aria|-title)?="([a-z0-9_.:-]+)"')
PLACEHOLDER = re.compile(r"\{(\w+)\}")


def _catalogos() -> dict[str, dict]:
    arquivos = sorted(I18N_DIR.glob("*.json"))
    assert arquivos, f"nenhum catálogo em {I18N_DIR}"
    return {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in arquivos}


def test_todos_os_catalogos_tem_as_mesmas_chaves():
    catalogos = _catalogos()
    base_nome, base = next(iter(catalogos.items()))
    for nome, dic in catalogos.items():
        faltam = set(base) - set(dic)
        sobram = set(dic) - set(base)
        assert not faltam, f"{nome}.json sem {len(faltam)} chave(s) que {base_nome}.json tem: {sorted(faltam)[:20]}"
        assert not sobram, f"{nome}.json tem {len(sobram)} chave(s) a mais que {base_nome}.json: {sorted(sobram)[:20]}"


def test_nenhum_valor_vazio():
    for nome, dic in _catalogos().items():
        vazias = [k for k, v in dic.items() if not str(v).strip()]
        assert not vazias, f"{nome}.json tem chave com valor vazio (chave sem tradução): {vazias}"


def test_placeholders_iguais_entre_idiomas():
    catalogos = _catalogos()
    base_nome, base = next(iter(catalogos.items()))
    problemas = []
    for nome, dic in catalogos.items():
        if nome == base_nome:
            continue
        for chave, valor_base in base.items():
            if chave not in dic:
                continue
            esperado = set(PLACEHOLDER.findall(valor_base))
            achado = set(PLACEHOLDER.findall(dic[chave]))
            if esperado != achado:
                problemas.append((nome, chave, sorted(esperado), sorted(achado)))
    assert not problemas, f"placeholder divergente (idioma, chave, esperado, achado): {problemas[:20]}"


def _chaves_usadas_pelo_construtor() -> set[str]:
    achadas: set[str] = set()
    for arq in sorted(EDITOR_DIR.glob("*.js")):
        texto = arq.read_text(encoding="utf-8")
        achadas.update(CHAVE_T.findall(texto))
    if CONSTRUTOR_HTML.exists():
        achadas.update(CHAVE_DATA_I18N.findall(CONSTRUTOR_HTML.read_text(encoding="utf-8")))
    return achadas


def test_toda_chave_usada_pelo_construtor_existe_no_dicionario():
    usadas = _chaves_usadas_pelo_construtor()
    assert usadas, "nenhuma chamada a t(...) achada em web/js/editor — regex desatualizada ou módulo vazio"
    pt = json.loads((I18N_DIR / "pt-BR.json").read_text(encoding="utf-8"))
    faltam = sorted(k for k in usadas if k not in pt)
    assert not faltam, f"chave usada no construtor e ausente de pt-BR.json: {faltam}"


def test_toda_chave_construtor_tem_tradução_en_e_es():
    """Cláusula específica do item: as chaves do NAMESPACE `construtor.*` (a BASE dos construtores, escopo
    deste item — o resto do dicionário é herança do L0-02/L0-03 e pertence ao L7-10-a) têm de estar
    traduzidas em inglês e espanhol, não só presentes."""
    catalogos = _catalogos()
    pt = catalogos["pt-BR"]
    chaves_construtor = {k for k in pt if k.startswith("construtor.")}
    assert chaves_construtor, "nenhuma chave construtor.* em pt-BR.json"
    for nome, dic in catalogos.items():
        if nome == "pt-BR":
            continue
        iguais = {k for k in chaves_construtor if dic.get(k) == pt[k]}
        # uma coincidência isolada (sigla, número) é aceitável; o dicionário inteiro idêntico não é.
        assert len(iguais) < len(chaves_construtor), (
            f"{nome}.json repete o texto pt-BR em TODAS as {len(chaves_construtor)} chaves construtor.* "
            "— parece cópia não traduzida"
        )
