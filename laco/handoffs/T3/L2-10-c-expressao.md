# Handoff — item L2-10-c-linguagem-expressao (arquiteto + backend, passagem única — NÚCLEO)

**Objetivo.** Construir o NÚCLEO da linguagem de expressão própria (equivalente ao Arcade da Esri
para os perfis popup, rótulo, cálculo, restrição, validação, visibilidade, indicador — item grande,
`L2_CONCEITO.md` decisão C6): gramática EBNF publicada, AST tipada exportável em JSON, e **dois
avaliadores que têm de concordar byte a byte** — Python (servidor) e JavaScript (navegador) — sobre
os MESMOS vetores de teste. Explicitamente FORA desta passagem: integração com popup, simbologia,
rótulo, formulário, regra de atributo (isso é `L5-11` e outros itens futuros do L2-10).

## O que fiz

- `docs/EXPRESSAO.md` (novo): EBNF completa (literais, `$campo`, aritmética `+ - * / % ^`,
  comparação `== != < <= > >=`, lógicos `&& || !`, condicional `Se(cond,a,b)`), tabela de tipos
  (número/texto/booleano/nulo; "data" é CONVENÇÃO — milissegundos desde a época Unix UTC, sem tipo
  dedicado, para os dois avaliadores não dependerem de biblioteca de fuso horário nenhuma das duas
  línguas), regras de propagação de nulo (semântica de três valores do SQL), curto-circuito,
  catálogo de 18 funções com 1 exemplo cada, os dois algoritmos que têm de ser byte-a-byte iguais
  (formatação de número, arredondamento meio-para-longe-de-zero), tabela de limites e catálogo de
  erros nomeados, formato da AST em JSON, paridade parcial com o Arcade function reference, e a
  lista nomeada do que fica fora desta passagem.
- `app/expressao/avaliador_py.py` (novo): tokenizador (mesmo padrão de `app/consulta/where_ast.py`
  — recusa, nunca ignora, caractere fora do vocabulário), parser recursivo descendente com
  precedência completa (`||` → `&&` → `==`/`!=` → comparação → `+`/`-` → `*`/`/`/`%` → `^` associa
  à direita → unário → primário), AST tipada em `dataclasses` (`Literal`, `Campo`, `Unario`,
  `Binario`, `Chamada`), `ast_para_json`/`ast_de_json`, avaliador (`avaliar`/`avaliar_texto`) contra
  um `contexto: dict` que o CHAMADOR passa — `$campo` fora dele é `campo_nao_permitido`, nunca
  `getattr` de objeto Python, nunca `vars()`/`globals()`. `TABELA_FUNCOES` com 18 entradas (texto:
  `Maiuscula`/`Minuscula`/`Concatenar`/`Texto`; número: `Arredondar`/`Absoluto`/`Minimo`/`Maximo`/
  `Numero`/`Potencia`; data: `AgoraUTC`/`Ano`/`Mes`/`Dia`/`DiferencaDias`; nulo: `SeNulo`/`EhNulo`;
  condicional: `Se`). Sem `eval`/`exec`/`compile`/`importlib` em lugar nenhum do módulo (provado por
  varredura AST em `test_expressao_seguranca.py`, não só grep).
- `web/js/expressao/avaliador.js` (novo, ES module puro, sem import de nada do resto do app):
  MESMO tokenizador/parser/AST/avaliador, escrito à mão em JavaScript, sem `eval`/`new Function`.
  `web/js/expressao/package.json` com `{"type":"module"}` — só para o Node dos testes entender o
  arquivo como ESM (nunca afeta o navegador, que decide módulo por `<script type="module">`).
