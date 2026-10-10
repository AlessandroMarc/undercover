import { type ReactNode, useId } from "react";

// A short form asking the handler for a few words, such as why a proposal is
// rejected or what the agent should look at again, which sends nothing until
// they're written. The words are the caller's, so they outlast the form.
export function ReasonForm({
  id,
  label,
  hint,
  submitLabel,
  value,
  onChange,
  sending,
  onSubmit,
  maxLength,
  children,
}: Readonly<{
  id: string;
  label: string;
  hint: ReactNode;
  submitLabel: ReactNode;
  value: string;
  onChange: (value: string) => void;
  sending: boolean;
  onSubmit: () => void;
  maxLength?: number;
  children?: ReactNode;
}>) {
  const textId = useId();
  const ready = value.trim() !== "";
  return (
    <form
      id={id}
      className="reason-form"
      onSubmit={(event) => {
        event.preventDefault();
        if (!sending && ready) onSubmit();
      }}
    >
      <label htmlFor={textId}>{label}</label>
      <textarea
        id={textId}
        required
        rows={3}
        maxLength={maxLength}
        value={value}
        onChange={(event) => {
          onChange(event.target.value);
        }}
      />
      <p className="muted small">{hint}</p>
      <button
        type="submit"
        className="button"
        aria-disabled={sending || !ready}
      >
        {submitLabel}
      </button>
      {children}
    </form>
  );
}
