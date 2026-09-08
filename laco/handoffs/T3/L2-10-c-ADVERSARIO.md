# L2-10-c-linguagem-expressao — ataque adversarial (06/09/2026)

**VEREDITO: REFUTADO.**

Refutado em três cláusulas do portão, nesta ordem de gravidade:

1. **Equivalência Python × JavaScript.** Os dois avaliadores NÃO dão o mesmo resultado para o mesmo
   texto e o mesmo contexto. 26 casos novos medidos, o mais grave deles em aritmética comum: o
   operador `%` com operando negativo devolve `2` no Python e `-1` no JavaScript. Não exige dado
   exótico e não está escrito em lugar nenhum do documento.
2. **"Erro nomeado, nunca exceção crua".** `TextoNumero` levanta `decimal.InvalidOperation` crua a
   partir de 1e13 com 15 casas (e de 1e20 com 8 casas). O guarda `abs(n) >= 1e21` não cobre o caso.
3. **Honestidade da tabela de paridade (seção 10 de `docs/EXPRESSAO.md`).** De 17 linhas marcadas
   `feito` que conferi contra a documentação oficial do Arcade, **6 não são `feito`** — `Month`,
   `Now`, `Abs`, `Reverse`, `Back`, `Front`. O handoff do construtor chama isso de "o pior defeito
   desta entrega, porque vira promessa em documento de paridade". Concordo.

O que o produto **defendeu**: o orçamento de tempo e de passos (ataque 1), a AST fabricada à mão
(ataque 3), o protótipo e os getters no JavaScript (ataque 4) e o valor intermediário (ataque 5).
Os números estão abaixo, com comando e saída.

Testes: `tests/unit/test_expressao_adversario.py` (novo). As três refutações estão escritas como
`pytest.mark.xfail(strict=True)` com a asserção do comportamento CORRETO — falham hoje e viram erro
no dia em que forem corrigidas, para que ninguém possa fechar o defeito sem apagar a marca.

---

## 0. Conferência independente dos números (ataque 7)

```
$ cd /home/dev/plataforma/enterprise && git log --oneline -1
cb92de9 Linguagem de expressão: >=40 funções, >=200 vetores Python=JS, listas e dicionários, limites

$ venv/bin/python -c "import sys;sys.path.insert(0,'.');from app.expressao.avaliador_py import TABELA_FUNCOES;print(len(TABELA_FUNCOES))"
43
$ node tests/expressoes/executar_js.mjs --nomes-funcoes | python3 -c "import json,sys;print(len(json.load(sys.stdin)))"
43
$ venv/bin/python -c "import json;print(len(json.load(open('tests/expressoes/vetores.json'))))"
309

$ flock /home/dev/plataforma/laco/.pytest.lock venv/bin/pytest tests/unit/test_expressao_avaliador.py \
    tests/unit/test_expressao_equivalencia.py tests/unit/test_expressao_doc_sincronizada.py \
    tests/unit/test_expressao_seguranca.py tests/unit/test_expressao_extensao.py \
    tests/unit/test_expressao_medidas.py -q -p no:randomly
19 linhas cheias de 72 pontos + 45 = 1.413 casos, todos com ponto, EXIT=0
```

**43 funções, 309 vetores e 1.413 casos conferem.** As 43 do Python são exatamente as 43 do
JavaScript (comparação de conjunto, não de contagem). Ressalvas de conferência:

- `tests/medidas/L2-10-c-expressao.json` traz `"git_sha": "9df2cff208eb"`, que é o commit ANTERIOR
  ao cb92de9 — as medidas foram gravadas antes do commit que elas descrevem. Não invalida os
  números, mas o carimbo aponta para a árvore errada.
- O handoff diz, na limitação 2, que "o relógio é conferido a cada 256 passos". **Não é**: os dois
  avaliadores conferem o relógio em TODO passo (`_Contador.passo`, `Contador.passo`), e o comentário
  no código diz isso explicitamente. O texto do handoff está defasado em relação ao código que
  descreve — e a favor do produto, não contra.
- A linguagem ainda não está ligada a nenhuma rota (`grep -rn "avaliador_py" app/` só acha o próprio
  módulo). Tudo que segue é sobre a biblioteca, não sobre uma superfície exposta.

---

