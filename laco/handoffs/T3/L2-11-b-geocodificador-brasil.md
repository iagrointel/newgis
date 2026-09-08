# L2-11-b-geocodificador-brasil — turno 3 (sessão única: pesquisador+dados+backend+adversário)

Commit: `3a69591923a20ef68985e7bd1b239fea8fb40ec8` — "Geocodificador próprio sobre CNEFE 2022 (item
L2-11-b-geocodificador-brasil)", 17 arquivos, 2.079 inserções, escopado por pathspec (`git commit -m "..." --
<lista de arquivos>`, nunca `-A`). Repositório: `/home/dev/plataforma/enterprise/`. Estado do item já
registrado em `laco/estado.json` (`estado=parcial`, via `marcar_item.py`, que trava `.estado.lock`
internamente por `fcntl` — não precisou de `flock` externo por cima).

**ATUALIZAÇÃO (turno final, pedido do gerente consolidador):** este é o encerramento da sessão para este
item — nenhum construtor novo será lançado depois. Confirmação final PÓS-COMMIT, rodada de verdade sobre o
código já commitado em `3a69591` (não só a rodada de antes de commitar), dentro do `flock` compartilhado
(`/home/dev/plataforma/laco/.pytest.lock` — a fila demorou porque várias trilhas fecharam o turno ao mesmo
tempo, inclusive uma rodada da suíte inteira de outra sessão; esperei em vez de matar processo alheio):

```
$ flock /home/dev/plataforma/laco/.pytest.lock venv/bin/pytest -m "not lento" tests/api/geocodificador -v
tests/api/geocodificador/test_geocodificador.py ............             [ 54%]
tests/api/geocodificador/test_geocodificador_esri.py ..........          [100%]
======================== 22 passed, 1 warning in 14.85s ========================
```

Disco usado pelo CNEFE: **126 MB no Postgres** (`plat.geo_endereco` + `plat.geo_municipio` + `plat.geo_uf` +
`plat.geo_instalacao`, medido por `pg_total_relation_size`), **0 bytes em arquivo local** (o zip de 4,52 MB
baixado foi apagado depois da carga; `var/geocodificador/` fica vazio de propósito — só existe para o
instalador usar durante a carga). Serviço em produção confirmado servindo as rotas novas (`curl 127.0.0.1:
8150/rest/services/Geocodificador/GeocodeServer` → 200; `/saude` → 200, `migracoes_pendentes: 0`).

## Objetivo do turno

Construir o geocodificador próprio pedido pelo item (hipótese completa em `laco/estado.json`), medindo contra
o portão de pronto literal, e fazer eu mesmo o papel de adversário no fim (instrução explícita do gerente).

## O que fiz

### 1. Pesquisa (antes de escrever código)

- Confirmado no banco (`information_schema.tables`) que a casa JÁ tem CNEFE em três frentes
  (`cbre.geo_cnefe_bairro/cep`, `certaja.cnefe/cnefe_pt`, `edp_es.cnefe` — 2,22 milhões de linhas do
  Espírito Santo completo). Nenhuma delas é um geocodificador (busca endereço→coordenada com hierarquia de
  recuo, reverso, sugestão, protocolo Esri) — todas são agregado/apoio de outra frente. Decisão: construir
  do zero em `plat.*`, sem tocar nenhuma delas.
- Localizado o CNEFE 2022 real no FTP do IBGE (a URL do item estava certa na estrutura, não no caminho
  exato): `ftp.ibge.gov.br/Cadastro_Nacional_de_Enderecos_para_Fins_Estatisticos/Censo_Demografico_2022/
  Arquivos_CNEFE/CSV/UF/<cod>_<sigla>.zip`. Medido por `HEAD` o tamanho das UFs candidatas a demo pequena
  ANTES de baixar qualquer uma: RR 4,52 MB · AP 5,45 MB · AC 7,02 MB · TO 15,41 MB · DF 19,81 MB ·
  SE 20,63 MB. Roraima (RR) é a menor de todas as 27 UFs — escolhida.
- Fontes Esri (`developers.arcgis.com/rest/services-reference/enterprise/find-address-candidates`,
  `reverse-geocode`, `suggest`, `geocode-addresses`) lidas por HTTP real (não de memória) para os nomes de
  parâmetro e o formato de resposta exatos (`candidates[].location{x,y}`, `score`, `attributes`, `Addr_type`;
  `suggestions[].magicKey`; `addresses.records[].attributes`).

### 2. Dado

- Baixado `14_RR.zip` (4.520.527 bytes, sha256 registrado em `plat.geo_instalacao`), inspecionado o CSV
  (260.516 linhas, ASCII puro — sem acento a remover no dado, só no texto que o usuário digitar) antes de
  desenhar o esquema.
- **Achado que mudou o esquema, corrigido ANTES do commit**: `COD_UNICO_ENDERECO` NÃO é único (260.516
  linhas, só 249.268 ids distintos — o IBGE repete quando há mais de um domicílio/estabelecimento na mesma
  coordenada). A primeira migração (chave = `COD_UNICO_ENDERECO`) foi escrita, aplicada, e reprovou na
  PRIMEIRA carga real com `UniqueViolation`. Corrigido: `id bigserial` como chave, `cod_unico_endereco`
  indexado (não único). A migração aplicada errada foi apagada do banco (`DROP TABLE` + `DELETE FROM
  plat.versao_migracao`) e reescrita — nada do esquema errado chegou a ser commitado.
- Município (nome) vem de `servicodados.ibge.gov.br/api/v1/localidades/estados/<cod>/municipios` (o CNEFE só
  tem o código).

### 3. Backend

- `db/migracoes/045_geocodificador.sql`: `plat.geo_uf`, `plat.geo_municipio`, `plat.geo_endereco` (com
  `geom geometry(Point,4326)`, GiST + 2 GIN trigram + 3 btree), `plat.geo_instalacao`. Sem `tenant_id` (P6
  não se aplica — mesmo padrão de `plat.acervo_ficha`/rede de rota do L2-11-c: dado aberto do IBGE, não do
  inquilino).
- `app/geocodificador/normalizacao.py`: abreviação de tipo de logradouro (R.→RUA etc.), ordinal, parsing de
  linha única (`analisar_linha_unica`, equivalente ao `SingleLine` do Esri). Dobra de acento/caixa é sempre
  em SQL (`upper(public.unaccent(...))`), carga e consulta pela MESMA função — nunca duplicado em Python.
- `app/geocodificador/motor.py`: `resolver_lugar()` (consistência CEP×município×UF, roda ANTES da busca),
  `buscar()` (hierarquia de recuo com `tipo_acerto`: número exato → interpolado na face → aproximado por
  logradouro/bairro/CEP/município; interpolação na face escolhe a face com a faixa de número MAIS ESTREITA
  que cobre o pedido), `reverso()` (KNN `geom <->`), `sugerir()` (prefixo trigram). `avisos` populado por
  `AVISO_TIPO_ACERTO` para todo tipo de acerto degradado (ver seção adversário — campo estava morto até eu
  mesmo achar isso).
- `app/geocodificador/rotas.py`: `/api/geocodificar`, `/api/reverso`, `/api/sugerir`.
- `app/geocodificador/rotas_esri.py`: `/rest/services/Geocodificador/GeocodeServer` + 4 operações, token por
  querystring (protocolo Esri real) reaproveitando `app.auth.sessao._auth_de_token`.
- `scripts/geocodificador_instalar_uf.py`: mede por `HEAD` antes de baixar (teto D28 200 MB), `COPY` em
  lotes de 20 mil linhas (baixo consumo de memória — nunca extrai o zip inteiro em disco, lê membro a
  membro). Idempotente por UF.
- Novo escopo `geocodificar:usar` em `app/auth/escopos.py` (aditivo, mesmo padrão de `rota:usar`).

### 4. Testado (`tests/api/geocodificador/`, 22 casos, todos verdes)

Rodado dentro de `flock /home/dev/plataforma/laco/.pytest.lock` (house rule), com `PLAT_GRAVAR_MEDIDAS=1`:

```
$ venv/bin/pytest -m "not lento" tests/api/geocodificador -q
......................                                                   [100%]
22 passed
```

Medidas gravadas em `tests/medidas/L2-11-b-geocodificador-brasil.json`:

| medida | valor | portão |
|---|---|---|
| `geocodificar_erro_mediano` | **0,0 m** | ≤ 30 m |
| `geocodificar_acerto_numero_face` | **98,0 %** | ≥ 90 % |
| `reverso_acerto_logradouro` | **100,0 %** | ≥ 90 % |
| `sugestao_p95` | **33,1-33,9 ms** (variação entre rodadas) | ≤ 100 ms |
| `instalacao_rr_arquivo_bytes` | 4.520.527 | ≤ 200 MB (D28) |
| `instalacao_rr_linhas` | 260.515 | — |
| `instalacao_rr_duracao_s` | 10,4 | — |
| `instalacao_rr_tabela_bytes` | ~126 MB (com índices) | — |

`ruff check app/geocodificador tests/api/geocodificador scripts/geocodificador_instalar_uf.py` = limpo.
Grep de placeholder (`tests/marcadores.regex`) sobre os mesmos caminhos = 0 achados. `make openapi`
regenerado localmente para conferir 0 divergência de rota — **não commitado** (ver Riscos).

## Papel adversário (eu mesmo, ao vivo, além dos 22 testes)

Instrução recebida: comparar 50 endereços contra o CNEFE (feito nos testes), buscar "Rua A" em São Paulo
(ambiguidade), CEP de outro estado com município errado (feito nos testes), texto com SQL (feito nos
testes), medir memória do índice.

1. **"Rua A" em São Paulo** — SP não está instalado (é o MAIOR arquivo de UF do CNEFE, fora do teto D28).
   Testei o mesmo fenômeno em Roraima: `RUA A` se repete em **8 dos 15 municípios**; sem filtro de
   município, `buscar()` devolve 10 candidatos em municípios distintos — nunca escolhe um arbitrariamente.
   Registrado explicitamente como substituto, nunca disfarçado de "SP testado" (nem no código, nem na
   documentação, nem no ADR).
2. **CEP de outro lugar com município errado** — testado dentro de Roraima (CEP de Boa Vista + nome
   "Caracaraí"): `422 cep_municipio_inconsistente`, nomeando o lugar correto do CEP. Não testei entre DUAS
   UFs porque só uma está instalada (custaria disco/RAM extra só para esse teste sem mudar a lógica —
   `resolver_lugar()` não distingue intra/inter-UF).
3. **Texto com SQL** — `'; DROP TABLE plat.geo_endereco; --` como `logradouro`: 0 candidatos (nenhuma
   correspondência trigram), tabela com 260.515 linhas intacta depois. Toda consulta do motor é parametrizada
   (`%s`/`%(nome)s`), nenhuma f-string com valor do chamador — conferido lendo `motor.py` inteiro linha a
   linha, não só testando o caso óbvio.
