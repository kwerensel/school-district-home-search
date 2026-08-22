const SAFE_ERROR_MESSAGE = "Internal application error";

export type SafeErrorLog = {
  name: string;
  message: string;
};

export function safeErrorForLog(error: unknown): SafeErrorLog {
  return {
    name: error instanceof Error && error.name ? error.name : "Error",
    message: SAFE_ERROR_MESSAGE,
  };
}
