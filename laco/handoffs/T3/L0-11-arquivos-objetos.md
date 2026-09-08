# Handoff — item L0-11-arquivos-objetos (arquiteto + backend, passagem única)

**Objetivo.** O dono pediu recorte rápido, entrega no mesmo dia: adaptador de objetos Garage por
inquilino (bucket/chave/cota), nome por sha256, entrega sempre pela API, réplica na 2ª máquina
quando existir. `app/objetos.py` (backend do L0-03) já cobria a metade "chave por sha256 + URL
assinada" com um adaptador de disco local; faltava a outra metade (bucket/chave/cota **por
inquilino** no Garage), que é o que este item constrói. Detalhe completo, medido, em
`docs/adr/0006-arquivos-objetos.md` (13 seções); aqui só o que mudou e as pendências.

## O que fiz

1. **`app/garage.py`** (novo): `ClienteS3` (AWS SigV4 à mão, sem boto3 — disco a 98%/12 GiB livres
   torna instalar botocore caro por um ganho que ~80 linhas de `hmac` resolvem) com PUT/GET/HEAD/
   DELETE/COPY/LIST/multipart (Create/UploadPart/Complete/Abort); `ClienteAdmin` para a Admin API
   v2 (:3903): criar bucket/chave, permitir, definir cota, ler uso. Tudo MEDIDO contra o Garage real
   desta máquina (`plataforma-garage`, já em produção para `plataforma/pipeline`) antes de entrar
   em `app/objetos.py`.
2. **`app/objetos.py`** (reescrito): mesma assinatura pública de `ler/existe/apagar/url_assinada/
   assinatura_valida` (zero mudança nos 4 chamadores existentes); `guardar` ganhou `cur` (1º
   parâmetro) e `item_id` virou opcional por *keyword*. Chave: `<slug>/<classe>/[<referencia>/]
   <sha256>.<ext>` — o slug no próprio texto é o que permite `ler/apagar/url_assinada` resolverem o
   bucket sem contexto de sessão (a entrega por URL assinada é rota anônima). Novo: `garantir_bucket`
   (idempotente, cria bucket+2 chaves+cota na 1ª vez, resincroniza cota depois), `uso(slug)`,
   `varrer_orfaos(cur, slug)`, contrato multipart do ADR 0005 (`parte_iniciar/enviar/concluir/
   abortar`, com sha256 real lido de volta em stream, não o ETag multipart).
3. **`app/rotas_arquivos.py`** (novo): `POST/GET/DELETE /api/arquivos[/{sha256}]`, `GET /api/arquivos`
   (uso×cota), `GET /api/arquivos/_varredura`. Achado no meio do turno: `checar_escrita_sob_cookie`
   (CSRF, ADR 0002 5.3) exige `application/json` em todo POST/PUT/PATCH/DELETE sob cookie de sessão;
   um arquivo cru nunca é JSON, então **`POST /api/arquivos` só aceita token de serviço**
   (`Authorization: Bearer`), nunca cookie — documentado no docstring da rota e no ADR seção 6.
4. **`db/migracoes/022_arquivos.sql`** (`arquivo_bucket`, `arquivo`, `arquivo_upload`, 4 funções
   `SECURITY DEFINER`), **`023_arquivos_dedupe_parcial.sql`** (índice único PARCIAL — só linhas
   vivas — para reenviar o mesmo conteúdo depois de apagado não colidir com a linha morta),
   **`024_arquivos_revoke_public.sql`** (as 4 funções nasceram com EXECUTE para PUBLIC apesar do
   default privilege de 003/006; REVOKE explícito, mesmo padrão que 010/012/013/016/019 já usam).
5. **Integração**: `app/settings.py` (+4 chaves PLAT_GARAGE_ADMIN_*/REGIAO/BUCKET_PREFIXO),
   `.env`/`.env.exemplo`/`install.sh` (novo bloco: lê o `admin_token` do `garage.toml` do
   `plataforma/pipeline`, nunca gera um novo — é o mesmo daemon Garage compartilhado),
   `app/limites.py` (`ARQUIVO_BYTES_MAX` 512 MiB — MEDIDO contra os 12 GiB livres do disco onde o
   Garage grava, deliberadamente bem abaixo do `CORPO_MAX_UPLOAD_BYTES` de 2 GiB que o L0-12 reservou
   para raster; `ARQUIVO_PARTE_BYTES` 8 MiB), `app/limite_corpo.py` (`/api/arquivos` isento, exatamente
   o que o comentário daquele módulo já previa desde o L0-12), `app/main.py` (router), `app/catalogo/
   miniatura.py` (1 linha: repassa `cur`), `app/catalogo/tarefas.py` (abre `with ctx.db()` de 3 linhas
   onde a exportação chamava `objetos.guardar` fora de contexto).
6. **Testes**: `tests/api/test_arquivos.py` (novo, 13 casos — bucket idempotente, salvar/ler/apagar
   com sha256 recalculado, isolamento demo×demo2 com objeto real dos dois lados, chave RO recusando
   escrita e chave cruzada recusando leitura — as duas contra o Garage de verdade, chave com `../`
   nunca chega ao Garage, upload não sobrescreve com conteúdo diferente, cota estourada com mensagem,
   multipart real com sha256 batendo, varredura acusando órfão plantado, ponta-a-ponta pela API com
   token, taxa MB/s); `tests/api/cruzado_casos.py` (5 rotas novas na varredura A→B gerada do OpenAPI);
   `tests/api/eventos_esperados.py` (POST/DELETE declarados sem evento de domínio — motivo ao lado,
   mesmo padrão que `/api/eu/2fa/iniciar` já usa); `tests/api/catalogo/test_miniatura.py` (o teste do
   adaptador reescrito para o novo contrato). `docs/PARIDADE.md` e `docs/adr/0006-arquivos-objetos.md`
   escritos; `docs/openapi.json` regenerado.