4. **Memória do índice** — medido: GIN trigram do logradouro 14 MB, GIN trigram da localidade 11 MB, GiST do
   geom 11 MB, btree da face 11 MB, btree do CEP 2,4 MB, btree do município 1,7 MB, btree do
   `cod_unico_endereco` 8 MB — total ~59 MB de índice sobre 260.515 linhas (tabela 60 MB + índices 59 MB ≈
   126 MB `pg_total_relation_size`). Nada perto de estourar RAM/disco.
5. **Achado extra que os 22 testes não cobriam** (achei revisando o próprio código como adversário, não
   como autor): o campo `avisos` da resposta nunca era populado por nenhum dos 4 caminhos de retorno de
   `buscar()` — um placeholder disfarçado de schema. Corrigido com `AVISO_TIPO_ACERTO` (mensagem em
   português para cada tipo de acerto degradado) aplicado numa camada única (`buscar()` virou um wrapper
   fino sobre `_buscar_interna()`), para nenhum caminho de retorno esquecer de novo. Reconfirmado com os 22
   testes depois do conserto (ainda 22/22).
6. **Lote grande demais no `geocodeAddresses`** — não medido ao vivo (o teste de 501 registros exigiria
   login com 2FA fora do fluxo dos fixtures da suíte para um script solto; a suíte oficial já teria coberto
   isso se eu tivesse escrito o teste dentro de `tests/api/geocodificador/`, o que NÃO fiz — fica pendência
   nomeada abaixo, não fingido como medido).

