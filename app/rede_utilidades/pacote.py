"""Leitura, validação e forma canônica do pacote de ativos.

FORMA CANÔNICA. O pacote é JSON UTF-8 com chaves em ordem alfabética, recuo de 1 espaço, listas ordenadas por
uma chave declarada em `ORDEM` e uma quebra de linha no fim. Isso existe para que a exportação seja
BYTE A BYTE igual à importação sem que o serviço precise guardar o arquivo que recebeu: o que volta é
reconstruído das tabelas `plat.rede_*` e serializado de novo. Guardar o arquivo original e devolvê-lo daria
o mesmo teste passando e esconderia a única coisa que interessa provar — que as tabelas carregam o pacote
inteiro. A prova disso é o teste que altera uma linha no banco e vê a exportação mudar.

VALIDAÇÃO em duas camadas: o esquema JSON (`app/rede_utilidades/esquema.py`) cuida da forma; a conferência de
referência abaixo cuida do que o esquema não alcança — código repetido e referência para algo que não existe
no pacote. Todo problema sai com o caminho (`tipos[41].grupo`), a LINHA do texto enviado e um código curto."""

import json

from jsonschema import Draft202012Validator

from app.rede_utilidades import localizador
from app.rede_utilidades.esquema import ESQUEMA, ESQUEMA_VERSAO

SECOES = ("dominios", "tiers", "categorias", "terminais", "grupos", "tipos", "atributos", "regras")
# chave de ordenação de cada lista na forma canônica; é sempre única depois da conferência de repetição
ORDEM = {
    "dominios": lambda d: (d.get("codigo", ""),),
    "tiers": lambda d: (d.get("dominio", ""), d.get("ordem", 0), d.get("codigo", "")),
    "categorias": lambda d: (d.get("codigo", ""),),
    "terminais": lambda d: (d.get("codigo", ""),),
    "grupos": lambda d: (d.get("dominio", ""), d.get("codigo", "")),
    "tipos": lambda d: (d.get("grupo", ""), d.get("codigo", 0)),
    "atributos": lambda d: (d.get("grupo", ""), d.get("tipo") or 0, d.get("codigo", "")),
    "regras": lambda d: (d.get("tipo", ""), d.get("de", ""), d.get("para", "")),
}


class ErroPacote(Exception):
    """Pacote recusado. `problemas` é a lista completa (nunca só o primeiro): caminho, linha, erro, mensagem."""

    def __init__(self, problemas: list[dict]):
        self.problemas = problemas
        super().__init__(f"{len(problemas)} problema(s) no pacote")


# listas internas cuja ordem não carrega significado; a forma canônica as ordena para que a exportação, que
# as reconstrói de tabelas sem ordem, bata byte a byte com o arquivo importado
LISTAS_ORDENADAS = {"tipos": ("categorias", "codigos_fonte"), "grupos": ("camadas_fonte",)}


def canonizar(pacote: dict) -> bytes:
    """Forma canônica em bytes. Único lugar do produto que serializa um pacote."""
    saida = dict(pacote)
    for secao, campos in LISTAS_ORDENADAS.items():
        if isinstance(saida.get(secao), list):
            novos = []
            for item in saida[secao]:
                item = dict(item) if isinstance(item, dict) else item
                for campo in campos:
                    if isinstance(item, dict) and isinstance(item.get(campo), list):
                        item[campo] = sorted(item[campo])
                novos.append(item)
            saida[secao] = novos
    for secao, chave in ORDEM.items():
        if isinstance(saida.get(secao), list):
            saida[secao] = sorted(saida[secao], key=chave)
    return (json.dumps(saida, ensure_ascii=False, indent=1, sort_keys=True) + "\n").encode("utf-8")


def _problema(bruto: str, caminho: list, erro: str, mensagem: str, extra: dict | None = None) -> dict:
    p = {
        "caminho": localizador.texto_do_caminho(caminho),
        "linha": localizador.linha(bruto, caminho),
        "erro": erro,
        "mensagem": mensagem,
    }
    if extra:
        p.update(extra)
    return p


def _repetidos(bruto: str, secao: str, itens: list, chave, rotulo: str) -> list[dict]:
    """Código repetido dentro de uma seção. Aponta a linha da SEGUNDA ocorrência e a da primeira."""
    vistos: dict = {}
    saida = []
    for i, item in enumerate(itens):
        try:
            k = chave(item)
        except (TypeError, KeyError):
            continue
        if k in vistos:
            primeiro = vistos[k]
            saida.append(
                _problema(
                    bruto, [secao, i], "codigo_repetido",
                    f"{rotulo} repetido no pacote: {k!r} já aparece em {secao}[{primeiro}]",
                    {"linha_anterior": localizador.linha(bruto, [secao, primeiro])},
                )
            )
        else:
            vistos[k] = i
    return saida