## 1. Custo que não cobra passo — **ataque FALHOU, o produto se defendeu**

Objetivo: expressão dentro dos 10⁵ passos que passasse de 500 ms no servidor ou de 50 ms no cliente.

Primeiro medi o custo bruto de cada candidata sobre o maior valor que os tetos deixam existir
(20.000 pontos de código, 1.024 elementos):

```
find de agulha de 10.000 em texto de 20.000   0,0105 ms/op
replace 'a'->'b' em 20.000                    0,0149 ms/op
replace de agulha de 5.000                    0,0320 ms/op
maiuscula de 20.000 acentuados                0,0559 ms/op
regex de Numero sobre 20.000 dígitos          0,0502 ms/op
split('') de 1.024                            0,0024 ms/op
```

**Nenhuma operação isolada passa de 0,06 ms.** Esse é o ponto: o custo de uma chamada é limitado
pelo teto do VALOR, não pelo contador. Uma operação que não cobrasse passo teria de custar mais que
o orçamento inteiro, e o teto do valor impede isso.

Depois montei a expressão de maior trabalho que o analisador aceita. Encadear com `+` não serve —
a árvore fica à esquerda e bate em `profundidade_excedida` aos 60 níveis. A forma que passa é
`Minimo` variádico: 3 grupos de 64 argumentos = 192 chamadas, profundidade 3, ~1.550 tokens
(o teto é 2.000).

```
192 Maiuscula de 20.000 acentuados      PY  11,86 ms  erro=None
192 Find de agulha de 10.000 em 20.000  PY   2,99 ms  erro=None
192 Juntar de lista de 1.024            PY  50,51 ms  erro=limite_passos
192 Reverter de lista de 1.024          PY  30,77 ms  erro=limite_passos
192 Soma de lista de 1.024              PY  30,42 ms  erro=limite_passos
192 Numero de 20.000 dígitos            PY   0,50 ms  erro=numero_invalido
```

**Máximo no servidor: 50,51 ms contra um orçamento de 500 ms.** No cliente, com o orçamento
apertado de 50 ms, o que interessa é o ESTOURO (quanto o avaliador passa do limite depois da última
conferência do relógio) — se houvesse operação cara sem cobrança de passo, o estouro seria da ordem
do custo dela:

```
192 Maiuscula de 20.000 acentuados   JS  50,26 ms  tempo_excedido   estouro 0,26 ms
192 Find de agulha de 10.000         JS  50,28 ms  tempo_excedido   estouro 0,28 ms
192 Contagem de texto de 20.000      JS  50,47 ms  tempo_excedido   estouro 0,47 ms
192 Contagem de 10.000 emoji         JS  50,25 ms  tempo_excedido   estouro 0,25 ms
```

**Estouro máximo 0,47 ms sobre 50 ms.** Testes: `test_ataque_1_nenhuma_expressao_legal_passa_de_500_ms_no_servidor`
(10 casos) e `test_ataque_1_no_javascript_o_estouro_do_relogio_de_50_ms_fica_abaixo_de_5_ms`.

Conclusão: **o guarda-corpo de tempo não é nominal.** Não achei função cujo trabalho cresça mais
rápido que a contagem de passos dentro dos tetos vigentes. A defesa não é o contador de passos
sozinho — é a combinação dele com os tetos de valor (`MAX_COLECAO` 1.024, `MAX_VALOR_TEXTO` 20.000,
`MAX_VALOR_NOS` 4.096) e com o `_valor_seguro` que roda em TODO resultado de nó. Fronteira: se algum
desses tetos subir, ou se entrar uma função que consuma dois valores grandes de uma vez com custo
quadrático (junção, ordenação, produto), esta conclusão cai e tem de ser remedida.

---

## 2. Divergência Python × JavaScript fora dos 309 vetores — **ataque PASSOU, REFUTADO**

304 casos novos gerados em três rodadas (89 + 162 + 53), comparados byte a byte com o mesmo executor
(`tests/expressoes/executar_js.mjs --stdin`) e a mesma canonicalização do teste de equivalência
(`json.dumps(..., ensure_ascii, sort_keys)`). 26 divergem. Os 54 casos escolhidos para o arquivo de
teste provam que nenhum repete um vetor existente (`test_casos_do_adversario_sao_novos`).

