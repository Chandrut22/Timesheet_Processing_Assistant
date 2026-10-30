// Each page must stay in its own chunk (autoCodeSplitting). That only works when the page
// is reached through its route file alone: a page exported from its feature's index.ts
// comes along with every import of that feature (hooks, types), into the main chunk.
// The files are read as text: nothing is imported or run.
import { describe, expect, it } from "vitest";

const barrels = import.meta.glob<string>("/src/features/*/index.ts", {
  query: "?raw",
  import: "default",
  eager: true,
});
const routes = import.meta.glob<string>("/src/routes/**/*.tsx", {
  query: "?raw",
  import: "default",
  eager: true,
});

describe("code splitting", () => {
  it("found the feature barrels and route files", () => {
    expect(Object.keys(barrels).length).toBeGreaterThan(10);
    expect(Object.keys(routes).length).toBeGreaterThan(10);
  });

  it.each(Object.entries(barrels))("%s exports no page", (_file, text) => {
    expect(text).not.toMatch(/from "\.\/components\/[A-Za-z]+Page"/);
  });

  it.each(Object.entries(routes))("%s imports its page directly", (_file, text) => {
    const page = /component:\s*([A-Z][A-Za-z]*Page)\b/.exec(text)?.[1];
    if (!page) return; // layouts (__root, _app, _auth) render no feature page
    expect(text).toMatch(
      new RegExp(`import \\{ ${page} \\} from "@/features/[a-z]+/components/[A-Za-z]+Page";`),
    );
  });
});
