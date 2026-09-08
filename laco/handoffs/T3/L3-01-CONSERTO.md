# L3-01-CONSERTO — resposta ao laudo `L3-01-ADVERSARIO.md` (itens L3-01-a-modelo-dado e L3-01-b-unidades)

Ramo `wt/amc`, worktree `/home/dev/plataforma/wt/amc`. Commits `7894cb0` (conserto) e `835991e` (renomeação que
destravou `make sem-marcador`), em cima do commit de ataque `0b0d47a`.

**Os 40 testes do adversário continuam lá, nenhum apagado, nenhuma asserção afrouxada.** Os 12 que eram
`xfail(strict=True)` viraram prova permanente: as marcas saíram e no lugar de cada uma ficou um comentário com o
texto original do defeito e o que o consertou. Onde a asserção dele dependia da FORMA do defeito (ele mesmo escreveu
`"a guarda mudou; refazer este teste"`), o teste foi refeito para medir o conserto, não removido.

Ambiente de prova: banco próprio da trilha, sem `flock`, sem tocar em `plat`.

```bash
cd /home/dev/plataforma/wt/amc
bash /home/dev/plataforma/laco/trilha_ambiente.sh amcfix
TRILHA=amcfix /home/dev/plataforma/laco/trilha_reescrever.py db/migracoes/045_amc.sql > /tmp/045r_amcfix.sql
sudo -u postgres psql -d iagro_sat -X -q -v ON_ERROR_STOP=1 -1 -f /tmp/045r_amcfix.sql
set -a; source /home/dev/plataforma/laco/var/trilha/amcfix.env; set +a
```

---

## Achado 1 (GRAVE) — a reescrita de schema escapava por `bytes`, e não só por ali

**O que ele mostrou.** `app/amc/unidades.gravar_feicoes` era o único ponto da aplicação a usar
`psycopg2.extras.execute_values`, que monta o comando final com `b"".join(...)` e chama `cur.execute(bytes)`.
`CursorSchemaAmbiente.execute` só reescrevia `str`, então o literal `plat.amc_unidade` ia ao servidor mesmo com
`PLAT_SCHEMA` apontando para outro schema: fora de `plat`, `POST /api/amc/conjuntos {"tipo":"feicoes"}` morria com
`permission denied for schema plat` e o cliente recebia `403 "operação fora do inquilino da sessão"`.

**O que o gerente acrescentou depois.** Um segundo adversário mediu o terceiro caso da mesma classe: `executemany`
também não passava pela reescrita, o que fazia `POST` e `PUT /api/papeis` baterem no `plat` de produção e
`tests/api/test_cruzado.py` — a prova de isolamento entre inquilinos — terminar com erro em base de trilha.

**Conserto, em três níveis.**

1. `app/amc/unidades.py`: `gravar_feicoes` não usa mais `execute_values`. É um `cur.execute` em TEXTO
   (`SQL_GRAVAR_FEICOES`) com `jsonb_to_recordset`, em lotes de `PAGINA_FEICOES = 500` — o mesmo tamanho de lote de
   antes, agora num comando que passa pela reescrita como qualquer outro.
2. `app/schema_ambiente.py`: a reescrita virou `MixinReescritaSchema`, separado do cursor do psycopg2 para poder ser
   testado sem banco. Cobre `execute`, `executemany`, `callproc`, `mogrify` e `copy_expert`, **em texto e em bytes**,
   devolvendo sempre o tipo que entrou. `PONTOS_COM_CONSULTA` declara o que é coberto e `PONTOS_FORA_DE_COBERTURA` o
   que não é e por quê. O no-op de produção continua: quando os dois schemas são o padrão, a consulta sai como o
   MESMO objeto que entrou, sem passar por regex nenhuma.
