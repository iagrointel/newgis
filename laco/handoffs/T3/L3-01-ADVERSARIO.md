# L3-01-ADVERSARIO — ataque independente aos itens L3-01-a-modelo-dado e L3-01-b-unidades

# VEREDITO: **REFUTADO** (parcialmente)

Cinco ataques encontraram defeito. Nenhum deles derruba as duas cláusulas centrais do portão — a imutabilidade do
modelo já executado e o isolamento entre inquilinos resistiram a tudo o que consegui montar —, mas um dos achados
quebra um contrato que o produto já entrega (o ambiente de homologação, item L7-31) e outro deixa entrar no modelo,
no hash e na execução um documento que a próxima etapa do motor não vai conseguir executar.

Escrevi 40 testes (28 passam, 12 são `xfail(strict=True)`). Cada `xfail` estrito é um defeito hoje e vira prova
automática no dia em que for consertado: o pytest acusa `XPASS` e reprova.

| # | ataque | resultado |
|---|---|---|
| 1 | imutabilidade do modelo executado | **DEFENDEU** (seis vias tentadas) |
| 2 | vazamento entre inquilinos nas 18 rotas | **DEFENDEU** (nenhum 200 com dado alheio) |
| 3 | validação do documento | **CEDEU** — 8 defeitos aceitos |
| 4 | a grade | **DEFENDEU** na contagem e na área; **CEDEU** na ficha de zonas UTM e no teto de unidades |
| 5 | a extrapolação declarada | **DEFENDEU** — e mais: gerei o milhão de células que não fora gerado |
| 6 | conferir os números | contagem diferente da que chegou ao gerente (ver §6) |

Ambiente: schema isolado `plat_tamcadv` criado por `laco/trilha_ambiente.sh amcadv`, com a migração 044 aplicada à
mão (o criador de trilha lê as migrações de `enterprise/`, onde a 044 ainda não existe). Sem `flock`, sem tocar em
`plat`.

---

## ACHADO PRINCIPAL — o conjunto do tipo `feicoes` está quebrado fora do schema `plat`

`app/amc/unidades.py::gravar_feicoes` é o **único ponto da aplicação inteira** que usa
`psycopg2.extras.execute_values`. Essa função monta o comando final e chama `cur.execute(b''.join(parts))` — com
**bytes**. `CursorSchemaAmbiente.execute` (`app/schema_ambiente.py`), que é o mecanismo que faz o produto falar com
`plat_homolog` sem reescrever as centenas de `plat.` espalhados pelo código, só reescreve quando a consulta é `str`:

```python
def execute(self, query, *args, **kwargs):
    if isinstance(query, str):
        query = self._reescrever(query)
```

Logo o literal `plat.amc_unidade` chega ao servidor mesmo com `PLAT_SCHEMA=plat_homolog`.

Comando e saída (reprodução direta, sem pytest):

```
$ set -a; source /home/dev/plataforma/laco/var/trilha/amcadv.env; set +a   # PLAT_SCHEMA=plat_tamcadv
$ venv/bin/python -c "... U.gravar_feicoes(cur, cid, tid, lista) ..."
Traceback (most recent call last):
  File "/home/dev/plataforma/wt/amc/app/amc/unidades.py", line 248, in gravar_feicoes
    psycopg2.extras.execute_values(
psycopg2.errors.InsufficientPrivilege: permission denied for schema plat
LINE 1: INSERT INTO plat.amc_unidade (conjunto_id, tenant_id, unidad...
```

Pela API o cliente recebe:

```
POST /api/amc/conjuntos {"tipo": "feicoes", ...}
403 {"erro":"sem_permissao","mensagem":"operação fora do inquilino da sessão"}
```

Duas coisas erradas de uma vez: a rota não funciona, e a mensagem diz ao operador que ele tentou sair do inquilino —
o que não aconteceu. `app/auth/comum.erro_do_banco` mapeia todo `InsufficientPrivilege` para essa frase.

O schema `plat_homolog` existe hoje na máquina (`SELECT nspname FROM pg_namespace WHERE nspname LIKE 'plat%'` →
`plat, plat_homolog, plat_tamc, plat_tamcadv, plat_tgadv, plat_trabalho, ...`), e `docs/HOMOLOGACAO.md` diz que
centralizar a troca no cursor "é o único jeito de a homologação nunca ficar um turno atrás da produção". Este item
abriu a primeira exceção a essa regra.

Prova em teste: `test_adv_conjunto_de_feicoes_funciona_em_qualquer_schema` (xfail estrito quando
`PLAT_SCHEMA != "plat"`; passa normalmente em produção) e `test_adv_execute_values_e_o_unico_desvio_da_reescrita_de_schema`
(mede o mecanismo, não depende do ambiente).

