# Manual — widget externo do inquilino (item L5-36)

Para quem desenvolve um widget fora da casa (parceiro ou equipe do próprio inquilino) e quer vê-lo rodando
na página `/aplicativo` do inquilino. O roteiro foi desenhado para caber em 60 min com leitura; o
cronômetro com um testador de verdade ainda não correu — primeira pessoa que seguir o passo a passo deve
registrar o tempo que levou neste arquivo.

## O pacote

Uma pasta com três arquivos:

```
meu-widget/
  manifesto.json   # quem é o widget e o que fala
  meu-widget.js    # o código (um único arquivo, ≤ 256 kB)
  i18n.json        # opcional: textos do widget
```

`manifesto.json` (todas as chaves são obrigatórias):

```json
{
  "nome": "meu-widget",
  "versao": "1.0.0",
  "api_widget": 1,
  "modulo": "./meu-widget.js",
  "elemento": "plat-meu-widget",
  "esquema_config": {"type": "object", "additionalProperties": false, "properties": {}},
  "eventos": [],
  "acoes": [],
  "fontes": {"min": 0, "max": 0, "tipos": []},
  "i18n": "widget.meu-widget"
}
```

Regras que a instalação recusa se você errar (mensagem nomeia o campo):

* `nome`: minúsculas, dígitos e hífen, começando por letra (3 a 40 caracteres).
* `elemento`: começa com `plat-`.
* `versao`: semver `MAIOR.MENOR.REMENDO`.
* `api_widget`: tem de ser `1` — outro valor é recusado com `api_widget_incompativel` (atualize o pacote).
* `modulo`: relativo, forma `./arquivo.js`. O código é sempre servido pelo próprio servidor; URL de
  terceiro não entra.
* `eventos`/`acoes`: os nomes que o widget fala e escuta. O portão do motor só deixa passar o que está
  aqui — se o widget emite `meu-widget.pronto`, este nome precisa estar em `eventos`.
* `esquema_config`: JSON Schema da configuração do nó (o mesmo validador dos widgets da casa).
* `i18n`: prefixo das chaves do `i18n.json`. Toda chave precisa começar com esse prefixo — chave fora do
  namespace é recusada (`i18n_invalido`), porque pacote nenhum sobrescreve tradução da casa.

## O código — dois modos

**Sandbox (padrão para código de terceiro — use este).** O widget corre num iframe de origem opaca, sem
rede e sem cookie. Ele fala com a página por `window.plat`:

```js
window.plat.registrar({
  montar(raiz) {
    const p = document.createElement('div');
    p.textContent = window.plat.configuracao.rotulo || 'olá';
    raiz.append(p);
  },
  acao(nome, detalhe) {           // ações declaradas no manifesto chegam aqui
    if (nome === 'definir_parametro') { /* ... */ }
  },
});
// para falar com a página:
window.plat.emitir('meu-widget.pronto', { ok: true });   // precisa estar em manifesto.eventos
```

Dentro do sandbox não existe `fetch` para a API (o CSP embute `connect-src 'none'`), não existe
`document.cookie` (lança `SecurityError`) e não existe import de módulo. Dados chegam pela configuração e
pelas ações; resultados saem por `emitir`. O exemplo completo da casa é
`web/ext/exemplo/semaforo/semaforo.js` (~30 linhas).

**Modo normal (só para código auditado pela casa).** O módulo corre na própria página e define um custom
element com a base da casa:

```js
import { PlatWidget, definir } from '/static/js/widgets/base.js';
class PlatMeuWidget extends PlatWidget {
  renderizar() { /* this.configuracao, this.emitir(nome, detalhe), this.executar */ }
}
definir('plat-meu-widget', PlatMeuWidget);
```

Só import absoluto `/static/js/...` — o módulo é um arquivo só, sem import relativo.

## Instalar

Empacote a pasta em JSON (só biblioteca padrão) e poste como admin do inquilino:

```bash
python3 scripts/widget_empacotar.py web/ext/exemplo/semaforo > pacote.json
curl -b cookies.txt -H 'Content-Type: application/json' --data @pacote.json \
     https://<host>/api/widgets/externos
```

* Quem instala precisa do privilégio `org.configurar` e de sessão de navegador (token de API não instala).
* O servidor calcula o sha256 do módulo e devolve na resposta. Guarde-o: é o compromisso do conteúdo.
* Reinstalar com o mesmo `nome` atualiza (versão nova, hash novo).
* O navegador reconfere o sha256 do texto baixado antes de o código correr — módulo adulterado no caminho
  é recusado com aviso na página, e o widget não monta.
* `GET /api/widgets/externos` lista o instalado (sem o código); `DELETE
  /api/widgets/externos/<nome>` desinstala (fica no log da organização).

## Usar no aplicativo

No construtor de aplicativos o widget aparece como um tipo de nó igual aos da casa (o `nome` do manifesto
é o tipo). Configure `configuracao` conforme o `esquema_config`, ligue eventos de outros widgets às ações
do seu (`acoes`) e salve. `sandbox: true` monta o hospedeiro `<plat-widget-sandboxe>`; a origem do código
fica à vista no atributo `data-widget-origem` do iframe (nome, versão, sha256).

## Checklist antes de enviar o pacote

1. `python3 scripts/widget_empacotar.py <pasta>` roda sem erro e o JSON contém os três arquivos.
2. `manifesto.api_widget` é 1 e cada evento/ação que o código usa está declarado.
3. Toda chave do `i18n.json` começa com o prefixo `manifesto.i18n.`.
4. Em sandbox: nada de fetch/import/cookie no código; tudo por `window.plat`.
5. Testado num aplicativo do próprio inquilino antes do envio.
