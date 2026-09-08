# L1-01-d-garage-por-inquilino — handoff (turno 3, 06/09/2026)

Ramo `wt/garage`, worktree `/home/dev/plataforma/wt/garage`. Constrói SOBRE o adaptador do L0-11 (ADR 0006), que
já estava entregue: nada dele foi refeito. ADR novo: `docs/adr/0016-garage-por-inquilino.md`.

## ⚠ numeração — ler antes de mesclar

- **Migração: `db/migracoes/042_garage_inquilino.sql`.** A reserva original era 031, depois 034; quando cheguei, a
  árvore principal já tinha commitado **034, 036, 040 e 041**, então 034 estava tomado. Usei 042, o próximo livre
  acima de tudo o que existe em `enterprise/` e nos quatro worktrees. Conferido em 06/09 13:40:
  `ls /home/dev/plataforma/enterprise/db/migracoes | tail -3` = 034, 036, 040, 041. **Se a principal passar de 042
  antes do merge, avisar — não renumerar sozinho de novo.**
- A linha `031_garage_inquilino` que a sessão anterior tinha aplicado em `plat.versao_migracao` foi APAGADA e a
  042 aplicada no lugar (a 042 é idempotente; o banco compartilhado já está com ela).
- **ADR: 0016.** 0011 (documento de construtor), 0012 e 0015 (validação de raster) já estavam tomados na principal;
  o código da sessão anterior citava "ADR 0011" e foi todo corrigido para 0016.

## O que foi construído

| arquivo | o quê |
|---|---|
| `db/migracoes/042_garage_inquilino.sql` | `plat.tenant.cota_objetos`, `plat.arquivo_bucket.cota_objetos`/`web_ativo`; as duas leitoras SECURITY DEFINER da 022 recriadas com as colunas novas; `plat.arquivo_bucket_cotas_atualizar`; visão `plat.tenant_bucket` (registro do balde SEM segredo, `security_invoker`) |
| `app/garage.py` | `CotaGarage` + `traduzir_erro_s3` (recusa do Garage em português, com o limite que ele citou); `definir_cota(bucket, bytes, objetos)`; `definir_web`; `ClienteS3.listar_buckets`; `copiar` entre baldes (existe para a refutação medir que a chave RO não consegue) |
| `app/objetos.py` | `garantir_bucket` com as duas cotas + web + `forcar`; `semear_bucket` (lê o balde de volta e reaplica quando o Garage discorda do banco); `conferir_cotas`; `uso_detalhado`; `apagar_bucket_do_inquilino`; `varrer_orfaos` agora deriva o caminho do balde da própria chave (aceita os dois formatos) |
| `app/objetos_raster.py` (novo) | objeto `<item_id>/<asset>_<sha8>.<ext>`, `HEAD` antes de gravar (`ObjetoJaExiste`), gravação em stream de arquivo ou bytes, leitura SEMPRE pela chave só-leitura, `listar_item`, `apagar_item`, `credenciais_leitura`, `caminho_web` |
| `app/baldes_semear.py` (novo) | `python -m app.baldes_semear` — passo de instalação, lê `id slug` do stdin, imprime uma linha por balde e o resumo |
| `app/rotas_arquivos.py` | `GET /api/arquivos` agora traz objetos usados/cota de objetos; `GET /api/arquivos/_chave-leitura` (sessão + `org.integracoes`); `GET /api/arquivos/_cog/autorizar` (subrequisição `auth_request` do nginx) |
| `install.sh` | passo `g3` (semeadura dos baldes); `PREFIXO_BALDE` substituído no nginx; `proxy_cache_path plat_cog` no `conf.d/plat_limites.conf`; `mkdir /var/cache/nginx/plat_cog` |
| `deploy/nginx.conf` | bloco `/svc/<token>/cog/<slug>/...` (slice 1m, cache das fatias, auth_request) + `location = /_plat_cog_autorizar` interno |
| `tests/unit/test_objetos_raster.py` (novo) | 30 casos: nome por conteúdo, dez formas de travessia recusadas, tradução das três recusas do Garage, e a expressão do caminho do COG conferida contra a que está em `deploy/nginx.conf` |
| `tests/api/test_garage_inquilino.py` (novo) | as seis cláusulas do portão + as refutações |
| `docs/openapi.json` | regenerado (`make openapi`). Além das 3 rotas deste item, entrou o que a principal já tinha commitado em código e não regenerado: `/api/itens/{id}/metadado.xml` e as 6 de `/ogc/records` |

## Portão, cláusula por cláusula

Reprodução (todos): a partir do worktree, com `PLAT_SECRET` de `/etc/plat/segredos/`, a API em `127.0.0.1:8161`
(`venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8161`) e
`PLAT_TESTE_API_PORTA=8161 flock /home/dev/plataforma/laco/.pytest.lock venv/bin/pytest tests/api/test_garage_inquilino.py tests/unit/test_objetos_raster.py -q`.
Números em `tests/medidas/L1-01-d.json`.

