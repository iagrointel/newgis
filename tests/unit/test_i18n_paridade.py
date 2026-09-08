"""Idiomas da interface (UX-02; base do L7-10-a): web/js/i18n/pt-BR.json é o dicionário de referência; en.json e
es.json têm de ter EXATAMENTE as mesmas chaves e, em cada chave, o mesmo conjunto de variáveis {nome} — senão a tela
mostra chave crua ou perde um parâmetro. Também: nenhum valor vazio, nenhum valor igual à própria chave, e a lista
de idiomas do servidor (app.limites PERFIL_IDIOMAS/ORG_IDIOMAS) só nomeia arquivos que existem."""

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
I18N = ROOT / "web" / "js" / "i18n"
REFERENCIA = "pt-BR"
OUTROS = ("en", "es")
RE_VAR = re.compile(r"\{(\w+)\}")


def _dic(idioma: str) -> dict:
    return json.loads((I18N / f"{idioma}.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("idioma", OUTROS)
def test_mesmas_chaves_que_a_referencia(idioma):
    ref, outro = _dic(REFERENCIA), _dic(idioma)
    faltam = sorted(set(ref) - set(outro))
    sobram = sorted(set(outro) - set(ref))
    assert faltam == [], f"{idioma}.json sem as chaves: {faltam}"
    assert sobram == [], f"{idioma}.json com chaves que não existem em pt-BR: {sobram}"


@pytest.mark.parametrize("idioma", OUTROS)
def test_mesmas_variaveis_por_chave(idioma):
    ref, outro = _dic(REFERENCIA), _dic(idioma)
    ruins = {k: (sorted(set(RE_VAR.findall(ref[k]))), sorted(set(RE_VAR.findall(outro[k]))))
             for k in ref if k in outro and set(RE_VAR.findall(ref[k])) != set(RE_VAR.findall(outro[k]))}
    assert ruins == {}, f"variáveis divergentes em {idioma}.json: {ruins}"


@pytest.mark.parametrize("idioma", (REFERENCIA, *OUTROS))
def test_sem_valor_vazio_nem_igual_a_chave(idioma):
    d = _dic(idioma)
    vazios = [k for k, v in d.items() if not isinstance(v, str) or not v.strip()]
    cruas = [k for k, v in d.items() if v == k]
    assert vazios == [] and cruas == [], (vazios, cruas)


def test_idiomas_do_servidor_existem_como_arquivo():
    import app.limites as limites

    for idioma in set(limites.PERFIL_IDIOMAS) | set(limites.ORG_IDIOMAS):
        assert (I18N / f"{idioma}.json").is_file(), f"app.limites cita {idioma} sem web/js/i18n/{idioma}.json"
