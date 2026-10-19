import { createServerFn } from "@tanstack/react-start";
import { getRequestHeaders } from "@tanstack/react-start/server";
import { createGroundtruthAuth } from "@/server/auth";

export const getSession = createServerFn({ method: "GET" }).handler(async () => {
  const { auth, close } = createGroundtruthAuth();
  try {
    return await auth.api.getSession({ headers: getRequestHeaders() });
  } finally {
    await close();
  }
});
