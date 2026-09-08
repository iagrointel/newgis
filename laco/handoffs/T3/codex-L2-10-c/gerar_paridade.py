"""Gera a seção 10 de docs/EXPRESSAO.md (paridade por função contra o Arcade function reference) e o
resumo por categoria para docs/PARIDADE.md. Lista de nomes do Arcade lida das páginas oficiais em
06/09/2026 (developers.arcgis.com/arcade/function-reference/<categoria>_functions/). Rodar com
`venv/bin/python gerar_paridade.py` a partir da raiz do repositório; imprime as duas seções."""

# (nome Arcade, equivalente nosso, estado, observação)
TEXTO = [
    ("Concatenate", "`Concatenar`", "feito", "nulo vira texto vazio, como no Arcade"),
    ("Count", "`Contagem`", "feito", "pontos de código, não unidades UTF-16"),
    ("Find", "`Find`", "feito", "índice em pontos de código; −1 se ausente"),
    ("FromCharCode", "—", "fora", ""),
    ("FromCodePoint", "—", "fora", ""),
    ("Guid", "—", "fora", "sem aleatoriedade: os dois avaliadores têm de dar o mesmo resultado"),
    ("Left", "`Left`", "feito", ""),
    ("Lower", "`Minuscula`", "feito", ""),
    ("Mid", "`Mid`", "feito", "sem quantidade vai até o fim"),
    ("Proper", "—", "fora", "regra de capitalização por locale ainda não escrita"),
    ("Replace", "`Replace`", "parcial", "sempre todas as ocorrências; o Arcade tem o 3º argumento `allReplacements`"),
    ("Right", "`Right`", "feito", ""),
    ("Split", "`Split`", "parcial", "sem `limit`/`removeEmpty`"),
    ("StandardizeFilename", "—", "fora", ""),
    ("StandardizeGuid", "—", "fora", ""),
    ("Text", "`Texto` · `TextoNumero` · `TextoData`", "parcial", "sem máscara livre (`#,###.00`, `DD/MM/Y`); pt-BR com casas e 4 formatos fixos de data, UTC"),
    ("ToCharCode", "—", "fora", ""),
    ("ToCodePoint", "—", "fora", ""),
    ("ToHex", "—", "fora", ""),
    ("Trim", "`Trim`", "parcial", "só espaço ASCII (espaço, tab, CR, LF, FF, VT); o Arcade também apara Unicode"),
    ("Upper", "`Maiuscula`", "feito", ""),
    ("UrlEncode", "—", "fora", ""),
]
MATEMATICA = [
    ("Abs", "`Absoluto`", "feito", ""),
    ("Acos", "—", "fora", ""), ("Asin", "—", "fora", ""), ("Atan", "—", "fora", ""), ("Atan2", "—", "fora", ""),
    ("Average", "`Media`", "parcial", "só lista; o Arcade aceita também argumentos soltos"),
    ("Ceil", "`Ceil`", "parcial", "sem 2º argumento de casas"),
    ("Constrain", "—", "fora", "`Minimo(Maximo(x, a), b)` faz o mesmo"),
    ("Cos", "—", "fora", ""),
    ("Exp", "—", "fora", ""),
    ("Floor", "`Floor`", "parcial", "sem 2º argumento de casas"),
    ("Hash", "—", "fora", ""),
    ("Log", "—", "fora", ""),
    ("Max", "`Maximo`", "parcial", "argumentos soltos; não aceita lista"),
    ("Mean", "`Media`", "parcial", "só lista"),
    ("Min", "`Minimo`", "parcial", "argumentos soltos; não aceita lista"),
    ("Number", "`Numero`", "parcial", "sem padrão de formato; texto inválido vira nulo, nunca NaN"),
    ("Pow", "`Potencia`", "feito", "|expoente| ≤ 1024, resultado finito"),
    ("Random", "—", "fora", "sem aleatoriedade (determinismo dos dois avaliadores)"),
    ("Round", "`Arredondar`", "feito", "meio-para-longe-de-zero, escrito à mão nos dois lados"),
    ("Sin", "—", "fora", ""),
    ("Sqrt", "`Sqrt`", "feito", "negativo é `numero_invalido`, não NaN"),
    ("Stdev", "—", "fora", ""),
    ("Sum", "`Soma`", "parcial", "só lista"),
    ("Tan", "—", "fora", ""),
    ("Variance", "—", "fora", ""),
]
DATA = [
    ("ChangeTimeZone", "—", "fora", "não há fuso: data é epoch-ms UTC"),
    ("Date", "—", "fora", "sem construtor; a data vem do contexto ou de `AgoraUTC`"),
    ("DateAdd", "aritmética", "parcial", "`$data + n * 86400000` soma dias; sem unidade mês/ano"),
    ("DateDiff", "`DiferencaDias`", "parcial", "só dias corridos completos"),
    ("DateOnly", "—", "fora", ""),
    ("Day", "`Dia`", "feito", "UTC"),
    ("Hour", "—", "fora", "`TextoData(x, 'data_hora')` exibe; não devolve o número"),
    ("ISOMonth", "—", "fora", ""), ("ISOWeek", "—", "fora", ""), ("ISOWeekday", "—", "fora", ""), ("ISOYear", "—", "fora", ""),
    ("Millisecond", "—", "fora", ""),
    ("Minute", "—", "fora", ""),
    ("Month", "`Mes`", "feito", "UTC, 1-12"),
    ("Now", "`AgoraUTC`", "feito", "sempre UTC"),
    ("Second", "—", "fora", ""),
    ("Time", "—", "fora", ""),
    ("Timestamp", "`AgoraUTC`", "feito", "é o `Now` em UTC"),
    ("TimeZone", "—", "fora", ""), ("TimeZoneOffset", "—", "fora", ""),
    ("ToLocal", "—", "fora", ""), ("ToUTC", "—", "fora", ""),
    ("Today", "aritmética", "parcial", "`Floor(AgoraUTC() / 86400000) * 86400000`"),
    ("Week", "—", "fora", ""),
    ("Weekday", "`Weekday`", "feito", "domingo 0 … sábado 6, UTC"),
    ("Year", "`Ano`", "feito", "UTC"),
]
LOGICA = [
    ("Boolean", "—", "fora", "sem conversão implícita para booleano"),
    ("Decode", "`Decode`", "feito", "igualdade estrutural; só o resultado escolhido é avaliado"),
    ("DefaultValue", "`SeNulo`", "parcial", "só nulo conta como vazio; texto vazio não"),
    ("Equals", "—", "fora", "identidade de geometria"),
    ("IIf", "`Se`", "feito", "condição booleana estrita; curto-circuito"),
    ("IsEmpty", "`EhNulo`", "parcial", "texto vazio não é vazio aqui"),
    ("IsNan", "—", "fora", "NaN não existe: vira `numero_invalido`"),
    ("TypeOf", "—", "fora", ""),
    ("When", "`Se` aninhado", "parcial", "sem forma plana `When(c1, r1, c2, r2, padrao)`"),
]
LISTA = [
    ("All", "—", "fora", "sem função por elemento"),
    ("Any", "—", "fora", "sem função por elemento"),
    ("Array", "`Lista`", "parcial", "cria com valores; não cria por tamanho"),
    ("Back", "`Ultimo`", "feito", ""),
    ("Count", "`Contagem`", "feito", ""),
    ("DefaultValue", "`Obter(lista, i, padrao)`", "parcial", "por índice, não pela lista inteira"),
    ("Distinct", "`Unicos`", "feito", "igualdade estrutural, primeira ocorrência"),
    ("Erase", "—", "fora", "listas são imutáveis"),
    ("Filter", "—", "fora", "sem função por elemento (pendência nomeada do item)"),
    ("First", "`Primeiro`", "feito", ""),
    ("Front", "`Primeiro`", "feito", ""),
    ("HasValue", "`Obter(lista, i, sentinela)`", "parcial", "no Arcade é \"tem valor no índice i\", não pertinência; sem sentinela, índice presente com nulo não se distingue de ausente"),
    ("Includes", "`Contem`", "feito", "igualdade estrutural estrita"),
    ("IndexOf", "—", "fora", ""),
    ("Insert", "—", "fora", "imutável"),
    ("Map", "—", "fora", "sem função por elemento (pendência nomeada do item)"),
    ("None", "—", "fora", ""),
    ("Pop", "—", "fora", "imutável"),
    ("Push", "—", "fora", "imutável"),
    ("Reduce", "—", "fora", ""),
    ("Resize", "—", "fora", "imutável"),
    ("Reverse", "`Reverter`", "feito", "devolve cópia"),
    ("Slice", "—", "fora", ""),
    ("Sort", "—", "fora", ""),
    ("Splice", "—", "fora", ""),
    ("Top", "—", "fora", ""),
]
DICIONARIO = [
    ("Count", "`Contagem`", "feito", "chaves próprias"),
    ("DefaultValue", "`Obter(dic, chave, padrao)`", "feito", ""),
    ("Dictionary", "—", "fora", "sem construtor; dicionário vem do contexto"),
    ("Erase", "—", "fora", "imutável"),
    ("FromJSON", "—", "fora", ""),
    ("GetKeys", "—", "fora", ""),
    ("GetValues", "—", "fora", ""),
    ("HasKey", "`Obter` com padrão sentinela", "parcial", "chave presente com valor nulo é indistinguível de ausente sem sentinela"),
    ("HasValue", "—", "fora", ""),
    ("Insert", "—", "fora", "imutável"),
]
FEICAO = [
    ("DefaultValue", "`SeNulo`/`Obter`", "parcial", ""),
    ("Domain", "—", "fora", "domínio é do L2-10 cheio"),
    ("DomainCode", "—", "fora", "idem"),
    ("DomainName", "—", "fora", "idem"),
    ("Expects", "—", "fora", ""),
    ("Feature", "—", "fora", ""),
    ("FeatureInFilter", "—", "fora", ""),
    ("GdbVersion", "—", "fora", ""),
    ("HasKey", "`Obter`", "parcial", ""),
    ("HasValue", "—", "fora", ""),
    ("Schema", "—", "fora", ""),
    ("SubtypeCode", "—", "fora", "subtipo é do L2-10 cheio"),
    ("SubtypeName", "—", "fora", "idem"),
    ("Subtypes", "—", "fora", "idem"),
    ("TimeReceived", "—", "fora", ""),
]
FORA_INTEIRAS = [
    ("FeatureSet", 43, "Area, AreaGeodetic, Attachments, Average, Contains, Count, Crosses, Distinct, Domain, DomainCode, DomainName, EnvelopeIntersects, Expects, FeatureSet, FeatureSetByAssociation, FeatureSetById, FeatureSetByName, FeatureSetByRelationshipClass, FeatureSetByRelationshipName, Filter, FilterBySubtypeCode, First, GdbVersion, GetFeatureSet, GetFeatureSetInfo, GetUser, GroupBy, Intersects, Length, Length3D, LengthGeodetic, Max, Mean, Min, OrderBy, Overlaps, Schema, Stdev, Subtypes, Sum, Top, Touches, Variance, Within", "não há camada ligada à expressão ainda (L2-10 cheio; `FeatureSetByRelationship` com limite é pendência nomeada)"),
    ("Geometria", 55, "Angle, Area, AreaGeodetic, Bearing, Buffer, BufferGeodetic, Centroid, Clip, Contains, ConvertDirection, ConvexHull, Crosses, Cut, DefaultValue, Densify, DensifyGeodetic, Difference, Disjoint, Distance, DistanceGeodetic, DistanceToCoordinate, EnvelopeIntersects, Equals, Extent, Generalize, Geometry, HasValue, Intersection, Intersects, IsSelfIntersecting, IsSimple, Length, Length3D, LengthGeodetic, MeasureToCoordinate, MultiPartToSinglePart, Multipoint, NearestCoordinate, NearestVertex, Offset, Overlaps, Point, PointToCoordinate, Polygon, Polyline, Relate, RingIsClockwise, Rotate, SetGeometry, Simplify, SymmetricDifference, Touches, Union, Within", "geometria via PostGIS (servidor) / fórmula esférica (cliente) é pendência nomeada"),
    ("IA", 1, "TranslateText", "chama serviço externo — a linguagem é sem rede por construção"),
    ("Depuração", 2, "Console, GetEnvironment", ""),
    ("Empresa", 1, "NextSequenceValue", "depende de banco"),
    ("Grafo de conhecimento", 2, "KnowledgeGraphByPortalItem, QueryGraph", "produto que não existe na pilha"),
    ("Pixel", 6, "Count, DefaultValue, GetKeys, GetValues, HasKey, HasValue", "perfil raster"),
    ("Portal", 3, "FeatureSetByPortalItem, GetUser, Portal", "sem rede; `$usuario` do contexto cobre o `GetUser` quando o L5-11 ligar"),
    ("Trajetória", 16, "TrackAccelerationAt, TrackAccelerationWindow, TrackCurrentAcceleration, TrackCurrentDistance, TrackCurrentSpeed, TrackCurrentTime, TrackDistanceAt, TrackDistanceWindow, TrackDuration, TrackFieldWindow, TrackGeometryWindow, TrackIndex, TrackSpeedAt, TrackSpeedWindow, TrackStartTime, TrackWindow", "perfil de rastreamento"),
    ("Voxel", 6, "Count, DefaultValue, GetKeys, GetValues, HasKey, HasValue", "perfil voxel"),
]
CATEGORIAS = [("Texto", TEXTO), ("Matemática", MATEMATICA), ("Data", DATA), ("Lógica", LOGICA), ("Lista", LISTA),
              ("Dicionário", DICIONARIO), ("Feição", FEICAO)]


