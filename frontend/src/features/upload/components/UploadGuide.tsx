// // "What happens next" and "Tips": what the system really does with an upload.
// import { ChevronDown } from "lucide-react";
// import type { ReactNode } from "react";
// import { Card } from "@/components/ui/card";

// const STEPS: { name: string; text: string }[] = [
//   { name: "Reading", text: "Each file is turned into text, including scans and photos." },
//   {
//     name: "Matching",
//     text: "The assistant extracts names and daily hours, then matches the company and employee.",
//   },
//   {
//     name: "Rule checks",
//     text: "Hours are split into regular, overtime, double time and holiday using the company's rules.",
//   },
//   { name: "Awaiting review", text: "A reviewer checks flagged items and approves." },
//   { name: "Approved", text: "Clean, confident timesheets can be approved automatically." },
//   { name: "Exported", text: "Approved timesheets go into the weekly payroll sheet." },
// ];

// const TIPS: string[] = [
//   "Pick a company to avoid the “company guessed” review flag.",
//   "The same file uploaded twice is flagged as a duplicate.",
//   "Very long documents may be only partly read; they are flagged so a reviewer checks them.",
//   "One upload can hold several people and weeks; a multi-week sheet becomes one timesheet per week.",
//   "Up to 10 files, 15 MB each: PDF, images (PNG, JPG, TIFF), DOCX, XLSX, CSV, TXT.",
// ];

// function Section({ title, children }: { title: string; children: ReactNode }) {
//   return (
//     <details open className="group">
//       <summary className="flex cursor-pointer list-none items-center justify-between gap-2 px-5 py-3 text-sm font-semibold outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50 [&::-webkit-details-marker]:hidden">
//         {title}
//         <ChevronDown
//           className="size-4 text-muted-foreground transition-transform group-open:rotate-180 motion-reduce:transition-none"
//           aria-hidden
//         />
//       </summary>
//       <div className="px-5 pb-4">{children}</div>
//     </details>
//   );
// }

// export function UploadGuide({ className }: { className?: string }) {
//   return (
//     <Card className={className}>
//       <Section title="What happens next">
//         <ol className="space-y-3">
//           {STEPS.map((step, i) => (
//             <li key={step.name} className="flex gap-3">
//               <span className="tabular grid size-6 shrink-0 place-items-center rounded-full bg-primary/10 text-xs font-semibold text-primary">
//                 {i + 1}
//               </span>
//               <span className="text-sm">
//                 <span className="font-medium">{step.name}.</span>{" "}
//                 <span className="text-muted-foreground">{step.text}</span>
//               </span>
//             </li>
//           ))}
//         </ol>
//       </Section>
//       <div className="border-t" />
//       <Section title="Tips">
//         <ul className="list-disc space-y-1.5 pl-5 text-sm text-muted-foreground">
//           {TIPS.map((tip) => (
//             <li key={tip}>{tip}</li>
//           ))}
//         </ul>
//       </Section>
//     </Card>
//   );
// }
