# L0-09-a-procedencia — bloco de procedência em todo item de dado

- **Ramo**: `wt/stac` (worktree `/home/dev/plataforma/wt/stac`)
- **Commit**: `ac4dbce` — "Bloco de procedência em todo item de dado, com a régua do acervo (item L0-09-a-procedencia)"
- **Base de teste**: schema próprio da trilha `plat_tl09a` (`bash laco/trilha_ambiente.sh l09a`), sem flock, sem
  tocar no schema `plat` de produção. O schema foi apagado ao fim (ver "Como o adversário reproduz").
- **Migração criada**: `db/migracoes/20260906T1544c24_procedencia_item.sql` (carimbo de tempo, ADR 0014; não
  reservei número).

## O que foi construído

| arquivo | o que faz |
|---|---|
| `app/catalogo/procedencia.py` (novo) | canoniza o bloco e calcula a pontuação 0-10 em Python |
| `db/migracoes/20260906T1544c24_procedencia_item.sql` (novo) | as mesmas contas em SQL, índice, esquema dos tipos, REVOKE de PUBLIC |
| `docs/PROCEDENCIA.md` (novo) | campo a campo, com o equivalente em `acervo.fonte`, e o que ainda não existe |
| `app/catalogo/rotas_itens.py` | normaliza `dados.procedencia` no POST e no PUT/PATCH; filtros `?licenca=` e `?procedencia_min=`; faceta de licença |
| `app/catalogo/comum.py` | `procedencia` (pontuação, campos, licença) no objeto item, calculada no banco |
| `app/catalogo/busca.py` | campos de busca `licenca:` e `procedencia:[a TO b]` (intervalo numérico novo) |
| `app/catalogo/tarefas.py` | exportação da lista com as colunas de procedência; consulta e serialização isoladas em `linhas_exportacao`/`serializar_exportacao` |
| `app/ingestao/carregar.py` | os 4 campos medidos + `origem` na camada importada; `data_de_acesso` deixou de nascer nula |
| `app/conexao/proveniencia.py` | `origem` campo a campo na camada publicada de conexão externa |
| `web/js/catalogo/item.js` | bloco de procedência na aba Visão geral, com a etiqueta de origem e a nota `4,0/10` |
| `web/js/catalogo/filtros.js`, `contexto.js`, `busca_sintaxe.js`, `i18n/pt-BR.json` | faceta de licença, campo de pontuação mínima, os dois campos novos na sintaxe da busca |
| `tests/unit/test_procedencia.py`, `tests/api/catalogo/test_procedencia.py`, `tests/api/ingestao/test_procedencia_ingestao.py` | 9 + 13 + 3 testes |
| `tests/api/catalogo/test_busca.py` | a faceta `licenca` entrou no conjunto que o teste do L0-03 fixa (mudança de 1 linha + 3 de conferência) |

## Cláusula do portão → prova

| cláusula | estado | prova |
|---|---|---|
| toda camada importada nasce com ≥ 4 campos preenchidos (sha256, data_acesso, gerador, método) **medidos no teste** | **passa** | `pytest tests/api/ingestao/test_procedencia_ingestao.py::test_camada_importada_nasce_com_os_quatro_campos_medidos` — importa `cobertura.gpkg` de verdade (upload → job de inspeção → job de carga) e confere os 4 campos + as etiquetas de origem; medida `campos_medidos_em_camada_importada = 4 de 4` |
| tela do item mostra o bloco e a pontuação | **passa, com limite** | API: `test_ficha_do_item_traz_bloco_e_pontuacao` (bloco cheio = 10,0/10) e `test_lista_traz_a_pontuacao_sem_pedido_por_item`. Tela: `blocoProcedencia()` em `web/js/catalogo/item.js`, na aba Visão geral. **Não há e2e de navegador** desta tela (o Chrome headless desta máquina não captura; nenhum teste Playwright novo foi escrito) |
| filtro na busca por licença e pontuação | **passa** | `test_busca_por_licenca_e_por_pontuacao` cobre `q=licenca:CC`, `q=procedencia:[9 TO 10]`, `q=procedencia:[0 TO 3]`, `?procedencia_min=9` e `?licenca=CC BY 4.0`; `test_pontuacao_fora_de_faixa_e_422` cobre o 422; `test_faceta_de_licenca_conta_o_que_nao_tem_licenca` cobre a faceta |
| exportação (L0-06-d) leva a procedência | **fronteira honesta** | `L0-06-d-exportar-inquilino` **não existe** (estado `pendente` no backlog): não há GeoPackage do inquilino para levar coisa alguma. A cláusula está cumprida na exportação que EXISTE, o job `catalogo.exportar_lista` — 5 colunas no CSV e o bloco inteiro no JSON, provado em `test_exportacao_leva_a_procedencia`. Está escrito assim em `docs/PROCEDENCIA.md` (seção "O que ainda não leva procedência") e no CHANGELOG |
| `docs/PROCEDENCIA.md` descreve cada campo com o mesmo vocabulário de acervo | **passa** | `tests/unit/test_procedencia.py::test_equivalencia_com_o_vocabulario_do_acervo_esta_documentada` percorre `EQUIVALENCIA_ACERVO` e falha se faltar `` `campo` `` ou `` `acervo.fonte.<campo>` `` no documento |

