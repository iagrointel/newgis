# L2-10-c-linguagem-expressao — conserto das refutações (06/09/2026)

Laudo consertado: `laco/handoffs/T3/L2-10-c-ADVERSARIO.md` (veredito REFUTADO, 38 testes
`xfail(strict=True)` em `tests/unit/test_expressao_adversario.py`, commit 61bfce5).
Árvore: `/home/dev/plataforma/enterprise` (ramo `master`). Commits deste conserto:

- `4a0524f` — código, vetores, documento e testes.
- `561f809` — `tests/medidas/L2-10-c-expressao.json` regravado DEPOIS do commit do código.

Prova geral, um comando (sem banco, sem flock):

```
$ venv/bin/pytest tests/unit/test_expressao_*.py
1652 passed in 3.68s        (EXIT=0)
$ venv/bin/pytest tests/unit/test_expressao_adversario.py
113 passed in 1.41s         (75 que já passavam + os 38 que eram xfail; 0 xfail restante)
```

Nenhum teste do adversário foi apagado, e nenhuma asserção dele ficou mais frouxa. Onde a marca
`xfail` saiu, a asserção ficou MAIS estreita (está dito caso a caso abaixo).

---

## Achado 1 (ALTA) — a equivalência quebrava fora dos 309 vetores (26 casos)

**Conserto.** As quatro operações que os dois lados entregavam ao operador ou à biblioteca da língua
passaram a ser do CONTRATO, escritas à mão nos dois lados e publicadas em `docs/EXPRESSAO.md`
**§3.1 "Convenções fixadas"** (seção nova; o documento não fixava sinal de resto nem unidade de texto):

| convenção escolhida | onde | como |
|---|---|---|
| resto `%` com o sinal do **DIVIDENDO** (truncado, como JavaScript/C/SQL) | `avaliador_py.py` `_binario` | `math.fmod(a, b)` no lugar do `%` do Python; o lado JavaScript já era assim |
| texto medido/cortado/comparado/casado em **PONTO DE CÓDIGO**, com par substituto alto+baixo contando como UM | `_texto_pareado` (py) · `compararTexto`, `acharAlinhado`, `dividirAlinhado` (js) | o Python normaliza todo texto em `_valor_seguro` (`encode/decode utf-16`, só quando há substituta); o JavaScript compara `< <= > >=` e faz `Find`/`Split`/`Replace` por ponto de código, recusando casamento que parta um par |
| `Numero` aceita **só algarismo ASCII** | `avaliador_py.py` | `\d` → `[0-9]` (o `\d` do Python casa dígito de qualquer escrita) |
| data arredonda **sempre para baixo** | `_ano_mes_dia_utc` (py) · `anoMesDiaUtc` (js) | `floor` do milissegundo antes de qualquer conta, nos dois lados |

**Prova.** Os 26 casos convergiram para o mesmo valor nos dois avaliadores e viraram vetor
compartilhado em `tests/expressoes/vetores_convergencia.json` (30 vetores: 26 + `AgoraUTC` + 3 de
`TextoNumero`), rodados junto dos 309 pelo teste de equivalência.

```
$ venv/bin/pytest tests/unit/test_expressao_equivalencia.py tests/unit/test_expressao_paridade.py
1368 passed        (339 vetores × 4 conferências + paridade)
$ venv/bin/python -c "...avaliar_texto('(0-7) % 3',{})" → -1
$ echo '[{"entrada":"(0-7) % 3","contexto":{}}]' | node tests/expressoes/executar_js.mjs --stdin → -1
```

