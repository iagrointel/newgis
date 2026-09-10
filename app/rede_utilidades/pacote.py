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
from app.rede_utilidades.esquema import (
    ESQUEMAS,
    ESQUEMA_VERSAO,
    GEOMETRIA_ARESTA,
    GEOMETRIA_JUNCAO,
)

SECOES = ("dominios", "tiers", "categorias", "terminais", "grupos", "tipos", "atributos", "regras")


def _chave_ref(ref: dict) -> tuple:
    """Chave de ordenação/unicidade de um lado de regra na versão 2 (objeto {grupo, tipo, terminal?})."""
    if not isinstance(ref, dict):
        return ("", 0, "")
    return (ref.get("grupo", ""), ref.get("tipo", 0), ref.get("terminal") or "")


# chave de ordenação de cada lista na forma canônica; é sempre única depois da conferência de repetição
ORDEM = {
    "dominios": lambda d: (d.get("codigo", ""),),
    "tiers": lambda d: (d.get("dominio", ""), d.get("ordem", 0), d.get("codigo", "")),
    "categorias": lambda d: (d.get("codigo", ""),),
    "terminais": lambda d: (d.get("codigo", ""),),
    "grupos": lambda d: (d.get("dominio", ""), d.get("codigo", "")),
    "tipos": lambda d: (d.get("grupo", ""), d.get("codigo", 0)),
    "atributos": lambda d: (d.get("grupo", ""), d.get("tipo") or 0, d.get("codigo", "")),
    "regras": lambda d: (d.get("tipo", ""), *_chave_ref(d.get("de")), *_chave_ref(d.get("via")),
                         *_chave_ref(d.get("para"))),
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


def _conferir_comum(bruto: str, doc: dict) -> list[dict]:
    """Conferências iguais nas duas versões do esquema: repetição de código e referência entre as seções de
    catálogo (domínio, tier, categoria, terminal, grupo, tipo, atributo). Regra fica de fora — muda de forma
    entre a versão 1 e a 2 e cada uma tem a sua conferência."""
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
    return problemas


def _conferir_regras_v1(bruto: str, doc: dict) -> list[dict]:
    """Regra da versão 1: par solto `de`/`para` em texto "grupo/codigo"."""
    problemas: list[dict] = []
    tipos_por_grupo: dict = {}
    for t in doc.get("tipos", []):
        if isinstance(t, dict):
            tipos_por_grupo.setdefault(t.get("grupo"), set()).add(t.get("codigo"))
    problemas += _repetidos(
        bruto, "regras", doc.get("regras", []), lambda d: (d["tipo"], d["de"], d["para"]), "regra",
    )
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


def _mapa_terminais(doc: dict) -> dict:
    """(grupo, codigo do tipo) -> conjunto dos NOMES de terminal da configuração que o tipo usa."""
    configs = {t.get("codigo"): {x.get("nome") for x in t.get("terminais", []) if isinstance(x, dict)}
               for t in doc.get("terminais", []) if isinstance(t, dict)}
    mapa: dict = {}
    for t in doc.get("tipos", []):
        if isinstance(t, dict):
            mapa[(t.get("grupo"), t.get("codigo"))] = configs.get(t.get("terminal"), set())
    return mapa


def _conferir_ref(bruto: str, doc: dict, caminho: list, ref, tipos_por_grupo: dict,
                  terminais: dict, problemas: list[dict]) -> None:
    """Um lado de regra na versão 2: {grupo, tipo, terminal?}. Confere existência e terminal."""
    if not isinstance(ref, dict):
        return
    grupo, codigo = ref.get("grupo"), ref.get("tipo")
    if codigo not in tipos_por_grupo.get(grupo, set()):
        problemas.append(_problema(
            bruto, caminho, "tipo_inexistente",
            f"a regra aponta para o tipo de ativo {codigo!r} do grupo {grupo!r}, "
            f"que não existe neste pacote",
        ))
        return
    terminal = ref.get("terminal")
    if terminal is not None and terminal not in terminais.get((grupo, codigo), set()):
        problemas.append(_problema(
            bruto, [*caminho, "terminal"], "terminal_inexistente",
            f"o terminal {terminal!r} não existe na configuração de terminal do tipo de ativo "
            f"{codigo!r} do grupo {grupo!r}",
        ))


def _conferir_regras_v2(bruto: str, doc: dict) -> list[dict]:
    """Regra da versão 2: lados {grupo, tipo, terminal?}, lado VIA só na aresta-junção-aresta, e PAPEL de
    geometria por tipo de regra (junção de um lado, aresta do outro)."""
    problemas: list[dict] = []
    tipos_por_grupo: dict = {}
    for t in doc.get("tipos", []):
        if isinstance(t, dict):
            tipos_por_grupo.setdefault(t.get("grupo"), set()).add(t.get("codigo"))
    terminais = _mapa_terminais(doc)
    geometrias = {g.get("codigo"): g.get("geometria") for g in doc.get("grupos", []) if isinstance(g, dict)}

    problemas += _repetidos(
        bruto, "regras", doc.get("regras", []),
        lambda d: (d["tipo"], _chave_ref(d["de"]), _chave_ref(d.get("via")), _chave_ref(d["para"])), "regra",
    )

    def _papel(i: int, r: dict, lado: str, esperadas: tuple, rotulo: str) -> None:
        ref = r.get(lado)
        if isinstance(ref, dict) and geometrias.get(ref.get("grupo")) not in esperadas:
            problemas.append(_problema(
                bruto, ["regras", i, lado], "papel_errado",
                f"o lado {lado!r} de uma regra {r.get('tipo')!r} tem de ser {rotulo}, mas o grupo "
                f"{ref.get('grupo')!r} tem geometria {geometrias.get(ref.get('grupo'))!r}",
            ))

    for i, r in enumerate(doc.get("regras", []) or []):
        if not isinstance(r, dict):
            continue
        tipo = r.get("tipo")
        for lado in ("de", "para", "via"):
            if lado in r:
                _conferir_ref(bruto, doc, ["regras", i, lado], r.get(lado), tipos_por_grupo, terminais, problemas)
        if tipo == "aresta_juncao_aresta":
            if "via" not in r:
                problemas.append(_problema(
                    bruto, ["regras", i], "via_obrigatorio",
                    "a regra aresta-junção-aresta exige o lado 'via' (a junção do meio)",
                ))
            else:
                _papel(i, r, "via", GEOMETRIA_JUNCAO, "uma junção")
            _papel(i, r, "de", GEOMETRIA_ARESTA, "uma aresta")
            _papel(i, r, "para", GEOMETRIA_ARESTA, "uma aresta")
        else:
            if "via" in r:
                problemas.append(_problema(
                    bruto, ["regras", i, "via"], "via_proibido",
                    f"o lado 'via' só existe na regra aresta-junção-aresta, não em {tipo!r}",
                ))
        if tipo == "juncao_aresta":
            _papel(i, r, "de", GEOMETRIA_JUNCAO, "uma junção")
            _papel(i, r, "para", GEOMETRIA_ARESTA, "uma aresta")
            if isinstance(r.get("para"), dict) and r["para"].get("terminal") is not None:
                problemas.append(_problema(
                    bruto, ["regras", i, "para", "terminal"], "terminal_nao_se_aplica",
                    "na regra junção-aresta o terminal fica no lado 'de' (a junção); a aresta não tem terminal",
                ))
        elif tipo == "juncao_juncao":
            _papel(i, r, "de", GEOMETRIA_JUNCAO, "uma junção")
            _papel(i, r, "para", GEOMETRIA_JUNCAO, "uma junção")
        if tipo != "juncao_aresta":
            # terminal só faz sentido no lado da junção da junção-aresta; o resto é o item L4-03-b-terminais
            for lado in ("de", "para", "via"):
                ref = r.get(lado)
                if isinstance(ref, dict) and ref.get("terminal") is not None:
                    problemas.append(_problema(
                        bruto, ["regras", i, lado, "terminal"], "terminal_nao_se_aplica",
                        f"terminal no lado {lado!r} não se aplica à regra {tipo!r} (só a junção-aresta "
                        f"declara terminal, e só no lado 'de')",
                    ))
    return problemas


# tradução do vocabulário da versão 1 para o da 2
_TIPO_V1_PARA_V2 = {
    "conectividade_no_trecho": "juncao_aresta",
    "conectividade_entre_nos": "juncao_juncao",
    "fixacao_estrutural": "estrutura",
    "contencao": "contencao",
}


def _converter_v1(bruto: str, doc: dict) -> dict:
    """Pacote da versão 1 -> forma 2. As seções de catálogo passam intactas; cada regra vira lados
    {grupo, tipo}. Na `conectividade_no_trecho` a junção vai para o lado `de` (a versão 1 não marcava
    qual era qual); regra em que os dois lados têm a mesma geometria não tem como normalizar e é recusada
    com a linha apontada — caso medido no pacote elétrico 1.0.0 (ramal->trecho), que por isso foi
    reescrito em versão 2 (1.1.0)."""
    geometrias = {g.get("codigo"): g.get("geometria") for g in doc.get("grupos", []) if isinstance(g, dict)}
    problemas: list[dict] = []
    regras = []
    for i, r in enumerate(doc.get("regras", []) or []):
        de_g, _, de_c = str(r.get("de", "")).partition("/")
        pa_g, _, pa_c = str(r.get("para", "")).partition("/")
        if not (de_c.isdigit() and pa_c.isdigit()):
            continue  # já saiu como problema na conferência da versão 1
        de_ref, para_ref = {"grupo": de_g, "tipo": int(de_c)}, {"grupo": pa_g, "tipo": int(pa_c)}
        tipo = _TIPO_V1_PARA_V2[r["tipo"]]
        if tipo == "juncao_aresta":
            de_eh_juncao = geometrias.get(de_g) in GEOMETRIA_JUNCAO
            para_eh_juncao = geometrias.get(pa_g) in GEOMETRIA_JUNCAO
            if para_eh_juncao and not de_eh_juncao:
                de_ref, para_ref = para_ref, de_ref
            elif de_eh_juncao == para_eh_juncao:
                problemas.append(_problema(
                    bruto, ["regras", i, "de"], "regra_sem_lado_juncao",
                    f"a regra {r['de']!r} -> {r['para']!r} não tem um lado junção e outro aresta "
                    f"(geometrias {geometrias.get(de_g)!r} e {geometrias.get(pa_g)!r}); na versão 2 a "
                    f"junção-aresta exige um lado de cada — reescreva a regra já em versão 2",
                ))
                continue
        nova = {"tipo": tipo, "de": de_ref, "para": para_ref}
        if r.get("descricao") is not None:
            nova["descricao"] = r["descricao"]
        regras.append(nova)
    if problemas:
        raise ErroPacote(problemas)
    convertido = dict(doc)
    convertido["esquema_versao"] = ESQUEMA_VERSAO
    convertido["regras"] = regras
    return convertido


def ler(bruto: bytes) -> dict:
    """bytes recebidos -> dicionário validado, SEMPRE na forma da versão corrente do esquema (pacote da
    versão 1 sai daqui convertido). Levanta ErroPacote com a lista inteira de problemas."""
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

    versao = doc.get("esquema_versao")
    if versao not in ESQUEMAS:
        raise ErroPacote([{"caminho": "esquema_versao", "linha": localizador.linha(texto, ["esquema_versao"]),
                           "erro": "esquema_versao_desconhecida",
                           "mensagem": f"esquema_versao {versao!r} não é aceita; este serviço lê as versões "
                                       f"{sorted(ESQUEMAS)} do esquema plat.rede.pacote"}])

    problemas = []
    for erro in sorted(Draft202012Validator(ESQUEMAS[versao]).iter_errors(doc),
                     key=lambda e: list(e.absolute_path)):
        caminho = list(erro.absolute_path)
        problemas.append(_problema(texto, caminho, "esquema", erro.message))
    if problemas:
        raise ErroPacote(problemas)

    problemas = _conferir_comum(texto, doc)
    problemas += _conferir_regras_v1(texto, doc) if versao == 1 else _conferir_regras_v2(texto, doc)
    if problemas:
        raise ErroPacote(problemas)
    if versao == 1:
        return _converter_v1(texto, doc)
    return doc


def versao_do_esquema() -> int:
    return ESQUEMA_VERSAO
