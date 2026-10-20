import type { FieldValues, Path, UseFormSetError } from "react-hook-form";
import { ApiError } from "@/api/errors";

/**
 * Puts FastAPI 422 field errors next to the matching form fields.
 * Returns true if at least one field error was placed.
 */
export function applyFieldErrors<T extends FieldValues>(
  err: unknown,
  setError: UseFormSetError<T>,
  fields: readonly string[],
): boolean {
  if (!(err instanceof ApiError)) return false;
  let placed = false;
  for (const [field, message] of Object.entries(err.fieldErrors)) {
    const match = fields.find((f) => field === f || field.startsWith(`${f}.`));
    if (match) {
      setError(field as Path<T>, { type: "server", message });
      placed = true;
    }
  }
  return placed;
}
