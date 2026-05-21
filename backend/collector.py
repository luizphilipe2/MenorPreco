"""Coletor de preços - Menor Preço Nota Paraná"""

import asyncio
import logging
import os
from datetime import datetime, timezone

import httpx

# ── Configuração ──────────────────────────────────────────────────────────────

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_KEY"]
LOCAL        = os.getenv("LOCAL", "6gf96u6q8")  # padrão: Cianorte

MENOR_PRECO_BASE = "https://menorpreco.notaparana.pr.gov.br"
DATA  = -1
ORDEM = 0

MP_HEADERS = {
    "Accept": "application/json",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://menorpreco.notaparana.pr.gov.br/",
}

SB_HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "resolution=ignore-duplicates",
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

# ── Helpers ───────────────────────────────────────────────────────────────────

async def _get(client: httpx.AsyncClient, url: str, **kwargs) -> httpx.Response:
    for attempt in range(3):
        try:
            resp = await client.get(url, **kwargs)
            resp.raise_for_status()
            return resp
        except (httpx.HTTPError, httpx.TimeoutException):
            if attempt == 2:
                raise
            await asyncio.sleep(2 ** attempt)

# ── API Menor Preço ───────────────────────────────────────────────────────────

async def buscar_categorias(client: httpx.AsyncClient, termo: str, raio: int) -> list[dict]:
    resp = await _get(
        client,
        f"{MENOR_PRECO_BASE}/api/v1/categorias",
        params={"local": LOCAL, "termo": termo, "raio": raio},
        headers=MP_HEADERS,
        timeout=15,
    )
    return resp.json().get("categorias", [])


async def buscar_produtos(client: httpx.AsyncClient, termo: str, categoria_id: int, raio: int) -> list[dict]:
    produtos = []
    offset = 0

    while True:
        resp = await _get(
            client,
            f"{MENOR_PRECO_BASE}/api/v1/produtos",
            params={
                "local": LOCAL, "termo": termo, "categoria": categoria_id,
                "offset": offset, "raio": raio, "data": DATA, "ordem": ORDEM,
            },
            headers=MP_HEADERS,
            timeout=15,
        )
        data = resp.json()
        page = data.get("produtos", [])
        produtos.extend(page)

        offset += 50
        if offset >= data.get("total", 0) or not page:
            break

        await asyncio.sleep(0.1)

    return produtos

# ── Supabase ──────────────────────────────────────────────────────────────────

async def upsert_produto(client: httpx.AsyncClient, produto: dict) -> None:
    gtin = produto.get("gtin", "").strip()
    if not gtin:
        return
    resp = await client.post(
        f"{SUPABASE_URL}/rest/v1/produtos",
        json={"gtin": gtin, "descricao": produto.get("desc", "").strip(), "ncm": produto.get("ncm", "").strip()},
        headers={**SB_HEADERS, "Prefer": "resolution=ignore-duplicates"},
        timeout=10,
    )
    resp.raise_for_status()


async def upsert_estabelecimento(client: httpx.AsyncClient, estab: dict) -> None:
    payload = {
        "codigo":     estab.get("codigo", ""),
        "nome_fan":   estab.get("nm_fan", "").strip(),
        "nome_emp":   estab.get("nm_emp", "").strip(),
        "logradouro": f"{estab.get('tp_logr', '')} {estab.get('nm_logr', '')}".strip(),
        "numero":     estab.get("nr_logr", "").strip(),
        "bairro":     estab.get("bairro", "").strip(),
        "municipio":  estab.get("mun", "").strip(),
        "uf":         estab.get("uf", "").strip(),
    }
    resp = await client.post(
        f"{SUPABASE_URL}/rest/v1/estabelecimentos",
        json=payload,
        headers={**SB_HEADERS, "Prefer": "resolution=ignore-duplicates"},
        timeout=10,
    )
    resp.raise_for_status()


