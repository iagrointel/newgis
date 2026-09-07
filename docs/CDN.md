# CDN de ladrilho (item L7-26-cdn-tiles)

Este documento cobre a camada de CDN em frente ao serviço de ladrilho raster (`L1-02-tiles-token`,
ADR `20260907T0300`) e o que foi decidido para ela (ADR `20260907T1522`). Ver também `docs/LIMITES.md`
(limites gerais da aplicação) e `docs/PARIDADE.md` (paridade com Esri).

## O que existe, testado de verdade

- **Endereço versionado**: `GET /svc/<token>/raster/<item>@<versao>/{z}/{x}/{y}.png`, onde `<versao>`
  são os 12 primeiros caracteres do sha256 do raster (`plat.raster_item.sha256`). Casa com o sha256
  vigente → `Cache-Control: public, max-age=31536000, immutable` e `ETag` com o sha256 inteiro. Não
  casa → `404 versao_inexistente`, sem ler o pixel (a checagem de inquilino sempre acontece ANTES da
  checagem de versão — ver ADR, seção 3, "achado").
- **O `TileJSON`** (`/svc/<token>/raster/<item>/tilejson.json`) já devolve a URL versionada nos
  `tiles[]`: o cliente de mapa (QGIS, navegador, ArcGIS) nunca precisa saber que "versão" existe.
- **Rota sem versão** (`/svc/<token>/raster/<item>/{z}/{x}/{y}`, contrato original do L1-02) continua
  com `Cache-Control: public, max-age=300` — nunca vira imutável, porque sem sha256 no caminho o
  conteúdo por trás do endereço pode mudar.
- **Rotas que não são ladrilho** sob o mesmo prefixo (`tilejson.json`, `info.json`, `wmts`
  GetCapabilities) continuam com `no-store, must-revalidate` — nunca ficam elegíveis a cache de CDN.
- **A API da aplicação** (`/api/...`) nunca tem `Cache-Control` de CDN — testado em
  `tests/api/imagens/test_cdn_tiles.py::test_rota_de_api_nunca_tem_cache_control_de_cdn`.
- **Simulação local do mecanismo de CDN** (`scripts/cdn_simulada.py`): um proxy HTTP real (socket de
  verdade, sem biblioteca de mock) que cacheia por CAMINHO sem query string, respeita o
  `Cache-Control` da origem para decidir o que guardar, marca `cf-cache-status: HIT|MISS|BYPASS` e
  aceita purge por prefixo em `POST /__purgar__ {"prefixos": [...]}` (até 100 por pedido, mesmo teto
  da API real da Cloudflare).
- **Prova fim-a-fim com sockets reais** (`scripts/prova_cdn.py` → `tests/medidas/L7-26-cdn-tiles.json`):
  sobe a API de verdade (uvicorn) e a CDN simulada, mede as 4 cláusulas testáveis localmente do
  portão + as duas refutações (martelar depois de revogar; token de outro inquilino).

## O que NÃO existe e é PENDENTE DO DONO

Não há acesso à conta Cloudflare real nesta bancada. Nenhum DNS foi criado, nenhuma Cache Rule foi
configurada na conta, nenhum purge de produção foi disparado. O que falta, passo a passo, para quem
tiver acesso à conta:

1. **Criar o registro DNS** `tiles-<x>.iagrointel.com` (nome real = decisão D18/D19, ainda aberta)
   apontando para o mesmo IP da aplicação, com o proxy da Cloudflare LIGADO (nuvem laranja) — ao
   contrário do hostname da aplicação (`<x>.iagrointel.com`), que fica DNS-only (nuvem cinza, D19).
2. **Criar a Cache Rule** (Cloudflare → Rules → Cache Rules; o plano Free permite até 10 regras):
   - Se o hostname/URL corresponder a `tiles-<x>.iagrointel.com/svc/*` → **Cache eligibility: Eligible
     for cache** (o equivalente a "cache everything" para esse prefixo).
   - **Edge Cache TTL: respeitar `Cache-Control` da origem** (não sobrescrever) — é o que faz o
     `max-age=31536000, immutable` do ladrilho versionado valer, e o `no-store` do TileJSON/
     info.json/capabilities continuar sem cache.
   - **Cache Key: NÃO marcar "ignore query string"** — deixar a chave padrão (caminho + query
     string completa). ⛔ **Correção à hipótese original** (achado medido nesta bancada, ver ADR
     20260907T1522 §2): "ignorar query string" faz duas renderizações diferentes do MESMO
     `item@versao/{z}/{x}/{y}` (ex.: `?bandas=3,2,1` contra `?expressao=(b4-b3)/(b4+b3)`) colidirem
     no mesmo slot de cache — um cliente recebe a imagem RENDERIZADA PARA O OUTRO, silenciosamente,
     sem erro. A versão no caminho garante que o byte não muda com o TEMPO; não garante que
     parâmetros de renderização diferentes produzam o mesmo byte — são dimensões diferentes.
     Confirmado com `scripts/cdn_simulada.py` antes da correção: pedir RGB e depois NDVI do mesmo
     ladrilho devolvia os bytes do RGB nos dois casos (`cf-cache-status: HIT` no 2º pedido). Sem
     perda prática em ignorar isso: o TileJSON já embute os MESMOS parâmetros de renderização em
     todo ladrilho que um cliente de mapa pede, então a query string é idêntica dentro de uma sessão.
