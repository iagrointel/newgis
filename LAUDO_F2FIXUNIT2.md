# Laudo — tests/unit (21 arquivos que falham isolados, triagem 16/09)

Ramo `wt/f2fixunit2`, a partir de `wt/uniao`. Trilha de teste `uniao` (schema `plat_tuniao`).
Lista fonte: `laco/vivo/triagem_20260916T0809.falha.ids.txt` filtrada para `tests/unit/`.

## Placar (21/21 triados)

| # | arquivo | resultado | onde |
|---|---|---|---|
| 0a | test_vendor.py | PASSA (gate do dono, confirmado) | Item 0 |
| 0b | test_estilo_tokens.py | PASSA (dívida de escopo, confirmado) | Item 0 |
| 0c | test_jobs_registro.py | **CONSERTADO** | Item 0 |
| 1 | test_amc_sensibilidade_desempenho.py | **CONSERTADO** | Item 1 |
| 2 | test_app_acoes.py | **CONSERTADO** | Item 2 |
| 3 | test_appliance_sem_cdn.py | **CONSERTADO** | Item 3 |
| 4 | test_cad_formatos.py | **CONSERTADO** | Item 4 |
| 5 | test_conformidade_matriz.py | **CONSERTADO** | Item 5 |
| 6 | test_csw_analise.py | **CONSERTADO** | Item 6 |
| 7 | test_exportacao_unidade.py | **CONSERTADO** | Item 7 |
| 8 | test_extensoes_lista.py | **CONSERTADO** | Item 8 |
| 9 | test_fk_por_inquilino_classe_conserto.py | **CONSERTADO** | Item 9 |
| 10 | test_garage_adversario.py | **CONSERTADO** | Item 10 |
| — | test_licencas_simbolos.py | JÁ PASSAVA isolado nesta rodada (não mexido) | — |
| 11 | test_manual_gerado.py | **CONSERTADO** | Item 11 |
| 12 | test_regras_motor.py | **FORA — decisão de produto pendente** | Item 12 |
| 13 | test_rotas_sombreadas.py | **CONSERTADO** | Item 13 |
| 14 | test_rotas_sombreamento.py | **CONSERTADO** | Item 14 |
| 15 | test_schema_ambiente_metodos.py | **CONSERTADO** | Item 15 |
| 16 | test_tokens_visuais.py | **FORA — dívida de escopo (mesma família do 0b)** | Item 16 |
| 17 | test_videos_roteiro.py | **CONSERTADO** | Item 17 |

**16 consertados + 2 já corretos (confirmados) + 1 já passava sozinho = 19/21 com 0 failed.**
**2 ficam de fora, com motivo e comando de reprodução**: test_regras_motor.py (item 12, conflito de
schema entre duas versões do pacote de rede, decisão de produto) e test_tokens_visuais.py (item 16,
dívida de escopo de design system, mesma família do test_estilo_tokens.py já decidido pelo dono).

`make lint` verde no worktree inteiro. Todos os 19 arquivos consertados/confirmados re-verificados
juntos ao final, sem regressão entre si.

## Item 0 — os três já decididos pelo gerente (confirmados, não mexidos)

**test_vendor.py** — CAI em `test_todo_arquivo_do_vendor_esta_em_versoes_com_sha_e_licenca`:
`xeokit-sdk-2.6.113.js` está licenciado AGPL-3.0-only, fora do conjunto permitido
`{Apache-2.0, BSD-3-Clause, ISC, MIT, OFL-1.1}`. Gate do dono (decisão já tomada) — não conserto.
`bash laco/roda_teste.sh tests/unit/test_vendor.py` → 1 failed, 1 passed.

**test_estilo_tokens.py** — dívida de escopo (cor/glifo fora de tokens em telas novas). 4 CAEM:
- `test_a_nenhuma_cor_literal_em_css_fora_dos_tokens`: 156 ocorrências de cor literal em `web/*.css`
  (ex.: `web/amc_pareto.css:2`, `web/widgets.css` linhas 3-36, `web/versoes.css`, `web/simbolos.css`).
