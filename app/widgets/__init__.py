"""Widgets externos por inquilino (item L5-36-widgets-personalizados-sdk).

O SDK do parceiro: o widget é um pacote de 3 arquivos (manifesto.json, modulo.js, i18n.json) instalado pelo
admin do inquilino via API, guardado em `plat.widget_externo` (RLS por inquilino) e servido same-origin por
`/api/widgets/externos/{nome}/modulo.js` com o sha256 gravado na instalação — o carregador do navegador
(`web/js/widgets/externos.js`) só registra o manifesto depois de reconferir o hash, e widgets marcados
`sandbox: true` rodam em iframe `sandbox="allow-scripts"` com ponte postMessage (`web/js/widgets/sandboxe.js`).

Regras escritas (uma por constante/função):

- `api_widget` é um contrato de versão: manifesto com valor diferente de 1 é RECUSADO na instalação (422
  nomeando o widget) e ACUSADO pelo verificador que roda no `make check` (tests/unit/test_widget_externo_check.py).
- o código do widget tem teto (`LIMITE_MODULO_BYTES`): widget não é aplicação, é elemento de painel;
- as chaves de i18n do pacote têm de vir sob o prefixo do próprio widget (`manifesto.i18n + '.'`) — um
  pacote nunca sobrescreve chave de tradução da casa nem de outro widget;
- origem registrada: sem sandbox, o widget corre na página — a instalação guarda quem instalou, e o GET do
  módulo (que é quando o código corre) passa pelo log de acesso com o nome no caminho (refutação do item).
"""
