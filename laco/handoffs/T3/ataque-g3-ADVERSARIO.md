# Ataque adversarial — grupo G3 (fila de trabalhos e ingestão de dado vetorial)

Adversário independente, turno 3, 06/09/2026. Nada aqui foi consertado: só medido e derrubado.

**Base de teste própria**, sem disputar a fila de ninguém: `bash laco/trilha_ambiente.sh adv3` →
schema `plat_tadv3` / `plat_trabalho_tadv3`, worker próprio em `:18160`, worktree
`/home/dev/plataforma/wt/adv3` no ramo `wt/adv3`. **Nenhum teste tocou o schema `plat` de produção.**

**Commit do código atacado: `2520afd`** (e não a ponta de `master`). Motivo, medido antes de começar:
entre `3a69591` e `2132603` a ponta de `master` **não importava** — `app/main.py` passou a importar
`app.auth.rotas_convites`/`rotas_redefinicao`, que não estavam no commit:

```
$ for c in 3a69591 2520afd 90ab545 a755cb7; do printf "%s: main importa=%s arquivo no commit=%s\n" $c \
   "$(git show $c:app/main.py | grep -c rotas_convites)" \
   "$(git cat-file -e $c:app/auth/rotas_convites.py 2>/dev/null && echo sim || echo NAO)"; done
3a69591: main importa=2 arquivo no commit=NAO
2520afd: main importa=0 arquivo no commit=NAO
90ab545: main importa=2 arquivo no commit=NAO
a755cb7: main importa=2 arquivo no commit=NAO
```
Outra trilha fechou o buraco em `2132603` enquanto eu media. Fica o registro: durante ~4 commits um
`git clone` de `master` não subia. É o mesmo `git add` explícito que o BRIEF pede — e o preço dele.

---

## (a) Veredito item a item

| item | veredito | o que derrubou |
|---|---|---|
| L0-04-ingest-vetor | **REFUTADO** | 4 dos formatos do portão existem; a cota do inquilino só sobe (medido 188.416 → 376.832 → 376.832) |
| L0-04-b-inspecao | **REFUTADO** | dos 12 arquivos do portão, 7 são de formato que a instalação não tem; CSV de 300 colunas/0 linhas termina em silêncio; zip malformado explode em vez de 422; a medida `tempo_inspecao_s` não existe |
| L0-04-c-tabela-camada | **REFUTADO** | a medida `tempo_import_100k_s` não existe; `d_<slug>` é partilhado entre instalações e a segunda não importa nada (`permission denied for schema d_demo`, medido ao vivo); inquilino com hífen no slug nunca importa |
| L0-04-d-formatos-base | **REFUTADO** | o portão pede 9 formatos e a instalação anuncia 4; a rota que anuncia os formatos responde 404 |
| L0-05-a-fila-postgres | **REFUTADO** | 3 SIGKILL no worker e o job termina **`concluido`** (a refutação exige `falhou` na 4ª e nunca `concluido`); traceback não é saneado; a chave do lock atravessa inquilino; a fila não tem justiça entre inquilinos |
| L0-05-b-progresso-cancelamento | **REFUTADO** | o limite de conexões SSE é por processo e a unidade sobe 2 (limite real 20, não 10); `plat.job_log` aceita linha depois do estado final |
| L0-05-c-tela-tarefas | **REFUTADO** | reproduzido ao vivo no módulo real: depois do `fim` de 30 min o navegador apaga a assinatura e nunca reassina |
| L0-05-d-periodicos | **REFUTADO** | as chaves dos periódicos são constantes e qualquer inquilino comum pode ocupá-las, travando `jobs.sessoes_expurgar` da plataforma |
| L0-05-e-worker-em-container | **REFUTADO** | item `entregue` com o portão ainda no texto "portão a fixar pelo arquiteto"; e o GDAL do contêiner (3.6.2) **não tem `ogrinfo -json`**, que é como o L0-04-b inspeciona todo arquivo |

9 de 9 refutados. Cada achado virou teste `xfail(strict=True)` em
`tests/api/adversario_g3/` (25 testes; passam a falhar no dia em que alguém consertar).