def _chave_repetida(bruto: str) -> list[dict]:
    """Seção ou campo repetido em qualquer profundidade (achado A2/A2b, turno 3). `json.loads` fica em silêncio
    com a ÚLTIMA ocorrência; aqui cada duplicata sai como problema, com a linha que a validação de fato usou e
    a linha da que foi descartada."""
    saida = []
    for d in localizador.chaves_repetidas(bruto):
        pai = localizador.texto_do_caminho(d["caminho"][:-1]) or "(raiz)"
        saida.append({
            "caminho": localizador.texto_do_caminho(d["caminho"]),
            "linha": d["linha"],
            "erro": "chave_repetida",
            "mensagem": (
                f"a chave {d['chave']!r} aparece duas vezes em {pai}; a ocorrência da linha "
                f"{d['linha_anterior']} foi descartada em silêncio e esta (linha {d['linha']}) é a que valeu"
            ),
            "linha_anterior": d["linha_anterior"],
        })
    return saida


def _procurar_nul(bruto: str, no, caminho: list) -> list[dict]:
    """Caractere nulo (`\\u0000`) dentro de qualquer texto do pacote (achado A3, turno 3): o esquema JSON não
    proíbe, mas nem `text` nem `jsonb` do Postgres aceitam — sem esta checagem o pacote passa na validação e
    derruba a importação com uma exceção não tratada (500)."""
    problemas = []
    if isinstance(no, str):
        if "\x00" in no:
            problemas.append(_problema(
                bruto, caminho, "caractere_nulo",
                f"o campo {localizador.texto_do_caminho(caminho)} contém um caractere nulo (\\u0000), "
                f"que o banco não aceita",
            ))
    elif isinstance(no, dict):
        for k, v in no.items():
            problemas += _procurar_nul(bruto, v, [*caminho, k])
    elif isinstance(no, list):
        for i, v in enumerate(no):
            problemas += _procurar_nul(bruto, v, [*caminho, i])
    return problemas