| cláusula | prova | resultado medido |
|---|---|---|
| **(a)** semeadura cria o balde do inquilino de teste com a cota declarada | `test_a_semeadura_cria_balde_do_inquilino_com_cota_declarada` (inquilino `zt-inq-*` novo, criado e apagado pelo próprio teste) | balde `plat-zt-inq-01170b`; banco 21.474.836.480 bytes / 200.000 objetos = Garage 21.474.836.480 / 200.000; 1ª execução **1 criado**, 2ª **0 alterados** |
| **(a′)** registro sem segredo | `test_a2_registro_do_balde_nao_expoe_segredo` | `plat.tenant_bucket` tem `bucket_alias`, `chave_ro_id`, cotas, `web_ativo`; nenhuma coluna com "segredo"; RLS devolve só a linha do próprio inquilino |
| **(b)** cota de bytes recusada pelo Garage, mensagem em português | `test_b_cota_de_bytes_recusada_pelo_garage_chega_em_portugues` — PUT direto pelo cliente S3, passando por cima da checagem prévia | cota 1.000, objeto de 4.096 → `CotaGarage(tipo="bytes")`, "o Garage recusou a gravação: a cota de armazenamento do inquilino foi atingida"; nenhuma palavra em inglês |
| **(b′)** cota de OBJETOS | `test_b2_cota_de_objetos_recusada_pelo_garage_chega_em_portugues` | cota de 1 objeto: o 1º PUT passa, o 2º volta "…a cota de objetos do inquilino foi atingida (limite do balde: 1 objetos)" |
| **(b″)** a mensagem chega à API | `test_b3_api_devolve_413_com_a_mensagem_em_portugues` | `POST /api/arquivos` com cota 500 → **413 `cota_excedida`**, "cota de 500 bytes excedida: uso atual 138906, objeto de 2048 bytes" |
| **(c)** chave RO de A não lista nem lê o balde de B | `test_c_chave_so_leitura_de_a_nao_ve_o_balde_de_b` (boto3) | `GetObject` 403 · `HeadObject` 403 · `ListObjectsV2` 403. Controle positivo no mesmo teste: a chave RO de B lê o objeto de B e o sha256 bate |
| **(d)** PUT na mesma chave é recusado | `test_d_put_na_mesma_chave_e_recusado_pelo_adaptador` | 2ª gravação do MESMO conteúdo → `ObjetoJaExiste`; conteúdo novo → chave nova (`cog_c9e41e3e.tif` → `cog_ebd6a855.tif`), versão 1 intacta |
| **(e)** GET por HTTPS com Range = 206 atrás do nginx com `slice 1m` | `test_e_range_responde_206_por_https_atras_do_nginx` — nginx PRÓPRIO na 8162, certificado autoassinado, bloco copiado de `deploy/nginx.conf` | objeto de 3.146.505 bytes, `Range: bytes=1048576-1048591` → **206**, `Content-Range: bytes 1048576-1048591/3146505`, os 16 bytes conferidos contra o conteúdo gravado; token inválido no caminho → **403** |
| **(f)** apagar item remove os objetos e o balde reflete a cota | `test_f_apagar_item_remove_objetos_e_o_balde_reflete_a_cota` | 73 objetos/138.906 bytes → 76/153.906 com 3 gravados → **73/138.906** depois (contadores do próprio Garage); 2ª chamada devolve zeros |

### Refutação (escrita antes, e medida)

| tentativa com a chave SÓ-LEITURA | resultado |
|---|---|
| `PutObject` | 403 |
| `DeleteObject` | 403 |
| `CopyObject` no mesmo balde | 403 |
| `CopyObject` de um balde para o outro | 403 |
| `CreateMultipartUpload` | 403 |
| `ListBuckets` | **200**, mas a lista traz só `['plat-demo']` — o balde do outro inquilino não aparece |
| chave de objeto com `..` (`..`, `../../etc`, `item01/..`, `cog/../..`, e a chave completa `demo/../demo2/...`) | `ChaveInvalida` em todas: a expressão não admite ponto nem barra no item/asset |
| `/svc/<token de A>/cog/demo2/...` (token de A no caminho de B) | 403 |
| `/svc/<token de A>/cog/demo/../demo2/...` | 403 |

Nenhuma escrita passou. O objeto alvo continuava intacto depois de todas as tentativas (conferido no teste).

## O que ficou de fora e por quê

