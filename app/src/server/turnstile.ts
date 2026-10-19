import { z } from "zod";

const TurnstileResponseSchema = z.object({
  success: z.boolean(),
  hostname: z.string().optional(),
  action: z.string().optional(),
  "error-codes": z.array(z.string()).optional(),
});

export type TurnstileVerification = z.infer<typeof TurnstileResponseSchema>;

export async function verifyTurnstileToken(
  token: string,
  options: {
    secretKey?: string;
    expectedAction?: string;
    expectedHostname?: string;
    remoteIp?: string;
    fetcher?: typeof fetch;
  } = {},
): Promise<TurnstileVerification> {
  const secretKey = options.secretKey ?? process.env.TURNSTILE_SECRET_KEY;
  if (!secretKey) {
    return { success: false, "error-codes": ["missing-secret"] };
  }
  if (!token || token.length > 2048) {
    return { success: false, "error-codes": ["invalid-token"] };
  }
  try {
    const response = await (options.fetcher ?? fetch)(
      "https://challenges.cloudflare.com/turnstile/v0/siteverify",
      {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          secret: secretKey,
          response: token,
          ...(options.remoteIp ? { remoteip: options.remoteIp } : {}),
          idempotency_key: crypto.randomUUID(),
        }),
      },
    );
    if (!response.ok) return { success: false, "error-codes": ["siteverify-unavailable"] };
    const result = TurnstileResponseSchema.parse(await response.json());
    if (!result.success) return result;
    if (options.expectedAction && result.action !== options.expectedAction) {
      return { ...result, success: false, "error-codes": ["action-mismatch"] };
    }
    if (options.expectedHostname && result.hostname !== options.expectedHostname) {
      return { ...result, success: false, "error-codes": ["hostname-mismatch"] };
    }
    return result;
  } catch {
    return { success: false, "error-codes": ["siteverify-unavailable"] };
  }
}
