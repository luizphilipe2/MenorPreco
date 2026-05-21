"""Testes unitários para collector.py"""

import json
import sys
import os
from unittest.mock import AsyncMock, patch

import httpx
import pytest
import respx

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from collector import (
    MENOR_PRECO_BASE,
    SUPABASE_URL,
    _get,
    buscar_categorias,
    buscar_produtos,
    buscar_produtos_monitorados,
    coletar_produto,
    inserir_preco,
    salvar_log,
    upsert_estabelecimento,
    upsert_produto,
)

# ── Fixtures ──────────────────────────────────────────────────────────────────

ESTAB = {
    "codigo": "estab001",
    "nm_fan": "SUPERMERCADO X",
    "nm_emp": "EMPRESA X LTDA",
    "tp_logr": "RUA",
    "nm_logr": "DAS FLORES",
    "nr_logr": "100",
    "bairro": "CENTRO",
    "mun": "CIANORTE",
    "uf": "PR",
}

PRODUTO = {
    "gtin": "7891118025664",
    "desc": "CHICLETE HUEVITOS",
    "ncm": "17049099",
    "valor": "3.99",
    "nrdoc": "DOC123",
    "datahora": "2024-01-15T10:30:00",
    "estabelecimento": ESTAB,
}

CATEGORIA = {"id": 1, "desc": "Alimentos", "qtd": 1}

# ── _get ──────────────────────────────────────────────────────────────────────

async def test_get_sucesso():
    with respx.mock:
        respx.get("https://example.com/api").mock(return_value=httpx.Response(200, json={"ok": True}))
        async with httpx.AsyncClient() as client:
            resp = await _get(client, "https://example.com/api")
    assert resp.json() == {"ok": True}


async def test_get_retry_sucede_na_terceira_tentativa():
    chamadas = 0

    async def lado(request):
        nonlocal chamadas
        chamadas += 1
        return httpx.Response(200, json={"ok": True}) if chamadas >= 3 else httpx.Response(500)

    with respx.mock:
        respx.get("https://example.com/api").mock(side_effect=lado)
        async with httpx.AsyncClient() as client:
            with patch("asyncio.sleep", new_callable=AsyncMock):
                resp = await _get(client, "https://example.com/api")

    assert chamadas == 3
    assert resp.json() == {"ok": True}


async def test_get_esgota_tres_tentativas_e_lanca():
    with respx.mock:
        respx.get("https://example.com/api").mock(return_value=httpx.Response(500))
        async with httpx.AsyncClient() as client:
            with patch("asyncio.sleep", new_callable=AsyncMock):
                with pytest.raises(httpx.HTTPStatusError):
                    await _get(client, "https://example.com/api")


async def test_get_retry_em_timeout():
    chamadas = 0

    async def lado(request):
        nonlocal chamadas
        chamadas += 1
        if chamadas < 3:
            raise httpx.TimeoutException("timeout", request=request)
        return httpx.Response(200, json={"ok": True})

    with respx.mock:
        respx.get("https://example.com/api").mock(side_effect=lado)
        async with httpx.AsyncClient() as client:
            with patch("asyncio.sleep", new_callable=AsyncMock):
                resp = await _get(client, "https://example.com/api")

    assert chamadas == 3

# ── buscar_categorias ─────────────────────────────────────────────────────────

async def test_buscar_categorias_retorna_lista():
    with respx.mock:
        respx.get(f"{MENOR_PRECO_BASE}/api/v1/categorias").mock(
            return_value=httpx.Response(200, json={"categorias": [CATEGORIA]})
        )
        async with httpx.AsyncClient() as client:
            cats = await buscar_categorias(client, "huevitos", 5)
    assert cats == [CATEGORIA]


async def test_buscar_categorias_retorna_vazio_quando_chave_ausente():
    with respx.mock:
        respx.get(f"{MENOR_PRECO_BASE}/api/v1/categorias").mock(
            return_value=httpx.Response(200, json={})
        )
        async with httpx.AsyncClient() as client:
            cats = await buscar_categorias(client, "xyz", 5)
    assert cats == []

# ── buscar_produtos ───────────────────────────────────────────────────────────

