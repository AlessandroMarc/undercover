import { Link, NavLink, Outlet, Route, Routes } from "react-router";
import { Brand } from "./components/Brand";
import { RequireHandler } from "./components/RequireHandler";
import { SignOutButton } from "./components/SignOutButton";
import { useHandler } from "./handler";
import { ClaimPage } from "./pages/ClaimPage";
import { EvaluationPage } from "./pages/EvaluationPage";
import { InstructionsPage } from "./pages/InstructionsPage";
import { QueuePage } from "./pages/QueuePage";
import { ScoreboardPage } from "./pages/ScoreboardPage";
import { SignInPage } from "./pages/SignInPage";
import {
  CLAIM_PAGE,
  EVALUATION_PAGE,
  INSTRUCTIONS,
  QUEUE,
  SCOREBOARD,
  SIGN_IN,
} from "./paths";

export function App() {
  return (
    <Routes>
      <Route path={SIGN_IN} element={<SignInPage />} />
      <Route
        element={
          <RequireHandler>
            <SignedInLayout />
          </RequireHandler>
        }
      >
        <Route path={QUEUE} element={<QueuePage />} />
        <Route path={CLAIM_PAGE} element={<ClaimPage />} />
        <Route path={SCOREBOARD} element={<ScoreboardPage />} />
        <Route path={EVALUATION_PAGE} element={<EvaluationPage />} />
        <Route path={INSTRUCTIONS} element={<InstructionsPage />} />
        <Route path="*" element={<p className="message">Page not found</p>} />
      </Route>
    </Routes>
  );
}

function SignedInLayout() {
  const handler = useHandler();
  return (
    <>
      <header className="header">
        <Link to={QUEUE} className="brand">
          <Brand />
        </Link>
        <nav className="nav" aria-label="Main">
          <NavLink to={QUEUE} end>
            Queue
          </NavLink>
          <NavLink to={SCOREBOARD}>Scoreboard</NavLink>
          <NavLink to={INSTRUCTIONS}>Instructions</NavLink>
        </nav>
        <div className="who" role="group" aria-label="Signed in">
          <span className="who-name">{handler.name}</span>
          <span className="who-role muted">{handler.role}</span>
          <SignOutButton className="button quiet" />
        </div>
      </header>
      <main className="page">
        <Outlet />
      </main>
    </>
  );
}