```
$ set -a; source laco/var/trilha/adv3.env; set +a
$ venv/bin/pytest tests/api/adversario_g3 -p no:randomly -m "not lento" -q
xxxxxxxxxxxxxxxxxxxx.xxxxx                                               [100%]
```
(25 `x` = achado reproduzido; o único `.` é a cláusula do CRS legado, que **aguentou**.)

---

## (b) Suposições transversais

Escritas antes de olhar item por item, e atacadas primeiro.

### T1 — "quem valida a entrada é a inspeção" · **CAIU**
Não existe teto de complexidade de feição em lugar nenhum do repositório: `grep -rE
"FEICAO_BYTES_MAX|ST_NPoints|npoints" app/ db/` não devolve nada. O único teto é `INGESTAO_CAMPOS_MAX
= 500`, conferido **depois** do `ogrinfo`. O arquivo inteiro é lido para a RAM (`objetos.ler`), com
`ARQUIVO_BYTES_MAX = 512 MiB` de um lado e `memoria_mb=768` do job do outro. Medido: 1 milhão de
vértices numa feição (24 MB) leva **14,8 s** de inspeção e conclui. Derruba L0-04-b e o item pai.

### T2 — "o inquilino está isolado" · **CAIU EM DOIS LUGARES, AGUENTOU NO TERCEIRO**
Aguentou o que a suíte já testava: RLS por linha, `FORCE ROW LEVEL SECURITY` na tabela de camada,
`plat_app` sem contexto não vê nada, job de A invisível para B. **Caiu no recurso partilhado**: a fila
é um só recurso sem cota de vazão entre inquilinos, e a chave do lock é global. **Caiu de novo no
disco**: o schema de dados do inquilino é `'d_' || slug`, sem prefixo de instalação, então produção,
homologação e as 15 trilhas deste laço escrevem no mesmo `d_demo`. Derruba L0-05-a, L0-05-d e L0-04-c.

### T3 — "o que sobra quando o processo morre" · **CAIU**
O ceifador só existe dentro do worker (`app/jobs/worker.py`, `job_ceifar` chamado no laço e na
partida; nenhum periódico o chama). Medido: 68 s depois do SIGKILL, sem worker vivo, o job continua
`rodando` — a tela mostra execução que não existe. E o gatilho de estado final não cobre
`plat.job_log`: um filho perdido segue escrevendo no log de um job já `falhou`. Derruba L0-05-a e
L0-05-b.

### T4 — "unidade e projeção" · **AGUENTOU**
A única cláusula do grupo que resistiu ao ataque. GeoJSON com o membro `crs` legado de EPSG:31982
é avisado, `.prj` ausente vira pergunta com sugestão 4674, CRS confirmado nunca é reprojetado.
O teste está em `test_geojson_com_crs_legado_31982_e_perguntado_ou_avisado` e **passa**.

### T5 — "fim de canal é fim de trabalho" · **CAIU**
`app/jobs/eventos.py` usa o MESMO evento `fim` para duas coisas diferentes: "o job acabou" e "esta
conexão bateu nos 30 min, reconecte". O cliente não distingue: `web/js/jobs/eventos.js::tratar`
chama `encerrar(a)` em qualquer `fim`. Derruba L0-05-b (contrato) e L0-05-c (tela).

### T6 — "o portão é o contrato" · **CAIU**
Dois portões pedem medida nomeada (`tempo_inspecao_s`, `tempo_import_100k_s`) e não existe nenhum
arquivo `tests/medidas/L0-04-*.json`. Um terceiro portão (L0-05-e) nunca foi escrito e o item está
marcado `entregue` mesmo assim.

---

## (c) Bloco por item — comando e saída real

### L0-05-a-fila-postgres

**1. Refutação literal: "mata o worker com SIGKILL 3 vezes seguidas no mesmo job e verifica que o job
termina 'falhou' na 4ª e nunca 'concluido'".** Roteiro:
`tests/api/adversario_g3/g3_sigkill_worker.py` (roda como único worker da base).