3. `app/auth/comum.py`: `_erro_de_privilegio` separa os dois donos do SQLSTATE 42501. Política de inquilino
   (`new row violates row-level security policy`) continua 403 `sem_permissao`; falta de GRANT
   (`permission denied for schema/table`) passa a 500 `privilegio_do_banco`, com a frase do servidor só no log. Erro
   de instalação do ambiente não é fronteira de inquilino.

### O que ficou de fora da cobertura, e por quê

| ponto de entrada | situação |
|---|---|
| `execute`, `executemany`, `callproc`, `mogrify`, `copy_expert` | cobertos, em `str` e em `bytes` |
| `copy_from`, `copy_to` | **fora**: recebem NOME de tabela, não SQL, e a casa não os usa — varrido em `app/`, `scripts/`, `db/` e `tests/` em 06/09/2026, zero ocorrências. Um teste reprova no dia em que alguém usar |
| `psycopg2.extras.execute_values` / `execute_batch` | não são métodos do cursor: são funções que montam o comando e chamam `cur.execute`. Desde que `execute` cubra `bytes`, elas passam pela reescrita. Nenhuma está em uso hoje |
| `psycopg2.sql.Composed` e afins | **fora**: passa cru, como sempre passou. A casa não importa `psycopg2.sql` (varrido; zero ocorrências). Reescrever um `Composable` exigiria desmontá-lo, e o ganho não existe enquanto ninguém o usa |

Escrito também no ADR 0009 (adendo de 06/09) e no ADR 0016 (Consequências).

### A trava para a classe não voltar

`tests/unit/test_schema_ambiente.py`, 22 casos, sem banco. Reprova se:

- aparecer um ponto de entrada do driver que não esteja nem coberto nem declarado fora com razão escrita (> 30
  caracteres);
- um método coberto for sobrescrito sem chamar `self._reescrever(`;
- um método público novo do mixin não constar da lista declarada;
- alguém passar a usar `copy_from`/`copy_to` em `app/`, `scripts/` ou `db/`;
- a MRO mudar (o mixin tem de vir antes do cursor do psycopg2, senão `super()` não chega ao driver);
- o no-op de produção deixar de devolver o mesmo objeto que entrou.

### Prova

```
$ venv/bin/pytest tests/unit/test_schema_ambiente.py -p no:randomly
......................                                                   [100%]
22 passed in 0.03s
```

Prova por ablação de que o `executemany` era mesmo o buraco (com a correção de conexões de teste `c311aa7` da
árvore principal aplicada, porque este ramo saiu antes dela):

```
# com a reescrita de executemany:
$ venv/bin/pytest tests/api/test_cruzado.py -k papeis -q
4 passed

# removendo só a linha `self._reescrever(query)` de MixinReescritaSchema.executemany:
$ venv/bin/pytest tests/api/test_cruzado.py -k papeis -q
ERROR tests/api/test_cruzado.py::test_rota_nao_cruza[DELETE-/api/papeis/{id}]
ERROR tests/api/test_cruzado.py::test_rota_nao_cruza[GET-/api/papeis]
ERROR tests/api/test_cruzado.py::test_rota_nao_cruza[POST-/api/papeis]
ERROR tests/api/test_cruzado.py::test_rota_nao_cruza[PUT-/api/papeis/{id}]
```

E a suíte cruzada inteira, no schema da trilha, com `c311aa7` aplicada:

```
$ venv/bin/pytest tests/api/test_cruzado.py -p no:randomly
1 failed, 156 passed        # era: 1 failed, 156 errors
```

O `1 failed` que sobra é `GET /saude` devolvendo **503** porque o schema da trilha tem uma migração pendente
(`045_amc.sql` foi aplicada à mão, sem entrar na tabela de migrações) e a fila do worker não roda ali. É artefato do
ambiente de trilha, não do produto.

A mensagem enganosa, provada nos dois lados
(`tests/api/amc/test_modelo.py::test_erro_de_privilegio_do_banco_nao_vira_403_de_inquilino`): INSERT com
`tenant_id` alheio → 42501 com `row-level security` → **403 `sem_permissao`**; `SELECT 1 FROM pg_catalog.pg_authid`
→ 42501 com `permission denied` → **500 `privilegio_do_banco`**.

