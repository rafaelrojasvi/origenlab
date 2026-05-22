import { describe, expect, it } from "vitest";

const freezeChecklist = import.meta.glob("../../scripts/run-v1-freeze-checklist.sh", {
  query: "?raw",
  import: "default",
  eager: true,
})["../../scripts/run-v1-freeze-checklist.sh"] as string;

const postgresMatrix = import.meta.glob("../../scripts/run-v1-postgres-matrix-check.sh", {
  query: "?raw",
  import: "default",
  eager: true,
})["../../scripts/run-v1-postgres-matrix-check.sh"] as string;

const POSTGRES_VARS = [
  "ORIGENLAB_API_BACKEND",
  "ORIGENLAB_POSTGRES_URL",
  "ORIGENLAB_TEST_POSTGRES_URL",
  "ALEMBIC_DATABASE_URL",
];

describe("v1 freeze scripts policy", () => {
  it("default freeze checklist unsets Postgres env vars", () => {
    for (const name of POSTGRES_VARS) {
      expect(freezeChecklist, `must reference ${name}`).toContain(name);
    }
    expect(freezeChecklist).toMatch(/unset\s+"\$\{_var\}"/);
    expect(freezeChecklist).toMatch(
      /env -u ORIGENLAB_API_BACKEND -u ORIGENLAB_POSTGRES_URL -u ORIGENLAB_TEST_POSTGRES_URL -u ALEMBIC_DATABASE_URL/,
    );
    expect(freezeChecklist).toMatch(/run-v1-postgres-matrix-check\.sh/);
    expect(freezeChecklist).toMatch(/not integration|'-m'.*not integration/);
    expect(freezeChecklist).not.toMatch(/freeze:postgres|EXPECT_BACKEND=postgres/);
  });

  it("postgres matrix script requires disposable URL and probes connectivity", () => {
    expect(postgresMatrix).toMatch(/ORIGENLAB_TEST_POSTGRES_URL/);
    expect(postgresMatrix).toMatch(/disposable/i);
    expect(postgresMatrix).toMatch(/production\/scratch|not production/i);
    expect(postgresMatrix).toMatch(/connectivity|psycopg\.connect/);
    expect(postgresMatrix).toMatch(/--expect-backend postgres/);
    expect(postgresMatrix).toMatch(/exit 2/);
  });

  it("default freeze keeps ORIGENLAB_SQLITE_PATH optional", () => {
    expect(freezeChecklist).toMatch(/ORIGENLAB_SQLITE_PATH/);
  });
});
