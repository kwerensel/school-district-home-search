import { createFileRoute } from "@tanstack/react-router";
import { OperatorDashboard } from "@/components/operator/OperatorDashboard";
export const Route = createFileRoute("/operator")({ component: OperatorDashboard });
