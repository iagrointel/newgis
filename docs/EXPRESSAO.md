# Linguagem de expressão própria (item `L2-10-c-linguagem-expressao`)

Estado: NÚCLEO entregue (turno 3) — o equivalente ao Arcade da Esri, para os perfis popup, rótulo,
cálculo, restrição, validação, visibilidade e indicador (L2_CONCEITO.md, decisão C6). Esta passagem
constrói só a linguagem: gramática, AST tipada e os dois avaliadores (Python e JavaScript), que têm
de concordar byte a byte. A integração com popup, rótulo, formulário e regra de atributo é de itens
futuros do L2-10 e do L5 (`L5-11`, citado como "ativo da casa" no item) — nada abaixo liga a
expressão a uma camada, um popup ou uma regra de formulário de verdade.

Implementações: `app/expressao/avaliador_py.py` (Python, servidor) e
`web/js/expressao/avaliador.js` (JavaScript puro, navegador). Nenhuma das duas usa `eval`/`exec`/
`compile`/`Function`/`new Function` — o analisador é escrito à mão, recursivo descendente, no
mesmo padrão de `app/consulta/where_ast.py` (que resolve o `where` de filtro, mais simples que
esta linguagem: aqui há aritmética, funções e condicional). Vetores de teste compartilhados entre
os dois avaliadores: `tests/expressoes/vetores.json` (≥ 200 casos, incluindo coleções e Unicode); a prova de equivalência está em
`tests/unit/test_expressao_equivalencia.py`.

## 1. Visão geral da gramática (EBNF)

```ebnf
expressao     = ou ;
ou            = "e" , { "||" , "e" } ;
e             = igualdade , { "&&" , igualdade } ;
igualdade     = comparacao , { ( "==" | "!=" ) , comparacao } ;
comparacao    = aditiva , { ( "<=" | ">=" | "<" | ">" ) , aditiva } ;
aditiva       = multiplicativa , { ( "+" | "-" ) , multiplicativa } ;
multiplicativa= potencia , { ( "*" | "/" | "%" ) , potencia } ;
potencia      = unario , [ "^" , potencia ] ;              (* associa à direita *)
unario        = ( "-" | "!" ) , unario | primario ;
primario      = numero | string | "verdadeiro" | "falso" | "nulo"
              | campo
              | identificador , "(" , [ expressao , { "," , expressao } ] , ")"
              | "(" , expressao , ")" ;

campo          = "$" , identificador ;
identificador  = ( letra | "_" ) , { letra | digito | "_" } ;
numero         = digitos , [ "." , digitos ] | "." , digitos ;
string         = "'" , { qualquer_caractere_exceto_aspa_simples | "''" } , "'" ;
```

Precedência, do menor para o maior (a tabela acima já reflete isto na ordem das regras): `||`,
depois `&&`, depois `==`/`!=`, depois `<`/`<=`/`>`/`>=`, depois `+`/`-`, depois `*`/`/`/`%`, depois
`^` (potência, associa à direita: `2^3^2` é `2^(3^2)` = 512, não `(2^3)^2` = 64), depois unário
(`-`, `!`), depois primário. Parênteses mudam a ordem normalmente.

Palavras-chave reservadas (minúsculas ou não, comparadas sem diferenciar caixa no tokenizador):
`verdadeiro`, `falso`, `nulo`. Nomes de função e de campo diferenciam maiúscula de minúscula.

### Exemplo completo

```
Se(EhNulo($vencimento), 'sem data', Concatenar('vence em ', Texto(DiferencaDias($hoje, $vencimento)), ' dias'))
```

com `contexto = {"hoje": 1788652800000, "vencimento": 1791244800000}` avalia para
`"vence em 30 dias"` — igual nos dois avaliadores (é o último vetor de
`tests/expressoes/vetores.json`).

## 2. Tipos do núcleo

| tipo | representação Python | representação JavaScript | literal |
|---|---|---|---|
| número | `int` ou `float` | `number` | `42`, `3.14`, `-7`, `.5` |
| texto | `str` | `string` | `'texto'` (aspa simples dobrada `''` escapa uma aspa) |
| booleano | `bool` | `boolean` | `verdadeiro`, `falso` |
| nulo | `None` | `null`/`undefined` tratados igual | `nulo` |
| **data** | **convenção**: número = milissegundos desde a época Unix (1970-01-01T00:00:00Z), sempre UTC | idem | não há literal de data; vem de `AgoraUTC()` ou de um campo do contexto |

Listas e dicionários JSON também são valores. Listas são criadas por `Lista`/`Split` ou recebidas
pelo contexto. Dicionários vêm do contexto autorizado e são lidos por `Obter`; a gramática não
introduz literais `[]`/`{}`. As coleções aceitam aninhamento dentro dos limites da seção 7.
A igualdade nas funções `Contem`, `Unicos` e `Decode` é estrutural: ordem de lista importa,
ordem de chaves de dicionário não, e booleano é diferente de número.

Geometria, domínio, relações entre camadas e funções com expressão por elemento (`Filter`/`Map`)
continuam fora do núcleo. O contexto só deve conter dados já autorizados pelo chamador.

Por que "data" não é um tipo dedicado: os dois avaliadores têm de concordar byte a byte, e a forma
mais barata de garantir isso é não depender de biblioteca de fuso horário nenhuma das duas línguas
— milissegundos UTC são um número puro, comparável e formatável identicamente nos dois lados. A
exibição em fuso do usuário (a hipótese cheia do item pede "data com fuso") é decisão de
formulário/popup, de outro item.

## 3. Regras de nulo (propagação de três valores, como SQL)

- **Aritmética** (`+ - * / % ^` e o unário `-`): se qualquer operando é `nulo`, o resultado é
  `nulo`. Divisão e resto por zero são erro nomeado (`divisao_por_zero`), nunca confundido com nulo.
- **Igualdade** (`==`/`!=`): `nulo == nulo` é `verdadeiro`; `nulo` comparado com qualquer valor
  não-nulo é sempre `falso` (para `==`) ou `verdadeiro` (para `!=`) — NUNCA lança erro nem
  propaga nulo. Comparar tipos diferentes (número com texto, por exemplo) nunca é `verdadeiro`.
- **Comparação de ordem** (`< <= > >=`): se qualquer operando é `nulo`, o resultado é `nulo`
  (propaga — não decide `verdadeiro` nem `falso` sozinho). Comparar número com texto (ou qualquer
  combinação que não seja número×número ou texto×texto) é `tipo_invalido`.
