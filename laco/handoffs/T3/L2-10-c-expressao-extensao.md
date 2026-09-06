# L2-10-c-linguagem-expressao — extensão do núcleo (turno 3, 06/09/2026)

Continuação de `laco/handoffs/T3/L2-10-c-expressao.md` (núcleo: 18 funções, 41 vetores). Esta passagem
foi começada por um agente que caiu por limite de cota da API **antes de rodar o pytest e de commitar**;
o trabalho estava em disco, sem commit, na árvore principal. Este handoff é a retomada: rodar, consertar,
completar o que faltava do portão, medir e commitar.

Árvore: `/home/dev/plataforma/enterprise` (master), SÓ os arquivos da linguagem de expressão.
Commit: **cb92de9db3ce60ca401227310b0c8a00ff6e42ee** — `Linguagem de expressão: >=40 funções, >=200
vetores Python=JS, listas e dicionários, limites (item L2-10-c-linguagem-expressao)`.

## O que foi construído (arquivos do commit)

| arquivo | o que mudou |
|---|---|
| `app/expressao/avaliador_py.py` | +564 linhas: 25 funções novas (texto, número, data, `Decode`, 11 de coleção, 2 de formatação pt-BR), tipos lista e dicionário como valor de 1ª classe, tetos por VALOR, orçamento cobrando elemento de coleção |
| `web/js/expressao/avaliador.js` | +318 linhas: as MESMAS 25 funções, mesmos códigos de erro, mesma aritmética; leitura só de propriedade própria de dado (sem herdada, sem getter) |
| `tests/expressoes/vetores.json` | 41 → **309 vetores** (entrada, contexto, saída) |
| `tests/expressoes/executar_js.mjs` | modo `--stdin` (vetores por entrada padrão) e `--nomes-funcoes`; devolve também `ast` e `resultado_ida_e_volta` |
| `tests/unit/test_expressao_equivalencia.py` | 10 testes → 1.242 casos: Python × JavaScript byte a byte, AST ida-e-volta nos dois lados e CRUZADA, erro de sintaxe com linha e coluna |
| `tests/unit/test_expressao_extensao.py` (novo) | 74 casos: 46 erros nomeados idênticos nos dois runtimes, imutabilidade, ciclo, orçamento, corte pelo relógio nos dois lados, getter/protótipo no JS, **21 casos de formatação pt-BR com oráculo escrito à mão** |
| `tests/unit/test_expressao_doc_sincronizada.py` | agora confere ≥ 40 funções documentadas e a EBNF byte a byte contra a gerada das tabelas do parser |
| `tests/unit/test_expressao_medidas.py` | grava `tests/medidas/L2-10-c-expressao.json`; ganhou o corte de 500 ms do servidor e o orçamento de passos |
| `docs/EXPRESSAO.md` | EBNF regerada; catálogo 41 → **43 funções**; seção nova de formatação pt-BR; **seção 10 refeita: paridade função a função contra as 269 funções do Arcade function reference**; seção 11 (pendências) corrigida |
| `docs/PARIDADE.md` | seção nova "Linguagem de expressão", uma linha por categoria do Arcade + 3 linhas de fronteira |
| `tests/medidas/L2-10-c-expressao.json` | 11 medidas |
| `CHANGELOG.md` | uma entrada na seção "turno 3" |

Duas falhas reais foram encontradas ao rodar o pytest pela primeira vez (o agente anterior nunca rodou):
`TextoNumero`/`TextoData` estavam implementadas nos dois avaliadores e **ausentes do documento**, e a EBNF
do documento estava defasada (a ordem dos operadores de comparação mudou no código: o documento dizia
`"<=" | ">=" | "<" | ">"`, o parser diz `"<" | "<=" | ">" | ">="`). As duas foram pegas pelo próprio
`test_expressao_doc_sincronizada.py` — é para isso que ele existe.

## Cláusula do portão → prova

Comando comum: `cd /home/dev/plataforma/enterprise`.

