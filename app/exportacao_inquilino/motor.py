"""Monta o pacote de exportação COMPLETA do inquilino (item L0-06-d-exportar-inquilino).

O pacote final é um zip com quatro componentes:

- `dados.gpkg` — um GeoPackage com uma camada por item `camada_vetorial` hospedado, gerado por `ogr2ogr`
  chamado uma vez por camada (mesma disciplina de segurança de `app.exportacao.motor`: o inquilino entra na
  string de conexão, `-c plat.tenant_id=N`, e a RLS da tabela faz o resto — nada de WHERE escrito à mão);
- `catalogo.json` — itens, pastas, grupos, compartilhamentos, relações e usuários SEM `senha_hash`/segredo de
  2FA/código de recuperação, no formato descrito em `docs/esquemas/exportacao_inquilino.schema.json`;
- `arquivos.zip` — os objetos do bucket (item `arquivo`, miniaturas, logotipo) baixados do Garage e zipados
  por item, um arquivo por item dentro do zip (nome = `<item_id><extensao>`);
- `manifesto.json` — sha256 e tamanho de cada um dos três componentes acima, mais o sha256 do próprio
  `catalogo.json` calculado ANTES de entrar no zip (o teste do portão confere os dois).

Nenhum componente é montado inteiro em memória além do necessário para escrever um JSON de catálogo (que já é
pequeno: só metadado, nunca geometria nem conteúdo de arquivo)."""

from __future__ import annotations

import hashlib
import json
import subprocess
import zipfile
from pathlib import Path

from app.exportacao import motor as motor_camada
from app.exportacao.formatos import obter as formato_de

CAMPOS_USUARIO_PUBLICOS = (
    "id", "login", "nome", "email", "perfil", "superadmin", "ativo", "papel_id",
    "origem", "idioma_preferido", "criado_em",
)


class ErroExportacaoInquilino(Exception):
    """Falha que o admin pode corrigir ou que é do próprio inquilino (nunca do código)."""


def _linha(r: dict, campos: tuple[str, ...]) -> dict:
    saida = {}
    for c in campos:
        v = r.get(c)
        saida[c] = v.isoformat() if hasattr(v, "isoformat") else v
    return saida


def montar_catalogo(cur, tenant_id: int) -> dict:
    """Lê o inquilino inteiro sob RLS (o `cur` já está no contexto do inquilino) e devolve o dict que vira
    `catalogo.json`. `usuarios` NUNCA carrega `senha_hash`, `totp_secret`, `codigos_recuperacao` nem
    `desafio_2fa_hash` — a exportação é para o cliente, não é um backup de autenticação."""
    cur.execute(
        "SELECT id, tipo, titulo, resumo, descricao, tags, dono_id, pasta_id, dados, acesso, status, "
        "origem, tamanho_bytes, criado_em, criado_por, modificado_em FROM plat.item "
        "WHERE apagado_em IS NULL ORDER BY criado_em"
    )
    itens = []
    for r in cur.fetchall():
        r = dict(r)
        r["id"] = str(r["id"])
        r["pasta_id"] = str(r["pasta_id"]) if r["pasta_id"] else None
        for campo in ("criado_em", "modificado_em"):
            r[campo] = r[campo].isoformat() if r[campo] else None
        itens.append(r)

    cur.execute("SELECT id, pai_id, nome, dono_id, criado_em FROM plat.pasta ORDER BY profundidade, criado_em")
    pastas = []
    for r in cur.fetchall():
        r = dict(r)
        r["id"] = str(r["id"])
        r["pai_id"] = str(r["pai_id"]) if r["pai_id"] else None
        r["criado_em"] = r["criado_em"].isoformat()
        pastas.append(r)

    cur.execute(
        "SELECT id, nome, resumo, visibilidade, entrada, contribuicao, dono_id, criado_em FROM plat.grupo "
        "ORDER BY criado_em"
    )
    grupos = []
    for r in cur.fetchall():
        r = dict(r)
        r["id"] = str(r["id"])
        r["criado_em"] = r["criado_em"].isoformat()
        cur.execute(
            "SELECT usuario_id, papel, estado FROM plat.grupo_membro WHERE grupo_id = %s::uuid", (r["id"],)
        )
        r["membros"] = [dict(m) for m in cur.fetchall()]
        cur.execute("SELECT item_id FROM plat.item_grupo WHERE grupo_id = %s::uuid", (r["id"],))
        r["itens"] = [str(m["item_id"]) for m in cur.fetchall()]
        grupos.append(r)

    cur.execute(
        "SELECT id, item_id, prefixo, nome, criado_em, expira_em, permite_download, revogado_em "
        "FROM plat.compartilhamento_link ORDER BY criado_em"
    )
    compartilhamentos = []
    for r in cur.fetchall():
        r = dict(r)
        r["id"] = str(r["id"])
        r["item_id"] = str(r["item_id"])
        for campo in ("criado_em", "expira_em", "revogado_em"):
            r[campo] = r[campo].isoformat() if r[campo] else None
        compartilhamentos.append(r)

    cur.execute("SELECT origem, destino, tipo, posicao FROM plat.item_relacao ORDER BY origem, tipo")
    relacoes = [
        {"origem": str(r["origem"]), "destino": str(r["destino"]), "tipo": r["tipo"], "posicao": r["posicao"]}
        for r in cur.fetchall()
    ]

    cur.execute(
        "SELECT id, login, nome, email, perfil, superadmin, ativo, papel_id, origem, idioma_preferido, "
        "criado_em FROM plat.usuario ORDER BY id"
    )
    usuarios = [_linha(dict(r), CAMPOS_USUARIO_PUBLICOS) for r in cur.fetchall()]

    return {
        "versao_esquema": 1,
        "tenant_id": tenant_id,
        "itens": itens,
        "pastas": pastas,
        "grupos": grupos,
        "compartilhamentos": compartilhamentos,
        "relacoes": relacoes,
        "usuarios": usuarios,
    }