```
$ venv/bin/python tests/api/adversario_g3/g3_sigkill_worker.py
"trilha": [
 {"passo": "job criado",                                   "estado": "pendente", "reinicios": 0},
 {"passo": "ciclo 1: SIGKILL no worker",                   "estado": "rodando",  "reinicios": 0},
 {"passo": "ciclo 1: 68 s depois, SEM worker vivo",        "estado": "rodando",  "reinicios": 0},
 {"passo": "ciclo 2: SIGKILL no worker",                   "estado": "rodando",  "reinicios": 1},
 {"passo": "ciclo 2: 68 s depois, SEM worker vivo",        "estado": "rodando",  "reinicios": 1},
 {"passo": "ciclo 3: SIGKILL no worker",                   "estado": "rodando",  "reinicios": 2},
 {"passo": "ciclo 3: 68 s depois, SEM worker vivo",        "estado": "rodando",  "reinicios": 2},
 {"passo": "4a passagem, worker vivo",                     "estado": "concluido","reinicios": 3}],
"veredito": "CAI: a refutação exige 'falhou' na 4ª e NUNCA 'concluido'; deu 'concluido'"
```
Duas coisas de uma vez. (i) Morte do worker entra como `reinicios` e não como `tentativa`
(`job_devolver(..., p_conta_tentativa := false)`, migração 008), e o teto é
`PLAT_JOB_MAX_REINICIOS = 5`; com 3 mortes o job volta à fila e na 4ª conclui. (ii) Enquanto **nenhum**
worker está vivo, ninguém ceifa: `plat.job_ceifar` só é chamada de dentro do laço do worker
(`app/jobs/worker.py:146,222`) e o `GRANT EXECUTE` é só para `plat_worker`. 68 s depois do SIGKILL —
oito segundos além do `LIMITE_SEM_SINAL_S = 60` — o job ainda estava `rodando`.

**2. A chave do lock atravessa inquilino.** `plat.job_pegar` (migração 006) filtra
`NOT EXISTS (SELECT 1 FROM plat.job r WHERE r.chave = j.chave AND r.estado = 'rodando')` — sem
`tenant_id`. E `prova.progresso` aceita a chave como parâmetro livre do usuário
(`app/jobs/tipos_prova.py`, `max_length=200`, `timeout_s=7200`), registrada em produção
(`app/jobs/tipos.py` importa `tipos_prova` sem condição de ambiente).

```
$ sudo -u postgres psql -d iagro_sat -f tests/api/adversario_g3/g3_chave.sql
  tipo   | tenant_id | chave |  estado
---------+-----------+-------+----------
 zadv3.A |         1 | X     | pendente
 zadv3.B |         2 | X     | pendente
 primeiro_pego | tenant_id
 zadv3.A       |         1
     segundo_pego
 NENHUM JOB ELEGIVEL
  tipo   | tenant_id | chave |  estado
 zadv3.A |         1 | X     | rodando
 zadv3.B |         2 | X     | pendente
```
O inquilino 2 fica parado por causa de uma chave escolhida pelo inquilino 1.

**3. A fila não tem justiça entre inquilinos.** `ORDER BY j.prioridade, j.agendado_para, j.criado_em`
é global, e `app/jobs/servico.py::criar` aceita `prioridade` de 1 a 9 de qualquer usuário. Com uma
vaga de worker (`PLAT_WORKER_PROCESSOS = 1` no `install.sh` e no `.env.exemplo` — a hipótese do item
diz "2 processos por padrão"):

```
$ sudo -u postgres psql -d iagro_sat -f tests/api/adversario_g3/g3_fila_justica.sql
 posicao |      tipo       | tenant_id | prioridade
       1 | zadvB.fura-fila |         2 |          1
       2 | zadvB.fura-fila |         2 |          1
       3 | zadvB.fura-fila |         2 |          1
      19 | zadvB.fura-fila |         2 |          1
      20 | zadvB.fura-fila |         2 |          1
      21 | zadvA.espera    |         1 |          5
            medida             | posicao
 posicao do job do inquilino A |      21
```
O inquilino A criou o job **primeiro** e foi servido por último. `cota_jobs_simultaneos` (padrão 2)
não corrige isso quando a máquina tem menos vagas que a cota.

**4. "termina 'falhou' com o traceback saneado" (portão literal).** Não há saneamento nenhum:
`app/jobs/filho.py` grava `traceback.format_exception(...)` inteiro em `plat.job_log`, e a API
devolve isso a quem tem `jobs.ver`.

