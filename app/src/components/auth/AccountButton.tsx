import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useServerFn } from "@tanstack/react-start";
import { LogOut, UserRound } from "lucide-react";
import { Button } from "@/components/ui/button";
import { authClient } from "@/lib/auth-client";
import { getSession } from "@/lib/auth.functions";

export function AccountButton({ returnTo }: { returnTo?: string }) {
  const [currentUrl, setCurrentUrl] = useState("/saved");
  useEffect(() => {
    setCurrentUrl(window.location.pathname + window.location.search);
  }, []);
  const getSessionFn = useServerFn(getSession);
  const queryClient = useQueryClient();
  const session = useQuery({
    queryKey: ["auth-session"],
    queryFn: () => getSessionFn(),
    staleTime: 30_000,
  });

  if (session.data?.user) {
    return (
      <div className="flex items-center gap-1">
        <Button asChild variant="outline" size="sm">
          <a href="/saved">
            <UserRound className="mr-2 h-4 w-4" />
            Saved
          </a>
        </Button>
        <Button
          type="button"
          variant="ghost"
          size="icon"
          aria-label="Sign out"
          onClick={async () => {
            await authClient.signOut();
            await queryClient.invalidateQueries({ queryKey: ["auth-session"] });
          }}
        >
          <LogOut className="h-4 w-4" />
        </Button>
      </div>
    );
  }

  return (
    <Button asChild variant="outline" size="sm">
      <a
        href={`/login?returnTo=${encodeURIComponent(returnTo ?? currentUrl)}`}
        onClick={(event) => {
          const destination = returnTo ?? window.location.pathname + window.location.search;
          event.currentTarget.href = `/login?returnTo=${encodeURIComponent(destination)}`;
        }}
      >
        Sign in
      </a>
    </Button>
  );
}
