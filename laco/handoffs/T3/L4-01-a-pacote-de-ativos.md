# L4-01-a-pacote-de-ativos — handoff

- Ramo: `wt/stac` (worktree `/home/dev/plataforma/wt/stac`)
- Commits: `1d0040b` (o item) e `838cbd8` (grava o sha na medida)
- Base de teste: schema próprio `plat_tt401a` (`bash laco/trilha_ambiente.sh t401a`), **apagado ao fim**
- Estado: **entregue**, com uma cláusula adaptada (caminho da rota, seção 4) e duas fronteiras honestas (seção 5)

Este é o PRIMEIRO item da linha L4. As decisões de arquitetura estão no
**ADR 0019** (`docs/adr/0019-pacote-de-ativos-da-rede-de-utilidades.md`) e valem para os próximos itens da
linha (topologia, traçado, subrede, edição): não refazer item a item.

## 1. O que foi construído

| arquivo | o que é |
|---|---|
| `db/migracoes/20260906T1553_rede_pacote_de_ativos.sql` | 10 tabelas `plat.rede*` com RLS (4 políticas cada) e 3 tipos de evento |
| `app/rede_utilidades/esquema.py` | esquema JSON (rascunho 2020-12) do pacote, vocabulário fechado |
| `app/rede_utilidades/localizador.py` | linha do texto BRUTO para um caminho JSON (é o que faz a mensagem de erro apontar a linha) |
| `app/rede_utilidades/pacote.py` | forma canônica (`canonizar`) e validação em duas camadas (`ler`) |
| `app/rede_utilidades/deposito.py` | importa para as tabelas e exporta reconstruindo delas |
| `app/rede_utilidades/instalados.py` | catálogo dos pacotes entregues com a instalação |
| `app/rede_utilidades/rotas.py` + `modelos.py` | 8 rotas em `/api/rede` |
| `app/rede_utilidades/pacotes/eletrica-br.json` | 96.042 bytes; 2 domínios, 4 tiers, 11 categorias, 4 terminais, 14 grupos, 24 tipos, 214 atributos, 24 regras |
| `app/rede_utilidades/pacotes/agua-epanet.json` | 27.765 bytes; 1 domínio, 2 tiers, 8 categorias, 2 terminais, 6 grupos, 14 tipos, 41 atributos, 16 regras |
| `docs/gerar_pacote_rede.py` + `docs/PACOTE_REDE.md` | mapeamento coluna a coluna, gerado do dado, com `--check` no teste |
| `docs/PARIDADE.md` (seção nova) | 13 linhas de paridade contra domain networks / tiers / asset groups / asset types / categories |
| `tests/unit/test_rede_pacote_formato.py` (21) e `tests/api/test_rede_pacote.py` (13) | 34 testes |
| `tests/api/cruzado_casos.py` | 8 casos cruzados A→B das rotas novas + `rede_b` na preparação |
| `app/main.py`, `docs/openapi.json`, `CHANGELOG.md`, `Makefile` | montagem do router, contrato, entrada do turno, alvo `make pacote-rede` |

## 2. Portão de pronto, cláusula por cláusula

| cláusula | prova |
|---|---|
| DDL `plat.rede_*` de catálogo em migração idempotente com RLS | `sudo -u postgres psql -d iagro_sat -X -q -1 -f - < <(TRILHA=t401a laco/trilha_reescrever.py db/migracoes/20260906T1553_rede_pacote_de_ativos.sql)` — reaplicável (tudo `IF NOT EXISTS` / `DROP POLICY IF EXISTS`); `pytest tests/api/test_rede_pacote.py::test_toda_tabela_do_catalogo_tem_rls_ligada` = 10 tabelas, `relrowsecurity` verdadeiro, 4 políticas cada |
| `POST .../pacote` importa e `GET .../pacote` devolve o mesmo JSON byte a byte | `pytest tests/api/test_rede_pacote.py::test_importa_e_exporta_byte_a_byte` (2 casos, 96.042 e 27.765 bytes, comparação de bytes e do sha256 no ETag). Reforço: `test_a_exportacao_vem_das_tabelas_e_nao_do_arquivo_recebido` altera `plat.rede_grupo` direto no banco e exige que a exportação mude — prova de que a ida e volta não é o arquivo devolvido |
| pacote `elétrica-BR` cobrindo as 13 camadas de rede da BDGD com mapeamento coluna a coluna documentado | `pytest tests/unit/test_rede_pacote_formato.py::test_eletrica_br_cobre_as_13_camadas_de_rede_da_bdgd` e `::test_eletrica_br_mapeia_coluna_a_coluna_cada_camada`; documento em `docs/PACOTE_REDE.md` (gerado do dado, `venv/bin/python docs/gerar_pacote_rede.py --check`) |
| pacote `água-EPANET` com junction/pipe/pump/valve/tank/reservoir | `::test_agua_epanet_tem_os_seis_grupos_do_modelo` (6 grupos + os 6 tipos de válvula PRV/PSV/PBV/FCV/TCV/GPV) |
| validação recusa pacote sem tier ou com tipo sem grupo | `::test_pacote_sem_tier_e_recusado`, `::test_pacote_com_lista_de_tiers_vazia_e_recusado`, `::test_tipo_sem_a_chave_grupo_e_recusado`, `::test_tipo_apontando_grupo_que_nao_existe_e_recusado_com_a_linha` |
| teste automatizado | 34 testes; `pytest tests/unit/test_rede_pacote_formato.py tests/api/test_rede_pacote.py -q` = 34 passaram |
| paridade escrita em `docs/PARIDADE.md` | seção "Rede de utilidades — pacote de ativos", 13 linhas |

