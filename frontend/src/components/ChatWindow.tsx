"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import MessageView from "./MessageView";
import type { Message } from "@/lib/types";

interface Props {
  messages: Message[];
  progress: string | null;
  busy: boolean;
  disabled: boolean;
  error: string | null;
  onSend: (question: string) => void;
  onStop: () => void;
}

export default function ChatWindow({ messages, progress, busy, disabled, error, onSend, onStop }: Props) {
  const [input, setInput] = useState("");
  const bottom = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, progress]);

  function submit(e: FormEvent) {
    e.preventDefault();
    const question = input.trim();
    if (!question || busy) return;
    setInput("");
    onSend(question);
  }

  return (
    <section className="chat">
      <div className="messages">
        {messages.length === 0 && !disabled && <p className="muted center">Ask anything about your data.</p>}
        {disabled && <p className="muted center">Add a database in the sidebar to start chatting.</p>}
        {messages.map((m) => <MessageView key={m.id} message={m} />)}
        {busy && (
          <div className="msg assistant">
            <div className="bubble skeleton">
              <span className="spinner" /> {progress ?? "Thinking…"}
            </div>
          </div>
        )}
        {error && <p className="error center" role="alert">{error}</p>}
        <div ref={bottom} />
      </div>
      <form onSubmit={submit} className="composer">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ask about your database…"
          maxLength={2000}
          disabled={disabled || busy}
        />
        {busy ? (
          <button type="button" className="secondary" onClick={onStop}>Stop</button>
        ) : (
          <button disabled={disabled || !input.trim()}>Send</button>
        )}
      </form>
    </section>
  );
}
