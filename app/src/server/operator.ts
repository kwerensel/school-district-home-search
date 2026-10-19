import { getRequestHeaders } from "@tanstack/react-start/server";
import { createGroundtruthAuth } from "./auth";
import { sql } from "./db";

export async function requireOperator() {
  if (process.env.GROUNDTRUTH_OPERATOR_ENABLED !== "true")
    throw new Error("Operator access unavailable");
  const { auth, close } = createGroundtruthAuth();
  try {
    const session = await auth.api.getSession({ headers: getRequestHeaders() });
    if (!session) throw new Error("Operator access unavailable");
    const rows =
      await sql`SELECT 1 FROM operator_roles WHERE user_id=${session.user.id} AND role='admin'`;
    if (!rows.length) throw new Error("Operator access unavailable");
    return session.user.id;
  } finally {
    await close();
  }
}
