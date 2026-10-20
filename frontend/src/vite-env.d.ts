/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Jaeger UI base URL, e.g. http://localhost:16686. When set, steps show "Open trace". */
  readonly VITE_JAEGER_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
