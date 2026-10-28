"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { api, ApiError, streamChat } from "@/lib/api";
import type { ChatSession, Connection, Message, User } from "@/lib/types";

const ACTIVE_KEY = "querychat.activeSession";

/** All workspace state and actions (connections, sessions, active chat, streaming). */
export function useWorkspace() {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [connections, setConnections] = useState<Connection[]>([]);
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [progress, setProgress] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const abort = useRef<AbortController | null>(null);

  const handleError = useCallback(
    (err: unknown) => {
      if (err instanceof ApiError && err.status === 401) return router.replace("/login");
      if (err instanceof DOMException && err.name === "AbortError") return;
      setError(err instanceof Error ? err.message : "Something went wrong.");
    },
    [router],
  );

  const openSession = useCallback(
    async (id: string) => {
      setError(null);
      try {
        const detail = await api.session(id);
        setActiveId(id);
        setMessages(detail.messages);
        localStorage.setItem(ACTIVE_KEY, id);
      } catch (err) {
        localStorage.removeItem(ACTIVE_KEY);
        handleError(err);
      }
    },
    [handleError],
  );

  /** Creates a chat for the connection and opens it. Returns the new session id. */
  const startChat = useCallback(
    async (connectionId: string): Promise<string> => {
      const session = await api.createSession(connectionId);
      setSessions((prev) => [session, ...prev]);
      await openSession(session.id);
      return session.id;
    },
    [openSession],
  );

  useEffect(() => {
    (async () => {
      try {
        const [me, conns, sess] = await Promise.all([api.me(), api.connections(), api.sessions()]);
        setUser(me);
        setConnections(conns);
        setSessions(sess);
        const saved = localStorage.getItem(ACTIVE_KEY);
        const initial = sess.find((s) => s.id === saved) ?? sess[0];
        if (initial) await openSession(initial.id);
        else if (conns.length > 0) await startChat(conns[conns.length - 1].id);
      } catch (err) {
        handleError(err);
      }
    })();
    return () => abort.current?.abort();
  }, [handleError, openSession, startChat]);

  const newChat = useCallback(
    async (connectionId: string) => {
      try {
        await startChat(connectionId);
      } catch (err) {
        handleError(err);
      }
    },
    [startChat, handleError],
  );

  const addConnection = useCallback(
    async (connection: Connection) => {
      setConnections((prev) => [...prev, connection]);
      await newChat(connection.id); // ready to chat immediately
    },
    [newChat],
  );

  const send = useCallback(
    async (question: string) => {
      if (connections.length === 0) return;
      setError(null);
      setBusy(true);
      setProgress("Starting…");
      let sessionId = activeId;
      try {
        if (!sessionId) sessionId = await startChat(connections[connections.length - 1].id);
      } catch (err) {
        setBusy(false);
        setProgress(null);
        return handleError(err);
      }
      const targetId = sessionId;
      setMessages((prev) => [
        ...prev,
        {
          id: `tmp-${Date.now()}`, session_id: targetId, seq: prev.length + 1, role: "user", content: question, query: null,
          result: null, attempts: null, status: "ok", created_at: new Date().toISOString(),
        },
      ]);
      abort.current = new AbortController();
      try {
        await streamChat(
          targetId,
          question,
          (event) => {
            if (event.type === "done") setMessages((prev) => [...prev, event.message]);
            else if (event.type === "status" || event.type === "retrying") setProgress(event.message);
            else if (event.type === "attempt_failed") setProgress(`Attempt failed (${event.stage}), correcting…`);
          },
          abort.current.signal,
        );
        setSessions(await api.sessions());
      } catch (err) {
        if (err instanceof DOMException && err.name === "AbortError") {
          // The server saves a "stopped" reply on disconnect; reload so the UI matches it.
          await openSession(targetId);
        } else {
          // Roll back the optimistic user bubble when the request was rejected up front.
          if (err instanceof ApiError) setMessages((prev) => prev.slice(0, -1));
          handleError(err);
        }
      } finally {
        setBusy(false);
        setProgress(null);
      }
    },
    [activeId, connections, handleError, openSession, startChat],
  );

  const removeSession = useCallback(
    async (id: string) => {
      try {
        await api.deleteSession(id);
        setSessions((prev) => prev.filter((s) => s.id !== id));
        if (id === activeId) {
          setActiveId(null);
          setMessages([]);
          localStorage.removeItem(ACTIVE_KEY);
        }
      } catch (err) {
        handleError(err);
      }
    },
    [activeId, handleError],
  );

  const removeConnection = useCallback(
    async (id: string) => {
      if (!confirm("Delete this database and all of its chats?")) return;
      try {
        await api.deleteConnection(id);
        setConnections((prev) => prev.filter((c) => c.id !== id));
        const removed = sessions.filter((s) => s.connection_id === id).map((s) => s.id);
        setSessions((prev) => prev.filter((s) => s.connection_id !== id));
        if (activeId && removed.includes(activeId)) {
          setActiveId(null);
          setMessages([]);
        }
      } catch (err) {
        handleError(err);
      }
    },
    [activeId, sessions, handleError],
  );

  const logout = useCallback(async () => {
    await api.logout().catch(() => undefined);
    localStorage.removeItem(ACTIVE_KEY);
    router.replace("/login");
  }, [router]);

  const stop = useCallback(() => abort.current?.abort(), []);

  return {
    user, connections, sessions, activeId, messages, progress, busy, error,
    openSession, newChat, addConnection, send, stop, removeSession, removeConnection, logout,
  };
}
