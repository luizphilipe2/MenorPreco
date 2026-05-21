<script lang="ts">
  import { onMount } from 'svelte';
  import { sbQuery, sbPatch } from '$lib/supabase';
  import { PUBLIC_GITHUB_TOKEN, PUBLIC_GITHUB_OWNER, PUBLIC_GITHUB_REPO } from '$env/static/public';

  type Produto     = { gtin: string; descricao: string; raio_km: number; monitorado: boolean };
  type LogItem     = { id: number; executado_em: string; sucesso: boolean; termo: string; total_novos: number; total_vistos: number; erro: string };
  type WorkflowRun = { id: number; run_number: number; status: string; conclusion: string | null; created_at: string; updated_at: string; html_url: string };
  type PrecoItem   = { id: number; gtin: string; valor: number; datahora_venda: string };

  let produtos     = $state<Produto[]>([]);
  let logs         = $state<LogItem[]>([]);
  let logOffset    = $state(0);
  const LOG_PAGE   = 20;

  let workflowRuns   = $state<WorkflowRun[]>([]);
  let workflowStatus = $state<'idle' | 'loading' | 'erro'>('idle');

  let precos       = $state<PrecoItem[]>([]);
  let precosOffset = $state(0);
  const PRECOS_PAGE = 30;

  let coletandoStatus = $state<'idle' | 'loading' | 'ok' | 'erro'>('idle');
  let coletandoMsg    = $state('');
  let salvando        = $state<Record<string, boolean>>({});

  function duracao(inicio: string, fim: string) {
    const s = Math.round((new Date(fim).getTime() - new Date(inicio).getTime()) / 1000);
    return s < 60 ? `${s}s` : `${Math.floor(s / 60)}m ${s % 60}s`;
  }

  function fmt(iso: string) {
    const dt = new Date(iso);
    return dt.toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit', year: '2-digit' })
      + ' ' + dt.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' });
  }

  async function carregarProdutos() {
    produtos = await sbQuery<Produto>('produtos', 'select=gtin,descricao,raio_km,monitorado&order=descricao');
  }

  async function carregarWorkflowRuns() {
    workflowStatus = 'loading';
    try {
      const resp = await fetch(
        `https://api.github.com/repos/${PUBLIC_GITHUB_OWNER}/${PUBLIC_GITHUB_REPO}/actions/workflows/coletar.yml/runs?per_page=10`,
        { headers: { Authorization: `Bearer ${PUBLIC_GITHUB_TOKEN}`, Accept: 'application/vnd.github+json' } }
      );
      if (!resp.ok) throw new Error(`GitHub ${resp.status}: ${resp.statusText}`);
      const data = await resp.json();
      workflowRuns = data.workflow_runs ?? [];
      workflowStatus = 'idle';
    } catch {
      workflowStatus = 'erro';
    }
  }

  async function carregarPrecos() {
    const page = await sbQuery<PrecoItem>(
      'precos',
      `select=id,gtin,valor,datahora_venda&order=id.desc&limit=${PRECOS_PAGE}&offset=${precosOffset}`
    );
    precos = precosOffset === 0 ? page : [...precos, ...page];
  }

  async function carregarMaisPrecos() {
    precosOffset += PRECOS_PAGE;
    await carregarPrecos();
  }

  async function carregarLogs() {
    const pagina = await sbQuery<LogItem>(
      'logs_coleta', `select=*&order=executado_em.desc&limit=${LOG_PAGE}&offset=${logOffset}`
    );
    logs = logOffset === 0 ? pagina : [...logs, ...pagina];
  }

  async function toggleMonitorado(p: Produto) {
    salvando = { ...salvando, [p.gtin]: true };
    try {
      await sbPatch('produtos', `gtin=eq.${p.gtin}`, { monitorado: !p.monitorado });
      produtos = produtos.map(x => x.gtin === p.gtin ? { ...x, monitorado: !x.monitorado } : x);
    } finally {
      salvando = { ...salvando, [p.gtin]: false };
    }
  }

  async function atualizarRaio(p: Produto, valor: number) {
    if (isNaN(valor) || valor < 1) return;
    await sbPatch('produtos', `gtin=eq.${p.gtin}`, { raio_km: valor });
    produtos = produtos.map(x => x.gtin === p.gtin ? { ...x, raio_km: valor } : x);
  }

  async function coletarAgora() {
    coletandoStatus = 'loading';
    coletandoMsg = 'disparando workflow...';
    try {
      const resp = await fetch(
        `https://api.github.com/repos/${PUBLIC_GITHUB_OWNER}/${PUBLIC_GITHUB_REPO}/actions/workflows/coletar.yml/dispatches`,
        {
          method: 'POST',
          headers: {
            Authorization: `Bearer ${PUBLIC_GITHUB_TOKEN}`,
            Accept: 'application/vnd.github+json',
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({ ref: 'main' }),
        }
      );
      if (!resp.ok) throw new Error(`GitHub ${resp.status}: ${resp.statusText}`);
      coletandoStatus = 'ok';
      coletandoMsg = 'workflow disparado! acompanhe em github.com/' + PUBLIC_GITHUB_OWNER + '/' + PUBLIC_GITHUB_REPO + '/actions';
    } catch (e: unknown) {
      coletandoStatus = 'erro';
      coletandoMsg = e instanceof Error ? e.message : String(e);
    }
  }

  async function carregarMaisLogs() {
    logOffset += LOG_PAGE;
    await carregarLogs();
  }

  onMount(async () => {
    await Promise.all([carregarProdutos(), carregarLogs(), carregarWorkflowRuns(), carregarPrecos()]);
  });
</script>

<svelte:head>
  <title>Admin · PriceWatch</title>
  <link rel="preconnect" href="https://fonts.googleapis.com" />
  <link href="https://fonts.googleapis.com/css2?family=Syne:wght@400;500;600;700;800&family=JetBrains+Mono:wght@300;400;500&display=swap" rel="stylesheet" />
</svelte:head>

<header>
  <div class="logo">price<span>watch</span>.pr</div>
  <nav>
    <a href="/" class="nav-link">dashboard</a>
    <a href="/explorar" class="nav-link">explorar</a>
    <a href="/admin" class="nav-link active">admin</a>
  </nav>
</header>

<main>

  <!-- Produtos monitorados -->
  <div class="section-header">
    <div>
      <div class="section-title">produtos monitorados</div>
      <div class="section-sub">{produtos.filter(p => p.monitorado).length} de {produtos.length} ativo{produtos.filter(p => p.monitorado).length !== 1 ? 's' : ''}</div>
    </div>
    <div class="coleta-wrap">
      <button class="btn-coletar" onclick={coletarAgora} disabled={coletandoStatus === 'loading'}>
        {#if coletandoStatus === 'loading'}
          <span class="spinner"></span> disparando...
        {:else}
          ▶ coletar agora
        {/if}
      </button>
      {#if coletandoMsg}
        <span class="coleta-msg" class:ok={coletandoStatus === 'ok'} class:err={coletandoStatus === 'erro'}>
          {coletandoMsg}
        </span>
      {/if}
    </div>
  </div>

  <div class="card" style="margin-bottom: 40px">
    {#if produtos.length === 0}
      <div class="placeholder">carregando...</div>
    {:else}
      <table class="produtos-table">
        <thead>
          <tr>
            <th>monitorado</th>
            <th>GTIN</th>
            <th>descrição</th>
            <th>raio (km)</th>
          </tr>
        </thead>
        <tbody>
          {#each produtos as p}
            <tr class:monitored={p.monitorado}>
              <td>
                <button
                  class="toggle"
                  class:on={p.monitorado}
                  class:saving={salvando[p.gtin]}
                  onclick={() => toggleMonitorado(p)}
                  title={p.monitorado ? 'desativar' : 'ativar'}
                >
                  <span class="toggle-knob"></span>
                </button>
              </td>
              <td class="mono dimmed">{p.gtin}</td>
              <td class="desc">{p.descricao}</td>
              <td>
                <input
                  class="raio-input"
                  type="number"
                  value={p.raio_km}
                  min="1"
                  max="50"
                  onchange={(e) => atualizarRaio(p, parseInt((e.target as HTMLInputElement).value))}
                />
              </td>
            </tr>
          {/each}
        </tbody>
      </table>
    {/if}
  </div>

  <!-- GitHub Actions runs -->
  <div class="section-title" style="margin-top: 40px">github actions</div>
  <div class="card" style="margin-bottom: 40px">
    <div class="card-header">
      <div>
        <div class="card-title">últimas execuções</div>
        <div class="card-meta">workflow: coletar.yml</div>
      </div>
      <button class="btn-reload" onclick={carregarWorkflowRuns} disabled={workflowStatus === 'loading'}>
        {workflowStatus === 'loading' ? '...' : '↻ atualizar'}
      </button>
    </div>
    <div class="card-body" style="padding: 0">
      {#if workflowStatus === 'erro'}
        <div class="placeholder" style="color: #ff4466">erro ao carregar — verifique PUBLIC_GITHUB_TOKEN</div>
      {:else if workflowRuns.length === 0}
        <div class="placeholder">{workflowStatus === 'loading' ? 'carregando...' : 'nenhuma execução encontrada'}</div>
      {:else}
        <table class="log-table">
          <thead>
            <tr><th>#</th><th>quando</th><th>status</th><th>duração</th><th>link</th></tr>
          </thead>
          <tbody>
            {#each workflowRuns as run}
              <tr>
                <td class="mono dimmed">#{run.run_number}</td>
                <td class="mono dimmed">{fmt(run.created_at)}</td>
                <td>
                  {#if run.status !== 'completed'}
                    <span class="badge pending">{run.status === 'in_progress' ? '▶ rodando' : '⏳ fila'}</span>
                  {:else}
                    <span class="badge" class:ok={run.conclusion === 'success'} class:err={run.conclusion !== 'success'}>
                      {run.conclusion === 'success' ? 'ok' : (run.conclusion ?? 'erro')}
                    </span>
                  {/if}
                </td>
                <td class="mono dimmed">{run.status === 'completed' ? duracao(run.created_at, run.updated_at) : '—'}</td>
                <td><a href={run.html_url} target="_blank" class="run-link">ver →</a></td>
              </tr>
            {/each}
          </tbody>
        </table>
      {/if}
    </div>
  </div>

  <!-- Log de coletas -->
  <div class="section-title">log de coletas</div>
  <div class="card">
    <div class="card-header">
      <div class="card-title">execuções</div>
      <div class="card-meta">GitHub Actions · a cada hora</div>
    </div>
    <div class="card-body" style="padding: 0">
      {#if logs.length === 0}
        <div class="placeholder">nenhuma execução registrada</div>
      {:else}
        <table class="log-table">
          <thead>
            <tr>
              <th>quando</th>
              <th>status</th>
              <th>termo</th>
              <th>novos</th>
              <th>vistos</th>
              <th>erro</th>
            </tr>
          </thead>
          <tbody>
            {#each logs as l}
              <tr>
                <td class="mono dimmed">{fmt(l.executado_em)}</td>
                <td><span class="badge" class:ok={l.sucesso} class:err={!l.sucesso}>{l.sucesso ? 'ok' : 'erro'}</span></td>
                <td class="mono">{l.termo || '—'}</td>
                <td class="mono" style="color: {l.total_novos > 0 ? 'var(--green)' : 'var(--text3)'}">+{l.total_novos}</td>
                <td class="mono dimmed">{l.total_vistos}</td>
                <td class="erro-cell">{l.erro || ''}</td>
              </tr>
            {/each}
          </tbody>
        </table>
        <div class="load-more-wrap">
          <button class="btn-load-more" onclick={carregarMaisLogs}>carregar mais</button>
        </div>
      {/if}
    </div>
  </div>


  <!-- Preços recentes -->
  <div class="section-title" style="margin-top: 40px">preços recentes</div>
  <div class="card">
    <div class="card-header">
      <div class="card-title">últimas coletas</div>
      <div class="card-meta">{precos.length} registros carregados</div>
    </div>
    <div class="card-body" style="padding: 0">
      {#if precos.length === 0}
        <div class="placeholder">nenhum preço registrado ainda</div>
      {:else}
        <table class="log-table">
          <thead>
            <tr><th>quando</th><th>GTIN</th><th>descrição</th><th>valor</th></tr>
          </thead>
          <tbody>
            {#each precos as p}
              {@const prod = produtos.find(x => x.gtin === p.gtin)}
              <tr>
                <td class="mono dimmed">{fmt(p.datahora_venda)}</td>
                <td class="mono dimmed">{p.gtin}</td>
                <td style="color: #a1a1aa; font-size: 12px">{prod?.descricao ?? '—'}</td>
                <td class="mono" style="color: #00ff87">R$ {Number(p.valor).toFixed(2)}</td>
              </tr>
            {/each}
          </tbody>
        </table>
        <div class="load-more-wrap">
          <button class="btn-load-more" onclick={carregarMaisPrecos}>carregar mais</button>
        </div>
      {/if}
    </div>
  </div>

</main>

<style>
  :global(body) { background: #09090b; color: #fafafa; font-family: 'Syne', sans-serif; font-size: 14px; min-height: 100vh; }

  header { position: sticky; top: 0; z-index: 100; display: flex; align-items: center; gap: 24px; padding: 0 32px; height: 60px; background: rgba(9,9,11,0.85); backdrop-filter: blur(20px); border-bottom: 1px solid #27272a; }
  .logo { font-family: 'Syne', sans-serif; font-size: 15px; font-weight: 800; letter-spacing: -0.02em; flex-shrink: 0; }
  .logo :global(span) { color: #00ff87; }
  nav { display: flex; gap: 4px; }
  .nav-link { font-family: 'JetBrains Mono', monospace; font-size: 11px; color: #52525b; text-decoration: none; padding: 4px 10px; border-radius: 6px; transition: all 0.15s; }
  .nav-link:hover { color: #a1a1aa; background: #1c1c1f; }
  .nav-link.active { color: #00ff87; background: rgba(0,255,135,0.08); }

  main { max-width: 1280px; margin: 0 auto; padding: 40px 32px; }
  .section-title { font-size: 11px; font-weight: 600; letter-spacing: 0.15em; text-transform: uppercase; color: #52525b; margin-bottom: 6px; font-family: 'JetBrains Mono', monospace; }
  .section-sub { font-family: 'JetBrains Mono', monospace; font-size: 11px; color: #3f3f46; }
  .section-header { display: flex; align-items: flex-end; justify-content: space-between; margin-bottom: 16px; }
  .coleta-wrap { display: flex; align-items: center; gap: 16px; flex-wrap: wrap; justify-content: flex-end; }
  .coleta-msg { font-family: 'JetBrains Mono', monospace; font-size: 11px; color: #52525b; max-width: 400px; }
  .coleta-msg.ok  { color: #00ff87; }
  .coleta-msg.err { color: #ff4466; }

  .btn-coletar { background: #00ff87; color: #000; border: none; border-radius: 6px; padding: 8px 18px; font-family: 'JetBrains Mono', monospace; font-size: 12px; font-weight: 500; cursor: pointer; transition: background 0.15s, transform 0.1s; display: flex; align-items: center; gap: 6px; white-space: nowrap; }
  .btn-coletar:hover { background: #00c968; }
  .btn-coletar:active { transform: scale(0.97); }
  .btn-coletar:disabled { opacity: 0.5; cursor: not-allowed; }

  .card { background: #111113; border: 1px solid #27272a; border-radius: 12px; overflow: hidden; }
  .card-header { display: flex; align-items: center; justify-content: space-between; padding: 18px 22px; border-bottom: 1px solid #27272a; }
  .card-title { font-size: 13px; font-weight: 600; color: #fafafa; }
  .card-meta { font-family: 'JetBrains Mono', monospace; font-size: 10px; color: #52525b; }
  .card-body { padding: 20px 22px; }

  .produtos-table { width: 100%; border-collapse: collapse; }
  .produtos-table th { font-family: 'JetBrains Mono', monospace; font-size: 10px; color: #52525b; text-transform: uppercase; letter-spacing: 0.08em; text-align: left; padding: 12px 16px; border-bottom: 1px solid #27272a; }
  .produtos-table td { padding: 12px 16px; border-bottom: 1px solid #1c1c1f; font-size: 13px; color: #a1a1aa; vertical-align: middle; }
  .produtos-table tr:last-child td { border-bottom: none; }
  .produtos-table tr.monitored td { color: #fafafa; }

  .toggle { width: 36px; height: 20px; border-radius: 10px; border: none; background: #27272a; cursor: pointer; position: relative; transition: background 0.2s; padding: 0; flex-shrink: 0; }
  .toggle.on { background: #00ff87; }
  .toggle.saving { opacity: 0.5; cursor: wait; }
  .toggle-knob { position: absolute; top: 3px; left: 3px; width: 14px; height: 14px; border-radius: 50%; background: #fff; transition: transform 0.2s; display: block; }
  .toggle.on .toggle-knob { transform: translateX(16px); background: #000; }

  .mono { font-family: 'JetBrains Mono', monospace; font-size: 12px; }
  .dimmed { color: #52525b !important; }
  .desc { color: #fafafa; }
  .raio-input { width: 56px; background: #1c1c1f; border: 1px solid #27272a; border-radius: 5px; color: #fafafa; font-family: 'JetBrains Mono', monospace; font-size: 12px; padding: 4px 8px; text-align: center; outline: none; transition: border-color 0.15s; }
  .raio-input:focus { border-color: #3f3f46; }

  .log-table { width: 100%; border-collapse: collapse; }
  .log-table th { font-family: 'JetBrains Mono', monospace; font-size: 10px; color: #52525b; text-transform: uppercase; letter-spacing: 0.08em; text-align: left; padding: 12px 16px; border-bottom: 1px solid #27272a; }
  .log-table td { padding: 10px 16px; font-size: 12px; color: #a1a1aa; border-bottom: 1px solid #1c1c1f; }
  .log-table tr:last-child td { border-bottom: none; }
  .badge { display: inline-block; font-family: 'JetBrains Mono', monospace; font-size: 10px; padding: 2px 8px; border-radius: 4px; font-weight: 500; }
  .badge.ok      { background: rgba(0,255,135,0.1); color: #00ff87; }
  .badge.err     { background: rgba(255,68,102,0.1); color: #ff4466; }
  .badge.pending { background: rgba(255,200,0,0.1); color: #ffc800; }

  .btn-reload { background: none; border: 1px solid #27272a; color: #52525b; font-family: 'JetBrains Mono', monospace; font-size: 11px; padding: 5px 14px; border-radius: 5px; cursor: pointer; transition: all 0.15s; }
  .btn-reload:hover { border-color: #3f3f46; color: #a1a1aa; }
  .btn-reload:disabled { opacity: 0.4; cursor: not-allowed; }
  .run-link { font-family: 'JetBrains Mono', monospace; font-size: 11px; color: #52525b; text-decoration: none; transition: color 0.15s; }
  .run-link:hover { color: #00ff87; }
  .erro-cell { color: #ff4466; font-family: 'JetBrains Mono', monospace; font-size: 11px; max-width: 300px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

  .load-more-wrap { padding: 16px; text-align: center; border-top: 1px solid #1c1c1f; }
  .btn-load-more { background: none; border: 1px solid #27272a; color: #52525b; font-family: 'JetBrains Mono', monospace; font-size: 11px; padding: 6px 16px; border-radius: 6px; cursor: pointer; transition: all 0.15s; }
  .btn-load-more:hover { border-color: #3f3f46; color: #a1a1aa; }

  .placeholder { display: flex; align-items: center; justify-content: center; height: 80px; font-family: 'JetBrains Mono', monospace; font-size: 12px; color: #52525b; }
  @keyframes spin { to { transform: rotate(360deg); } }
  .spinner { display: inline-block; width: 10px; height: 10px; border: 1.5px solid #3f3f46; border-top-color: #00ff87; border-radius: 50%; animation: spin 0.7s linear infinite; }
</style>
