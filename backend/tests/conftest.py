import os

# Deve ser definido antes do import do collector, que lê as vars no topo do módulo.
os.environ.setdefault("SUPABASE_URL", "https://test.supabase.co")
os.environ.setdefault("SUPABASE_KEY", "test-key")
os.environ.setdefault("LOCAL", "test-local")
