# ADR 20260908T1255 — Balde por inquilino no Garage: cota dupla, chave só-leitura e objeto nomeado por conteúdo (item L1-01-d-garage-por-inquilino)

Estado: aceito (arquiteto + backend + raster, turno 3, 06/09/2026). Estende o ADR 0006, que criou o adaptador
genérico de arquivos/objetos (`app/objetos.py`, item L0-11). Nada aqui substitui aquele contrato: `guardar/ler/
existe/apagar/url_assinada` continuam iguais para os quatro chamadores do catálogo. O que este ADR acrescenta é o
que a linha L1 (imagens) precisa e o adaptador genérico não dava: cota em objetos, chave só-leitura que sai de
casa, nome de objeto no formato da linha de imagens, recusa explícita de sobrescrita e entrega por Range atrás do
nginx. Todo número abaixo foi MEDIDO nesta instância (Garage v2.3.0, `GetClusterStatus` em 06/09/2026) ou LIDO em
código que já roda; nada vem de documentação de fora.

## 1. Por que uma segunda cota (objetos), se já havia cota em bytes

A cota do L0-11 era só `maxSize`. Um COG de 200 MB e 200 mil miniaturas de 2 KB somam bytes parecidos e custam
coisas muito diferentes ao cluster: o Garage indexa cada objeto e a contagem, não o volume, é o que enche a
partição de metadado. `UpdateBucket` aceita `quotas: {maxSize, maxObjects}` — MEDIDO: com `maxObjects` na conta
exata dos objetos existentes, o PUT seguinte volta 403 `AccessDenied` com "Object quota is reached, maximum
objects for this bucket: N". As duas cotas moram em `plat.tenant` (autoridade) e são espelhadas em
`plat.arquivo_bucket` (o que já foi aplicado no Garage); divergência entre os dois é corrigida na semeadura, com
linha impressa, nunca em silêncio.

Consequência medida durante o próprio turno: o balde `plat-demo` estava com `maxObjects: null` no Garage e 200000
no banco (a coluna nasceu com DEFAULT na migração, e `garantir_bucket` só reaplica quando o banco MUDA). É
exatamente o caso que `semear_bucket` existe para pegar: ele lê o balde de volta pela Admin API depois de
sincronizar e reaplica quando o Garage discorda do banco.

## 2. A mensagem de recusa é traduzida na borda, não no meio