- **Lógicos** (`&& || !`): semântica de três valores do SQL. Um `falso` em qualquer lado do `&&`
  decide o resultado como `falso`, mesmo que o outro lado seja `nulo` (curto-circuito: o lado que
  decide sozinho evita avaliar o outro). Um `verdadeiro` em qualquer lado do `||` decide
  `verdadeiro` do mesmo jeito. Fora esses casos, se um dos lados é `nulo`, o resultado é `nulo`.
  `!nulo` é `nulo`. Operando que não é booleano nem nulo em `&&`/`||`/`!` é `tipo_invalido`.
- **Texto**: `Concatenar` trata `nulo` como texto vazio (decisão de conveniência, documentada aqui
  — é a única função que faz isso). `Texto(nulo)` devolve `""`. Toda outra função de texto/número
  que receber `nulo` onde espera um valor concreto propaga `nulo` (ex.: `Arredondar(nulo)` → `nulo`)
  — EXCETO `SeNulo` e `EhNulo`, que existem exatamente para tratar nulo.

### 3.1 Convenções fixadas (o que a língua hospedeira decidiria sozinha, e aqui não decide)

Toda operação que os dois avaliadores entregassem ao operador ou à biblioteca da língua divergiria:
o Python e o JavaScript não concordam em resto de divisão, em unidade de texto, em algarismo e em
arredondamento de data. As quatro convenções abaixo são do CONTRATO, estão escritas à mão nos dois
lados e têm vetor de teste em `tests/expressoes/vetores_convergencia.json`.

1. **Resto (`%`) tem o sinal do DIVIDENDO** (resto truncado, como no JavaScript, no C e no SQL), não
   o sinal do divisor (que é o que o `%` do Python daria). `(0-7) % 3` é `-1`, `7 % (0-3)` é `1`,
   `(0-0.5) % 2` é `-0.5`. O lado Python usa `math.fmod`, nunca o operador `%` da língua.
2. **Texto é medido, cortado, comparado e casado em PONTO DE CÓDIGO**, e um par substituto alto+baixo
   conta como UM ponto de código, mesmo quando chega ao contexto como duas metades soltas (é a regra
   do UTF-16, que o `String` do JavaScript aplica sozinho e o `str` do Python não). Vale para
   `Contagem`, `Left`, `Mid`, `Right`, `Find`, `Split`, `Replace` e para a ordem `< <= > >=` entre
   textos: emoji vem DEPOIS de `U+E000`–`U+FFFF`, e nenhuma busca casa meia-substituta. O lado Python
   normaliza o texto (`_texto_pareado`); o lado JavaScript compara e corta por ponto de código, nunca
   por unidade UTF-16 (`compararTexto`, `acharAlinhado`, `dividirAlinhado`).
3. **`Numero` aceita só algarismo ASCII `0`–`9`.** `Numero('٤٢')` (algarismo arábico-índico) é `nulo`,
   como qualquer texto que não seja número. O `\d` do Python casaria dígito decimal de qualquer
   escrita e o do JavaScript não.
4. **Data arredonda SEMPRE para baixo.** `Ano`, `Mes`, `Dia`, `Weekday`, `TextoData` e `DiferencaDias`
   aplicam `floor` ao milissegundo antes de qualquer conta, então `Ano(0-0.5)` é `1969` nos dois lados
   (o `timedelta` do Python arredondaria ao microssegundo mais próximo e o `new Date` truncaria para
   zero, que é o que dava `1969` de um lado e `1970` do outro).

## 4. Curto-circuito (o ramo não avaliado não roda)

- **`Se(condicao, entao, senao)`**: `condicao` tem de avaliar para booleano estrito (`nulo` ou
  qualquer outro tipo é `tipo_invalido` — não há regra implícita de "nulo vira falso" aqui, ao
  contrário dos operadores lógicos). Só o ramo escolhido é avaliado; o outro nunca roda, mesmo que
  contenha um erro (`Se($x > 0, 1, 10 / 0)` com `$x = 5` devolve `1` sem nunca calcular `10 / 0`).
- **`SeNulo(valor, alternativa)`**: se `valor` é `nulo`, avalia e devolve `alternativa`; senão
  devolve `valor` sem nunca avaliar `alternativa`.
- **`&&`/`||`**: como descrito acima — o lado que decide sozinho evita avaliar o outro.

## 5. Catálogo de funções (49)

Uma linha por função, com 1 exemplo. `TABELA_FUNCOES` em `avaliador_py.py` e `TABELA_FUNCOES` em
`avaliador.js` são a fonte única — `tests/unit/test_expressao_doc_sincronizada.py` confere que
TODA função aqui existe nos dois avaliadores e vice-versa.

### Texto

| função | aridade | descrição | exemplo |
|---|---|---|---|
| `Maiuscula(texto)` | 1 | converte para maiúsculas | `Maiuscula('sítio')` → `'SÍTIO'` |
| `Minuscula(texto)` | 1 | converte para minúsculas | `Minuscula('SÍTIO')` → `'sítio'` |
| `Concatenar(a, b, ...)` | 1+ | junta 2+ valores como texto (nulo vira texto vazio) | `Concatenar('lote ', 12)` → `'lote 12'` |
| `Texto(valor)` | 1 | converte número/booleano/nulo para texto | `Texto(3.5)` → `'3.5'` |

### Número

| função | aridade | descrição | exemplo |
|---|---|---|---|
| `Arredondar(numero, casas=0)` | 1-2 | arredonda para N casas, meio-para-longe-de-zero | `Arredondar(2.345, 2)` → `2.35` |
| `Absoluto(numero)` | 1 | valor absoluto | `Absoluto(-4)` → `4` |
| `Minimo(a, b, ...)` | 1+ | menor valor | `Minimo(4, 1, 9)` → `1` |
| `Maximo(a, b, ...)` | 1+ | maior valor | `Maximo(4, 1, 9)` → `9` |
| `Numero(valor)` | 1 | converte texto/booleano para número (`nulo` se não for número válido) | `Numero('42')` → `42` |
| `Potencia(base, expoente)` | 2 | base elevada ao expoente | `Potencia(2, 10)` → `1024` |

### Data (convenção: milissegundos desde a época Unix, UTC)

