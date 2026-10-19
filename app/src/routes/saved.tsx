import { createFileRoute } from "@tanstack/react-router";
import { SavedDashboard } from "@/components/auth/SavedDashboard";

export const Route = createFileRoute("/saved")({ component: SavedDashboard });
