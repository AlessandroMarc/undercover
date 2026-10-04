import { ApiError } from "../api";

// What a page shows until its data arrives: that it's loading, that it wasn't
// found, when that's given, or why it failed.
export function Message({
  error,
  notFound,
}: Readonly<{ error?: Error; notFound?: string }>) {
  if (notFound && error instanceof ApiError && error.status === 404)
    return (
      <p className="message" role="status">
        {notFound}
      </p>
    );
  return (
    <p className="message" role={error ? "alert" : "status"}>
      {error ? error.message : "Loading..."}
    </p>
  );
}
