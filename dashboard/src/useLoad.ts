import { useEffect, useState } from "react";
import { ApiError } from "./api";

export const REFRESH_MS = 2000;

export interface Loaded<T> {
  data?: T;
  error?: Error;
}

// Loads data once, or again every refreshMs milliseconds when that's given,
// stopping if the data isn't found. `load` must keep the same identity between
// renders, as with useCallback.
export function useLoad<T>(
  load: () => Promise<T>,
  refreshMs?: number,
): Loaded<T> {
  const [loaded, setLoaded] = useState<Loaded<T>>({});

  useEffect(() => {
    let active = true;
    const fetchNow = () => {
      load().then(
        (data) => {
          if (active) setLoaded({ data });
        },
        (error: unknown) => {
          if (error instanceof ApiError && error.status === 404)
            clearInterval(timer);
          if (active)
            setLoaded((previous) => ({
              data: previous.data,
              error:
                error instanceof Error
                  ? error
                  : new Error("The request failed"),
            }));
        },
      );
    };
    fetchNow();
    const timer =
      refreshMs === undefined ? undefined : setInterval(fetchNow, refreshMs);
    return () => {
      active = false;
      clearInterval(timer);
    };
  }, [load, refreshMs]);

  return loaded;
}
