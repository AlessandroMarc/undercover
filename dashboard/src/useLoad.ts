import { useEffect, useState } from "react";

interface Loaded<T> {
  data: T | undefined;
  failed: boolean;
  reload: () => void;
}

export function useLoad<T>(
  load: () => Promise<T>,
  refreshMs: number | null,
): Loaded<T> {
  const [data, setData] = useState<T>();
  const [failed, setFailed] = useState(false);
  const [version, setVersion] = useState(0);

  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const tick = () => {
      void load()
        .then(
          (next) => {
            if (cancelled) return;
            setData(next);
            setFailed(false);
          },
          () => {
            if (!cancelled) setFailed(true);
          },
        )
        .finally(() => {
          if (!cancelled && refreshMs !== null) {
            timer = setTimeout(tick, refreshMs);
          }
        });
    };
    tick();
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [load, refreshMs, version]);

  return {
    data,
    failed,
    reload: () => {
      setVersion((current) => current + 1);
    },
  };
}
