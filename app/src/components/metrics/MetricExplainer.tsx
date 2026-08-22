import { CircleHelp, ExternalLink } from "lucide-react";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { cn } from "@/lib/utils";

export function MetricExplainer({
  label,
  title,
  children,
  sourceHref,
  sourceLabel,
  compact = false,
}: {
  label: string;
  title: string;
  children: React.ReactNode;
  sourceHref?: string;
  sourceLabel?: string;
  compact?: boolean;
}) {
  return (
    <Popover>
      <PopoverTrigger asChild>
        <button
          type="button"
          className={cn(
            "inline-flex items-center gap-1 rounded-sm text-xs font-medium text-primary underline-offset-2 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2",
            compact && "shrink-0",
          )}
          aria-label={compact ? label : undefined}
        >
          <CircleHelp className="h-3.5 w-3.5" aria-hidden="true" />
          {!compact ? <span>{label}</span> : null}
        </button>
      </PopoverTrigger>
      <PopoverContent align="start" className="w-[min(23rem,calc(100vw-2rem))] space-y-3 text-sm">
        <p className="font-semibold text-foreground">{title}</p>
        <div className="space-y-2 text-muted-foreground">{children}</div>
        {sourceHref && sourceLabel ? (
          <a
            href={sourceHref}
            target="_blank"
            rel="noreferrer noopener"
            className="inline-flex items-center gap-1 font-medium text-primary underline underline-offset-2"
          >
            {sourceLabel}
            <ExternalLink className="h-3.5 w-3.5" aria-hidden="true" />
          </a>
        ) : null}
      </PopoverContent>
    </Popover>
  );
}
