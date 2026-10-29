import { Toaster as Sonner, type ToasterProps } from "sonner";
import type { JSX } from "react";

export function Toaster(props: ToasterProps): JSX.Element {
  return <Sonner position="top-right" richColors closeButton duration={5000} {...props} />;
}
