# Exemplos executáveis da API do plat (item L7-08-d)

Vinte programas, dez em Python e dez em JavaScript, que rodam de verdade contra uma instalação do plat.
São os mesmos arquivos que o portal `/portal` mostra: o portal os lê deste diretório, não guarda cópia.

Duas variáveis de ambiente, iguais nos vinte:

- `PLAT_URL` — endereço da API, sem barra no fim. Sem ela, `http://127.0.0.1:8153`.
- `PLAT_CHAVE` — chave de API (`plat_...`), criada em `POST /api/tokens` sob sessão. Os exemplos que só
  leem pedem uma chave de perfil `leitura` (escopos `catalogo:ler`, `camada:ler`, `tiles:ler`).

Rodar um:

    PLAT_URL=https://exemplo PLAT_CHAVE=plat_... python3 exemplos/python/01_versao.py
    PLAT_URL=https://exemplo PLAT_CHAVE=plat_... node exemplos/js/01_versao.mjs

Cada programa termina com código 0 quando o que ele afirma acontece, e com código 1 escrevendo o motivo
em `stderr` quando não acontece. Nenhum depende de biblioteca de terceiro: Python usa só a biblioteca
padrão (`urllib`), JavaScript usa o `fetch` nativo do Node 18 ou mais novo.

Os exemplos `09` e `10` são deliberadamente exemplos de RECUSA: o 09 prova que uma chave de leitura não
escreve, o 10 prova o formato de erro (RFC 9457). Eles terminam com 0 quando a recusa acontece.
