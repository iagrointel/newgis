"""Importação e exportação do conjunto de regras em CSV, nas colunas da Esri (item
L4-03-a-regras-de-conectividade).

As 13 colunas são as das ferramentas Import Rules / Export Rules do ArcGIS Pro 3.4 (fontes do item):
RULETYPE, FROMFEATURECLASS, FROMASSETGROUP, FROMASSETTYPE, FROMTERMINAL, TOFEATURECLASS, TOASSETGROUP,
TOASSETTYPE, TOTERMINAL, VIAFEATURECLASS, VIAASSETGROUP, VIAASSETTYPE, VIATERMINAL.

Mapeamento para o nosso vocabulário (documentado no ADR e na paridade do item):
- FEATURECLASS e ASSETGROUP carregam o MESMO valor: o código do nosso grupo de ativo (na utility network a
  classe de feição contém grupos de ativo; aqui o grupo é as duas coisas). Na importação, ASSETGROUP
  divergente de FEATURECLASS é recusado com a linha apontada.
- ASSETTYPE é o CÓDIGO inteiro do tipo de ativo na exportação; na importação aceita o código ou a chave.
- RULETYPE usa os rótulos da Esri ("Junction Edge Connectivity" etc.).
- A importação SUBSTITUI o conjunto inteiro de regras da rede numa transação (a ferramenta da Esri
  ACRESCENTA; a diferença está na paridade). Exportar e reimportar devolve o mesmo conjunto."""

import csv
import io

COLUNAS = (
    "RULETYPE", "FROMFEATURECLASS", "FROMASSETGROUP", "FROMASSETTYPE", "FROMTERMINAL",
    "TOFEATURECLASS", "TOASSETGROUP", "TOASSETTYPE", "TOTERMINAL",
    "VIAFEATURECLASS", "VIAASSETGROUP", "VIAASSETTYPE", "VIATERMINAL",
)

TIPO_PARA_ESRI = {
    "juncao_juncao": "Junction Junction Connectivity",
    "juncao_aresta": "Junction Edge Connectivity",
    "aresta_juncao_aresta": "Edge Junction Edge Connectivity",
    "contencao": "Containment",
    "estrutura": "Structural Attachment",
}
ESRI_PARA_TIPO = {v: k for k, v in TIPO_PARA_ESRI.items()}


class ErroCsv(Exception):
    """CSV de regras recusado; `problemas` aponta linha e causa de cada erro (a lista inteira, nunca só o
    primeiro, como no pacote)."""

    def __init__(self, problemas: list[dict]):
        self.problemas = problemas
        super().__init__(f"{len(problemas)} problema(s) no CSV de regras")


def _problema(linha: int | None, coluna: str | None, erro: str, mensagem: str) -> dict:
    return {"linha": linha, "coluna": coluna, "erro": erro, "mensagem": mensagem}


def exportar(regras: list) -> bytes:
    """Lista de `regras.Regra` -> CSV UTF-8 com as 13 colunas, ordenado de forma estável (a reimportação
    dá o mesmo conjunto e a reexportação dá o mesmo arquivo)."""
    from app.rede_utilidades.regras import Regra  # só para anotação; a lista já vem pronta

    def k(r: Regra):
        return (r.tipo, r.de, r.de_terminal or "", r.via or ("", 0), r.para, r.para_terminal or "")

    mem = io.StringIO()
    w = csv.writer(mem)
    w.writerow(COLUNAS)
    for r in sorted(regras, key=k):
        w.writerow([
            TIPO_PARA_ESRI[r.tipo],
            r.de[0], r.de[0], str(r.de[1]), r.de_terminal or "",
            r.para[0], r.para[0], str(r.para[1]), r.para_terminal or "",
            r.via[0] if r.via else "", r.via[0] if r.via else "",
            str(r.via[1]) if r.via else "", r.via_terminal or "",
        ])
    return mem.getvalue().encode("utf-8")