def contar(linhas):
    return {e: sum(1 for _, _, est, _ in linhas if est == e) for e in ("feito", "parcial", "fora")}


def secao_expressao():
    out = ["## 10. Paridade com o Arcade function reference, função por função", ""]
    total = {"feito": 0, "parcial": 0, "fora": 0}
    n_fora_inteiras = sum(n for _, n, _, _ in FORA_INTEIRAS)
    for nome, linhas in CATEGORIAS:
        c = contar(linhas)
        for k in total:
            total[k] += c[k]
    tot_arcade = sum(total.values()) + n_fora_inteiras
    out.append(
        f"Lista de nomes lida das páginas oficiais (`developers.arcgis.com/arcade/function-reference/`) em setembro de "
        f"2026: **{tot_arcade} funções em 17 categorias**. Estado por função: **feito** = mesma semântica para os "
        f"casos que os vetores cobrem; **parcial** = existe com assinatura ou regra mais estreita (dito na "
        f"observação); **fora** = não existe. Nas {len(CATEGORIAS)} categorias com correspondência: "
        f"**{total['feito']} feito · {total['parcial']} parcial · {total['fora']} fora** de "
        f"{sum(total.values())}; as outras 10 categorias ({n_fora_inteiras} funções) ficam inteiras de fora, com o "
        f"motivo. O nome nosso é sempre outro (português): paridade aqui é de CAPACIDADE, nunca promessa de rodar "
        f"um script Arcade sem adaptação. Gerado por `laco/handoffs/T3/codex-L2-10-c/gerar_paridade.py`."
    )
    out.append("")
    for nome, linhas in CATEGORIAS:
        c = contar(linhas)
        out.append(f"### {nome} ({c['feito']} feito · {c['parcial']} parcial · {c['fora']} fora)")
        out.append("")
        out.append("| Arcade | nós | estado | observação |")
        out.append("|---|---|---|---|")
        for arcade, nosso, estado, obs in linhas:
            out.append(f"| {arcade} | {nosso} | {estado} | {obs} |")
        out.append("")
    out.append("### Categorias inteiras de fora")
    out.append("")
    out.append("| categoria (Arcade) | funções | motivo |")
    out.append("|---|---|---|")
    for cat, n, nomes, motivo in FORA_INTEIRAS:
        out.append(f"| {cat} ({n}) | {nomes} | {motivo} |")
    out.append("")
    return "\n".join(out), total, n_fora_inteiras, tot_arcade


