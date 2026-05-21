"""Coletor de preços - Menor Preço Nota Paraná"""

import asyncio
import logging
import os
from datetime import datetime, timezone

import httpx

# ── Configuração ──────────────────────────────────────────────────────────────

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_KEY"]
LOCAL        = os.getenv("LOCAL", "6gf96u6q8")

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
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

# ── GitHub Actions helpers ────────────────────────────────────────────────────

_GHA           = os.getenv("GITHUB_ACTIONS") == "true"
_SUMMARY_FILE  = os.getenv("GITHUB_STEP_SUMMARY", "")

def _gha(cmd: str, msg: str = "") -> None:
    if _GHA:
        print(f"::{cmd}::{msg}", flush=True)

def gh_group(title: str)  -> None: _gha("group", title)
def gh_endgroup()         -> None: _gha("endgroup")
def gh_notice(msg: str)   -> None: _gha("notice", msg)
def gh_warning(msg: str)  -> None: _gha("warning", msg)
def gh_error(msg: str)    -> None: _gha("error", msg)

def gh_summary(md: str) -> None:
    if _SUMMARY_FILE:
        with open(_SUMMARY_FILE, "a", encoding="utf-8") as f:
            f.write(md + "\n")

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
            log.warning("  tentativa %d falhou, aguardando %ds...", attempt + 1, 2 ** attempt)
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
            "gtin":            gtin,
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

async def coletar_produto(
    mp_client: httpx.AsyncClient,
    sb_client: httpx.AsyncClient,
    gtin: str,
    desc: str,
    raio: int,
) -> tuple[int, int, bool]:
    gh_group(f"📦 {desc}  ·  {gtin}  ·  raio {raio}km")
    log.info("┌─ %s", desc)
    log.info("│  GTIN: %s  |  raio: %dkm", gtin, raio)
    novos = vistos = 0

    try:
        categorias = await buscar_categorias(mp_client, gtin, raio)
        if not categorias:
            log.info("│  ⚠ nenhuma categoria encontrada")
            log.info("└─ sem resultados")
            await salvar_log(sb_client, gtin, 0, 0, True)
            gh_notice(f"Sem resultados para {desc} ({gtin})")
            return 0, 0, True

        log.info("│  %d categoria(s): %s", len(categorias),
                 ", ".join(f"{c['desc']} ({c['qtd']})" for c in categorias))

        for cat in categorias:
            produtos = await buscar_produtos(mp_client, gtin, cat["id"], raio)
            log.info("│  [%s] %d produto(s) retornado(s)", cat["desc"], len(produtos))

            for p in produtos:
                vistos += 1
                estab = p.get("estabelecimento", {})
                loja  = (estab.get("nm_fan") or estab.get("nm_emp") or "?")[:35]
                await upsert_produto(sb_client, p)
                await upsert_estabelecimento(sb_client, estab)
                if await inserir_preco(sb_client, p):
                    novos += 1
                    log.info("│  ✚ NOVO  R$ %6.2f  │  %-35s  │  %s",
                             float(p["valor"]), loja, p["desc"][:40])
                else:
                    log.info("│  · dup   R$ %6.2f  │  %s",
                             float(p["valor"]), loja)

        log.info("└─ %d novos  /  %d vistos", novos, vistos)
        await salvar_log(sb_client, gtin, novos, vistos, True)
        gh_notice(f"{desc}: {novos} novos / {vistos} vistos")
        return novos, vistos, True

    except Exception as e:
        log.error("└─ ✖ ERRO: %s", e)
        await salvar_log(sb_client, gtin, novos, vistos, False, str(e))
        gh_error(f"Falha em {desc} ({gtin}): {e}")
        return novos, vistos, False

    finally:
        gh_endgroup()


async def main() -> None:
    inicio = datetime.now(timezone.utc)

    sep = "─" * 55
    log.info(sep)
    log.info("  PriceWatch · Coletor de Preços")
    log.info("  %s  |  LOCAL: %s", inicio.strftime("%d/%m/%Y %H:%M:%S UTC"), LOCAL)
    log.info(sep)

    resultados: list[tuple[int, int, bool]] = []

    async with httpx.AsyncClient() as mp_client, httpx.AsyncClient() as sb_client:

        gh_group("🔎 Produtos monitorados")
        monitorados = await buscar_produtos_monitorados(sb_client)
        if monitorados:
            for gtin, desc, raio in monitorados:
                log.info("  · %-45s  %s  raio %dkm", desc, gtin, raio)
        gh_endgroup()

        if not monitorados:
            gh_warning("Nenhum produto com monitorado=true no Supabase. Ative produtos no /admin.")
            log.warning("Nenhum produto monitorado — encerrando.")
            gh_summary("## ⚠️ Nenhum produto monitorado\n\nAtive produtos na página `/admin` antes de rodar a coleta.")
            return

        log.info("%d produto(s) para coletar", len(monitorados))

        for gtin, desc, raio in monitorados:
            r = await coletar_produto(mp_client, sb_client, gtin, desc, raio)
            resultados.append(r)

    duracao      = (datetime.now(timezone.utc) - inicio).seconds
    total_novos  = sum(r[0] for r in resultados)
    total_vistos = sum(r[1] for r in resultados)
    falhas       = sum(1 for r in resultados if not r[2])

    log.info(sep)
    log.info("  CONCLUÍDO em %ds", duracao)
    log.info("  Novos: %d  |  Vistos: %d  |  Falhas: %d", total_novos, total_vistos, falhas)
    log.info(sep)

    # ── Step summary ──────────────────────────────────────────────────────────
    agora  = datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M UTC")
    emoji  = "✅" if not falhas else ("⚠️" if total_novos > 0 else "❌")
    linhas = "\n".join(
        f"| {desc[:45]} | `{gtin}` | {novos} | {vistos} | {'✅' if ok else '❌'} |"
        for (gtin, desc, _), (novos, vistos, ok) in zip(monitorados, resultados)
    )
    extras = f" &nbsp;·&nbsp; **❌ Falhas:** {falhas}" if falhas else ""
    gh_summary(f"""\
## {emoji} Coleta de Preços — {agora}

| Produto | GTIN | Novos | Vistos | Status |
|---------|------|------:|-------:|:------:|
{linhas}

---
**⏱ Duração:** {duracao}s &nbsp;·&nbsp; **🆕 Novos:** {total_novos} &nbsp;·&nbsp; **👁 Vistos:** {total_vistos}{extras}
""")


if __name__ == "__main__":
    asyncio.run(main())
