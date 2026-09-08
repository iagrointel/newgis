# L3-01-a-modelo-dado — modelo do motor multicritério, versão por hash e proveniência da execução

Ramo `wt/amc`, worktree `/home/dev/plataforma/wt/amc`. Commits `d794266` (implementação) e `7f40612` (testes,
medidas, CHANGELOG). Turno 3, setembro de 2026.

## O que foi construído

| arquivo | o que faz |
|---|---|
| `db/migracoes/044_amc.sql` | sete tabelas `plat.amc_*` com RLS por inquilino, gatilhos de imutabilidade e vocabulário de eventos |
| `docs/esquemas/amc_modelo.v1.json` | JSON Schema Draft 2020-12 do documento do modelo (fatores, restrições, transformações, combinadores) |
| `app/amc/esquema.py` | validação em duas camadas (esquema + semântica) e hash canônico |
| `app/amc/camadas.py` | proveniência de cada camada de entrada da execução (acervo e item do catálogo) |
| `app/amc/rotas.py` | 18 rotas `/api/amc` (modelos, conjuntos, execuções) sob o privilégio `analise.amc` |
| `scripts/amc_hash_independente.py` | recomputa o hash por fora da aplicação (arquivo ou banco) |
| `docs/adr/0016-motor-amc-modelo-e-unidades.md` | decisão registrada, com o que foi descartado e por quê |

Forma: `plat.amc_modelo` é a cabeça editável (nome + versão atual); `plat.amc_modelo_versao` guarda toda versão que
já existiu, imutável para `plat_app`; `plat.amc_execucao` referencia o par (modelo, versão) por chave estrangeira
composta e congela pesos, camadas, versão do motor e semente; `plat.amc_fator_bruto` e `plat.amc_resultado` são
linhas por (execução, unidade, fator), nunca coluna por fator.

## Cláusula do portão → prova

| cláusula | prova |
|---|---|
| migração idempotente | `sudo -u postgres PLAT_MIGRACOES=$PWD/db/migracoes bash db/migrar.sh` duas vezes: 2ª rodada diz `aplicadas 0 · pendentes 0`; todo objeto é `IF NOT EXISTS` / `CREATE OR REPLACE` / `DROP ... IF EXISTS` |
| JSON Schema em `docs/esquemas/amc_modelo.v1.json` validado no POST | `tests/unit/test_amc_esquema.py::test_esquema_publicado_e_valido_e_e_o_declarado` e `tests/api/amc/test_modelo.py::test_modelo_valido_nasce_com_hash_e_versao_1` |
| peso negativo → 422 com a cláusula | `test_modelo_invalido_devolve_422_com_a_clausula[peso_negativo]` → cláusula `fatores[].peso >= 0` |
| fator sem transformação → 422 com a cláusula | `[fator_sem_transformacao]` → `fatores[].transformacao obrigatória` |
| soma de pesos zero → 422 com a cláusula | `[soma_de_pesos_zero]` → `soma(fatores[].peso) > 0` |
| fator duplicado → 422 com a cláusula | `[fator_duplicado]` → `fatores[].id único` |
| teste cruzado A→B falha em `amc_modelo`, `amc_execucao`, `amc_resultado` | `test_a_nao_le_modelo_execucao_nem_resultado_de_b_pela_api` (11 rotas por id direto de B: todas 401/403/404) e `test_rls_no_banco_esconde_amc_de_outro_inquilino` (as seis tabelas com o contexto do outro inquilino: 0 linhas; INSERT com `tenant_id` alheio barrado pelo `WITH CHECK`). Além disso as 18 rotas entraram na varredura cruzada gerada do OpenAPI (`tests/api/test_cruzado.py`, 100 % de cobertura mantida) |
| hash recomputado por script independente igual ao gravado | `test_script_independente_da_o_mesmo_hash` (arquivo) e `test_script_independente_confere_o_que_esta_no_banco` (`scripts/amc_hash_independente.py --tenant <id>` → `divergentes: 0 · cabeças órfãs: 0`) |
| OpenAPI atualizado | `make openapi` rodado; `docs/openapi.json` comitado com as 18 rotas; `tests/api/test_privilegios_declarados.py` verde (toda rota declara `x-auth` e `x-privilegio`) |

## Refutação (escrita como teste, não como promessa)

`test_refutacao_editar_modelo_executado_nao_muda_a_execucao_nem_o_resultado`: cria modelo, conjunto e execução;
grava dois resultados; **edita o modelo** (peso e transformação diferentes) e confere que a cabeça mudou de versão,
que a execução continua com `versao_hash` antigo, que `GET /api/amc/execucoes/{id}` devolve a definição QUE RODOU,
e que os resultados são bit a bit os mesmos.

`test_versao_gravada_e_imutavel_para_a_aplicacao`: `UPDATE` e `DELETE` em `plat.amc_modelo_versao` como `plat_app`
levantam `amc_versao_imutavel`.

Ler execução de outro inquilino por id direto: coberto acima (404 em `GET/DELETE /api/amc/execucoes/{id}` e em
`/resultados`), e a execução de B não aparece na listagem de A.

## Comandos para o adversário reproduzir

```bash
cd /home/dev/plataforma/wt/amc
export PLAT_SECRET=$(sudo cat /etc/plat/segredos/PLAT_SECRET)
flock /home/dev/plataforma/laco/.pytest.lock venv/bin/pytest tests/unit/test_amc_esquema.py tests/api/amc/test_modelo.py
# hash por fora da aplicação, direto do banco (o id do inquilino sai de plat.auth_login('demo','admin'))
venv/bin/python scripts/amc_hash_independente.py --tenant <id>
# varredura cruzada inteira (inclui as 18 rotas novas)
flock /home/dev/plataforma/laco/.pytest.lock venv/bin/pytest tests/api/test_cruzado.py
```

