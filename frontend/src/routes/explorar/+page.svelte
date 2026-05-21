<script lang="ts">
  import { PUBLIC_LOCAL } from '$env/static/public';
  import { sbPost } from '$lib/supabase';

  type Estab   = { nm_fan?: string; nm_emp?: string };
  type Produto = { gtin?: string; desc: string; valor: string; tempo?: string; estabelecimento: Estab };
  type WatchItem = { gtin: string; desc: string; vendas: number };

  const BASE = 'https://menorpreco.notaparana.pr.gov.br';

  let termo   = $state('');
  let raio    = $state(5);
  let status  = $state<{ tipo: 'loading' | 'error' | ''; msg: string }>({ tipo: '', msg: '' });
  let grupos  = $state<Array<[string, Produto[]]>>([]);
  let abertos = $state(new Set<string>());

  let mGtins = $state(0);
  let mTotal = $state(0);
  let mMin   = $state('—');
  let mMax   = $state('—');
  let mostrarMetrics = $state(false);

  let watchlist = $state<WatchItem[]>(
    JSON.parse(typeof localStorage !== 'undefined' ? (localStorage.getItem('watchlist') || '[]') : '[]')
  );
  let toast = $state('');
  let toastVisible = $state(false);

  let buscando = $state(false);
  let salvandoSupabase = $state(false);

  async function buscar() {
    if (!termo.trim()) return;
    buscando = true;
    mostrarMetrics = false;
    grupos = [];
    status = { tipo: 'loading', msg: 'buscando categorias...' };

    try {
      const catResp = await fetch(
        `${BASE}/api/v1/categorias?local=${PUBLIC_LOCAL}&termo=${encodeURIComponent(termo)}&raio=${raio}`
      );
      const cats: Array<{ id: number; desc: string; qtd: number }> = (await catResp.json()).categorias || [];

      if (!cats.length) {
        status = { tipo: '', msg: 'nenhum resultado.' };
        buscando = false;
        return;
      }

      let todos: Produto[] = [];
      for (const cat of cats) {
        status = { tipo: 'loading', msg: `${cat.desc} — ${cat.qtd} registros...` };
        let offset = 0;
        while (true) {
          const resp = await fetch(
            `${BASE}/api/v1/produtos?local=${PUBLIC_LOCAL}&termo=${encodeURIComponent(termo)}&categoria=${cat.id}&offset=${offset}&raio=${raio}&data=-1&ordem=0`
          );
          const data = await resp.json();
          const page: Produto[] = data.produtos || [];
          todos = todos.concat(page);
          offset += 50;
          if (offset >= (data.total || 0) || !page.length) break;
        }
      }

      processarResultados(todos);
    } catch (e: unknown) {
      status = { tipo: 'error', msg: 'erro: ' + (e instanceof Error ? e.message : String(e)) };
    }

    buscando = false;
  }

  function processarResultados(produtos: Produto[]) {
    const map: Record<string, Produto[]> = {};
    for (const p of produtos) {
      const key = p.gtin?.trim() || '__sem_gtin__';
      if (!map[key]) map[key] = [];
      map[key].push(p);
    }

    const vals = produtos.map(p => parseFloat(p.valor));
    const gtinsValidos = Object.keys(map).filter(k => k !== '__sem_gtin__').length;

    mGtins = gtinsValidos;
    mTotal = produtos.length;
    mMin = vals.length ? 'R$ ' + Math.min(...vals).toFixed(2) : '—';
    mMax = vals.length ? 'R$ ' + Math.max(...vals).toFixed(2) : '—';
    mostrarMetrics = true;

    grupos = Object.entries(map).sort((a, b) => {
      if (a[0] === '__sem_gtin__') return 1;
      if (b[0] === '__sem_gtin__') return -1;
      return b[1].length - a[1].length;
    });

    status = { tipo: '', msg: `${gtinsValidos} GTINs encontrados` };
  }

  function toggleAberto(gtin: string) {
    const next = new Set(abertos);
    if (next.has(gtin)) next.delete(gtin); else next.add(gtin);
    abertos = next;
  }

  function isWatched(gtin: string) {
    return watchlist.some(w => w.gtin === gtin);
  }

  function toggleWatch(gtin: string, desc: string, vendas: number) {
    const idx = watchlist.findIndex(w => w.gtin === gtin);
    if (idx >= 0) {
      watchlist = watchlist.filter(w => w.gtin !== gtin);
    } else {
      watchlist = [...watchlist, { gtin, desc, vendas }];
    }
    salvarWatchlist();
  }

  function remover(gtin: string) {
    watchlist = watchlist.filter(w => w.gtin !== gtin);
    salvarWatchlist();
  }

  function limparLista() {
    if (!watchlist.length || !confirm('Limpar toda a lista?')) return;
    watchlist = [];
    salvarWatchlist();
  }

  function salvarWatchlist() {
    localStorage.setItem('watchlist', JSON.stringify(watchlist));
  }

  function exportar() {
    if (!watchlist.length) return;
    const linhas = watchlist.map(w =>
      `    ("${w.gtin}", "${w.desc.replace(/"/g, '\\"')}", 5),`
    ).join('\n');
    const codigo = `# Cole isso no seu collector.py, substituindo PRODUTOS_MONITORADOS:\n\nPRODUTOS_MONITORADOS = [\n${linhas}\n]\n\n# Formato: (gtin, descricao_referencia, raio_km)\n`;
    navigator.clipboard.writeText(codigo).then(() => mostrarToast('copiado para a área de transferência!'));
  }

  async function salvarNoSupabase() {
    if (!watchlist.length || salvandoSupabase) return;
    salvandoSupabase = true;
    try {
      for (const w of watchlist) {
        await sbPost(
          'produtos',
          { gtin: w.gtin, descricao: w.desc, raio_km: raio, monitorado: true },
          'resolution=merge-duplicates'
        );
      }
      const n = watchlist.length;
      mostrarToast(`${n} produto${n > 1 ? 's' : ''} adicionado${n > 1 ? 's' : ''} ao monitoramento!`);
    } catch (e: unknown) {
      mostrarToast('erro: ' + (e instanceof Error ? e.message : String(e)));
    } finally {
      salvandoSupabase = false;
    }
  }

  function mostrarToast(msg: string) {
    toast = msg;
    toastVisible = true;
    setTimeout(() => { toastVisible = false; }, 2500);
  }
