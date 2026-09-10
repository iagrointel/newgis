# 20260907T1919 — Metadado do fator do motor multicritério e teto de peso do proxy

Item `L3-15-metadado-fator`. Decisão A11 de `laco/decomposicao/L3L6_CONCEITO.md`.

## Contexto

O motor de linha de transmissão da casa (`rs-coop/tracado-lt/motor/pesos.py`) registra três coisas que o
esquema do modelo da plataforma declarava mas ninguém conferia: de que classe é cada peso (custo medido em
R$, apetite de risco, consequência normativa), se o peso tem âncora externa ou é escolha de quem decide, e
quais camadas medem uma grandeza DIFERENTE do gatilho — os proxies. Naquele motor, a camada de vegetação
nativa mede presença declarada, não supressão de árvore, e por isso o peso dela para em `TETO_PROXY = 0,60`
da escala: subir o peso de quem mede a coisa errada amplifica o erro em vez de corrigi-lo.

No esquema `amc_modelo.v1` os campos `proxy`, `classe_peso`, `ancora_peso` e `nao_sustenta` já existiam, mas
eram decorativos: nada lia `proxy.teto_peso`, e nenhum relatório dizia quais fatores eram proxy nem quais
pesos eram escolha.

## Decisão

1. **O teto de proxy limita a FATIA do peso, não um valor absoluto.** No motor de LT os pesos vivem numa
   escala fixa `[w_min, w_max]` e o teto é `w_min + 0,60 · (w_max − w_min)`. Aqui o peso é um multiplicador
   livre (≥ 0), então "fração da escala" não existe; o que existe é `peso_i / Σ pesos`, exatamente a fatia
   que a soma ponderada normalizada usa. Ela é invariante a multiplicar todos os pesos pelo mesmo número,
   que é a propriedade que a regra precisa ter para não ser burlada com uma mudança de unidade.
   Consequência declarada: um modelo cujo único fator é proxy sempre reprova, porque a nota da unidade fica
   inteiramente determinada por um dado que mede outra grandeza.
2. **A recusa vale nos dois lugares onde um peso entra**: no documento do modelo (`POST /api/amc/modelos`,
   `POST /api/amc/modelos/validar`) e nos pesos de uma execução, que podem sobrescrever os do modelo
   (`POST /api/amc/execucoes`). Barrar só no primeiro deixaria a porta dos fundos aberta — foi o primeiro
   ataque que o adversário deste item tentou.
3. **A recusa explica**: nomeia o fator, a fatia medida, o teto declarado, o que a camada mede de fato e
   qual peso caberia com os demais pesos mantidos. Erro que só diz "inválido" devolve o usuário ao mesmo
   lugar.
4. **`versao_fonte` entra como campo opcional**, não obrigatório. Obrigar a versão em todo fator recusaria
   modelos legítimos sobre camadas que não publicam edição; o preço da ausência é ficar nomeado na lista
   `fatores_sem_versao_de_fonte` do relatório. `fonte` e `base` seguem obrigatórios no JSON Schema.
5. **Campo ausente nunca vira valor.** A ficha devolve `null` e o resumo escreve "não declarado". A âncora
   ausente não é tratada como "escolhida": ela aparece em `ancoras.nao_declarada`, que é uma terceira coisa.

## Consequências

- `app/amc/metadado.py` é o único lugar que sabe o que é o teto e o que é a ficha; `esquema.py`,
  `relatorio.py` e `explicacao.py` chamam de lá.
- O relatório com `definicao` ganha o bloco `metadado` (fichas, proxies, âncoras); sem `definicao` ele
  continua igual ao que era, e não inventa metadado.
- A tela `/amc/explicacao/...` mostra a ficha no `?` de cada fator (elemento `details` nativo, sem
  biblioteca) e o cartão "proxies e âncoras".
- Quem quiser peso alto num fator proxy tem de tirar a marca de proxy — e aí responde pela declaração, que
  fica visível na ficha e no relatório. A regra não é um limite universal de peso.

## Alternativas descartadas

- **Teto sobre o peso absoluto** (`peso ≤ 0,6`): burlável multiplicando todos os pesos por 10.
- **Rebaixar o peso em silêncio** (o `min(w, teto)` do motor de LT): silencioso demais para uma API. O
  usuário digitaria 9 e receberia 1,5 sem saber; aqui ele recebe 422 dizendo por quê.
- **`versao_fonte` obrigatório**: recusaria camada sem edição publicada e empurraria o usuário a escrever
  qualquer coisa no campo, que é pior que o campo vazio e nomeado.