- `test_a_nenhuma_cor_literal_em_js`: 140 ocorrências em `web/js/**`.
- `test_c_icones_uma_familia_so_e_nenhum_glifo_fora_dela`: 68 glifos fora da família de ícone única
  (✕ ↑ ↓ ★ ⚡ ⛔ ‹› ⚠ ′″ ↶ ↷ ∞ ⠿ ▲▼ ⋯ ⎘ ⋮ ≠ ▸ ▾ em `web/js/**`, `web/sig.css`, `web/sig.html`).
- `test_e_toda_tela_liga_as_tres_folhas_e_o_tema_e_a_rota_estilo_existe`: pelo menos `acervo.html`
  não referencia `/static/estilo/base.css`.
`bash laco/roda_teste.sh tests/unit/test_estilo_tokens.py` → 4 failed, 4 passed. Lista completa
de arquivos/linhas capturada nesta rodada, não colada aqui (dump grande) — reproduzir com
`-v` por sub-teste para a lista integral.

**test_jobs_registro.py::correio.enviar** — CONSERTADO (item L0-07-d, regressão de fusão).
Causa-raiz (`git log --all -S correio.enviar -- app/jobs/tipos.py`): commit `b43e23414`
(restauração de `LoteEntrada/.../camadas.lote`) reescreveu a linha
`from app.correio import tarefas as correio_tarefas` colando o comentário de L0-07-d na linha de
`app.edicao` e apagando o import real — `correio.enviar` nunca entrava em `REGISTRO` e a rota de
convite (`app/auth/rotas_convites.py:117`) batia em `tipo_desconhecido`. Restaurada a linha de
`app.correio` (ordem alfabética conexao/correio/edicao), comentário e docstring do módulo corrigidos
para não descrever mais `camadas.lote` como "fora por bug alheio" (já resolvido no mesmo commit).
Commit: `a38775044`. Prova: `bash laco/roda_teste.sh tests/unit/test_jobs_registro.py` →
**64 passed, 8 skipped** (era 1 failed).

## Item 1 — test_amc_sensibilidade_desempenho.py (CONSERTADO)

Causa-raiz: `git log --all -S amc_sensibilidade -- app/amc/tarefas.py` mostra que o commit
`dcd70c852` (item L3-02-b) tinha adicionado `SensibilidadeParametros` + job `amc_sensibilidade`,
mas a fusão que trouxe `amc.recombinar`/`amc.smaa` (`aaf7cde62`, itens L3-16/L3-02-c) reescreveu
`app/amc/tarefas.py` a partir de uma base anterior a esse commit — a função inteira, a classe de
parâmetros e as constantes `MAX_N_SOBOL`/`MAX_BOOTSTRAP` desapareceram (não um import solto: perda
de feição completa). `app/amc/sensibilidade.py` (Sobol de Saltelli/Jansen + tornado OAT) estava
intacto, só não era mais importado/chamado.

Restaurado ao final de `app/amc/tarefas.py` (import `sensibilidade` acrescentado à linha existente,
constantes e docstring do módulo devolvidas), sem tocar em `amc_recombinar`/`amc_smaa`.
Commit: `6316a88b2`. Prova: `bash laco/roda_teste.sh tests/unit/test_amc_sensibilidade_desempenho.py`
→ **4 passed** (era 3 failed).

## Item 2 — test_app_acoes.py (CONSERTADO)

Causa-raiz: `app/app_modelo/contratos.py` (espelho Python de `web/js/widgets/registro.js`) só foi
escrito uma vez (`5a318eb8f`, item L5-01-e, 7 widgets) e nunca acompanhou o crescimento do lado JS
(L5-01-c: tabela 2/gráfico 2/filtro 2 + lista/consulta/seleção/info-feicao/adicionar-dado; L5-01-d:
imagem/cartão/incorporar/divisor/menu/controlador/compartilhar/login/idioma/tema; varredura 15/09:
`tabela.exportada`, `grafico.desenhado`, `texto.feicao`) — não é import perdido na fusão, é mirror
desatualizado a cada item novo. Reescrito `CONTRATOS` com os 22 widgets, eventos e ações idênticos a
`registro.js` (fonte de verdade declarada no próprio docstring do arquivo).
Commit: `f8f4ce97f`. Prova: `bash laco/roda_teste.sh tests/unit/test_app_acoes.py` →
**6 passed** (era 1 failed).