3. **Configurar o webhook de revogação de token** para chamar a API de purge por prefixo da
   Cloudflare quando um token for revogado (endpoint `app/auth/rotas_tokens.py::revogar`, hoje só
   grava `revogado_em` no banco — não há chamada de purge nem local nem remota automatizada ainda).
   Comando real (token de API da zona com permissão `Cache Purge`):
   ```
   curl -X POST "https://api.cloudflare.com/client/v4/zones/<ZONE_ID>/purge_cache" \
     -H "Authorization: Bearer <API_TOKEN>" -H "Content-Type: application/json" \
     --data '{"prefixes": ["tiles-<x>.iagrointel.com/svc/<token>/"]}'
   ```
   **Importante** (achado da bancada, ver ADR seção 3): a origem cacheia a autorização do token por
   2 segundos (`AUTH_TTL_S` em `app/imagens/rotas_tiles.py`). Se o purge disparar e uma chamada
   acontecer dentro dessa janela, a origem ainda responde 200 (autorização antiga) e a Cloudflare
   RECACHEIA o 200 por 1 ano. O webhook de revogação deve chamar o purge pelo menos duas vezes,
   com pelo menos 2 segundos de intervalo (ou esperar 2 s antes do único purge) — nunca purgar uma
   vez só na mesma transação da revogação.
4. **Medir o tráfego real de origem por mês** (Cloudflare → Analytics → Cache, ou logs de origem) e
   comparar com o gatilho de saída abaixo antes de decidir manter Free/Pro, migrar para Bunny ou usar
   R2 como origem.
5. **Verificar o teto de 10 Cache Rules do plano Free** antes de adicionar novas regras a outras
   frentes do produto (L2-L6 podem competir pelo mesmo orçamento de regras).

## Limites do plano Cloudflare Free citados na hipótese (não medidos aqui — citados do que a
Cloudflare publica; conferir a página oficial de preços/limites antes de comprometer decisão)

- Até **10 Cache Rules** por zona no plano Free.
- Purge por prefixo: até **100 prefixos por chamada** de API (mesmo teto que `cdn_simulada.py`
  reproduz localmente).
- Sem SLA contratual de cache/uptime no Free; "cache everything" ainda respeita os limites de
  tamanho de arquivo cacheável do plano (checar antes de servir ladrilho muito grande, ex.: banda
  científica de 16 bits sem compressão agressiva).

## Gatilho de saída do Cloudflare (Free/Pro) para Bunny ou R2-como-origem

A hipótese registra ~1 TB/mês de origem externa como o ponto em que o ToS do Cloudflare Free/Pro
passa a pesar (histórico de contas de CDN de mídia pesada sendo contatadas/limitadas; não é um
número technical hard-coded publicado com precisão por tier). **Não há tráfego de produção medido
ainda** — este item não gerou volume real, é a primeira vez que a rota de ladrilho existe. Decisão
de sair fica em aberto até o primeiro mês com número real:

- **Bunny.net**: PoPs no Brasil (menor latência do público-alvo do produto), suporte nativo a
  assinatura HMAC de URL (não é preciso hoje, porque o token já vai embutido no caminho — mas
  relevante se o contrato de URL mudar), preço por TB competitivo com tráfego pesado.
- **Cloudflare R2 como origem** (em vez de nginx/Garage direto): tira o egresso de banda do
  cálculo (R2 não cobra egresso para a própria Cloudflare), mas exige mover o objeto do Garage
  para o R2 ou servir o COG do R2 diretamente — mudança de arquitetura de armazenamento, fora do
  escopo deste item.

Decisão a registrar quando o número existir: `<mês> — <TB medidos> — <ação: manter | Bunny | R2>`.

## Faixa (range) de COG

Pedido de range HTTP num COG (leitura parcial, usada por clientes de imagem crua/científica) **não
passa pela CDN de ladrilho** — fica no cache `slice` do nginx de origem (já existente, fora do
escopo deste item; ver `deploy/nginx.conf` da origem para o cache de objetos do Garage). A CDN
descrita aqui só cobre o prefixo de ladrilho renderizado (`/svc/<token>/raster|mosaico/.../{z}/{x}/{y}`).

## Como reproduzir a prova localmente

```
set -a; source <arquivo .env da trilha>; set +a
cd <worktree>
venv/bin/python scripts/prova_cdn.py --porta-api 8274 --porta-cdn 8275 \
    --saida tests/medidas/L7-26-cdn-tiles.json
```

O script sobe a API de verdade e a CDN simulada em processos próprios, mede as cláusulas 1-4 do
portão contra sockets reais, roda as duas refutações e derruba os dois processos ao final (sucesso
ou falha). Não precisa de rede externa nem de conta Cloudflare.
