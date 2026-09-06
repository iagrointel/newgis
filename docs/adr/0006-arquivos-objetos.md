# ADR 0006 — Arquivos/objetos por inquilino no Garage (item L0-11-arquivos-objetos)

Estado: aceito (arquiteto+backend, turno avulso, 06/09/2026). Garage já rodava em produção nesta máquina
(`plataforma-garage`, :3900 S3 / :3903 admin, v2.3.0 — ADR 0001 seção 2, "Garage, já ativo em :3900") a serviço de
`plataforma/pipeline`; este item constrói o cliente que o `plat` usa, com bucket, chave de acesso e cota **por
inquilino**, e estende o adaptador local que o L0-03 (catálogo) já criava por conta própria (`app/objetos.py`,
contrato fixado no ADR 0004 seção 11.3 e estendido no ADR 0005 seção 11.3-estendida). Nenhuma decisão vale por
moda: MEDIDO nesta máquina (comando e saída abaixo), LIDO em código que já roda, ou contrato já escrito por outro
ADR que este apenas cumpre.

## 1. O que já existia e o que faltava

`app/objetos.py` (backend do L0-03) já tinha `guardar(classe, item_id, dados, content_type) -> {chave, sha256,
bytes}`, `ler(chave)`, `existe(chave)`, `apagar(chave)`, `url_assinada(chave, segundos)`, `assinatura_valida(...)`,
gravando em disco local (`PLAT_DADOS_DIR`) com chave `<classe>/<uuid>/<sha256>.<ext>`. Isso cobria a METADE da
hipótese do item (nome por sha256, nunca sobrescrito, entrega só pela API com URL assinada) mas não a outra
metade, que é o motivo de o item existir: bucket **por inquilino** no Garage, chave de acesso **própria** por
inquilino, cota **verificável** pela API admin, upload grande sem estourar a RAM da máquina (1,9 GiB
"available", `free -h` 06/09/2026) nem o disco (`/` a 98%, 12 GiB livres — é onde o Garage grava).

## 2. Isolamento: por que bucket, não por prefixo de chave

A hipótese do estado do laço já fixava a forma: "1 bucket por inquilino (nome = slug), 1 chave de escrita da API
(nunca entregue) e 1 chave só-leitura por inquilino para tiles (L1-02)". MEDIDO contra o Garage real desta
máquina (script descartado, comandos abaixo reproduzem):

```
PUT com a chave RW de um bucket, acima da cota → 403 AccessDenied "Bucket size quota is reached"
PUT com a chave RO de um bucket → 403 AccessDenied "Operation is not allowed for this key"
GET no bucket A com a chave RW do bucket B → 403 AccessDenied "Operation is not allowed for this key"
```

As três recusas são do **Garage**, não de uma checagem nossa — é a diferença entre "isolamento que uma linha de
código pode esquecer de aplicar numa rota nova" e "isolamento que o servidor de objetos aplica sempre, mesmo se
`app/objetos.py` tiver um bug amanhã". Por isso o desenho é: **bucket físico por inquilino** (`plat-<slug>`, o
prefixo `plat-` evita colidir com o bucket `demo` que o `plataforma/pipeline` já usa nesta mesma instância —
`ListBuckets` mostrou o alias `demo` ocupado, MEDIDO antes de escolher o prefixo), **2 chaves de acesso por
bucket** (RW só para a API do `plat`, nunca sai do processo; RO reservada para o L1-02 servir tiles direto —
ainda não usada, criada agora para não exigir migração de chave depois), **cota do bucket = `tenant.cota_bytes`**
posta pela Admin API (`UpdateBucket`, campo `quotas.maxSize`) e resincronizada a cada `garantir_bucket()` quando
o valor do inquilino muda.

## 3. Cliente S3 sem boto3 (decisão por medição)

