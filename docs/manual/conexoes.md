---
id: conexoes
titulo: Conexões
titulo_en: Connections
titulo_es: Conexiones
resumo: "conexões externas de dados: teste de saúde, histórico de disponibilidade e publicação de camada"
resumo_en: "external data connections: health test, availability history and layer publication"
resumo_es: "conexiones externas de datos: prueba de salud, historial de disponibilidad y publicación de capa"
classe: tela
pagina: conexoes.html
caminho: /conexoes
e2e: tests/e2e/test_conexoes.py
captura: L6-02-l-saude_lista_nunca_testada.png
e2e_captura: capturar("lista_nunca_testada")
palavras: [conexoes, externa, saude, historico, wms, wfs, ogc, publicar, camada]
palavras_en: [connections, external, health, history, wms, wfs, ogc, publish, layer]
palavras_es: [conexiones, externa, salud, historico, wms, wfs, ogc, publicar, capa]
---

## Conexões

A tela Conexões registra fontes externas de dados (WMS, WFS, API OGC e afins) e vigia a saúde delas.

### Registrar e testar

1. Escolha Nova conexão: nome, URL e tipo.
2. O servidor valida a URL contra as defesas de rede (endereços internos e de link local são
   recusados) e testa a conexão na hora.
3. A lista marca a última teste: nunca testada, em ordem ou fora do ar.

### Histórico e publicação

Cada conexão tem histórico de disponibilidade (as últimas testes com instante e resultado) e, para
fontes de camada, a ação Publicar cria um item de catálogo que serve a camada com procedência: o
item aponta a origem, o instante da carga e o estado da fonte.

A captura desta seção é produzida pelo teste de ponta a ponta da própria tela
(`tests/e2e/test_conexoes.py`) contra a versão atual.
