import type { ListingProps } from "@/lib/housing/types";

export function ListingPopup({ p }: { p: ListingProps }) {
  return (
    <div className="min-w-[220px] space-y-2 p-1">
      <div className="text-base font-semibold text-foreground">
        ${p.price.toLocaleString()}
      </div>
      <div className="text-sm text-foreground">
        {p.beds} bd · {p.baths} ba
      </div>
      <div className="text-sm text-muted-foreground">
        {p.address}
        <br />
        {p.city}, {p.zip}
      </div>
      <div className="text-xs text-muted-foreground">
        District: <span className="font-medium text-foreground">{p.school_district}</span>
        {p.good_district ? (
          <span className="ml-1 inline-block rounded bg-primary/10 px-1.5 py-0.5 text-[10px] font-medium text-primary">
            Good
          </span>
        ) : null}
      </div>
      <a
        href={p.url}
        target="_blank"
        rel="noreferrer noopener"
        className="inline-flex w-full items-center justify-center rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground hover:bg-primary/90"
      >
        View listing
      </a>
    </div>
  );
}
