"use client";

import { FormEvent, useState } from "react";
import { api } from "@/lib/api";
import type { Connection } from "@/lib/types";

const TEMPLATES: Record<string, string> = {
  SQLite: "sqlite:///./chinook.db",
  PostgreSQL: "postgresql+psycopg://user:password@host:5432/dbname",
  MySQL: "mysql+pymysql://user:password@host:3306/dbname",
  "SQL Server": "mssql+pyodbc://user:password@host/dbname?driver=ODBC+Driver+18+for+SQL+Server",
  MongoDB: "mongodb://user:password@host:27017/dbname",
};

interface Props {
  onCreated: (connection: Connection) => void;
}

/** One replaceable URL field: pick a template or paste any SQLAlchemy / MongoDB URL. */
export default function ConnectionForm({ onCreated }: Props) {
  const [name, setName] = useState("");
  const [url, setUrl] = useState("");
  const [note, setNote] = useState<{ ok: boolean; text: string } | null>(null);
  const [busy, setBusy] = useState(false);

  async function run(action: () => Promise<string>) {
    setBusy(true);
    setNote(null);
    try {
      setNote({ ok: true, text: await action() });
    } catch (err) {
      setNote({ ok: false, text: err instanceof Error ? err.message : "Failed." });
    } finally {
      setBusy(false);
    }
  }

  const test = () =>
    run(async () => {
      const { schema_preview } = await api.testConnection(url);
      const tables = schema_preview ? schema_preview.split("\n").length : 0;
      return `Connected. Found ${tables} table(s)/collection(s).`;
    });

  const save = (e: FormEvent) => {
    e.preventDefault();
    return run(async () => {
      const connection = await api.createConnection(name || "My database", url);
      onCreated(connection);
      setName("");
      setUrl("");
      return "Connection saved.";
    });
  };

  return (
    <form onSubmit={save} className="stack">
      <select
        aria-label="URL template"
        defaultValue=""
        onChange={(e) => e.target.value && setUrl(TEMPLATES[e.target.value])}
      >
        <option value="">Use a template…</option>
        {Object.keys(TEMPLATES).map((k) => (
          <option key={k}>{k}</option>
        ))}
      </select>
      <input placeholder="Name" value={name} maxLength={100} onChange={(e) => setName(e.target.value)} />
      <input
        placeholder="Database URL"
        required
        value={url}
        onChange={(e) => setUrl(e.target.value)}
        spellCheck={false}
        autoComplete="off"
      />
      <div className="row">
        <button type="button" className="secondary" disabled={busy || !url} onClick={test}>
          Test
        </button>
        <button disabled={busy || !url}>Save</button>
      </div>
      {note && <p className={note.ok ? "ok" : "error"}>{note.text}</p>}
    </form>
  );
}
