import { cn } from "@/lib/utils";

type ViewHeaderProps = {
  /** The page's name, exactly as the sidebar shows it. */
  title: string;
  /** The question the page answers, when it has one. */
  question?: string;
  /** A sentence or two on what the page shows, including that the data is synthetic. */
  children: React.ReactNode;
  className?: string;
};

/** The top of a university view: the same name, question and lead on every one. */
export function ViewHeader({ title, question, children, className }: ViewHeaderProps) {
  return (
    <header className={cn("flex max-w-3xl flex-col gap-1", className)}>
      <h1 className="text-2xl font-semibold tracking-tight text-balance">{title}</h1>
      {question && <p className="text-base font-medium text-balance">{question}</p>}
      <div className="flex flex-col gap-2 text-sm text-muted-foreground">{children}</div>
    </header>
  );
}
