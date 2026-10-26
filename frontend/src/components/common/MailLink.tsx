// "Open in Gmail": the email's subject (or any text) as a link that opens the original
// email in the mailbox the system reads, in a new tab. The API builds the link
// (mail_url); without one (uploads, links turned off) the text is shown as it is.
import { ExternalLink } from "lucide-react";
import type { MouseEvent, ReactNode } from "react";
import { cn } from "@/lib/utils";

export function MailLink({
  url,
  children,
  className,
}: {
  /** From the API (`mail_url`); null or missing = plain text. */
  url: string | null | undefined;
  children: ReactNode;
  className?: string;
}) {
  if (!url) return <span className={className}>{children}</span>;
  return (
    <a
      href={url}
      target="_blank"
      rel="noopener noreferrer"
      title="Open in Gmail"
      // Inside a clickable row or card: open the email only, not the row as well.
      onClick={(e: MouseEvent<HTMLAnchorElement>) => e.stopPropagation()}
      className={cn("inline-flex min-w-0 max-w-full items-center gap-1 hover:underline", className)}
    >
      <span className="truncate">{children}</span>
      <ExternalLink aria-hidden className="size-3.5 shrink-0 opacity-70" />
      <span className="sr-only">(opens in Gmail)</span>
    </a>
  );
}