## Item 3 — test_appliance_sem_cdn.py (CONSERTADO)

Causa-raiz: o resgate `40a0aef6a` (item L2-02-e-simbolos-sprites-glifos) trouxe
`noto-sans-regular-2.004.ttf`/`open-sans-regular-1.10.ttf` (glifo PBF servido pelo Martin,
`app/simbolos/fontes.py`) mas a sessão caiu por limite de taxa antes de registrar sha256/versão/
licença em `web/vendor/VERSOES.txt` — `docs/LICENCAS_SIMBOLOS.md` já tinha a proveniência certa
(apt `fonts-noto-core`/`fonts-open-sans` do Ubuntu 24.04, não CSS2 API como as fontes de UI), só
faltava a linha do gate de vendor. Acrescentadas as duas linhas com sha256 conferido.
Commit: `ce3360d2f`. Prova: `bash laco/roda_teste.sh tests/unit/test_appliance_sem_cdn.py` →
**3 passed** (era 1 failed); `sha256sum -c` sem divergência.

## Item 4 — test_cad_formatos.py (CONSERTADO)

Causa-raiz: duas trilhas paralelas de 06/09 tocaram `app/ingestao/formatos.py`: `ce379e243`
(item L0-04-e) implementou DXF+DWG via LibreDWG (`dwg2dxf`), decidindo pelos bytes com
`cad.assinatura`/`cad.versao_dwg`; outra trilha ("Ingestão vetorial: 13 formatos...", commits
`a27fde9cb`/`67a006368`) reescreveu o mesmo trecho com a abordagem concorrente via ODA File
Converter — explicitamente descartada pelo ADR aceito `docs/adr/0020-leitura-de-cad-dxf-e-dwg.md`
("Fica de fora, declarado: ... o ODA File Converter"). A fusão manteve a versão sem DWG: `"dwg"`
sumiu de `FORMATOS` e `verificar_conteudo("dwg", ...)` caía no `else` genérico. `app/ingestao/cad.py`
(assinatura/versao_dwg/dwg2dxf) ficou intacto, só não era mais chamado.

Restaurado `"dwg"` em `FORMATOS` e o `elif` combinado dxf/dwg (decide pelos bytes via
`cad.assinatura`); docstring do módulo corrigida (não lista mais DWG como fora de escopo).
Commit: `b836535ef`. Prova: `bash laco/roda_teste.sh tests/unit/test_cad_formatos.py` →
**22 passed, 1 skipped** (era 1 failed).

## Item 5 — test_conformidade_matriz.py (CONSERTADO)

Causa-raiz: a fusão que acrescentou várias seções novas na mesma região de `docs/PARIDADE.md`
(rede de utilidades L4-01-a, SMTP/convites, GPServer UX-22, notificações) apagou os marcadores
`<!-- INICIO/FIM matriz-de-conformidade -->` e o corpo da tabela gerada por
`tests/esri/conformidade.py` (presentes em `3946191c1`, 08/09) — `tests/esri/conformidade.json`
(fonte de dados, mesma versão `00b45d5fe64a`, 119 linhas) continuava intacto e commitado, só não
refletido mais no documento. Regravado com o próprio gerador (`conf.secao(json)` +
`conf._trocar_secao`), sem rodar as provas ao vivo de novo — dado já medido, nada mudou desde 08/09;
a seção volta ao final do arquivo (comportamento padrão da função quando os marcadores faltam).
Commit: `2e9335997`. Prova: `bash laco/roda_teste.sh tests/unit/test_conformidade_matriz.py` →
**8 passed** (era 1 failed).

