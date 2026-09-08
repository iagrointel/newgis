from pathlib import Path
p=Path('/home/dev/plataforma/enterprise/docs/EXPRESSAO.md');s=p.read_text()
s=s.replace('(≥ 20 casos — hoje tem mais, para dar folga\nantes do L5-11 crescer a lista)', '(≥ 200 casos, incluindo coleções e Unicode)')
s=s.replace('## 2. Tipos desta passagem','## 2. Tipos do núcleo')
a=s.index('**Fora desta passagem**');b=s.index('Por que "data"',a)
s=s[:a]+'''Listas e dicionários JSON também são valores. Listas são criadas por `Lista`/`Split` ou recebidas
pelo contexto. Dicionários vêm do contexto autorizado e são lidos por `Obter`; a gramática não
introduz literais `[]`/`{}`. As coleções aceitam aninhamento dentro dos limites da seção 7.
A igualdade nas funções `Contem`, `Unicos` e `Decode` é estrutural: ordem de lista importa,
ordem de chaves de dicionário não, e booleano é diferente de número.

Geometria, domínio, relações entre camadas e funções com expressão por elemento (`Filter`/`Map`)
continuam fora do núcleo. O contexto só deve conter dados já autorizados pelo chamador.

'''+s[b:]
s=s.replace('## 5. Catálogo de funções (18, ≥ 15 do portão)','## 5. Catálogo de funções (41)')
a=s.index('## 6. Algoritmos')
s=s[:a]+'''### Texto, número, data e escolha adicionados

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

As funções novas propagam argumento nulo, exceto `Lista`, `Obter`, `Contem` e `Decode`.
`Obter` avalia o padrão antecipadamente e o usa apenas quando a chave está ausente ou a coleção
é nula; uma chave presente com valor nulo permanece nula. `Contem` admite valor buscado nulo.
`Decode` compara casos em ordem e ignora resultados dos casos não escolhidos, além dos casos
posteriores à primeira correspondência. Não modifica o contexto. As chaves `__proto__`,
`prototype` e `constructor` são recusadas por `Obter`; getters e propriedades herdadas não
são caminhos de acesso a dados.

'''+s[a:]
s=s.replace('conferido a cada 256 passos (o relógio não é grátis)', 'conferido a cada passo, inclusive em operações de coleção')
a=s.index('`ast_de_json` (reimportação')
s=s[:a]+'''Limites de valores e operações, aplicados também aos resultados intermediários:

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

'''+s[a:]
s=s.replace('| `divisao_por_zero` |', '| `valor_grande` | coleção, texto acumulado ou aninhamento do valor acima do limite |\n| `numero_invalido` | número não finito, domínio matemático inválido ou limite numérico excedido |\n| `divisao_por_zero` |')
a=s.index('Esta passagem cobre só o núcleo',s.index('## 10.'))
b=s.index('## 11.',a)
s=s[:a]+'''A referência de [texto do Arcade](https://developers.arcgis.com/arcade/function-reference/text_functions/)
e a de [coleções](https://developers.arcgis.com/arcade/function-reference/array_functions/) foram
consultadas em 06/09/2026. O núcleo oferece operações correspondentes de recorte, busca, divisão
e consulta de coleções. A compatibilidade permanece parcial: nomes, coerção, tratamento de nulo,
assinaturas e limites são os desta especificação própria, e não uma promessa de executar scripts
Arcade sem adaptação. `Mid` exige texto, `Trim` remove apenas espaços ASCII e `Replace` substitui
todas as ocorrências. Coleções não suportam callbacks, mutação ou objetos FeatureSet.

| capacidade | estado | prova ou fronteira |
|---|---|---|
| funções de texto/número/UTC/nulo e coleções JSON | implementada no núcleo | vetores compartilhados e testes de erro |
| limites de valor, AST e custo de avaliação | implementados no núcleo | testes de segurança em ambos os runtimes |
| scripts Arcade completos e seus perfis | parcial | sintaxe e funções próprias; integração ainda ausente |
| geometria, domínio, FeatureSet e consulta entre camadas | fora | não implementados |
| consumo por Pro/AGOL reais | pendente | depende de integração e prova externa |

'''+s[b:]
s=s.replace('- Tipos lista, dicionário, geometria; funções de lista (`Filter`/`Map`/`Includes`/`Count`/`First`),','- Geometria; funções com expressão por elemento (`Filter`/`Map`),')
p.write_text(s)
