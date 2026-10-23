import { useCallback, useMemo, useState } from "react";
import { headerState, toggleAllRows, toggleRow, visibleSelection, type BulkRow } from "./selection";

type State = { key: string; ids: ReadonlySet<string>; anchor: string | null };

const EMPTY: ReadonlySet<string> = new Set();

/**
 * Ticked rows on the current page only. The selection belongs to `pageKey` (the filters
 * and page number): when that changes, it starts empty again.
 */
export function useRowSelection(rows: readonly BulkRow[], pageKey: string) {
  const [state, setState] = useState<State>({ key: pageKey, ids: EMPTY, anchor: null });
  const current = state.key === pageKey ? state : { key: pageKey, ids: EMPTY, anchor: null };

  const selectable = useMemo(() => rows.filter((r) => !r.disabled).map((r) => r.id), [rows]);
  const selectedRows = useMemo(() => visibleSelection(current.ids, rows), [current.ids, rows]);
  const selected = useMemo(() => new Set(selectedRows.map((r) => r.id)), [selectedRows]);
  const anchor = current.anchor;

  const set = useCallback(
    (ids: Iterable<string>, nextAnchor: string | null = null) =>
      setState({ key: pageKey, ids: new Set(ids), anchor: nextAnchor }),
    [pageKey],
  );
  const toggle = useCallback(
    (id: string, shift = false) => set(toggleRow(selected, id, selectable, anchor, shift), id),
    [selected, selectable, anchor, set],
  );
  const toggleAll = useCallback(
    () => set(toggleAllRows(selected, selectable)),
    [selected, selectable, set],
  );
  const clear = useCallback(() => set([]), [set]);

  return {
    selected,
    selectedRows,
    header: headerState(selected, selectable),
    hasSelectable: selectable.length > 0,
    toggle,
    toggleAll,
    clear,
    set,
  };
}

export type RowSelection = ReturnType<typeof useRowSelection>;
