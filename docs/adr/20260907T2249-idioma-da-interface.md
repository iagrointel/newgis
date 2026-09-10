# ADR — idioma da interface: resolução no cliente, dicionários com paridade, preferência da conta (UX-02)

Data: setembro de 2026. Estado: aceito. Trilha de interface; base do L7-10-a.

## Contexto
`PUT /api/eu` já gravava `idioma_preferido` (pt-BR, en, es), mas a tela não o seguia e só existia `pt-BR.json`.

## Decisão
1. Dicionários `web/js/i18n/{pt-BR,en,es}.json` com o MESMO conjunto de chaves e as mesmas variáveis por chave
   (`tests/unit/test_i18n_paridade.py` reprova divergência). pt-BR é a referência; chave ausente no idioma cai para o
   pt-BR (nunca chave crua por tradução atrasada).
2. Resolução no cliente (`js/base/i18n.js`), do mais ao menos específico: `?idioma=` > `localStorage plat_idioma` >
   `<html lang>` fora do padrão > `navigator.languages` > pt-BR. A preferência gravada na conta é aplicada por
   `exigirSessao` e lembrada em `plat_idioma`, valendo também nas telas públicas depois.
3. `<plat-idioma>` nas telas públicas troca o dicionário sem recarregar; textos montados por código re-traduzem por
   `aoTraduzir`/`plat:i18n`. Nome de cada idioma no próprio idioma.
4. `ORG_IDIOMAS` e `PERFIL_IDIOMAS` só nomeiam idiomas com arquivo (teste); documento `docs/LIMITES.md` regenerado.

## Consequências
- Chave nova entra nos três arquivos no mesmo commit; a suíte rápida barra o esquecimento.
- Mensagens vindas da API continuam em português (contrato da API); o L7-10-a decide se a API negocia idioma.