Conserto sugerido (não apliquei): trocar `execute_values` por `execute` com `unnest`/`jsonb_to_recordset`, ou passar
a consulta já reescrita (`CursorSchemaAmbiente._reescrever`) ao `execute_values`.

---

## 1. Imutabilidade do modelo já executado — DEFENDEU

`test_adv_modelo_executado_nao_se_altera_por_nenhuma_via`. Modelo + conjunto + execução em A, dois resultados
gravados, e então seis tentativas de mudar o que rodou:

| via | resultado |
|---|---|
| `PUT /api/amc/modelos/{id}` com definição nova | 200, `versao_nova: true`; a execução continua no `versao_hash` antigo |
| `PATCH /api/amc/modelos/{id}` | 405 (a rota não existe) |
| `POST /api/amc/modelos/{id}` | 405 |
| reordenar as chaves do JSON | 200, `versao_nova: **false**`, mesmo hash — o hash é do JSON canônico |
| `UPDATE plat.amc_modelo_versao` como `plat_app` | `amc_versao_imutavel` |
| `DELETE FROM plat.amc_modelo_versao` como `plat_app` | `amc_versao_imutavel` |
| `UPDATE plat.amc_execucao SET versao_hash` como `plat_app` | `amc_execucao_proveniencia_imutavel` |
| `UPDATE plat.amc_resultado SET favorabilidade` como `plat_app` | `amc_resultado_imutavel` |

Depois de tudo: `GET /api/amc/execucoes/{id}` devolve a definição QUE RODOU, `pesos` e `motor_versao` iguais, e os
resultados bit a bit os mesmos.

**Dois JSON semanticamente iguais com hashes diferentes: SIM, existe** —
`test_hash_igual_para_numeros_json_iguais_escritos_de_forma_diferente` (xfail estrito). `"peso": 3` e `"peso": 3.0`
são o mesmo número em JSON e dão `21bf5775…` × `ae04b30a…`. Consequência: reenviar o mesmo modelo com o peso escrito
como inteiro cria uma versão nova que não mudou nada. Não é falha de segurança; é ruído no histórico de versões.

**Dois JSON diferentes com o mesmo hash: SIM, na camada de parsing** —
`test_chave_repetida_no_json_cru_some_sem_aviso_e_nao_muda_o_hash` e
`test_adv_chave_repetida_no_corpo_cru_deveria_ser_recusada` (xfail estrito). O corpo
`{"nome": "MODELO FALSO", "nome": "modelo de teste interno", ...}` é aceito com 200 e hash idêntico ao do documento
sem a chave repetida: `json.loads` fica com a última ocorrência e ninguém avisa que a primeira foi descartada. Não é
colisão de sha256 — é o parser. Para um documento cuja versão é o hash, aceitar em silêncio um texto ambíguo é um
buraco de auditoria.

**Escrita direta com a role da aplicação: fronteira honesta.**
`test_adv_versao_forjada_no_banco_e_aceita_pelo_banco_mas_denunciada_pelo_recomputo` prova que **não há restrição no
banco** ligando `versao_hash` a `sha256(definicao)`: o gatilho só barra `UPDATE` e `DELETE`, então `plat_app`
consegue INSERIR uma versão com hash forjado. O que sustenta a proveniência é o recomputo por fora, não o banco.
Isso está certo como projeto, mas tem de ser dito assim — a frase "o banco garante o hash" seria falsa.

O hash gravado confere com recomputo independente: `test_adv_hash_gravado_confere_com_recomputo_independente` (a
regra reescrita dentro do próprio teste, sem importar `app.amc.esquema` nem o script) e o script no modo arquivo:

```
$ venv/bin/python scripts/amc_hash_independente.py --arquivo /tmp/m_adv.json
ae04b30afb2bd94785af9137dd3bcae1c06e3ad68a96a87e854a452ad61f7b8a
$ venv/bin/python -c "hashlib.sha256(json.dumps(d, sort_keys=True, separators=(',',':'), ensure_ascii=False)...)"
ae04b30afb2bd94785af9137dd3bcae1c06e3ad68a96a87e854a452ad61f7b8a
```

⚠ O modo `--tenant` do script está preso ao schema `plat` (`SET search_path = plat, public` e `FROM plat.amc_modelo_versao`,
linhas 55/58/61): não audita `plat_homolog` nem uma trilha. A auditoria que o item promete não alcança o ambiente de
homologação.

## 2. Vazamento entre inquilinos — DEFENDEU nas 18 rotas

