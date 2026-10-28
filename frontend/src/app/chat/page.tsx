"use client";

import ChatWindow from "@/components/ChatWindow";
import Sidebar from "@/components/Sidebar";
import { useWorkspace } from "@/hooks/useWorkspace";

export default function ChatPage() {
  const w = useWorkspace();

  if (!w.user) return <main className="auth"><span className="spinner" /></main>;

  return (
    <div className="layout">
      <Sidebar
        email={w.user.email}
        connections={w.connections}
        sessions={w.sessions}
        activeSessionId={w.activeId}
        onSelectSession={w.openSession}
        onNewChat={w.newChat}
        onDeleteSession={w.removeSession}
        onDeleteConnection={w.removeConnection}
        onConnectionCreated={w.addConnection}
        onLogout={w.logout}
      />
      <ChatWindow
        messages={w.messages}
        progress={w.progress}
        busy={w.busy}
        disabled={w.connections.length === 0}
        error={w.error}
        onSend={w.send}
        onStop={w.stop}
      />
    </div>
  );
}
