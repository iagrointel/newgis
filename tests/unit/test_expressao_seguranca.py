"""Refutação do item-pai (L2-10-relacoes-regras) contra a linguagem de expressão: "adversário
escreve expressão maliciosa: laço infinito, recursão profunda (10^6), texto de 10 MB, acesso a
tabela de outro inquilino, e mede se o limite de tempo vale sob carga". Nesta passagem (núcleo,
sem integração com camada/formulário) o equivalente de "tabela de outro inquilino" é campo fora
da lista branca do `contexto` — não há acesso a outra camada ainda para tentar. Todo ataque tem de
terminar RÁPIDO com `ErroExpressao` nomeada; nunca com `RecursionError`, nunca com o processo
travado, nunca devolvendo silenciosamente `None`."""

import time

import pytest

from app.expressao.avaliador_py import (
    MAX_PROFUNDIDADE,
    MAX_TEXTO,
    MAX_TOKENS,
    ErroExpressao,
    analisar,
    ast_de_json,
    avaliar,
    avaliar_texto,
)

TETO_ATAQUE_MS = 500  # nenhum ataque nesta suíte pode custar mais que isso — é o próprio limite
# de tempo do servidor (LIMITE_MS_SERVIDOR); um ataque que custasse mais já seria, por si, a prova
# de que o limite não vale sob carga


# --------------------------------------------------------------------- 1. campo fora da lista branca
def test_campo_fora_da_lista_branca_nunca_devolve_valor():
    """o equivalente, nesta passagem, de 'acessar tabela de outro inquilino': `contexto` é a lista
    BRANCA do chamador — nada além dela é alcançável, nem por nome parecido, nem por maiúscula/
    minúscula, nem tentando dunder do Python (não há `getattr`, então nada disso teria efeito de
    qualquer forma; o teste prova que o CAMINHO comum — `$campo` — sempre nega)."""
    contexto = {"area_ha": 450.5, "municipio": "Guarulhos"}
    for tentativa in ["area_HA", "__class__", "__init__", "outro_inquilino_id", "password", "AREA_HA", ""]:
        with pytest.raises(ErroExpressao) as exc:
            avaliar_texto(f"${tentativa}" if tentativa else "$", contexto)
        assert exc.value.codigo in ("campo_nao_permitido", "sintaxe_invalida")


def test_contexto_nunca_e_alcancado_por_caminho_indireto():
    """não existe função de indexação/reflexão na tabela (`TABELA_FUNCOES`) capaz de enumerar ou
    ler o contexto por outro nome que não `$campo` — o avaliador nunca expõe `contexto` como valor."""
    from app.expressao.avaliador_py import TABELA_FUNCOES

    nomes_perigosos = {"Eval", "Exec", "Getattr", "Contexto", "Campos", "Vars", "Globals", "Import"}
    assert nomes_perigosos.isdisjoint(TABELA_FUNCOES)


# --------------------------------------------------------------------- 2. profundidade / recursão
def test_cadeia_longa_do_mesmo_operador_nao_estoura_a_pilha():
    """900 termos encadeados (~1.800 tokens, sob o teto de tokens) — só a MEDIÇÃO DA ÁRVORE pega
    isto; o parser não recursa por termo (é um `while`), então esta é a prova específica do
    segundo guarda-corpo (`_profundidade_da_arvore`), não do primeiro."""
    texto = "1" + "+1" * 900
    assert len(texto) < MAX_TEXTO
    t0 = time.perf_counter()
    with pytest.raises(ErroExpressao):
        analisar(texto)
    ms = (time.perf_counter() - t0) * 1000.0
    assert ms < TETO_ATAQUE_MS


def test_cadeia_longa_levanta_profundidade_excedida_com_erro_nomeado():
    texto = "1" + "+1" * 900
    with pytest.raises(ErroExpressao) as exc:
        analisar(texto)
    assert exc.value.codigo == "profundidade_excedida"
    assert exc.value.detalhe["medido"] > MAX_PROFUNDIDADE


def test_parenteses_profundamente_aninhados_nao_estouram_a_pilha_do_parser():
    """aqui quem pega é o PRIMEIRO guarda-corpo: o parser conta a descida a cada '(' antes de
    recursar — nunca deixa a pilha do Python chegar perto do limite."""
    texto = "(" * 500 + "1" + ")" * 500
    t0 = time.perf_counter()
    with pytest.raises(ErroExpressao) as exc:
        analisar(texto)
    ms = (time.perf_counter() - t0) * 1000.0
    assert exc.value.codigo == "profundidade_excedida"
    assert ms < TETO_ATAQUE_MS


def test_unarios_profundamente_encadeados_nao_estouram_a_pilha():
    texto = "!" * 500 + "Verdadeiro"
    with pytest.raises(ErroExpressao) as exc:
        analisar(texto)
    assert exc.value.codigo == "profundidade_excedida"


def test_chamadas_de_funcao_profundamente_aninhadas_nao_estouram_a_pilha():
    texto = "Absoluto(" * 500 + "1" + ")" * 500
    with pytest.raises(ErroExpressao) as exc:
        analisar(texto)
    assert exc.value.codigo == "profundidade_excedida"


def test_expressao_no_limite_da_profundidade_permitida_ainda_funciona():
    """o guarda-corpo não pode ser tão apertado que quebre uso legítimo — uma expressão bem dentro
    do limite continua avaliando normalmente."""
    n = 20
    texto = "1" + "+1" * n
    assert avaliar_texto(texto, {}) == 1 + n