| função | aridade | descrição | exemplo |
|---|---|---|---|
| `AgoraUTC()` | 0 | instante atual, milissegundos UTC | `AgoraUTC()` → `1788652800000` |
| `Ano(data)` | 1 | ano civil UTC | `Ano(1788652800000)` → `2026` |
| `Mes(data)` | 1 | mês civil UTC (1-12) | `Mes(1788652800000)` → `9` |
| `Dia(data)` | 1 | dia do mês civil UTC (1-31) | `Dia(1798675200000)` → `31` |
| `DiferencaDias(data1, data2)` | 2 | dias corridos completos entre duas datas (`data2 − data1`) | `DiferencaDias(a, b)` → `30` |

### Nulo

| função | aridade | descrição | exemplo |
|---|---|---|---|
| `SeNulo(valor, alternativa)` | 2 | se `valor` é nulo, avalia e devolve `alternativa` (curto-circuito) | `SeNulo($x, 0)` → `0` se `$x` é nulo |
| `EhNulo(valor)` | 1 | verdadeiro se o argumento é nulo | `EhNulo($x)` → `falso` |

### Condicional

| função | aridade | descrição | exemplo |
|---|---|---|---|
| `Se(condicao, entao, senao)` | 3 | condição booleana decide qual ramo é avaliado (curto-circuito) | `Se($area > 300, 'grande', 'pequena')` |

### Texto, número, data e escolha adicionados

Índices de texto contam pontos de código Unicode, começando em zero; contagens e índices devem
ser inteiros não negativos. As funções novas exigem os tipos declarados, sem conversão implícita.

| função | aridade | descrição | exemplo |
|---|---|---|---|
| `Trim(texto)` | 1 | remove espaços ASCII das pontas (espaço, tabulação, CR, LF, FF, VT) | `Trim(' a ')` → `'a'` |
| `Left(texto, quantidade)` | 2 | primeiros pontos de código | `Left('a🌍b', 2)` → `'a🌍'` |
| `Right(texto, quantidade)` | 2 | últimos pontos de código; zero devolve vazio | `Right('abc', 1)` → `'c'` |
| `Mid(texto, inicio, quantidade)` | 2-3 | trecho; sem quantidade, vai até o fim | `Mid('abcd', 1, 2)` → `'bc'` |
| `Find(busca, texto, inicio)` | 2-3 | índice da primeira ocorrência; início padrão zero, ausente retorna -1 | `Find('b', 'abc')` → `1` |
| `Split(texto, separador)` | 2 | divisão literal; separador vazio divide pontos de código | `Split('a,b', ',')` → lista com `'a'`, `'b'` |
| `Replace(texto, busca, novo)` | 3 | troca todas as ocorrências literais; busca vazia preserva texto | `Replace('aba', 'a', 'x')` → `'xbx'` |
| `Floor(numero)` | 1 | inteiro inferior | `Floor(-1.5)` → `-2` |
| `Ceil(numero)` | 1 | inteiro superior | `Ceil(-1.5)` → `-1` |
| `Sqrt(numero)` | 1 | raiz quadrada; negativo é erro | `Sqrt(9)` → `3` |
| `Weekday(data)` | 1 | dia UTC, domingo 0 a sábado 6, anos 1–9999 | `Weekday(0)` → `4` |
| `Decode(valor, caso, resultado, padrao)` | 4+ par | pares caso/resultado e padrão obrigatório; só avalia resultado escolhido | `Decode(1, 1, 'sim', 'não')` → `'sim'` |

### Coleções

| função | aridade | descrição | exemplo |
|---|---|---|---|
| `Lista(valores)` | 0-64 | lista nova, preserva nulos | `Lista(1, nulo)` |
| `Contagem(valor)` | 1 | tamanho de lista, texto ou dicionário | `Contagem(Lista(1, 2))` → `2` |
| `Primeiro(lista)` | 1 | primeiro elemento; vazio retorna nulo | `Primeiro(Lista(4, 5))` → `4` |
| `Ultimo(lista)` | 1 | último elemento; vazio retorna nulo | `Ultimo(Lista(4, 5))` → `5` |
| `Obter(colecao, chave, padrao)` | 2-3 | lista por índice ou dicionário por chave própria; ausência retorna padrão/nulo | `Obter(Lista(4), 0)` → `4` |
| `Contem(lista, valor)` | 2 | presença por igualdade estrutural estrita | `Contem(Lista(1), verdadeiro)` → `falso` |
| `Soma(lista)` | 1 | soma de números, lista vazia retorna zero; membro nulo propaga nulo | `Soma(Lista(1, 2))` → `3` |
| `Media(lista)` | 1 | média de números; lista vazia ou membro nulo retorna nulo | `Media(Lista(1, 2))` → `1.5` |
| `Reverter(lista)` | 1 | cópia com ordem invertida | `Reverter(Lista(1, 2))` |
| `Unicos(lista)` | 1 | remove repetições preservando primeira ocorrência | `Unicos(Lista(1, 1))` |
| `Juntar(lista, separador)` | 1-2 | texto de valores escalares, nulo vira vazio; separador padrão vazio | `Juntar(Lista(1, 2), '/')` → `'1/2'` |

### Formatação em pt-BR (número e data)

Formatação escrita à mão nos dois avaliadores, sem `Intl`, sem `locale` e sem biblioteca de
internacionalização: os dois lados têm de produzir o MESMO texto byte a byte (seção 6). A data
continua sendo milissegundos UTC — não há fuso do usuário nesta passagem.

| função | aridade | descrição | exemplo |
|---|---|---|---|
| `TextoNumero(numero, casas)` | 1-2 | número em pt-BR: milhar `.`, decimal `,`, N casas inteiras de 0 a 15 (padrão 2); empate arredonda para longe de zero; zero nunca leva sinal | `TextoNumero(1234.5)` → `'1.234,50'` |
| `TextoData(data, formato)` | 1-2 | data UTC em pt-BR; formato `'data'` (padrão), `'data_hora'`, `'data_hora_segundos'` ou `'extenso'`; anos 1–9999 | `TextoData(0)` → `'01/01/1970'`; `TextoData(0, 'extenso')` → `'1 de janeiro de 1970'` |

Casas fora de 0–15, valor com módulo ≥ 10²¹ ou data fora da faixa de anos são `numero_invalido`;
casas não inteira ou formato fora da lista são `tipo_invalido`.

As funções novas propagam argumento nulo, exceto `Lista`, `Obter`, `Contem` e `Decode`.
`Obter` avalia o padrão antecipadamente e o usa apenas quando a chave está ausente ou a coleção
é nula; uma chave presente com valor nulo permanece nula. `Contem` admite valor buscado nulo.
`Decode` compara casos em ordem e ignora resultados dos casos não escolhidos, além dos casos
posteriores à primeira correspondência. Não modifica o contexto. As chaves `__proto__`,
`prototype` e `constructor` são recusadas por `Obter`; getters e propriedades herdadas não
são caminhos de acesso a dados.