A venv do `plat` (`--system-site-packages`) tem `requests` mas não `boto3`/`botocore`; o `plataforma/pipeline` tem
os dois numa venv PRÓPRIA de ~80 MB de pacote. Com o disco desta máquina a 98% (12 GiB livres), instalar
botocore aqui por uma chamada de API que a assinatura AWS SigV4 resolve em ~80 linhas de `hmac`/`hashlib` é o
mesmo padrão já usado no repo para senha (pbkdf2 da stdlib em vez de bcrypt, ADR 0001 seção 6: "zero dependência
nova"). A assinatura foi **medida contra o Garage real** desta máquina antes de entrar no código de produção:

```
PUT/GET/HEAD/DELETE, COPY (x-amz-copy-source), multipart (CreateMultipartUpload/UploadPart/
CompleteMultipartUpload/AbortMultipartUpload), ListObjectsV2 — todos MEDIDOS OK contra plataforma-garage :3900
antes de app/garage.py existir; ClienteAdmin.criar_bucket/criar_chave/permitir/definir_cota/info_bucket também
medidos contra a Admin API v2 (:3903) antes de app/objetos.py chamá-los.
```

`app/garage.py` tem os dois clientes (`ClienteS3`, `ClienteAdmin`); nenhuma outra parte do repo importa `boto3`.

## 4. Chave: sha256 do conteúdo, com o inquilino no próprio texto

Formato: `<slug>/<classe>/[<referencia>/]<sha256>.<ext>` (regex em `app/objetos.CHAVE`). O `<slug>` (não o
`tenant_id`) é o que permite `ler/existe/apagar/url_assinada` resolverem sozinhos o bucket certo **sem contexto
de sessão** — a entrega por URL assinada (`GET /api/objetos/{chave}`, ADR 0004 seção 11.2) é uma rota anônima,
sem `db.db(ctx)`; só `guardar` precisa de `cur` dentro do contexto do inquilino (é dali que vem o `tenant_id`
para achar/criar o bucket e gravar `plat.arquivo`). Duas gravações do MESMO conteúdo (mesma classe/referência)
caem na mesma chave: `HEAD` antes de `PUT` decide se grava; **nunca pode sobrescrever conteúdo diferente**,
porque a chave só é igual quando o sha256 é igual — não existe caminho de código em que o servidor escreva bytes
diferentes na mesma chave (a chave é *derivada* do conteúdo recebido, nunca escolhida pelo chamador).

`<referencia>` opcional: quando o objeto pertence a um item do catálogo (miniatura, exportação), é o uuid/id
desse dono, preservando o comportamento que o L0-03 já tinha; quando é um upload genérico (`/api/arquivos`), fica
ausente e o dedup vale só por `classe + sha256` dentro do inquilino.

## 5. Contrato preservado para os quatro chamadores existentes

`app/catalogo/miniatura.py`, `tarefas.py`, `destruidores.py`, `rotas_compartilhamento.py` chamavam
`objetos.guardar/ler/apagar/existe/url_assinada/assinatura_valida` antes deste item. Depois dele:

- `ler`, `existe`, `apagar`, `url_assinada`, `assinatura_valida`: **assinatura idêntica**, zero mudança nos quatro
  arquivos (a chave por si só resolve o bucket).
- `guardar`: ganhou `cur` como 1º parâmetro (para achar o inquilino e gravar `plat.arquivo` com RLS) e o antigo
  2º parâmetro (`item_id`) virou `item_id=None` opcional por *keyword*. Duas chamadas mudaram: `miniatura.guardar`
  (a função pública que `rotas_miniatura.py`/`tarefas.py` chamam **continua com a mesma assinatura**; só o corpo
  dela passou a repassar `cur`) e a exportação de lista em `tarefas.py` (que abre um `with ctx.db()` de 3 linhas
  onde antes chamava `objetos.guardar` fora de qualquer contexto — o pool aceita transações curtas extras sem
  problema, ADR 0001 seção 3.2).

## 6. Upload grande: streaming, multipart real, e por que nunca por cookie

Contrato pedido pelo item: `salvar(inquilino, bytes) -> {sha256, tamanho, content_type}`, `ler(inquilino, sha256)
-> stream`, `uso(inquilino) -> bytes_usados`. Isso virou a rota genérica `POST/GET/DELETE /api/arquivos` (`app/
rotas_arquivos.py`), construída sobre o mesmo `app/objetos.py`.

**Achado no meio do turno**: a suíte reprovou a primeira versão com `415 tipo_nao_aceito`. Causa: `checar_
escrita_sob_cookie` (ADR 0002 seção 5.3) exige `application/json` em **todo** verbo de escrita sob cookie de
sessão (CSRF) — o mesmo motivo pelo qual `rotas_miniatura.py` manda a imagem em base64 dentro de JSON (comentário
já deixado lá: "multipart entra com o L0-11"). Um upload de bytes crus não pode ser `application/json`. Decisão:
**`POST /api/arquivos` só aceita token de serviço (`Authorization: Bearer`), nunca cookie** — `auth.modo != "token"
→ 403 exige_token`, checado depois do 415 que o middleware de CSRF já dá de qualquer forma. Um cliente de
navegador that queira enviar um arquivo cria um token de escopo restrito pela rota JSON de sempre
(`POST /api/tokens`, essa sim sob cookie) e usa o token para o envio — o mesmo padrão que upload assinado de S3
resolve com URL pré-assinada. `GET`/`DELETE` continuam aceitando sessão OU token (sem corpo, sem CSRF).

Streaming: a rota lê `request.stream()` (ASGI puro, isenta de `app/limite_corpo.py` — `PREFIXOS_ISENTOS` ganhou
`/api/arquivos`, exatamente o que o comentário daquele módulo já previa desde o L0-12) em pedaços de
`limites.ARQUIVO_PARTE_BYTES` (8 MiB). Até `ARQUIVO_BUFFER_UNICO_BYTES` (= a mesma constante): um `PUT` só.
Acima: abre multipart real no Garage (`objetos.parte_iniciar/parte_enviar/parte_concluir`, contrato do ADR 0005
seção 11.3-estendida) contra um objeto temporário (`_tmp/<uuid>`), lê o objeto de volta **em stream** para
calcular o sha256 verdadeiro (o ETag multipart do S3 não é isso — é um hash das partes, não do conteúdo, doc
AWS), copia (`x-amz-copy-source`, sem baixar/reenviar) para a chave final por conteúdo e apaga o temporário.
RAM usada pelo processo por upload: nunca mais que uma parte (8 MiB) + overhead do driver, **mesmo para um
arquivo no teto de `ARQUIVO_BYTES_MAX`** — importante nesta máquina (RAM "available" medida em 1,9-3,0 GiB ao
longo do turno). `ARQUIVO_BYTES_MAX = 512 MiB`, deliberadamente bem abaixo do `CORPO_MAX_UPLOAD_BYTES` de 2 GiB
que o L0-12 reservou para raster (L1-01-e): o disco onde o Garage grava tinha 12 GiB livres quando este item foi
medido; 2 GiB por objeto encheria o disco em poucos envios. Revisar junto do L1-01-e.

## 7. Cota: o Garage decide, nós só sincronizamos e explicamos

`garantir_bucket(cur, tenant_id, tenant_slug)` é chamada em todo `guardar`/`parte_*`; na 1ª vez cria bucket + 2
chaves + cota no Garage e registra em `plat.arquivo_bucket` (`SECURITY DEFINER`, mesmo padrão de `auth_*` do ADR
0001 seção 3.3, porque a leitura por chave/URL assinada não tem contexto de inquilino); nas seguintes, compara
`tenant.cota_bytes` (autoridade) com o cache local e resincroniza a cota real no Garage se mudou. `guardar`
também faz uma checagem PRÓPRIA antes do `PUT` (soma `uso atual + tamanho do objeto` contra a cota, via
`GetBucketInfo`) para devolver uma mensagem legível (`CotaExcedida`, 413) em vez de deixar o Garage estourar
primeiro com um XML de erro S3 — mas o Garage recusaria de qualquer forma mesmo que essa checagem tivesse um bug
(seção 2). `uso(slug)` lê `GetBucketInfo(bucket_id).bytes`: contagem exata do próprio Garage, não uma soma
mantida por nós (que poderia divergir).

## 8. Metadado, varredura de órfãos, migração `db/migracoes/`

`plat.arquivo` (RLS por `tenant_id`) grava classe/referência/sha256/bytes/content-type/chave por objeto; é dali
que `GET /api/arquivos/{sha256}` resolve a chave completa (a chave nunca é adivinhada a partir do sha256 sozinho:
precisaria saber a extensão) e é dali que `varrer_orfaos(cur, slug)` compara **o bucket real** (`ListObjectsV2`,
excluindo `_tmp/`) com as linhas vivas: `sem_linha` (upload que terminou no Garage mas a transação do metadado
falhou depois) e `sem_objeto` (linha sem objeto — apagado por fora, ou bucket recriado). Migração
`db/migracoes/022_arquivos.sql` (`arquivo_bucket`, `arquivo`, `arquivo_upload`, funções `SECURITY DEFINER`) +
`023_arquivos_dedupe_parcial.sql` (ver Anexo — corrigiu um índice único cheio que uma corrida com outra sessão de
teste tinha aplicado antes da versão final do arquivo existir; migração imutável, por isso a correção veio em
arquivo novo, nunca editando o já aplicado).

## 9. `/saude`: Garage vira obrigatório a partir daqui

ADR 0001 seção 7 já previa isso: "o item que criar o serviço muda o contrato". `app/saude.py` não foi editado
neste turno por falta de tempo do turno avulso — **fica registrado como pendência explícita** (não como decisão
silenciosa): o campo `servicos.garage` de `/saude` deveria passar a contar para o HTTP 200/503, do jeito que
`banco` já conta. Enquanto isso não entra, `/saude` continua reportando `garage` como informativo. Não é uma
lacuna escondida: está na tabela da seção 11 e no handoff.

## 10. O que este item NÃO fez (pendências nomeadas)

- `/saude` não marca Garage como obrigatório de verdade (seção 9): próximo turno, 1 linha em `app/saude.py` +
  teste.
- `objetos.migrar_local` (job que o ADR 0004 seção 11.3 promete para mover arquivos do adaptador local antigo
  para o Garage): não construído — o adaptador local nunca chegou a acumular dado real nesta máquina (só dado de
  teste/demo, apagado a cada rodada da suíte), então não há dado para migrar hoje; o job fica pendente para
  quando/se um ambiente tiver dado local real.
- X-Accel-Redirect (ADR 0004 seção 11.2, "padrão que o L0-11 fixa para todo objeto"): não implementado —
  os bytes continuam passando pelo processo Python (como o próprio ADR 0004 já aceitava como caminho válido
  "enquanto o L0-11 não entregar o cliente"); trocar por proxy interno do nginx é uma mudança de infraestrutura
  (risco de colidir com outra trilha mexendo em nginx no mesmo turno) que fica para quando houver objeto grande
  o bastante para o custo de CPU do proxy em Python importar de verdade (nenhum medido até agora passa de
  poucos MB).
- Réplica na 2ª máquina: `replication_factor = 1` no `garage.toml` desta instância (config do
  `plataforma/pipeline`, compartilhada); replicar exige outro nó no cluster Garage, decisão de infraestrutura
  fora do escopo deste item (o adaptador já funciona sem mudança de código quando isso acontecer — é o Garage
  quem replica, não a aplicação).

## 11. Paridade Esri (linha para `docs/PARIDADE.md`)

Referência: ArcGIS Enterprise usa o "object store" (S3-compatível ou Azure Blob) para hospedar itens grandes,
sem bucket por organização exposto ao administrador (é interno ao portal). Aqui cada inquilino tem bucket e
chaves PRÓPRIOS, verificáveis pela Admin API — mais granular que o portal Esri, que não expõe isolamento físico
de armazenamento por organização ao cliente. `parcial`: falta `/saude` obrigatório e X-Accel-Redirect (seção 10).

## 12. Consequências e o que custa mudar

| decisão | custo de reverter |
|---|---|
| SigV4 à mão em vez de boto3 | trocar por boto3 = novo requirement (~80 MB), reescrever `app/garage.py`; nenhuma mudança em `app/objetos.py` (a interface de `ClienteS3`/`ClienteAdmin` não vaza detalhe de assinatura) |
| chave com slug embutido | mudar para "bucket único + prefixo" exigiria migrar toda chave existente; hoje só dado de teste |
| upload só por token (nunca cookie) | é a mesma restrição de CSRF que já existe para toda escrita sob cookie (ADR 0002); não há como afrouxar sem reabrir o CSRF que aquele ADR fechou |
| `ARQUIVO_BYTES_MAX = 512 MiB` | 1 linha em `limites.py`, sem migração; revisar quando o disco crescer |
| multipart com objeto temporário + copy | Garage não tem "rename"; o custo é 1 COPY (servidor-a-servidor, sem baixar) por upload grande — aceitável |