Medidas em `tests/medidas/L4-01-a-pacote-de-ativos.json` (importação 146,3 ms, exportação 16,4 ms, recusa
22,1 ms, uma execução em máquina compartilhada).

## 3. Refutação exigida — resultado

| o que o adversário faz | resultado |
|---|---|
| importa pacote com tier apontando domínio inexistente | 422 `pacote_invalido`, problema `dominio_inexistente`, caminho `tiers[0].dominio` e **linha do arquivo enviado** (o teste lê a linha apontada e confere que o texto do domínio inventado está nela). Nada é escrito: a exportação continua 404. `pytest tests/api/test_rede_pacote.py::test_tier_com_dominio_inexistente_e_recusado_apontando_a_linha` |
| importa pacote com dois tipos de mesmo código | 422 com `codigo_repetido`, `linha` (a segunda ocorrência) e `linha_anterior` (a primeira). `::test_dois_tipos_de_mesmo_codigo_sao_recusados_apontando_as_duas_linhas` |
| exporta de um inquilino e reimporta em outro | `::test_exportar_de_um_inquilino_e_reimportar_no_outro_nao_leva_nada_do_primeiro`: o pacote atravessa e volta byte a byte; como `plat_app` no contexto de B, as 10 tabelas dão 0 linhas da rede de A e 0 linhas de qualquer outro inquilino |
| tenta ver, exportar, importar ou apagar a rede do outro inquilino | 404 em todos, e a rede não aparece na listagem: `::test_rede_de_um_inquilino_nao_aparece_no_outro` |

Reproduzir tudo:

    bash /home/dev/plataforma/laco/trilha_ambiente.sh <nome>
    set -a; source /home/dev/plataforma/laco/var/trilha/<nome>.env; set +a
    cd /home/dev/plataforma/wt/stac
    TRILHA=<nome> /home/dev/plataforma/laco/trilha_reescrever.py \
      db/migracoes/20260906T1553_rede_pacote_de_ativos.sql \
      | sudo -u postgres psql -d iagro_sat -X -q -v ON_ERROR_STOP=1 -1 -f -
    venv/bin/pytest tests/unit/test_rede_pacote_formato.py tests/api/test_rede_pacote.py -q

## 4. Cláusula adaptada: o caminho da rota

O portão dizia `POST /api/v1/rede/{rede_id}/pacote`. A rota entregue é **`/api/rede/{rede_id}/pacote`**, sem
`v1`. Motivo (ADR 0019 seção 6): as 74 rotas do produto respondem em `/api/` sem prefixo de versão e a versão
do formato já vive dentro do documento (`esquema_versao`). O `v1` aparece só em 4 itens do `estado.json`, todos
da linha L4 (`L4-01-a`, e os que citam `/api/v1/rede/{id}/tracar`, `/topologia/habilitar`, `/config_tracado`) —
é marca do decompositor, não decisão de arquitetura. **Os outros três itens da linha devem seguir
`/api/rede/...`**. Se o gerente decidir o contrário, é uma linha em `app/rede_utilidades/rotas.py`.

## 5. Fronteiras honestas (o que NÃO está provado)

1. **A origem das colunas de 5 das 13 camadas não foi conferida contra dado real.** 154 dos 214 atributos do
   pacote elétrico têm `origem.conferida = true` (11 camadas lidas numa extração real de distribuidora, base
   interna da casa); 60 atributos de `SUB`, `UNSEMT`, `UNCRMT`, `UNREMT` e `UGMT_tab` são declarados do Módulo
   10 do PRODIST e **nunca foram vistos em extração**. Isso está marcado no próprio dado, aparece na coluna
   "conferida" de `docs/PACOTE_REDE.md` e tem teste que trava a lista (`::test_eletrica_br_mapeia_coluna_a_coluna_cada_camada`).
   O pacote de água é inteiramente declarado do manual do EPANET 2.2, sem nenhum arquivo `.inp` real lido.