### Feição e geometria (item L5-11)

A feição é o dicionário `{"atributos": {...}, "geometria": ...}` e chega às expressões como
`$feicao`; `$geometria` é a geometria dela e cada atributo cujo nome é um identificador válido
chega como `$nome` (quem monta isso é `app/expressao/perfis.py` / `web/js/expressao/perfis.js`,
seção 12). Geometria é GeoJSON (RFC 7946) com as chaves do próprio padrão — `{"type": "Point" |
"LineString" | "Polygon", "coordinates": ...}` —, grau decimal em WGS-84 e longitude ANTES da
latitude. Coordenada fora de −180..180 / −90..90, anel de polígono que não fecha, anel com menos
de quatro posições, tipo de geometria diferente do que a função pede e dicionário que não é
geometria dão `geometria_invalida`.

| função | aridade | descrição | exemplo |
|---|---|---|---|
| `Atributo(feicao, nome, padrao)` | 2-3 | atributo por nome; ausente devolve o padrão (ou nulo); presente com valor nulo permanece nulo; `__proto__`/`prototype`/`constructor` são `campo_nao_permitido` | `Atributo($feicao, 'nome do lote')` → `'L-7'` |
| `Geometria(feicao)` | 1 | geometria da feição, ou nulo se ela não tiver | `EhNulo(Geometria($feicao))` → `falso` |
| `Area(poligono)` | 1 | área do polígono em metros quadrados, descontando os anéis internos | `Area($geometria)` → `12363718145.180046` |
| `Comprimento(linha)` | 1 | comprimento da linha em metros (soma dos segmentos) | `Comprimento($geometria)` → `111195.080234` |
| `Distancia(ponto, ponto)` | 2 | distância entre dois pontos em metros | `Distancia($a, $b)` → `111195.080234` |
| `Dentro(ponto, poligono)` | 2 | verdadeiro se o ponto está dentro do polígono | `Dentro($p, $geometria)` → `verdadeiro` |

**Modelo da Terra, e o que ele NÃO é.** Esfera de raio autálico 6.371.008,8 m (IUGG), sem
elipsoide, sem projeção e sem PostGIS: área pela fórmula de Chamberlain & Duquette
(`A = R²/2 · Σ (λ₂−λ₁)(sin φ₁ + sin φ₂)`, o sinal do anel dá a orientação e o resultado é o módulo
do anel externo menos o módulo de cada anel interno), comprimento e distância por haversine,
`Dentro` por cruzamento de raio par-ímpar no plano de graus. O erro do modelo esférico chega a
0,5 % contra o elipsoide — serve para ordem de grandeza e comparação, nunca para medição legal de
área. Todo resultado métrico é arredondado a 6 casas decimais (1 micrômetro quando a unidade é
metro) porque `sin`/`cos`/`asin` da biblioteca matemática do Python e do V8 podem divergir no
último bit e o portão exige o MESMO número nos dois lados.

**Bordas, e a assimetria que existe de propósito.** Ponto sobre a aresta ou sobre um vértice do
anel EXTERNO conta como dentro; ponto sobre a borda de um anel interno (buraco) conta como fora.
Não há tolerância: a comparação é exata em ponto flutuante. `Dentro` não cruza o antimeridiano nem
trata polígono que contém um polo — polígono assim tem de ser partido antes.

**Fora desta passagem** (nomeado, não escondido): `MultiPoint`/`MultiLineString`/`MultiPolygon`/
`GeometryCollection`, `Buffer`, `Centroide`, `Interseta`, `Toca`, distância de ponto a linha ou a
polígono, área de linha, comprimento de polígono (perímetro) e qualquer sistema de coordenadas que
não seja grau decimal WGS-84.

## 6. Algoritmos que têm de ser IDÊNTICOS nos dois avaliadores

Números de ponto flutuante e formatação são onde Python e JavaScript mais divergem por padrão
(`round()` do Python é banker's rounding; `toFixed`/`String(numero)` do JavaScript não distinguem
inteiro de decimal como `json.dumps` do Python). Por isso três algoritmos são escritos À MÃO, iguais
nos dois lados, em vez de usar a função pronta de cada língua:

1. **Formatação de número → texto** (`_formatar_numero`/`formatarNumero`): se o número não tem
   parte fracionária, vira texto sem ponto (`3.0` → `'3'`); senão, até 6 casas decimais sem zero à
   direita (`3.5` → `'3.5'`, nunca `'3.500000'`).
2. **Arredondamento** (`_arredondar`/`arredondarNumero`): meio-para-longe-de-zero —
   `piso(x·10^casas + 0,5) / 10^casas` para `x ≥ 0`, `teto(x·10^casas − 0,5) / 10^casas` para
   `x < 0`. NÃO é o `round()` do Python (banker's) nem o `Math.round` do JavaScript (arredonda
   para +∞ em negativos) — os dois avaliadores implementam esta fórmula, não a função nativa.
3. **Conversão texto → número** (`Numero`): regex `^-?\d+$` vira inteiro, `^-?\d+\.\d+$` vira
   decimal; qualquer outro texto vira `nulo` (nunca `NaN` — `NaN` não compara de forma previsível
   entre as duas línguas).

## 7. Limites (negação de serviço — refutação do item-pai)

| limite | valor | onde age | erro nomeado |
|---|---|---|---|
| tamanho do texto bruto | 20.000 caracteres | antes de tokenizar (um literal de 10 MB nunca chega ao tokenizador) | `expressao_grande` |
| tokens | 2.000 | depois de tokenizar | `expressao_grande` |
| profundidade de aninhamento | 60 níveis | o PARSER conta a cada `(`/unário/chamada ANTES de descer (nunca deixa a própria pilha do Python/JS estourar); depois de montada, a árvore inteira é medida de novo com pilha explícita — cobre a cadeia longa do mesmo operador (`1+1+1+...`), que o parser constrói em laço, não em recursão | `profundidade_excedida` |
| argumentos por chamada | 64 | ao ler `,` dentro de `(...)` | `expressao_grande` |
| passos de avaliação | 10⁵ (padrão; o chamador pode passar outro) | a cada nó visitado pelo avaliador | `limite_passos` |
| tempo de avaliação | 500 ms servidor / 50 ms cliente (padrão; o chamador pode passar outro) | conferido a cada passo, inclusive em operações de coleção | `tempo_excedido` |