---

## Achado 2 — validação aceitava transformação incoerente

Faixa invertida (`minimo` ≥ `maximo`), faixa degenerada, `len(notas)` diferente de `len(quebras) + 1`, quebras e
bandas fora de ordem crescente e função contínua sem parâmetro entravam no modelo, ganhavam hash e só quebrariam —
ou dariam nota errada em silêncio — quando o motor do item L3-01-d fosse executá-las.

Conserto: `app/amc/esquema._violacoes_transformacao`, chamada por fator dentro de `_violacoes_semanticas`. Cada caso
tem cláusula própria, no mesmo formato dos quatro defeitos que o item já pegava. A regra da função contínua é
deliberadamente fraca — **pelo menos um parâmetro numérico além de `tipo`, `abaixo`, `acima` e `metodo`** — porque a
lista de parâmetros de cada curva do Rescale by Function só fecha no L3-01-d; apertar mais agora seria inventar
contrato. Escrito no ADR 0016, decisão 1.b.

Prova: os 6 casos dele (`test_transformacao_incoerente_deveria_ser_recusada`, agora sem `xfail`) mais 9 casos de
recusa e **8 casos de aceitação** meus (`tests/unit/test_amc_esquema.py`) — a trava não pode endurecer demais, e o
que é legítimo (linear normal, faixa negativa, faixas certas, uma quebra só, degraus em ordem, categoria, gaussiana
com parâmetro, `grande` com mínimo e máximo) continua entrando.

---

## Achado 3 — `zonas_utm_cobertas` perdia as zonas do meio

Era `{zona(xmin), zona(xmax), zona(centróide)}`: de −60° a −42° declarava `[21, 22, 24]` e o aviso dizia "cruza 3
zonas UTM". Conserto em `app/amc/crs.py`: `range(zona(xmin), zona(xmax) + 1)` unido à zona do centróide.

Prova, com polígono largo (`tests/unit/test_amc_crs.py::test_zonas_utm_cobertas_nao_perde_as_zonas_do_meio` e o
teste dele):

```
$ venv/bin/python -c "from app.amc import crs; ..."
[21, 22, 23, 24]
a área cruza 4 zonas UTM (21, 22, 23, 24); todo o conjunto usa a zona 22S do centróide...
```

Um segundo polígono, de −66° a −36°, declara `[20, 21, 22, 23, 24, 25]`.

---

## Achado 4 — o teto valia para a estimativa, não para o resultado

`preparar_grade` comparava `AMC_UNIDADES_MAX` com a estimativa área/área-da-célula; a célula de borda entra
recortada e o conjunto terminava acima do teto (ele mediu **1.000.175** unidades com o teto em 1.000.000).

Conserto: `gerar_grade` confere o teto sobre a CONTAGEM REAL depois de gerar. Passou, apaga as unidades, marca o
conjunto `estado='falhou'` com o motivo e devolve a ficha com `recusado: true`; a tarefa `amc.gerar_unidades`
levanta `FalhaDefinitiva`, para o operador não ver "concluído" sobre um conjunto recusado. A guarda da estimativa
continua na entrada, para recusar barato o que já se sabe grande demais.

**Por que a limpeza fica em `gerar_grade` e a falha do job na tarefa**: o teste dele chama `gerar_grade` direto e
afirma `conjunto["n_unidades"] <= 420` DEPOIS de a chamada retornar. Se `gerar_grade` levantasse a exceção, o teste
terminaria em erro — continuaria `xfail` para sempre e a marca nunca poderia ser trocada. Quem grava o estado do
conjunto é quem é dono da linha; quem falha o job é o job.