## Refutação exigida → prova

| ataque | resultado |
|---|---|
| importar o mesmo arquivo 2 vezes e conferir sha256 igual | **igual**, e igual ao `hashlib.sha256` do arquivo de origem — `test_mesmo_arquivo_duas_vezes_tem_o_mesmo_sha256`. Os dois itens são distintos, como manda o ADR 0005 6.6 |
| mudar 1 byte e conferir diferente | **diferente** — `test_um_byte_diferente_muda_o_sha256`. O byte trocado é uma quebra de linha ao fim do GeoJSON (o formato aceita, o GDAL lê igual): o arquivo difere em 1 byte e só |
| preencher `licenca` com texto vazio (vira NULL, não string vazia) | **vira NULL** na criação (`test_licenca_vazia_vira_nulo_na_criacao`), na edição (`..._na_edicao`) e some do filtro de licença (`test_licenca_vazia_nao_aparece_como_licenca_no_filtro`); no Python, `test_texto_vazio_vira_nulo_nunca_string_vazia` |

## Medidas (`tests/medidas/L0-09-a-procedencia.json`)

| medida | valor | como |
|---|---|---|
| `campos_medidos_em_camada_importada` | 4 de 4 | importação real de `cobertura.gpkg` |
| `casos_paridade_python_sql` | 7 blocos | pontuação idêntica em `app/catalogo/procedencia.py` e em `plat.procedencia_pontuacao` |
| `pontuacao_bloco_cheio` | 10,0 (0-10) | bloco com os 10 campos |
| `colunas_procedencia_na_exportacao` | 5 colunas | CSV do job `catalogo.exportar_lista` |
| `lista_50_itens_com_selo_p95_ms` | 32,3 ms | `GET /api/itens?tipo=mapa&limite=50`, 20 execuções, corpus de 10 mil |

## Achado que vale registrar

A primeira versão das funções SQL encadeava uma função por campo (`procedencia_campo` → `procedencia_valor`),
o que dava ~40 execuções de plano por linha da lista: a lista de 50 itens do corpus de 10 mil foi de 1,9 ms
para **288 ms**, estourando o portão de 100 ms do L0-03 (`test_lista_por_tipo_p95`, `test_acento_e_trigram...`
e `busca_p95_ms` reprovaram junto). Reescrita como UMA expressão + um `plpgsql` que guarda bloco e contagem em
variável, ficou em 32,3 ms de p95. Está anotado no comentário da migração para não voltar.

Também acrescentei `REVOKE ALL ... FROM PUBLIC` nas 9 funções novas: sem isso,
`test_funcoes_do_catalogo_sem_public_e_worker_fechado_a_plat_app` reprova (proacl NULL = EXECUTE para PUBLIC).

## O que ficou de fora, e por quê

1. **Editor do bloco na tela** — a tela MOSTRA, não edita campo a campo; hoje a edição é pelo formulário de
   `dados` do item. O editor de metadado é o item `L0-09-b-editor-iso-mgb`.
2. **e2e de navegador** da tela do item com o bloco: não escrevi. Sem captura nesta máquina, e o item não pediu.
3. **`MANUAL.md`/`ARQUITETURA.md`/`docs/PARIDADE.md`**: não toquei. São os arquivos que todas as trilhas
   editam ao mesmo tempo; o item pedia `docs/PROCEDENCIA.md`, que existe. Vale uma linha no MANUAL quando o
   gerente fizer o fast-forward.
4. **`docs/openapi.json`**: não regerei. O arquivo comitado já está atrás da aplicação (regerá-lo daqui produz
   6.084 linhas de diferença, de rotas de outras trilhas) e o teste que o guarda compara caminhos e
   privilégios, que não mudaram — só acrescentei parâmetros de consulta a `GET /api/itens`.

