"""Motor de regras de conectividade da rede de utilidades (item L4-03-a-regras-de-conectividade).

POLÍTICA PADRÃO: "SEM REGRA = PROIBIDO". Uma conexão (junção-junção, junção-aresta ou aresta-junção-aresta)
ou associação (contenção, estrutura) só existe se uma LINHA de `plat.rede_regra` permitir exatamente aquele
par de tipos de ativo, naquele papel e com aquele terminal. É o mesmo princípio da utility network da Esri
("features can only connect or associate if a rule exists"); a única comporta é `rede.regras_ativas`, e
desligá-la é ato de admin da rede (ver `rotas_regras.ativar_regras` e o ADR do item).

As funções de avaliação são PURAS: recebem a lista de regras (já com as chaves naturais grupo/código) e o
pedido de conexão, e devolvem a regra que casa — ou None e as candidatas próximas, para a mensagem citar a
regra. Quem mede a geometria e grava é `rotas_regras`; quem mede o CSV é `regras_csv`.

Chave natural do tipo de ativo: tupla (codigo do grupo, codigo do tipo) — é o vocabulário do pacote, estável
entre inquilinos, ao contrário do uuid interno."""

from dataclasses import dataclass, field

Ref = tuple[str, int]  # (codigo do grupo de ativo, codigo do tipo de ativo)

TIPOS_REGRA = ("juncao_juncao", "juncao_aresta", "aresta_juncao_aresta", "contencao", "estrutura")


@dataclass
class Regra:
    id: str
    tipo: str
    de: Ref
    para: Ref
    de_terminal: str | None = None
    para_terminal: str | None = None
    via: Ref | None = None
    via_terminal: str | None = None
    descricao: str | None = None


@dataclass
class Violacao:
    """Uma conexão/associação recusada. `candidatas` são as regras do mesmo tipo para o mesmo par de tipos
    de ativo que NÃO casaram (quase sempre por terminal) — é com elas que a mensagem cita a regra."""
    codigo: str
    mensagem: str
    feicoes: list[str] = field(default_factory=list)
    candidatas: list[dict] = field(default_factory=list)

    def json(self) -> dict:
        d = {"codigo": self.codigo, "mensagem": self.mensagem, "feicoes": self.feicoes}
        if self.candidatas:
            d["regras_candidatas"] = self.candidatas
        return d


def texto_ref(ref: Ref) -> str:
    return f"{ref[0]}/{ref[1]}"


def _ref_json(ref: Ref) -> dict:
    return {"grupo": ref[0], "tipo": ref[1]}


def regra_json(r: Regra) -> dict:
    """A regra em forma citável (a mesma forma dos lados no pacote versão 2)."""
    d = {"id": r.id, "tipo": r.tipo, "de": _ref_json(r.de), "para": _ref_json(r.para)}
    if r.de_terminal:
        d["de"]["terminal"] = r.de_terminal
    if r.para_terminal:
        d["para"]["terminal"] = r.para_terminal
    if r.via is not None:
        d["via"] = _ref_json(r.via)
        if r.via_terminal:
            d["via"]["terminal"] = r.via_terminal
    if r.descricao:
        d["descricao"] = r.descricao
    return d


def texto_regra(r: Regra) -> str:
    """A regra numa frase curta, para a mensagem de recusa citar."""
    if r.tipo == "juncao_aresta":
        terminal = f" pelo terminal {r.de_terminal!r}" if r.de_terminal else " sem terminal"
        return f"juncao_aresta {texto_ref(r.de)}{terminal} -> {texto_ref(r.para)}"
    if r.tipo == "aresta_juncao_aresta":
        return f"aresta_juncao_aresta {texto_ref(r.de)} via {texto_ref(r.via)} -> {texto_ref(r.para)}"
    return f"{r.tipo} {texto_ref(r.de)} -> {texto_ref(r.para)}"


SEM_REGRA = "a política padrão é 'sem regra = proibido'"


def avaliar_je(regras: list[Regra], juncao: Ref, aresta: Ref, terminal: str | None,
               feicoes: list[str]) -> tuple[Regra | None, Violacao | None]:
    """Junção-aresta: a junção (lado `de` da regra) recebe a ponta da aresta; o terminal é o DA JUNÇÃO naquela
    ponta (None = conexão sem terminal declarado). Terminal só casa com terminal igual: regra que pede 'alta'
    não autoriza conexão sem terminal nem com terminal 'baixa'."""
    candidatas = [r for r in regras
                  if r.tipo == "juncao_aresta" and r.de == juncao and r.para == aresta]
    for r in candidatas:
        if r.de_terminal == terminal:
            return r, None
    par = f"a junção {texto_ref(juncao)} e a aresta {texto_ref(aresta)}"
    if candidatas:
        terminais = ", ".join(repr(r.de_terminal) for r in candidatas)
        v = Violacao(
            "terminal_errado",
            f"conexão junção-aresta proibida entre {par} pelo terminal {terminal!r}: a regra deste par exige "
            f"terminal {terminais} ({texto_regra(candidatas[0])})",
            feicoes, [regra_json(r) for r in candidatas],
        )
    else:
        v = Violacao(
            "sem_regra",
            f"conexão junção-aresta proibida entre {par} pelo terminal {terminal!r}: nenhuma regra "
            f"juncao_aresta cobre este par; {SEM_REGRA}",
            feicoes,
        )
    return None, v


def avaliar_jj(regras: list[Regra], a: Ref, b: Ref, feicoes: list[str]) -> tuple[Regra | None, Violacao | None]:
    """Junção-junção (pontos coincidentes): par NÃO ordenado."""
    for r in regras:
        if r.tipo == "juncao_juncao" and {r.de, r.para} == {a, b}:
            return r, None
    return None, Violacao(
        "sem_regra",
        f"conexão junção-junção proibida entre {texto_ref(a)} e {texto_ref(b)}: nenhuma regra "
        f"juncao_juncao cobre este par; {SEM_REGRA}",
        feicoes,
    )


def avaliar_eje(regras: list[Regra], aresta_a: Ref, juncao: Ref, aresta_b: Ref,
                feicoes: list[str]) -> tuple[Regra | None, Violacao | None]:
    """Aresta-junção-aresta: duas arestas na MESMA junção; as pontas `de`/`para` da regra são não ordenadas,
    a junção do meio é o lado `via`."""
    for r in regras:
        if r.tipo == "aresta_juncao_aresta" and r.via == juncao and {r.de, r.para} == {aresta_a, aresta_b}:
            return r, None
    return None, Violacao(
        "sem_regra",
        f"passagem proibida pela junção {texto_ref(juncao)} entre as arestas {texto_ref(aresta_a)} e "
        f"{texto_ref(aresta_b)}: nenhuma regra aresta_juncao_aresta cobre esta combinação; {SEM_REGRA}",
        feicoes,
    )


def avaliar_associacao(regras: list[Regra], tipo: str, de: Ref, para: Ref,
                       feicoes: list[str]) -> tuple[Regra | None, Violacao | None]:
    """Contenção/estrutura: DIRECIONAL (de = recipiente/estrutura, para = conteúdo/anexado)."""
    for r in regras:
        if r.tipo == tipo and r.de == de and r.para == para:
            return r, None
    rotulo = "contenção" if tipo == "contencao" else "fixação estrutural"
    return None, Violacao(
        "sem_regra",
        f"associação de {rotulo} proibida de {texto_ref(de)} para {texto_ref(para)}: nenhuma regra "
        f"{tipo} cobre este par; {SEM_REGRA}",
        feicoes,
    )