def _lado(prefixo: str, linha_n: int, row: dict, tipos_por_grupo: dict, terminais: dict,
          problemas: list[dict], obrigatorio: bool):
    """Lê FROM*/TO*/VIA* de uma linha. Devolve (ref, terminal) ou None (o problema já está na lista)."""
    fc = row[f"{prefixo}FEATURECLASS"].strip()
    ag = row[f"{prefixo}ASSETGROUP"].strip()
    at = row[f"{prefixo}ASSETTYPE"].strip()
    te = row[f"{prefixo}TERMINAL"].strip()
    if not (fc or ag or at or te):
        if obrigatorio:
            problemas.append(_problema(linha_n, f"{prefixo}FEATURECLASS", "lado_vazio",
                                       f"o lado {prefixo} é obrigatório neste tipo de regra"))
        return None
    if ag != fc:
        problemas.append(_problema(
            linha_n, f"{prefixo}ASSETGROUP", "grupo_divergente",
            f"ASSETGROUP {ag!r} diverge de FEATURECLASS {fc!r}; nesta plataforma o grupo de ativo é a "
            f"própria classe de feição, então as duas colunas carregam o mesmo código",
        ))
        return None
    candidatos = tipos_por_grupo.get(fc)
    if candidatos is None:
        problemas.append(_problema(linha_n, f"{prefixo}FEATURECLASS", "grupo_inexistente",
                                   f"não existe grupo de ativo {fc!r} nesta rede"))
        return None
    ref = None
    if at.isdigit() and int(at) in candidatos:
        ref = (fc, int(at))
    else:
        achados = [cod for cod, chave in candidatos.items() if chave == at]
        if len(achados) == 1:
            ref = (fc, achados[0])
    if ref is None:
        problemas.append(_problema(
            linha_n, f"{prefixo}ASSETTYPE", "tipo_inexistente",
            f"{at!r} não é código nem chave de um tipo de ativo do grupo {fc!r}",
        ))
        return None
    if te and te not in terminais.get(ref, set()):
        problemas.append(_problema(
            linha_n, f"{prefixo}TERMINAL", "terminal_inexistente",
            f"o terminal {te!r} não existe na configuração de terminal do tipo {ref[1]} do grupo {fc!r}",
        ))
        return None
    return ref, (te or None)