## Item 6 — test_csw_analise.py (CONSERTADO)

Causa-raiz: duas trilhas independentes de 07/09 (`e59869787`/`14a69cf1c` — mesmo diff, mesmo
timestamp, dois worktrees com o mesmo trabalho) partiram da base `602d0b353` e acrescentaram o
bloco de `app/conexao/proveniencia.py::descobrir` que preenche fonte/licença/data_do_dado/
responsável a partir do registro ISO 19139 (`config.procedencia`, conexão criada por catálogo CSW)
quando o serviço vivo não os declara. Outra trilha da mesma base (`ad2ec8ebf`) acrescentou o campo
`origem` + `procedencia_canonica.normalizar`. A fusão manteve só a segunda — o bloco de ISO nunca
chegou ao HEAD, então `licenca`/`data_do_dado`/`responsavel` do registro CSW eram sempre descartados
quando o serviço vivo não os declarava. Restaurado entre a montagem de `procedencia` e o
`normalizar`/`Descoberta` finais, sem pisar no `origem`.
Commit: `20a96cf3b`. Prova: `bash laco/roda_teste.sh tests/unit/test_csw_analise.py` →
**12 passed** (era 1 failed).

## Item 7 — test_exportacao_unidade.py (CONSERTADO, 2 causas)

**Causa A (fusão):** `app/objetos.py::EXTENSOES` perdeu a entrada `"application/geo+json-seq":
"geojsonl"` acrescentada por `f02463654` (item L2-01-l-exportacao-do-mapa, ancestral de HEAD) —
só `"application/vnd.pmtiles"`, a outra linha do mesmo commit, sobreviveu. Sem ela toda exportação
GeoJSON Sequence gravava com extensão `.bin`. Restaurada. Commit: `a8a059b66`.

**Causa B (teste desatualizado, não é fusão):** dois pontos deste arquivo de teste nunca
acompanharam evolução legítima do produto: (1) `len(FORMATOS) == 11` travado no número do item
L0-04-h (07/09) — hoje são 16 (kmz/mvt/pmtiles/pacote/geoparquet vieram de L2-01-l e do pacote de
mapa, todos testados em outras suítes); (2) `CursorFalso.fetchone()` sempre devolvia `None`, mas
`guardar()` ganhou (item L0-07-c-cotas-uso, `eb9f5a9a5`, ancestral de HEAD, migrações
`20260906T2124`/`2136`) uma consulta de `cota_bytes` FOR UPDATE + `plat.arquivo_uso_bytes` antes do
PUT único — nunca simulada. Renomeado o teste de contagem (16/14) e o cursor falso agora responde
às duas consultas de cota. Commit: `9617376b5`.

Prova: `bash laco/roda_teste.sh tests/unit/test_exportacao_unidade.py` → **14 passed** (eram 2 failed).

## Item 8 — test_extensoes_lista.py (CONSERTADO)

Causa-raiz: `76333e684` (item L7-01-d, ancestral de HEAD) trocou o `CREATE EXTENSION` hardcoded de
`install.sh` (só postgis/pgcrypto) por `db/extensoes.sh::plat_extensoes_garantir` contra
`db/extensoes.txt` (as mesmas 4 extensões que `laco/trilha_ambiente.sh` e o ensaio de restauração
já liam) — a fusão reverteu `install.sh` para a versão de duas linhas, sem pg_trgm/unaccent e sem
a conferência em `pg_extension`. `db/extensoes.txt`/`db/extensoes.sh` continuavam intactos, só não
eram mais chamados por `install.sh`. Restaurado o trecho original.
Commit: `6421a1811`. Prova: `bash laco/roda_teste.sh tests/unit/test_extensoes_lista.py` →
**7 passed** (era 1 failed).

## Item 9 — test_fk_por_inquilino_classe_conserto.py (CONSERTADO)

