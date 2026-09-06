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
os dois avaliadores: `tests/expressoes/vetores.json` (≥ 20 casos — hoje tem mais, para dar folga
antes do L5-11 crescer a lista); a prova de equivalência está em
`tests/unit/test_expressao_equivalencia.py`.

## 1. Visão geral da gramática (EBNF)

```ebnf
expressao     = ou ;
ou            = "e" , { "||" , "e" } ;
e             = igualdade , { "&&" , igualdade } ;
igualdade     = comparacao , { ( "==" | "!=" ) , comparacao } ;
comparacao    = aditiva , { ( "<" | "<=" | ">" | ">=" ) , aditiva } ;
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

## 2. Tipos desta passagem

| tipo | representação Python | representação JavaScript | literal |
|---|---|---|---|
| número | `int` ou `float` | `number` | `42`, `3.14`, `-7`, `.5` |
| texto | `str` | `string` | `'texto'` (aspa simples dobrada `''` escapa uma aspa) |
| booleano | `bool` | `boolean` | `verdadeiro`, `falso` |
| nulo | `None` | `null`/`undefined` tratados igual | `nulo` |
| **data** | **convenção**: número = milissegundos desde a época Unix (1970-01-01T00:00:00Z), sempre UTC | idem | não há literal de data; vem de `AgoraUTC()` ou de um campo do contexto |

**Fora desta passagem** (pedidos na hipótese cheia do item, para quando a integração com
popup/formulário/rede existir): lista, dicionário, geometria, `FeatureSetByRelationship`, funções
de domínio (`DomainName`/`DomainCode`/`Subtypes`) e funções de lista (`Count`/`First`/`Includes`/
`Filter`/`Map`). Não há função aqui que produza ou consuma esses tipos — uma expressão que tentar
usá-los recebe `funcao_desconhecida`.

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

## 4. Curto-circuito (o ramo não avaliado não roda)

- **`Se(condicao, entao, senao)`**: `condicao` tem de avaliar para booleano estrito (`nulo` ou
  qualquer outro tipo é `tipo_invalido` — não há regra implícita de "nulo vira falso" aqui, ao
  contrário dos operadores lógicos). Só o ramo escolhido é avaliado; o outro nunca roda, mesmo que
  contenha um erro (`Se($x > 0, 1, 10 / 0)` com `$x = 5` devolve `1` sem nunca calcular `10 / 0`).
- **`SeNulo(valor, alternativa)`**: se `valor` é `nulo`, avalia e devolve `alternativa`; senão
  devolve `valor` sem nunca avaliar `alternativa`.
- **`&&`/`||`**: como descrito acima — o lado que decide sozinho evita avaliar o outro.

## 5. Catálogo de funções (18, ≥ 15 do portão)

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
| tempo de avaliação | 500 ms servidor / 50 ms cliente (padrão; o chamador pode passar outro) | conferido a cada 256 passos (o relógio não é grátis) | `tempo_excedido` |

`ast_de_json` (reimportação de uma AST gravada) aplica os MESMOS limites de profundidade e
aridade que `analisar` aplica ao texto — uma AST em JSON é entrada tão não confiável quanto o
texto (é o que se grava no documento, C6 do L2_CONCEITO.md), e nada garante que veio de
`ast_para_json`; sem essa conferência, um JSON fabricado à mão contornaria os dois guarda-corpos
do lado texto por inteiro.

`$campo` fora do `contexto` que o chamador passou é **erro de permissão** (`campo_nao_permitido`),
nunca `nulo` silencioso — o avaliador nunca faz `getattr` em objeto do chamador, nunca lê
`globals()`/`vars()`/protótipo: a única leitura é `contexto[nome]` (dicionário), e um nome fora
dele é sempre recusado.

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
| `divisao_por_zero` | `/` ou `%` com divisor zero |
| `limite_passos` | avaliação acima do orçamento de passos |
| `tempo_excedido` | avaliação acima do orçamento de tempo |
| `no_desconhecido` | AST em JSON malformada ou com tipo de nó fora do vocabulário |
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

## 10. Paridade com o Arcade (parcial — a tabela completa é do item L2-10 cheio)

Esta passagem cobre só o núcleo (aritmética, lógica, condicional, texto/número/data/nulo básicos).
A tabela de paridade feito/parcial/fora contra o Arcade function reference completo (perfis popup,
labeling, calculation, constraint, validation, dashboard; `FeatureSetByRelationship`; funções de
lista, domínio e geometria) fica para quando a integração com camada/formulário existir — registrar
aqui uma paridade "feito" antes disso venderia o que não existe (regra da casa). O que dá para
dizer hoje, por comparação com
[Arcade function reference](https://developers.arcgis.com/arcade/function-reference/) (lido
05/09/2026): as 18 funções acima cobrem o equivalente do Arcade a `Upper`/`Lower`/`Concatenate`/
`Text`, `Round`/`Abs`/`Min`/`Max`/`Number`/`Pow`, `Now`/`Year`/`Month`/`Day`/`DateDiff`, `IsEmpty`/
`DefaultValue` (nossos `EhNulo`/`SeNulo`) e `IIf` (nosso `Se`) — nomes em português, sem os
sinônimos do Arcade (`Trim`, `Left`/`Right`/`Mid`, `Find`, `Split`, `Floor`/`Ceil`/`Sqrt`, `Weekday`,
`Decode`), que ficam pendentes de item futuro se o backlog do L2-10 pedir.

## 11. O que fica FORA desta passagem (pendências nomeadas)

- Tipos lista, dicionário, geometria; funções de lista (`Filter`/`Map`/`Includes`/`Count`/`First`),
  domínio (`DomainName`/`DomainCode`/`Subtypes`) e `FeatureSetByRelationship`.
- Integração com popup, rótulo (MapLibre), regra de atributo/formulário, restrição/validação,
  indicador — todas de itens futuros do L2-10/L5 (o "ativo da casa" `L5-11` do item).
- Formatação de número e data localizada em pt-BR (a hipótese cheia do item pede; aqui `Texto()` e
  a formatação interna são deliberadamente sem localidade, para os dois avaliadores concordarem sem
  depender de biblioteca de internacionalização nenhuma das duas línguas).
- Fuso horário do usuário (data é epoch-ms UTC puro nesta passagem).
- `pyparsing` (presente na máquina) não é usado no runtime — o mesmo motivo do L2_CONCEITO.md C6:
  o analisador tem de existir em JavaScript também, e gramática pequena escrita duas vezes à mão é
  mais barata de manter igual do que um gerador em duas línguas.