async def inserir_preco(client: httpx.AsyncClient, produto: dict) -> bool:
    gtin = produto.get("gtin", "").strip()
    if not gtin:
        return False
    resp = await client.post(
        f"{SUPABASE_URL}/rest/v1/precos",
        json={
            "gtin":           gtin,
            "estabelecimento": produto["estabelecimento"]["codigo"],
            "nrdoc":           produto.get("nrdoc", ""),
            "valor":           float(produto.get("valor", 0)),
            "datahora_venda":  produto.get("datahora", ""),
        },
        headers={**SB_HEADERS, "Prefer": "resolution=ignore-duplicates,return=representation"},
        timeout=10,
    )
    resp.raise_for_status()
    return len(resp.json()) > 0


async def buscar_produtos_monitorados(client: httpx.AsyncClient) -> list[tuple[str, str, int]]:
    resp = await client.get(
        f"{SUPABASE_URL}/rest/v1/produtos",
        params={"monitorado": "eq.true", "select": "gtin,descricao,raio_km"},
        headers=SB_HEADERS,
        timeout=10,
    )
    resp.raise_for_status()
    return [(p["gtin"], p["descricao"], p["raio_km"]) for p in resp.json()]


async def salvar_log(client: httpx.AsyncClient, termo: str, novos: int, vistos: int, sucesso: bool, erro: str = "") -> None:
    await client.post(
        f"{SUPABASE_URL}/rest/v1/logs_coleta",
        json={"termo": termo, "total_novos": novos, "total_vistos": vistos, "sucesso": sucesso, "erro": erro},
        headers=SB_HEADERS,
        timeout=10,
    )

# ── Fluxo principal ───────────────────────────────────────────────────────────

async def coletar_produto(mp_client: httpx.AsyncClient, sb_client: httpx.AsyncClient, gtin: str, desc: str, raio: int) -> None:
    log.info("Buscando: %s (GTIN: %s | raio: %dkm)", desc, gtin, raio)
    novos = vistos = 0

    try:
        categorias = await buscar_categorias(mp_client, gtin, raio)
        if not categorias:
            log.info("Nenhum resultado para %s", gtin)
            await salvar_log(sb_client, gtin, 0, 0, True)
            return

        for cat in categorias:
            log.info("Categoria: %s (%d resultados)", cat["desc"], cat["qtd"])
            produtos = await buscar_produtos(mp_client, gtin, cat["id"], raio)

            for p in produtos:
                vistos += 1
                estab = p.get("estabelecimento", {})
                await upsert_produto(sb_client, p)
                await upsert_estabelecimento(sb_client, estab)
                if await inserir_preco(sb_client, p):
                    novos += 1
                    loja = estab.get("nm_fan") or estab.get("nm_emp") or "?"
                    log.info("  + R$ %6.2f | %s | %s", float(p["valor"]), loja[:35], p["desc"][:30])

        log.info("Resultado %s: %d novos / %d vistos", gtin, novos, vistos)
        await salvar_log(sb_client, gtin, novos, vistos, True)

    except Exception as e:
        log.error("Erro ao coletar %s: %s", gtin, e)
        await salvar_log(sb_client, gtin, novos, vistos, False, str(e))


async def main() -> None:
    inicio = datetime.now(timezone.utc)

    async with httpx.AsyncClient() as mp_client, httpx.AsyncClient() as sb_client:
        produtos = await buscar_produtos_monitorados(sb_client)
        if not produtos:
            log.warning("Nenhum produto monitorado encontrado no Supabase.")
            return

        log.info("Coletor iniciado — %d produto(s)", len(produtos))
        await asyncio.gather(*(
            coletar_produto(mp_client, sb_client, gtin, desc, raio)
            for gtin, desc, raio in produtos
        ))

    duracao = (datetime.now(timezone.utc) - inicio).seconds
    log.info("Concluído em %ds", duracao)


if __name__ == "__main__":
    asyncio.run(main())