## Evidência (comando + saída)

```
$ flock .../.pytest.lock ./venv/bin/pytest -m "not lento" -q      # suíte inteira, 4 rodadas até verde
... (rodada 1) FAILED: 2 funções com EXECUTE p/ PUBLIC + 2 ERROR de caplog (falso-positivo do meu -p no:logging)
... (rodada 2, sem -p no:logging, migração 024 aplicada) TUDO VERDE (10 blocos de "." = ~730 testes)
... (rodada 3, depois de tests/api/cruzado_casos.py) FAILED test_cobertura_100_por_cento + 5 rotas sem caso
... (rodada 4, casos acrescentados) TUDO VERDE
... (rodada 5, depois de tests/api/eventos_esperados.py) FAILED test_toda_rota_de_escrita_tem_evento_declarado
... (rodada 6, eventos acrescentados) TUDO VERDE — última rodada confirmada
$ flock .../.pytest.lock make lint sem-marcador limites    # green (rodou 2x, incl. depois do openapi regen)
All checks passed! / (sem-marcador: 0 linhas) / gerar_limites.py --check: ok
```

Isolamento MEDIDO diretamente contra o Garage real (script descartado, refeito como teste):
`PUT` com chave RO → `403 AccessDenied "Operation is not allowed for this key"`; `GET` no bucket A
com a chave RW do bucket B → mesmo 403; `PUT` acima da cota → `403 AccessDenied "Bucket size quota
is reached"`. As três são o Garage recusando, não uma checagem nossa.

## Riscos / achados durante o turno

- **Migração 021 duplicada por corrida**: outra sessão rodou `db/migrar.sh` no meio da edição deste
  arquivo e aplicou uma versão INCOMPLETA (sem `arquivo_upload`, sem índice parcial) sob o nome
  `021_arquivos` antes de eu renomear para `022`. Corrigido: linha órfã apagada de
  `plat.versao_migracao`, `022` (completo) e `023` (índice parcial) aplicados por cima. Lição para o
  laço: `ls db/migracoes | tail -1` no MOMENTO de criar não basta quando outra sessão pode aplicar
  migração no meio do trabalho — conferir de novo antes do `git add` final (fiz: `021_acervo_ficha`
  de outra trilha também apareceu nesse meio-tempo; meu arquivo é `022`, sem colisão de nome).
- **Suíte compartilhada**: rodei sob `flock` como pedido, mas vi PIDs de outras sessões rodando
  `pytest`/`make check` SEM o flock ao mesmo tempo (ex.: pid 228640 às 02:02). Não é algo que este
  item resolve; registrado para o gerente do laço avaliar se o flock precisa de reforço (ex.: alias
  do `pytest` que recuse rodar fora dele).
- Usei `git stash --include-untracked` uma vez para checar se uma falha era pré-existente e
  `git stash pop` na sequência (recuperado, conferido byte a byte depois); não repeti — é arriscado
  com trabalho concorrente de outra sessão na mesma árvore.

## Pendências (nomeadas, não escondidas)

1. **`/saude` não marca Garage como obrigatório de verdade** (o portão pede isso; ADR 0006 seção 9).
   1 linha em `app/saude.py` (status 503 quando `servicos.garage != "ok"`) + teste. Não fiz por
   tempo do turno avulso.
2. **`objetos.migrar_local`** (job prometido pelo ADR 0004 11.3): não construído — não há dado local
   real nesta máquina para migrar (só dado de teste, apagado a cada rodada da suíte).
3. **X-Accel-Redirect** (ADR 0004 11.2, "padrão que o L0-11 fixa"): não implementado; bytes
   continuam passando pelo processo Python (caminho que o próprio ADR 0004 já aceitava como válido
   "enquanto o L0-11 não entregar o cliente"). Mudança de nginx = risco de colidir com outra trilha
   no mesmo turno; nenhum objeto medido até agora passa de poucos MB para justificar o custo agora.
4. **Réplica na 2ª máquina**: `replication_factor = 1` no `garage.toml` (config compartilhada com
   `plataforma/pipeline`); é decisão de infraestrutura do cluster Garage, não de código — o
   adaptador já funciona sem mudança quando isso mudar.
5. **Sem adversário independente do turno** (era uma passagem única de 2 papéis, conforme pedido).
   As 13 refutações do próprio portão foram provadas por mim mesmo contra o Garage real; um
   adversário de fora ainda não tentou.

## Para quem continuar

- L1-02 (tiles) usa a chave **RO** já criada em `plat.arquivo_bucket.chave_ro_id/segredo` — nunca
  precisa criar bucket de novo, só ler a linha.
- L1-01-e (upload de raster grande) pode reusar `objetos.parte_iniciar/enviar/concluir/abortar`
  diretamente — é o mesmo contrato que este item entrega para o ADR 0005.
- Se `tenant.cota_bytes` mudar por fora (SQL direto), a cota real do Garage só resincroniza na
  PRÓXIMA chamada de `garantir_bucket` (implícita em todo `guardar`/`parte_*`) — não é instantânea.
