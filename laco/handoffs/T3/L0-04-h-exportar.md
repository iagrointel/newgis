# L0-04-h-exportar — exportação de camada em 11 formatos

Trilha `stac`, worktree `/home/dev/plataforma/wt/stac`, ramo `wt/stac`. Base de teste própria `plat_tt04h`
(`bash laco/trilha_ambiente.sh t04h`), **sem** `flock`. 06/09/2026.

## 1. O que foi construído

| arquivo | o que é |
|---|---|
| `db/migracoes/20260906T1551_exportacao_camada.sql` | `plat.exportacao` (+RLS, gatilho de estado final), `plat.exportacoes_em_curso()`, `plat.exportacoes_expirar_candidatos()` (SECURITY DEFINER), privilégio `conteudo.exportar`, esquema **v3** do tipo `camada_vetorial` (bloco `exportacao.permitir_outros`), eventos `camadas/exportar` e `camadas/exportar_baixar` |
| `app/exportacao/formatos.py` | catálogo dos 11 formatos (driver, extensão, tipo de conteúdo, codificações, o que cada formato NÃO guarda) |
| `app/exportacao/motor.py` | string de conexão do ogr2ogr COM o inquilino (`options='-c plat.tenant_id=N'`), montagem da consulta (`where_ast` + `mogrify`), guarda de disco, argumentos do ogr2ogr, zip, GeoParquet por DuckDB, contagem lida do arquivo gerado |
| `app/exportacao/csv_saida.py` | CSV brasileiro (separador, vírgula decimal, nomes das colunas de coordenada, codificação), linha a linha |
| `app/exportacao/erros.py` | erro do banco saneado para o corpo do 400 |
| `app/exportacao/tarefas.py` | job `exportacao.gerar` |
| `app/exportacao/periodicos.py` | periódico `exportacao.expirar` (de hora em hora) |
| `app/exportacao/rotas.py` | `GET /api/exportacoes/formatos`, `POST /api/exportacoes`, `GET /api/exportacoes[/{id}]`, `GET /api/exportacoes/{id}/baixar`, `DELETE /api/exportacoes/{id}` |
| `app/objetos.py` | **novo** `guardar_arquivo` (envio de arquivo do disco em blocos, multipart real acima de 8 MiB) e `ler_stream`; tipos de conteúdo dos formatos em `EXTENSOES` |
| `app/schema_ambiente.py` | `CursorSchemaAmbiente` passou a reescrever o schema em `executemany` e `mogrify` (ver seção 5) |
| `app/auth/privilegios.py`, `app/limites.py`, `app/jobs/tipos.py`, `app/main.py` | espelho do privilégio novo, seção de limites da exportação, registro do tipo de job, router |
| `web/js/catalogo/item_exportar.js`, `item.js`, `api.js`, `web/js/i18n/pt-BR.json` | botão **Exportar** no painel do item + diálogo (formato, campos, filtro, CRS, codificação, opções de CSV, caixa do dono "permitir que outros exportem") |
| `docs/adr/0023-exportacao-de-camada.md`, `CHANGELOG.md`, `docs/LIMITES.md`, `docs/PRIVILEGIOS.md`, `docs/openapi.json`, `requirements.txt` | documentação e dependências |
| `tests/unit/test_exportacao_unidade.py`, `tests/api/exportacao/*`, `tests/e2e/test_exportar.py` | testes (seção 2) |

## 2. Portão de pronto, cláusula por cláusula

Comando comum a todas:

```bash
bash /home/dev/plataforma/laco/trilha_ambiente.sh t04h
set -a; source /home/dev/plataforma/laco/var/trilha/t04h.env; set +a
cd /home/dev/plataforma/wt/stac
venv/bin/pytest tests/api/exportacao tests/unit/test_exportacao_unidade.py -q
```

| cláusula do portão | prova | resultado |
|---|---|---|
| "10 formatos gerados de uma camada de 100 mil feições, cada um reaberto por ogrinfo com a mesma contagem" | `test_onze_formatos_da_camada_de_100_mil_feicoes_reabertos_com_a_mesma_contagem` | PENDENTE_NUMERO |
| "CSV com vírgula decimal opcional" | `test_csv_com_virgula_decimal_e_colunas_de_coordenada_escolhidas` + 5 de unidade em `test_exportacao_unidade.py` | PENDENTE_NUMERO |
| "export com where inválido devolve 400 com o erro do banco saneado" | `test_where_invalido_devolve_400_com_erro_saneado` (5 casos) + `test_erro_do_banco_perde_nome_interno_comando_e_caminho` | PENDENTE_NUMERO |
| "usuário sem 'exportar' recebe 403 na camada de outro" | `test_usuario_sem_privilegio_exportar_recebe_403`, `test_camada_de_outro_inquilino_e_404`, `test_camada_de_outro_usuario_do_mesmo_inquilino_exige_a_opcao_do_dono` | PENDENTE_NUMERO |
| "arquivo expira e some em 7 dias" | `test_arquivo_expira_e_some_em_sete_dias` | PENDENTE_NUMERO |
| "e2e do botão Exportar com captura" | `tests/e2e/test_exportar.py` | PENDENTE_E2E |
| "medida tempo por formato" | `tests/medidas/L0-04-h-exportar.json` | PENDENTE_NUMERO |

## 3. Refutação exigida

| ataque do adversário | prova | resultado |
|---|---|---|
| "5 exportações em paralelo da mesma camada (limite de jobs por usuário)" | `test_limite_de_exportacoes_em_curso_por_usuario` | PENDENTE_NUMERO |
| "... e de disco temporário" | `test_disco_insuficiente_recusa_antes_de_escrever` | PENDENTE_NUMERO |
| "injeta SQL no where" | `test_injecao_no_where_nao_apaga_nem_vaza` (5 vetores) | PENDENTE_NUMERO |
| "pede EPSG inexistente" | `test_epsg_inexistente_e_recusado_e_epsg_valido_reprojeta` | PENDENTE_NUMERO |

## 4. Exigência do gerente (dado de cliente)

PENDENTE_CRUZADO

## 5. Consertos de produto que este item destravou

PENDENTE_CONSERTOS

## 6. Fronteira honesta

PENDENTE_FRONTEIRA

## 7. Commits do ramo

PENDENTE_COMMITS