`test_adv_as_18_rotas_de_amc_estao_todas_cobertas_por_este_ataque` lê `docs/openapi.json` e afirma que
`/api/amc` tem exatamente 18 rotas; `test_adv_nenhuma_das_18_rotas_entrega_dado_de_outro_inquilino` monta uma sonda
para **cada uma** (o teste falha se a lista de sondas não bater com a lista do OpenAPI) e busca no texto da resposta
o id do modelo, do conjunto, da execução e o `unidade_id` de B. Nenhum 200 com dado alheio.

Vias cobertas além do id no caminho: `POST /api/amc/execucoes` com `modelo_id` e `conjunto_id` de B no **corpo**
(404), `GET /api/amc/execucoes?modelo_id=<B>` no **parâmetro de consulta** (200 com lista vazia),
`GET /api/amc/conjuntos/{id de B}/unidades` (404), e as três listagens (nada de B).

Detalhe importante que separei: `POST /api/amc/modelos` e `/modelos/validar` **ecoam** o documento que A mandou. Se A
copia o documento de B, a resposta traz o `versao_hash` e o id de item de B — porque A os escreveu, não porque o
sistema os revelou. O que importa é que A não consiga **resolver** a camada, e não consegue: criar execução com essa
cópia dá `422 camada_inexistente`.

## 3. Validação do modelo — CEDEU em 8 casos

**Defendeu** (`test_defeito_recusado_com_422_e_a_clausula`, 7 casos, todos 422 com a cláusula, nenhum 500):
peso `NaN` e `Infinity` (`números finitos`), peso como texto `"0.5"` (`$.fatores[0].peso: type "number"`), peso
booleano, id que só difere na caixa (`"Declividade"`) ou por espaço (`"declividade "`) — os dois barrados pelo
`pattern ^[a-z][a-z0-9_]{0,31}$` —, nota fora de 0-100. Corpo de ~11 MB: **413 `corpo_grande`** (o teto de
`CORPO_MAX_PADRAO_BYTES` pega antes). Aninhamento de 5.000 níveis em `extrator.parametros`: aceito, sem 500.
Combinador `percentual` somando 99,9999999: aceito dentro da tolerância declarada de 0,01; somando 99,0: 422.

**Cedeu** (`test_transformacao_incoerente_deveria_ser_recusada`, 6 casos + a versão pela API, todos xfail estritos —
`ACEITO` significa 201/200 com hash gerado):

| documento | hoje |
|---|---|
| `linear` com `minimo: 30, maximo: 0` (faixa invertida) | ACEITO |
| `linear` com `minimo == maximo` (divisão por zero no L3-01-d) | ACEITO |
| `faixas` com 5 quebras e 2 notas | ACEITO |
| `faixas` com `quebras: [5, 1, 3]` (fora de ordem) | ACEITO |
| `degraus` com `bandas` fora de ordem crescente de `ate` | ACEITO |
| `gaussiana` sem nenhum parâmetro | ACEITO |

Causa: o `allOf` de `docs/esquemas/amc_modelo.v1.json` só descreve 4 dos 16 tipos de transformação, e
`_violacoes_semanticas` não olha para dentro da transformação. O portão do item nomeou quatro defeitos (peso
negativo, fator sem transformação, soma zero, fator duplicado) e os quatro estão cobertos; o que ficou de fora é a
coerência **interna** da transformação, que é exatamente o que o item L3-01-d vai ter de executar. Um modelo com
faixa invertida entra no banco, ganha hash, entra numa execução e só quebra (ou pior, dá nota errada em silêncio)
quando alguém rodar o motor.

## 4. A grade — recontada por fora

`test_adv_grade_250m_recontada_por_shapely_e_pyproj` (`-m lento`), com a área projetada por `pyproj.Transformer`,
medida por `shapely` e a área geodésica por `pyproj.Geod(ellps="GRS80")`:

```
[adversario] 250 m · 33677 células · 0.99 s · esperado 33,315 · desvio +1.086 % ·
             área plano 2,082,195,160 m² · geodésica 2,082,149,492 m² · soma das células 2,082,140,224 m²
```

Contagem dentro de ±2 %, tempo muito abaixo dos 60 s, e a soma das áreas geodésicas das células reproduz a área
geodésica da região com erro de 0,0004 % — o recorte não perde nem duplica área. A distorção medida entre o plano e
o geodésico cai dentro da faixa `distorcao_area_min_pct`/`max_pct` que a ficha declara.

Geometrias difíceis (`test_adv_grade_com_buraco_e_multipoligono_desconta_a_area`,
`test_adv_geometria_invalida_antimeridiano_e_area_quase_zero`):

