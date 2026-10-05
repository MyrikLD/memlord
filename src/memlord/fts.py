"""Full-text search configuration.

Memlord uses its own text search configuration named ``memlord``:

- If the PostgreSQL server ships the ``zhparser`` extension, ``memlord`` uses the
  zhparser parser, so Chinese text is segmented into words.
- Otherwise it is a plain copy of the built-in ``simple`` configuration, which is
  exactly the previous behaviour.

The configuration is created by the ``optional_zh_fts`` migration; tests that use
``create_all`` run :data:`ENSURE_TS_CONFIG_SQL` first.
"""

TS_CONFIG = "memlord"

ENSURE_TS_CONFIG_SQL = """
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_ts_config WHERE cfgname = 'memlord') THEN
    RETURN;
  END IF;
  IF EXISTS (SELECT 1 FROM pg_available_extensions WHERE name = 'zhparser') THEN
    BEGIN
      CREATE EXTENSION IF NOT EXISTS zhparser;
      CREATE TEXT SEARCH CONFIGURATION memlord (PARSER = zhparser);
      ALTER TEXT SEARCH CONFIGURATION memlord ADD MAPPING FOR n,v,a,i,e,l,j,t WITH simple;
      RETURN;
    EXCEPTION WHEN OTHERS THEN
      NULL;  -- zhparser not usable (e.g. missing privileges): fall back to simple
    END;
  END IF;
  CREATE TEXT SEARCH CONFIGURATION memlord (COPY = simple);
END $$;
"""
