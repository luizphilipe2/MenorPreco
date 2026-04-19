"""
Coletor de preços - Menor Preço Nota Paraná
Busca preços de produtos e salva histórico no Supabase.
"""

import httpx
import os
import time
from datetime import datetime, timezone

# ── Configuração ──────────────────────────────────────────────────────────────

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_KEY"]

MENOR_PRECO_BASE = "https://menorpreco.notaparana.pr.gov.br"

LOCAL = "6gf96u6q8"  # Cianorte

# Formato: (gtin, descricao_referencia, raio_km)
PRODUTOS_MONITORADOS = [
    ("7891118025664", "CHICLETE HUEVITOS TORTUGUITAS 25G", 20),
    ("7891118006922", "HUEVITOS ARCOR", 20),
    ("07891118006922", "BIG BIG HUEVITOS", 20),
    ("7891118025671", "HUEVITOS TORTUGUITA 300GR", 20),
    ("7891000457634", "CHOC NESTLE KIT KAT COTTON CANDY 41 5G", 20),
]

DATA  = -1
ORDEM = 0

HEADERS = {
    "Accept": "application/json",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://menorpreco.notaparana.pr.gov.br/",
}

SUPABASE_HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "resolution=ignore-duplicates",
}

# ── Funções da API Menor Preço ────────────────────────────────────────────────

def buscar_categorias(client: httpx.Client, termo: str, raio: int) -> list[dict]:
    url = f"{MENOR_PRECO_BASE}/api/v1/categorias"
    params = {"local": LOCAL, "termo": termo, "raio": raio}
    resp = client.get(url, params=params, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    return resp.json().get("categorias", [])


def buscar_produtos(client: httpx.Client, termo: str, categoria_id: int, raio: int) -> list[dict]:
    url = f"{MENOR_PRECO_BASE}/api/v1/produtos"
    produtos = []
    offset = 0

    while True:
        params = {
            "local": LOCAL,
            "termo": termo,
            "categoria": categoria_id,
            "offset": offset,
            "raio": raio,
            "data": DATA,
            "ordem": ORDEM,
        }
        resp = client.get(url, params=params, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        page = data.get("produtos", [])
        produtos.extend(page)

        offset += 50
        if offset >= data.get("total", 0) or not page:
            break

        time.sleep(0.1)

    return produtos


# ── Funções do Supabase ───────────────────────────────────────────────────────

def upsert_produto(client: httpx.Client, produto: dict) -> None:
    gtin = produto.get("gtin", "").strip()
    if not gtin:
        return

    payload = {
        "gtin":      gtin,
        "descricao": produto.get("desc", "").strip(),
        "ncm":       produto.get("ncm", "").strip(),
    }
    resp = client.post(
        f"{SUPABASE_URL}/rest/v1/produtos",
        json=payload,
        headers={**SUPABASE_HEADERS, "Prefer": "resolution=ignore-duplicates"},
        timeout=10,
    )
    resp.raise_for_status()


def upsert_estabelecimento(client: httpx.Client, estab: dict) -> None:
    payload = {
        "codigo":     estab.get("codigo", ""),
        "nome_fan":   estab.get("nm_fan", "").strip(),
        "nome_emp":   estab.get("nm_emp", "").strip(),
        "logradouro": f"{estab.get('tp_logr','')} {estab.get('nm_logr','')}".strip(),
        "numero":     estab.get("nr_logr", "").strip(),
        "bairro":     estab.get("bairro", "").strip(),
        "municipio":  estab.get("mun", "").strip(),
        "uf":         estab.get("uf", "").strip(),
    }
    resp = client.post(
        f"{SUPABASE_URL}/rest/v1/estabelecimentos",
        json=payload,
        headers={**SUPABASE_HEADERS, "Prefer": "resolution=ignore-duplicates"},
        timeout=10,
    )
    resp.raise_for_status()


def inserir_preco(client: httpx.Client, produto: dict) -> bool:
    gtin = produto.get("gtin", "").strip()
    if not gtin:
        return False

    payload = {
        "gtin":            gtin,
        "estabelecimento": produto["estabelecimento"]["codigo"],
        "nrdoc":           produto.get("nrdoc", ""),
        "valor":           float(produto.get("valor", 0)),
        "datahora_venda":  produto.get("datahora", ""),
    }
    resp = client.post(
        f"{SUPABASE_URL}/rest/v1/precos",
        json=payload,
        headers={**SUPABASE_HEADERS, "Prefer": "resolution=ignore-duplicates,return=representation"},
        timeout=10,
    )
    resp.raise_for_status()
    return len(resp.json()) > 0


def salvar_log(client: httpx.Client, termo: str, novos: int, vistos: int, sucesso: bool, erro: str = "") -> None:
    payload = {
        "termo":        termo,
        "total_novos":  novos,
        "total_vistos": vistos,
        "sucesso":      sucesso,
        "erro":         erro,
    }
    client.post(
        f"{SUPABASE_URL}/rest/v1/logs_coleta",
        json=payload,
        headers=SUPABASE_HEADERS,
        timeout=10,
    )


# ── Fluxo principal ───────────────────────────────────────────────────────────

def coletar_produto(mp_client: httpx.Client, sb_client: httpx.Client, gtin: str, desc: str, raio: int) -> None:
    print(f"\n{'─'*50}")
    print(f"  Buscando: {desc}")
    print(f"  GTIN: {gtin} | raio: {raio}km")
    print(f"{'─'*50}")

    novos  = 0
    vistos = 0

    try:
        categorias = buscar_categorias(mp_client, gtin, raio)
        if not categorias:
            print(f"  Nenhum resultado encontrado.")
            salvar_log(sb_client, gtin, 0, 0, True)
            return

        for cat in categorias:
            print(f"  Categoria: {cat['desc']} ({cat['qtd']} resultados)")
            produtos = buscar_produtos(mp_client, gtin, cat["id"], raio)

            for p in produtos:
                vistos += 1
                estab = p.get("estabelecimento", {})

                upsert_produto(sb_client, p)
                upsert_estabelecimento(sb_client, estab)

                inserido = inserir_preco(sb_client, p)
                if inserido:
                    novos += 1
                    loja = estab.get("nm_fan") or estab.get("nm_emp") or "?"
                    print(f"  + R$ {float(p['valor']):>6.2f} | {loja[:35]} | {p['desc'][:30]}")

        print(f"\n  Resultado: {novos} novos / {vistos} vistos")
        salvar_log(sb_client, gtin, novos, vistos, True)

    except Exception as e:
        print(f"  ERRO: {e}")
        salvar_log(sb_client, gtin, novos, vistos, False, str(e))


def main():
    inicio = datetime.now(timezone.utc)
    print(f"\n{'='*50}")
    print(f"  Coletor iniciado: {inicio.strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print(f"  {len(PRODUTOS_MONITORADOS)} produto(s) na lista")
    print(f"{'='*50}")

    with httpx.Client() as mp_client, httpx.Client() as sb_client:
        for gtin, desc, raio in PRODUTOS_MONITORADOS:
            coletar_produto(mp_client, sb_client, gtin, desc, raio)
            time.sleep(1)

    fim = datetime.now(timezone.utc)
    duracao = (fim - inicio).seconds
    print(f"\n{'='*50}")
    print(f"  Concluído em {duracao}s")
    print(f"{'='*50}\n")


if __name__ == "__main__":
    main()