// What an upload accepts, and the checks run when files are added (before anything is
// sent). The same limits as the API (core-service: MAX_FILES_PER_UPLOAD, 15 MB each).
export const MAX_FILES = 10;
export const MAX_BYTES = 15 * 1024 * 1024;
export const ACCEPT = [
  ".pdf",
  ".png",
  ".jpg",
  ".jpeg",
  ".tif",
  ".tiff",
  ".docx",
  ".xlsx",
  ".csv",
  ".txt",
];

export function extOf(name: string): string {
  const i = name.lastIndexOf(".");
  return i >= 0 ? name.slice(i).toLowerCase() : "";
}

export type FileKind = "pdf" | "image" | "word" | "excel" | "text" | "other";

export function fileKind(name: string): FileKind {
  const ext = extOf(name);
  if (ext === ".pdf") return "pdf";
  if ([".png", ".jpg", ".jpeg", ".tif", ".tiff"].includes(ext)) return "image";
  if (ext === ".docx") return "word";
  if (ext === ".xlsx") return "excel";
  if (ext === ".csv" || ext === ".txt") return "text";
  return "other";
}

export const totalBytes = (files: readonly File[]): number =>
  files.reduce((sum, f) => sum + f.size, 0);

/**
 * `current` plus the acceptable files from `incoming`, and one message per refused file.
 * A file already in the list (same name and size) is skipped without a message, as before.
 */
export function validateFiles(
  current: readonly File[],
  incoming: Iterable<File>,
): { files: File[]; problems: string[] } {
  const files = [...current];
  const problems: string[] = [];
  for (const f of Array.from(incoming)) {
    if (files.some((x) => x.name === f.name && x.size === f.size)) continue;
    if (!ACCEPT.includes(extOf(f.name))) {
      problems.push(`${f.name}: this file type isn't supported.`);
      continue;
    }
    if (f.size > MAX_BYTES) {
      problems.push(`${f.name}: larger than 15 MB.`);
      continue;
    }
    if (files.length >= MAX_FILES) {
      problems.push(`${f.name}: you can upload at most ${MAX_FILES} files at once.`);
      continue;
    }
    files.push(f);
  }
  return { files, problems };
}