Prova: o teste dele (agora sem `xfail`) mais
`tests/api/amc/test_unidades.py::test_teto_de_unidades_vale_para_a_contagem_real_e_o_job_falha`, que confere as
cinco coisas: estimativa dentro do teto, `FalhaDefinitiva`, `estado='falhou'`, `n_unidades = 0` com `erro` escrito,
e `GET /conjuntos/{id}/unidades` com `total: 0` (as unidades foram apagadas de verdade, não descontadas na ficha).

⚠ **Efeito colateral que precisa ser dito**: a área do teste dele do milhão de células (0,92° × 0,92°) produzia
exatamente 1.000.175 unidades, ou seja, **acima do teto**, e passou a ser recusada. Encolhi a ÁREA de entrada 0,5 %
em cada lado (0,915°), com comentário no teste. Nenhuma asserção dele mudou; a escala do portão (100 m, ~9.400 km²,
perto de 1 milhão de células) é a mesma.

---

## Achado 5 — JSON canônico: chave repetida e `3` × `3.0`

**Chave repetida.** `{"nome": "A", "nome": "B"}` era aceito em silêncio: `json.loads` fica com a última ocorrência.
Num documento cuja versão é o hash dele mesmo, isso é buraco de auditoria. Conserto: `corpo_json_sem_chave_repetida`
(dependência do FastAPI) relê o corpo cru com `object_pairs_hook` nas três rotas de modelo e devolve 422
`json_ambiguo` com a chave. Corpo malformado continua sendo assunto do parser do FastAPI.

**Normalização numérica.** `3` e `3.0` são o mesmo número em JSON e davam hashes diferentes; reenviar o mesmo modelo
com o peso escrito como inteiro criava versão nova que não mudara nada. A regra, escrita no ADR 0016 decisão 1.a:
**todo número de ponto flutuante com parte fracionária zero e magnitude menor que 2^53 vira inteiro; nada mais
muda.** `0,5` continua `0,5`, `1e30` continua `1e30`, booleano nunca é número, `-0.0` vira `0`. A implementação é
iterativa, não recursiva, porque `extrator.parametros` é objeto livre e a validação aceita milhares de níveis de
aninhamento (um dos testes dele, que passava, quebrou na primeira versão recursiva — está consertado e o teste
passa).

**Escolha que precisa ficar registrada**: a normalização é aplicada **também ao documento gravado**, não só ao texto
que entra no sha256. É isso que mantém verdadeiro o teste dele
`test_adv_hash_gravado_confere_com_recomputo_independente`, que recomputa o hash sobre a definição GRAVADA com a
regra simples. Custo: o hash de um documento com float integral muda em relação à regra anterior. Medido antes de
decidir — os 53 modelos que existem em `plat` são todos resíduo de teste:

```
$ sudo -u postgres psql -d iagro_sat -c "SELECT left(nome,30), count(*) FROM plat.amc_modelo GROUP BY 1"
 zt-amc modelo           |  44
 modelo de teste interno |   7
 zt-cruzado-amc-8f441a   |   1
 zt-cruzado-amc-e7aaf1   |   1
```

Nenhum modelo real existe ainda, então a mudança de regra não invalida histórico de ninguém.
`scripts/amc_hash_independente.py` reescreve a normalização de forma independente (não importa `app.amc.esquema`) e
passou a honrar `PLAT_SCHEMA` / `--schema` — o modo `--tenant` estava preso a `plat` e não auditava homologação:

```
$ venv/bin/python scripts/amc_hash_independente.py --tenant 1
versões conferidas: 132 · divergentes: 0 · cabeças órfãs: 0
```

---

## Achado 6 — o "207 testes" não existia

O adversário procurou e não achou. Conferido: ele tem razão, e o `CHANGELOG` também estava errado com "45 testes
novos". O número verificável, no estado dos commits `d794266` + `7f40612`, é **47 casos de teste**, contados assim:

```
$ venv/bin/pytest tests/unit/test_amc_esquema.py tests/unit/test_amc_crs.py \
                  tests/api/amc/test_modelo.py tests/api/amc/test_unidades.py --collect-only -q | tail -5
tests/api/amc/test_modelo.py: 16
tests/api/amc/test_unidades.py: 12
tests/unit/test_amc_crs.py: 8
tests/unit/test_amc_esquema.py: 11
```

11 + 8 + 16 + 12 = 47. São CASOS, não funções: `grep -c "^def test_"` nos mesmos quatro arquivos dá **38**, e os
`parametrize` expandem a diferença. "45" não é nem uma coisa nem outra; "207" não é nada. Corrigido em
`CHANGELOG.md` e nos dois handoffs (`L3-01-a-modelo-dado.md`, `L3-01-b-unidades.md`), com o comando junto.

Depois do conserto: os mesmos quatro arquivos somam **73** casos (31 + 9 + 20 + 13), mais **40** do adversário e
**22** da trava de reescrita de schema.

⛔ **`laco/PAINEL.md` linha 226 continua com "207 testes" e NÃO foi editada** — é arquivo do gerente. Precisa da
correção dele.

---

## Achado 7 — a escala que faltava foi gerada (por ele)

`tests/medidas/L3-01-b.json` não tem mais o campo `grade_100m_1milhao_celulas_EXTRAPOLADO`. No lugar entraram três
campos MEDIDOS, com a autoria dita em cada um:

| campo | valor | de onde vem |
|---|---|---|
| `grade_100m_1milhao_celulas_segundos` | **33,55 s** | re-medição depois do conserto do teto. **Quem primeiro gerou a escala foi o adversário do item**, em 06/09/2026, com 43 GB livres em `/mnt/pgdata`: **1.000.175 células em 30,97 s** — está escrito no campo `nota` |
| `grade_100m_1milhao_celulas_contagem` | **989.334 células** | idem; a contagem dele foi 1.000.175, e a área do teste encolheu 0,5 % por causa do achado 4 |
| `grade_100m_1milhao_desvio_contagem_pct` | **+0,202 %** | ele mediu +0,201 % |
| `grade_100m_extrapolacao_antiga_erro_pct` | **−9,6 %** | a projeção de 34,3 s era conservadora: errou ~10 % para mais |

A única linha ainda marcada `EXTRAPOLADO` é `amc_unidade_bytes_1milhao_EXTRAPOLADO` — essa ninguém mediu, e o teste
dele que exige a marcação continua verde por causa dela.

Saída literal da medição:

```
$ venv/bin/pytest tests/api/amc/test_amc_adversario_api.py::test_adv_o_milhao_de_celulas_que_nao_foi_gerado -s
[adversario] MEDIDO: 989,334 células em 33.55 s (33.9 µs/célula) · esperado 987,337 · desvio +0.202 % · faixas 10
[adversario] projeção do construtor para 989,334 células: 33.9 s · medido 33.6 s · razão 0.99×
```

O handoff `L3-01-b-unidades.md` foi corrigido na linha do portão: a cláusula está cumprida, e **não por esta
trilha**.

---

## Como reproduzir tudo

```bash
cd /home/dev/plataforma/wt/amc
bash /home/dev/plataforma/laco/trilha_ambiente.sh amcfix
TRILHA=amcfix /home/dev/plataforma/laco/trilha_reescrever.py db/migracoes/045_amc.sql > /tmp/045r_amcfix.sql
sudo -u postgres psql -d iagro_sat -X -q -v ON_ERROR_STOP=1 -1 -f /tmp/045r_amcfix.sql
set -a; source /home/dev/plataforma/laco/var/trilha/amcfix.env; set +a

venv/bin/pytest tests/unit/test_amc_adversario.py tests/api/amc/test_amc_adversario_api.py -p no:randomly
#  -> 40 passed  (0 xfailed: os 12 defeitos viraram prova)
venv/bin/pytest tests/unit/test_schema_ambiente.py -p no:randomly     # -> 22 passed
venv/bin/pytest tests/api/amc tests/unit -p no:randomly               # -> 637 passed
venv/bin/ruff check app tests docs/gerar_limites.py && make sem-marcador
```