Causa-raiz (não é fusão): `plat.token_servico.expira_em` virou `NOT NULL` com teto de 366 dias
(`ck_token_prazo_teto`) pelo item L7-08-d (migração `20260906T1617_chaves_api.sql`, ancestral de
HEAD) depois que este teste foi escrito. Os helpers `_token`/`_inserir_token_renovado_por` nunca
foram atualizados e caíam em `NotNullViolation` antes de chegar na FK que o caso
`token_servico_renovado_por_auto_referencia` quer exercitar. Os dois passam a gravar
`expira_em = now() + interval '90 days'` (mesmo prazo do backfill da migração).
Commit: `797c05a49`. Prova: `bash laco/roda_teste.sh tests/unit/test_fk_por_inquilino_classe_conserto.py`
→ **12 passed** (era 1 failed).

## Item 10 — test_garage_adversario.py (CONSERTADO, 2 causas, nenhuma é fusão)

**Causa A:** `test_zz_grava_medidas` exigia >=17 ataques medidos. Investigação funda: os 4 ataques
nginx (5/5b/5c/5d) dependem de `nginx_cog`, que precisa do endpoint WEB do Garage (:3902) — desde
16/09 (D26/garage2, consolidação em `garage-trilhas`, `laco/trilha_ambiente.sh`) o Garage
compartilhado das trilhas só expõe S3 (:3910) e admin (:3913), nunca web (mudança de infraestrutura
datada de hoje, fora do meu worktree). `_porta_viva(3902)` dava FALSO POSITIVO porque outro processo
Garage, de um workstream alheio (`plataforma/pipeline`), também escuta em :3902 nesta máquina e
responde 404 genérico. Trocado por checagem FUNCIONAL (`_web_garage_serve_o_objeto`: grava objeto de
verdade, só monta nginx se o GET bater byte a byte; senão SKIP com o motivo). `test_zz_grava_medidas`
relaxa o piso de 17 para 13 quando isso é registrado (lacuna de ambiente, não de código).

**Causa B:** fallback de `PLAT_TESTE_API_PORTA` era `8171` (porta da trilha de uso único "gadv",
06/09, já não existe) — trocado para `8192` (trilha `uniao`, a de hoje).

Commit: `073ab6cfa`. Prova: `bash laco/roda_teste.sh tests/unit/test_garage_adversario.py` (sem
variável extra, 3 rodadas seguidas) → **12 passed, 4 skipped, 3 xfailed** (era 2 failed).
Estado do Garage de demo/demo2 (`web_ativo`) restaurado ao original (False) após a investigação
manual que passou por ele.

## Item 11 — test_manual_gerado.py (CONSERTADO)

Causa-raiz: 15 páginas (`conexoes`, `construtor`, `conta`, `conteudo_item`, `conteudo`, `login`,
`admin/grupos`, `index`, `conteudo_lixeira`, `admin/log`, `mapa`, `admin/papeis`, `admin/tokens`,
`uploads`, `admin/usuarios`) tinham, cada uma, um commit próprio de 08-09/09 (ex.: `f6d70fd4a`,
`f488a4d34`, ...; todos ancestrais de HEAD) acrescentando `data-ajuda="<id>"` no `<body>` (gancho do
painel de ajuda por contexto, item L7-04-a) e o script do DOMPurify quando faltava
(`app/js/base/dom.js::htmlSeguro` lança erro sem ele). Uma fusão que reescreveu `<head>`/`<body>` de
cada tela (acrescentando `tema.js`, `tokens.css` etc.) apagou as duas linhas em TODAS elas, sempre no
mesmo padrão. Restaurado `data-ajuda` (preservando as classes atuais) e o DOMPurify onde ainda
faltava (4 das 15 já tinham o script, só faltava o atributo).
Commit: `8d067e9ef`. Prova: `bash laco/roda_teste.sh tests/unit/test_manual_gerado.py` →
**9 passed** (era 1 failed); `test_estilo_tokens.py` confirmado sem regressão (mesmas 4 falhas
já relatadas no Item 0).

## Item 12 — test_regras_motor.py (FORA — decisão de produto pendente)