### 2.1 Operador `%` com operando negativo — o achado principal

```
$ venv/bin/python -c "import sys;sys.path.insert(0,'.');from app.expressao.avaliador_py import avaliar_texto;print(avaliar_texto('(0-7) % 3',{}))"
2
$ echo '[{"entrada":"(0-7) % 3","contexto":{}}]' | node tests/expressoes/executar_js.mjs --stdin
[{"entrada":"(0-7) % 3","resultado":-1,...}]
```

| expressão | Python | JavaScript |
|---|---|---|
| `(0-7) % 3` | `2` | `-1` |
| `$a % $b` com `a=7, b=-3` | `-2` | `1` |
| `$a % $b` com `a=-1, b=2` | `1` | `-1` |
| `$a % $b` com `a=5, b=-2` | `-1` | `1` |
| `$a % $b` com `a=-0.5, b=2` | `1.5` | `-0.5` |
| `Texto((0-10) % 3)` | `"2"` | `"-1"` |
| `Se($a % $b > 0,'p','n')` com `a=-7, b=3` | `"p"` | `"n"` |

Causa: o `%` do Python é resto de módulo (sinal do divisor); o do JavaScript é resto truncado
(sinal do dividendo). Nenhum dos dois avaliadores implementa a operação à mão — os dois delegam ao
operador da língua (`app/expressao/avaliador_py.py` `return a % b`; `web/js/expressao/avaliador.js`
`if (op === '%') return a % b`). `docs/EXPRESSAO.md` cita `%` na EBNF, na precedência, na lista de
aritmética e no erro `divisao_por_zero`, e **em nenhum lugar fixa a convenção de sinal**. Não é só
divergência: é semântica não decidida.

Gravidade ALTA. Uma regra de validação escrita no cliente e reexecutada no servidor
(que é o motivo declarado de existirem dois avaliadores) toma decisão contrária nos dois lados.
A última linha da tabela mostra isso: o mesmo `Se` escolhe ramos diferentes.

### 2.2 Texto: ponto de código no Python, unidade UTF-16 no JavaScript

O contrato (`docs/EXPRESSAO.md` §5 e a linha `Count` da seção 10) diz **ponto de código**. O
JavaScript converte com `Array.from` em `Left`/`Right`/`Mid`/`Contagem`/`Split('')` — e esses
passam. Ficaram de fora três caminhos:

| caso | Python | JavaScript |
|---|---|---|
| `Find($a,$b)` com `a` = meia-substituta baixa `\udf0d`, `b` = `🌍` | `-1` | `1` |
| `Find($a,$b)` com `a` = meia-substituta alta `\ud83c`, `b` = `🌍` | `-1` | `0` |
| `Split($t,$s)` com `t` = `a🌍b`, `s` = `\udf0d` | `["a🌍b"]` | `["a\ud83c","b"]` |
| `Replace($t,$s,'X')`, mesmos valores | `"a🌍b"` | `"a\ud83cXb"` |
| `Contagem(Concatenar($a,$b))` com `a`=`\ud83c`, `b`=`\udf0d` | `2` | `1` |
| `Left(Concatenar($a,$b),1)`, idem | `"\ud83c"` | `"🌍"` |
| `$a < $b` com `a`=`🌍`, `b`=`�` | `false` | `true` |
| `$a <= $b`, idem | `false` | `true` |
| `$a >= $b`, idem | `true` | `false` |
| `$a < $b` com `a`=`U+10000`, `b`=`U+FF00` | `false` | `true` |

Duas causas distintas:
- `Find`, `Split` e `Replace` usam `indexOf`/`split` do JavaScript, que casam em unidade UTF-16 e
  portanto casam METADE de um par substituto; o Python, que indexa ponto de código, não casa.
  Concatenar duas metades também produz coisas diferentes: no Python continuam dois pontos de
  código, no JavaScript viram um.
- Comparação de ordem (`<`, `<=`, `>`, `>=`) entre textos é feita pelo operador nativo dos dois
  lados: o Python compara ponto de código, o JavaScript compara unidade UTF-16. Todo emoji fica
  ANTES de `U+E000`–`U+FFFF` no JavaScript e DEPOIS no Python. Isso não precisa de meia-substituta:
  basta um emoji e um caractere BMP alto, o que é dado corriqueiro.