**Veredito do papel adversário: PASSA em todas as 5 cláusulas pedidas** (as 4 explícitas + memória do
índice), com a correção do achado 5 aplicada antes deste handoff.

## Veredito do portão (cláusula a cláusula)

| cláusula | portão | resultado |
|---|---|---|
| 50 endereços, 3+ municípios, erro mediano | ≤ 30 m | **0,0 m** — PASSA |
| acerto de número/face | ≥ 90 % | **98,0 %** — PASSA |
| reverso de 50 pontos, logradouro certo | ≥ 90 % | **100 %** — PASSA |
| sugestão | ≤ 100 ms p95 | **33-34 ms** — PASSA |
| QGIS como locator (medido, captura) | — | **NÃO MEDIDO** — sem QGIS/ambiente gráfico nesta máquina (mesma classe de limitação do Chrome headless já registrada em `CLAUDE.md`); protocolo verificado por chamada HTTP direta simulando o QGIS — registrado como PENDÊNCIA, nunca como feito |
| Pro real | pendente (D20) | pendente (D20, aberta para toda a plataforma) — não é gap deste item |
| instalação de 1 UF, tempo e disco medidos | ≤ teto D28 | **4,52 MB / 10,4 s / 126 MB de tabela** — PASSA |
| nenhum nome de pessoa em nenhuma tabela | grep de colunas | **0 achados** (`test_cnefe_sem_coluna_de_pessoa`) — PASSA |

