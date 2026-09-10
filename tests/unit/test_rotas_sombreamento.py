"""Varredura de sombreamento de rota (item L0-04-k): o roteador do Starlette casa a requisição na ORDEM em que
as rotas foram declaradas, e um segmento `{param}` casa qualquer segmento. Logo, uma rota de segmento fixo
declarada DEPOIS de uma parametrizada que a cobre é inalcançável — nunca responde, e o cliente recebe a
resposta da outra (foi o caso de `GET /api/importacoes/formatos`, engolida por `GET /api/importacoes/{id}`,
que respondia 404 importacao_inexistente).

O teste percorre a aplicação viva inteira, não só a ingestão: qualquer par novo com essa inversão reprova aqui,
nomeando as duas rotas e o método."""

from __future__ import annotations

import re

from app.main import app

PARAMETRO = re.compile(r"^\{[^}]+\}$")


def achatar_rotas(rotas):
    """Do FastAPI 0.138 em diante, `app.routes` guarda um nó por router incluído (`_IncludedRouter`), não as
    rotas em si: um `getattr(r, "path")` cru enxerga 3 rotas onde há 236. Cada nó sabe expandir os seus
    candidatos NA ORDEM em que o roteador os testa (`effective_candidates`), e é essa ordem que decide quem
    responde. As rotas de baixa prioridade (arquivos estáticos do frontend) ficam de fora de propósito: não
    são rotas de API e só entram depois que nenhuma outra casa."""
    for r in rotas:
        expandir = getattr(r, "effective_candidates", None)
        if callable(expandir):
            yield from achatar_rotas(expandir())
            continue
        caminho, metodos = getattr(r, "path", None), getattr(r, "methods", None)
        if caminho and metodos:
            yield caminho, frozenset(m.upper() for m in metodos)


def _rotas_declaradas() -> list[tuple[int, str, frozenset[str]]]:
    """(posição de declaração, caminho, métodos) de cada rota da aplicação, na ordem em que o roteador as testa."""
    return [(pos, caminho, metodos) for pos, (caminho, metodos) in enumerate(achatar_rotas(app.routes))]


def _cobre(parametrizada: str, fixa: str) -> bool:
    """A rota `parametrizada` casa toda requisição que a rota `fixa` casaria? É verdade quando as duas têm o
    mesmo número de segmentos e, em cada posição, ou os segmentos são iguais, ou a parametrizada tem `{param}`
    ali (que casa qualquer segmento sem barra) e a fixa tem um segmento literal."""
    a, b = parametrizada.split("/"), fixa.split("/")
    if len(a) != len(b):
        return False
    tem_parametro_no_lugar_de_literal = False
    for seg_a, seg_b in zip(a, b, strict=True):
        if seg_a == seg_b:
            continue
        if PARAMETRO.match(seg_a) and not PARAMETRO.match(seg_b):
            tem_parametro_no_lugar_de_literal = True
            continue
        return False
    return tem_parametro_no_lugar_de_literal


def pares_encobertos() -> list[tuple[str, str, str]]:
    """(método, rota parametrizada declarada antes, rota fixa inalcançável)."""
    rotas = _rotas_declaradas()
    achados = []
    for pos_antes, caminho_antes, metodos_antes in rotas:
        for pos_depois, caminho_depois, metodos_depois in rotas:
            if pos_depois <= pos_antes:
                continue
            comuns = metodos_antes & metodos_depois
            if not comuns:
                continue
            if _cobre(caminho_antes, caminho_depois):
                for metodo in sorted(comuns):
                    achados.append((metodo, caminho_antes, caminho_depois))
    return achados


def test_varredura_nao_acha_rota_fixa_encoberta_em_toda_a_app():
    rotas = _rotas_declaradas()
    assert len(rotas) > 100, f"app.routes com {len(rotas)} rotas — a varredura não provaria nada"
    achados = pares_encobertos()
    assert achados == [], "rota de segmento fixo declarada depois de uma parametrizada que a cobre " + str(
        [f"{m} {fixa} é engolida por {param} (declarada antes)" for m, param, fixa in achados]
    )


def test_formatos_declarada_antes_da_rota_com_id():
    """A cláusula do item, olhada na ordem de declaração: sem isso, `/api/importacoes/formatos` volta a ser 404."""
    ordem = {c: p for p, c, _ in _rotas_declaradas()}
    assert ordem["/api/importacoes/formatos"] < ordem["/api/importacoes/{id}"]


def test_a_varredura_acusa_quando_a_ordem_e_invertida():
    """Refutação exigida: invertida a ordem, a varredura nomeia as duas rotas. Aqui a inversão é simulada sobre a
    mesma função de cobertura, sem mexer na aplicação viva (que os outros testes deste arquivo protegem)."""
    assert _cobre("/api/importacoes/{id}", "/api/importacoes/formatos")
    assert not _cobre("/api/importacoes/formatos", "/api/importacoes/{id}")
    assert not _cobre("/api/importacoes/{id}", "/api/importacoes/{id}/confirmar")
    assert not _cobre("/api/itens/{id}", "/api/camadas/formatos")
