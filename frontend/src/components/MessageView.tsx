import Markdown from "./Markdown";
import ResultView from "./ResultView";
import type { Message } from "@/lib/types";

export default function MessageView({ message }: { message: Message }) {
  const failed = message.status === "failed";
  const retried = (message.attempts?.length ?? 0) > 1;

  return (
    <div className={`msg ${message.role}`}>
      <div className={`bubble ${failed ? "failed" : ""}`}>
        {message.role === "assistant" ? <Markdown>{message.content}</Markdown> : <p>{message.content}</p>}
        {message.result && (
          <ResultView
            result={message.result}
            exportUrl={message.role === "assistant" && !message.id.startsWith("tmp-")
              ? `/api/sessions/${message.session_id}/messages/${message.id}/export`
              : undefined}
          />
        )}
        {message.query && (
          <details>
            <summary>
              Query{retried ? ` · self-corrected over ${message.attempts!.length} attempts` : ""}
            </summary>
            <pre>{message.query}</pre>
            {retried &&
              message.attempts!.map((a) => (
                <p key={a.n} className={a.error ? "error" : "ok"}>
                  #{a.n} {a.error ? `${a.stage}: ${a.error}` : "succeeded"} ({a.duration_ms} ms)
                </p>
              ))}
          </details>
        )}
      </div>
    </div>
  );
}
