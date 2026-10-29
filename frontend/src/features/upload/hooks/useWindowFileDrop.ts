// Page-wide drag and drop for the Upload page. While mounted:
// - dragging FILES anywhere over the window sets `dragging` (a depth counter keeps the
//   overlay steady while the pointer crosses child elements); text and links are ignored;
// - dragover and drop are default-prevented on the window, so a drop that misses the
//   page never makes the browser open the file and leave the app;
// - a drop with files calls onFiles (unless `enabled` is false, e.g. while uploading).
// The listeners are removed on unmount.
import { useEffect, useRef, useState } from "react";

export function hasFiles(event: DragEvent): boolean {
  return Array.from(event.dataTransfer?.types ?? []).includes("Files");
}

export function useWindowFileDrop(
  onFiles: (files: File[]) => void,
  { enabled = true }: { enabled?: boolean } = {},
): { dragging: boolean } {
  const [dragging, setDragging] = useState(false);
  const depth = useRef(0);
  const latest = useRef({ onFiles, enabled });
  useEffect(() => {
    latest.current = { onFiles, enabled }; // the listeners below always see the newest
  });

  useEffect(() => {
    const onDragEnter = (e: DragEvent): void => {
      if (!hasFiles(e)) return;
      e.preventDefault();
      depth.current += 1;
      if (latest.current.enabled) setDragging(true);
    };
    const onDragLeave = (e: DragEvent): void => {
      if (!hasFiles(e)) return;
      depth.current = Math.max(0, depth.current - 1);
      if (depth.current === 0) setDragging(false);
    };
    const onDragOver = (e: DragEvent): void => {
      e.preventDefault();
      if (e.dataTransfer && hasFiles(e)) {
        e.dataTransfer.dropEffect = latest.current.enabled ? "copy" : "none";
      }
    };
    const onDrop = (e: DragEvent): void => {
      e.preventDefault();
      depth.current = 0;
      setDragging(false);
      const files = Array.from(e.dataTransfer?.files ?? []);
      if (files.length && latest.current.enabled) latest.current.onFiles(files);
    };
    window.addEventListener("dragenter", onDragEnter);
    window.addEventListener("dragleave", onDragLeave);
    window.addEventListener("dragover", onDragOver);
    window.addEventListener("drop", onDrop);
    return () => {
      window.removeEventListener("dragenter", onDragEnter);
      window.removeEventListener("dragleave", onDragLeave);
      window.removeEventListener("dragover", onDragOver);
      window.removeEventListener("drop", onDrop);
    };
  }, []);

  return { dragging };
}