```
$ venv/bin/pytest tests/api/adversario_g3/test_g3_fila.py -k traceback --runxfail --tb=line
E  AssertionError: o log do job devolvido pela API expõe o caminho absoluto do servidor
   ['/home/dev/plataforma']
```

**O que aguentou:** `jobs_vazios_por_min = 2135,9` (portão pede ≥ 600, `tests/medidas/L0-05-jobs.json`);
RLS entre inquilinos; execução exatamente uma vez com 2 processos; `job nasce pendente` e
`transição para concluido só pelo worker` barraram até as minhas próprias inserções de teste.

### L0-05-b-progresso-cancelamento

**1. Refutação literal: "abre 200 conexões SSE no mesmo job (limite por usuário)".** O contador é um
`collections.Counter` na memória do processo (`app/jobs/eventos.py`, `_por_usuario`), e
`deploy/plat-api.service` sobe `uvicorn ... --workers 2`.

```
E  AssertionError: POR_USUARIO_MAX=10 é por processo e a unidade sobe 2 processos:
   o limite real por usuário é 20
```

**2. "estados finais imutáveis" (hipótese do item).** O gatilho `job_estado_final_imutavel` congela
`estado/progresso/erro/...`, mas não `linhas_log`, e `plat.job_log` não olha o estado do job:

```
E  AssertionError: o banco aceitou uma linha de log no job 4963aa08-... já em estado final
   (linhas_log era 6)
```

**O que aguentou:** o grampo de progresso em 0-100 (duas travas: `least/greatest` na 006 e o `CHECK`
da 004), cancelar concluído = 409, cancelar de outro inquilino = 404.

### L0-05-c-tela-tarefas

**Refutação literal: "deixa a aba aberta 2 h (reconexão do SSE)".** O bloqueio do item já registrava
isto por LEITURA de código; aqui está **reproduzido**, carregando o módulo real
`web/js/jobs/eventos.js` com um `EventSource` de mentira e mandando o `fim` que o servidor manda aos
30 min (estado real, não final, motivo "reconecte"):

```
$ node tests/api/adversario_g3/g3_sse_reconexao.mjs
{ "eventos_entregues": ["estado","fim"],
  "ainda_assinado_apos_o_fim_de_conexao": false,
  "conexao_do_navegador_fechada": true,
  "modo_apos_o_fim": null,
  "total_de_assinaturas": 0 }
CAI: o job segue RODANDO no servidor e a página parou de receber qualquer evento
```
O defeito é da camada de assinatura (`tratar()` chama `encerrar()` em qualquer `fim`), não só de
`detalhe.js`. A LISTA se recupera por acaso, porque `atualizarResumo` roda em `setInterval` e
`carregar()` reassina; o painel de DETALHE não tem esse caminho e fica mudo.

**A outra cláusula da refutação AGUENTOU — e com folga.** "abre a tela com 100 mil jobs (paginação
obrigatória)": inseri 100 mil jobs no inquilino e medi a API que a tela chama.
```
$ cat tests/medidas/adv-g3-tela.json
{"jobs_na_base": 100012, "primeira_pagina_s": 0.138, "resumo_s": 0.032,
 "itens_na_pagina": 50, "total_declarado": 100012, "resumo_status": 200}
```
0,138 s com 100.012 jobs. A pendência que o bloqueio do item registrava está medida e fechada.

### L0-05-d-periodicos

As chaves dos periódicos são constantes de código (`chave=lambda p: "sessoes_expurgar"`,
`"manutencao_analyze"`, em `app/jobs/periodicos.py`). Como o lock não olha o inquilino (achado 2 do
L0-05-a), um usuário `editor` de qualquer inquilino enfileira `prova.progresso` com essa chave e o
periódico do inquilino técnico não roda enquanto o dele rodar:

```
E  AssertionError: o periódico do inquilino técnico ficou impedido pela chave escolhida por um
   inquilino comum: ['prova.progresso', 'NENHUM']
```
`jobs.sessoes_expurgar` é o expurgo de sessões vencidas: mantê-lo parado tem efeito de segurança,
não só de higiene.

**O que aguentou:** cron inválida = 422, dedup do `rodar agora` por `job_pegar`, `ON CONFLICT
(agenda_id, programado_para)` contra dois relógios no mesmo tick, `PLAT_RELOGIO_TESTE` barrado em
produção (`agora_do_worker` confere `settings.producao`).

