// Better Auth CLI entrypoint. Runtime requests use the request-scoped factory.
import { createGroundtruthAuth } from "./src/server/auth";

export const auth = createGroundtruthAuth().auth;
