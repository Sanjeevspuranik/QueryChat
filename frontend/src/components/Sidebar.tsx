"use client";

import ConnectionForm from "./ConnectionForm";
import type { ChatSession, Connection } from "@/lib/types";

interface Props {
  email: string;
  connections: Connection[];
  sessions: ChatSession[];
  activeSessionId: string | null;
  onSelectSession: (id: string) => void;
  onNewChat: (connectionId: string) => void;
  onDeleteSession: (id: string) => void;
  onDeleteConnection: (id: string) => void;
  onConnectionCreated: (connection: Connection) => void;
  onLogout: () => void;
}

export default function Sidebar(p: Props) {
  return (
    <aside className="sidebar">
      <h2>📊 QueryChat</h2>

      <section>
        <h3>Chats</h3>
        <ul className="list">
          {p.sessions.map((s) => (
            <li key={s.id} className={s.id === p.activeSessionId ? "active" : ""}>
              <button className="link" onClick={() => p.onSelectSession(s.id)}>
                {s.title}
              </button>
              <button className="icon" aria-label="Delete chat" onClick={() => p.onDeleteSession(s.id)}>
                ✕
              </button>
            </li>
          ))}
          {p.sessions.length === 0 && <li className="muted">No chats yet</li>}
        </ul>
      </section>

      <section>
        <h3>Databases</h3>
        <ul className="list">
          {p.connections.map((c) => (
            <li key={c.id}>
              <button className="link" title="Start a new chat" onClick={() => p.onNewChat(c.id)}>
                ＋ {c.name} <span className="muted">({c.db_type})</span>
              </button>
              <button className="icon" aria-label="Delete database" onClick={() => p.onDeleteConnection(c.id)}>
                ✕
              </button>
            </li>
          ))}
        </ul>
        <details open={p.connections.length === 0}>
          <summary>Add database</summary>
          <ConnectionForm onCreated={p.onConnectionCreated} />
        </details>
      </section>

      <footer>
        <span className="muted">{p.email}</span>
        <button className="secondary" onClick={p.onLogout}>
          Sign out
        </button>
      </footer>
    </aside>
  );
}
