// A page's code is loaded when you first open it (autoCodeSplitting). After a deploy,
// a tab opened earlier asks for its old chunk, which no longer exists; the browser then
// fails the dynamic import with one of these messages (Chrome / Edge, Firefox, Safari)
// or Vite's own preload error.
const CHUNK_ERRORS = [
  "failed to fetch dynamically imported module",
  "error loading dynamically imported module",
  "importing a module script failed",
  "unable to preload css",
];

/** The page's code could not be loaded (usually: a newer version was deployed). */
export function isChunkLoadError(error: unknown): boolean {
  if (!(error instanceof Error)) return false;
  if (error.name === "ChunkLoadError") return true;
  const message = error.message.toLowerCase();
  return CHUNK_ERRORS.some((m) => message.includes(m));
}
