# Handoff — item L5-05-documento-versoes (arquiteto + backend, passagem única)

**Objetivo.** Modelo genérico de "documento de construtor" (base para app/painel/formulário/fluxo do L5):
grafo JSON com ULID imutável por nó, versão imutável publicada por ponteiro, reaproveitando por inteiro o
mecanismo já entregue de L0-03 (`plat.item.dados`, `plat.tipo_item.esquema`, `plat.item_versao`) — nenhuma
tabela nova. Portão do `estado.json` e `laco/decomposicao/L5_CONCEITO.md` D2/D3 lidos antes de começar.

## O que fiz

1. **`app/catalogo/documento.py`** (novo): `ULID_RE` + `gerar_ulid()` (Crockford base32, 26 chars);
   `validar_grafo(tipo, dados)` — recusa (`422 grafo_invalido`) nó sem ULID, dois nós com o mesmo id, ou
   ligação apontando para id inexistente (o que JSON Schema puro não expressa: precisa olhar a lista
   inteira); `corpo_canonico`/`sha256_canonico` — hash À PARTE do `sha256` de `item_versao`, sobre
   `dados.corpo` numa forma reproduzível fora do banco (`json.dumps(sort_keys=True, separators=(",",":"))`,
   MEDIDO contra `sha256sum` de verdade); `migrar_para_leitura` — aplica `migrar_<tipo>_v<N>_v<N+1>` só na
   LEITURA, nunca grava de volta no banco.
2. **`db/migracoes/028_documento_grafo.sql`** (novo): bump `app`/`painel` de `esquema_versao` 1→2, esquema
   novo com `corpo.nos`/`corpo.ligacoes` OPCIONAIS (não `required`: os 1.573/1.571 itens já semeados em
   demo/demo2 com `corpo:{}` continuam válidos sem migração de escrita) + `corpo.mapas`/`mapa_id` mantidos
   (contrato já entregue de `app/catalogo/relacoes.py::_app`, item L0-03-i — quebrar isso quebraria
   "usado-por" de app/painel→mapa, achado ao ler o código antes de escrever o esquema).
3. **`app/catalogo/rotas_itens.py`**: `validar_grafo` chamado logo após `tipos.validar` em `criar` e no
   núcleo do PUT/PATCH; `ver()` migra o documento na leitura e registra evento `itens/esquema_migrado`
   (vocabulário novo, mesma migração 028); `GET /api/esquemas` + `GET /api/esquemas/{tipo}?versao=N` (serve
   o schema vigente ou histórico, de `docs/esquemas/`); `GET /api/itens/{id}/integridade` (recomputa em SQL
   `digest(corpo::text,'sha256')` de cada versão e compara com o `sha256` gravado); `_versao_json` ganhou
   `sha256_canonico`.
4. **`docs/gerar_esquemas.py`** (novo, mesma disciplina de `docs/gerar_limites.py`): espelha o esquema vigente
   de tipos com família em `documento.FAMILIAS_GRAFO` para `docs/esquemas/<tipo>-v<N>.json`, `--check` falha
   se divergir do banco. `docs/esquemas/{app,painel}-v1.json` são registro histórico, escritos à mão (a
   versão anterior à migração), nunca regerados.
5. Rotas novas cadastradas em `tests/api/cruzado_casos.py` (P6): `/api/esquemas`/`/api/esquemas/{tipo}` como
   vocabulário (`proprio=True`, mesmo padrão de `/api/tipos-item`); `/api/itens/{id}/integridade` como alvo
   padrão 401/403/404.
6. Documentação: ADR 0011, `MANUAL.md` §17, `ARQUITETURA.md` §14, `docs/PARIDADE.md` (5 linhas novas),
   `CHANGELOG.md` (entrada no topo).

## Evidência

```
$ flock /home/dev/plataforma/laco/.pytest.lock venv/bin/pytest -q tests/api/catalogo/test_documento.py
..........                                                               [100%]
$ flock ... venv/bin/pytest -q tests/api/catalogo/            # suíte inteira do catálogo
.........................F.............................................. [ 78%]
....................                                                     [100%]
# a única falha (test_eventos_e_seguranca.py::test_funcoes_do_catalogo_sem_public...) é de OUTRA trilha
# concorrente (029_ingestao_vetor.sql, funções 'importacao_*' sem REVOKE ainda) — não a toquei
$ flock ... venv/bin/ruff check app/catalogo/documento.py app/catalogo/rotas_itens.py \
    tests/api/catalogo/test_documento.py docs/gerar_esquemas.py
All checks passed!
$ venv/bin/python docs/gerar_esquemas.py --check
docs/esquemas em dia (2 arquivo(s))
$ ! grep -rnI -E -f tests/marcadores.regex <meus arquivos>   -> limpo (sem marcador)
```
Medida: mediana de 30 `PUT /api/itens/{id}` (painel, 2 nós) = **17,3 ms**
(`tests/medidas/L5-05-documento-versoes.json`).

