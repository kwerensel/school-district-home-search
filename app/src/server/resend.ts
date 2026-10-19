export async function sendPasswordResetEmail(input: {
  to: string;
  name: string;
  resetUrl: string;
  fetcher?: typeof fetch;
}) {
  const apiKey = process.env.RESEND_API_KEY;
  if (!apiKey) throw new Error("RESEND_API_KEY is not configured");
  const from = process.env.RESEND_FROM_EMAIL || "Groundtruth <onboarding@resend.dev>";
  const response = await (input.fetcher ?? fetch)("https://api.resend.com/emails", {
    method: "POST",
    headers: {
      authorization: `Bearer ${apiKey}`,
      "content-type": "application/json",
    },
    body: JSON.stringify({
      from,
      to: [input.to],
      subject: "Reset your Groundtruth password",
      text: `Hi ${input.name},\n\nReset your Groundtruth password: ${input.resetUrl}\n\nIf you did not request this, you can ignore this email.`,
    }),
  });
  if (!response.ok) throw new Error(`Resend request failed (${response.status})`);
}
