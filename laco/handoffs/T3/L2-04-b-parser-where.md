# Handoff — item L2-04-b-parser-where-ast (arquiteto + backend, passagem única)

**Objetivo.** Parser próprio e isolado de `where`/CQL2 restrito (subconjunto: `campo operador
valor` com `=,!=,<,<=,>,>=,in,like,is null,and,or`, parênteses) → AST tipada → SQL parametrizado
contra lista branca de colunas do chamador. Sem `eval`/`exec`, sem interpolação de texto do usuário
em SQL. Sem tabela de mapa, sem integração de rota — infraestrutura pura para o L2-04-servicos-esri-
ogc e para L7-03-d-injecao-consulta (que já lista `L2-04-b-parser-where-ast` como dependência no
`estado.json`).

**Decisão de arquitetura (motivo, não moda).** `L2_CONCEITO.md` seção C7 já registra a decisão:
CQL2-JSON como AST interna canônica e "um único gerador de SQL parametrizado é o ponto de auditoria
de injeção", citando o `_where_seguro` por expressão regular do SIG de teste interno como frágil
(recusa funções e datas). Este item entrega esse gerador para o subconjunto `where`, em duas etapas
separadas — `analisar()` (só sintaxe → AST) e `compilar()` (só semântica de segurança: cada campo da
AST é validado contra a lista branca ANTES de virar texto de coluna) — para que o mesmo tipo de AST
sirva de alvo, mais adiante, a um tradutor CQL2-JSON/FES sem reescrever o gerador de SQL. Não achei
menção literal a "where/AST perigoso" nos handoffs de L0-05-jobs em `laco/handoffs/T2/` (busca por
"AST"/"injeç"/"where perigoso" não encontrou nada além de SQL comum de teste); o achado real e
correlato mora em `L7-03-d-injecao-consulta`, que já depende deste item e cita exatamente o mesmo
desenho (parser → AST → SQL parametrizado, lista branca de colunas/funções).

## O que fiz

- `app/consulta/where_ast.py` (novo, isolado): tokenizador que recusa (nunca ignora) qualquer
  caractere fora da gramática — é isso que fecha `;`, `--`, `/* */`, `#`, `~`; analisador descendente
  recursivo (`_Parser`) produz AST tipada (`Comparacao`, `E`, `Ou`); `compilar(no, colunas)` resolve
  cada campo contra a lista branca do chamador (`dict` nome→expressão SQL de confiança, ou
  `set`/`list` de nomes validados por regex de identificador) e só então gera texto SQL — todo valor
  literal vira parâmetro `%s`, nunca concatenado. Limites de negação-de-serviço: 4000 caracteres,
  400 tokens, 20 níveis de parênteses. `compilar_where(texto, colunas)` é o atalho de um passo.
- `app/consulta/__init__.py`: reexporta a API pública do módulo.
- `tests/unit/test_where_ast.py`: 39 casos (bem acima do mínimo de 15), organizados em três blocos:
  consultas legítimas (todos os operadores, `IN`, `LIKE`, `IS [NOT] NULL`, precedência AND-antes-de-
  OR, mapeamento de coluna para expressão diferente do nome no filtro), ataques (SQLi clássico com
  string fechada — vira parâmetro, nunca aparece no `sql`; `;` fora de string; comentário `--`;
  tautologia `1=1` e `'1'='1'` — recusadas porque a gramática exige identificador do lado do campo;
  campo fora da lista branca; injeção dentro de uma lista `IN`; `IN` vazio; string sem fechamento;
  caractere não reconhecido; aninhamento acima/no limite; texto acima do tamanho máximo; nome de
  coluna inválido no `set`) e duas garantias estáticas (módulo não usa `eval`/`exec`/`.format` para
  montar SQL; a AST é tipada antes de compilar).
- Portão do usuário (consulta-espelho): `test_consulta_legitima_complexa_3_condicoes_and_or_parenteses`
  compara literalmente SQL e parâmetros esperados para
  `(idade >= 18 AND idade <= 65) OR (uf = 'SP' AND status != 'inativo')`.

## Evidência (comando + saída literal)