**Refutação do portão** (adversário = eu mesmo, item pequeno o bastante para caber na mesma passagem):
`test_no_sem_ulid_e_ulid_repetido_e_ligacao_pendente_sao_recusados` — dois nós com o mesmo id E ligação
apontando para id inexistente, os dois recusados, na criação E no PUT. `test_integridade_acusa_linha_de_
versao_editada_direto_no_banco` — edita `plat.item_versao.corpo` via `sudo -u postgres psql` (superusuário
real, porque `plat_app` tem INSERT/UPDATE/DELETE revogados nessa tabela desde a 011 — provado por
`test_plat_app_nao_pode_editar_item_versao` antes) e confere que `/api/itens/{id}/integridade` acusa.

## Riscos / limites conhecidos

- **Achado tardio (depois deste handoff escrito), não meu para consertar**: rodando `tests/api/catalogo/
  test_documento.py` sozinho, os 10 testes passam (`..........`) mas a limpeza de FIM DE SESSÃO (fixture
  `itens_a`/`usuarios_a`, compartilhada por todo `tests/api/catalogo/`, dona é L0-03) agora ERRA ao expurgar
  itens `zt-*` de sessões anteriores: `ForeignKeyViolation: importacao_arquivo_id_fkey` — outra trilha viva
  neste turno (`029_ingestao_vetor.sql`) criou `plat.importacao.arquivo_id → plat.item` sem `ON DELETE
  CASCADE`/expurgo próprio, e o acúmulo de `zt-*` de ~10 trilhas rodando testes ao mesmo tempo faz a limpeza
  esbarrar num item que virou "arquivo de importação" de outra suíte. Não é bug do meu item (nenhuma
  asserção minha falha; é teardown de fixture alheia) — fica nomeado para quem fechar o turno: ou a trilha de
  ingestão adiciona seu próprio expurgo, ou `_expurgar_zt` (L0-03) aprende sobre a tabela nova.
- `docs/openapi.json` NÃO foi regenerado: outra trilha (`app/catalogo/metadado.py`) estava regravando o
  mesmo arquivo ao vivo quando eu testei `make openapi` (842 linhas de diff, a maioria não minha) — revertido
  de propósito. Fica para a integração final do turno (mesma decisão que a trilha do metadado já tinha
  registrado em `docs/PARIDADE.md` para o caso dela).
- `docs/LIMITES.md`/`app/limites.py` estão desalinhados (`docs/gerar_limites.py --check` falha) por causa de
  OUTRA trilha em andamento (`app/limites.py` modificado, não commitado) — não toquei nenhum dos dois.
- `formulario`/`fluxo` continuam com envelope trivial de propósito: a forma dos nós é decisão dos itens que
  os constroem (L5-02, L5-03); só precisam entrar em `documento.FAMILIAS_GRAFO` quando decidirem.

## Para o próximo papel

Testador/adversário independente: rodar de novo com o banco em uso normal (não isolado) e tentar achar um
terceiro jeito de burlar `validar_grafo` (por exemplo, nó dentro de uma `ligacao` aninhada, ou array de nós
não-lista via injeção de tipo). Cronista: quando `docs/openapi.json` for regenerado no fechamento do turno,
conferir que as 3 rotas novas aparecem certas (`x-privilegio: vocabulario` nas duas de `/api/esquemas`).

## `make check` (escopo do item)

Ver evidência acima — a suíte do item e a suíte inteira de `tests/api/catalogo/` passam (uma falha alheia,
nomeada); `ruff`/`gerar_esquemas.py --check`/sem-marcador limpos nos meus arquivos.

## Commit

`cc5f81d` — "Documento de construtor: grafo de nós com ULID sobre o versionamento do catálogo (item
L5-05-documento-versoes)", 16 arquivos, 1.122 inserções, 4 remoções. `ARQUITETURA.md`/`CHANGELOG.md`/
`MANUAL.md`/`docs/PARIDADE.md`/`tests/api/cruzado_casos.py`/`app/catalogo/rotas_itens.py` estavam com diffs
de outras trilhas no working tree no meio da sessão (concorrência real, turno com ~10 trilhas ao vivo) — as
outras já tinham commitado o próprio trabalho ANTES do meu commit (verificado com `git diff HEAD -- <arquivo>`
em cada um: diff limpo, só meu, sem hunk alheio) — nenhuma técnica de isolamento de staging foi necessária
desta vez.

## Resumo (8 linhas)

Grafo JSON com ULID por nó sobre o mecanismo de versão já entregue de L0-03 (nenhuma tabela nova):
`validar_grafo` recusa id duplicado/ligação pendente/ULID inválido; migração de esquema (`028_documento_
grafo.sql`, app/painel v1→v2) aplicada só na LEITURA e registrada em evento; `sha256_canonico` é um hash
verificável fora do banco (o `sha256` de `item_versao` não é, MEDIDO); `/api/esquemas` serve o JSON Schema
vigente; `/api/itens/{id}/integridade` acusa edição direta em `plat.item_versao` (só superusuário consegue,
`plat_app` tem os privilégios revogados desde a 011). 10 testes verdes, `sha256sum` externo bate byte a
byte, RLS cruzado provado. Pendência: `docs/openapi.json`/`docs/LIMITES.md` ficaram para o fechamento do
turno (outras trilhas os regravavam ao vivo).