- **Achado corrigido nesta mesma passagem** (não ficou para depois): uma cadeia longa do mesmo
  operador (`1+1+1+...+1`) é montada pelo parser em um `while` — nunca recursa por termo, então o
  contador de profundidade do PARSER nunca dispara — mas produz uma AST tão funda quanto o número
  de termos, e o AVALIADOR (que É recursivo em `v()`) estouraria a pilha do Python/JS nessa cadeia.
  Corrigido com uma segunda defesa: depois de montada, a árvore inteira é medida com PILHA
  EXPLÍCITA (nunca recursão) em `_profundidade_da_arvore`/`profundidadeDaArvore`, chamada dentro de
  `analisar()`. `ast_de_json`/`astDeJson` ganharam o mesmo limite (threading de um parâmetro de
  profundidade pela própria recursão de reconstrução) — sem isso, uma AST em JSON fabricada à mão
  (que é entrada tão não confiável quanto o texto, já que é isto que se grava no documento)
  contornaria os dois guarda-corpos do lado texto por inteiro.
- `tests/expressoes/vetores.json` (novo, 41 vetores — portão pede ≥ 20): compartilhado entre os
  dois avaliadores; `tests/expressoes/executar_js.mjs` (novo): runner Node que avalia cada vetor
  com `avaliador.js` e imprime JSON (`--nomes-funcoes` imprime só a lista de nomes de função, usada
  para conferir que as duas tabelas batem).
- `tests/unit/test_expressao_equivalencia.py` (novo): compara Python × JavaScript vetor a vetor,
  por ÍNDICE (não pelo texto da expressão — dois vetores podem ter o mesmo texto com contexto
  diferente; casar pelo texto juntaria o resultado errado com o vetor errado, bug que peguei e
  corrigi durante a construção, ver Riscos), com canonicalização de int/float documentada (JSON não
  distingue os dois; Python distingue) para a comparação ser byte a byte de verdade.
- `tests/unit/test_expressao_avaliador.py` (novo): gramática/precedência, propagação de nulo
  (tabela de três valores), catálogo de erros nomeados, as 18 funções (1 caso cada), curto-circuito,
  AST↔JSON.
- `tests/unit/test_expressao_seguranca.py` (novo): campo fora da lista branca (nenhum caminho
  indireto alcança o contexto), cadeia longa do mesmo operador, parênteses/unários/chamadas
  profundamente aninhados, string de 10 MB, muitos tokens, muitos argumentos variádicos, limite de
  passos sob largura (não profundidade), limite de tempo sob carga (árvore balanceada de 256 folhas
  para garantir trabalho suficiente até o relógio cortar — o relógio é conferido em TODO passo, não
  amostrado a cada 256; a frase original estava errada e foi corrigida em 06/09), varredura AST
  por `eval`/`exec`/`compile`/`__import__`, confirmação de que não há `getattr(` no módulo.
- `tests/unit/test_expressao_doc_sincronizada.py` (novo, mesmo padrão de `docs/gerar_limites.py`):
  toda função de `TABELA_FUNCOES` aparece em `EXPRESSAO.md` e vice-versa; as tabelas Python e
  JavaScript têm o mesmo vocabulário; ≥ 15 funções documentadas; todo código de erro que o código
  levanta (varredura AST) está no catálogo do documento.
- `tests/unit/test_expressao_medidas.py` (novo) grava `tests/medidas/L2-10-c-expressao.json` via
  fixture `medida` (ADR 0001 seção 10) — número de funções, vetores, tempos dos 3 ataques
  cronometrados, vetores concordantes no lado JavaScript.
- `docs/EXPRESSAO.md` seção "8. Catálogo de erros nomeados" e `ARQUITETURA.md`/`CHANGELOG.md`
  atualizados; `laco/estado.json` (`backlog[236]`): `estado="parcial"`, `tentativas=1`, `turno=3`,
  `portao_de_pronto` com o resumo do que foi feito e do que falta, `bloqueio` nomeado.

## Evidência (comando + saída literal)

```
$ cd /home/dev/plataforma/enterprise && venv/bin/ruff check app/expressao tests/unit/test_expressao_avaliador.py tests/unit/test_expressao_equivalencia.py tests/unit/test_expressao_seguranca.py tests/unit/test_expressao_doc_sincronizada.py
All checks passed!

$ flock /home/dev/plataforma/laco/.pytest.lock venv/bin/pytest tests/unit/test_expressao_avaliador.py tests/unit/test_expressao_equivalencia.py tests/unit/test_expressao_seguranca.py tests/unit/test_expressao_doc_sincronizada.py tests/unit/test_expressao_medidas.py -q
........................................................................ [ 32%]
........................................................................ [ 64%]
........................................................................ [ 97%]
......                                                                   [100%]
```