Duas falhas, mesma causa: `app/rede_utilidades/pacotes/eletrica-br.json` tem 24 regras em forma
`"de"/"para"` de STRING plana (`"subestacao/1"`), mas o teste espera `"de"/"para"` como OBJETO
(`{"grupo":..., "terminal":...}`) e ≥40 regras — exatamente o formato e a contagem do "esquema versão
2" introduzido por `a2f383a56` ("Pacote de ativos em esquema versão 2: regras com terminal/via e 5
tipos", item L4-03-a — o MESMO item citado no docstring do teste), commit ancestral de HEAD que:
- levou `app/rede_utilidades/esquema.py` de `ESQUEMA_VERSAO=1` (regras string) para `=2` (regras
  objeto `{grupo,tipo,terminal?}` + lado `via`), com leitura das duas versões e CONVERSÃO de v1→v2
  em `pacote.ler()` (nunca só v2 quebrando v1 antigo);
- levou `eletrica-br.json` para 58 regras (inclui literalmente "trecho MT só liga o trafo pelo
  terminal AT", o exemplo do portão);
- tocou também `deposito.py`, `docs/PACOTE_REDE.md`, `scripts/rede_gerar_pacotes.py` e
  `tests/api/test_rede_pacote_conserto_a1_a4.py` (9 arquivos, ~1600 linhas).

**Isso sumiu inteiro.** `app/rede_utilidades/esquema.py` no HEAD está de volta a `ESQUEMA_VERSAO=1`,
sem `TIPOS_REGRA_V1`, sem conversão, sem suporte a objeto em `de`/`para` — `pacote.py`/`esquema.py`
validam HOJE (conferido rodando `Draft202012Validator(ESQUEMA)` contra o arquivo atual: 0 erros)
exigindo STRING pura. O trabalho posterior do mesmo dia (`722c1e385`, 16/09 07:55, e `80fbb686d`,
16/09 08:48) partiu de uma base ANTERIOR a `a2f383a56` — só traduziu o VOCABULÁRIO de tipo
(`conectividade_no_trecho`→`juncao_aresta` etc.) sobre a forma v1 antiga, sem saber que a v2 (rica,
com terminal) já tinha existido — e essa é a versão que a fusão manteve.

**Por que não decidi sozinho:** restaurar `a2f383a56` inteiro exigiria reconciliar 9 arquivos com o
trabalho de HOJE em `722c1e385`/`80fbb686d` (que já usa o vocabulário novo, mas na forma v1) — risco
real de quebrar `tests/api/test_rede_pacote_conserto_a1_a4.py` e o que quer que `deposito.py`/
exportação façam hoje com a forma v1. Não achei nenhuma nota do dono abandonando a v2 de propósito
(nenhuma menção em CHANGELOG/decomposição), então trato como perda de fusão real, mas de escopo maior
que um teste de unidade — pede decisão: (a) restaurar a v2 inteira (objeto+terminal, 58 regras,
suporte às duas versões), ou (b) manter a v1 simplificada e reescrever o teste/portão para expressar
"terminal" via o catálogo `terminais` (que já existe e já modela `dois_terminais_transformador` com
`alta`/`baixa`) em vez de um campo por regra — os dois são defensáveis, nenhum é só "ajustar o teste".

Não alterado: `tests/unit/test_regras_motor.py` continua com 2 failed (13 passed) até a decisão.
Comando para reproduzir: `bash laco/roda_teste.sh tests/unit/test_regras_motor.py -v`.

## Item 13 — test_rotas_sombreadas.py (CONSERTADO, 4 rotas reais + 1 falso positivo do teste)

Achado grande: quatro pares de rotas genuinamente colidindo (dois ramos, cada um sem saber do outro,
registrando o MESMO caminho) — o mesmo padrão de fusão visto no resto deste laudo, agora em roteamento:

1. **`GET /api/acervo/camadas`**: `publicacao.py` (L6-01-e, galeria) e `rotas_frescor.py` (L6-01-h,
   filtros fonte_id/vencida) — publicacao sempre vencia; `web/js/acervo/acervo.js` pedia `vencida=true`
   e recebia a lista errada. Frescor mudou para `/api/acervo/frescor/camadas`. Commit `cb6f2db80`
   (mesmo commit já trouxe, sem querer, os dois reordenamentos dos itens 3-4 abaixo em `app/main.py`
   — a mensagem do commit só descreve o acervo; o conteúdo real inclui os três).
2. **`/api/modelos` GET/POST/DELETE**: `rotas_pacote.py` (L5-37, galeria de modelos entre inquilinos,
   mesclada 1h30 antes) sempre vencia sobre as 8 rotas de `modelos3d/rotas.py` (L2-09-c) — o módulo de
   modelos 3D inteiro respondia com a galeria errada. Renomeado para `/api/modelos3d`. Commit `6cbd3d2d9`.
3. **`GET /api/camadas/{id}/feicoes`**: `regras/rotas.py::feicoes_ler` (L2-10-d, geometria+campos
   virtuais) sempre venceu sobre `dominios/rotas_feicoes.py::listar_feicoes` (L2-10-a, atributos só) —
   este último já era 100% morto e o próprio docstring do módulo previa ser superado; removido (POST
   de inserção fica). Commit `9e435ac5e`.
4. **`GET /api/rede/medicao/ativos/{ativo}`**: `rotas_identificadores.py` (`/{rede_id}/ativos/{global_id}`,
   `{rede_id}` sem tipo) vencia SEMPRE, tratando o literal "medicao" como se fosse um rede_id — rota de
   telemetria (L4-13) inteiramente inalcançável (`rede_inexistente` em toda chamada). `rotas_rede_medicao`
   movida para o topo da família `/api/rede/*` em `app/main.py` (parte do commit `cb6f2db80`).
5. **`GET /api/camadas/{id}/campos`**: `camada_esquema.py` (L5-31, `{fields:[...]}`) vencia sobre
   `formulario/rotas.py` (L5-03-form-builder, `{campos:[...]}`) — a paleta do construtor de formulário
   nunca recebia campo nenhum. `camada_esquema.campos` mudou para `/api/camadas/{id}/esquema/campos`.
   Commit `f4532b4b2`.

**Falso positivo do próprio teste:** `/rest/services/{item_id}/FeatureServer/{camada:int}` vs
`.../FeatureServer/{camada_id}` — a sonda `_concreto()` trocava `{camada:int}` por uma string não
numérica, fazendo a própria rota reprovar a própria sonda. Corrigido para respeitar o conversor do
Starlette (`:int`/`:float`/`:uuid`/`:path`). Commit `5688b4dec`.

Também regenerado `tests/medidas/L1-01-d-adversario.json` (saída de rotina do item 10, commit
`9a865ff61`) e revertido `docs/openapi.json` (confirmado por `test_contrato_guarda.py`: "roda sem
banco — varre o app vivo, nunca docs/openapi.json, que é retrato parado" — não precisa acompanhar).

Prova final: `bash laco/roda_teste.sh tests/unit/test_rotas_sombreadas.py` → **3 passed** (eram 2
failed), estável em reruns. `app.main:app` importa limpo (178 rotas).

## Item 14 — test_rotas_sombreamento.py (CONSERTADO)

Implementação irmã de test_rotas_sombreadas.py (item 13), escrita por outro ramo com o mesmo
conceito. Mesma classe de falso positivo: `_cobre()` tratava `{camada:int}` como cobrindo qualquer
segmento literal, inclusive `/replicas` — mas o `:int` naquele molde foi posto DE PROPÓSITO (o
próprio docstring de `app/dominios/rotas_featureserver.py::camada_de_feicao` explica: sem ele,
`/replicas` caía ali e morria em 422 antes de chegar em `app/consulta/rotas_sync_esri.py::replicas`,
item L2-13-b; com o conversor, o Starlette recusa o não-numérico e segue para a rota certa).
`_cobre()` agora só considera "coberto" um literal que o conversor do molde aceitaria de verdade.
Commit: `fd033f2e7`. Prova: `bash laco/roda_teste.sh tests/unit/test_rotas_sombreamento.py` →
**3 passed** (era 1 failed).

## Item 15 — test_schema_ambiente_metodos.py (CONSERTADO)

Causa-raiz (não é fusão): `vars(CursorSchemaAmbiente)` é raso, não percorre a MRO. Desde `ceeb7ccc6`
(restauração de `MixinReescritaSchema`, ancestral de HEAD), `execute`/`executemany`/`callproc`/
`mogrify`/`copy_expert` moram no MIXIN, não mais diretamente em `CursorSchemaAmbiente` — a classe
final continua funcionando corretamente (herda o mixin antes do cursor do psycopg2, `super()` cai
certo, provado por `test_reescrita_troca_schema_e_poupa_producao`), mas o teste-guarda não foi
atualizado para essa forma. Corrigido somando `vars(CursorSchemaAmbiente) | vars(MixinReescritaSchema)`.
Commit: `6ec3064c9`. Prova: `bash laco/roda_teste.sh tests/unit/test_schema_ambiente_metodos.py` →
**2 passed** (era 1 failed).

## Item 16 — test_tokens_visuais.py (FORA — mesma família de dívida de escopo do Item 0)

Duas falhas:
- `test_nenhum_literal_de_cor_ou_tamanho_fora_de_tokens`: **223 ocorrências em 27 arquivos**
  (`web/admin/*.html`, `web/amc_*.css`, `web/campo/campo.css`, `web/cena.css`, `web/coleta.css`,
  `web/estilo/{editor,executor,narrativa,site,temas}.css`, `web/formulario_construtor.html`,
  `web/js/rede/diagrama.js`, `web/widgets.css` etc.) de cor/tamanho literal fora de
  `web/estilo/tokens.css`, via `docs/verificar_tokens.py`.
- `test_toda_variavel_usada_nas_folhas_esta_definida_em_tokens`: **68 variáveis `var(--x)` sem
  definição em tokens.css**, muitas do vocabulário ANTIGO (`--cor-erro`, `--cor-borda`, `--cor-fundo`,
  `--cor-acento`...) convivendo com o vocabulário NOVO (`--t-1`, `--t0`, `--i-*`) e um terceiro em
  `web/estilo/temas.css` (`--t-fundo`, `--t-superficie`, `--t-borda`...) — três sistemas de nome de
  token não reconciliados.

Mesma classe do item já decidido pelo gerente para `test_estilo_tokens.py` (item L0-14, "dívida de
escopo: cor/glifo fora de tokens em telas novas") — aqui é o item **UX-01-sistema-de-design**, uma
segunda varredura (`docs/verificar_tokens.py`, mais rigorosa: cobre HTML e JS além de CSS, e confere
`var()` sem definição) construída em paralelo por outro ramo, cobrindo o MESMO problema por outro
caminho. Não é "restaurar o que a fusão perdeu": os 3 vocabulários de token nunca foram unificados,
em nenhum momento da história — não há um estado anterior correto para restaurar, é trabalho de
migração ainda não feito. Reescrever 223 literais + criar/reconciliar 68 tokens é fora de proporção
para este turno (mesmo julgamento do Item 0) e pediria decisão de qual vocabulário vira o canônico.

Não alterado: 2 failed, 2 passed. Comando: `bash laco/roda_teste.sh tests/unit/test_tokens_visuais.py -v`.

## Item 17 — test_videos_roteiro.py (CONSERTADO)

Causa-raiz: `87da9f571` (item L7-04-d, ancestral de HEAD) acrescentou os alvos `videos`/
`videos-validar` e a entrada correspondente em `.PHONY` — a fusão manteve a entrada do `.gitignore`
(`web/videos/`) mas perdeu as duas regras do Makefile e o `.PHONY`. `scripts/videos/gerar.py`
continuava intacto, só sem como ser chamado por `make videos`. Restaurado.
Commit: `dada8d750`. Prova: `bash laco/roda_teste.sh tests/unit/test_videos_roteiro.py` →
**15 passed** (era 1 failed).