def _conferir_referencias(bruto: str, doc: dict) -> list[dict]:
    problemas: list[dict] = _chave_repetida(bruto) + _procurar_nul(bruto, doc, [])
    dominios = {d.get("codigo") for d in doc.get("dominios", []) if isinstance(d, dict)}
    categorias = {c.get("codigo") for c in doc.get("categorias", []) if isinstance(c, dict)}
    terminais = {t.get("codigo") for t in doc.get("terminais", []) if isinstance(t, dict)}
    tiers = {t.get("codigo"): t.get("dominio") for t in doc.get("tiers", []) if isinstance(t, dict)}
    grupos = {g.get("codigo"): g.get("dominio") for g in doc.get("grupos", []) if isinstance(g, dict)}

    problemas += _repetidos(bruto, "dominios", doc.get("dominios", []), lambda d: d["codigo"], "código de domínio")
    problemas += _repetidos(bruto, "tiers", doc.get("tiers", []), lambda d: d["codigo"], "código de tier")
    problemas += _repetidos(
        bruto, "categorias", doc.get("categorias", []), lambda d: d["codigo"], "código de categoria"
    )
    problemas += _repetidos(bruto, "terminais", doc.get("terminais", []), lambda d: d["codigo"], "código de terminal")
    problemas += _repetidos(bruto, "grupos", doc.get("grupos", []), lambda d: d["codigo"], "código de grupo")
    problemas += _repetidos(
        bruto, "tipos", doc.get("tipos", []), lambda d: (d["grupo"], d["codigo"]),
        "código de tipo de ativo dentro do grupo",
    )
    problemas += _repetidos(
        bruto, "tipos", doc.get("tipos", []), lambda d: (d["grupo"], d["chave"]),
        "chave de tipo de ativo dentro do grupo",
    )
    problemas += _repetidos(
        bruto, "atributos", doc.get("atributos", []),
        lambda d: (d["grupo"], d.get("tipo"), d["codigo"]), "código de atributo dentro do grupo",
    )
    problemas += _repetidos(
        bruto, "regras", doc.get("regras", []), lambda d: (d["tipo"], d["de"], d["para"]), "regra",
    )

    for i, t in enumerate(doc.get("tiers", [])):
        if isinstance(t, dict) and t.get("dominio") not in dominios:
            problemas.append(_problema(
                bruto, ["tiers", i, "dominio"], "dominio_inexistente",
                f"o tier {t.get('codigo')!r} aponta para a rede de domínio {t.get('dominio')!r}, "
                f"que não existe neste pacote",
            ))
    for i, g in enumerate(doc.get("grupos", [])):
        if isinstance(g, dict) and g.get("dominio") not in dominios:
            problemas.append(_problema(
                bruto, ["grupos", i, "dominio"], "dominio_inexistente",
                f"o grupo {g.get('codigo')!r} aponta para a rede de domínio {g.get('dominio')!r}, "
                f"que não existe neste pacote",
            ))
    for i, t in enumerate(doc.get("tipos", [])):
        if not isinstance(t, dict):
            continue
        if t.get("grupo") not in grupos:
            problemas.append(_problema(
                bruto, ["tipos", i, "grupo"], "grupo_inexistente",
                f"o tipo de ativo {t.get('chave')!r} aponta para o grupo {t.get('grupo')!r}, "
                f"que não existe neste pacote",
            ))
        if t.get("tier") not in tiers:
            problemas.append(_problema(
                bruto, ["tipos", i, "tier"], "tier_inexistente",
                f"o tipo de ativo {t.get('chave')!r} aponta para o tier {t.get('tier')!r}, "
                f"que não existe neste pacote",
            ))
        elif t.get("grupo") in grupos and tiers[t["tier"]] != grupos[t["grupo"]]:
            problemas.append(_problema(
                bruto, ["tipos", i, "tier"], "tier_de_outro_dominio",
                f"o tipo de ativo {t.get('chave')!r} está no grupo {t.get('grupo')!r} (domínio "
                f"{grupos[t['grupo']]!r}) mas usa o tier {t.get('tier')!r}, que é do domínio {tiers[t['tier']]!r}",
            ))
        if t.get("terminal") not in terminais:
            problemas.append(_problema(
                bruto, ["tipos", i, "terminal"], "terminal_inexistente",
                f"o tipo de ativo {t.get('chave')!r} usa a configuração de terminal {t.get('terminal')!r}, "
                f"que não existe neste pacote",
            ))
        for j, c in enumerate(t.get("categorias", []) or []):
            if c not in categorias:
                problemas.append(_problema(
                    bruto, ["tipos", i, "categorias", j], "categoria_inexistente",
                    f"o tipo de ativo {t.get('chave')!r} usa a categoria {c!r}, que não existe neste pacote",
                ))

    tipos_por_grupo: dict = {}
    for t in doc.get("tipos", []):
        if isinstance(t, dict):
            tipos_por_grupo.setdefault(t.get("grupo"), set()).add(t.get("codigo"))
    for i, a in enumerate(doc.get("atributos", []) or []):
        if not isinstance(a, dict):
            continue
        if a.get("grupo") not in grupos:
            problemas.append(_problema(
                bruto, ["atributos", i, "grupo"], "grupo_inexistente",
                f"o atributo {a.get('codigo')!r} aponta para o grupo {a.get('grupo')!r}, "
                f"que não existe neste pacote",
            ))
        elif a.get("tipo") is not None and a["tipo"] not in tipos_por_grupo.get(a["grupo"], set()):
            problemas.append(_problema(
                bruto, ["atributos", i, "tipo"], "tipo_inexistente",
                f"o atributo {a.get('codigo')!r} aponta para o tipo de ativo {a['tipo']} do grupo "
                f"{a.get('grupo')!r}, que não existe neste pacote",
            ))
    for i, r in enumerate(doc.get("regras", []) or []):
        if not isinstance(r, dict):
            continue
        for lado in ("de", "para"):
            alvo = r.get(lado, "")
            grupo, _, codigo = str(alvo).partition("/")
            if not codigo.isdigit() or int(codigo) not in tipos_por_grupo.get(grupo, set()):
                problemas.append(_problema(
                    bruto, ["regras", i, lado], "tipo_inexistente",
                    f"a regra aponta para {alvo!r}, que não é um tipo de ativo deste pacote "
                    f"(o formato é grupo/codigo, por exemplo 'trecho_de_media_tensao/1')",
                ))
    return problemas


def ler(bruto: bytes) -> dict:
    """bytes recebidos -> dicionário validado. Levanta ErroPacote com a lista inteira de problemas."""
    try:
        texto = bruto.decode("utf-8")
    except UnicodeDecodeError as e:
        raise ErroPacote([{"caminho": "(raiz)", "linha": None, "erro": "nao_e_utf8",
                           "mensagem": f"o corpo não é UTF-8 válido: {e}"}]) from e
    try:
        doc = json.loads(texto)
    except json.JSONDecodeError as e:
        raise ErroPacote([{"caminho": "(raiz)", "linha": e.lineno, "erro": "json_invalido",
                           "mensagem": f"JSON inválido na coluna {e.colno}: {e.msg}"}]) from e
    if not isinstance(doc, dict):
        raise ErroPacote([{"caminho": "(raiz)", "linha": 1, "erro": "raiz_nao_e_objeto",
                           "mensagem": "a raiz do pacote tem de ser um objeto JSON"}])

    problemas = []
    for erro in sorted(Draft202012Validator(ESQUEMA).iter_errors(doc), key=lambda e: list(e.absolute_path)):
        caminho = list(erro.absolute_path)
        problemas.append(_problema(texto, caminho, "esquema", erro.message))
    if problemas:
        raise ErroPacote(problemas)

    problemas = _conferir_referencias(texto, doc)
    if problemas:
        raise ErroPacote(problemas)
    return doc


def versao_do_esquema() -> int:
    return ESQUEMA_VERSAO
