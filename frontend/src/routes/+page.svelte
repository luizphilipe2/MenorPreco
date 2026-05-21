<script lang="ts">
  import { onMount } from 'svelte';
  import Chart from 'chart.js/auto';
  import { sbQuery } from '$lib/supabase';

  type Produto   = { gtin: string; descricao: string };
  type Venda     = { valor: string; datahora_venda: string; estabelecimento: { nome_fan?: string; nome_emp?: string } | null };
  type RankItem  = { valor: string; estabelecimento: { nome_fan?: string; nome_emp?: string } | null };
  type StatCount = { gtin?: string; id?: number; codigo?: string };

  let lastUpdate    = $state('carregando...');
  let sProdutos     = $state('—');
  let sRegistros    = $state('—');
  let sEstabs       = $state('—');
  let sColeta       = $state('—');
  let sColetaSub    = $state('—');

  let produtos      = $state<Produto[]>([]);
  let busca         = $state('');
  let produtoAtivo  = $state('');
  let descAtiva     = $state('');

  let vendas        = $state<Venda[]>([]);
  let ranking       = $state<Array<[string, number]>>([]);
  let carregandoVendas   = $state(true);
  let carregandoRanking  = $state(true);

  let canvas: HTMLCanvasElement;
  let chartInst: Chart | null = null;

  let produtosFiltrados = $derived(
    busca.trim()
      ? produtos.filter(p => p.descricao.toLowerCase().includes(busca.toLowerCase()))
      : produtos
  );

  let minVal = $derived(vendas.length ? Math.min(...vendas.map(v => parseFloat(v.valor))) : 0);
  let maxVal = $derived(vendas.length ? Math.max(...vendas.map(v => parseFloat(v.valor))) : 0);

  function fmt(iso: string, time = false) {
    const dt = new Date(iso);
    const d = dt.toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit' });
    return time ? d + ' ' + dt.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' }) : d;
  }

  async function carregarStats() {
    const [prods, precos, estabs, lg] = await Promise.all([
      sbQuery<StatCount>('produtos', 'select=gtin&monitorado=eq.true'),
      sbQuery<StatCount>('precos', 'select=id'),
      sbQuery<StatCount>('estabelecimentos', 'select=codigo'),
      sbQuery<{ executado_em: string }>('logs_coleta', 'select=executado_em&order=executado_em.desc&limit=1'),
    ]);
    sProdutos  = String(prods.length);
    sRegistros = String(precos.length);
    sEstabs    = String(estabs.length);
    if (lg.length) {
      const dt = new Date(lg[0].executado_em);
      sColeta    = dt.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' });
      sColetaSub = dt.toLocaleDateString('pt-BR');
    }
  }

  async function carregarProdutos() {
    produtos = await sbQuery<Produto>('produtos', 'select=gtin,descricao&monitorado=eq.true&order=descricao');
    if (produtos.length) await selecionarProduto(produtos[0].gtin, produtos[0].descricao);
  }

  async function selecionarProduto(gtin: string, desc: string) {
    produtoAtivo = gtin;
    descAtiva    = desc.substring(0, 30);
    await Promise.all([carregarHistorico(gtin), carregarVendas(gtin), carregarRanking(gtin)]);
  }

  async function carregarHistorico(gtin: string) {
    const dados = await sbQuery<{ valor: string; datahora_venda: string }>(
      'precos', `select=valor,datahora_venda&gtin=eq.${gtin}&order=datahora_venda.asc&limit=200`
    );
    const porDia: Record<string, number> = {};
    for (const d of dados) {
      const dia = d.datahora_venda.substring(0, 10);
      const v = parseFloat(d.valor);
      if (!porDia[dia] || v < porDia[dia]) porDia[dia] = v;
    }
    renderChart(
      Object.keys(porDia).map(d => new Date(d + 'T12:00:00').toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit' })),
      Object.values(porDia)
    );
  }

  function renderChart(labels: string[], values: number[]) {
    chartInst?.destroy();
    if (!canvas || !values.length) return;
    const min = Math.min(...values), max = Math.max(...values);
    chartInst = new Chart(canvas, {
      type: 'line',
      data: {
        labels,
        datasets: [{
          data: values,
          borderColor: '#00ff87', borderWidth: 2,
          backgroundColor: (ctx) => {
            const g = ctx.chart.ctx.createLinearGradient(0, 0, 0, 260);
            g.addColorStop(0, 'rgba(0,255,135,0.15)'); g.addColorStop(1, 'rgba(0,255,135,0)');
            return g;
          },
          fill: true, tension: 0.4,
          pointBackgroundColor: values.map(v => v === min ? '#00ff87' : v === max ? '#ff4466' : 'transparent'),
          pointBorderColor:     values.map(v => v === min ? '#00ff87' : v === max ? '#ff4466' : 'transparent'),
          pointRadius:          values.map(v => (v === min || v === max) ? 5 : 2),
          pointHoverRadius: 6,
        }]
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        interaction: { mode: 'index', intersect: false },
        plugins: {
          legend: { display: false },
          tooltip: {
            backgroundColor: '#1c1c1f', borderColor: '#3f3f46', borderWidth: 1,
            titleColor: '#a1a1aa', bodyColor: '#fafafa',
            bodyFont: { family: 'JetBrains Mono', size: 13 },
            callbacks: { label: ctx => `  R$ ${ctx.parsed.y.toFixed(2)}` }
          }
        },
        scales: {
          x: { grid: { color: 'rgba(255,255,255,0.04)' }, ticks: { color: '#52525b', font: { family: 'JetBrains Mono', size: 10 }, maxTicksLimit: 10 }, border: { color: '#27272a' } },
          y: { grid: { color: 'rgba(255,255,255,0.04)' }, ticks: { color: '#52525b', font: { family: 'JetBrains Mono', size: 10 }, callback: v => 'R$ ' + (v as number).toFixed(2) }, border: { color: '#27272a' } }
        }
      }
    });
  }

  async function carregarVendas(gtin: string) {
    carregandoVendas = true;
    vendas = await sbQuery<Venda>(
      'precos', `select=valor,datahora_venda,estabelecimento(nome_fan,nome_emp)&gtin=eq.${gtin}&order=datahora_venda.desc&limit=15`
    );
    carregandoVendas = false;
  }

  async function carregarRanking(gtin: string) {
    carregandoRanking = true;
    const dados = await sbQuery<RankItem>(
      'precos', `select=valor,estabelecimento(nome_fan,nome_emp)&gtin=eq.${gtin}&order=valor.asc&limit=100`
    );
    const lojas: Record<string, number> = {};
    for (const d of dados) {
      const nome = d.estabelecimento?.nome_fan || d.estabelecimento?.nome_emp || '?';
      const v = parseFloat(d.valor);
      if (!lojas[nome] || v < lojas[nome]) lojas[nome] = v;
    }
    ranking = Object.entries(lojas).sort((a, b) => a[1] - b[1]).slice(0, 8);
    carregandoRanking = false;
  }

  async function init() {
    await Promise.all([carregarStats(), carregarProdutos()]);
    lastUpdate = 'atualizado ' + new Date().toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' });
  }

  onMount(async () => {
    await init();
    const interval = setInterval(init, 5 * 60 * 1000);
    return () => clearInterval(interval);
  });
</script>

<svelte:head>
  <title>PriceWatch · Menor Preço PR</title>
  <link rel="preconnect" href="https://fonts.googleapis.com" />
  <link href="https://fonts.googleapis.com/css2?family=Syne:wght@400;500;600;700;800&family=JetBrains+Mono:wght@300;400;500&display=swap" rel="stylesheet" />
</svelte:head>

<header>
  <div class="logo">price<span>watch</span>.pr</div>
  <nav>
    <a href="/" class="nav-link active">dashboard</a>
    <a href="/explorar" class="nav-link">explorar</a>
    <a href="/admin" class="nav-link">admin</a>
  </nav>
  <div class="header-right">
    <div class="last-update">{lastUpdate}</div>
    <div class="live-dot">ao vivo</div>
  </div>
</header>

<main>

  <div class="section-title">visão geral</div>
  <div class="stats-row">
    <div class="stat-card">
      <div class="stat-label">produtos monitorados</div>
      <div class="stat-val green">{sProdutos}</div>
      <div class="stat-sub">GTINs distintos</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">registros coletados</div>
      <div class="stat-val">{sRegistros}</div>
      <div class="stat-sub">total histórico</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">última coleta</div>
      <div class="stat-val" style="font-size:20px">{sColeta}</div>
      <div class="stat-sub">{sColetaSub}</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">estabelecimentos</div>
      <div class="stat-val">{sEstabs}</div>
      <div class="stat-sub">com vendas registradas</div>
    </div>
  </div>

  <div class="section-title">histórico de preços</div>
  <div class="card" style="margin-bottom:20px">
    <div class="produto-selector">
      <div class="search-wrap">
        <svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="6.5" cy="6.5" r="5"/><path d="M10.5 10.5L14 14"/></svg>
        <input
          type="text"
          class="search-input"
          placeholder="filtrar produto..."
          bind:value={busca}
        />
        {#if busca}
          <button class="clear-btn" onclick={() => busca = ''}>×</button>
        {/if}
      </div>
      <div class="produto-tabs">
        {#if produtos.length === 0}
          <div class="placeholder loading">carregando produtos...</div>
        {:else if produtosFiltrados.length === 0}
          <div class="placeholder">nenhum produto encontrado</div>
        {:else}
          {#each produtosFiltrados as p}
            <button
              class="tab"
              class:active={produtoAtivo === p.gtin}
              title={p.gtin}
              onclick={() => selecionarProduto(p.gtin, p.descricao)}
            >{p.descricao}</button>
          {/each}
        {/if}
      </div>
    </div>
    <div class="chart-wrap">
      <canvas bind:this={canvas}></canvas>
    </div>
  </div>

  <div class="grid-2">
    <div class="card">
      <div class="card-header">
        <div class="card-title">últimas vendas</div>
        <div class="card-meta">{descAtiva}</div>
      </div>
      <div class="card-body" style="padding:0">
        {#if carregandoVendas}
          <div class="placeholder loading">carregando...</div>
        {:else if vendas.length === 0}
          <div class="placeholder">nenhuma venda registrada ainda</div>
        {:else}
          <table class="price-table" style="padding:0 22px">
            <thead><tr><th>preço</th><th>estabelecimento</th><th>quando</th></tr></thead>
            <tbody>
              {#each vendas as v}
                {@const val = parseFloat(v.valor)}
                {@const loja = v.estabelecimento?.nome_fan || v.estabelecimento?.nome_emp || '?'}
                <tr>
                  <td class="val" class:best={val === minVal} class:worst={val === maxVal}>
                    R$ {val.toFixed(2)}
                    {#if val === minVal}<span class="badge best">mín</span>{/if}
                    {#if val === maxVal}<span class="badge worst">máx</span>{/if}
                  </td>
                  <td class="store">{loja}</td>
                  <td class="when">{fmt(v.datahora_venda, true)}</td>
                </tr>
              {/each}
            </tbody>
          </table>
        {/if}
      </div>
    </div>

    <div class="card">
      <div class="card-header">
        <div class="card-title">melhores preços por loja</div>
        <div class="card-meta">{descAtiva}</div>
      </div>
      <div class="card-body" style="padding: 4px 22px">
        {#if carregandoRanking}
          <div class="placeholder loading">carregando...</div>
        {:else if ranking.length === 0}
          <div class="placeholder">sem dados</div>
        {:else}
          <ul class="ranking-list">
            {#each ranking as [nome, val], i}
              <li class="ranking-item">
                <span class="ranking-num">{i + 1}</span>
                <div class="ranking-info">
                  <div class="ranking-name">{nome}</div>
                  <div class="ranking-sub">menor preço registrado</div>
                </div>
                <span class="ranking-val">R$ {val.toFixed(2)}</span>
              </li>
            {/each}
          </ul>
        {/if}
      </div>
    </div>
  </div>

</main>

<style>
  :global(:root) {
    --bg: #09090b; --bg2: #111113; --bg3: #1c1c1f; --bg4: #242428;
    --border: #27272a; --border2: #3f3f46;
    --text: #fafafa; --text2: #a1a1aa; --text3: #52525b;
    --green: #00ff87; --green2: #00c968; --red: #ff4466;
    --mono: 'JetBrains Mono', monospace; --display: 'Syne', sans-serif;
  }
  :global(body) { background: var(--bg); color: var(--text); font-family: var(--display); font-size: 14px; min-height: 100vh; overflow-x: hidden; }
  :global(body::before) { content: ''; position: fixed; inset: 0; background-image: url("data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='noise'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23noise)' opacity='1'/%3E%3C/svg%3E"); opacity: 0.03; pointer-events: none; z-index: 0; }

  header { position: sticky; top: 0; z-index: 100; display: flex; align-items: center; gap: 24px; padding: 0 32px; height: 60px; background: rgba(9,9,11,0.85); backdrop-filter: blur(20px); border-bottom: 1px solid var(--border); }
  .logo { font-family: var(--display); font-size: 15px; font-weight: 800; letter-spacing: -0.02em; flex-shrink: 0; }
  .logo :global(span) { color: var(--green); }
  nav { display: flex; gap: 4px; }
  .nav-link { font-family: var(--mono); font-size: 11px; color: var(--text3); text-decoration: none; padding: 4px 10px; border-radius: 6px; transition: all 0.15s; }
  .nav-link:hover { color: var(--text2); background: var(--bg3); }
  .nav-link.active { color: var(--green); background: rgba(0,255,135,0.08); }
  .header-right { margin-left: auto; display: flex; align-items: center; gap: 20px; }
  .last-update { font-family: var(--mono); font-size: 11px; color: var(--text3); }
  .live-dot { display: flex; align-items: center; gap: 6px; font-family: var(--mono); font-size: 11px; color: var(--text2); }
  .live-dot::before { content: ''; width: 7px; height: 7px; border-radius: 50%; background: var(--green); box-shadow: 0 0 8px var(--green); animation: pulse 2s ease infinite; }
  @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.3; } }

  main { position: relative; z-index: 1; max-width: 1280px; margin: 0 auto; padding: 40px 32px; }
  .section-title { font-size: 11px; font-weight: 600; letter-spacing: 0.15em; text-transform: uppercase; color: var(--text3); margin-bottom: 16px; font-family: var(--mono); }
  .stats-row { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-bottom: 40px; }
  .stat-card { background: var(--bg2); border: 1px solid var(--border); border-radius: 12px; padding: 20px 24px; position: relative; overflow: hidden; transition: border-color 0.2s; }
  .stat-card:hover { border-color: var(--border2); }
  .stat-card::after { content: ''; position: absolute; top: 0; left: 0; right: 0; height: 1px; background: linear-gradient(90deg, transparent, var(--green), transparent); opacity: 0; transition: opacity 0.3s; }
  .stat-card:hover::after { opacity: 0.5; }
  .stat-label { font-family: var(--mono); font-size: 10px; color: var(--text3); text-transform: uppercase; letter-spacing: 0.1em; margin-bottom: 8px; }
  .stat-val { font-size: 32px; font-weight: 700; letter-spacing: -0.03em; color: var(--text); line-height: 1; margin-bottom: 4px; }
  .stat-val.green { color: var(--green); }
  .stat-sub { font-family: var(--mono); font-size: 11px; color: var(--text3); }

  .grid-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-bottom: 20px; }
  .card { background: var(--bg2); border: 1px solid var(--border); border-radius: 12px; overflow: hidden; }
  .card-header { display: flex; align-items: center; justify-content: space-between; padding: 18px 22px; border-bottom: 1px solid var(--border); }
  .card-title { font-size: 13px; font-weight: 600; color: var(--text); letter-spacing: -0.01em; }
  .card-meta { font-family: var(--mono); font-size: 10px; color: var(--text3); }
  .card-body { padding: 20px 22px; }

  .produto-selector { border-bottom: 1px solid var(--border); }
  .search-wrap { display: flex; align-items: center; gap: 8px; padding: 12px 22px; border-bottom: 1px solid var(--border); }
  .search-wrap svg { color: var(--text3); flex-shrink: 0; }
  .search-input { background: none; border: none; outline: none; color: var(--text); font-family: var(--mono); font-size: 12px; flex: 1; }
  .search-input::placeholder { color: var(--text3); }
  .clear-btn { background: none; border: none; color: var(--text3); cursor: pointer; font-size: 16px; line-height: 1; padding: 0 2px; transition: color 0.15s; }
  .clear-btn:hover { color: var(--text); }
  .produto-tabs { display: flex; gap: 6px; flex-wrap: wrap; padding: 12px 22px; min-height: 50px; }
  .tab { background: none; border: 1px solid var(--border); color: var(--text2); font-family: var(--mono); font-size: 11px; padding: 5px 12px; border-radius: 20px; cursor: pointer; transition: all 0.15s; white-space: nowrap; max-width: 200px; overflow: hidden; text-overflow: ellipsis; }
  .tab:hover { border-color: var(--border2); color: var(--text); }
  .tab.active { background: var(--green); border-color: var(--green); color: #000; font-weight: 500; }
  .chart-wrap { position: relative; height: 260px; padding: 20px 22px; }

  .price-table { width: 100%; border-collapse: collapse; }
  .price-table th { font-family: var(--mono); font-size: 10px; color: var(--text3); text-transform: uppercase; letter-spacing: 0.08em; text-align: left; padding: 0 12px 10px 0; border-bottom: 1px solid var(--border); }
  .price-table td { padding: 10px 12px 10px 0; font-size: 13px; color: var(--text2); border-bottom: 1px solid var(--border); vertical-align: middle; }
  .price-table tr:last-child td { border-bottom: none; }
  .price-table td.val { font-family: var(--mono); font-weight: 500; color: var(--text); }
  .price-table td.val.best { color: var(--green); }
  .price-table td.val.worst { color: var(--red); }
  .price-table td.store { max-width: 200px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .price-table td.when { font-family: var(--mono); font-size: 11px; color: var(--text3); }
  .badge { display: inline-block; font-family: var(--mono); font-size: 9px; padding: 2px 6px; border-radius: 4px; font-weight: 500; margin-left: 6px; vertical-align: middle; }
  .badge.best { background: rgba(0,255,135,0.12); color: var(--green); }
  .badge.worst { background: rgba(255,68,102,0.12); color: var(--red); }

  .ranking-list { list-style: none; }
  .ranking-item { display: flex; align-items: center; gap: 14px; padding: 12px 0; border-bottom: 1px solid var(--border); }
  .ranking-item:last-child { border-bottom: none; }
  .ranking-num { font-family: var(--mono); font-size: 11px; color: var(--text3); width: 20px; flex-shrink: 0; text-align: center; }
  .ranking-info { flex: 1; min-width: 0; }
  .ranking-name { font-size: 13px; color: var(--text); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; margin-bottom: 2px; }
  .ranking-sub { font-family: var(--mono); font-size: 10px; color: var(--text3); }
  .ranking-val { font-family: var(--mono); font-size: 13px; font-weight: 500; color: var(--green); white-space: nowrap; }

  .placeholder { display: flex; align-items: center; justify-content: center; height: 60px; font-family: var(--mono); font-size: 12px; color: var(--text3); }
  @keyframes shimmer { 0% { opacity: 0.3; } 50% { opacity: 0.6; } 100% { opacity: 0.3; } }
  .loading { animation: shimmer 1.2s ease infinite; }

  @media (max-width: 900px) {
    .grid-2 { grid-template-columns: 1fr; }
    .stats-row { grid-template-columns: repeat(2, 1fr); }
    main { padding: 24px 16px; }
    header { padding: 0 16px; }
  }
</style>