```
$ cd /home/dev/plataforma/enterprise && flock /home/dev/plataforma/laco/.pytest.lock venv/bin/pytest tests/unit/test_where_ast.py -v
...
collected 39 items
tests/unit/test_where_ast.py .......................................     [100%]
39 passed in 0.08s
```

```
$ cd /home/dev/plataforma/enterprise && flock /home/dev/plataforma/laco/.pytest.lock make check-rapido
venv/bin/ruff check app tests
All checks passed!
! grep -rnI ... -f tests/marcadores.regex app web db docs deploy install.sh Makefile requirements.txt pyproject.toml *.md
venv/bin/pytest -m "not lento"
...
651 passed, 25 deselected, 5 warnings in 215.33s (0:03:35)
[exited com código 0]
```

(A suíte inteira passou, não só o item; os 25 `deselected` são os marcados `lento`, fora do escopo
do `check-rapido`. Rodei sob `flock` — havia OUTRAS trilhas mexendo em `app/limites.py`,
`app/main.py`, `app/acervo/` e `db/migracoes/021_acervo_ficha.sql` ao mesmo tempo neste mesmo
repositório; nada disso é meu e nada foi tocado ou comitado por mim.)

## Riscos

- O portão de pronto FORMAL deste item, por desenho (`estado.json`), só se fixa quando
  `L2-04-servicos-esri-ogc` (o item pai que consome isto) entrar; o que passou aqui é o portão
  operacional dado pelo pedido: injeção recusada/neutralizada, consulta legítima com o SQL certo,
  ≥15 casos. Isso não substitui a refutação formal do item pai quando ele for construído.
- `compilar()` aceita `colunas` como `dict` (nome→expressão de confiança do desenvolvedor) OU
  `set/list` (nome→identificador entre aspas, validado por regex). A segunda forma confia que o
  regex de identificador (`^[A-Za-z_][A-Za-z0-9_]*$`) é suficiente para colocar o nome em SQL sem
  escaping adicional — é o mesmo padrão do `CAMPOS_TEXTO`/`CAMPOS_EXATOS` hardcoded de
  `app/catalogo/busca.py`, aqui parametrizado porque o chamador (camada por camada) muda.
  Nenhum destes dois caminhos aceita nome vindo do usuário sem checagem.
- Este parser NÃO resolve `outFields`/`orderByFields`/`groupByFieldsForStatistics`/`outStatistics`
  (mencionados no `L7-03-d-injecao-consulta`) nem funções (data, matemática); ficou fora de propósito
  — o item pediu só `where`. Quando o L2-04-servicos-esri-ogc ou o L7-03-d entrarem, precisam de
  validação equivalente para esses parâmetros (mesma ideia: lista branca, nunca lista livre).
- Não escrevi ADR em `docs/adr/`: o próprio item registra que "portão a fixar pelo arquiteto no
  turno em que o item que a pediu entrar" — decidi documentar a decisão de desenho aqui e em
  docstring do módulo, e deixar o ADR formal para quando `L2-04-servicos-esri-ogc` abrir (vai
  precisar decidir CQL2-text/FES XML → mesma AST, o que este módulo já deixa pronto para receber).

## Pendências

- Nenhuma dependência declarada no item (`dependencias: []`); nenhum bloqueio.
- Integração em rota, tradutor CQL2-text/FES XML → mesma AST, e validação de `outFields`/
  `orderByFields`/`outStatistics` ficam para quando `L2-04-servicos-esri-ogc` ou `L7-03-d-injecao-
  consulta` entrarem — registrado acima, não travou este turno.

## Para o próximo papel

`app/consulta/where_ast.py` está pronto para ser importado por qualquer rota futura via
`compilar_where(texto, colunas)`; `colunas` tem de vir do esquema real da camada (nunca de uma
lista aberta) — é o contrato que L2-04-servicos-esri-ogc e L7-03-d-injecao-consulta esperam.

---

Commit: ver `git log` do repositório `/home/dev/plataforma/enterprise` (mensagem em português,
escopo só `app/consulta/` e `tests/unit/test_where_ast.py`).
