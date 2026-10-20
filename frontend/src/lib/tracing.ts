/** Link to a trace in Jaeger, or null when VITE_JAEGER_URL or the trace id is missing. */
export function traceUrl(traceId: string | null | undefined, base: string | undefined = import.meta.env.VITE_JAEGER_URL): string | null {
  const root = base?.trim().replace(/\/+$/, "");
  const id = traceId?.trim();
  if (!root || !id) return null;
  return `${root}/trace/${encodeURIComponent(id)}`;
}
