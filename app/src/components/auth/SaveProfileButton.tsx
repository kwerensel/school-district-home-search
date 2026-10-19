import { useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useServerFn } from "@tanstack/react-start";
import { BookmarkPlus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { getSession } from "@/lib/auth.functions";
import type { DiscoveryProfile } from "@/lib/discovery/profile";
import { saveProfile } from "@/lib/saved/persistence.functions";

export function SaveProfileButton({
  profile,
  ready,
}: {
  profile: DiscoveryProfile;
  ready: boolean;
}) {
  const sessionFn = useServerFn(getSession);
  const saveFn = useServerFn(saveProfile);
  const queryClient = useQueryClient();
  const autoHandled = useRef(false);
  const [status, setStatus] = useState<"idle" | "saving" | "saved" | "error">("idle");
  const session = useQuery({
    queryKey: ["auth-session"],
    queryFn: () => sessionFn(),
    staleTime: 30_000,
  });

  async function save() {
    if (!session.data?.user) {
      const returnUrl = new URL(window.location.href);
      returnUrl.searchParams.set("save", "1");
      window.location.assign(
        `/login?returnTo=${encodeURIComponent(returnUrl.pathname + returnUrl.search)}`,
      );
      return;
    }
    setStatus("saving");
    try {
      await saveFn({
        data: {
          name: `${profile.regionGroup === "all" ? "All regions" : profile.regionGroup} search · ${new Date().toLocaleDateString()}`,
          profile,
        },
      });
      await queryClient.invalidateQueries({ queryKey: ["saved-profiles"] });
      setStatus("saved");
      const url = new URL(window.location.href);
      url.searchParams.delete("save");
      window.history.replaceState(null, "", url.pathname + url.search);
    } catch {
      setStatus("error");
    }
  }

  useEffect(() => {
    if (!ready || session.isPending || autoHandled.current || typeof window === "undefined") return;
    if (new URLSearchParams(window.location.search).get("save") !== "1") return;
    autoHandled.current = true;
    void save();
  });

  return (
    <Button
      type="button"
      variant="outline"
      size="sm"
      disabled={!ready || status === "saving"}
      aria-label={status === "error" ? "Save failed. Retry saving this search" : undefined}
      onClick={() => void save()}
    >
      <BookmarkPlus className="mr-2 h-4 w-4" />
      {status === "saving"
        ? "Saving…"
        : status === "saved"
          ? "Saved"
          : status === "error"
            ? "Retry save"
            : "Save search"}
    </Button>
  );
}
