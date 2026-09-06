"""Relatório de inventário do Portal/AGOL (item L2-08-a-leitor-portal-inventario): a mesma leitura em duas
formas, o resumo que a tela mostra e o CSV que o cliente abre na planilha.

O CSV é escrito com `csv.writer` (aspas e vírgula tratadas pela biblioteca padrão) e sai com BOM UTF-8,
porque o destinatário abre o arquivo no Excel em português e sem o BOM os acentos chegam trocados. Uma linha
por item; nenhuma coluna de dado pessoal (dono é LOGIN, nunca e-mail ou nome completo)."""

import csv
import io

COLUNAS = (
    ("item_esri_id", "id do item no portal"),
    ("titulo", "título"),
    ("tipo", "tipo Esri"),
    ("classificacao", "classificação"),
    ("classificacao_motivo", "motivo da classificação"),
    ("dono_login", "dono (login)"),
    ("tamanho_bytes", "tamanho declarado (bytes)"),
    ("contagem_total", "feições contadas"),
    ("num_camadas", "camadas e tabelas"),
    ("num_dependencias", "dependências"),
    ("num_visualizacoes", "visualizações"),
    ("modificado_esri_em", "modificado em"),
    ("ultimo_acesso_em", "último acesso"),
    ("url", "url do serviço"),
)


def _texto(valor) -> str:
    if valor is None:
        return ""
    return str(valor)


def csv_de_itens(linhas) -> bytes:
    """CSV do inventário. `linhas` são dicionários vindos de `plat.migracao_item`."""
    buffer = io.StringIO(newline="")
    escritor = csv.writer(buffer, delimiter=";", quoting=csv.QUOTE_MINIMAL, lineterminator="\r\n")
    escritor.writerow([rotulo for _, rotulo in COLUNAS])
    for linha in linhas:
        registro = dict(linha)
        registro["num_camadas"] = len(registro.get("camadas") or [])
        registro["num_dependencias"] = len(registro.get("dependencias") or [])
        escritor.writerow([_texto(registro.get(campo)) for campo, _ in COLUNAS])
    return b"\xef\xbb\xbf" + buffer.getvalue().encode("utf-8")


def resumo_por_tipo(linhas) -> list[dict]:
    """Uma linha por tipo Esri: quantos itens, quantas feições, quantos bytes, e a classificação (que é
    sempre a mesma dentro de um tipo, salvo quando `typeKeywords` separa hospedado de não hospedado — por
    isso a classificação sai como CONTAGEM por classe, nunca como rótulo único do tipo)."""
    por_tipo: dict[str, dict] = {}
    for linha in linhas:
        tipo = linha.get("tipo") or "(sem tipo)"
        alvo = por_tipo.setdefault(tipo, {"tipo": tipo, "itens": 0, "feicoes": 0, "bytes": 0, "classes": {}})
        alvo["itens"] += 1
        alvo["feicoes"] += int(linha.get("contagem_total") or 0)
        alvo["bytes"] += int(linha.get("tamanho_bytes") or 0)
        classe = linha.get("classificacao") or "desconhecido"
        alvo["classes"][classe] = alvo["classes"].get(classe, 0) + 1
    return sorted(por_tipo.values(), key=lambda r: (-r["itens"], r["tipo"]))
