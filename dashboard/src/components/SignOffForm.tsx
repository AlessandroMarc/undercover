import { useState } from "react";
import { api } from "../api";
import { useLoad } from "../useLoad";
import { ActionForm } from "./ActionForm";

export function SignOffForm({
  claimId,
  onSignedOff,
}: Readonly<{ claimId: string; onSignedOff: () => void }>) {
  const { data: handlers } = useLoad(api.listHandlers);
  const [handlerId, setHandlerId] = useState("");

  return (
    <ActionForm
      label="Sign off"
      ready={handlerId !== ""}
      action={() => api.signOff(claimId, handlerId).then(onSignedOff)}
    >
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
    </ActionForm>
  );
}
