"""Motor do diagrama de rede sem banco (item L4-04-d-diagrama-esquematico): regras de construção, layouts e
exportação sobre grafos montados à mão.

O que estas provas cobrem do portão:
  * `reduzir_juncao_de_passagem` REDUZ o número de nós e NÃO muda a conectividade (nº de componentes igual
    antes e depois) — `test_reduzir_juncao_reduz_e_preserva_conectividade`;
  * a mesma regra NÃO apaga a aresta de um laço — `test_reduzir_nao_apaga_a_aresta_do_laco`;
  * os seis layouts terminam com ZERO par de nós a menos de 1 unidade — `test_layouts_sem_sobreposicao`;
  * nenhum layout cria ou apaga nó ou aresta, e o laço continua no desenho de árvore (é a refutação
    declarada do item) — `test_layout_nao_perde_no_nem_aresta` e `test_arvore_mantem_a_aresta_do_laco`.

Grafos de banco (recorte, gravação, consistência, seleção) ficam em `tests/api/test_rede_diagrama.py`: aqui
não se toca em Postgres de propósito, porque regra e layout são aritmética e têm de poder ser conferidas em
milissegundos."""

import pytest

from app.erros import ErroAPI
from app.rede_utilidades import diagrama


def _no(chave, papel="conexao", tipo=None, feicao=None, terminal=None, lon=None, lat=None):
    return {"chave": chave, "papel": papel, "feicao_id": feicao, "terminal_num": terminal,
            "tipo_id": None, "tipo_chave": tipo, "tipo_nome": tipo, "rotulo": chave, "agregados": 1,
            "lon": lon, "lat": lat, "x": 0.0, "y": 0.0}


def _aresta(chave, de, para, origem="topologia", comprimento=10.0):
    return {"chave": chave, "de": de, "para": para, "origem": origem, "feicoes": [chave],
            "tipo_id": None, "tipo_chave": "trecho", "agregadas": 1, "comprimento_m": comprimento}


def _cadeia(n: int, prefixo: str = "c") -> dict:
    """Cadeia de `n` nós de conexão em fila: todos os do meio são junção de passagem (grau 2)."""
    nos = {f"{prefixo}{i}": _no(f"{prefixo}{i}", lon=-46.6 + i * 0.001, lat=-23.5) for i in range(n)}
    arestas = [_aresta(f"a{i}", f"{prefixo}{i}", f"{prefixo}{i + 1}") for i in range(n - 1)]
    return {"nos": nos, "arestas": arestas}


def _anel(n: int) -> dict:
    """Anel fechado de `n` nós de conexão: todo nó tem grau 2, e o grafo tem um laço que o desenho precisa
    mostrar. É o grafo da refutação do item."""
    g = _cadeia(n)
    g["arestas"].append(_aresta("fecha", f"c{n - 1}", "c0"))
    return g


def _alimentador(ramos: int = 8, por_ramo: int = 12) -> dict:
    """Tronco com ramais: um nó de dispositivo na cabeça, tronco de junções de passagem e um ramal a cada
    dois nós do tronco. Fica com nós e arestas suficientes para que sobreposição de layout apareça."""
    g = _cadeia(ramos * 2, "t")
    g["nos"]["cabeca"] = _no("cabeca", papel="terminal", tipo="disjuntor", feicao="f-cabeca", terminal=1,
                             lon=-46.6, lat=-23.5)
    g["arestas"].append(_aresta("cabeca-t0", "cabeca", "t0"))
    for r in range(ramos):
        anterior = f"t{r * 2}"
        for i in range(por_ramo):
            chave = f"r{r}_{i}"
            g["nos"][chave] = _no(chave, lon=-46.6 + r * 0.002, lat=-23.5 - i * 0.001)
            g["arestas"].append(_aresta(f"ar{r}_{i}", anterior, chave))
            anterior = chave
        ponta = f"p{r}"
        g["nos"][ponta] = _no(ponta, papel="terminal", tipo="transformador_de_distribuicao",
                              feicao=f"f-tr{r}", terminal=1, lon=-46.6 + r * 0.002, lat=-23.52)
        g["arestas"].append(_aresta(f"ap{r}", anterior, ponta))
    return g


# --- regras ------------------------------------------------------------------------------------------

def test_reduzir_juncao_reduz_e_preserva_conectividade():
    """Cláusula do portão: a regra reduz o número de nós (medido) sem mudar a conectividade."""
    g = _cadeia(30)
    antes_componentes = diagrama.componentes(g)
    relatorio = diagrama.aplicar_regras(g, [{"regra": "reduzir_juncao_de_passagem"}])
    assert antes_componentes == 1
    assert relatorio[0]["nos_removidos"] == 28, relatorio
    assert len(g["nos"]) == 2, "só as duas pontas sobram: o resto era passagem"
    assert diagrama.componentes(g) == antes_componentes
    assert len(g["arestas"]) == 1
    assert g["arestas"][0]["agregadas"] == 29, "a aresta única guarda quantas ela representa"
    assert g["arestas"][0]["comprimento_m"] == pytest.approx(290.0), "o comprimento é somado, não perdido"
    assert len(g["arestas"][0]["feicoes"]) == 29, "e guarda as feições que representa"