```
$ flock /home/dev/plataforma/laco/.pytest.lock env PLAT_GRAVAR_MEDIDAS=1 venv/bin/pytest tests/unit/test_expressao_medidas.py -q
.                                                                        [100%]
$ cat tests/medidas/L2-10-c-expressao.json
{
 "item": "L2-10-c-expressao",
 "medidas": {
  "funcoes_implementadas": {"valor": 18, "unidade": "funções"},
  "vetores_de_equivalencia": {"valor": 41, "unidade": "vetores"},
  "tempo_ataque_cadeia_900_termos_ms": {"valor": 3.81, "unidade": "ms"},
  "tempo_ataque_string_10mb_ms": {"valor": 19.56, "unidade": "ms"},
  "tempo_ataque_500_parenteses_ms": {"valor": 1.32, "unidade": "ms"},
  "vetores_avaliados_sem_erro_no_lado_javascript": {"valor": 41, "unidade": "vetores"}
 },
 "gerado_em": "2026-09-06T10:52:32Z",
 "git_sha": "c5135e5df6e6"
}
```

```
$ venv/bin/ruff check app tests docs/gerar_limites.py
E501 Line too long (122 > 120) — app/limites.py:111 (LDAP, item L0-08, OUTRA trilha em WIP; não
mexi neste arquivo)
```
(Lint do escopo próprio 100% limpo; a reprova em `make check` completo veio de um arquivo que
outra trilha estava editando ao vivo no mesmo repositório — ver Riscos.)

`make teste` (suíte inteira, `-m "not lento"`) rodou sob `flock` ao final da passagem:
`16 failed, 986 passed, 42 deselected in 261.78s`. **Nenhuma das 16 falhas menciona "expressao"**
(`grep -i express` no log devolve vazio) — todas são em `tests/api/test_cruzado.py` (rotas
`/api/org/ldap*`, `/api/login/ldap`), `tests/api/test_eventos.py`, `tests/api/test_funcoes_seguras.py`,
`tests/api/jobs/*` e `tests/api/catalogo/*`: a árvore tinha, ao mesmo tempo, outra trilha com
`app/auth/ldap.py` NOVO e NÃO COMITADO e `app/limites.py`/`app/main.py`/`app/db.py` modificados
(`git status` confirmado antes e depois desta passagem) — item L0-08/LDAP em WIP, alheio a este
item, não tocado por mim. `make check` completo reprovou primeiro no `lint` pelo mesmo motivo
(`app/limites.py:111`, linha de outra trilha). Isolado, os 5 arquivos de teste desta passagem
(`test_expressao_avaliador.py`, `test_expressao_equivalencia.py`, `test_expressao_seguranca.py`,
`test_expressao_doc_sincronizada.py`, `test_expressao_medidas.py`) rodam 100% verdes, como a
evidência acima mostra — a suíte inteira só não fecha "verde de ponta a ponta" por trabalho alheio
em curso no mesmo repositório compartilhado, não por nada desta passagem.

## Riscos

- **Bug que EU escrevi e corrigi antes de terminar**: a primeira versão de
  `test_expressao_equivalencia.py` casava vetor Python × resultado JavaScript pelo TEXTO da
  expressão; dois vetores («SeNulo com valor presente»/«ausente») têm o mesmo texto
  (`SeNulo($nome, 'sem nome')`) com contexto diferente — o dicionário por texto sobrescrevia um
  resultado com o outro, produzindo falso-negativo (`EhNulo`/`SeNulo` "discordando" quando na
  verdade o harness de teste é que estava errado, não os avaliadores). Corrigido casando por
  ÍNDICE/posição na lista, com um teste extra (`test_vetores_e_resultados_js_no_mesmo_numero_e_ordem`)
  que prova a correspondência. Registro para quem ler isto depois: NUNCA casar vetor por texto de
  expressão quando o mesmo texto pode aparecer com contexto diferente.
