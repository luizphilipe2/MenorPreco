"""
Explorador de GTINs - Menor Preço Nota Paraná
Agrupa resultados por GTIN pra você descobrir quais produtos rastrear.

Uso:
    python explorar_gtins.py huevitos
    python explorar_gtins.py "arroz tio joao" --raio 3
    python explorar_gtins.py cafe --raio 10
"""

import httpx
import os
import sys
import time
from collections import defaultdict

LOCAL = os.getenv("LOCAL", "6gf96u6q8")  # padrão: Cianorte
BASE  = "https://menorpreco.notaparana.pr.gov.br"

HEADERS = {
    "Accept": "application/json",
    "User-Agent": "Mozilla/5.0",
    "Referer": "https://menorpreco.notaparana.pr.gov.br/",
}

def buscar_tudo(termo: str, raio: int) -> list[dict]:
    with httpx.Client() as client:
        # 1. Categorias
        cats = client.get(
            f"{BASE}/api/v1/categorias",
            params={"local": LOCAL, "termo": termo, "raio": raio},
            headers=HEADERS, timeout=15
        ).json().get("categorias", [])

        if not cats:
            print("Nenhuma categoria encontrada.")
            return []

        todos = []
        for cat in cats:
            print(f"  Carregando: {cat['desc']} ({cat['qtd']} registros)...")
            offset = 0
            while True:
                data = client.get(
                    f"{BASE}/api/v1/produtos",
                    params={"local": LOCAL, "termo": termo, "categoria": cat["id"],
                            "offset": offset, "raio": raio, "data": -1, "ordem": 0},
                    headers=HEADERS, timeout=15
                ).json()
                page = data.get("produtos", [])
                todos.extend(page)
                offset += 50
                if offset >= data.get("total", 0) or not page:
                    break
                time.sleep(0.2)

    return todos


def exibir(produtos: list[dict]) -> None:
    # Agrupa por GTIN
    grupos: dict[str, list] = defaultdict(list)
    for p in produtos:
        gtin = p.get("gtin", "").strip() or "SEM_GTIN"
        grupos[gtin].append(p)

    # Ordena: mais vendas primeiro, sem GTIN por último
    ordenados = sorted(
        grupos.items(),
        key=lambda x: (x[0] == "SEM_GTIN", -len(x[1]))
    )

    todos_vals = [float(p["valor"]) for p in produtos]
    print(f"\n{'═'*65}")
    print(f"  {len(produtos)} registros  |  {len(grupos)} GTINs distintos  |  "
          f"R$ {min(todos_vals):.2f} – R$ {max(todos_vals):.2f}")
    print(f"{'═'*65}\n")

    for gtin, items in ordenados:
        vals  = [float(p["valor"]) for p in items]
        descs = list(dict.fromkeys(p["desc"] for p in items))  # únicas, em ordem

        print(f"  GTIN: {gtin}")
        print(f"  Preço: R$ {min(vals):.2f} – R$ {max(vals):.2f}  |  {len(items)} venda(s)")
        print(f"  Descrições encontradas:")
        for d in descs[:6]:
            print(f"    · {d}")
        if len(descs) > 6:
            print(f"    · ... +{len(descs)-6} outras")

        # Mostra as 3 vendas mais baratas
        mais_baratas = sorted(items, key=lambda p: float(p["valor"]))[:3]
        print(f"  Mais baratas:")
        for p in mais_baratas:
            loja = (p["estabelecimento"].get("nm_fan") or
                    p["estabelecimento"].get("nm_emp") or "?")
            print(f"    R$ {float(p['valor']):.2f}  ·  {loja[:45]}")

        print()

    print("Dica: copie os GTINs que interessam para usar no coletor.")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("termo", help="Produto a buscar")
    parser.add_argument("--raio", type=int, default=5, help="Raio em km (padrão: 5)")
    args = parser.parse_args()

    print(f"\nBuscando '{args.termo}' num raio de {args.raio}km...")
    produtos = buscar_tudo(args.termo, args.raio)
    if produtos:
        exibir(produtos)