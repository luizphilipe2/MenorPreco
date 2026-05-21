import { PUBLIC_SUPABASE_URL, PUBLIC_SUPABASE_ANON_KEY } from '$env/static/public';

const BASE = `${PUBLIC_SUPABASE_URL}/rest/v1`;

const h = {
  apikey: PUBLIC_SUPABASE_ANON_KEY,
  Authorization: `Bearer ${PUBLIC_SUPABASE_ANON_KEY}`,
  'Content-Type': 'application/json',
};

export async function sbQuery<T>(table: string, params = ''): Promise<T[]> {
  const resp = await fetch(`${BASE}/${table}?${params}`, { headers: h });
  if (!resp.ok) throw new Error(`Supabase ${resp.status}: ${resp.statusText}`);
  return resp.json();
}

export async function sbPost(table: string, data: object, prefer = 'resolution=ignore-duplicates'): Promise<void> {
  const resp = await fetch(`${BASE}/${table}`, {
    method: 'POST',
    headers: { ...h, Prefer: prefer },
    body: JSON.stringify(data),
  });
  if (!resp.ok) throw new Error(`Supabase ${resp.status}: ${resp.statusText}`);
}

export async function sbPatch(table: string, filters: string, data: object): Promise<void> {
  const resp = await fetch(`${BASE}/${table}?${filters}`, {
    method: 'PATCH',
    headers: h,
    body: JSON.stringify(data),
  });
  if (!resp.ok) throw new Error(`Supabase ${resp.status}: ${resp.statusText}`);
}
