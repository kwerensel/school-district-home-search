import { createFileRoute } from "@tanstack/react-router";
import { createGroundtruthAuth } from "@/server/auth";

async function handle(request: Request) {
  const { auth, close } = createGroundtruthAuth();
  try {
    return await auth.handler(request);
  } finally {
    await close();
  }
}

export const Route = createFileRoute("/api/auth/$")({
  server: {
    handlers: {
      GET: ({ request }) => handle(request),
      POST: ({ request }) => handle(request),
    },
  },
});