Gravidade ALTA para a comparação de ordem (dado normal), MÉDIA para as meias-substitutas (entrada
patológica, mas alcançável por qualquer JSON de contexto).

### 2.3 `Numero` sobre algarismo que não é ASCII

| `Numero($t)` com `t` = | Python | JavaScript |
|---|---|---|
| `٤٢` (arábico-índico) | `42` | `null` |
| `१२` (devanágari) | `12` | `null` |
| `１２` (largura inteira) | `12` | `null` |
| `𝟙𝟚` (matemático) | `12` | `null` |
| `٤.٢` | `4.2` | `null` |

Causa: `re.fullmatch(r"-?\d+", texto)` — o `\d` do Python casa dígito decimal Unicode de qualquer
escrita, e o `float()` do Python aceita esses dígitos; o `/^-?\d+$/` do JavaScript é só ASCII.
Gravidade MÉDIA. Corrige-se trocando o `\d` por `[0-9]` no Python (uma linha).

### 2.4 `Ano`/`Mes`/`Dia` com milissegundo fracionário negativo

| expressão | Python | JavaScript |
|---|---|---|
| `Ano(0-0.5)` | `1969` | `1970` |
| `Mes(0-0.5)` | `12` | `1` |
| `Dia(0-0.5)` | `31` | `1` |
| `Ano(0-0.4)` | `1969` | `1970` |

Causa: `_ano_mes_dia_utc` monta `timedelta(milliseconds=ms)`, que arredonda para o microssegundo
mais próximo e cai antes da época; `new Date(ms)` trunca para zero. `TextoData` NÃO diverge porque
faz `math.floor(ms)` / `Math.floor(ms)` antes — a correção do `Ano`/`Mes`/`Dia` é aplicar o mesmo
`floor`. Gravidade BAIXA (data com fração de milissegundo é rara), mas é a mesma família de defeito:
o cálculo delegado à biblioteca da língua em vez de escrito à mão.

### 2.5 `TextoNumero` levanta exceção crua — segunda cláusula refutada

```
$ venv/bin/python -c "import sys;sys.path.insert(0,'.');from app.expressao.avaliador_py import avaliar_texto;print(avaliar_texto('TextoNumero(\$x,15)',{'x':1e13}))"
decimal.InvalidOperation: [<class 'decimal.InvalidOperation'>]
```

| valor | casas | Python | JavaScript |
|---|---|---|---|
| 1e13 | 15 | `InvalidOperation` crua | `"10.000.000.000.000,000000000000000"` |
| 1e14 | 14 | `InvalidOperation` crua | formata |
| 1e20 | 8 | `InvalidOperation` crua | formata |
| 1e12 | 15 | formata | formata |

Causa: `_decimal_fixo` usa `Decimal(n).quantize(...)` com o contexto PADRÃO do módulo `decimal`
(28 dígitos significativos). Quando dígitos inteiros + casas passa de 28, o `quantize` levanta
`decimal.InvalidOperation`, que é `ArithmeticError` — não está na lista que `avaliar` captura
(`OverflowError, ValueError, ZeroDivisionError`) e não é `ErroExpressao`. O guarda existente
(`abs(n) >= 1e21`) não cobre: 1e20 com 8 casas já estoura. Correção: usar um `decimal.localcontext`
com precisão suficiente, ou capturar `decimal.DecimalException` como `numero_invalido`.

Gravidade ALTA. É a cláusula "erro nomeado, nunca exceção crua" quebrada dentro do próprio catálogo
de erros da seção 8 do documento, e vira 500 no dia em que houver rota.

### 2.6 O que NÃO divergiu (o produto se defendeu)

`Contagem`/`Left`/`Mid`/`Right`/`Split('')`/`Find` sobre emoji BEM formado; acento composto contra
precomposto (nenhum dos dois normaliza, e é isso que se quer); caixa alta e baixa de eszett,
ligadura `ﬁ`, `İ`, sigma final, cheroqui, deseret, adlam, georgiano; `Texto` acima de 2^53, de 1e21
e de 1e308; `Arredondar` com fator infinito (`OverflowError` capturado dos dois lados);
`0.0078125` com 6 casas (o `Decimal`/`toFixed` bate); zero negativo; estouro de soma e de produto;
`Weekday`, `TextoData` e `DiferencaDias` em 1900, 1600, ano 1, 9999 e nos dois 29 de fevereiro.

