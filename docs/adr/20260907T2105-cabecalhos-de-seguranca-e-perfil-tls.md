# Cabeçalhos de segurança na aplicação, `frame-ancestors` por inquilino, TLS no nginx

- estado: aceito
- data: 2026-09
- item: L7-03-e-cabecalhos-csp-tls

## Contexto

Até aqui os cabeçalhos de segurança eram do nginx e eram os mesmos para toda rota: `X-Robots-Tag`,
`X-Content-Type-Options`, `X-Frame-Options: DENY`, `Referrer-Policy`, `Strict-Transport-Security`. Não
havia Content-Security-Policy. O relatório do Mozilla Observatory sobre a instalação pública, medido em
07/09/2026 antes deste item, deu **B (75 de 100), 11 de 12 exames passados** — a falta de CSP é o que
tira 25 pontos na versão 6 do algoritmo.

Duas coisas pedem que isso mude. A primeira é a CSP em si: sem ela, um nome de camada ou um texto de
popup com `<img onerror>` executa. A segunda é o produto: embutir o mapa no sítio do cliente é caso de
uso, e `X-Frame-Options` não sabe dizer "estas três origens sim, as demais não".

## Decisão

**1. O cabeçalho que depende da resposta nasce na aplicação; o que depende do transporte, no nginx.**
`add_header` do nginx acrescenta e nunca substitui, então cabeçalho declarado nos dois lugares sai em
dobro — foi o que já tinha acontecido com o `Cache-Control` no turno T2, e a decisão de lá se estende
aqui. Ficam na aplicação (`app/cabecalhos.py`, middleware mais externo): CSP, Permissions-Policy,
COOP, CORP, Referrer-Policy, `X-Content-Type-Options` e o CORS. Ficam no nginx: HSTS, `X-Robots-Tag`
e, em `/static/`, o conjunto inteiro, porque ali o nginx é a origem do corpo.

**2. `X-Frame-Options` sai; quem manda no embutir é `frame-ancestors`.** Ele aceita lista de origens e
tem precedência sobre o cabeçalho antigo nos navegadores atuais. A lista é do inquilino
(`plat.tenant.config -> 'origens_embutidas'`); sem lista a política sai `'none'` — a falta fecha.

**3. Nonce por resposta, não `'unsafe-inline'`.** As páginas de `web/` já não têm script em linha nem
tratador de evento em atributo, e um teste que lê os arquivos impede que voltem. O único script em linha
da casa é o de arranque da Swagger UI, que recebe o nonce da própria resposta.

**4. A leitura das origens vai por função `SECURITY DEFINER`.** O middleware monta o cabeçalho antes de
haver contexto de inquilino na conexão; sem a função, a RLS de `plat.tenant` devolveria zero linhas e a
política sairia sempre fechada, inclusive para quem autorizou. A função devolve um campo de configuração
de um inquilino — o mesmo valor que o cabeçalho publica em seguida.

**5. O CORS reusa a restrição que o token já tem.** `restricao.referer` existe desde o item L0-02 e já
barra a requisição cuja origem não está na lista. O CORS só ecoa a origem quando ela está nessa mesma
lista; nunca `*`, nunca credencial.

**6. O perfil TLS mora num arquivo próprio, de contexto http.** `deploy/nginx_tls.conf` não disputa com
as linhas que o certbot escreve no bloco do servidor. Perfil intermediate da Mozilla, com uma diferença
declarada: sem as cifras `DHE-*`, o que dispensa manter um `ssl_dhparam` e não perde cliente do alvo do
perfil.

## Consequências

- O `deploy/nginx.conf` e a aplicação passam a ser um par: instalados separados, ou saem cabeçalhos em
  dobro (nginx velho + app nova) ou faltam (nginx novo + app velha). O `install.sh` faz os dois.
- O que o Observatory ainda vai medir depende de o dono instalar: a nota B de 07/09 é da instalação
  ANTES deste item, e a de depois não foi medida por não existir instalação pública com este código.
- Um caminho novo que sirva HTML e não passe pelo middleware (por exemplo um `location` de nginx com
  `alias` para um HTML fora de `/static/`) sairia sem CSP. O teste que percorre o OpenAPI inteiro pega
  isso do lado da aplicação; do lado do nginx, quem pega é o teste que lê o `deploy/nginx.conf`.
- `frame-ancestors` depende de o inquilino ser conhecido na resposta. Quando a página redireciona para
  o login, o parâmetro `inquilino` tem de sobreviver ao salto — por isso `web/js/auth/sessao.js` passou
  a lê-lo da URL atual quando o `localStorage` está vazio, que é o caso de quem chega embutido.

## Alternativas descartadas

- **Manter tudo no nginx, com um `map` por inquilino.** O nginx não conhece o inquilino da requisição
  sem consultar o banco, e o nonce por resposta exigiria `ngx_http_sub_module` reescrevendo o corpo.
- **`Content-Security-Policy-Report-Only` primeiro.** Não haveria como recolher o relatório sem uma
  rota nova que aceita POST de qualquer origem; e a varredura dos arquivos de `web/` já mostrou que não
  há script em linha para quebrar.
- **`style-src 'unsafe-inline'` por precaução.** Medido no navegador: a Swagger UI e o MapLibre desenham
  com `style-src 'self'`, porque escrevem estilo por CSSOM, que a CSP não governa.