| entrada | resultado |
|---|---|
| polígono com buraco | 451 células, faixa honesta [396, 518] (esperado + perímetro/lado); área geodésica bate em 0,3 % |
| MultiPolygon (2 partes) | dentro da faixa; área bate |
| auto-interseção (gravata) | 201, `ST_MakeValid` resolve, área > 0 |
| antimeridiano | **422 `crs_fora_da_cobertura`** — recusa em vez de escolher um CRS qualquer |
| área de ~1 m² | 201, área geodésica < 10 m² |
| LineString e Point | 422 `geometria_invalida` |

Nenhum 500.

⚠ Erro meu, registrado porque é armadilha para quem repetir: `pyproj.Geod.geometry_area_perimeter` sobre um polígono
com buraco **soma** o anel interno em vez de descontar (136,8 mi m² onde o correto é 99,1 mi m²). Quem conferir área
com buraco tem de somar anel a anel com `polygon_area_perimeter`. O produto estava certo; a minha primeira conferência
é que estava errada.

**Cedeu na ficha de zonas UTM** (`test_zonas_utm_cobertas_lista_todas_as_zonas_da_area`, xfail estrito):
`crs.ficha_crs` monta `zonas_utm_cobertas` como `{zona(xmin), zona(xmax), zona(centróide)}`. Uma área de −60° a −42°
cobre as zonas 21, 22, 23 e 24, e a ficha declara `[21, 22, 24]` com o aviso "a área cruza **3** zonas UTM (21, 22,
24)". O número e a lista estão errados; a distorção declarada continua correta (ela é medida ponto a ponto).

**Cedeu no teto de unidades** (`test_adv_teto_de_unidades_vale_para_a_contagem_real`, xfail estrito):
`preparar_grade` compara com `AMC_UNIDADES_MAX` a **estimativa** área/área-da-célula, nunca o resultado. As células
de borda entram recortadas e o conjunto termina acima do teto declarado. Medido de verdade, com o teto em 1.000.000:
**1.000.175 unidades geradas**.

A cláusula "CRS de trabalho e distorção na ficha" foi conferida
(`test_adv_area_que_cruza_duas_zonas_declara_crs_e_distorcao_na_ficha`): `GET /api/amc/conjuntos/{id}` traz os doze
campos, `cruza_zonas_utm: true`, aviso escrito, e a distorção declarada cobre a pior que eu meço na borda mais
afastada com `pyproj.Proj.get_factors`. Nada escondido.

## 5. A extrapolação declarada — DEFENDEU, e eu gerei o milhão

O campo está marcado: `tests/medidas/L3-01-b.json` tem
`grade_100m_1milhao_celulas_EXTRAPOLADO` com unidade `"s (extrapolação linear, NÃO medido)"` e o comando que a
produziu; `CHANGELOG.md` e o ADR 0016 dizem "1 milhão de células NÃO foi gerado". Varri CHANGELOG, `docs/` e
`tests/medidas/`: **em nenhum lugar o 34,3 aparece como medido**. Isso é conferido em
`test_adv_extrapolacao_do_milhao_esta_marcada_e_a_reta_se_sustenta`.

A reta se sustenta. Dois pontos meus, na mesma área:

```
[adversario] lado 500 m ·  8523 células · 0.26 s · 30.2 µs/célula
[adversario] lado 250 m · 33677 células · 0.99 s · 29.4 µs/célula
```

E, como `/mnt/pgdata` agora tem 43 GB livres (tinha 13 GB quando o construtor mediu), **gerei a escala que ele não
gerou** (`test_adv_o_milhao_de_celulas_que_nao_foi_gerado`, com guarda de disco que pula o teste abaixo de 8 GB):

```
[adversario] MEDIDO: 1,000,175 células em 30.97 s (31.0 µs/célula) · esperado 998,172 ·
             desvio +0.201 % · faixas 10
[adversario] projeção do construtor para 1,000,175 células: 34.3 s · medido 31.0 s · razão 0.90×
```

A extrapolação era honesta e **conservadora**: o real ficou 10 % abaixo do projetado, com desvio de contagem de
+0,201 %. A cláusula do portão que ficou em aberto ("100 m sobre ~10.000 km² ≈ 1 mi de células, tempo medido") está
cumprida agora — por mim, não pelo construtor. O conjunto foi apagado ao fim; `/mnt/pgdata` continua com 43 GB.

## 6. Os números, conferidos por mim

