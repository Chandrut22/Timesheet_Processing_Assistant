import js from "@eslint/js";
import globals from "globals";
import reactHooks from "eslint-plugin-react-hooks";
import reactRefresh from "eslint-plugin-react-refresh";
import tseslint from "typescript-eslint";
import prettier from "eslint-config-prettier";
import { defineConfig, globalIgnores } from "eslint/config";

const USE_CLIENT =
  "Use the functions in src/api (they go through the axios client in src/api/client.ts).";
const NETWORK_GLOBALS = [
  { name: "fetch", message: `No fetch(). ${USE_CLIENT}` },
  { name: "XMLHttpRequest", message: `No XMLHttpRequest. ${USE_CLIENT}` },
];
const OTHER_HTTP_LIBRARIES = [
  "ky",
  "ofetch",
  "node-fetch",
  "superagent",
  "cross-fetch",
  "isomorphic-fetch",
  "got",
].map((name) => ({
  name,
  message: `The app has one HTTP client (axios, in src/api). ${USE_CLIENT}`,
}));
const AXIOS_OUTSIDE_API = {
  name: "axios",
  message: `axios is only imported inside src/api. ${USE_CLIENT}`,
};
const AXIOS_SUBPATHS = {
  group: ["axios/*"],
  message: "Import from 'axios' itself, inside src/api only.",
};

export default defineConfig([
  globalIgnores(["dist", "src/app/routeTree.gen.ts"]),
  {
    files: ["**/*.{ts,tsx}"],
    extends: [
      js.configs.recommended,
      tseslint.configs.recommended,
      reactHooks.configs.flat.recommended,
      reactRefresh.configs.vite,
      prettier,
    ],
    languageOptions: { globals: globals.browser },
    rules: {
      "@typescript-eslint/no-explicit-any": "error",
    },
  },
  {
    // One HTTP client: every request goes through the axios instance in src/api/client.ts
    // (token, refresh on 401, cookies only to /auth, errors as ApiError). Screens call the
    // functions in src/api/*.ts; nothing else talks to the network directly.
    files: ["src/**/*.{ts,tsx}"],
    rules: {
      "no-restricted-globals": ["error", ...NETWORK_GLOBALS],
      "no-restricted-properties": [
        "error",
        ...["window", "globalThis", "self"].flatMap((object) =>
          NETWORK_GLOBALS.map(({ name, message }) => ({ object, property: name, message })),
        ),
      ],
      "no-restricted-imports": [
        "error",
        { paths: [...OTHER_HTTP_LIBRARIES, AXIOS_OUTSIDE_API], patterns: [AXIOS_SUBPATHS] },
      ],
    },
  },
  {
    // Inside src/api axios is allowed (it is the client); other HTTP libraries still are not.
    files: ["src/api/**/*.ts"],
    rules: {
      "no-restricted-imports": [
        "error",
        { paths: OTHER_HTTP_LIBRARIES, patterns: [AXIOS_SUBPATHS] },
      ],
    },
  },
  {
    // Route files export `Route`; UI kit files export variants next to components.
    files: ["src/routes/**/*.tsx", "src/components/ui/**/*.tsx"],
    rules: { "react-refresh/only-export-components": "off" },
  },
]);
