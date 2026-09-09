# ADR 20260907T1642 — sprite por inquilino é composto pela própria API, não servido cru pelo Martin

Item: `L2-02-e-simbolos-sprites-glifos` (linha L2 plataforma).

## Contexto

O portão de pronto do item exige que "ícone novo aparece no sprite em ≤ 5 s sem reinício". A hipótese
original do item propunha servir o sprite direto do Martin, com "fonte de sprites por diretório do
inquilino". O binário já está instalado nesta máquina (`/usr/local/bin/martin`, v1.15.0) e o Martin
de fato sabe servir sprite (`--sprite <dir>`, formato `sprite.json`/`sprite.png` compatível com o
`spec` do MapLibre) — mas com uma condição que muda a decisão.

## Medição (07/09/2026)

Reproduzido com o binário real, sem código nosso, dentro do worktree:

```
mkdir -p /tmp/msprite_test2/base
# 1 SVG em base/casa.svg
martin --sprite /tmp/msprite_test2 --listen-addresses 127.0.0.1:39003 &
curl http://127.0.0.1:39003/sprite/msprite_test2.json
# -> {"base/casa": {...}}
# acrescenta base/arvore.svg AO VIVO, sem reiniciar o processo
curl http://127.0.0.1:39003/sprite/msprite_test2.json
# -> {"base/casa": {...}}   (arvore NÃO aparece — mesmo catálogo da primeira chamada)
```

O Martin lê o diretório de sprites **uma vez, na subida do processo**, e não tem opção de linha de
comando nem endpoint HTTP para recarregar o catálogo (conferido em `martin --help`: não há `--watch`,
`--reload`, sinal documentado nem rota de administração). Não é um defeito do Martin — ele foi desenhado
para um catálogo de sprites estático, publicado no deploy, igual às camadas de tile.

## Decisão

1. **Sprite por inquilino é composto pela nossa API** (`app/simbolos/sprite.py`), no MESMO formato que
   o MapLibre consome do Martin (`sprite.json` com `{nome: {width,height,x,y,pixelRatio}}` + `sprite.png`
   com o atlas, 1x e 2x) — o cliente (MapLibre GL) não percebe diferença nenhuma; só troca quem gera.
   Composição sob demanda, cacheada por uma **versão** (contagem + carimbo do upload mais recente do
   inquilino, uma consulta rápida ao Postgres): um upload novo muda a versão na hora, então a PRÓXIMA
   leitura já compõe o sprite atualizado. Medido: compor os 163 itens embutidos (153 ícones + 10 padrões)
   nos dois fatores de escala leva **0,24 s** nesta máquina (`0,097 s` 1x + `0,145 s` 2x, medidas
   `composicao_atlas_1x_s`/`composicao_atlas_2x_s` de `tests/medidas/L2-02-e-simbolos-sprites-glifos.json`,
   gravadas por `tests/api/test_simbolos.py::test_medidas_do_portao`) — bem dentro dos 5 s do portão. O
   caminho completo que o portão cobra, do POST do ícone até ele aparecer no `sprite.json` pelo HTTP, foi
   medido de ponta a ponta em **0,271 s** (`upload_ate_aparecer_no_sprite_s`), com a máquina sob carga
   12,38 e 0,4 GiB livres — ou seja, passa com folga de mais de 18x mesmo na pior condição da casa.
2. **Os glifos de fonte continuam vindo do Martin de verdade** (`app/simbolos/fontes.py`): fontes
   embutidas (Noto Sans, Open Sans) nunca mudam em runtime, então a limitação acima não se aplica —
   não existe cláusula de "fonte nova em ≤ 5 s" no portão, só de ícone. Rodar um Martin dedicado (config
   `deploy/martin_simbolos.yaml`, unidade `deploy/plat-martin-simbolos.service`) para servir só
   `/font/{fontstack}/{inicio}-{fim}.pbf` é a solução mais simples que já reusa o binário instalado.
3. Namespacing evita a colisão de nome: um upload do inquilino entra no sprite como `personalizado/<nome>`,
   nunca como `<nome>` cru — um ícone chamado igual a um da base (`energia-raio`, por exemplo) não
   sobrescreve nem é sobrescrito, os dois aparecem lado a lado no mesmo sprite (é a defesa contra a
   refutação "sobe SVG com o mesmo nome de um ícone padrão").

## Consequência

O sprite não é gerado por um processo Martin isolado por inquilino (o que também custaria uma porta e um
processo por inquilino, sem necessidade). A composição é uma função pura sobre bytes já em memória/Postgres
(o SVG do upload cabe direto numa coluna `text`, ver `db/migracoes/20260907T1642_simbolo_upload.sql`), sem
necessidade de tocar disco por requisição. Se um dia a base de ícones crescer a ponto de a composição sob
demanda pesar, a mesma função vira um job de fundo que escreve `sprite.png` pronto num objeto do Garage
(item L0-11) — não muda o contrato HTTP visto pelo MapLibre.