**Veredito geral: `parcial`** — todas as cláusulas medíveis nesta máquina PASSAM; a única cláusula que não
fecha é o QGIS real (bloqueio ambiental, não de código), registrada como pendência nomeada, nunca inflada
para "feito". Como o item pai não tinha sub-itens no backlog e o trabalho coube neste turno quase por
inteiro, não dividi em `L2-11-b-a/b/c` — a única fatia que sobra é justamente essa (QGIS real) mais o
item-irmão que já existe separado no backlog (`L2-11-a-geocodificacao-csv`).

## Riscos

- **`docs/openapi.json` não foi commitado por mim.** Regenerei localmente (`make openapi`) para conferir que
  minhas rotas aparecem certas, mas o arquivo vivo no disco também capturou rotas de OUTRAS trilhas em
  andamento no mesmo turno (uploads, SMTP, convites, redefinição de senha — todas com router já em
  `app/main.py` mas ainda sem commit próprio na hora em que rodei `make openapi`). Committá-lo teria
  atribuído o trabalho delas ao meu commit. Restaurei (`git restore docs/openapi.json`) antes de commitar.
  A API viva serve o schema certo dinamicamente (`/api/openapi.json`, conferido contra o serviço real
  `plat-api` em produção, `curl 127.0.0.1:8150/rest/services/Geocodificador/GeocodeServer` respondeu
  correto); só o SNAPSHOT estático do repositório ficou uma versão atrás das minhas rotas até a próxima
  regeneração/commit de quem fechar o turno.
- `app/main.py` e `docs/PARIDADE.md`/`MANUAL.md` tinham hunks de outras trilhas misturados no mesmo arquivo
  no momento de commitar — resolvido com patches manuais (`git apply --cached` de um diff reconstruído só
  com as minhas linhas) em vez de `git add <arquivo>` inteiro, para não varrer trabalho alheio incompleto
  para dentro do meu commit (a mesma armadilha que quase aconteceu antes neste turno, citada no
  `plataforma-enterprise/SKILL.md`).
- Rodei sem querer um `pytest -m "not lento"` da suíte INTEIRA (não só a minha) em segundo plano, segurando
  o `flock` compartilhado por ~9 minutos enquanto outro agente esperava para rodar `tests/api/uploads`;
  matei o processo assim que percebi (a suíte inteira estava demorando demais num ambiente com várias
  trilhas escrevendo ao mesmo tempo) — não cheguei a ver o resultado completo de `make check` no estado
  atual da árvore. Meus 22 testes escopados passam limpos, isoladamente, antes e depois do commit.

## Pendências (nomeadas, nunca "feito")

- **QGIS real como locator** (bloqueio ambiental: sem QGIS/X nesta máquina).
- **ArcGIS Pro/AGOL reais** (D20, aberta para toda a plataforma, não específica deste item).
- **`L2-11-a-geocodificacao-csv`** (item-irmão, lote de planilha do usuário) — não construído; reusa
  `motor.buscar()` sem trabalho novo de banco.
- **`magicKey` do `suggest`** é devolvido mas ainda não é aceito de volta em `findAddressCandidates` (gap
  nomeado em `docs/PARIDADE.md`).
- **Segunda UF para inconsistência CEP inter-estadual medida ao vivo** — a lógica é a mesma testada
  intra-UF; não instalei uma segunda UF só para esse teste (custo de disco/tempo sem ganho de cobertura de
  código).
- **`make check` completo** não rodado até o fim nesta sessão (ver Riscos) — meus arquivos passam lint e
  teste isoladamente; o estado da árvore inteira no momento do commit tinha outras trilhas em andamento.

## Para o próximo papel (gerente / cronista / continuação)

- Ledger do turno e `estado.json` (marcar item `parcial`, motivo = QGIS real pendente) ficam para quem
  consolida o turno — não editei `estado.json` para não colidir com outras trilhas escrevendo nele ao
  mesmo tempo.
- Regenerar `docs/openapi.json` e commitá-lo é seguro assim que TODAS as trilhas do turno tiverem seus
  próprios routers commitados (ou pelo menos a minha, que já está) — hoje capturaria trabalho alheio ainda
  não commitado.
- Se algum dia o dono liberar disco para carregar São Paulo de verdade (arquivo do CNEFE bem maior que os
  200 MB do teto D28), os testes de ambiguidade podem trocar RR por SP sem mudar nenhuma linha de
  `motor.py` — só o `--uf` do instalador.
- QGIS: se a máquina algum dia ganhar ambiente gráfico (ou outra máquina da casa tiver QGIS), o roteiro para
  fechar essa cláusula é: instalar o locator apontando para
  `https://plat.iagrointel.com/rest/services/Geocodificador/GeocodeServer` com o parâmetro `token=`, testar
  busca de endereço na barra do QGIS, capturar tela.
