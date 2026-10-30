import js from "@eslint/js";
import globals from "globals";
import reactHooks from "eslint-plugin-react-hooks";
import reactRefresh from "eslint-plugin-react-refresh";
import tseslint from "typescript-eslint";
import prettier from "eslint-config-prettier";
import { defineConfig, globalIgnores } from "eslint/config";

const USE_CLIENT =
  "Use the feature services (they go through the axios instance in src/lib/axios.ts).";
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
  message: `The app has one HTTP client (axios, in src/lib/axios.ts). ${USE_CLIENT}`,
}));
const AXIOS_OUTSIDE_CLIENT = {
  name: "axios",
  message: `axios is only imported by src/lib/axios.ts and src/services. ${USE_CLIENT}`,
};
const AXIOS_SUBPATHS = {
  group: ["axios/*"],
  message: "Import from 'axios' itself, and only where the client lives.",
};
// Feature boundaries: another feature is reached through its index.ts, never its insides.
const FEATURE_INTERNALS = {
  group: ["@/features/*/*"],
  message: "Import from the feature's public API instead: '@/features/<name>'.",
};
// Route files are the one place that reaches into a feature: they import its page and
// its search validator directly, so the page is not pulled in through the feature's
// index.ts (which would put it in the main chunk; autoCodeSplitting splits each page).
const ROUTE_FEATURE_INTERNALS = {
  // A regex: gitignore-style "!" can't re-include a file inside a folder already matched.
  regex: "^@/features/[^/]+/(?!components/[A-Za-z]+Page$|utils/[A-Za-z]*[sS]earch$).+",
  message:
    "Routes import only a feature's page (components/*Page) and search validator (utils/*Search); everything else comes from '@/features/<name>'.",
};
// Files that own the HTTP client (and tests that mock it) may import axios.
const CLIENT_FILES = ["src/lib/axios.ts", "src/services/session.ts", "src/services/apiErrors.ts"];
const TEST_FILES = ["src/**/*.test.{ts,tsx}", "src/test/**/*.{ts,tsx}"];
// Components and layouts get server data only through hooks (features/<name>/hooks):
// Component -> Hook -> Service -> API client.
const UI_FILES = [
  "src/features/*/components/**/*.{ts,tsx}",
  "src/components/**/*.{ts,tsx}",
  "src/layouts/**/*.{ts,tsx}",
];
const USE_A_HOOK = "Use the feature's hook (features/<name>/hooks) instead.";
const QUERY_HOOKS_IN_UI = {
  name: "@tanstack/react-query",
  importNames: ["useQuery", "useQueries", "useInfiniteQuery", "useSuspenseQuery", "useMutation"],
  message: `No queries or mutations in components. ${USE_A_HOOK}`,
};
const SERVICES_IN_UI = {
  group: ["../services/*", "@/services/*", "@/features/*/services/*"],
  message: `Components don't call services. ${USE_A_HOOK} Error helpers are in @/utils/errors.`,
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
    languageOptions: {
      globals: globals.browser,
      parserOptions: {
        projectService: true,
        tsconfigRootDir: import.meta.dirname,
      },
    },
    rules: {
      "@typescript-eslint/no-explicit-any": "error",
      "@typescript-eslint/explicit-function-return-type": ["warn", { allowExpressions: true }],
      "@typescript-eslint/no-floating-promises": "error",
    },
  },
  {
    // One HTTP client: every request goes through the axios instance in src/lib/axios.ts
    // (token, refresh on 401, cookies only to /auth, errors as ApiError). Screens call the
    // feature services; nothing else talks to the network directly.
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
        {
          paths: [...OTHER_HTTP_LIBRARIES, AXIOS_OUTSIDE_CLIENT],
          patterns: [AXIOS_SUBPATHS, FEATURE_INTERNALS],
        },
      ],
    },
  },
  {
    files: ["src/routes/**/*.{ts,tsx}"],
    rules: {
      "no-restricted-imports": [
        "error",
        {
          paths: [...OTHER_HTTP_LIBRARIES, AXIOS_OUTSIDE_CLIENT],
          patterns: [AXIOS_SUBPATHS, ROUTE_FEATURE_INTERNALS],
        },
      ],
    },
  },
  {
    // The client files may import axios; other HTTP libraries still are not allowed.
    files: CLIENT_FILES,
    rules: {
      "no-restricted-imports": [
        "error",
        { paths: OTHER_HTTP_LIBRARIES, patterns: [AXIOS_SUBPATHS, FEATURE_INTERNALS] },
      ],
    },
  },
  {
    files: UI_FILES,
    rules: {
      "no-restricted-imports": [
        "error",
        {
          paths: [...OTHER_HTTP_LIBRARIES, AXIOS_OUTSIDE_CLIENT, QUERY_HOOKS_IN_UI],
          patterns: [AXIOS_SUBPATHS, FEATURE_INTERNALS, SERVICES_IN_UI],
        },
      ],
    },
  },
  {
    // Tests may mock axios and reach into a feature to mock one module.
    files: TEST_FILES,
    rules: {
      "no-restricted-imports": [
        "error",
        { paths: OTHER_HTTP_LIBRARIES, patterns: [AXIOS_SUBPATHS] },
      ],
    },
  },
  {
    // Route files export `Route`; UI kit files export variants next to components.
    // (Search validators live in features/<name>/utils, not next to the page.)
    files: ["src/routes/**/*.tsx", "src/components/ui/**/*.tsx"],
    rules: { "react-refresh/only-export-components": "off" },
  },
]);