Limites de valores e operações, aplicados também aos resultados intermediários:

| limite | valor | erro |
|---|---|---|
| elementos por coleção | 1.024 | `valor_grande` |
| nós agregados por valor | 4.096 | `valor_grande` |
| texto acumulado por valor | 20.000 pontos de código | `valor_grande` |
| profundidade de valor | 20 | `valor_grande` |
| nós de AST importada | 2.000 | `expressao_grande` |
| módulo do expoente | 1.024 | `numero_invalido` |
| casas de arredondamento | -15 a 15 | `numero_invalido` |

Cada visita a valor ou operação de coleção consome passos. Números devem ser finitos;
potência inválida, estouro numérico e raiz negativa são `numero_invalido`. Valores cíclicos,
objetos não JSON ou acessores são recusados. Limites de entrada e saída complementam o relógio:
uma única chamada também precisa ter trabalho limitado.

`ast_de_json` (reimportação de uma AST gravada) aplica os MESMOS limites de profundidade e
aridade que `analisar` aplica ao texto — uma AST em JSON é entrada tão não confiável quanto o
texto (é o que se grava no documento, C6 do L2_CONCEITO.md), e nada garante que veio de
`ast_para_json`; sem essa conferência, um JSON fabricado à mão contornaria os dois guarda-corpos
do lado texto por inteiro.

`$campo` fora do `contexto` que o chamador passou é **erro de permissão** (`campo_nao_permitido`),
nunca `nulo` silencioso — o avaliador nunca faz `getattr` em objeto do chamador, nunca lê
`globals()`/`vars()`/protótipo: a única leitura é `contexto[nome]` (dicionário), e um nome fora
dele é sempre recusado.

O **contexto de topo** tem de ser dicionário simples nos dois lados: o Python recusa o que não é
`dict` exato (`tipo_invalido`); o JavaScript recusa o que não é objeto de protótipo `Object.prototype`
ou nulo, recusa lista, e recusa `Proxy` quando roda em Node (`util.types.isProxy`). **No navegador não
existe forma de detectar um `Proxy`** — lá a defesa é o contrato de que quem monta o contexto é a
aplicação, mais a lista branca por campo e a leitura por DESCRITOR (`Object.getOwnPropertyDescriptor`,
que exige descritor de dado e por isso nunca executa um getter do chamador). Está escrito aqui porque
é a única assimetria conhecida entre os dois avaliadores. Pelo mesmo motivo, **campo desconhecido
dentro de um nó de AST é recusado** (`no_desconhecido`), não ignorado: a forma do nó é fechada.

## 8. Catálogo de erros nomeados

| código | quando |
|---|---|
| `expressao_vazia` | texto vazio ou só espaço |
| `expressao_grande` | texto, tokens ou argumentos acima do limite |
| `profundidade_excedida` | aninhamento acima de 60 níveis (texto ou AST em JSON) |
| `sintaxe_invalida` | token inesperado, parêntese não fechado, aspa não fechada, expressão incompleta |
| `caractere_invalido` | caractere fora do vocabulário (`;`, `#`, `~`, etc. — nunca ignorado silenciosamente) |
| `campo_nao_permitido` | `$campo` fora da lista branca do `contexto` |
| `funcao_desconhecida` | nome de função fora de `TABELA_FUNCOES` |
| `aridade_invalida` | número de argumentos fora do intervalo aceito pela função |
| `tipo_invalido` | operando/argumento de tipo que a operação não aceita |
| `valor_grande` | coleção, texto acumulado ou aninhamento do valor acima do limite |
| `numero_invalido` | número não finito, domínio matemático inválido ou limite numérico excedido |
| `divisao_por_zero` | `/` ou `%` com divisor zero |
| `limite_passos` | avaliação acima do orçamento de passos |
| `tempo_excedido` | avaliação acima do orçamento de tempo |
| `no_desconhecido` | AST em JSON malformada ou com tipo de nó fora do vocabulário |
| `geometria_invalida` | geometria fora do contrato GeoJSON aceito: tipo errado para a função, coordenada fora da faixa ou não numérica, anel que não fecha, anel com menos de quatro posições, `coordinates` ausente |
| `feicao_invalida` | feição que não é dicionário, `atributos` que não é dicionário de nomes ou `geometria` que não é dicionário (montagem do contexto, seção 12) |
| `perfil_desconhecido` | nome de perfil fora de `PERFIS` (seção 12) |
| `tipo_de_retorno_invalido` | a expressão avaliou, mas devolveu um tipo que o perfil não aceita (seção 12) |
| `operador_desconhecido` | defesa interna (`# pragma: no cover`): nunca alcançável a partir da gramática publicada — todo operador que o parser aceita tem tratamento no avaliador |

