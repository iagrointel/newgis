"""Rede de utilidades (linha L4): o esquema da rede é DADO, não código.

Um PACOTE DE ATIVOS é um documento JSON versionado que descreve, para uma disciplina (elétrica, água, gás,
esgoto, telecom), as redes de domínio, os tiers, os grupos e tipos de ativo, as categorias de rede, os
atributos e as configurações de terminal. O pacote é importado para as tabelas `plat.rede_*` do inquilino e
exportado de volta a partir delas — é essa ida e volta que permite levar o mesmo esquema de um inquilino para
outro sem código novo. O primeiro item da linha (L4-01-a) entrega o formato, as tabelas, a validação e dois
pacotes prontos; o traçado, a topologia e a edição são itens seguintes."""
