# ADR — sistema de design único: tokens em duas camadas, componentes base, guia viva e guarda de literal (UX-01)

Data: setembro de 2026. Estado: aceito. Trilha de interface.

## Contexto

Nove telas nasceram em turnos diferentes com duas paletas (azul de sistema do T2 e o "instrumento" âmbar do L0-14,
ligado tela a tela por `body.instrumento`), cores e tamanhos literais espalhados em cinco folhas e nenhum componente
para estado vazio, carregando, erro ou negado. O alfa exige interface completa e polida; polimento sem fonte única de
verdade volta a divergir no turno seguinte.

## Decisão

1. `web/estilo/tokens.css` é a ÚNICA fonte de cor, tipo, espaço, raio, sombra e foco. Duas camadas: primitivos
   `--i-*` por tema (escuro padrão do produto; claro por `prefers-color-scheme` ou `data-theme`) e semânticos
   (`--fundo`, `--painel`, `--texto`, `--acento`, `--e0..--e6`, `--t-3..--t4`, `--raio`, `--sombra`, `--foco`...)
   que toda regra usa. O remapeamento por `body.instrumento` deixou de existir: todas as telas usam a identidade.
2. `web/style.css` importa os tokens e é a folha base de todas as telas; folhas de tela só acrescentam arranjo.
3. Componentes base como Custom Elements sem shadow DOM (L5 D1): `<plat-estado>` (vazio, carregando, erro com
   referência de suporte, negado), `<plat-toasts>` + `notificar()`, `<plat-painel>` (o chrome único de painel, o
   mesmo para cartão, painel do mapa e gaveta), `<plat-tema>` + `js/base/tema_cedo.js` (aplica a escolha antes da
   primeira pintura), somados a aviso, busca, paginação, tabela, formulário e diálogo que já existiam.
4. `/estilo-guia` renderiza toda variação com os tokens vivos e calcula a razão de contraste no navegador; o e2e
   roda o axe nos dois temas e prova que trocar um token muda três telas.
5. `docs/verificar_tokens.py` + `tests/unit/test_tokens_visuais.py`: cor literal ou tamanho literal de escala fora de
   tokens.css reprova; exceções em `web/estilo/tokens_excecoes.json`, uma por arquivo, com motivo (hoje só a
   cartografia do MapLibre, que lê JSON).
6. Tema em três estados (regra da casa): sistema, claro, escuro; a escolha vive em `localStorage plat_tema`.

## Consequências

- Ramo que acrescente folha com literal reprova a suíte rápida; a saída é usar o token ou declarar a exceção.
- O ajuste de contraste do acento claro (`#9a5a17`) foi medido pelo axe: o valor anterior falhava AA sobre âmbar
  preenchido.
- `scripts/servir_local.py` ganhou TLS opcional: escrita sob cookie exige `Origin` https igual a `PLAT_URL_PUBLICA`;
  o e2e de trilha roda contra `https://127.0.0.1:<porta>` com certificado autoassinado e o conftest ignora o erro de
  certificado só para hosts locais.
- Achado corrigido de passagem: `/admin/organizacao` nunca ficava pronta (`smtpAtual` na zona morta temporal do
  `let` depois do `await` de módulo).
