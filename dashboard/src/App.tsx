import { useSyncExternalStore } from "react";
import { ClaimPage } from "./ClaimPage";
import { InstructionsPage } from "./InstructionsPage";
import { QueuePage } from "./QueuePage";

function subscribe(onChange: () => void): () => void {
  window.addEventListener("hashchange", onChange);
  return () => {
    window.removeEventListener("hashchange", onChange);
  };
}

const currentHash = () => window.location.hash;

function Page({ hash }: Readonly<{ hash: string }>) {
  const claim = /^#\/claims\/([\w-]+)$/.exec(hash);
  if (claim) return <ClaimPage key={claim[1]} claimId={claim[1]} />;
  if (hash === "#/instructions") return <InstructionsPage />;
  return <QueuePage />;
}

export function App() {
  const hash = useSyncExternalStore(subscribe, currentHash);
  const onInstructions = hash === "#/instructions";

  return (
    <div className="shell">
      <nav className="nav" aria-label="Main">
        <span className="brand">UnderCover</span>
        <a href="#/" aria-current={onInstructions ? undefined : "page"}>
          Claims
        </a>
        <a
          href="#/instructions"
          aria-current={onInstructions ? "page" : undefined}
        >
          Agent instructions
        </a>
      </nav>
      <main>
        <Page hash={hash} />
      </main>
    </div>
  );
}