Para as suítes fora de `tests/api/amc` é preciso a correção de conexões de teste `c311aa7`, que está na árvore
principal e não neste ramo:

```bash
cd /home/dev/plataforma/enterprise && git show c311aa7 -- tests/conftest.py > /tmp/c311_conftest.patch
cd /home/dev/plataforma/wt/amc && git apply /tmp/c311_conftest.patch
venv/bin/pytest tests/api/test_cruzado.py -p no:randomly     # -> 1 failed (GET /saude 503), 156 passed
git apply -R /tmp/c311_conftest.patch
```

Limpeza do banco da trilha ao fim:

```bash
sudo -u postgres psql -d iagro_sat -c 'DROP SCHEMA plat_tamcfix CASCADE; DROP SCHEMA plat_trabalho_tamcfix CASCADE'
rm -f /home/dev/plataforma/laco/var/trilha/amcfix.env
```

---

## O que ficou de fora, e por quê

- **A varredura repo-inteira de `plat.` no código de TESTE.** `tests/api/test_rls.py::ids_por_slug`, `contexto()` e
  mais de 200 ocorrências em 25 arquivos escrevem `plat.` na mão em SQL cru, o que faz a suíte inteira falhar em
  base de trilha. A correção estrutural é a `c311aa7` da árvore principal (conexão de teste com
  `CursorSchemaAmbiente`), que resolve quase tudo sem tocar em nenhum desses arquivos — medido acima: `test_cruzado`
  vai de 156 errors para 156 passed. O resto (helpers que abrem conexão própria) é trabalho de outra trilha e
  colidiria com a árvore principal.
- **O worker de verdade.** Como o construtor e como o adversário, os testes chamam `app.amc.unidades.gerar_grade`
  direto; o worker só conhece o tipo de job depois do merge. A exigência continua de pé.
- **Concorrência.** Duas edições do mesmo modelo ao mesmo tempo, ou dois jobs de grade do mesmo conjunto, continuam
  sem medição — a fronteira honesta que ele declarou não mudou.
- **Parâmetros de cada função contínua.** A validação exige "pelo menos um parâmetro numérico"; a lista fechada por
  curva é do item L3-01-d.
- **`laco/PAINEL.md`.** Arquivo do gerente; a linha 226 ("207 testes") precisa da correção dele.

## Riscos de merge

- **Migração renumerada de `044_amc.sql` para `045_amc.sql`** — a árvore principal publicou `044_uploads.sql`
  enquanto esta trilha estava parada. Conferir `ls /home/dev/plataforma/enterprise/db/migracoes | tail -3` antes do
  merge: se ela já passou de 044, renumerar de novo.
- `app/schema_ambiente.py` e `app/auth/comum.py` são de produto e a árvore principal também os toca. As mudanças são
  localizadas: no primeiro, a classe foi partida em mixin + cursor (a função `reescrever_schema` e as constantes não
  mudaram); no segundo, um bloco novo `_erro_de_privilegio` e uma linha trocada em `erro_do_banco`.
- `tests/api/amc/test_amc_adversario_api.py` e `tests/unit/test_amc_adversario.py` são do adversário e foram
  editados por mim (marcas, um teste refeito, a área do teste do milhão, três erros de lint que vieram no commit
  dele e reprovavam `make lint`).
- `CHANGELOG.md`, `docs/adr/0009-*.md` e `docs/adr/0016-*.md`: mudanças no fim de seção.

## Commits do ramo

- `0b0d47a` — ataque do adversário (não é meu; base deste trabalho)
- `7894cb0` — conserto dos cinco achados + trava de reescrita de schema + documentos
- `835991e` — renomeação `METODOS_*` → `PONTOS_*` (a palavra continha `TODO` e reprovava `make sem-marcador`)