def secao_paridade_md():
    texto, total, n_fora, tot = secao_expressao()
    linhas = ["| capacidade | Esri | nós | estado | testado por | data | Pro/AGOL real |", "|---|---|---|---|---|---|---|"]
    for nome, dados in CATEGORIAS:
        c = contar(dados)
        feitos = ", ".join(f"`{n}`" for n, _, e, _ in dados if e == "feito")
        parciais = ", ".join(f"`{n}`" for n, _, e, _ in dados if e == "parcial")
        estado = "feito" if c["fora"] == 0 and c["parcial"] == 0 else "parcial"
        linhas.append(
            f"| funções de {nome.lower()} | {len(dados)} funções na referência | feito: {feitos or '—'}; parcial: "
            f"{parciais or '—'} (equivalentes em português, tabela por função em `docs/EXPRESSAO.md` seção 10) | "
            f"{estado} ({c['feito']} feito · {c['parcial']} parcial · {c['fora']} fora) | equivalência Python × JavaScript "
            f"byte a byte em `test_expressao_equivalencia.py` (vetores compartilhados) | 2026-09-06 | pendente (D20) |"
        )
    return "\n".join(linhas), total, n_fora, tot


if __name__ == "__main__":
    texto, total, n_fora, tot = secao_expressao()
    print(texto)
    print("=====PARIDADE.md")
    print(secao_paridade_md()[0])
    print("=====TOTAIS", total, n_fora, tot)
