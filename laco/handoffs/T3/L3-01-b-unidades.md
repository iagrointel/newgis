# L3-01-b-unidades — conjunto de unidades de análise (grade PostGIS ou feições do usuário)

Ramo `wt/amc`, worktree `/home/dev/plataforma/wt/amc`. Commits `d794266` e `7f40612`. Turno 3, setembro de 2026.

## O que foi construído

| arquivo | o que faz |
|---|---|
| `app/amc/crs.py` | escolhe o CRS de trabalho (UTM SIRGAS 2000 da zona do centróide) e MEDE a distorção de área com `pyproj.Proj.get_factors(...).areal_scale` |
| `app/amc/unidades.py` | valida a área, estima a contagem, gera a grade em faixas de até 100 mil células e grava feições do usuário |
| `app/amc/tarefas.py` | tipo de job `amc.gerar_unidades` (registro no `app/jobs/tipos.py`: uma linha) |
| `app/amc/rotas.py` | `POST/GET/DELETE /api/amc/conjuntos`, `GET /api/amc/conjuntos/{id}`, `GET .../unidades` |
| tabelas | `plat.amc_conjunto_unidade` (ficha em JSONB) e `plat.amc_unidade` (chave `(conjunto_id, unidade_id)`, geometria 4326, `area_m2` geodésica) |

Grade: `ST_HexagonGrid` ou `ST_SquareGrid` no `srid_trabalho`, célula inteira dentro da área mantida, célula de
borda recortada por `ST_Intersection`, resultado reprojetado para 4326 e área calculada em `geography` (GRS80).
Feições: id vem de `feature.id` ou de uma propriedade escolhida (`campo_id`), preservado como `unidade_id`.

## Cláusula do portão → prova

| cláusula | prova |
|---|---|
| grade de 250 m sobre polígono de 2.000 km² como job em ≤ 60 s | **1,14 s** medidos (`tests/medidas/L3-01-b.json`, campo `grade_250m_2000km2_segundos`); o conjunto nasce com `estado='pendente'` e `job_id` preenchido, e o teste afirma isso antes de rodar a função do job |
| contagem bate com área / área da célula ± 2 % | **1,175 %** (`grade_250m_2000km2_desvio_contagem_pct`); o esperado é calculado por fora do banco, projetando o polígono com pyproj e medindo com shapely |
| grade de 100 m sobre 10.000 km² (≈ 1 mi de células) em tempo medido e gravado | ⚠ **CLÁUSULA CUMPRIDA DEPOIS, e não por esta trilha** — o adversário do item gerou a escala em 06/09/2026, com 43 GB livres em `/mnt/pgdata`: **1.000.175 células em 30,97 s**, desvio de contagem +0,201 %; a re-medição depois do conserto do teto (o teto passou a valer para a contagem real) deu **989.334 células em 33,55 s**, +0,202 %. `tests/medidas/L3-01-b.json` já traz o valor MEDIDO no lugar do extrapolado. O texto abaixo é o que valia quando este handoff foi escrito: **NÃO medido nessa escala.** `/mnt/pgdata` está a 99 % com 13 GB livres, então, pela permissão do próprio item, mediu-se **100 m sobre 2.500 km² = 250.986 células em 8,61 s**, ocupando 186 MB de tabela e índices. A extrapolação linear (34,3 s e ~741 MB para 1 milhão) está gravada em campos cujo nome termina em `EXTRAPOLADO`, com o comando que a produziu. Os conjuntos de teste foram APAGADOS ao fim (`plat.amc_unidade` volta a 0 linhas; o espaço já reservado no arquivo permanece até o autovacuum) |
| feições com id duplicado recusadas com mensagem em português | `test_feicao_com_id_duplicado_e_recusada_em_portugues` → 422 `feicoes_id_duplicado`, mensagem "…id(s) repetido(s) em feature.id: a; o id da unidade tem de ser único", com as posições no detalhe. Também `feicoes_sem_id` para id ausente |
| CRS de trabalho e distorção máxima de área gravados na ficha (a API devolve a ficha) | `GET /api/amc/conjuntos/{id}` devolve `ficha` com `srid_trabalho`, `crs_nome`, `zona_utm`, `hemisferio`, `meridiano_central`, `distorcao_area_min_pct`, `distorcao_area_max_pct`, `distorcao_area_max_abs_pct`, `zonas_utm_cobertas`, `cruza_zonas_utm`, `avisos` e `metodo`. Provado em `test_e2e_da_api_do_conjunto` e `test_area_que_cruza_duas_zonas_utm_e_aceita_com_crs_e_distorcao_declarados` |
| e2e da API | `test_e2e_da_api_do_conjunto`: POST → GET (pendente, ficha com contagem esperada) → job → GET (pronto) → `GET .../unidades` paginado em GeoJSON, com e sem geometria → DELETE 204 → GET 404 |