---

## 3. AST fabricada à mão — **ataque FALHOU, o produto se defendeu**

22 ASTs fora do contrato, montadas como `dict`/objeto e passadas a `ast_de_json` nos dois lados.
**Nenhuma avaliou.** Todas param com `ErroExpressao`, nunca com exceção crua, nunca com estouro de
pilha:

| ataque | Python | JavaScript |
|---|---|---|
| tipo de nó desconhecido / sem `tipo` | `no_desconhecido` | `no_desconhecido` |
| literal com `tipo_valor` incoerente ou fora do contrato | `no_desconhecido` | `no_desconhecido` |
| booleano declarado número | `no_desconhecido` | `no_desconhecido` |
| campo com nome fora do identificador / não textual | `no_desconhecido` | `no_desconhecido` |
| operador unário/binário inventado | `no_desconhecido` | `no_desconhecido` |
| `argumentos` que não é lista | `no_desconhecido` | `no_desconhecido` |
| 65 argumentos | `expressao_grande` | `expressao_grande` |
| profundidade 200 | `profundidade_excedida` | `profundidade_excedida` |
| ciclo no operando / nos argumentos | `profundidade_excedida` | `profundidade_excedida` |
| grafo compartilhado de 64×64 nós | `expressao_grande` | `expressao_grande` |
| aridade errada (`Se` com 1, `Left` com 5) | `aridade_invalida` | `aridade_invalida` |
| função inexistente | `funcao_desconhecida` | `funcao_desconhecida` |
| literal infinito / NaN | `numero_invalido` | `numero_invalido` |
| campo `__proto__` / `constructor` | `campo_nao_permitido` | `campo_nao_permitido` |
| literal com getter no campo `valor` (JS) | — | `no_desconhecido`, getter não executado |
| AST herdando de protótipo (JS) | — | `no_desconhecido` |

Aridade e existência da função são conferidas na AVALIAÇÃO, não na importação. Não é furo: nenhuma
avalia. O ciclo é cortado pela profundidade antes de virar recursão infinita, nos dois lados.

**Única tolerância:** campo extra dentro de um nó é IGNORADO, não recusado — inclusive uma chave
literal `"__proto__"` vinda de `JSON.parse`. Não muda comportamento e não polui protótipo
(conferido: `Object.prototype.p === undefined` depois do ataque), mas uma AST assinada com campo
extra passa. Registrado em `test_ataque_3_campo_extra_no_no_e_ignorado_nos_dois_lados`; não é
refutação, é fronteira.

---

## 4. Contexto hostil no JavaScript — **defendido no essencial, uma brecha de contrato**

Defendeu (`test_ataque_4_javascript_nao_le_prototipo_nem_executa_getter`, contadores todos em zero):

- campo que só existe em `Object.prototype` → `campo_nao_permitido`; via `Obter` → `null`;
- getter no contexto, getter dentro de dicionário, getter num índice de lista → `tipo_invalido`,
  **0 execuções** (o `proprio()` exige descritor de dado, não aceita `get`);
- `toJSON` e `valueOf` no dicionário → `tipo_invalido`, **0 chamadas**;
- `__proto__` vindo de `JSON.parse`, `constructor`, `prototype` como nome de campo →
  `campo_nao_permitido`;
- contexto `Object.create(null)` → funciona (é o caso legítimo);
- `Object.prototype` intacto no fim.

**Brecha:** o `avaliar` do Python confere `type(contexto) is not dict` e recusa qualquer coisa
exótica (conferido: um `dict` com `__missing__` dá `tipo_invalido`). O JavaScript não confere nada
no contexto de TOPO. Um `Proxy` sobre objeto simples atravessa — o protótipo do alvo é
`Object.prototype` —, suas armadilhas `has`/`getOwnPropertyDescriptor` executam código e
`$campoQueNaoExiste` resolve para o que a armadilha devolver. O mesmo vale para uma AST entregue
como `Proxy` (avaliou, 6 disparos da armadilha `get`).

