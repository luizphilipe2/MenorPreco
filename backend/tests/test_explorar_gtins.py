"""Testes unitários para explorar_gtins.py"""

import sys
import os
from io import StringIO
from unittest.mock import patch

import httpx
import pytest
import respx

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from explorar_gtins import buscar_tudo, exibir

BASE = "https://menorpreco.notaparana.pr.gov.br"

PRODUTO = {
    "gtin": "7891118025664",
    "desc": "CHICLETE HUEVITOS",
    "valor": "3.99",
    "estabelecimento": {"nm_fan": "SUPERMERCADO X", "nm_emp": "EMPRESA X LTDA"},
}

CATEGORIA = {"id": 1, "desc": "Alimentos", "qtd": 1}

# ── buscar_tudo ───────────────────────────────────────────────────────────────

def test_buscar_tudo_retorna_produtos():
    with respx.mock:
        respx.get(f"{BASE}/api/v1/categorias").mock(
            return_value=httpx.Response(200, json={"categorias": [CATEGORIA]})
        )
        respx.get(f"{BASE}/api/v1/produtos").mock(
            return_value=httpx.Response(200, json={"produtos": [PRODUTO], "total": 1})
        )
        resultado = buscar_tudo("huevitos", 5)

    assert len(resultado) == 1
    assert resultado[0]["gtin"] == "7891118025664"


def test_buscar_tudo_sem_categorias_retorna_vazio(capsys):
    with respx.mock:
        respx.get(f"{BASE}/api/v1/categorias").mock(
            return_value=httpx.Response(200, json={"categorias": []})
        )
        resultado = buscar_tudo("produto-inexistente", 5)

    assert resultado == []
    saida = capsys.readouterr().out
    assert "Nenhuma categoria" in saida


def test_buscar_tudo_paginacao():
    chamadas = 0

    def paginar(request):
        nonlocal chamadas
        chamadas += 1
        page = [PRODUTO] * 50 if chamadas == 1 else [PRODUTO] * 5
        return httpx.Response(200, json={"produtos": page, "total": 55})

    with respx.mock:
        respx.get(f"{BASE}/api/v1/categorias").mock(
            return_value=httpx.Response(200, json={"categorias": [CATEGORIA]})
        )
        respx.get(f"{BASE}/api/v1/produtos").mock(side_effect=paginar)
        resultado = buscar_tudo("huevitos", 5)

    assert len(resultado) == 55
    assert chamadas == 2

# ── exibir ────────────────────────────────────────────────────────────────────

def test_exibir_agrupa_por_gtin(capsys):
    produtos = [
        {**PRODUTO, "gtin": "111", "valor": "2.00"},
        {**PRODUTO, "gtin": "111", "valor": "3.00"},
        {**PRODUTO, "gtin": "222", "valor": "5.00"},
    ]
    exibir(produtos)
    saida = capsys.readouterr().out
    assert "111" in saida
    assert "222" in saida
    assert "3 registros" in saida
    assert "2 GTINs" in saida


def test_exibir_mostra_faixa_de_preco(capsys):
    produtos = [
        {**PRODUTO, "valor": "1.50"},
        {**PRODUTO, "valor": "4.00"},
    ]
    exibir(produtos)
    saida = capsys.readouterr().out
    assert "1.50" in saida
    assert "4.00" in saida


def test_exibir_produto_sem_gtin_agrupado_como_sem_gtin(capsys):
    produtos = [{**PRODUTO, "gtin": ""}]
    exibir(produtos)
    saida = capsys.readouterr().out
    assert "SEM_GTIN" in saida


def test_exibir_usa_nm_emp_quando_nm_fan_ausente(capsys):
    produto = {**PRODUTO, "estabelecimento": {"nm_fan": "", "nm_emp": "EMPRESA Y"}}
    exibir([produto])
    saida = capsys.readouterr().out
    assert "EMPRESA Y" in saida