# --------------------------------------------------------------------- 3. texto/tokens gigantes
def test_string_de_10_mb_e_rejeitada_pelo_tamanho_do_texto_antes_de_tokenizar():
    texto = "'" + ("a" * 10_000_000) + "'"
    t0 = time.perf_counter()
    with pytest.raises(ErroExpressao) as exc:
        analisar(texto)
    ms = (time.perf_counter() - t0) * 1000.0
    assert exc.value.codigo == "expressao_grande"
    assert ms < TETO_ATAQUE_MS, f"string gigante custou {ms:.1f} ms — devia ser rejeitada antes de tokenizar"


def test_muitos_tokens_sem_ultrapassar_caracteres_e_rejeitado():
    texto = "+".join(["1"] * (MAX_TOKENS + 100))
    with pytest.raises(ErroExpressao) as exc:
        analisar(texto)
    assert exc.value.codigo == "expressao_grande"


def test_muitos_argumentos_em_uma_chamada_variadica_e_rejeitado():
    texto = "Concatenar(" + ",".join(["'a'"] * 1000) + ")"
    with pytest.raises(ErroExpressao) as exc:
        analisar(texto)
    assert exc.value.codigo == "expressao_grande"


# --------------------------------------------------------------------- 4. limite de passos sob carga
def test_limite_de_passos_corta_avaliacao_larga_mesmo_sem_ser_funda():
    """largura em vez de profundidade: uma soma de 50 termos (dentro do limite de árvore, que é 60)
    com um orçamento de passos artificialmente baixo tem de cortar, mesmo sem chegar perto do
    limite de tempo — prova que o contador de passos é independente do relógio."""
    n = 50
    texto = "1" + "+1" * n
    no = analisar(texto)
    with pytest.raises(ErroExpressao) as exc:
        avaliar(no, {}, limite_passos=10)
    assert exc.value.codigo == "limite_passos"


def _arvore_soma_balanceada(folhas):
    """monta, em JSON de AST (não passa pelo texto — `ast_de_json`), uma árvore BALANCEADA de somas
    com `folhas` literais nas pontas: profundidade log2(folhas), bem abaixo de MAX_PROFUNDIDADE,
    mas com `2*folhas - 1` nós — é como se chega a centenas de nós sem violar o limite de árvore,
    o que uma cadeia linear (`1+1+1+...`) não conseguiria fazer sem estourar a profundidade."""
    nos = [{"tipo": "literal", "tipo_valor": "numero", "valor": 1} for _ in range(folhas)]
    while len(nos) > 1:
        pares = list(zip(nos[0::2], nos[1::2], strict=False))
        nova_camada = [{"tipo": "binario", "operador": "+", "esquerda": a, "direita": b} for a, b in pares]
        if len(nos) % 2 == 1:
            nova_camada.append(nos[-1])
        nos = nova_camada
    return nos[0]


def test_limite_de_tempo_vale_sob_carga_com_orcamento_de_passos_alto():
    """o inverso do teste anterior: orçamento de PASSOS generoso, orçamento de TEMPO
    artificialmente baixo — o relógio tem de cortar sozinho. Usa uma árvore BALANCEADA (256 folhas,
    511 nós, profundidade 8) em vez de uma cadeia linear: o contador de tempo só é conferido a cada
    256 passos (relógio não é grátis), então uma expressão com poucas dezenas de nós nunca ativa a
    amostragem — não é um "furo", é que ela termina rápido demais para o relógio importar."""
    d = _arvore_soma_balanceada(256)
    no = ast_de_json(d)
    with pytest.raises(ErroExpressao) as exc:
        avaliar(no, {}, limite_passos=10_000_000, limite_ms=0.0)
    assert exc.value.codigo == "tempo_excedido"


def test_expressao_legitima_dentro_do_orcamento_padrao_nao_e_afetada():
    n = 40
    texto = "1" + "+1" * n
    assert avaliar_texto(texto, {}) == 1 + n


# --------------------------------------------------------------------- 5. sem eval/exec no processo
def test_nenhum_eval_exec_compile_no_modulo():
    import ast
    import inspect

    import app.expressao.avaliador_py as modulo

    codigo_fonte = inspect.getsource(modulo)
    arvore = ast.parse(codigo_fonte)
    proibidos = {"eval", "exec", "compile", "__import__"}
    achados = []
    for no in ast.walk(arvore):
        # só `ast.Name` (chamada direta ao builtin: `compile(...)`) — `re.compile(...)` é
        # `ast.Attribute` sobre o módulo `re` (compila EXPRESSÃO REGULAR, não código Python) e não
        # pode dar falso positivo aqui
        if isinstance(no, ast.Name) and no.id in proibidos:
            achados.append(no.id)
    assert achados == [], f"chamada proibida encontrada no código-fonte: {achados}"


def test_nenhum_getattr_dinamico_sobre_valor_do_contexto():
    """o avaliador só lê `contexto[nome]` (dict), nunca `getattr(objeto, nome)` — confirmado lendo
    o código-fonte: `getattr` não aparece no módulo inteiro."""
    import inspect

    import app.expressao.avaliador_py as modulo

    assert "getattr(" not in inspect.getsource(modulo)