| cláusula | estado | prova (comando → resultado) |
|---|---|---|
| ≥ 40 funções | **passou** | `venv/bin/python -c "import sys;sys.path.insert(0,'.');from app.expressao.avaliador_py import TABELA_FUNCOES;print(len(TABELA_FUNCOES))"` → **43**; `test_expressao_doc_sincronizada.py::test_portao_ao_menos_40_funcoes_documentadas`; `test_python_e_javascript_documentam_a_mesma_lista_de_funcoes` prova que o JS tem as mesmas 43 |
| ≥ 200 vetores passando em Python E em JavaScript, byte a byte | **passou** | `venv/bin/python -c "import json;print(len(json.load(open('tests/expressoes/vetores.json'))))"` → **309**; `test_expressao_equivalencia.py::test_python_e_javascript_concordam_byte_a_byte` (309 casos, comparação de `json.dumps(..., sort_keys=True)` contra `JSON.stringify` canônico) |
| EBNF publicada e GERADA da tabela de tokens (teste prova que a gramática do documento é a do código) | **passou** | `test_ebnf_do_documento_e_a_gerada_das_tabelas_do_parser` (igualdade byte a byte com `ebnf()`), `test_todo_operador_do_tokenizador_esta_na_ebnf_e_vice_versa`, `test_palavras_chave_do_tokenizador_estao_na_ebnf` |
| laço infinito / recursão profunda cortado em ≤ 50 ms com erro nomeado | **passou** | `test_expressao_extensao.py::test_ataque_de_custo_por_passo_e_cortado_pelo_relogio_em_50_ms_no_python` e `..._no_javascript`. Medido: **50,63 ms (Python)** e **53,65 ms (JavaScript)**, código `tempo_excedido`. O ataque é `40 × Contagem(Unicos($x))` sobre 1.024 dicionários (≈ 21 milhões de comparações estruturais) com o orçamento de PASSOS posto em 10⁹ de propósito, para que só o RELÓGIO possa cortar — custo escondido dentro de UMA chamada, não árvore funda |
| AST exportado e reimportado avalia igual | **passou** | `test_ast_ida_e_volta_avalia_igual_em_todos_os_vetores` (309, Python), `vetores_ast_ida_e_volta_nos_dois_lados` = **309** (JavaScript), e `test_ast_exportada_pelo_python_reimportada_no_javascript_avalia_igual_em_todos_os_vetores` (**cruzado**: AST escrita pelo Python, lida e avaliada pelo JavaScript) |
| formatação de número e data em pt-BR conferida | **passou** | `test_formatacao_pt_br_confere_nos_dois_runtimes` — **21 casos**, esperado escrito à mão a partir da regra (milhar `.`, decimal `,`, empate para longe de zero, zero sem sinal, 4 formatos de data, bissexto, antes da época), conferido no Python E no JavaScript. Mais 39 vetores de `TextoNumero`/`TextoData` dentro dos 309 |
| tabela de paridade contra o Arcade function reference por função (feito/parcial/fora) | **passou** | `docs/EXPRESSAO.md` seção 10: **269 funções em 17 categorias**, uma linha por função nas 7 categorias com correspondência (**29 feito · 24 parcial · 81 fora** de 134) + as 10 categorias inteiras de fora (135 funções) com o motivo de cada. Resumo por categoria em `docs/PARIDADE.md`. Gerador: `laco/handoffs/T3/codex-L2-10-c/gerar_paridade.py` |
| erro de sintaxe devolve linha e coluna | **passou** | `test_expressao_equivalencia.py::test_erro_de_sintaxe_devolve_linha_e_coluna` |
| tipos lista e dicionário | **passou** | 11 funções de coleção; `Contagem`/`Obter` aceitam dicionário; 46 casos de erro nomeado em `test_expressao_extensao.py`; `test_operacoes_nao_mutam_colecoes_do_chamador`; `test_contexto_ciclico_rejeitado_com_erro_nomeado` |
| limite de passos (10⁵) e de tempo (500 ms servidor / 50 ms cliente) medidos sob ataque | **passou** | medidas `tempo_corte_relogio_50ms_python_ms` 50,63 · `..._javascript_ms` 53,65 · `tempo_corte_relogio_500ms_servidor_ms` **500,69** · `orcamento_de_passos_padrao` 10⁵ (o MESMO ataque, com o relógio folgado em 10⁶ ms, para em `limite_passos` — os dois orçamentos cortam de forma independente). Mais `test_expressao_seguranca.py` (16 casos: cadeia de 900 termos, 500 parênteses, 500 unários, 500 chamadas aninhadas, texto de 10 MB) |
| expressão que acessa camada de outro inquilino = erro de permissão | **NÃO PROVADA — fora desta passagem** | não existe camada ligada à expressão; não há caminho de acesso a camada para atacar. Escrito na seção 11 de `docs/EXPRESSAO.md` e no CHANGELOG. Fica com o L5-11 / L2-10 cheio |

