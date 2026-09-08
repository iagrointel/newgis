# ADR 20260908T2125 — /saude marca o Garage como serviço obrigatório (achado G4-19 do item L0-11)

Contexto: o portão do L0-11-arquivos-objetos diz "/saude marca garage como obrigatório a partir deste
item (ADR novo)". A varredura adversarial G4 (`wt/adv4`) registrou o achado G4-19: `app/saude.py`
decidia o status HTTP só pelo banco (`200 if banco == "ok" else 503`); com o Garage inalcançável a
plataforma continuava respondendo 200 "saudável" com `servicos["garage"] == "erro"` — a sonda existia
só como informativo, então uma instalação sem onde guardar objetos se declarava sadia. O comentário em
`app/settings.py` ("garage vira obrigatório a partir deste item (saude.py)") descrevia a intenção; a
regra nunca tinha sido implementada.

## Decisão

`/saude` passa a responder **503 quando um serviço obrigatório está configurado e não responde**, além
do caso de banco desatualizado/erro. A lista dos obrigatórios é a constante `OBRIGATORIOS = ("garage",)`
em `app/saude.py` e também sai no corpo da resposta (`servicos_obrigatorios`), para o leitor do JSON
saber por que um 503 veio com `"banco": "ok"`.

Regra exata: para cada nome em `OBRIGATORIOS`, se a URL está configurada em `settings.servicos()` e o
sonda não devolveu `"ok"`, a instalação está doente. O sonda do Garage já considera `ok` qualquer
resposta abaixo de 500 — o Garage responde 403 sem assinatura para quem só pergunta se ele está de pé,
e isso é saúde, não erro.

## Fronteira (declarada, não escondida)

- **Sem `PLAT_GARAGE_URL` configurada**: o sonda devolve `"ausente"` e o status NÃO é afetado — é o modo
  de desenvolvimento sem objetos. Obrigatório se aplica a instalação que DECLARA o serviço e não o tem.
  (Em produção a chave é exigida pelo instalador do item; torná-la `_obrigatoria` em `settings` é
  decisão separada, que quebraria toda trilha de teste sem Garage.)
- **martin, titiler e worker continuam informativos**: indisponíveis não derrubam o 200. O worker vivo
  já é conferido por `plat.fila_estado()` na mesma resposta (teste exige `workers_vivos >= 1`).

## Prova

`tests/api/test_g4_adversario.py::test_saude_reprova_quando_o_garage_esta_fora` nasceu como
`xfail(strict=True)` apontando o defeito; com esta decisão o marcador sai e o teste vale como portão:
Garage sondado como `erro` com URL configurada → 503. A fronteira ganhou o teste complementar
`test_saude_200_quando_garage_ausente` (sem URL configurada → 200 com `"ausente"`), e o contrato do
corpo (`tests/api/test_saude.py::CAMPOS`) passou a exigir `servicos_obrigatorios == ["garage"]`.
