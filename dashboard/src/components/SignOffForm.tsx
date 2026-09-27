import { type SyntheticEvent, useState } from "react";
import { api } from "../api";
import { useLoad } from "../useLoad";

export function SignOffForm({
  claimId,
  onSignedOff,
}: Readonly<{ claimId: string; onSignedOff: () => void }>) {
  const { data: handlers } = useLoad(api.listHandlers);
  const [handlerId, setHandlerId] = useState("");
  const [error, setError] = useState<string>();
  const [sending, setSending] = useState(false);

  function submit(event: SyntheticEvent<HTMLFormElement>) {
    event.preventDefault();
    setSending(true);
    api.signOff(claimId, handlerId).then(onSignedOff, (reason: unknown) => {
      setError(reason instanceof Error ? reason.message : "Sign-off failed");
      setSending(false);
    });
  }

  return (
    <form className="sign-off-form" onSubmit={submit}>
      <label>
        Handler
        <select
          value={handlerId}
          onChange={(event) => {
            setHandlerId(event.target.value);
          }}
        >
          <option value="" disabled>
            Choose a handler
          </option>
          {handlers
            ?.filter((handler) => handler.can_approve_over_limit)
            .map((handler) => (
              <option key={handler.handler_id} value={handler.handler_id}>
                {handler.name}
              </option>
            ))}
        </select>
      </label>
      <button type="submit" disabled={!handlerId || sending}>
        Sign off
      </button>
      {error && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}
    </form>
  );
}
