"""Varredura de sombreamento de rota (item L0-04-k): o roteador do Starlette casa a requisição na ORDEM em que
as rotas foram declaradas, e um segmento `{param}` casa qualquer segmento. Logo, uma rota de segmento fixo
declarada DEPOIS de uma parametrizada que a cobre é inalcançável — nunca responde, e o cliente recebe a
resposta da outra (foi o caso de `GET /api/importacoes/formatos`, engolida por `GET /api/importacoes/{id}`,
que respondia 404 importacao_inexistente).

O teste percorre a aplicação viva inteira, não só a ingestão: qualquer par novo com essa inversão reprova aqui,
nomeando as duas rotas e o método."""

from __future__ import annotations

import re

from starlette.routing import compile_path

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


def _neutralizar(caminho: str) -> str:
    """Troca cada `{param}` do caminho ENGOLIDO por um literal sem barra, para que ele possa ser testado como
    se fosse uma requisição concreta contra o regex da outra rota. O sentinela não tem barra nem chaves, então
    um `{x:path}` do lado engolido nunca ganha poder de casar vários segmentos por acidente."""
    return "/".join("sentinela" if PARAMETRO.match(seg) else seg for seg in caminho.split("/"))


def _so_troca_parametro_por_parametro(a: str, fixa: str) -> bool:
    """As duas rotas têm a mesma forma e, onde diferem, os dois lados são parâmetro? Então nenhum literal está
    sendo engolido: é o caso de `/api/itens/{id}` x `/api/itens/{slug}`, que é outro assunto (nome de
    parâmetro repetido) e nunca foi o que esta varredura acusa."""
    sa, sb = a.split("/"), fixa.split("/")
    if len(sa) != len(sb):
        return False
    return all(x == y or (PARAMETRO.match(x) and PARAMETRO.match(y)) for x, y in zip(sa, sb, strict=True))


def _cobre(parametrizada: str, fixa: str) -> bool:
    """A rota `parametrizada` casa toda requisição que a rota `fixa` casaria?

    Quem responde é o regex que o PRÓPRIO Starlette compila do molde (`compile_path`), não uma reimplementação
    segmento a segmento. Foi a reimplementação que deixou passar a classe de bug do item: ela comparava só
    caminhos com o mesmo número de segmentos, e o convertor `path` compila para `.*`, que casa qualquer número
    de segmentos, barra inclusive (`/api/x/{a:path}/fim` engole `/api/x/{b}/{c}/fim`). Usando o regex de
    verdade, os convertores `int`, `float`, `uuid` e `path` passam a valer de graça e exatamente como na
    aplicação viva."""
    if parametrizada == fixa or _so_troca_parametro_por_parametro(parametrizada, fixa):
        return False
    regex, _, _ = compile_path(parametrizada)
    return regex.fullmatch(_neutralizar(fixa)) is not None


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


def test_a_varredura_enxerga_o_convertor_path_multisegmento():
    """Refutação do adversário de linha L0 (rodada 2, item L0-04-k): o convertor `path` do Starlette compila
    para `.*`, que casa qualquer número de segmentos, barra inclusive. A varredura antiga comparava só
    caminhos com o MESMO número de segmentos e por isso era cega para esta classe de sombreamento — a mesma
    que motivou o item, agora com `{x:path}` no lugar de `{id}`."""
    assert _cobre("/api/x/{a:path}/fim", "/api/x/{b}/{c}/fim")
    assert _cobre("/api/x/{a:path}", "/api/x/y/z/w")
    assert not _cobre("/api/x/{b}/{c}/fim", "/api/x/{a:path}/fim")
    assert not _cobre("/api/y/{a:path}", "/api/x/y/z")


def test_os_convertores_do_starlette_valem_sem_tabela_propria():
    """`int`, `float` e `uuid` deixam de precisar da tabela paralela que a varredura mantinha: quem recusa o
    literal é o regex que o próprio roteador usa."""
    assert not _cobre("/api/camadas/{camada:int}/x", "/api/camadas/replicas/x")
    assert _cobre("/api/camadas/{camada:int}/x", "/api/camadas/12/x")
    assert not _cobre("/api/itens/{id:uuid}", "/api/itens/formatos")
    assert _cobre("/api/itens/{id:uuid}", "/api/itens/0b3c2a1e-0000-4000-8000-000000000000")


def test_rota_de_licencas_de_imagem_nao_esta_encoberta():
    """Cláusula do portão sobre a aplicação viva: `GET /api/imagens/licencas` (segmento fixo) tem de ser
    declarada antes de `GET /api/imagens/{item_id}`. Estava depois em master e respondia o painel do item."""
    ordem = {c: p for p, c, _ in _rotas_declaradas()}
    assert ordem["/api/imagens/licencas"] < ordem["/api/imagens/{item_id}"]


def test_rotas_com_convertor_path_nao_engolem_nenhuma_rota_fixa_da_app():
    """As 5 rotas `{x:path}` que hoje existem na aplicação passam a ser cobertas pela garantia da varredura,
    não pelo cuidado manual na ordem de `include_router`."""
    com_path = [c for _, c, _ in _rotas_declaradas() if ":path}" in c]
    assert len(com_path) >= 4, f"esperava rotas com convertor path na app; achei {com_path}"
    assert [p for p in pares_encobertos() if ":path}" in p[1]] == []
