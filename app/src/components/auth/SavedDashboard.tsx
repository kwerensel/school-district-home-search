import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useServerFn } from "@tanstack/react-start";
import { Heart, Search, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { authClient } from "@/lib/auth-client";
import { getSession } from "@/lib/auth.functions";
import { serializeDiscoveryProfile, type DiscoveryProfile } from "@/lib/discovery/profile";
import { deleteProfile, listFavorites, listProfiles } from "@/lib/saved/persistence.functions";

type SavedProfileRow = { id: number; name: string; profile: DiscoveryProfile; updated_at: string };
type FavoriteRow = {
  listing_id: number;
  address: string;
  city: string;
  price: number;
  beds: number;
  baths: number;
  school_district: string;
};

export function SavedDashboard() {
  const [actionError, setActionError] = useState("");
  const sessionFn = useServerFn(getSession);
  const profilesFn = useServerFn(listProfiles);
  const favoritesFn = useServerFn(listFavorites);
  const deleteFn = useServerFn(deleteProfile);
  const queryClient = useQueryClient();
  const session = useQuery({ queryKey: ["auth-session"], queryFn: () => sessionFn() });
  const profiles = useQuery({
    queryKey: ["saved-profiles"],
    queryFn: () => profilesFn() as Promise<SavedProfileRow[]>,
    enabled: Boolean(session.data?.user),
  });
  const favorites = useQuery({
    queryKey: ["favorites"],
    queryFn: () => favoritesFn() as Promise<FavoriteRow[]>,
    enabled: Boolean(session.data?.user),
  });

  if (session.isPending) return <main className="p-8 text-sm text-muted-foreground">Loading…</main>;
  if (session.isError)
    return (
      <main className="p-8">
        <p className="text-sm" role="alert">
          Your account could not be loaded.
        </p>
        <Button className="mt-3" onClick={() => void session.refetch()}>
          Try again
        </Button>
        <a className="ml-4 text-sm underline" href="/discover/results">
          Continue signed out
        </a>
      </main>
    );
  if (!session.data?.user) {
    return (
      <main className="flex min-h-screen items-center justify-center p-4">
        <section className="max-w-md rounded-lg border p-6 text-center">
          <h1 className="text-xl font-semibold">Your saved Groundtruth searches</h1>
          <p className="mt-2 text-sm text-muted-foreground">
            Sign in to see saved searches and favorites. The rest of Groundtruth remains available
            without an account.
          </p>
          <Button asChild className="mt-4">
            <a href="/login?returnTo=%2Fsaved">Sign in</a>
          </Button>
          <Button asChild variant="ghost" className="mt-2">
            <a href="/discover/results">Continue signed out</a>
          </Button>
        </section>
      </main>
    );
  }

  return (
    <main className="mx-auto min-h-screen max-w-5xl p-4 md:p-8">
      <header className="flex flex-wrap items-center justify-between gap-3 border-b pb-5">
        <div>
          <h1 className="text-2xl font-semibold">Saved</h1>
          <p className="text-sm text-muted-foreground">Signed in as {session.data.user.email}</p>
        </div>
        <div className="flex gap-2">
          <Button asChild variant="outline">
            <a href="/discover/results">
              <Search className="mr-2 h-4 w-4" />
              Discovery
            </a>
          </Button>
          <Button
            variant="destructive"
            onClick={async () => {
              if (
                !window.confirm(
                  "Delete your account and all saved Groundtruth data? This cannot be undone.",
                )
              )
                return;
              setActionError("");
              try {
                const result = await authClient.deleteUser();
                if (result.error) throw new Error("Delete failed");
                window.location.assign("/");
              } catch {
                setActionError(
                  "Your account could not be deleted. Please sign in again and retry.",
                );
              }
            }}
          >
            Delete account
          </Button>
        </div>
      </header>
      {actionError ? (
        <p className="mt-4 text-sm text-destructive" role="alert">
          {actionError}
        </p>
      ) : null}
      <div className="mt-8 grid gap-8 md:grid-cols-2">
        <section>
          <h2 className="text-lg font-semibold">Saved searches</h2>
          <div className="mt-3 space-y-3">
            {(profiles.data ?? []).map((item) => {
              const href = `/discover/results?${serializeDiscoveryProfile(item.profile).toString()}`;
              return (
                <article key={item.id} className="rounded-md border p-4">
                  <div className="flex justify-between gap-3">
                    <div>
                      <a className="font-medium hover:underline" href={href}>
                        {item.name}
                      </a>
                      <p className="mt-1 text-xs text-muted-foreground">
                        Updated {new Date(item.updated_at).toLocaleDateString()}
                      </p>
                    </div>
                    <Button
                      variant="ghost"
                      size="icon"
                      aria-label={`Delete ${item.name}`}
                      onClick={async () => {
                        setActionError("");
                        try {
                          await deleteFn({ data: { id: Number(item.id) } });
                          await queryClient.invalidateQueries({ queryKey: ["saved-profiles"] });
                        } catch {
                          setActionError(
                            "This saved search could not be deleted. Please try again.",
                          );
                        }
                      }}
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </div>
                </article>
              );
            })}
            {profiles.isPending ? (
              <p className="text-sm text-muted-foreground" role="status">
                Loading saved searches…
              </p>
            ) : null}
            {profiles.isError ? (
              <div className="space-y-2">
                <p className="text-sm" role="alert">
                  Saved searches could not be loaded.
                </p>
                <Button size="sm" variant="outline" onClick={() => void profiles.refetch()}>
                  Try again
                </Button>
              </div>
            ) : null}
            {profiles.isSuccess && !profiles.data?.length ? (
              <p className="text-sm text-muted-foreground">No saved searches yet.</p>
            ) : null}
          </div>
        </section>
        <section>
          <h2 className="flex items-center gap-2 text-lg font-semibold">
            <Heart className="h-5 w-5" />
            Favorites
          </h2>
          <div className="mt-3 space-y-3">
            {(favorites.data ?? []).map((item) => (
              <article key={item.listing_id} className="rounded-md border p-4">
                <p className="font-medium">{item.address}</p>
                <p className="text-sm text-muted-foreground">
                  {item.city} · {item.school_district}
                </p>
                <p className="mt-2 text-sm">
                  ${Number(item.price).toLocaleString()} · {item.beds} bd · {item.baths} ba
                </p>
              </article>
            ))}
            {favorites.isPending ? (
              <p className="text-sm text-muted-foreground" role="status">
                Loading favorites…
              </p>
            ) : null}
            {favorites.isError ? (
              <div className="space-y-2">
                <p className="text-sm" role="alert">
                  Favorites could not be loaded.
                </p>
                <Button size="sm" variant="outline" onClick={() => void favorites.refetch()}>
                  Try again
                </Button>
              </div>
            ) : null}
            {favorites.isSuccess && !favorites.data?.length ? (
              <p className="text-sm text-muted-foreground">No favorite listings yet.</p>
            ) : null}
          </div>
        </section>
      </div>
    </main>
  );
}
