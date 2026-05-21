# MenorPreco

Monitora preços de produtos via API pública do [Menor Preço Nota Paraná](https://menorpreco.notaparana.pr.gov.br), armazena histórico no Supabase e exibe dashboards com gráficos de evolução de preços.

## Estrutura

```
MenorPreco/
├── backend/
│   ├── collector.py       # Coletor de preços (roda a cada hora via GitHub Actions)
│   ├── explorar_gtins.py  # CLI para explorar produtos e GTINs
│   ├── requirements.txt
│   └── tests/             # Suíte de testes unitários
├── frontend/              # Dashboard SvelteKit
│   ├── src/
│   │   ├── lib/supabase.ts        # Cliente Supabase (lê env vars)
│   │   └── routes/
│   │       ├── +page.svelte       # Dashboard de preços
│   │       └── explorar/
│   │           └── +page.svelte   # Explorador de GTINs
│   └── .env.example
├── .github/
│   └── workflows/
│       └── coletar.yml    # Agendamento automático
└── .env.example           # Variáveis de ambiente necessárias
```

## Configuração

1. Crie um projeto no [Supabase](https://supabase.com) e configure as tabelas (ver abaixo)
2. Copie `.env.example` para `.env` e preencha as variáveis
3. No GitHub, adicione `SUPABASE_URL` e `SUPABASE_KEY` em *Settings > Secrets*

### Tabelas Supabase

- `produtos` — produtos monitorados (gtin, descricao)
- `estabelecimentos` — lojas (id, nome_fan, nome_emp, municipio)
- `precos` — histórico de preços (gtin, estabelecimento_id, preco, data)
- `logs_coleta` — log de execuções do coletor

## Rodando localmente

**Backend:**
```bash
cd backend
pip install -r requirements.txt
cp ../.env.example ../.env  # preencha o .env
python collector.py
```

**Frontend (requer Node.js 18+):**
```bash
cd frontend
cp .env.example .env        # preencha PUBLIC_SUPABASE_URL e PUBLIC_SUPABASE_ANON_KEY
npm install
npm run dev                 # http://localhost:5173
```

**Rotas:**
- `/` — dashboard com gráfico de histórico de preços
- `/explorar` — explorador de GTINs para adicionar produtos ao coletor

**Build para produção:**
```bash
cd frontend && npm run build   # gera pasta build/
```

## Variáveis de ambiente

| Variável | Descrição |
|---|---|
| `SUPABASE_URL` | URL do projeto Supabase |
| `SUPABASE_KEY` | Chave anon do Supabase |
| `LOCAL` | ID da localidade (padrão: Cianorte) |