def test_reduzir_juncao_num_alimentador_reduz_muito_e_nao_parte_a_rede():
    g = _alimentador()
    antes = (len(g["nos"]), diagrama.componentes(g))
    diagrama.aplicar_regras(g, [{"regra": "reduzir_juncao_de_passagem"}])
    assert len(g["nos"]) < antes[0]
    assert diagrama.componentes(g) == antes[1] == 1


def test_reduzir_nao_apaga_a_aresta_do_laco():
    """Refutação declarada do item: num anel, reduzir junção de passagem não pode fazer o laço sumir. O anel
    de 12 nós encolhe, mas continua sendo um anel — arestas >= nós, e um componente só."""
    g = _anel(12)
    diagrama.aplicar_regras(g, [{"regra": "reduzir_juncao_de_passagem"}])
    assert diagrama.componentes(g) == 1
    assert len(g["arestas"]) >= len(g["nos"]), (len(g["arestas"]), len(g["nos"]))
    assert len(g["nos"]) >= 2, "o último par de nós fica: reduzi-lo apagaria a aresta do laço"


def test_colapsar_conteiner_funde_os_terminais_do_mesmo_dispositivo():
    g = {"nos": {}, "arestas": []}
    g["nos"]["a"] = _no("a")
    g["nos"]["b"] = _no("b")
    for t in (1, 2):
        chave = f"terminal:f-tr:{t}"
        g["nos"][chave] = _no(chave, papel="terminal", tipo="transformador_de_distribuicao",
                              feicao="f-tr", terminal=t)
    g["arestas"] += [
        _aresta("e1", "a", "terminal:f-tr:1"),
        _aresta("interna", "terminal:f-tr:1", "terminal:f-tr:2", origem="dispositivo", comprimento=0.0),
        _aresta("e2", "terminal:f-tr:2", "b"),
    ]
    relatorio = diagrama.aplicar_regras(g, [{"regra": "colapsar_conteiner"}])
    assert relatorio[0]["conteineres"] == 1
    assert "conteiner:f-tr" in g["nos"]
    assert g["nos"]["conteiner:f-tr"]["agregados"] == 2
    assert not any(c.startswith("terminal:f-tr") for c in g["nos"])
    assert [a["chave"] for a in g["arestas"]] == ["e1", "e2"], "a ligação interna virou o próprio nó"
    assert diagrama.componentes(g) == 1


def test_remover_tipos_tira_os_nos_daquele_tipo():
    g = _alimentador(ramos=2, por_ramo=2)
    antes = len(g["nos"])
    relatorio = diagrama.aplicar_regras(
        g, [{"regra": "remover_tipos", "tipos": ["transformador_de_distribuicao"]}])
    assert relatorio[0]["nos_removidos"] == 2
    assert len(g["nos"]) == antes - 2
    assert not any(n["tipo_chave"] == "transformador_de_distribuicao" for n in g["nos"].values())


def test_regra_desconhecida_e_recusada():
    with pytest.raises(ErroAPI) as e:
        diagrama.aplicar_regras(_cadeia(3), [{"regra": "inventada"}])
    assert e.value.erro == "regra_desconhecida"


def test_ordem_das_regras_importa_e_e_respeitada():
    """Colapsar antes de reduzir deixa o dispositivo como UM nó de grau 2, que a redução seguinte não toca
    (ele tem feição própria e não está em `tipos`). É a leitura da fonte: uma regra vê o resultado da
    anterior."""
    g = _cadeia(5)
    for t in (1, 2):
        chave = f"terminal:f-ch:{t}"
        g["nos"][chave] = _no(chave, papel="terminal", tipo="chave", feicao="f-ch", terminal=t)
    g["arestas"] += [_aresta("x1", "c4", "terminal:f-ch:1"),
                     _aresta("x2", "terminal:f-ch:2", "c0")]
    diagrama.aplicar_regras(g, [{"regra": "colapsar_conteiner"}, {"regra": "reduzir_juncao_de_passagem"}])
    assert "conteiner:f-ch" in g["nos"], "o dispositivo continua no desenho depois da redução"


# --- layouts -----------------------------------------------------------------------------------------

@pytest.mark.parametrize("layout", diagrama.LAYOUTS)
def test_layouts_sem_sobreposicao(layout):
    """Cláusula do portão: resultado sem sobreposição de nós — 0 pares a menos de 1 unidade."""
    g = _alimentador()
    medida = diagrama.aplicar_layout(g, layout)
    assert medida["layout"] == layout
    assert diagrama.pares_sobrepostos(g) == 0, layout
    menor = diagrama.menor_distancia(g)
    assert menor is None or menor >= diagrama.SEPARACAO_MINIMA, (layout, menor)
    assert diagrama._menor_arredondada(g) == (round(menor, 6) if menor is not None else None)