## Refutação (escrita como teste)

- **Contagem e área conferidas por cálculo independente**: `pyproj.Transformer` + `shapely` para a área no plano, e
  `pyproj.Geod(ellps="GRS80")` para a área geodésica. A soma das áreas geodésicas das células reproduz a área da
  região de estudo com erro ≤ 0,5 % — ou seja, o recorte não perde nem duplica área.
- **Área que cruza duas zonas UTM**: `test_area_que_cruza_duas_zonas_utm_e_aceita_com_crs_e_distorcao_declarados`
  (3° de longitude a cavalo do meridiano −48°). O conjunto usa um CRS só, o da zona do centróide, e a ficha traz
  `cruza_zonas_utm: true`, `zonas_utm_cobertas: [22, 23]`, a distorção medida e o aviso escrito. Em unidade:
  `tests/unit/test_amc_crs.py` confere o mesmo sem banco, e ainda o sinal da distorção (no meridiano central o
  fator de escala é 0,9996, logo a área no plano é MENOR que a geodésica — a ficha tem de dar valor negativo).
- Fora da cobertura brasileira do SIRGAS 2000 a criação falha com 422 `crs_fora_da_cobertura` em vez de devolver
  um CRS qualquer.

## Comandos para o adversário reproduzir

```bash
cd /home/dev/plataforma/wt/amc
export PLAT_SECRET=$(sudo cat /etc/plat/segredos/PLAT_SECRET)
flock /home/dev/plataforma/laco/.pytest.lock venv/bin/pytest tests/unit/test_amc_crs.py tests/api/amc/test_unidades.py -m "not lento"
# as duas medidas (cria e apaga ~283 mil células; confira o disco antes: df -h /mnt/pgdata)
flock /home/dev/plataforma/laco/.pytest.lock env PLAT_GRAVAR_MEDIDAS=1 venv/bin/pytest tests/api/amc/test_unidades.py -m lento
```

## O que ficou de fora, e por quê

- **O worker de produção não conhece `amc.gerar_unidades` até o merge** (o processo em execução carregou
  `app/jobs/tipos.py` antes desta trilha existir). Por isso os testes chamam `app.amc.unidades.gerar_grade`
  diretamente, com um contexto de teste que implementa `db()`, `log()`, `progresso()` e `verificar()` — a mesma
  interface do `ContextoJob`. Depois do merge e do restart do `plat-worker`, o job roda pela fila sem mudança de
  código. **Isto não foi verificado com o worker real** e o adversário deve exigir essa prova no merge.
- **H3**: `h3-pg` não está instalado e o brief proíbe instalar. Fica como índice opcional por biblioteca Python.
- **Envio de arquivo (KML/shapefile/GPKG) para o conjunto de feições**: aqui só GeoJSON inline, com teto de 20 mil
  feições por envio. Arquivo é o caminho da ingestão (L0-04).
- **Tela**: o item pedia só a ficha pela API; a tela é outro item.
- **Reprojeção da grade para o CRS de trabalho na agregação** (L3-07): a geometria é guardada em 4326 e quem for
  medir área ou distância tem de reprojetar para `srid_trabalho`. Não há guarda automática contra medir em 4326.

## Limitações honestas

- O teto de 1.000.000 de unidades por conjunto (`app/limites.py`) foi escolhido pela extrapolação de armazenamento,
  não por medição direta nessa escala.
- A grade é determinística (origem no 0,0 do CRS) e as faixas se juntam por `ON CONFLICT DO NOTHING`; a reexecução
  apaga as unidades do conjunto antes de recomeçar, então repetir o job dá o mesmo conjunto. Isso foi verificado só
  indiretamente (contagem estável entre rodadas do teste), não com um teste dedicado de reexecução.
- `desvio_contagem_pct` de ±2 % vale para a escala do portão (250 m sobre 2.000 km²). Em áreas pequenas com célula
  grande a faixa de borda domina, e o teste do hexágono usa a tolerância honesta para aquele caso: entre o esperado
  e o esperado mais perímetro dividido pelo lado.

## Riscos de merge

Os mesmos do handoff `L3-01-a-modelo-dado.md` (mesmos commits): `app/main.py`, `app/jobs/tipos.py`,
`app/limites.py`, `docs/LIMITES.md`, `docs/openapi.json`, `CHANGELOG.md`, `tests/api/cruzado_casos.py`, e a
numeração da migração (**044_amc.sql**; principal em 041 na hora deste handoff).


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
