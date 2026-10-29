import { getAccessToken, refreshAccessToken } from "@/services/session";
import { SseError, type SseMessage, parseBlock } from "@/lib/sse";

const STREAM_URL = "/api/dashboard/stream";

/** Server-sent events over fetch, so the Authorization header can be sent
 *  (the browser's EventSource cannot). Resolves when the server closes the stream. */
export async function streamDashboard(
  onMessage: (m: SseMessage) => void,
  signal: AbortSignal,
): Promise<void> {
  const open = (token: string): Promise<Response> =>
    // The one deliberate fetch() in the app: EventSource cannot send an Authorization
    // header and axios cannot stream in a browser. Keep this file the only exception.
    // eslint-disable-next-line no-restricted-globals
    fetch(STREAM_URL, {
      headers: { Authorization: `Bearer ${token}`, Accept: "text/event-stream" },
      cache: "no-store",
      signal,
    });

  let token = getAccessToken() ?? (await refreshAccessToken());
  if (!token) throw new SseError("Not signed in", 401);
  let res = await open(token);
  if (res.status === 401) {
    token = await refreshAccessToken();
    if (!token) throw new SseError("Session expired", 401);
    res = await open(token);
  }
  if (!res.ok || !res.body) throw new SseError(`HTTP ${res.status}`, res.status);

  const reader = res.body.pipeThrough(new TextDecoderStream()).getReader();
  try {
    let buffer = "";
    for (;;) {
      const { done, value } = await reader.read();
      if (done) return;
      buffer += value;
      let end: number;
      while ((end = buffer.search(/\r?\n\r?\n/)) !== -1) {
        const block = buffer.slice(0, end);
        buffer = buffer.slice(end).replace(/^\r?\n\r?\n/, "");
        const message = parseBlock(block);
        if (message) onMessage(message);
      }
    }
  } finally {
    // Close the connection on every exit (server closed, error, abort, or a throwing
    // onMessage), so a reconnect never leaves the old stream running.
    await reader.cancel().catch(() => undefined);
  }
}