def importar(bruto: bytes, tipos_por_grupo: dict, terminais: dict, geometrias: dict) -> list[dict]:
    """CSV -> lista de regras validadas [{tipo, de, para, via?, de_terminal, ...}] pronta para gravar.
    `tipos_por_grupo`: {grupo: {codigo: chave}}; `terminais`: {(grupo, codigo): {nomes}}; `geometrias`:
    {grupo: geometria}. Levanta ErroCsv com a lista inteira de problemas."""
    from app.rede_utilidades.esquema import GEOMETRIA_ARESTA, GEOMETRIA_JUNCAO

    try:
        texto = bruto.decode("utf-8-sig")
    except UnicodeDecodeError as e:
        raise ErroCsv([_problema(None, None, "nao_e_utf8", f"o corpo não é UTF-8 válido: {e}")]) from e
    leitor = csv.reader(io.StringIO(texto))
    linhas = list(leitor)
    if not linhas:
        raise ErroCsv([_problema(None, None, "vazio", "o CSV está vazio")])
    cabecalho = [c.strip() for c in linhas[0]]
    if tuple(cabecalho) != COLUNAS:
        raise ErroCsv([_problema(
            1, None, "cabecalho_invalido",
            f"o cabeçalho tem de ser exatamente: {','.join(COLUNAS)} (as 13 colunas das ferramentas "
            f"Import/Export Rules da Esri); veio: {','.join(cabecalho) or '(vazio)'}",
        )])

    problemas: list[dict] = []
    regras: list[dict] = []
    vistos: dict = {}
    for n, valores in enumerate(linhas[1:], start=2):
        if not any(v.strip() for v in valores):
            continue  # linha em branco não é regra nem erro
        if len(valores) != len(COLUNAS):
            problemas.append(_problema(n, None, "colunas_erradas",
                                       f"a linha tem {len(valores)} colunas; são {len(COLUNAS)}"))
            continue
        row = dict(zip(COLUNAS, valores, strict=True))
        tipo = ESRI_PARA_TIPO.get(row["RULETYPE"].strip())
        if tipo is None:
            problemas.append(_problema(
                n, "RULETYPE", "regra_tipo_inexistente",
                f"RULETYPE {row['RULETYPE'].strip()!r} não existe; vale um de: "
                f"{', '.join(sorted(ESRI_PARA_TIPO))}",
            ))
            continue
        de = _lado("FROM", n, row, tipos_por_grupo, terminais, problemas, True)
        para = _lado("TO", n, row, tipos_por_grupo, terminais, problemas, True)
        via = _lado("VIA", n, row, tipos_por_grupo, terminais, problemas, tipo == "aresta_juncao_aresta")
        if de is None or para is None or (tipo == "aresta_juncao_aresta" and via is None):
            continue
        if tipo != "aresta_juncao_aresta" and via is not None:
            problemas.append(_problema(n, "VIAFEATURECLASS", "via_proibido",
                                       f"o lado VIA só existe na Edge Junction Edge Connectivity, não em "
                                       f"{row['RULETYPE'].strip()!r}"))
            continue
        # papel de geometria: junção de um lado, aresta do outro (a mesma regra do pacote versão 2)
        if tipo == "juncao_aresta":
            if geometrias.get(de[0][0]) not in GEOMETRIA_JUNCAO or geometrias.get(para[0][0]) not in GEOMETRIA_ARESTA:
                problemas.append(_problema(n, "FROMFEATURECLASS", "papel_errado",
                                           "na Junction Edge Connectivity o lado FROM é a junção (grupo de "
                                           "geometria ponto) e o TO é a aresta (linha)"))
                continue
            if para[1] is not None:
                problemas.append(_problema(n, "TOTERMINAL", "terminal_nao_se_aplica",
                                           "na Junction Edge Connectivity o terminal fica no lado FROM (a junção)"))
                continue
        elif tipo == "juncao_juncao":
            if geometrias.get(de[0][0]) not in GEOMETRIA_JUNCAO or geometrias.get(para[0][0]) not in GEOMETRIA_JUNCAO:
                problemas.append(_problema(n, "FROMFEATURECLASS", "papel_errado",
                                           "na Junction Junction Connectivity os dois lados são junções (ponto)"))
                continue
        elif tipo == "aresta_juncao_aresta":
            if (geometrias.get(de[0][0]) not in GEOMETRIA_ARESTA
                    or geometrias.get(para[0][0]) not in GEOMETRIA_ARESTA
                    or geometrias.get(via[0][0]) not in GEOMETRIA_JUNCAO):
                problemas.append(_problema(n, "VIAFEATURECLASS", "papel_errado",
                                           "na Edge Junction Edge Connectivity FROM e TO são arestas (linha) "
                                           "e VIA é a junção (ponto)"))
                continue
        if tipo != "juncao_aresta":
            for lado, rotulo in ((de, "FROM"), (para, "TO"), (via, "VIA")):
                if lado is not None and lado[1] is not None:
                    problemas.append(_problema(n, f"{rotulo}TERMINAL", "terminal_nao_se_aplica",
                                               f"terminal no lado {rotulo} só se aplica à Junction Edge "
                                               f"Connectivity, e só no lado FROM"))
        chave = (tipo, de, para, via)
        if chave in vistos:
            problemas.append(_problema(n, None, "regra_repetida",
                                       f"regra repetida: igual à da linha {vistos[chave]}"))
            continue
        vistos[chave] = n
        regras.append({
            "tipo": tipo, "de": de[0], "para": para[0], "via": via[0] if via else None,
            "de_terminal": de[1], "para_terminal": para[1], "via_terminal": via[1] if via else None,
        })
    if problemas:
        raise ErroCsv(problemas)
    return regras