- **O bloco do nginx NÃO foi aplicado em `/etc/nginx`.** Regra do turno: escrever o trecho em `deploy/` e deixar
  o gerente aplicar. Ele está em `deploy/nginx.conf` e o `install.sh` já sabe substituir `PREFIXO_BALDE` e criar
  `/var/cache/nginx/plat_cog` + a zona `proxy_cache_path plat_cog` em `conf.d/plat_limites.conf`. **Para aplicar:
  `sudo bash install.sh <dominio> <porta>`** (ou só reescrever o site com `escrever_nginx`). Enquanto não for
  aplicado, a entrega de COG por HTTPS existe como configuração provada, não como serviço no ar.
- **Rotação de chave de acesso.** `criar_chave` é idempotente por NOME e o Garage só devolve o segredo na criação;
  rodar chave é outro item.
- **`endpoint_publico` na credencial só-leitura sai `null`.** Expor a API S3 do Garage por HTTPS para um ArcGIS Pro
  fora desta máquina é decisão de infraestrutura (DNS, certificado, quem responde por abuso). Hoje a credencial
  serve a quem alcança o endpoint interno (TiTiler na mesma máquina).
- **Cota por classe de objeto** (tantos bytes de miniatura × de COG): a cota é do balde. Separar exigiria balde por
  classe ou contabilidade nossa — e contabilidade nossa é o que este item evita.

## Limitações honestas

- A mensagem de cota de BYTES que esta instância do Garage devolve **não cita o limite**; a de objetos cita. O
  código lê o número quando ele existe (`CotaGarage.limite`) e não inventa quando não existe.
- Na prática quem responde à API é a **checagem prévia** (`conferir_cotas`, GetBucketInfo antes do PUT), porque ela
  corre antes e dá mensagem mais informativa. A recusa do Garage é a garantia, não o caminho comum: o teste (b) só
  a alcança mandando o PUT direto pelo cliente S3.
- `ListBuckets` com a chave RO responde 200. O Garage lista só os baldes que a chave alcança, então não vaza o do
  vizinho — mas quem esperava 403 tem de saber que não é 403.
- A cláusula (e) foi provada contra um **nginx de teste**, não contra o nginx do sistema. O bloco é o mesmo arquivo
  (o teste recorta o trecho de `deploy/nginx.conf`), mas a pilha real tem certbot, HSTS e modsecurity por cima.
- `apagar_item` apaga objeto por objeto (`DeleteObject`). Para um item com dezenas de milhares de objetos isso é
  lento; o `listar` pagina de 1.000 em 1.000 e não há `DeleteObjects` em lote no cliente.
- Só há UM inquilino de teste por rodada do módulo, criado e apagado pelo próprio teste; se a rodada morrer no
  meio, sobra um balde `plat-zt-inq-*` no Garage (a limpeza de fim de sessão do `conftest` apaga o inquilino no
  banco, não o balde). Conferido ao fim desta rodada: **nenhum balde nem chave `zt-*` sobrou**.

## Como o adversário reproduz

```bash
cd /home/dev/plataforma/wt/garage
set -a; source .env; set +a
export PLAT_SECRET=$(sudo cat /etc/plat/segredos/PLAT_SECRET) PLAT_AMBIENTE=dev
# a API tem de estar ouvindo: a cláusula (e) faz auth_request HTTP de verdade
venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8161 &
PLAT_TESTE_API_PORTA=8161 flock /home/dev/plataforma/laco/.pytest.lock \
  venv/bin/pytest tests/api/test_garage_inquilino.py tests/unit/test_objetos_raster.py -q
# semeadura à mão (a 2ª vez tem de imprimir "0 criados/alterados")
printf '1 demo\n2 demo2\n' | venv/bin/python -m app.baldes_semear
```

Resultado desta rodada: **43 passaram, 0 falharam, 0 pulados** (13 de API + 30 unitários). `make lint`,
`make sem-marcador` e `make limites` passam.

## Riscos de merge

- `docs/openapi.json` — regenerado; a principal também mexe. Se conflitar, resolver rodando `make openapi` depois
  do merge, nunca à mão.
- `install.sh` — três blocos novos, todos localizados (passo `g3`, `PREFIXO_BALDE`, `plat_limites.conf`).
- `deploy/nginx.conf` — dois `location` novos inseridos ANTES de `location / {`.
- `app/objetos.py`, `app/garage.py`, `app/rotas_arquivos.py` — só deste item no turno, até onde vi.
- `CHANGELOG.md` — entrada nova no topo da seção do turno 3.
- **`db/migracoes/042_garage_inquilino.sql`** — ver o aviso de numeração no topo.

## Commits do ramo

- `087e94e` — Balde por inquilino no Garage: cota dupla, chave só-leitura e COG por Range (item L1-01-d)

Ramo `wt/garage`, sobre `fa11658` (último commit de `master` quando o worktree nasceu). Um commit só: o trabalho
estava em disco sem commit quando esta sessão retomou (a anterior caiu por cota da API) e foi terminado inteiro
antes de fechar.
