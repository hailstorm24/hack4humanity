import { ApiError } from "./api";

/** Branch on the error code, never on the server's message text. */
export function describeError(e: unknown, what = "do that"): string {
  if (e instanceof ApiError) {
    switch (e.body?.error) {
      case "model_unavailable":
        return "The classifier is unavailable right now. Try again in a moment.";
      case "not_found":
        return "Not found.";
      case "internal":
        return "Something went wrong on our side. Try again.";
      case "invalid_request":
        return "The request was rejected. This is a bug in the page; please report it.";
    }
    if (e.status === 0) return e.body?.message ?? "Can’t reach the server. Check your connection and try again.";
  }
  return `Couldn’t ${what}. Try again.`;
}