async def test_buscar_produtos_pagina_unica():
    with respx.mock:
        respx.get(f"{MENOR_PRECO_BASE}/api/v1/produtos").mock(
            return_value=httpx.Response(200, json={"produtos": [PRODUTO], "total": 1})
        )
        async with httpx.AsyncClient() as client:
            produtos = await buscar_produtos(client, "huevitos", 1, 5)
    assert len(produtos) == 1
    assert produtos[0]["gtin"] == "7891118025664"


async def test_buscar_produtos_paginacao_duas_paginas():
    chamadas = 0

    async def paginar(request):
        nonlocal chamadas
        chamadas += 1
        page = [PRODUTO] * 50 if chamadas == 1 else [PRODUTO] * 10
        return httpx.Response(200, json={"produtos": page, "total": 60})

    with respx.mock:
        respx.get(f"{MENOR_PRECO_BASE}/api/v1/produtos").mock(side_effect=paginar)
        async with httpx.AsyncClient() as client:
            produtos = await buscar_produtos(client, "huevitos", 1, 5)

    assert len(produtos) == 60
    assert chamadas == 2


async def test_buscar_produtos_para_quando_pagina_vazia():
    chamadas = 0

    async def paginar(request):
        nonlocal chamadas
        chamadas += 1
        page = [PRODUTO] * 50 if chamadas == 1 else []
        return httpx.Response(200, json={"produtos": page, "total": 100})

    with respx.mock:
        respx.get(f"{MENOR_PRECO_BASE}/api/v1/produtos").mock(side_effect=paginar)
        async with httpx.AsyncClient() as client:
            produtos = await buscar_produtos(client, "huevitos", 1, 5)

    assert len(produtos) == 50
    assert chamadas == 2

# ── upsert_produto ────────────────────────────────────────────────────────────

async def test_upsert_produto_envia_payload_correto():
    with respx.mock:
        route = respx.post(f"{SUPABASE_URL}/rest/v1/produtos").mock(return_value=httpx.Response(201))
        async with httpx.AsyncClient() as client:
            await upsert_produto(client, PRODUTO)

    payload = json.loads(route.calls[0].request.content)
    assert payload["gtin"] == "7891118025664"
    assert payload["descricao"] == "CHICLETE HUEVITOS"
    assert payload["ncm"] == "17049099"


async def test_upsert_produto_ignora_gtin_vazio():
    with respx.mock:
        route = respx.post(f"{SUPABASE_URL}/rest/v1/produtos").mock(return_value=httpx.Response(201))
        async with httpx.AsyncClient() as client:
            await upsert_produto(client, {**PRODUTO, "gtin": ""})

    assert not route.called


async def test_upsert_produto_ignora_gtin_apenas_espacos():
    with respx.mock:
        route = respx.post(f"{SUPABASE_URL}/rest/v1/produtos").mock(return_value=httpx.Response(201))
        async with httpx.AsyncClient() as client:
            await upsert_produto(client, {**PRODUTO, "gtin": "   "})

    assert not route.called

# ── upsert_estabelecimento ────────────────────────────────────────────────────

async def test_upsert_estabelecimento_monta_logradouro_corretamente():
    with respx.mock:
        route = respx.post(f"{SUPABASE_URL}/rest/v1/estabelecimentos").mock(return_value=httpx.Response(201))
        async with httpx.AsyncClient() as client:
            await upsert_estabelecimento(client, ESTAB)

    payload = json.loads(route.calls[0].request.content)
    assert payload["logradouro"] == "RUA DAS FLORES"
    assert payload["numero"] == "100"
    assert payload["municipio"] == "CIANORTE"
    assert payload["uf"] == "PR"


async def test_upsert_estabelecimento_logradouro_sem_tipo():
    estab = {**ESTAB, "tp_logr": "", "nm_logr": "INDEPENDENCIA"}
    with respx.mock:
        route = respx.post(f"{SUPABASE_URL}/rest/v1/estabelecimentos").mock(return_value=httpx.Response(201))
        async with httpx.AsyncClient() as client:
            await upsert_estabelecimento(client, estab)

    payload = json.loads(route.calls[0].request.content)
    assert payload["logradouro"] == "INDEPENDENCIA"

# ── inserir_preco ─────────────────────────────────────────────────────────────

