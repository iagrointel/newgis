# Log de correções — CVE conhecido

Gerado por `docs/gerar_correcoes.py` (`make correcoes`) a partir de `plat.vulnerabilidade` — item L7-03-f-dependencias-cve-log-correcoes; não editar à mão. Uma linha por achado de `scripts/varredura_cve.py` (pip-audit em `requirements.txt`, npm audit em `web/vendor/VERSOES.txt`); `resolvida` fica vazio enquanto o achado segue aberto e ganha data no instante em que ele some de uma varredura para a próxima (nunca apagado — histórico completo).

Fonte desta geração: banco (plat.vulnerabilidade).

Última varredura: 2026-09-15 22:59 — **falhou** — pip-audit: falhou (pip-audit não devolveu JSON: ); npm-audit: 4 achado(s)

**4 achado(s)** no log · **4 aberto(s)** agora.

| aviso | pacote | versão | gravidade | detectada | resolvida |
|---|---|---|---|---|---|
| `GHSA-px8p-9vwx-vf98` | `fflate` | `>=0.7.0 <0.7.5` | média | 2026-09-15 22:59 | — |
| `GHSA-w3rx-r6r6-pgpr` | `image-size` | `<=2.0.2` | alta | 2026-09-15 22:59 | — |
| `GHSA-5p2g-fcmc-qvqq` | `image-size` | `<=2.0.2` | alta | 2026-09-15 22:59 | — |
| `GHSA-jrc7-96c5-q579` | `maplibre-gl` | `<=6.4.0` | crítica | 2026-09-15 22:59 | — |