def _nome_camada_seguro(item_id: str) -> str:
    return "c_" + item_id.replace("-", "")


def gerar_gpkg(cur, tenant_id: int, catalogo: dict, destino: Path, executar=None) -> int:
    """Um GeoPackage com uma camada por item `camada_vetorial` de `dados.fonte == 'hospedada'`. Devolve o
    número de camadas escritas (0 quando o inquilino não tem nenhuma — o portão aceita N=0)."""
    rodar = executar or (lambda a: subprocess.run(a, capture_output=True, text=True, timeout=1800))
    n = 0
    for item in catalogo["itens"]:
        if item["tipo"] != "camada_vetorial":
            continue
        dados = item.get("dados") or {}
        if dados.get("fonte") != "hospedada":
            continue
        schema, tabela = dados.get("schema"), dados.get("tabela")
        if not (schema and tabela):
            continue
        campos = [c["nome"] for c in (dados.get("campos") or [])]
        srid_tabela = int(dados.get("srid") or 4326)
        sql = motor_camada.montar_select(
            cur, schema=schema, tabela=tabela, campos=campos, coluna_geom="geom", where=None, bbox=None,
            srid_tabela=srid_tabela,
            colunas_brancas=motor_camada.colunas_permitidas(dados.get("campos") or []),
        )
        conninfo = motor_camada.conninfo_pg(tenant_id)
        nome_camada = _nome_camada_seguro(item["id"])
        argv = ["ogr2ogr", "-f", "GPKG"]
        if n > 0:
            argv.append("-update")
        argv += [str(destino), conninfo, "-sql", sql, "-nln", nome_camada]
        r = rodar(argv)
        if r.returncode != 0:
            avisos = [ln for ln in (r.stderr or "").splitlines() if ln.strip()]
            raise ErroExportacaoInquilino(
                f"ogr2ogr falhou na camada {item['titulo']!r}: {(avisos[-1] if avisos else 'sem detalhe')[:300]}"
            )
        n += 1
    if n == 0:
        # GeoPackage vazio mas válido (SQLite com as tabelas gpkg_* e zero camadas de usuário): cria uma
        # camada de um GeoJSON vazio e a apaga em seguida — o teste do portão só exige "N camadas do
        # catálogo", e N=0 é um catálogo sem camada hospedada, não um erro.
        temp_geojson = destino.parent / "_vazio.geojson"
        temp_geojson.write_text('{"type": "FeatureCollection", "features": []}', encoding="utf-8")
        r = rodar(["ogr2ogr", "-f", "GPKG", str(destino), str(temp_geojson), "-nln", "_vazio"])
        if r.returncode != 0:
            raise ErroExportacaoInquilino("não foi possível criar o GeoPackage vazio")
        rodar(["ogrinfo", str(destino), "-sql", "DROP TABLE _vazio"])
        temp_geojson.unlink(missing_ok=True)
    return n


def gerar_arquivos_zip(catalogo: dict, destino: Path, ler_stream) -> int:
    """Zip com um arquivo por item que tem `dados.chave` (upload/arquivo/logotipo/miniatura de item), lido do
    Garage em blocos (`ler_stream`, injetado para o teste não depender do bucket real)."""
    n = 0
    with zipfile.ZipFile(destino, "w", zipfile.ZIP_DEFLATED) as z:
        for item in catalogo["itens"]:
            dados = item.get("dados") or {}
            chave = dados.get("chave")
            if not chave:
                continue
            extensao = Path(dados.get("nome_original") or "").suffix or ""
            nome_interno = f"{item['id']}{extensao}"
            with z.open(nome_interno, "w") as f:
                for bloco in ler_stream(chave):
                    f.write(bloco)
            n += 1
    return n


def sha256_arquivo(caminho: Path) -> str:
    h = hashlib.sha256()
    with open(caminho, "rb") as f:
        for bloco in iter(lambda: f.read(8 * 1024 * 1024), b""):
            h.update(bloco)
    return h.hexdigest()


def sha256_bytes(dados: bytes) -> str:
    return hashlib.sha256(dados).hexdigest()


def montar_manifesto(componentes: dict[str, Path], sha256_catalogo: str) -> dict:
    manifesto = {"versao": 1, "componentes": {}}
    for nome, caminho in componentes.items():
        manifesto["componentes"][nome] = {
            "sha256": sha256_arquivo(caminho),
            "bytes": caminho.stat().st_size,
        }
    manifesto["componentes"]["catalogo.json"]["sha256_conteudo"] = sha256_catalogo
    return manifesto


def empacotar(destino_zip: Path, componentes: dict[str, Path]) -> None:
    """Zip final com os quatro arquivos (dados.gpkg, catalogo.json, arquivos.zip, manifesto.json) na raiz —
    lido do disco em blocos pelo próprio `zipfile.write`, nunca montado inteiro em memória."""
    with zipfile.ZipFile(destino_zip, "w", zipfile.ZIP_DEFLATED) as z:
        for nome, caminho in componentes.items():
            z.write(caminho, nome)