Todo erro de sintaxe (`sintaxe_invalida`, `caractere_invalido`, `profundidade_excedida` quando
medido no texto) devolve `detalhe.linha`/`detalhe.coluna` (1-based) — é o portão do item ("erro de
sintaxe devolve linha e coluna").

## 9. AST em JSON (exportável)

`ast_para_json(no)` / `astParaJson(no)` convertem a AST tipada em um `dict`/objeto serializável por
`json.dumps`/`JSON.stringify` puro — sem classes, sem referência circular, sem tipo que o JSON não
carregue. É isto que se grava junto com o texto da expressão (C6 do L2_CONCEITO.md: a AST é
exportável). `ast_de_json(d)` / `astDeJson(d)` fazem o caminho inverso; reimportar e reavaliar
devolve exatamente o mesmo valor que avaliar a AST original (provado em
`test_ast_para_json_e_de_volta_produz_estrutura_equivalente` e no equivalente entre os dois
avaliadores, `test_ast_exportada_e_reimportada_avalia_igual_nos_dois_lados`).

Vocabulário de nós (campo `"tipo"`):

```json
{"tipo": "literal", "tipo_valor": "numero" | "texto" | "booleano" | "nulo", "valor": ...}
{"tipo": "campo", "nome": "area_ha"}
{"tipo": "unario", "operador": "-" | "!", "operando": <no>}
{"tipo": "binario", "operador": "+" | "-" | "*" | "/" | "%" | "^" | "==" | "!=" | "<" | "<=" | ">" | ">=" | "&&" | "||", "esquerda": <no>, "direita": <no>}
{"tipo": "chamada", "nome": "Maiuscula", "argumentos": [<no>, ...]}
```

## 10. Paridade com o Arcade function reference, função por função

Lista de nomes lida das páginas oficiais (`developers.arcgis.com/arcade/function-reference/`) em setembro de 2026: **269 funções em 17 categorias**. Estado por função: **feito** = mesma semântica, sem NENHUMA diferença conhecida contra a documentação oficial, e com pelo menos um vetor de teste que exercita a nossa função (`test_expressao_paridade.py` reprova a linha `feito` que não tiver vetor, e reprova a contagem do cabeçalho que não bater com as linhas); **parcial** = existe com assinatura ou regra mais estreita (dito na observação); **fora** = não existe. Nas 7 categorias com correspondência: **11 feito · 42 parcial · 81 fora** de 134; as outras 10 categorias (135 funções) ficam inteiras de fora, com o motivo. O nome nosso é sempre outro (português): paridade aqui é de CAPACIDADE, nunca promessa de rodar um script Arcade sem adaptação. Gerado por `laco/handoffs/T3/codex-L2-10-c/gerar_paridade.py`.

### Texto (2 feito · 10 parcial · 10 fora)

| Arcade | nós | estado | observação |
|---|---|---|---|
| Concatenate | `Concatenar` | parcial | junta argumentos soltos (nulo vira texto vazio, como no Arcade); a forma do Arcade com lista + separador é a nossa `Juntar` |
| Count | `Contagem` | parcial | conta PONTO DE CÓDIGO (§3.1); o Arcade não documenta a unidade e roda sobre UTF-16 |
| Find | `Find` | parcial | índice e início em ponto de código, e não casa meia-substituta (§3.1); −1 se ausente |
| FromCharCode | — | fora |  |
| FromCodePoint | — | fora |  |
| Guid | — | fora | sem aleatoriedade: os dois avaliadores têm de dar o mesmo resultado |
| Left | `Left` | parcial | corta em ponto de código (§3.1) |
| Lower | `Minuscula` | feito |  |
| Mid | `Mid` | parcial | corta em ponto de código (§3.1); sem quantidade vai até o fim |
| Proper | — | fora | regra de capitalização por locale ainda não escrita |
| Replace | `Replace` | parcial | sempre todas as ocorrências (o Arcade tem o 3º argumento `allReplacements`); casa em ponto de código (§3.1) |
| Right | `Right` | parcial | corta em ponto de código (§3.1) |
| Split | `Split` | parcial | sem `limit`/`removeEmpty`; separa em ponto de código (§3.1) |
| StandardizeFilename | — | fora |  |
| StandardizeGuid | — | fora |  |
| Text | `Texto` · `TextoNumero` · `TextoData` | parcial | sem máscara livre (`#,###.00`, `DD/MM/Y`); pt-BR com casas e 4 formatos fixos de data, UTC |
| ToCharCode | — | fora |  |
| ToCodePoint | — | fora |  |
| ToHex | — | fora |  |
| Trim | `Trim` | parcial | só espaço ASCII (espaço, tab, CR, LF, FF, VT); o Arcade também apara Unicode |
| Upper | `Maiuscula` | feito |  |
| UrlEncode | — | fora |  |

### Matemática (1 feito · 11 parcial · 14 fora)

| Arcade | nós | estado | observação |
|---|---|---|---|
| Abs | `Absoluto` | parcial | o Arcade devolve 0 para nulo; `Absoluto(nulo)` é `tipo_invalido` |
| Acos | — | fora |  |
| Asin | — | fora |  |
| Atan | — | fora |  |
| Atan2 | — | fora |  |
| Average | `Media` | parcial | só lista; o Arcade aceita também argumentos soltos |
| Ceil | `Ceil` | parcial | sem 2º argumento de casas |
| Constrain | — | fora | `Minimo(Maximo(x, a), b)` faz o mesmo |
| Cos | — | fora |  |
| Exp | — | fora |  |
| Floor | `Floor` | parcial | sem 2º argumento de casas |
| Hash | — | fora |  |
| Log | — | fora |  |
| Max | `Maximo` | parcial | argumentos soltos; não aceita lista |
| Mean | `Media` | parcial | só lista |
| Min | `Minimo` | parcial | argumentos soltos; não aceita lista |
| Number | `Numero` | parcial | sem padrão de formato; texto inválido vira nulo, nunca NaN |
| Pow | `Potencia` | parcial | |expoente| ≤ 1024 e resultado finito; o Arcade não tem esse teto |
| Random | — | fora | sem aleatoriedade (determinismo dos dois avaliadores) |
| Round | `Arredondar` | feito | meio-para-longe-de-zero, escrito à mão nos dois lados |
| Sin | — | fora |  |
| Sqrt | `Sqrt` | parcial | negativo é `numero_invalido`; o Arcade devolve NaN |
| Stdev | — | fora |  |
| Sum | `Soma` | parcial | só lista |
| Tan | — | fora |  |
| Variance | — | fora |  |

### Data (1 feito · 8 parcial · 17 fora)

| Arcade | nós | estado | observação |
|---|---|---|---|
| ChangeTimeZone | — | fora | não há fuso: data é epoch-ms UTC |
| Date | — | fora | sem construtor; a data vem do contexto ou de `AgoraUTC` |
| DateAdd | aritmética | parcial | `$data + n * 86400000` soma dias; sem unidade mês/ano |
| DateDiff | `DiferencaDias` | parcial | só dias corridos completos |
| DateOnly | — | fora |  |
| Day | `Dia` | parcial | sempre UTC; no Arcade o valor sai no fuso do contexto de execução |
| Hour | — | fora | `TextoData(x, 'data_hora')` exibe; não devolve o número |
| ISOMonth | — | fora |  |
| ISOWeek | — | fora |  |
| ISOWeekday | — | fora |  |
| ISOYear | — | fora |  |
| Millisecond | — | fora |  |
| Minute | — | fora |  |
| Month | `Mes` | parcial | o Arcade numera 0-11 (janeiro = 0); o nosso `Mes` numera 1-12 e é sempre UTC |
| Now | `AgoraUTC` | parcial | o Arcade devolve a hora LOCAL do contexto de execução; `AgoraUTC` é sempre UTC (o equivalente exato é o `Timestamp`) |
| Second | — | fora |  |
| Time | — | fora |  |
| Timestamp | `AgoraUTC` | feito | é o `Now` em UTC |
| TimeZone | — | fora |  |
| TimeZoneOffset | — | fora |  |
| ToLocal | — | fora |  |
| ToUTC | — | fora |  |
| Today | aritmética | parcial | `Floor(AgoraUTC() / 86400000) * 86400000` |
| Week | — | fora |  |
| Weekday | `Weekday` | parcial | domingo 0 … sábado 6, sempre UTC; no Arcade o dia sai no fuso do contexto |
| Year | `Ano` | parcial | sempre UTC; no Arcade o valor sai no fuso do contexto de execução |

### Lógica (2 feito · 3 parcial · 4 fora)

| Arcade | nós | estado | observação |
|---|---|---|---|
| Boolean | — | fora | sem conversão implícita para booleano |
| Decode | `Decode` | feito | escolha por igualdade estrutural, com valor padrão no fim (a avaliação preguiçosa do ramo escolhido está na §4) |
| DefaultValue | `SeNulo` | parcial | só nulo conta como vazio; texto vazio não |
| Equals | — | fora | identidade de geometria |
| IIf | `Se` | feito | condição booleana estrita; curto-circuito |
| IsEmpty | `EhNulo` | parcial | texto vazio não é vazio aqui |
| IsNan | — | fora | NaN não existe: vira `numero_invalido` |
| TypeOf | — | fora |  |
| When | `Se` aninhado | parcial | sem forma plana `When(c1, r1, c2, r2, padrao)` |

### Lista (4 feito · 6 parcial · 16 fora)

| Arcade | nós | estado | observação |
|---|---|---|---|
| All | — | fora | sem função por elemento |
| Any | — | fora | sem função por elemento |
| Array | `Lista` | parcial | cria com valores; não cria por tamanho |
| Back | `Ultimo` | parcial | no Arcade a avaliação FALHA em lista vazia; `Ultimo(Lista())` devolve nulo |
| Count | `Contagem` | feito |  |
| DefaultValue | `Obter(lista, i, padrao)` | parcial | por índice, não pela lista inteira |
| Distinct | `Unicos` | feito | igualdade estrutural, primeira ocorrência |
| Erase | — | fora | listas são imutáveis |
| Filter | — | fora | sem função por elemento (pendência nomeada do item) |
| First | `Primeiro` | feito |  |
| Front | `Primeiro` | parcial | no Arcade a avaliação falha em lista vazia; `Primeiro(Lista())` devolve nulo (esse é o `First`, que tem linha própria) |
| HasValue | `Obter(lista, i, sentinela)` | parcial | no Arcade é "tem valor no índice i", não pertinência; sem sentinela, índice presente com nulo não se distingue de ausente |
| Includes | `Contem` | feito | igualdade estrutural estrita |
| IndexOf | — | fora |  |
| Insert | — | fora | imutável |
| Map | — | fora | sem função por elemento (pendência nomeada do item) |
| None | — | fora |  |
| Pop | — | fora | imutável |
| Push | — | fora | imutável |
| Reduce | — | fora |  |
| Resize | — | fora | imutável |
| Reverse | `Reverter` | parcial | o Arcade inverte NO LUGAR (a lista de entrada muda); o nosso devolve cópia — listas aqui são imutáveis |
| Slice | — | fora |  |
| Sort | — | fora |  |
| Splice | — | fora |  |
| Top | — | fora |  |

### Dicionário (1 feito · 2 parcial · 7 fora)

| Arcade | nós | estado | observação |
|---|---|---|---|
| Count | `Contagem` | feito | chaves próprias |
| DefaultValue | `Obter(dic, chave, padrao)` | parcial | no Arcade `DefaultValue(valor, padrão)` substitui nulo/vazio e NÃO busca por chave; o equivalente dele aqui é o `SeNulo` (linha de Lógica) |
| Dictionary | — | fora | sem construtor; dicionário vem do contexto |
| Erase | — | fora | imutável |
| FromJSON | — | fora |  |
| GetKeys | — | fora |  |
| GetValues | — | fora |  |
| HasKey | `Obter` com padrão sentinela | parcial | chave presente com valor nulo é indistinguível de ausente sem sentinela |
| HasValue | — | fora |  |
| Insert | — | fora | imutável |

### Feição (0 feito · 2 parcial · 13 fora)

| Arcade | nós | estado | observação |
|---|---|---|---|
| DefaultValue | `SeNulo`/`Obter` | parcial |  |
| Domain | — | fora | domínio é do L2-10 cheio |
| DomainCode | — | fora | idem |
| DomainName | — | fora | idem |
| Expects | — | fora |  |
| Feature | — | fora |  |
| FeatureInFilter | — | fora |  |
| GdbVersion | — | fora |  |
| HasKey | `Obter` | parcial |  |
| HasValue | — | fora |  |
| Schema | — | fora |  |
| SubtypeCode | — | fora | subtipo é do L2-10 cheio |
| SubtypeName | — | fora | idem |
| Subtypes | — | fora | idem |
| TimeReceived | — | fora |  |

### Categorias inteiras de fora

| categoria (Arcade) | funções | motivo |
|---|---|---|
| FeatureSet (43) | Area, AreaGeodetic, Attachments, Average, Contains, Count, Crosses, Distinct, Domain, DomainCode, DomainName, EnvelopeIntersects, Expects, FeatureSet, FeatureSetByAssociation, FeatureSetById, FeatureSetByName, FeatureSetByRelationshipClass, FeatureSetByRelationshipName, Filter, FilterBySubtypeCode, First, GdbVersion, GetFeatureSet, GetFeatureSetInfo, GetUser, GroupBy, Intersects, Length, Length3D, LengthGeodetic, Max, Mean, Min, OrderBy, Overlaps, Schema, Stdev, Subtypes, Sum, Top, Touches, Variance, Within | não há camada ligada à expressão ainda (L2-10 cheio; `FeatureSetByRelationship` com limite é pendência nomeada) |
| Geometria (55) | Angle, Area, AreaGeodetic, Bearing, Buffer, BufferGeodetic, Centroid, Clip, Contains, ConvertDirection, ConvexHull, Crosses, Cut, DefaultValue, Densify, DensifyGeodetic, Difference, Disjoint, Distance, DistanceGeodetic, DistanceToCoordinate, EnvelopeIntersects, Equals, Extent, Generalize, Geometry, HasValue, Intersection, Intersects, IsSelfIntersecting, IsSimple, Length, Length3D, LengthGeodetic, MeasureToCoordinate, MultiPartToSinglePart, Multipoint, NearestCoordinate, NearestVertex, Offset, Overlaps, Point, PointToCoordinate, Polygon, Polyline, Relate, RingIsClockwise, Rotate, SetGeometry, Simplify, SymmetricDifference, Touches, Union, Within | geometria via PostGIS (servidor) / fórmula esférica (cliente) é pendência nomeada |
| IA (1) | TranslateText | chama serviço externo — a linguagem é sem rede por construção |
| Depuração (2) | Console, GetEnvironment |  |
| Empresa (1) | NextSequenceValue | depende de banco |
| Grafo de conhecimento (2) | KnowledgeGraphByPortalItem, QueryGraph | produto que não existe na pilha |
| Pixel (6) | Count, DefaultValue, GetKeys, GetValues, HasKey, HasValue | perfil raster |
| Portal (3) | FeatureSetByPortalItem, GetUser, Portal | sem rede; `$usuario` do contexto cobre o `GetUser` quando o L5-11 ligar |
| Trajetória (16) | TrackAccelerationAt, TrackAccelerationWindow, TrackCurrentAcceleration, TrackCurrentDistance, TrackCurrentSpeed, TrackCurrentTime, TrackDistanceAt, TrackDistanceWindow, TrackDuration, TrackFieldWindow, TrackGeometryWindow, TrackIndex, TrackSpeedAt, TrackSpeedWindow, TrackStartTime, TrackWindow | perfil de rastreamento |
| Voxel (6) | Count, DefaultValue, GetKeys, GetValues, HasKey, HasValue | perfil voxel |


## 11. O que fica FORA desta passagem (pendências nomeadas)

- Funções com expressão por elemento (`Filter`/`Map`), domínio (`DomainName`/`DomainCode`/
  `Subtypes`) e `FeatureSetByRelationship`. **Geometria deixou de estar aqui no item L5-11**: ponto,
  linha e polígono simples com `Area`/`Comprimento`/`Distancia`/`Dentro` existem (seção 5); o que
  continua fora está nomeado no fim daquela subseção (multi-geometria, `Buffer`, `Centroide`,
  `Interseta`, ponto a linha, projeção).
- **Os perfis de uso existem desde o item L5-11 (seção 12)**: popup, rótulo, cálculo de formulário,
  visibilidade, restrição, indicador de painel e título dinâmico, com o contrato de tipo de retorno
  e o orçamento de cada um. O que ainda NÃO existe é a ligação com a TELA: nenhum popup do mapa,
  nenhum rótulo do MapLibre e nenhum formulário de edição chamam `avaliar_perfil` ainda — quem liga
  são os itens de tela do L2-01/L5, e a regra de atributo do L2-10-d tem o próprio caminho de
  avaliação no servidor.
- Máscara livre de formatação (`#,###.00`, `DD/MM/Y`) do `Text` do Arcade: `TextoNumero` tem casas
  decimais e `TextoData` tem 4 formatos fixos, nada além disso. `Texto()` continua sem localidade
  de propósito (é a conversão crua para texto, usada por `Concatenar` e `Juntar`); quem quer pt-BR
  chama `TextoNumero`/`TextoData`, escritos à mão nos dois avaliadores, sem `Intl` e sem `locale`.
- Fuso horário do usuário (data é epoch-ms UTC puro nesta passagem; `TextoData` também formata em UTC).
- Permissão de camada de outro inquilino: não há camada ligada à expressão nesta passagem, então a
  cláusula do portão "expressão que acessa camada de outro inquilino = erro de permissão" NÃO foi
  provada aqui — não existe caminho de acesso a camada para atacar. Fica com o L5-11/L2-10 cheio.
- `pyparsing` (presente na máquina) não é usado no runtime — o mesmo motivo do L2_CONCEITO.md C6:
  o analisador tem de existir em JavaScript também, e gramática pequena escrita duas vezes à mão é
  mais barata de manter igual do que um gerador em duas línguas.

## 12. Perfis de uso (item L5-11)

Um PERFIL diz três coisas sobre uma expressão: onde ela é usada, que TIPO de valor ela tem de
devolver e com que ORÇAMENTO ela roda. O perfil não muda a semântica da linguagem — a mesma
expressão avaliada em dois perfis que aceitam o mesmo tipo devolve o mesmo valor, e é isso que o
portão deste item exige entre o popup e o cálculo de formulário.

| perfil | tipos de retorno aceitos | orçamento de tempo | onde |
|---|---|---|---|
| `popup` | texto, número, booleano, nulo | 50 ms | navegador, a cada clique na feição |
| `rotulo` | texto, número, nulo | 50 ms | navegador, a cada quadro do mapa |
| `calculo_formulario` | texto, número, booleano, nulo | 500 ms | formulário de edição, conferido também no servidor |
| `visibilidade` | booleano, nulo | 50 ms | navegador, mostra/esconde campo ou elemento |
| `restricao` | booleano, nulo | 500 ms | servidor, na gravação |
| `indicador_painel` | número, nulo | 500 ms | painel |
| `titulo_dinamico` | texto, número, nulo | 50 ms | navegador |

Valor de tipo fora da lista do perfil devolve `tipo_de_retorno_invalido` — a expressão avaliou, o
perfil é que recusa. Nome de perfil fora da tabela devolve `perfil_desconhecido`.

**Montagem do contexto (`contexto_da_feicao`).** Entra só o que veio da feição recebida:
`$feicao` (o dicionário inteiro, normalizado para `{"atributos": ..., "geometria": ...}`),
`$geometria` e um `$nome` para cada atributo cujo nome case com `[A-Za-z_][A-Za-z0-9_]*`. Atributo
chamado `feicao` ou `geometria` NÃO sombreia os dois reservados, e atributo com espaço, acento ou
hífen não vira `$nome`: os dois casos se alcançam por `Atributo($feicao, '<nome>')`. `$campo` fora
dessa lista é `campo_nao_permitido`, como em qualquer outro uso da linguagem.

**Isolamento.** O módulo de perfis não abre rede, arquivo nem banco: importa só o avaliador, e o
teste (`tests/unit/test_expressao_perfis.py`) varre a árvore sintática do arquivo Python e o texto
do arquivo JavaScript para reprovar `fetch`, `XMLHttpRequest`, `window`, `document`, `import(`,
`eval`, `open`, `socket`, `subprocess` e cliente de banco. Uma expressão só enxerga a feição que o
chamador passou; não há caminho para outra feição, outra camada ou outro inquilino, porque não há
caminho para lugar nenhum.
