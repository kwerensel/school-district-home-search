import { createFileRoute } from "@tanstack/react-router";
import { PasswordResetCard } from "@/components/auth/PasswordResetCard";

export const Route = createFileRoute("/reset-password")({
  component: () => <PasswordResetCard mode="reset" />,
});