O Garage responde em inglês, em XML de erro S3. `app/garage.traduzir_erro_s3` converte as três frases que esta
instância devolve ("Bucket size quota is reached…", "Object quota is reached…", "Operation is not allowed for
this key") em uma frase em português, com o limite que o próprio Garage citou, e devolve `CotaGarage` — subclasse
de `ErroGarage` com `tipo` ("bytes" ou "objetos") e `limite`. Quem chama distingue cota de falta de permissão sem
ler texto. A rota `POST /api/arquivos` já transformava `CotaExcedida` em 413 `cota_excedida`; agora a mensagem que
chega ao cliente é a do Garage, traduzida, e não uma paráfrase nossa que pode divergir do que ele fez.

Decisão explícita: a checagem prévia (`objetos.conferir_cotas`, GetBucketInfo antes do PUT) CONTINUA existindo,
mas não é a garantia. A garantia é a recusa do Garage. A checagem prévia serve para dar mensagem boa e evitar
gastar upload multipart; se ela tiver bug, o Garage recusa do mesmo jeito — é o que o teste (b) mede, mandando o
PUT direto pelo cliente S3, por cima da checagem.

## 3. Nome do objeto: `<item_id>/<asset>_<sha8>.<ext>`, nunca sobrescrito

Regra medida em 29/08/2026 na prova do pipeline: sobrescrever o mesmo nome de objeto deixou o TiTiler em 500 (o
GDAL guarda o cabeçalho do COG em cache por caminho) e a CDN servindo fatia velha ao lado de fatia nova. Aqui isso
deixa de ser convenção e vira recusa: `app/objetos_raster.py` faz `HEAD` antes de gravar e levanta `ObjetoJaExiste`
se a chave já está no balde. O `sha8` é o prefixo do sha256 do conteúdo, então conteúdo novo produz chave nova por
construção — nunca é preciso sobrescrever para publicar versão nova, e as duas versões coexistem enquanto o
catálogo apontar para as duas.

A expressão que valida a chave não admite ponto nem barra no `item_id` e no `asset`, então `..` não é um caso
especial tratado: é uma forma que a expressão não gera nem aceita. O teste unitário cobre dez formas erradas.

## 4. Duas chaves de acesso, e só uma sai de casa

Cada balde tem chave RW (read+write+owner) e chave RO (read). A RW só existe dentro de `objetos._cliente(bucket)`,
no processo da API e do worker; nenhuma rota a devolve. A RO sai por `GET /api/arquivos/_chave-leitura`, só sob
sessão e com o privilégio `org.integracoes` (o mesmo que o ADR 0002 reservou para SSO/SMTP/integração), porque a
conexão S3 do ArcGIS Pro e o `/vsis3` do GDAL do TiTiler precisam de uma credencial S3 de verdade — não dá para
entregar COG a eles por rota autenticada nossa sem intermediar cada Range.

REFUTAÇÃO escrita antes do código e medida com boto3 (o mesmo cliente que o Pro usa por baixo): com a chave RO,
`PutObject`, `DeleteObject`, `CopyObject` no mesmo balde, `CopyObject` entre baldes e `CreateMultipartUpload` são
todos recusados, e `GetObject`/`HeadObject`/`ListObjectsV2` no balde do outro inquilino também. Qualquer escrita
bem-sucedida refutaria o item; os códigos medidos estão em `tests/medidas/L1-01-d.json`.

## 5. Entrega por HTTPS: endpoint web do Garage, token no caminho, autorização por auth_request

O TiTiler e o ArcGIS Pro seguem a URL crua por Range e não carregam cabeçalho nosso. URL assinada que expira
quebra o mapa colado no web map (crítica registrada em 29/08). Então o token de serviço do inquilino vai no
CAMINHO: `/svc/<token>/cog/<slug>/<item_id>/<asset>_<sha8>.<ext>`.

Quem serve o byte é o endpoint **web** do Garage (:3902), que faz leitura anônima do balde — a API S3 (:3900)
continua exigindo assinatura, e MEDIDO: ligar o web não abre a API S3. Como o web é anônimo, quem autoriza é a
aplicação, por `auth_request` do nginx: a subrequisição chega em `GET /api/arquivos/_cog/autorizar` com o caminho
original em `X-Original-URI`, e a rota exige que o token exista, esteja vivo e seja do MESMO inquilino do `<slug>`
do caminho. A resposta é sempre a mesma 403 quando qualquer condição falha — a rota não vira oráculo de token.

`slice 1m` + `proxy_cache_lock` fazem o nginx pedir fatias de 1 MiB alinhadas e cacheáveis (medição de 31/08: 20
pedidos simultâneos ao mesmo tile frio = 1 MISS + 19 HIT). Sem `slice`, cada Range diferente do GDAL seria um
MISS diferente.

Limitação honesta: o bloco foi escrito em `deploy/nginx.conf` e PROVADO contra um nginx próprio, de teste, com
certificado autoassinado na porta 8162 (206 com `Content-Range` conferido byte a byte contra o conteúdo gravado).
Ele NÃO foi aplicado no nginx do sistema neste turno — quem aplica é o gerente, com `install.sh`. Enquanto não for
aplicado, a entrega de COG por HTTPS existe como configuração provada, não como serviço no ar.

## 6. Ciclo de vida: quem cria e quem apaga

Criação: passo `g3` do `install.sh` (`python -m app.baldes_semear`, lista de inquilinos ativos vinda do psql como
postgres, porque a RLS de `plat.tenant` só deixa `plat_app` ver o próprio). Idempotente por construção: a segunda
execução imprime "0 criados/alterados", e é assim que o teste (a) mede.

Apagamento: `objetos_raster.apagar_item` remove todos os objetos do prefixo `<item_id>/` e marca as linhas de
`plat.arquivo`; o balde reflete a cota na hora (GetBucketInfo do próprio Garage volta aos contadores de antes).
`objetos.apagar_bucket_do_inquilino` desfaz o balde inteiro (objetos, as duas chaves de acesso, o balde e a linha
de `plat.arquivo_bucket`) — existe porque `plat.inquilino_apagar` só limpa o banco, e sem isto balde e chaves
ficariam órfãos no Garage.

## 7. O que ficou de fora, de propósito

- **Rotação de chave.** `criar_chave` é idempotente por NOME e o Garage só devolve o segredo na criação; rodar
  chave exige criar a nova, repermitir, regravar e só então apagar a velha, com janela em que as duas valem.
  Não é este item.
- **Cota por CLASSE de objeto** (tantos bytes de miniatura, tantos de COG). A cota é do balde; separar por classe
  exigiria balde por classe ou contabilidade nossa — e contabilidade nossa é justamente o que este ADR evita.
- **`endpoint_publico` na credencial só-leitura.** Sai `null`: expor a API S3 do Garage por HTTPS para o ArcGIS
  Pro de fora da máquina é decisão de infraestrutura (nome DNS, certificado, quem responde por abuso) que este
  turno não tem como fechar sozinho. Enquanto for `null`, a credencial serve a quem alcança o endpoint interno.
