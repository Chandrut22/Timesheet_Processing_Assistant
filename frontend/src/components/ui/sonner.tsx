import { Toaster as Sonner, type ToasterProps } from "sonner";

export function Toaster(props: ToasterProps) {
  return <Sonner position="top-right" richColors closeButton duration={5000} {...props} />;
}