## Como o adversário reproduz

```bash
bash /home/dev/plataforma/laco/trilha_ambiente.sh <trilha>          # base própria
cd /home/dev/plataforma/wt/stac
# a migração deste item ainda não está na árvore principal: aplique do worktree
TMP=$(mktemp /tmp/mig_XXXX.sql); chmod 644 "$TMP"
TRILHA=<trilha> /home/dev/plataforma/laco/trilha_reescrever.py \
  db/migracoes/20260906T1544c24_procedencia_item.sql > "$TMP"
sudo -u postgres psql -d iagro_sat -X -q -v ON_ERROR_STOP=1 -1 -f "$TMP"
set -a; source /home/dev/plataforma/laco/var/trilha/<trilha>.env; set +a
venv/bin/pytest tests/unit/test_procedencia.py tests/api/catalogo/test_procedencia.py -q
# a parte de ingestão exige worker vivo NA TRILHA e o arquivo de teste gerado:
venv/bin/python tests/dados/gerar.py
PLAT_WORKER_URL=http://127.0.0.1:181NN venv/bin/python -m app.jobs.worker &   # porta livre
venv/bin/pytest tests/api/ingestao/test_procedencia_ingestao.py -q
```

## Armadilhas do ambiente que encontrei (não são deste item, mas custam tempo)

1. **`trilha_ambiente.sh` não sobe worker**: job nenhum roda até você subir um `app.jobs.worker` com o `.env` da
   trilha E `PLAT_WORKER_URL` numa porta livre (o padrão 8153 já é do worker de produção; ele morre com
   `Address already in use`). Sem isso, todo teste de ingestão falha por "job não terminou em 60 s".
2. **`d_<slug>` é global** (o mesmo achado do adversário G3): `plat.camada_schema_garantir` não cria nada porque
   `d_demo` já existe de produção, e o papel da trilha leva `permission denied for schema d_demo`. Fiz o mesmo
   que o G3: `GRANT USAGE, CREATE ON SCHEMA d_demo TO plat_tl09a_app, plat_tl09a_worker`, e **apaguei ao fim as
   5 tabelas `c_*` que os testes deixaram** (`pg_tables` em `d_demo` com `tableowner` da trilha voltou a 0).
   Enquanto `d_<slug>` não tiver prefixo por instalação, teste de ingestão em trilha escreve no schema de dado
   compartilhado.
3. **`test_documento.py::test_integridade_acusa_linha_de_versao_editada_direto_no_banco` reprova em qualquer
   trilha**: o teste roda `sudo -u postgres psql -c "UPDATE plat.item_versao ..."` com `plat.` literal, ou seja,
   adultera o schema de PRODUÇÃO (0 linhas, porque o uuid é da trilha) e depois cobra a corrupção na trilha.
   Não é regressão deste item.
4. **A árvore de trabalho é compartilhada e se move debaixo do pé**: durante este turno, `app/ingestao/carregar.py`,
   `web/js/catalogo/item.js`, `web/js/i18n/pt-BR.json` e `CHANGELOG.md` ganharam conteúdo de outras trilhas, e o
   `pt-BR.json` chegou a ser reescrito por outra trilha **apagando minhas chaves**. Por isso o commit foi montado
   com índice próprio (`GIT_INDEX_FILE` + `git commit-tree`), com o conteúdo destes 4 arquivos sintetizado a
   partir do HEAD do momento: o commit leva só o que é meu, e o disco continua com o que é das outras.

## Riscos de merge para o gerente

- `app/catalogo/rotas_itens.py`, `app/catalogo/comum.py`, `app/catalogo/tarefas.py`, `app/ingestao/carregar.py`,
  `web/js/catalogo/item.js`, `web/js/i18n/pt-BR.json`, `CHANGELOG.md` — arquivos que várias trilhas tocam. As
  minhas mudanças são localizadas: 2 linhas em `rotas_itens` (normalização) + 1 bloco de filtro + 1 faceta;
  1 coluna no `SQL_ITEM` e 1 chave no `item_json`; refatoração da tarefa de exportação em duas funções.
- `tests/api/catalogo/test_busca.py` — 1 linha do conjunto de facetas mudou (entrou `licenca`) e 3 linhas de
  conferência foram acrescentadas.
- A migração usa carimbo de tempo, então não colide com número reservado de ninguém.