### L0-05-e-worker-em-container

**1. O portão nunca foi escrito, e o item está `entregue`.**
```
E  AssertionError: item em estado 'entregue' com portão não escrito:
   'portão a fixar pelo arquiteto no turno em que o item que a pediu entrar
    (registrar aqui antes de construir)'
```

**2. O executor entregue não roda a tarefa que o outro item do grupo precisa.** A inspeção do L0-04-b
chama `ogrinfo -ro -json -so` (`app/ingestao/inspecionar.py`), e a hipótese do item cita "GDAL 3.8.4
instalado". A imagem do contêiner é `python:3.12-slim-bookworm` + `apt-get install gdal-bin`, que no
Debian bookworm é GDAL 3.6.2 — onde `-json` **não existe**:

```
$ docker run --rm python:3.12-slim-bookworm bash -lc \
   'apt-get update -qq && apt-get install -y -qq --no-install-recommends gdal-bin; \
    ogrinfo --version; ogrinfo -ro -json -so /tmp/a.geojson'
VERSAO: GDAL 3.6.2, released 2023/01/02
FAILURE: Unknown option name '-json'
```
Todo job `ingestao.inspecionar` que cair neste executor falha. É exatamente o que a refutação do item
manda conferir ("o item que pediu esta dependência funciona com ela").

**3. A prova do handoff não é reproduzível hoje:** `docker images | grep plat-worker` não devolve nada
— a imagem `plat-worker:test` já não existe na máquina.

### L0-04-d-formatos-base

**1. O portão pede 9 formatos; a instalação tem 4.**
```
E  AssertionError: formato kml não existe nesta instalação:
   {"erro":"formato_nao_suportado","mensagem":"formato 'kml' não suportado nesta instalação;
    aceitos: ['csv','geojson','gpkg','shapefile.zip']"}
```
O mesmo para `kmz`, `gpx`, `xlsx`, `gml`, `flatgeobuf`, `dxf`, `gdb`. Com isso caem, por construção,
"KMZ com 3 pastas gera 3 camadas", "GPX (trilhas, rotas, pontos)", "XLSX/XLS (planilha por camada)" e
o "e2e do fluxo completo com captura por formato".

**2. A rota que anuncia os formatos não é alcançável.** `GET /api/importacoes/formatos` está declarada
**depois** de `GET /api/importacoes/{id}` em `app/ingestao/rotas.py`, e o parâmetro de caminho é livre:
```
E  AssertionError: a rota que anuncia os formatos responde 404 (engolida por /api/importacoes/{id}):
   {"erro":"importacao_inexistente","mensagem":"importação inexistente"}
```

**A cláusula que aguentou:** "GeoJSON com `crs` legado em 31982 (deve avisar e reprojetar ou
perguntar)" — avisa. Teste passa.

### L0-04-b-inspecao

**1. Dos 12 arquivos do portão, 7 não têm formato na instalação** (XLSX, DXF, GML, GDB zipada,
FlatGeobuf, KML/KMZ) — mesma medida do L0-04-d.

**2. "GPKG com 3 camadas" perde 2 camadas em silêncio.** `inspecionar.py` faz `camada = camadas[0]`.
Montei um GeoPackage com `camada_um`/`camada_dois`/`camada_tres` a partir do dado aberto que a própria
suíte gera:
```
E  AssertionError: a proposta só cita a 1ª camada; estado=proposta;
   proposta={"crs": {...}, "avisos": [], "campos": [...]}
```
`avisos: []` — o usuário não é informado de que duas camadas do arquivo dele foram descartadas.

**3. Refutação literal "CSV com 300 colunas e 0 linhas ... silêncio ou 500 = refutado": silêncio.**
```
E  AssertionError: inspeção terminou em 'proposta' sem pergunta nem aviso para um CSV de 300 colunas
   e 0 linhas: perguntas=[] avisos=[]
```

**4. Entrada malformada explode em vez de recusar.** `app/ingestao/rotas.py` captura
`ConteudoNaoCorresponde`, mas `conferir_zip` levanta `ZipSuspeito` — as duas herdam de `ValueError`,
uma não é mãe da outra, e não há tratador genérico em `app/erros.py`:
```
E  app.ingestao.formatos.ZipSuspeito: zip inválido: File is not a zip file
E  app.ingestao.formatos.ZipSuspeito: zip aninhado: 'dentro.zip'
```
Em produção isso é 500 com rastro, não 422 com mensagem.

