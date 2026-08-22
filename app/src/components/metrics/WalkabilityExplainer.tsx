import { CircleHelp, ExternalLink } from "lucide-react";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { cn } from "@/lib/utils";

const EPA_WALKABILITY_URL =
  "https://www.epa.gov/smartgrowth/national-walkability-index-user-guide-and-methodology";

export function WalkabilityExplainer({ compact = false }: { compact?: boolean }) {
  return (
    <Popover>
      <PopoverTrigger asChild>
        <button
          type="button"
          className={cn(
            "inline-flex items-center gap-1 rounded-sm text-xs font-medium text-primary underline-offset-2 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2",
            compact && "shrink-0",
          )}
          aria-label={compact ? "How the EPA walkability score works" : undefined}
        >
          <CircleHelp className="h-3.5 w-3.5" aria-hidden="true" />
          {!compact ? <span>How EPA scores this</span> : null}
        </button>
      </PopoverTrigger>
      <PopoverContent align="start" className="w-[min(22rem,calc(100vw-2rem))] space-y-3 text-sm">
        <div>
          <p className="font-semibold text-foreground">EPA walkability score</p>
          <p className="mt-1 text-muted-foreground">
            This 1–20 index estimates how supportive a neighborhood is for walking as
            transportation, compared with Census block groups nationwide.
          </p>
        </div>
        <p className="text-muted-foreground">
          Public-transit proximity is a major input: a shorter walk from the block group&apos;s
          population center to the nearest transit stop raises the score. EPA also considers
          pedestrian-oriented street intersections and the mix of homes, jobs, and destinations.
        </p>
        <p className="text-muted-foreground">
          It does not directly measure sidewalk quality, traffic or personal safety, or how pleasant
          a walk feels.
        </p>
        <a
          href={EPA_WALKABILITY_URL}
          target="_blank"
          rel="noreferrer noopener"
          className="inline-flex items-center gap-1 font-medium text-primary underline underline-offset-2"
        >
          View the EPA National Walkability Index
          <ExternalLink className="h-3.5 w-3.5" aria-hidden="true" />
        </a>
      </PopoverContent>
    </Popover>
  );
}