- **Achado de segurança real, corrigido nesta mesma passagem** (não é hipotético — reproduzi antes
  de corrigir): `ast_de_json`/`astDeJson` reconstruíam a árvore sem limite de profundidade nem de
  aridade. Como a AST em JSON é o que se grava no documento (C6), e nada garante que um JSON chegue
  só de `ast_para_json`, um JSON fabricado à mão com nós `binario` aninhados dezenas de milhares de
  vezes bypassava os dois guarda-corpos do lado texto (tamanho de texto, tokens, profundidade do
  parser) por inteiro. Fechado com o mesmo padrão do parser: profundidade contada a cada nível de
  reconstrução, erro nomeado (`profundidade_excedida`) antes de estourar a pilha.
- Esta passagem NÃO integra com nada (nenhuma rota nova, nenhuma tabela nova, nenhum acesso a
  camada) — o "campo fora do inquilino" da refutação do item-pai é testado como "campo fora da
  lista branca do `contexto`" (o equivalente possível hoje: não há camada ainda para tentar acessar
  fora dela). Quando a integração com camada/formulário existir, o teste real de "outro inquilino"
  terá de rodar contra ela.
- `TABELA_FUNCOES` tem 18 funções, não as ≥ 40 da hipótese cheia do item (faltam sinônimos como
  `Trim`/`Left`/`Right`/`Mid`/`Find`/`Split`/`Floor`/`Ceil`/`Sqrt`/`Weekday`/`Decode` e as funções de
  lista/domínio/geometria) — nomeado no `estado.json` como pendência, não escondido.
- `make check` completo (o alvo, não `check-rapido`) reprovou o `lint` por causa de
  `app/limites.py:111` (linha de 122 caracteres) — esse arquivo pertence ao item L0-08/LDAP, que
  outra trilha estava editando ativamente no mesmo repositório durante esta passagem (`git status`
  mostrava `app/auth/ldap.py` como novo, não commitado, e vários arquivos modificados fora do meu
  escopo). Não toquei nesse arquivo. O lint do MEU escopo (`app/expressao/`, os 5 arquivos de teste
  novos) está limpo, confirmado isoladamente.

## Pendências

- Todas nomeadas no `portao_de_pronto` atualizado do item em `estado.json` e na seção 11 de
  `docs/EXPRESSAO.md`: tipos lista/dicionário/geometria, ≥ 40 funções, ≥ 200 vetores, fuso horário,
  formatação pt-BR, compilação para expressão MapLibre e para SQL, integração com popup/rótulo/
  formulário/regra de atributo (`L5-11`), tabela de paridade Arcade completa.
- `app/limites.py:111` (linha longa) não é meu — sinalizado para quem estiver na trilha L0-08/LDAP
  ou para o gerente consolidar antes do próximo `make check` completo do turno.

## Para o próximo papel

`app/expressao/avaliador_py.py` está pronto para ser importado por qualquer rota futura de
popup/formulário/rótulo — o contrato é `avaliar(ast_ou_texto, contexto: dict, limite_passos=,
limite_ms=)`; `contexto` tem de vir dos atributos REAIS permitidos da camada/formulário (nunca uma
lista aberta), mesmo padrão de `where_ast.compilar_where(texto, colunas)`. `web/js/expressao/
avaliador.js` é o par exato para o cliente (popup, calculadora de formulário) — importar como ES
module, nunca reimplementar em JS de novo. Vetores novos entram só em `tests/expressoes/
vetores.json` (nunca duplicando texto de expressão com contexto diferente sem checar a comparação
por índice).

---

Commit: `a221ac4` — "Núcleo da linguagem de expressão própria (item L2-10-c-linguagem-expressao)"
(mensagem em português, escopo exatamente: `app/expressao/`, `web/js/expressao/`,
`docs/EXPRESSAO.md`, `tests/expressoes/`, `tests/unit/test_expressao_*.py`,
`tests/medidas/L2-10-c-expressao.json`, `ARQUITETURA.md`, `CHANGELOG.md` — 15 arquivos, nada de
outra trilha). `laco/estado.json`: `backlog[236]` (`estado="parcial"`) e ledger atualizados.
