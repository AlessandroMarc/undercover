import { signOut } from "../auth";

export function SignOutButton({ className }: Readonly<{ className: string }>) {
  return (
    <button
      type="button"
      className={className}
      onClick={() => {
        void signOut();
      }}
    >
      Sign out
    </button>
  );
}