@pytest.mark.parametrize("layout", diagrama.LAYOUTS)
def test_layout_nao_perde_no_nem_aresta(layout):
    g = _alimentador(ramos=4, por_ramo=5)
    antes = (len(g["nos"]), len(g["arestas"]))
    diagrama.aplicar_layout(g, layout)
    assert (len(g["nos"]), len(g["arestas"])) == antes


@pytest.mark.parametrize("layout", diagrama.LAYOUTS)
def test_arvore_mantem_a_aresta_do_laco(layout):
    """Refutação declarada: o layout de árvore (e qualquer outro) desenha o anel sem perder a aresta que o
    fecha. A árvore geradora só guia a POSIÇÃO; a aresta que sobra continua no grafo."""
    g = _anel(10)
    chaves_antes = {a["chave"] for a in g["arestas"]}
    diagrama.aplicar_layout(g, layout)
    assert {a["chave"] for a in g["arestas"]} == chaves_antes
    assert "fecha" in chaves_antes


def test_layout_desconhecido_e_recusado():
    with pytest.raises(ErroAPI) as e:
        diagrama.aplicar_layout(_cadeia(3), "espiral")
    assert e.value.erro == "layout_desconhecido"


def test_forca_dirigida_e_deterministica():
    """A semente vem do sha256 da chave do nó: o mesmo grafo dá sempre o mesmo desenho, senão duas leituras
    do mesmo diagrama mostrariam figuras diferentes."""
    posicoes = []
    for _ in range(2):
        g = _alimentador(ramos=3, por_ramo=4)
        diagrama.aplicar_layout(g, "forca_dirigida")
        posicoes.append({c: (round(n["x"], 9), round(n["y"], 9)) for c, n in g["nos"].items()})
    assert posicoes[0] == posicoes[1]


def test_forca_dirigida_grande_cai_na_grade_com_aviso():
    g = _cadeia(diagrama.FORCA_DIRIGIDA_NOS_MAXIMO + 5)
    medida = diagrama.aplicar_layout(g, "forca_dirigida")
    assert medida["layout_efetivo"] == "grade"
    assert medida["aviso"] and str(diagrama.FORCA_DIRIGIDA_NOS_MAXIMO) in medida["aviso"]
    assert diagrama.pares_sobrepostos(g) == 0


def test_geografico_sem_coordenada_cai_na_grade():
    g = _cadeia(6)
    for n in g["nos"].values():
        n["lon"] = n["lat"] = None
    diagrama.aplicar_layout(g, "geografico")
    assert diagrama.pares_sobrepostos(g) == 0


# --- exportação --------------------------------------------------------------------------------------

def _documento(g: dict, nome: str = "diagrama de teste") -> dict:
    nos = [{"chave": c, "papel": n["papel"], "rotulo": n["rotulo"], "x": n["x"], "y": n["y"]}
           for c, n in sorted(g["nos"].items())]
    arestas = [{"chave": a["chave"], "origem": a["origem"],
                "x1": g["nos"][a["de"]]["x"], "y1": g["nos"][a["de"]]["y"],
                "x2": g["nos"][a["para"]]["x"], "y2": g["nos"][a["para"]]["y"]} for a in g["arestas"]]
    return {"nome": nome, "nos": nos, "arestas": arestas}


def test_svg_tem_uma_linha_por_aresta_e_um_circulo_por_no():
    g = _alimentador(ramos=2, por_ramo=3)
    diagrama.aplicar_layout(g, "arvore_inteligente")
    svg = diagrama.para_svg(_documento(g))
    assert svg.startswith("<svg ") and svg.rstrip().endswith("</svg>")
    assert svg.count("<line ") == len(g["arestas"])
    assert svg.count("<circle ") == len(g["nos"])


def test_svg_escapa_o_rotulo_que_veio_do_arquivo():
    """O rótulo é atributo do arquivo do usuário. Sem escape, um `cod_id` com marcação fecharia o elemento e
    o arquivo exportado viraria injeção de marcação."""
    g = _cadeia(2)
    g["nos"]["c0"]["papel"] = "terminal"
    g["nos"]["c0"]["rotulo"] = '<script>alerta()</script>'
    diagrama.aplicar_layout(g, "grade")
    svg = diagrama.para_svg(_documento(g, nome='rede "a" & <b>'))
    assert "<script>" not in svg
    assert "&lt;script&gt;" in svg
    assert "&amp;" in svg and "&lt;b&gt;" in svg


def test_png_sai_com_a_assinatura_de_png():
    g = _alimentador(ramos=2, por_ramo=3)
    diagrama.aplicar_layout(g, "linha_principal")
    dados = diagrama.para_png(_documento(g))
    assert dados[:8] == b"\x89PNG\r\n\x1a\n"
    assert len(dados) > 100