async def test_inserir_preco_retorna_true_quando_novo():
    with respx.mock:
        respx.post(f"{SUPABASE_URL}/rest/v1/precos").mock(
            return_value=httpx.Response(201, json=[{"id": 1}])
        )
        async with httpx.AsyncClient() as client:
            resultado = await inserir_preco(client, PRODUTO)
    assert resultado is True


async def test_inserir_preco_retorna_false_quando_duplicado():
    with respx.mock:
        respx.post(f"{SUPABASE_URL}/rest/v1/precos").mock(
            return_value=httpx.Response(200, json=[])
        )
        async with httpx.AsyncClient() as client:
            resultado = await inserir_preco(client, PRODUTO)
    assert resultado is False


async def test_inserir_preco_ignora_gtin_vazio():
    with respx.mock:
        route = respx.post(f"{SUPABASE_URL}/rest/v1/precos").mock(return_value=httpx.Response(201, json=[]))
        async with httpx.AsyncClient() as client:
            resultado = await inserir_preco(client, {**PRODUTO, "gtin": ""})

    assert resultado is False
    assert not route.called


async def test_inserir_preco_converte_valor_para_float():
    with respx.mock:
        route = respx.post(f"{SUPABASE_URL}/rest/v1/precos").mock(
            return_value=httpx.Response(201, json=[{"id": 1}])
        )
        async with httpx.AsyncClient() as client:
            await inserir_preco(client, {**PRODUTO, "valor": "3.99"})

    payload = json.loads(route.calls[0].request.content)
    assert payload["valor"] == 3.99
    assert isinstance(payload["valor"], float)

# ── salvar_log ────────────────────────────────────────────────────────────────

async def test_salvar_log_envia_campos_corretos():
    with respx.mock:
        route = respx.post(f"{SUPABASE_URL}/rest/v1/logs_coleta").mock(return_value=httpx.Response(201))
        async with httpx.AsyncClient() as client:
            await salvar_log(client, "7891118025664", novos=3, vistos=10, sucesso=True)

    payload = json.loads(route.calls[0].request.content)
    assert payload["termo"] == "7891118025664"
    assert payload["total_novos"] == 3
    assert payload["total_vistos"] == 10
    assert payload["sucesso"] is True
    assert payload["erro"] == ""


async def test_salvar_log_inclui_mensagem_de_erro():
    with respx.mock:
        route = respx.post(f"{SUPABASE_URL}/rest/v1/logs_coleta").mock(return_value=httpx.Response(201))
        async with httpx.AsyncClient() as client:
            await salvar_log(client, "gtin123", novos=0, vistos=0, sucesso=False, erro="timeout")

    payload = json.loads(route.calls[0].request.content)
    assert payload["sucesso"] is False
    assert payload["erro"] == "timeout"

# ── coletar_produto ───────────────────────────────────────────────────────────

async def test_coletar_produto_sem_categorias_salva_log_zerado():
    with respx.mock:
        respx.get(f"{MENOR_PRECO_BASE}/api/v1/categorias").mock(
            return_value=httpx.Response(200, json={"categorias": []})
        )
        route_log = respx.post(f"{SUPABASE_URL}/rest/v1/logs_coleta").mock(return_value=httpx.Response(201))

        async with httpx.AsyncClient() as mp, httpx.AsyncClient() as sb:
            await coletar_produto(mp, sb, "7891118025664", "HUEVITOS", 5)

    payload = json.loads(route_log.calls[0].request.content)
    assert payload["total_novos"] == 0
    assert payload["total_vistos"] == 0
    assert payload["sucesso"] is True


async def test_coletar_produto_fluxo_completo_conta_novos():
    with respx.mock:
        respx.get(f"{MENOR_PRECO_BASE}/api/v1/categorias").mock(
            return_value=httpx.Response(200, json={"categorias": [CATEGORIA]})
        )
        respx.get(f"{MENOR_PRECO_BASE}/api/v1/produtos").mock(
            return_value=httpx.Response(200, json={"produtos": [PRODUTO, PRODUTO], "total": 2})
        )
        respx.post(f"{SUPABASE_URL}/rest/v1/produtos").mock(return_value=httpx.Response(201))
        respx.post(f"{SUPABASE_URL}/rest/v1/estabelecimentos").mock(return_value=httpx.Response(201))
        respx.post(f"{SUPABASE_URL}/rest/v1/precos").mock(
            return_value=httpx.Response(201, json=[{"id": 1}])
        )
        route_log = respx.post(f"{SUPABASE_URL}/rest/v1/logs_coleta").mock(return_value=httpx.Response(201))

        async with httpx.AsyncClient() as mp, httpx.AsyncClient() as sb:
            await coletar_produto(mp, sb, "7891118025664", "HUEVITOS", 5)

    payload = json.loads(route_log.calls[0].request.content)
    assert payload["total_novos"] == 2
    assert payload["total_vistos"] == 2
    assert payload["sucesso"] is True


