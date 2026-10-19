import { createFileRoute } from "@tanstack/react-router";
import { PasswordResetCard } from "@/components/auth/PasswordResetCard";

export const Route = createFileRoute("/forgot-password")({
  component: () => <PasswordResetCard mode="request" />,
});