Gravidade BAIXA hoje: quem monta o contexto é a aplicação, não o autor da expressão, então isto não
é fuga do isolamento — é a promessa "lista branca de campos" valendo só enquanto o objeto passado
for simples, e valendo de forma diferente nas duas línguas. `valorSeguro` já aplica o teste de
protótipo a dicionário aninhado; falta aplicá-lo ao contexto de topo. Registrado como
`xfail(strict=True)` em `test_ataque_4_contexto_exotico_deveria_ser_recusado_como_no_python`.

---

## 5. Valor intermediário — **ataque FALHOU, o produto se defendeu**

Pico de memória por `tracemalloc`, em cada expressão que tenta inchar o valor antes de
`valor_grande` disparar:

```
Concatenar 64 textos de 20.000       pico 1.280,38 KiB   1,37 ms   valor_grande
Lista de 64 listas de 1.024          pico 2.148,14 KiB  98,29 ms   valor_grande
Replace que multiplica por 20        pico     4,97 KiB   0,11 ms   valor_grande
Split vazio de texto de 20.000       pico   160,89 KiB   0,49 ms   valor_grande
Unicos de 1.024 listas               pico   154,27 KiB   7,12 ms   valor_grande
árvore de 192 Concatenar dobrados    pico    44,98 KiB   3,05 ms   valor_grande
Juntar de 1.024 textos de 19         pico    38,26 KiB   2,90 ms   ok
```

**Pico máximo 2,1 MiB.** A razão é estrutural e vale a pena escrever: `avaliar` passa TODO resultado
de nó por `_valor_seguro` antes de ele subir na árvore. O maior valor intermediário possível é o de
UMA operação sobre argumentos já limitados — 64 argumentos × 20.000 pontos de código — e o teto
dispara logo depois. Não achei caminho para acumular. Fronteira: `Lista` de 64 listas de 1.024 leva
98 ms para descobrir que é grande demais, porque a contagem é feita nó a nó durante a cópia; é caro
mas está dentro do orçamento e cobra passo.

---

## 6. Honestidade da tabela de paridade — **ataque PASSOU, REFUTADO**

Conferi 17 linhas marcadas `feito` contra a documentação oficial lida em
`developers.arcgis.com/arcade/function-reference/` (páginas `date_functions`, `text_functions`,
`math_functions`, `array_functions`, `logical_functions`) em 06/09/2026. **6 estão erradas.**

| linha `feito` | o que o Arcade documenta | o que a nossa faz |
|---|---|---|
| `Month` → `Mes` | "Values range from 0-11 where January is `0` and December is `11`" | `Mes(0)` → `1`. A própria observação da linha escreve "1-12" e mesmo assim marca `feito` |
| `Now` → `AgoraUTC` | "current date and time in the time zone of the profile's execution context" — hora LOCAL | `AgoraUTC` é UTC. O equivalente UTC é o `Timestamp`, que já tem linha própria (essa está certa) |
| `Abs` → `Absoluto` | "If the input is `null`, then it returns 0" | `Absoluto(nulo)` → `tipo_invalido` |
| `Reverse` → `Reverter` | "Reverses the contents of the array **in place**" | devolve cópia — e a observação da linha DIZ "devolve cópia", ainda assim marcada `feito` |
| `Back` → `Ultimo` | "If the input array is empty, then the expression evaluation will fail" | `Ultimo(Lista())` → `nulo` |
| `Front` → `Primeiro` | mesma regra do `Back`: falha em lista vazia | `Primeiro(Lista())` → `nulo`. Isso é o `First` do Arcade (que tem linha própria e está certa), não o `Front` |

Achado menor da mesma varredura: **`DefaultValue` aparece três vezes com três estados** — `parcial`
para `SeNulo` (Lógica), `parcial` para `Obter(lista, i, padrão)` (Lista) e `feito` para
`Obter(dic, chave, padrão)` (Dicionário). No Arcade é uma função só,
`DefaultValue(value, defaultValue)`, substituição de nulo/vazio — nunca busca por chave. A linha do
Dicionário mapeia para a função errada e é a que está marcada `feito`.

Linhas `feito` que conferi e que **estão certas**: `Timestamp`, `Year`, `Day`, `Weekday` (0=domingo),
`Find` (−1 quando ausente, `startPosition` opcional), `Mid` (contagem opcional, vai até o fim),
`Left`, `Right`, `Upper`, `Lower`, `First`, `Sqrt` e `Round` (o Arcade não documenta regra de empate
nem negativo, então "meio-para-longe-de-zero" não contradiz o que está escrito), `Count` de texto e
de lista (a nossa conta ponto de código e a do Arcade conta caractere — a observação declara a
diferença; deixo como fronteira, não como erro).