async def test_coletar_produto_duplicado_conta_vistos_mas_nao_novos():
    with respx.mock:
        respx.get(f"{MENOR_PRECO_BASE}/api/v1/categorias").mock(
            return_value=httpx.Response(200, json={"categorias": [CATEGORIA]})
        )
        respx.get(f"{MENOR_PRECO_BASE}/api/v1/produtos").mock(
            return_value=httpx.Response(200, json={"produtos": [PRODUTO], "total": 1})
        )
        respx.post(f"{SUPABASE_URL}/rest/v1/produtos").mock(return_value=httpx.Response(201))
        respx.post(f"{SUPABASE_URL}/rest/v1/estabelecimentos").mock(return_value=httpx.Response(201))
        respx.post(f"{SUPABASE_URL}/rest/v1/precos").mock(
            return_value=httpx.Response(200, json=[])  # duplicado
        )
        route_log = respx.post(f"{SUPABASE_URL}/rest/v1/logs_coleta").mock(return_value=httpx.Response(201))

        async with httpx.AsyncClient() as mp, httpx.AsyncClient() as sb:
            await coletar_produto(mp, sb, "7891118025664", "HUEVITOS", 5)

    payload = json.loads(route_log.calls[0].request.content)
    assert payload["total_novos"] == 0
    assert payload["total_vistos"] == 1
    assert payload["sucesso"] is True


async def test_coletar_produto_erro_na_api_salva_log_com_falha():
    with respx.mock:
        respx.get(f"{MENOR_PRECO_BASE}/api/v1/categorias").mock(
            return_value=httpx.Response(500)
        )
        route_log = respx.post(f"{SUPABASE_URL}/rest/v1/logs_coleta").mock(return_value=httpx.Response(201))

        async with httpx.AsyncClient() as mp, httpx.AsyncClient() as sb:
            with patch("asyncio.sleep", new_callable=AsyncMock):
                await coletar_produto(mp, sb, "7891118025664", "HUEVITOS", 5)

    payload = json.loads(route_log.calls[0].request.content)
    assert payload["sucesso"] is False
    assert payload["erro"] != ""

# ── buscar_produtos_monitorados ───────────────────────────────────────────────

async def test_buscar_produtos_monitorados_retorna_tuplas():
    rows = [
        {"gtin": "7891118025664", "descricao": "HUEVITOS", "raio_km": 10},
        {"gtin": "7891000457634", "descricao": "KIT KAT", "raio_km": 20},
    ]
    with respx.mock:
        respx.get(f"{SUPABASE_URL}/rest/v1/produtos").mock(
            return_value=httpx.Response(200, json=rows)
        )
        async with httpx.AsyncClient() as client:
            resultado = await buscar_produtos_monitorados(client)

    assert resultado == [
        ("7891118025664", "HUEVITOS", 10),
        ("7891000457634", "KIT KAT", 20),
    ]


async def test_buscar_produtos_monitorados_retorna_vazio():
    with respx.mock:
        respx.get(f"{SUPABASE_URL}/rest/v1/produtos").mock(
            return_value=httpx.Response(200, json=[])
        )
        async with httpx.AsyncClient() as client:
            resultado = await buscar_produtos_monitorados(client)

    assert resultado == []


async def test_buscar_produtos_monitorados_lanca_em_erro_http():
    with respx.mock:
        respx.get(f"{SUPABASE_URL}/rest/v1/produtos").mock(
            return_value=httpx.Response(500)
        )
        async with httpx.AsyncClient() as client:
            with pytest.raises(httpx.HTTPStatusError):
                await buscar_produtos_monitorados(client)