</script>

<svelte:head>
  <title>Explorador · Menor Preço PR</title>
  <link rel="preconnect" href="https://fonts.googleapis.com" />
  <link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans:wght@300;400;500&display=swap" rel="stylesheet" />
</svelte:head>

<div class="layout">

  <header>
    <a href="/" class="logo">pricewatch.pr</a>

    <div class="search-bar">
      <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5">
        <circle cx="6.5" cy="6.5" r="5"/><path d="M10.5 10.5L14 14"/>
      </svg>
      <input
        type="text"
        placeholder="buscar produto... (ex: huevitos, arroz, café)"
        bind:value={termo}
        autocomplete="off"
        onkeydown={(e) => e.key === 'Enter' && buscar()}
      />
      <div class="raio-wrap">
        <span>raio</span>
        <input type="number" bind:value={raio} min="1" max="20" />
        <span>km</span>
      </div>
    </div>

    <button class="btn-buscar" onclick={buscar} disabled={buscando}>buscar</button>
    <div class="header-spacer"></div>
    {#if mostrarMetrics}
      <div class="header-count">{mGtins} GTINs · {mTotal} registros</div>
    {/if}
  </header>

  <main class="main-pane">
    <div class="status-bar" class:loading={status.tipo === 'loading'} class:error={status.tipo === 'error'}>
      {#if status.tipo === 'loading'}
        <span class="spinner"></span>
      {/if}
      {status.msg}
    </div>

    {#if mostrarMetrics}
      <div class="metrics">
        <div class="metric"><div class="metric-label">GTINs</div><div class="metric-val green">{mGtins}</div></div>
        <div class="metric"><div class="metric-label">Registros</div><div class="metric-val">{mTotal}</div></div>
        <div class="metric"><div class="metric-label">Menor preço</div><div class="metric-val">{mMin}</div></div>
        <div class="metric"><div class="metric-label">Maior preço</div><div class="metric-val">{mMax}</div></div>
      </div>
    {/if}

    {#if grupos.length === 0 && !buscando}
      <div class="empty">
        <div class="empty-title">pricewatch.pr</div>
        busque um produto acima para explorar os GTINs<br>
        selecione os que quiser monitorar →
      </div>
    {/if}

    {#each grupos as [gtin, items]}
      {@const semGtin = gtin === '__sem_gtin__'}
      {@const vals = items.map(p => parseFloat(p.valor))}
      {@const gMin = Math.min(...vals)}
      {@const gMax = Math.max(...vals)}
      {@const descs = [...new Set(items.map(p => p.desc))]}
      {@const watched = !semGtin && isWatched(gtin)}
      {@const aberto = abertos.has(gtin)}

      <div class="gtin-card" class:selected={watched}>

        <div class="gtin-header" role="button" tabindex="0"
          onclick={() => toggleAberto(gtin)}
          onkeydown={(e) => e.key === 'Enter' && toggleAberto(gtin)}
        >
          <div
            class="check"
            class:checked={watched}
            role="checkbox"
            aria-checked={watched}
            tabindex="0"
            onclick={(e) => { e.stopPropagation(); if (!semGtin) toggleWatch(gtin, descs[0], items.length); }}
            onkeydown={(e) => { if (e.key === ' ' || e.key === 'Enter') { e.stopPropagation(); if (!semGtin) toggleWatch(gtin, descs[0], items.length); }}}
          ></div>
          <div class="gtin-code" class:no-gtin={semGtin}>{semGtin ? 'sem GTIN' : gtin}</div>
          <div class="gtin-desc">
            {descs[0]}{#if descs.length > 1}&nbsp;<span style="color:var(--text3);font-size:11px">+{descs.length - 1} var.</span>{/if}
          </div>
          <div class="gtin-range">R$ {gMin.toFixed(2)} – R$ {gMax.toFixed(2)}</div>
          <div class="gtin-count">{items.length} venda{items.length > 1 ? 's' : ''}</div>
        </div>

        {#if aberto}
          <div class="gtin-body open">
            <div class="desc-list">
              {#each descs.slice(0, 5) as d}
                <div class="desc-item">{d}</div>
              {/each}
              {#if descs.length > 5}
                <div class="desc-item" style="color:var(--text3)">+{descs.length - 5} outras descrições</div>
              {/if}
            </div>
            <table class="vendas-table">
              <thead><tr><th>preço</th><th>estabelecimento</th><th>quando</th></tr></thead>
              <tbody>
                {#each [...items].sort((a, b) => parseFloat(a.valor) - parseFloat(b.valor)).slice(0, 8) as p}
                  {@const v = parseFloat(p.valor)}
                  {@const loja = (p.estabelecimento?.nm_fan || p.estabelecimento?.nm_emp || '?').substring(0, 40)}
                  <tr>
                    <td class="val" class:min={v === gMin} class:max={v === gMax}>R$ {v.toFixed(2)}</td>
                    <td>{loja}</td>
                    <td class="ago">{p.tempo || ''}</td>
                  </tr>
                {/each}
              </tbody>
            </table>
          </div>
        {/if}

      </div>
    {/each}
  </main>

  <aside class="sidebar">
    <div class="sidebar-header">
      <span class="sidebar-title">monitorando</span>
      <span class="sidebar-badge">{watchlist.length}</span>
    </div>

    <div class="watchlist">
      {#if watchlist.length === 0}
        <div class="watchlist-empty">
          nenhum produto selecionado ainda.<br>marque os checkboxes ao buscar.
        </div>
      {:else}
        {#each watchlist as w}
          <div class="watch-item">
            <div class="watch-dot"></div>
            <div class="watch-info">
              <div class="watch-name">{w.desc}</div>
              <div class="watch-gtin">{w.gtin}</div>
            </div>
            <button class="watch-remove" onclick={() => remover(w.gtin)} title="remover">×</button>
          </div>
        {/each}
      {/if}
    </div>

    <div class="sidebar-footer">
      <button class="btn-export" onclick={salvarNoSupabase} disabled={watchlist.length === 0 || salvandoSupabase}>
        {#if salvandoSupabase}
          <span class="spinner"></span> salvando...
        {:else}
          + adicionar ao monitoramento
        {/if}
      </button>
      <button class="btn-secondary" onclick={exportar} disabled={watchlist.length === 0}>copiar para collector.py</button>
      <button class="btn-clear" onclick={limparLista}>limpar lista</button>
    </div>
  </aside>

</div>

<div class="copy-toast" class:show={toastVisible}>{toast}</div>

<style>
  :global(body) { background: #0f0f0f; color: #e8e8e8; font-family: 'IBM Plex Sans', sans-serif; font-size: 14px; min-height: 100vh; }

  .layout { display: grid; grid-template-columns: 1fr 320px; grid-template-rows: 56px 1fr; height: 100vh; overflow: hidden; }
  header { grid-column: 1 / -1; display: flex; align-items: center; gap: 16px; padding: 0 24px; border-bottom: 1px solid #2e2e2e; background: #0f0f0f; }
  .logo { font-family: 'IBM Plex Mono', monospace; font-size: 13px; font-weight: 500; color: #00e5a0; letter-spacing: 0.05em; white-space: nowrap; text-decoration: none; }
  .search-bar { display: flex; align-items: center; gap: 8px; flex: 1; max-width: 520px; background: #1a1a1a; border: 1px solid #2e2e2e; border-radius: 6px; padding: 0 12px; transition: border-color 0.15s; }
  .search-bar:focus-within { border-color: #00e5a0; }
  .search-bar svg { color: #555; flex-shrink: 0; }
  .search-bar input { background: none; border: none; outline: none; color: #e8e8e8; font-family: 'IBM Plex Sans', sans-serif; font-size: 13px; flex: 1; padding: 9px 0; }
  .search-bar input::placeholder { color: #555; }
  .raio-wrap { display: flex; align-items: center; gap: 6px; font-size: 12px; color: #888; border-left: 1px solid #2e2e2e; padding-left: 12px; white-space: nowrap; }
  .raio-wrap input { width: 40px; background: none; border: none; outline: none; color: #e8e8e8; font-family: 'IBM Plex Mono', monospace; font-size: 12px; text-align: center; }
  .btn-buscar { background: #00e5a0; color: #000; border: none; border-radius: 5px; padding: 7px 16px; font-family: 'IBM Plex Mono', monospace; font-size: 12px; font-weight: 500; cursor: pointer; white-space: nowrap; transition: background 0.15s, transform 0.1s; }
  .btn-buscar:hover { background: #00b87a; }
  .btn-buscar:active { transform: scale(0.97); }
  .btn-buscar:disabled { opacity: 0.4; cursor: not-allowed; }
  .header-spacer { flex: 1; }
  .header-count { font-family: 'IBM Plex Mono', monospace; font-size: 11px; color: #555; white-space: nowrap; }
  .main-pane { overflow-y: auto; padding: 20px 24px; border-right: 1px solid #2e2e2e; }
  .status-bar { font-family: 'IBM Plex Mono', monospace; font-size: 11px; color: #555; margin-bottom: 16px; height: 16px; display: flex; align-items: center; gap: 6px; }
  .status-bar.loading { color: #00e5a0; }
  .status-bar.error   { color: #ff4d4d; }
  .metrics { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; margin-bottom: 20px; }
  .metric { background: #1a1a1a; border: 1px solid #2e2e2e; border-radius: 8px; padding: 12px 14px; }
  .metric-label { font-size: 10px; font-family: 'IBM Plex Mono', monospace; color: #555; text-transform: uppercase; letter-spacing: 0.08em; margin-bottom: 4px; }
  .metric-val { font-size: 22px; font-weight: 300; color: #e8e8e8; }
  .metric-val.green { color: #00e5a0; }
  .gtin-card { background: #1a1a1a; border: 1px solid #2e2e2e; border-radius: 8px; margin-bottom: 8px; overflow: hidden; transition: border-color 0.15s; }
  .gtin-card:hover { border-color: #3a3a3a; }
  .gtin-card.selected { border-color: #00e5a0; }
  .gtin-header { display: grid; grid-template-columns: 20px 140px 1fr auto auto; align-items: center; gap: 12px; padding: 12px 14px; cursor: pointer; }
  .check { width: 16px; height: 16px; border: 1.5px solid #3a3a3a; border-radius: 4px; display: flex; align-items: center; justify-content: center; flex-shrink: 0; transition: all 0.15s; cursor: pointer; }
  .check.checked { background: #00e5a0; border-color: #00e5a0; }
  .check.checked::after { content: ''; width: 8px; height: 5px; border-left: 1.5px solid #000; border-bottom: 1.5px solid #000; transform: rotate(-45deg) translateY(-1px); display: block; }
  .gtin-code { font-family: 'IBM Plex Mono', monospace; font-size: 11px; color: #555; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .gtin-code.no-gtin { color: #f5a623; }
  .gtin-desc { font-size: 13px; color: #e8e8e8; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .gtin-range { font-family: 'IBM Plex Mono', monospace; font-size: 11px; color: #888; white-space: nowrap; }
  .gtin-count { font-family: 'IBM Plex Mono', monospace; font-size: 10px; background: #242424; color: #555; padding: 2px 7px; border-radius: 20px; white-space: nowrap; }
  .gtin-body { border-top: 1px solid #2e2e2e; padding: 10px 14px 10px 46px; }
  .desc-list { margin-bottom: 10px; }
  .desc-item { font-size: 12px; color: #888; padding: 2px 0; }
  .desc-item::before { content: '· '; color: #555; }
  .vendas-table { width: 100%; border-collapse: collapse; font-size: 12px; }
  .vendas-table th { font-family: 'IBM Plex Mono', monospace; font-size: 10px; color: #555; text-transform: uppercase; letter-spacing: 0.06em; text-align: left; padding: 4px 8px 6px 0; border-bottom: 1px solid #2e2e2e; }
  .vendas-table td { padding: 5px 8px 5px 0; color: #888; border-bottom: 1px solid #2e2e2e; }
  .vendas-table tr:last-child td { border-bottom: none; }
  .vendas-table td.val { font-family: 'IBM Plex Mono', monospace; color: #e8e8e8; }
  .vendas-table td.val.min { color: #00e5a0; }
  .vendas-table td.val.max { color: #ff4d4d; }
  .vendas-table td.ago { color: #555; font-size: 11px; }
  .empty { text-align: center; padding: 80px 0; color: #555; font-size: 13px; line-height: 2; }
  .empty-title { font-size: 18px; font-weight: 300; color: #888; margin-bottom: 8px; font-family: 'IBM Plex Mono', monospace; }
  .sidebar { display: flex; flex-direction: column; overflow: hidden; background: #0f0f0f; }
  .sidebar-header { padding: 16px 20px 12px; border-bottom: 1px solid #2e2e2e; display: flex; align-items: center; justify-content: space-between; }
  .sidebar-title { font-family: 'IBM Plex Mono', monospace; font-size: 11px; color: #555; text-transform: uppercase; letter-spacing: 0.08em; }
  .sidebar-badge { background: #00e5a0; color: #000; font-family: 'IBM Plex Mono', monospace; font-size: 10px; font-weight: 500; padding: 1px 7px; border-radius: 20px; min-width: 20px; text-align: center; }
  .watchlist { flex: 1; overflow-y: auto; padding: 12px 16px; }
  .watch-item { display: flex; align-items: flex-start; gap: 10px; padding: 10px 12px; background: #1a1a1a; border: 1px solid #2e2e2e; border-radius: 6px; margin-bottom: 6px; position: relative; }
  .watch-item:hover .watch-remove { opacity: 1; }
  .watch-dot { width: 6px; height: 6px; border-radius: 50%; background: #00e5a0; margin-top: 5px; flex-shrink: 0; }
  .watch-info { flex: 1; min-width: 0; }
  .watch-name { font-size: 12px; color: #e8e8e8; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; margin-bottom: 2px; }
  .watch-gtin { font-family: 'IBM Plex Mono', monospace; font-size: 10px; color: #555; }
  .watch-remove { position: absolute; top: 8px; right: 8px; opacity: 0; background: none; border: none; color: #555; cursor: pointer; font-size: 14px; padding: 2px 4px; border-radius: 3px; transition: opacity 0.15s, color 0.15s; line-height: 1; }
  .watch-remove:hover { color: #ff4d4d; }
  .watchlist-empty { text-align: center; padding: 40px 0; color: #555; font-size: 12px; line-height: 2; }
  .sidebar-footer { padding: 14px 16px; border-top: 1px solid #2e2e2e; display: flex; flex-direction: column; gap: 8px; }
  .btn-export { width: 100%; background: #00e5a0; color: #000; border: none; border-radius: 5px; padding: 9px; font-family: 'IBM Plex Mono', monospace; font-size: 12px; font-weight: 500; cursor: pointer; transition: background 0.15s; letter-spacing: 0.03em; display: flex; align-items: center; justify-content: center; gap: 6px; }
  .btn-export:hover { background: #00b87a; }
  .btn-export:disabled { opacity: 0.3; cursor: not-allowed; }
  .btn-secondary { width: 100%; background: none; color: #555; border: 1px solid #2e2e2e; border-radius: 5px; padding: 7px; font-family: 'IBM Plex Mono', monospace; font-size: 11px; cursor: pointer; transition: all 0.15s; }
  .btn-secondary:hover { border-color: #3a3a3a; color: #888; }
  .btn-secondary:disabled { opacity: 0.3; cursor: not-allowed; }
  .btn-clear { width: 100%; background: none; color: #555; border: 1px solid #2e2e2e; border-radius: 5px; padding: 7px; font-family: 'IBM Plex Mono', monospace; font-size: 11px; cursor: pointer; transition: all 0.15s; }
  .btn-clear:hover { border-color: #ff4d4d; color: #ff4d4d; }
  .copy-toast { position: fixed; bottom: 24px; left: 50%; transform: translateX(-50%) translateY(10px); background: #00e5a0; color: #000; font-family: 'IBM Plex Mono', monospace; font-size: 12px; font-weight: 500; padding: 8px 20px; border-radius: 20px; opacity: 0; transition: all 0.2s; pointer-events: none; z-index: 100; }
  .copy-toast.show { opacity: 1; transform: translateX(-50%) translateY(0); }
  @keyframes spin { to { transform: rotate(360deg); } }
  .spinner { display: inline-block; width: 10px; height: 10px; border: 1.5px solid #555; border-top-color: #00e5a0; border-radius: 50%; animation: spin 0.7s linear infinite; vertical-align: middle; }
</style>