O arquivo novo existe para NÃO mexer em `vetores.json`: o teste
`test_ataque_7_contagem_independente_de_funcoes_e_vetores` do adversário confere `len(vetores) == 309`
e `test_casos_do_adversario_sao_novos` confere que nenhum caso dele está lá. Acrescentar os 26 ao
arquivo antigo quebraria os dois — o arquivo separado cumpre a ordem ("acrescente esses 26 casos aos
vetores compartilhados") sem afrouxar teste nenhum.

No teste do adversário, a marca saiu e a asserção ficou mais estreita: além de `py == js`, o valor
comum tem de ser exatamente o da tabela `CONVERGENCIA_APOS_CONSERTO` (§3.1). A tabela
`DIVERGENCIAS_MEDIDAS` dele ficou no arquivo como registro do que se media antes.

## Achado 2 (ALTA) — exceção crua em `TextoNumero`

**Conserto.** Duas camadas: (1) `_decimal_fixo` passou a rodar dentro de `decimal.localcontext()` com
`prec = 60` — o contexto padrão de 28 dígitos era a causa (1e20 com 8 casas já estoura; o teto do
contrato é 1e21 com 15 casas = 36 dígitos); (2) `avaliar` passou a capturar `decimal.DecimalException`
junto de `OverflowError/ValueError/ZeroDivisionError`, devolvendo `numero_invalido` — rede para
qualquer estouro de `Decimal` que apareça depois.

**Escolha declarada:** o lado Python passou a FORMATAR (igual ao `toFixed` do JavaScript) em vez de os
dois devolverem erro nomeado. O pedido era "erro nomeado, e confira que o JavaScript devolve o mesmo
código"; entre errar dos dois lados e acertar dos dois, acertar é melhor — e obriga o JavaScript a
nada. A asserção do adversário ficou mais estreita: além de não subir exceção crua, o texto do Python
tem de ser byte a byte o do JavaScript nos cinco casos (1e13/15, 1e14/14, 1e20/8, 1e20/15, 1e15/14).

```
$ venv/bin/python -c "...avaliar_texto('TextoNumero($x,15)',{'x':1e13})"
10.000.000.000.000,000000000000000        (antes: decimal.InvalidOperation crua)
```

## Achado 3 (ALTA) — a tabela de paridade estava desonesta

**Conserto.** A tabela INTEIRA (134 linhas em 7 categorias) foi revista com o critério estreito, agora
escrito no próprio documento: `feito` = nenhuma diferença conhecida contra a documentação oficial E
pelo menos um vetor de teste da nossa função. As 6 linhas derrubadas pelo adversário viraram `parcial`
com a diferença escrita (`Month` 0-11 × 1-12 · `Now` hora local × UTC · `Abs` nulo→0 × `tipo_invalido`
· `Reverse` no lugar × cópia · `Back`/`Front` falham em lista vazia × devolvem nulo), e mais 12 caíram
pelo mesmo critério: `Concatenate` (lista+separador é o nosso `Juntar`), `Count`/`Find`/`Left`/`Mid`/
`Right` (ponto de código, §3.1), `Pow` (teto de expoente), `Sqrt` (NaN × `numero_invalido`),
`Day`/`Year`/`Weekday` (sempre UTC, sem fuso do contexto) e `DefaultValue` do dicionário (mapeava para
`Obter`, que não é `DefaultValue`; o equivalente é o `SeNulo`). **29 feito · 24 parcial · 81 fora →
11 feito · 42 parcial · 81 fora.** `docs/PARIDADE.md` foi atualizado com as mesmas contagens.

**Prova / trava contra a volta da mentira** — `tests/unit/test_expressao_paridade.py` (novo, 5 testes):

1. toda linha `feito` precisa de vetor em `vetores*.json` que chame a nossa função;
2. a contagem no cabeçalho de cada categoria tem de bater com as linhas contadas;
3. o total do parágrafo de abertura idem;
4. `docs/PARIDADE.md` tem de repetir as mesmas contagens;
5. nenhuma linha `feito` pode ter, na própria observação, palavra que declare diferença ("o Arcade",
   "não", "sem", "só", "em vez") — foi assim que `Reverse | feito | devolve cópia` sobreviveu.

O teste do adversário sobre `DefaultValue` registrava a contradição (`["feito","parcial"]`); agora
exige `["parcial"]` — mais estreito, não mais frouxo.

## Achado 4 (BAIXA) — contexto `Proxy` no JavaScript e campo extra no nó

**Conserto (contexto).** `contextoSimples()` no `avaliar` do JavaScript: recusa o que não é objeto,
o que é lista e o que tem protótipo diferente de `Object.prototype`/`null` — e, no Node, recusa `Proxy`
por `util.types.isProxy` (import dinâmico protegido por `try/catch`). Nenhuma armadilha do `Proxy`
chega a rodar (o teste do adversário exige contador em zero). **Limitação honesta, escrita em
`docs/EXPRESSAO.md` §7: no NAVEGADOR não existe forma portátil de detectar um `Proxy`** — qualquer
verificação que o denunciasse (`in`, `Object.keys`, `getOwnPropertyDescriptor`) já dispara a armadilha.
Lá a defesa continua sendo o contrato (quem monta o contexto é a aplicação), a lista branca por campo e
a leitura por descritor, que nunca executa getter. Essa assimetria está declarada, não escondida.

**Conserto (campo extra).** `ast_de_json` (py) e `astDeJson` (js) passaram a RECUSAR nó com campo
desconhecido (`no_desconhecido`) em vez de ignorá-lo — a forma do nó é fechada. De quebra, a
importação no JavaScript passou a ler cada campo por `Object.getOwnPropertyDescriptor`, então uma AST
entregue como `Proxy` não dispara nem o `get`.

**Discordância registrada, teste mantido:** o teste `test_ataque_3_campo_extra_no_no_e_ignorado_nos_
dois_lados` afirmava o comportamento TOLERANTE (`avaliar(...) == 7`). Corrigir o defeito o derruba
necessariamente. Não apaguei: reescrevi a mesma entrada para exigir a RECUSA nos dois lados (mais
estreito) e a manter a prova de que o nó bem formado continua avaliando e o protótipo não é poluído.
O nome passou a `..._e_recusado_nos_dois_lados`. Foi a única mudança de sentido em teste do adversário,
e ela vai na direção que o laudo pedia ("está registrado, porque uma AST assinada com campo extra não
é rejeitada").

## Achado 5 — imprecisões do handoff anterior

- "o relógio é conferido a cada 256 passos" era FALSO (a favor do produto): os dois avaliadores leem o
  relógio em TODO passo. Corrigido em `L2-10-c-expressao-extensao.md` (limitação 2) e em
  `L2-10-c-expressao.md` (descrição do teste de segurança), com a correção datada.
- `tests/medidas/L2-10-c-expressao.json` carimbava o commit anterior porque era gerado antes de
  commitar. Regravado com `PLAT_GRAVAR_MEDIDAS=1` DEPOIS do commit do código: `git_sha` agora é
  `4a0524ff5c58` = o commit que contém o código descrito, e o arquivo ganhou o campo `observacao`
  dizendo essa regra. Duas medidas novas: `vetores_de_convergencia_pos_adversario` = 30 e
  `linhas_feito_na_paridade_arcade` = 11 de 134.

---

## O que este conserto NÃO resolve (fronteira honesta)

1. **Não prova equivalência universal.** Prova equivalência em 339 vetores (309 + 30) e nos 54 casos do
   arquivo do adversário. A regra que ficou vale para o futuro: toda operação entregue ao operador ou à
   biblioteca da língua é candidata a divergir — `Trim`, por exemplo, ainda usa `strip()` do Python
   contra `trim()` do JavaScript, que aparam conjuntos de espaço diferentes fora do ASCII; não foi
   medido divergindo, e não está fixado em §3.1.
2. **`Proxy` no navegador continua indetectável** (achado 4 acima). A igualdade de contrato entre os
   dois avaliadores vale integralmente no Node e parcialmente no navegador.
3. **A paridade continua sendo de CAPACIDADE, não de execução.** Nenhum script Arcade roda aqui. As 11
   linhas `feito` agora têm vetor, mas a conferência contra a documentação oficial foi feita por
   leitura humana, não por teste automático contra o produto da Esri.
4. **A linguagem continua sem rota.** `grep -rn "avaliador_py" app/` só acha o próprio módulo — tudo
   isto é biblioteca, não superfície exposta.
5. **O custo do texto em ponto de código não foi remedido sob ataque.** As funções novas (`compararTexto`,
   `acharAlinhado`, `dividirAlinhado`) têm caminho rápido quando não há substituta no texto, que é o caso
   comum; o ataque 1 do adversário continua passando (`test_ataque_1_*`), mas ele não tem caso de
   comparação de dois textos de 20.000 pontos de código com substituta.

## Como reproduzir

```bash
cd /home/dev/plataforma/enterprise
venv/bin/pytest tests/unit/test_expressao_*.py            # 1.652 passed, 0 xfail
venv/bin/pytest tests/unit/test_expressao_adversario.py   # 113 passed (os 38 xfail viraram passe)
git show --stat 4a0524f 561f809
```

## Arquivos tocados

`app/expressao/avaliador_py.py` · `web/js/expressao/avaliador.js` ·
`tests/expressoes/vetores_convergencia.json` (novo) · `tests/unit/test_expressao_paridade.py` (novo) ·
`tests/unit/test_expressao_adversario.py` · `tests/unit/test_expressao_equivalencia.py` ·
`tests/unit/test_expressao_medidas.py` · `docs/EXPRESSAO.md` · `docs/PARIDADE.md` · `CHANGELOG.md` ·
`tests/medidas/L2-10-c-expressao.json` · (fora do repositório) os dois handoffs anteriores do item.
