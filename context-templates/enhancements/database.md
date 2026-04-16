# Database Enhancement Request — [FILL: Feature Name]

## 1. Platform Context [PRE-FILLED]

- **Engine:** SQLite — file path `data/tickets.db` (relative to repo root)
- **Access pattern:** `aiosqlite` + raw SQL strings, no ORM, no migrations framework
- **Table creation strategy:** lazy `CREATE TABLE IF NOT EXISTS` executed on first endpoint call — safe to redeploy repeatedly
- **Standard column conventions:**
  - Primary key: `id TEXT PRIMARY KEY` (UUID string)
  - Timestamps: `created_at TEXT` / `updated_at TEXT` (ISO-8601 strings)
  - Soft-delete: `is_deleted INTEGER NOT NULL DEFAULT 0` (not used everywhere — only add if needed)
- **Existing tables:**

  | Table | Purpose |
  |---|---|
  | `telco_tickets` | Core ticket records — fault type, status, location, network type, node |
  | `dispatch_records` | Dispatch actions linked to tickets |
  | `sop_documents` | SOP text chunks for ChromaDB ingestion |
  | `location_geocache` | Nominatim geocode cache keyed by address string |

- **Reference implementation:** `app/storage/repositories.py` — mirror `aiosqlite` open/query patterns from this file
- **Connection pattern:**
  ```python
  async with aiosqlite.connect("data/tickets.db") as db:
      db.row_factory = aiosqlite.Row
      async with db.execute("SELECT ...", (param,)) as cursor:
          rows = await cursor.fetchall()
  ```

---

## 2. Schema Change Description [FILL]

<!-- Describe exactly what is changing in the DB.
     Choose ONE or MORE of:

     A. New table
        Name: <table_name>
        Columns: name | type | constraints | notes
        Indexes: CREATE INDEX IF NOT EXISTS ...

     B. New column on existing table
        Table: <table_name>
        Column: <name> <type> [DEFAULT value] [NOT NULL]
        Note: SQLite ALTER TABLE only supports ADD COLUMN — new columns must be nullable or have a DEFAULT

     C. Data backfill / seed
        Describe the INSERT ... SELECT or UPDATE logic needed after the schema change
-->

---

## 3. Migration Strategy [FILL]

<!-- SQLite has limited ALTER TABLE — plan carefully.

     For new tables:
       CREATE TABLE IF NOT EXISTS <name> (...) — run in endpoint startup, safe to re-run

     For new columns on existing table:
       ALTER TABLE <name> ADD COLUMN <col> <type> DEFAULT <val>
       — only safe if column is nullable OR has a DEFAULT value
       — cannot add NOT NULL without a DEFAULT to a non-empty table

     For data backfill:
       INSERT OR IGNORE INTO <target> SELECT ... FROM <source>

     State explicitly:
       - Whether existing rows are affected
       - Whether this can be run against a populated DB without data loss
       - Whether a rollback is possible (for SQLite ADD COLUMN: no rollback, but non-breaking)
-->

---

## 4. Query Patterns [FILL]

<!-- Write the full SQL for every SELECT / INSERT / UPDATE / DELETE this feature needs.
     Use ? placeholders for parameters.

     Example — grouped count query:
       SELECT location_details, status, COUNT(*) AS cnt
       FROM telco_tickets
       WHERE location_details IS NOT NULL
         AND location_details != ''
       GROUP BY location_details, status
       ORDER BY cnt DESC

     Example — upsert to cache table:
       INSERT INTO location_geocache (address, lat, lng, display_name, geocoded_at)
       VALUES (?, ?, ?, ?, ?)
       ON CONFLICT(address) DO UPDATE SET
         lat = excluded.lat,
         lng = excluded.lng,
         display_name = excluded.display_name,
         geocoded_at = excluded.geocoded_at
-->

---

## 5. RICEF Classification [FILL]

- **Type:** [FILL: C (Conversion — data load/migration) or I (Interface — if a new API endpoint reads/writes this schema)]
- **RICEF ID:** [FILL: R-xx]
- **Release:** [FILL: e.g., Release 15 — Feature Name]

---

## 6. Acceptance Criteria [FILL]

- [ ] Schema created automatically on first backend startup — no manual SQL needed
- [ ] Existing rows in other tables unaffected
- [ ] [FILL: e.g., INSERT of a new geocache row succeeds and is retrievable in the same request]
- [ ] [FILL: e.g., Queries return within 50 ms for ~1 600 ticket rows (current DB size)]
- [ ] [FILL: add more as needed]

---

## 7. Affected Backend Files [FILL]

<!-- List every file to create or modify. -->

- `app/api/v1/[FILL: feature].py` — new router + endpoint that uses this schema
- `app/api/v1/router.py` — register `[FILL: feature].router`
- `app/storage/repositories.py` — [FILL: add shared DB helper, or "no change if logic stays in endpoint file"]

---

## 8. Testing Requirements [FILL]

1. Start backend: `uvicorn app.main:app --reload --port 8000`
2. Check startup logs — confirm `[FILL: table name]` table created (add a startup log line)
3. Call endpoint: `curl "http://localhost:8000/api/v1/[FILL: path]"`
4. Verify response shape matches Pydantic model at [FILL: `app/api/v1/<feature>.py`]
5. Call again — confirm second call is faster (cached path, no Nominatim/external call)
6. [FILL: any additional DB state checks, e.g., "SQLite browser confirms row inserted in geocache"]