- **18 rotas em `/api/amc`**: confirmado, lidas do `docs/openapi.json` comitado.
- **Migração 044 idempotente**: confirmado — reapliquei o arquivo inteiro no schema da trilha, sem erro, e a
  contagem de linhas não mudou.
- **"207 testes passam"**: **não confirmei e não achei essa contagem em lugar nenhum.** O `CHANGELOG.md` do próprio
  turno diz "45 testes novos"; o pytest coleta **47** nos quatro arquivos do item (16 + 12 + 8 + 11). O número 207
  não aparece no CHANGELOG, nos dois handoffs nem no ADR. Ou é a contagem de outro recorte, ou está errado.
- **Suíte do construtor no meu schema isolado**: `32 passed, 6 failed, 7 errors, 2 deselected`. Doze desses quinze
  são do **código de teste**, que escreve `plat.` na mão em SQL cru (`plat.amc_resultado`, `plat.auth_login`) em vez
  de honrar `PLAT_SCHEMA`; três são o defeito real de `feicoes`. Não consegui rodar a suíte deles contra `plat` para
  confrontar: o superadmin de `plataforma` está com `423 bloqueado` em produção (outra trilha), e não mexo em estado
  de autenticação de produção para conseguir um número.
- **Os meus 40 testes**: `28 passed, 12 xfailed` em 62 s.

## Fronteira honesta (o que este ataque NÃO cobriu)

- **Não testei o worker real.** Como o construtor, chamo `app.amc.unidades.gerar_grade` direto. Que o job rode pela
  fila depois do merge continua por provar — a exigência dele no handoff segue de pé.
- **Não testei concorrência**: duas edições do mesmo modelo ao mesmo tempo, ou duas execuções do mesmo job de grade.
  A `UNIQUE (modelo_id, numero)` e o `n_versoes` lido-e-escrito na mesma transação sugerem que duas edições
  simultâneas dão 409 em vez de corromper, mas não medi.
- **Não testei o caminho de token de serviço** (escopo `catalogo:ler`), só sessão de navegador.
- **Não ataquei os privilégios**: um usuário sem `analise.amc` dentro do MESMO inquilino não entrou no meu teste.
- **Não medi memória** durante o milhão de células, só tempo e disco.
- **Nenhum teste meu prova nota de favorabilidade**, porque nada calcula favorabilidade ainda (L3-01-c/d/e). Os
  resultados que uso são inseridos à mão para conferir imutabilidade.
- Os dois nomes de arquivo pedidos colidiam: `pytest` sem `__init__.py` em `tests/` recusa dois módulos de teste com
  o mesmo basename. O de API ficou `tests/api/amc/test_amc_adversario_api.py`.

## Como reproduzir

```bash
cd /home/dev/plataforma/wt/amc
bash /home/dev/plataforma/laco/trilha_ambiente.sh amcadv
# a 044 não está em enterprise/db/migracoes: aplicar à mão no schema da trilha
TRILHA=amcadv /home/dev/plataforma/laco/trilha_reescrever.py db/migracoes/044_amc.sql > /tmp/044r_amcadv.sql
sudo -u postgres psql -d iagro_sat -X -q -v ON_ERROR_STOP=1 -1 -f /tmp/044r_amcadv.sql

set -a; source /home/dev/plataforma/laco/var/trilha/amcadv.env; set +a
venv/bin/pytest tests/unit/test_amc_adversario.py tests/api/amc/test_amc_adversario_api.py -p no:randomly -rx
# só o milhão de células (precisa de ~8 GB livres em /mnt/pgdata; leva ~31 s)
venv/bin/pytest tests/api/amc/test_amc_adversario_api.py::test_adv_o_milhao_de_celulas_que_nao_foi_gerado -s

# limpeza do schema da trilha ao terminar
sudo -u postgres psql -d iagro_sat -c 'DROP SCHEMA plat_tamcadv CASCADE; DROP SCHEMA plat_trabalho_tamcadv CASCADE'
```

## Fila de conserto, na ordem em que eu consertaria

1. `gravar_feicoes` sem `execute_values` (quebra a homologação, e a mensagem de erro mente).
2. Coerência da transformação no validador (faixa invertida, faixa degenerada, notas × quebras, ordem) — antes de
   L3-01-d, que é quem vai executar esses documentos.
3. `zonas_utm_cobertas` com todas as zonas do intervalo, não só as pontas.
4. Teto de unidades conferido sobre a contagem real, não sobre a estimativa.
5. `scripts/amc_hash_independente.py --tenant` honrando `PLAT_SCHEMA`.
6. Recusar chave repetida no JSON cru (`json.loads(..., object_pairs_hook=)`), e normalizar número antes do hash.