## O que ficou de fora, e por quê

- **Extração de fator, transformações e combinação** são os itens L3-01-c/d/e. A execução nasce no estado
  `registrada`; nada calcula favorabilidade ainda. As tabelas para isso já existem, então esses itens não precisam
  de migração nova para o caminho básico.
- **Contagem e sha256 de camada `item`**: só a tabela hospedada no schema de trabalho é contada (`COUNT(*)` com
  25 s de limite dentro de um SAVEPOINT). Nos outros casos o campo diz `nao_registrado`. Isso é deliberado: valor
  inventado em campo de proveniência é pior que campo vazio.
- **Item de catálogo do tipo `modelo_amc`**: o tipo existe no catálogo, mas ligar o modelo do motor a um item do
  catálogo é o item L3-13 (publicar resultado como camada). Aqui o modelo vive só em `plat.amc_modelo`.
- **Assinatura/exigência de árvore git limpa para execução "oficial"** (parte da decisão A10): a versão do motor
  já grava o sha do commit, mas não há portão que recuse execução com árvore suja. Fica para o item de relatório.

## Limitações honestas

- `motor_versao` é `amc/0.1+<VERSAO>+<sha curto>`. O `amc/0.1` só muda quando extrator, transformação ou
  combinador mudarem de resultado — quem mexer nesses módulos tem de subir esse número à mão; não há teste que
  force isso ainda.
- A execução é criada de forma síncrona e resolve as camadas na hora. Com muitas camadas de acervo isso pode
  passar de um segundo; não foi medido com mais de 3 camadas.
- Apagar modelo é esconder (`apagado_em`). As versões e as execuções ficam. A cota de 500 modelos conta só os não
  escondidos, então rodadas repetidas da suíte não esgotam a cota, mas deixam linhas.

## Riscos de merge

- `app/main.py` (uma linha de import + uma no `ROUTERS`), `app/jobs/tipos.py` (uma linha de import),
  `app/limites.py` (uma seção no fim), `CHANGELOG.md`, `docs/LIMITES.md`, `docs/openapi.json` — todos também
  mexidos pela árvore principal; as mudanças aqui são localizadas e no fim de cada arquivo.
- `tests/api/cruzado_casos.py`: três campos novos em `Preparacao`, um bloco de criação em `preparar()`, três
  linhas em `desfazer()` e 18 casos no fim do dicionário `CASOS`. Conflito provável se outra trilha acrescentar
  rotas ao mesmo dicionário — a resolução é juntar os dois blocos.
- **Numeração da migração**: renumerada de 031 para 037 e depois para **044** por ordem do gerente. A árvore
  principal estava em `041_acervo_lgpd` quando este handoff foi escrito (`ls
  /home/dev/plataforma/enterprise/db/migracoes | tail -3` = 036, 040, 041). Se ela passar de 043 antes do merge,
  avisar em vez de renumerar sozinho.
- `tests/api/test_migracoes.py::test_tabela_reflete_os_arquivos_em_disco` **falha neste worktree** e falhava antes
  deste trabalho: o banco é compartilhado e já tem as migrações 029/032/034/036/040/041 da árvore principal, que
  não existem em disco aqui. `044_amc` está aplicada e em disco. O teste volta a passar depois do merge.


---

## Correção de 06/09/2026 (depois do laudo `L3-01-ADVERSARIO.md` e do conserto `L3-01-CONSERTO.md`)

**Contagem de testes — o número que circulou estava errado.** O painel do laço (`laco/PAINEL.md`, linha 226) diz
"207 testes" e o `CHANGELOG.md` dizia "45 testes novos". **Nenhum dos dois sai de artefato nenhum.** O adversário
do item procurou e não achou; conferido depois, ele tem razão nos dois casos. O número verificável, no estado em
que este handoff foi escrito (commits `d794266` + `7f40612`), é **47 casos de teste**, contados assim:

```
$ set -a; source laco/var/trilha/<trilha>.env; set +a
$ venv/bin/pytest tests/unit/test_amc_esquema.py tests/unit/test_amc_crs.py \
                  tests/api/amc/test_modelo.py tests/api/amc/test_unidades.py --collect-only -q | tail -5
tests/api/amc/test_modelo.py: 16
tests/api/amc/test_unidades.py: 12
tests/unit/test_amc_crs.py: 8
tests/unit/test_amc_esquema.py: 11
```

11 + 8 + 16 + 12 = **47**. São CASOS, não funções: `grep -c "^def test_"` nos mesmos quatro arquivos dá **38**
funções, e os `@pytest.mark.parametrize` expandem a diferença. "45" não é nem uma coisa nem outra. Depois do
conserto os mesmos quatro arquivos somam **73 casos** (31 + 9 + 20 + 13), mais **40** do adversário
(`tests/unit/test_amc_adversario.py` 23 + `tests/api/amc/test_amc_adversario_api.py` 17) e **22** da trava nova
`tests/unit/test_schema_ambiente.py`.

⚠ `laco/PAINEL.md` **não foi editado por esta trilha** (é do gerente): a linha 226 continua com "207 testes" e
precisa da correção dele.

**Numeração da migração**: `044_amc.sql` foi renumerada para **`045_amc.sql`** — a árvore principal publicou
`044_uploads.sql` enquanto esta trilha estava parada. Referências corrigidas em `CHANGELOG.md`,
`app/amc/__init__.py`, `app/amc/rotas.py` e `tests/api/amc/test_modelo.py`.