## Medidas gravadas

`tests/medidas/L2-10-c-expressao.json` (nome do arquivo é o do núcleo, mantido para não duplicar o
registro do item; o gerador é `test_expressao_medidas.py`, que só grava com `PLAT_GRAVAR_MEDIDAS=1`):

`funcoes_implementadas` 43 · `vetores_de_equivalencia` 309 · `vetores_avaliados_sem_erro_no_lado_javascript`
309 · `vetores_ast_ida_e_volta_nos_dois_lados` 309 · `tempo_corte_relogio_50ms_python_ms` 50,63 ·
`tempo_corte_relogio_50ms_javascript_ms` 53,65 · `tempo_corte_relogio_500ms_servidor_ms` 500,69 ·
`orcamento_de_passos_padrao` 100000 · `tempo_ataque_cadeia_900_termos_ms` 4,18 ·
`tempo_ataque_string_10mb_ms` 19,15 · `tempo_ataque_500_parenteses_ms` 0,53.

## O que ficou de fora e por quê

- **Permissão de camada de outro inquilino**: não há camada. Não dá para atacar o que não existe.
- **Geometria** (`Area`, `Length`, `Distance`, `Centroid`, `Intersects`, `Within`, `Buffer`): pedem PostGIS
  no servidor e fórmula esférica no cliente, com tolerância declarada — os dois têm de dar o mesmo número,
  e isso é trabalho próprio, não sobra de uma passagem de linguagem.
- **`Filter`/`Map`/`Reduce`** (função por elemento) e `FeatureSetByRelationship`: mudam a forma da
  linguagem (valor-função) e o custo (uma expressão por elemento). Fora.
- **Domínio** (`DomainName`/`DomainCode`/`Subtypes`): dependem do metadado de campo do catálogo.
- **Integração popup / rótulo / formulário / regra de atributo (L5-11, L5-03-b)**: nenhum perfil ligado.
- **Fuso horário do usuário**: data continua epoch-ms UTC; `TextoData` também formata em UTC.
- **Máscara livre de formatação** (`#,###.00`, `DD/MM/Y`): `TextoNumero` tem casas decimais e `TextoData`
  tem 4 formatos fixos. Máscara livre é um mini-analisador a mais, escrito duas vezes.
- **Compilação para expressão MapLibre e para SQL**: não começada.
- Não foi criado arquivo de gerador dentro do repositório para a seção 10 (o gerador vive em
  `laco/handoffs/T3/codex-L2-10-c/gerar_paridade.py`), para não abrir arquivo novo fora da lista da
  trilha. Consequência honesta: a seção 10 NÃO tem teste de regeneração como a EBNF tem. Quem quiser
  fechar isso move o gerador para `docs/gerar_paridade.py` e escreve o teste, como `docs/gerar_limites.py`.

## Limitações honestas

1. Os tempos de corte (50,63 / 53,65 / 500,69 ms) foram medidos com a máquina em `load average` ≈ 5,7 e
   outras trilhas rodando pytest. São medidas SOB CARGA, o que é o caso interessante, mas variam entre
   rodadas: o portão é "corta com erro nomeado", não "corta em X ms exatos".
2. CORRIGIDO em 06/09 (o adversário conferiu contra o código e este texto estava errado, a favor do
   produto): o relógio é conferido em TODO passo, não a cada 256 — `_Contador.passo` (Python) e
   `Contador.passo` (JavaScript) leem o relógio a cada nó. Uma ÚNICA operação que custasse mais que o
   orçamento inteiro sem passar pelo contador escaparia; por isso `Unicos`, `Contem`, `Soma`, `Media` e
   `Juntar` cobram passo por elemento visitado, e é exatamente isso que o ataque de 21 milhões de
   comparações testa. O ataque 1 do adversário mediu o estouro do relógio de 50 ms no JavaScript em
   0,47 ms no pior caso, o que só se sustenta porque a conferência é a cada passo.
3. Paridade é de CAPACIDADE. Todo nome nosso é em português. Nenhum script Arcade roda aqui sem reescrita,
   e a seção 10 diz isso na primeira linha.