**5. A medida do portão não existe.** "medida `tempo_inspecao_s` por arquivo (100 mil feições ≤ 5 s)":
```
E  AssertionError: medidas do portão ausentes; achadas: {};
   arquivos: ['L0-01-repo.json','L0-02-e.json','L0-02-tenant-auth.json','L0-03-catalogo.json',
              'L0-05-jobs.json','L0-08-d-ldap.json','L0-09-metadado-catalogo.json',
              'L2-10-c-expressao.json','L5-05-documento-versoes.json','L7-31-homologacao.json']
```
Não há arquivo de medida de L0-04 nenhum, e o maior fixture da suíte tem 80 feições — três ordens de
grandeza abaixo das 100 mil que o portão manda medir.

**6. O que aguentou, medido:** 1 milhão de vértices numa feição só (24 MB) **passa**: inspeção conclui
em 14,8 s (`tests/medidas/adv-g3-vertices.json`). Não há teto, mas também não há queda nessa escala.

### L0-04-c-tabela-camada

**1. Duas instalações no mesmo banco: a segunda não importa nada.** `plat.camada_schema_garantir` cria
`'d_' || slug`, sem prefixo de instalação, com `AUTHORIZATION <papel da instalação>`. Como o schema já
existia (criado pela produção), o `CREATE SCHEMA IF NOT EXISTS` é no-op e o papel da segunda
instalação não pode criar tabela lá:
```
$ sudo -u postgres psql -d iagro_sat -c "SELECT tipo, estado, left(erro,60) FROM plat_tadv3.job
   WHERE tipo LIKE 'ingestao%' ORDER BY criado_em DESC LIMIT 2"
 ingestao.carregar    | falhou    | InsufficientPrivilege: permission denied for schema d_demo
 ingestao.inspecionar | concluido |
```
O banco tem hoje 84 schemas `d_*`, com donos `plat_app`, `plat_tadv1_app`, `plat_tadv2_app`,
`plat_tamc_app`, `plat_tt02g_app` — a colisão já aconteceu de verdade. (Para seguir medindo o resto,
dei `GRANT USAGE, CREATE ON SCHEMA d_demo, d_demo2 TO plat_tadv3_app`; é aditivo e está registrado
aqui.) A mensagem que chega ao usuário vaza o nome interno do schema.

**2. Inquilino com hífen no slug nunca importa.** A migração 002 aceita
`slug ~ '^[a-z0-9][a-z0-9-]{1,38}$'`; a 029 recusa `p_slug !~ '^[a-z][a-z0-9_]{0,60}$'`:
```
E  AssertionError: o slug 'minha-org' é aceito na criação do inquilino e recusado pela ingestão
   (criação=true, ingestão=false)
```
A suíte inteira usa `demo`/`demo2`/`plataforma`, que passam nas duas regras — por isso ninguém viu.

**3. A cota do inquilino só sobe.** `uso_bytes` é somado em `app/ingestao/carregar.py` e não é
devolvido por caminho nenhum: apagar a camada e rodar o expurgo físico não devolve um byte.
```
E  AssertionError: uso_bytes do inquilino: 188416 antes, 376832 depois da carga,
   376832 depois de apagar e expurgar a camada — a cota nunca desce
```
Isso transforma "cota por inquilino aplicada" (portão do item pai) numa conta que só fecha para baixo:
o inquilino perde espaço a cada importação, mesmo desfazendo tudo.

**4. A medida `tempo_import_100k_s` não existe** (mesma saída do achado 5 do L0-04-b).

### L0-04-ingest-vetor (pai)

Herda 1 e 3 do L0-04-c e 1, 2 e 4 do L0-04-b. Do portão do próprio item: "cada formato listado
importa por upload no navegador" — DXF/DWG e KML não importam por nada; "tamanho máximo e cota por
inquilino aplicados" — a cota é aplicada na entrada e nunca devolvida, e não há teto por feição.

---

## (d) Fronteira honesta — o que eu NÃO provei