A seção 10 não tem teste de regeneração (o gerador vive fora do repositório, e o próprio handoff diz
isso). Enquanto não tiver, essa tabela é texto solto: nada impede que a próxima função entre com o
mesmo tipo de rótulo generoso.

---

## Fronteira honesta: o que este item NÃO prova

1. **Não prova equivalência dos dois avaliadores.** Prova equivalência em 309 vetores escolhidos por
   quem escreveu os dois lados. Fora deles, `%`, comparação de ordem de texto, `Find`/`Split`/
   `Replace` com meia-substituta, `Numero` com algarismo não-ASCII e `Ano`/`Mes`/`Dia` com fração
   negativa divergem. A regra que sai disso: **toda operação que os dois lados delegam ao operador
   ou à biblioteca da língua é candidata a divergir** — o que está escrito à mão (`Arredondar`,
   `_decimal_fixo`, `formatarNumero`, `Weekday`) é justamente o que passou.
2. **Não prova que a comparação é byte a byte de verdade em dicionário.** O teste de equivalência
   serializa com `sort_keys=True`, o que apaga a diferença de ordem de chave (o `Object.keys` do
   JavaScript põe chave que parece inteiro primeiro, em ordem numérica; o `dict` do Python preserva
   inserção). Não é erro, é escopo — mas quem ler "byte a byte" vai entender mais do que foi medido.
3. **Não prova nada sobre permissão de camada de outro inquilino.** O construtor já escreve isso; eu
   confirmo que não há caminho de acesso a camada para atacar.
4. **Não prova comportamento sob carga real.** Os cortes de tempo foram medidos com a máquina em
   `load average` alto e variam entre rodadas. O que se prova é "corta com erro nomeado", e isso se
   sustentou em todas as rodadas.
5. **Não prova paridade com o Arcade.** Prova que existe uma tabela de 134 linhas em 7 categorias;
   a amostragem de 17 linhas `feito` encontrou 6 erradas. Uma tabela sem teste de regeneração e com
   35 % de erro na amostra não é evidência de paridade — é uma lista de intenções.
6. **Não prova o teto de custo para um catálogo maior.** A defesa do ataque 1 depende de os tetos de
   valor de hoje (1.024 elementos, 20.000 pontos de código) e de nenhuma função consumir dois valores
   grandes com custo quadrático. `Filter`/`Map`/`Reduce` e geometria — as pendências nomeadas —
   mudam exatamente essa conta e obrigam a remedir.

## Como reproduzir

```bash
cd /home/dev/plataforma/enterprise
flock /home/dev/plataforma/laco/.pytest.lock venv/bin/pytest tests/unit/test_expressao_adversario.py -p no:randomly
# saída real: 75 passed, 38 xfailed in 1.44s   (EXIT=0)
#   75 passed  = os ataques que o produto defendeu
#   38 xfailed = as três refutações (26 divergências + 5 de TextoNumero + 1 de contexto Proxy
#                + 6 linhas da tabela de paridade)
# Um xfail que vira XPASS = alguém corrigiu o defeito e tem de apagar a marca.
```

## Suíte inteira da linguagem, com o arquivo do adversário junto

```
$ flock /home/dev/plataforma/laco/.pytest.lock venv/bin/pytest \
    tests/unit/test_expressao_avaliador.py tests/unit/test_expressao_equivalencia.py \
    tests/unit/test_expressao_doc_sincronizada.py tests/unit/test_expressao_seguranca.py \
    tests/unit/test_expressao_extensao.py tests/unit/test_expressao_medidas.py \
    tests/unit/test_expressao_adversario.py -p no:randomly
1488 passed, 38 xfailed in 3.62s   (EXIT=0)
```

Os 1.413 casos do construtor continuam passando: o ataque não quebrou nada do que já existia.
O que ele mostra é o que os 1.413 não cobriam.

## Commits deste ataque

- `tests/unit/test_expressao_adversario.py` e este handoff, em um commit só. Nada mais foi tocado:
  não consertei nenhum dos defeitos, por instrução.