4. `make lint` e `make sem-marcador` REPROVAM na árvore hoje, mas por arquivos de OUTRA trilha não
   commitada (`app/conexao/rotas.py` 9 avisos, `app/conexao/proveniencia.py` 2, e um "TODOS" maiúsculo
   dentro de um comentário em `db/migracoes/036_conexao_saude_e_camada.sql`). Nos arquivos desta trilha:
   `venv/bin/ruff check app/expressao/avaliador_py.py tests/unit/test_expressao_*.py` → `All checks passed!`
   e `grep -nI -E -f tests/marcadores.regex` nos arquivos da trilha → nada.

## Para o adversário reproduzir

```bash
cd /home/dev/plataforma/enterprise
git show --stat cb92de9

# 1.413 casos, sem banco, ~3 min
flock /home/dev/plataforma/laco/.pytest.lock venv/bin/pytest \
  tests/unit/test_expressao_avaliador.py tests/unit/test_expressao_equivalencia.py \
  tests/unit/test_expressao_doc_sincronizada.py tests/unit/test_expressao_seguranca.py \
  tests/unit/test_expressao_extensao.py tests/unit/test_expressao_medidas.py -q -p no:randomly

# regravar as medidas (grava tests/medidas/L2-10-c-expressao.json)
PLAT_GRAVAR_MEDIDAS=1 flock /home/dev/plataforma/laco/.pytest.lock \
  venv/bin/pytest tests/unit/test_expressao_medidas.py -q -p no:randomly

# atacar à mão, com expressão própria, nos dois avaliadores
venv/bin/python -c "import sys;sys.path.insert(0,'.');from app.expressao.avaliador_py import avaliar_texto;print(avaliar_texto(\"SUA EXPRESSAO\", {}))"
echo '[{"entrada":"SUA EXPRESSAO","contexto":{}}]' | node tests/expressoes/executar_js.mjs --stdin

# a EBNF do documento tem de ser a do parser
venv/bin/python -c "import sys;sys.path.insert(0,'.');from app.expressao.avaliador_py import ebnf;print(ebnf())" | diff - <(sed -n '/^```ebnf$/,/^```$/p' docs/EXPRESSAO.md | sed '1d;$d')
```

Onde atacar (é aqui que eu apostaria contra mim mesmo):

1. **Uma operação cara que não cobre passo.** Achar uma função em que o custo cresça com o tamanho do
   dado sem que o contador de passos avance na mesma proporção (candidatas: `Replace` com busca curta em
   texto grande, `Split` com separador vazio, `Juntar` de lista longa, `Find` com busca longa). Se existir,
   o corte de 50 ms cai.
2. **Divergência Python × JavaScript fora dos 309 vetores.** Ponto flutuante em `TextoNumero` com muitas
   casas; `Arredondar` em valores como `x.5` binariamente inexatos; ordem de chave em dicionário na
   igualdade estrutural do `Contem`/`Unicos`/`Decode`; texto com par substituto (emoji) em `Left`/`Mid`/
   `Find` — o contrato diz PONTO DE CÓDIGO, e JavaScript conta UTF-16 por padrão.
3. **AST fabricada à mão** que o texto nunca produziria: nó com aridade fora do contrato, profundidade
   maior que a do parser, tipo de nó desconhecido, número não finito, chave repetida no JSON. Deve dar
   erro nomeado (`no_desconhecido`, `profundidade_excedida`, `aridade_invalida`), nunca exceção crua.
4. **Protótipo no lado JavaScript**: contexto criado com `Object.create`, getter, `Proxy`, `toJSON`.
   `test_js_nao_executa_getters_nem_le_prototipo` cobre três casos; achar o quarto.
5. **Crescimento de valor intermediário**: encadear `Concatenar`/`Replace`/`Split` para estourar memória
   ANTES de `valor_grande` disparar (os tetos são 1.024 itens, 4.096 nós, 20.000 pontos de código,
   profundidade 20 — o ataque é chegar perto de cada um deles várias vezes na mesma expressão).
6. **Honestidade da seção 10**: pegar 20 funções do Arcade function reference ao acaso e conferir se o
   estado escrito (feito/parcial/fora) corresponde ao que o código faz. Uma linha `feito` que não seja
   `feito` é o pior defeito desta entrega, porque vira promessa em documento de paridade.

## Commits

- `cb92de9db3ce60ca401227310b0c8a00ff6e42ee` — Linguagem de expressão: >=40 funções, >=200 vetores
  Python=JS, listas e dicionários, limites (item L2-10-c-linguagem-expressao). 12 arquivos,
  +4.406 / −217.