1. **`.dbf` de 4 GB e zip-bomba de verdade.** Não gerei: disco a 91 % (45 GB livres). O que dá para
   afirmar é de leitura, não de medida: `ZIP_DESCOMPRIMIDO_MAX = 8 GiB` deixa passar um membro maior
   que a memória do job (`memoria_mb=768`) e `inspecionar.py` usa `zf.read(membro)`, que descomprime o
   membro inteiro antes de fatiar os 64 KiB da amostra.
2. **GeoJSON com 10 milhões de vértices.** Medi 1 milhão (24 MB, 14,8 s). A extrapolação linear para
   10 milhões (≈ 240 MB) é **minha conta, não medida**: ~150 s, dentro do `timeout_s=300` da tarefa,
   mas com o arquivo inteiro em RAM contra `RLIMIT_DATA` de 768 MB. Quem quiser fechar isso roda o
   mesmo teste com `n = 10_000_000`.
3. **Nome de camada em caracteres de controle** (refutação do L0-04-b) e **injeção no dialeto OGRSQL**
   por aspas no nome da camada (`carregar.py` monta `SELECT ... FROM "{camada_origem}"` por f-string,
   com o nome lido do arquivo). O caminho do zip recusa byte de controle; o caminho do GPKG eu não
   consegui exercitar — o `ogr2ogr` local não me deixou criar camada com aspas no nome.
4. **Matar o worker no MEIO da carga** (refutação do L0-04-c: "não fica tabela sem item nem item sem
   tabela"). Não rodei. O que vi por leitura: `_limpar_orfao` roda só em `except Cancelado` e
   `except FalhaDefinitiva`, não há `except Exception`, e sob SIGKILL nenhum `finally` roda. O próprio
   handoff do item admite que o teste não foi escrito.
5. **200 conexões SSE reais por HTTP.** Provei o limite pela aritmética (contador por processo ×
   `--workers 2`), não abrindo 200 conexões contra a URL pública. O handoff anterior já tinha medido
   que `starlette.testclient` não sustenta conexões SSE concorrentes.
6. **Relógio do sistema 1 dia para trás** (refutação do L0-05-d). Não testei. O mecanismo é `croniter`
   puro sobre um instante passado, com `ON CONFLICT (agenda_id, programado_para)`; não achei estado de
   "última vez vista" no processo que pudesse duplicar. Sem medida, fica como não refutado e não
   provado.
7. **Navegador de verdade.** A refutação da tela pede aba aberta 2 h. Reproduzi o mecanismo no módulo
   real com Node 22 e um `EventSource` de mentira; não abri Chrome (o headless quebra nesta máquina,
   registro conhecido da casa).
8. **`repetir` job de outro usuário** (refutação do L0-05-c). Não rodei; o filtro `_filtro_dono` em
   `servico.obter` cobre por leitura, e a suíte da casa já tem
   `test_usuario_nao_admin_so_ve_os_proprios_jobs`.

## Reproduzir tudo

```
bash /home/dev/plataforma/laco/trilha_ambiente.sh adv3
cd /home/dev/plataforma/wt/adv3            # ramo wt/adv3, commit 2520afd
set -a; source /home/dev/plataforma/laco/var/trilha/adv3.env; set +a
export PLAT_DB=iagro_sat PLAT_GIT_SHA=$(git rev-parse HEAD)
venv/bin/python -m app.jobs.worker &        # worker próprio; PLAT_WORKER_URL=http://127.0.0.1:18160
venv/bin/pytest tests/api/adversario_g3 -p no:randomly -m "not lento" -q
venv/bin/pytest tests/api/adversario_g3 -p no:randomly -m lento -q     # 100 mil jobs e 1 mi de vértices
node tests/api/adversario_g3/g3_sse_reconexao.mjs
venv/bin/python tests/api/adversario_g3/g3_sigkill_worker.py           # exige ser o único worker
sudo -u postgres psql -d iagro_sat -f tests/api/adversario_g3/g3_chave.sql
sudo -u postgres psql -d iagro_sat -f tests/api/adversario_g3/g3_fila_justica.sql
```
Limpeza da base do adversário:
`sudo -u postgres psql -d iagro_sat -c 'DROP SCHEMA plat_tadv3 CASCADE; DROP SCHEMA plat_trabalho_tadv3 CASCADE'`
