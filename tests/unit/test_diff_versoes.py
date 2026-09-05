"""JSON Patch entre versões (ADR 0004 seção 4.2): 6 casos add/replace/remove em objeto e lista; aplicar o patch
sobre o antes devolve o depois (ida e volta)."""

import pytest

from app.catalogo import diff

CASOS = [
    ({"a": 1}, {"a": 2}, [{"op": "replace", "path": "/a", "value": 2}]),
    ({"a": 1}, {"a": 1, "b": 3}, [{"op": "add", "path": "/b", "value": 3}]),
    ({"a": 1, "b": 3}, {"a": 1}, [{"op": "remove", "path": "/b"}]),
    ({"l": [1, 2]}, {"l": [1, 2, 3]}, [{"op": "add", "path": "/l/2", "value": 3}]),
    (
        {"l": [1, 2, 3]},
        {"l": [1, 9]},
        [{"op": "replace", "path": "/l/1", "value": 9}, {"op": "remove", "path": "/l/2"}],
    ),
    ({"o": {"x": {"y": 1}}}, {"o": {"x": {"y": 1, "z": [1]}}}, [{"op": "add", "path": "/o/x/z", "value": [1]}]),
]


@pytest.mark.parametrize("antes,depois,esperado", CASOS)
def test_patch_e_ida_e_volta(antes, depois, esperado):
    p = diff.patch(antes, depois)
    assert p == esperado
    assert diff.aplicar(antes, p) == depois


def test_igual_e_vazio_e_chave_escapada():
    assert diff.patch({"a": [1, {"b": 2}]}, {"a": [1, {"b": 2}]}) == []
    p = diff.patch({"a/b": 1}, {"a/b": 2})
    assert p == [{"op": "replace", "path": "/a~1b", "value": 2}]
    assert diff.aplicar({"a/b": 1}, p) == {"a/b": 2}


def test_tipo_diferente_e_substituicao():
    assert diff.patch({"a": 1}, {"a": "1"}) == [{"op": "replace", "path": "/a", "value": "1"}]
    assert diff.patch(1, {"a": 1}) == [{"op": "replace", "path": "", "value": {"a": 1}}]