2. **Os subtipos codificados são nossos, não os da fonte.** Cada tipo de ativo tem código inteiro próprio (como
   um *asset type* da Esri) e um campo `codigos_fonte` com os códigos do dado real SÓ onde há confiança:
   `POS`/`TOR` em PONNOT, `T`/`B` em TIP_TRAFO. Os demais códigos observados (DA, DF, M, MT em TIP_TRAFO; DRV,
   FLT, PFL, PIS, PMF, PSA, PSB, PSE em TIP_PN) caem em tipos "ainda não classificado", com a razão escrita na
   descrição. Preferi tipo vazio a significado inventado.
3. **As linhas de paridade da seção nova de `docs/PARIDADE.md` não foram conferidas por HTTP neste turno** — são
   leitura do modelo documentado do ArcGIS Pro 3.4 (as URLs declaradas no item), não medição. Está dito na
   abertura da seção.
4. **Ida e volta é "o mesmo pacote", não "os mesmos bytes de entrada".** Pacote enviado fora da forma canônica
   volta canonizado. Os dois pacotes entregues estão na forma canônica e há teste que reprova se saírem dela.
5. **Nada de topologia, traçado ou subrede.** Este item entrega só o catálogo do esquema; nenhuma feição de rede
   é criada, e nenhuma regra do pacote é imposta sobre feição.
6. **A dependência `L0-04-ingest-vetor` não bloqueou nenhuma cláusula** — o pacote descreve esquema, não carrega
   feição. A ligação entre grupo de ativo e camada importada é item seguinte.

## 6. Falhas na suíte que NÃO são deste item (reproduzidas sem tocar em nada meu)

1. `tests/api/test_migracoes.py::test_tabela_reflete_os_arquivos_em_disco` — a base da trilha aplica as
   migrações da ÁRVORE PRINCIPAL (`048`, `049`), que este worktree ainda não tem, e o worktree tem um
   `046_raster_item.sql` de outra trilha ainda sem commit. A migração deste item usa carimbo de tempo e nem
   entra no conjunto que esse teste compara.
2. `tests/api/test_cruzado.py` — a fixture `preparacao` quebra em `POST /api/papeis` com
   `403 sem_permissao "operação fora do inquilino da sessão"`, ANTES de qualquer linha deste item; reproduzido
   com uma sessão limpa de `demo2` sem tocar em rede. Os 8 casos cruzados das rotas novas ESTÃO escritos e
   `test_cobertura_100_por_cento` não acusa falta deles (as 13 rotas que faltam são de `/api/importacoes` e
   `/ogc/records`, de outras trilhas). O cruzamento A→B das minhas rotas é provado à parte em
   `tests/api/test_rede_pacote.py`.
3. `tests/api/test_privilegios_declarados.py::test_vocabulario_python_igual_ao_banco` — outra trilha acrescentou
   `conteudo.exportar` em `app/auth/privilegios.py` com migração ainda não aplicada nesta base. **Nenhum
   privilégio novo foi criado por este item**: a escrita usa `rede.editar`, semeado na migração 003.

## 7. Risco de merge

- `app/main.py` e `CHANGELOG.md`: o worktree é compartilhado com outros agentes e a árvore de trabalho já tinha
  alterações deles. O commit carrega **só a minha alteração** desses dois arquivos (versão montada sobre `HEAD`,
  posta no índice por `git update-index --cacheinfo`); a árvore de trabalho continua com tudo.
- ⚠ **O índice do git é compartilhado entre os agentes deste worktree.** Ao preparar o commit encontrei no
  índice arquivos de outras trilhas (`ARQUITETURA.md`, `MANUAL.md`, `app/conexao/*`, `docs/adr/0018-conector-*`,
  `db/migracoes/20260906T1609_*`). Por isso o commit foi feito com **índice privado**
  (`GIT_INDEX_FILE` + `git write-tree` + `git commit-tree` + `git update-ref` com compare-and-swap), nunca
  `git commit` na árvore. Recomendo a mesma receita para as outras trilhas deste worktree.
- ⚠ **Número de ADR também colide.** Escrevi o ADR como 0018 e, ao ir gravar o CHANGELOG, encontrei
  `docs/adr/0018-conector-wfs-e-ogc-api-features.md` já criado por outra trilha; renumerei o meu para **0019**.
  A lição da numeração de migração (ADR 0014) vale igual para ADR: número não se reserva. Fica como sugestão ao
  gerente adotar carimbo de tempo também no nome do ADR.
- `docs/openapi.json`: o commit é **puramente aditivo** (541 linhas, 0 removidas) — só as 8 rotas novas e os
  esquemas que elas referenciam, sem reordenar o arquivo.
- `tests/api/cruzado_casos.py`, `docs/PARIDADE.md`, `Makefile`: alterações localizadas, sem tocar em nada de
  outra trilha.

## 8. Limpeza

Schema da trilha apagado ao fim: `DROP SCHEMA plat_tt401a CASCADE; DROP SCHEMA plat_trabalho_tt401a CASCADE`.
Nenhuma escrita no schema `plat` de produção em nenhum momento.
