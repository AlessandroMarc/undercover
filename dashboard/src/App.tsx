import {
  Link,
  Navigate,
  NavLink,
  Outlet,
  Route,
  Routes,
  useMatch,
} from "react-router";
import { Brand } from "./components/Brand";
import { RequireHandler } from "./components/RequireHandler";
import { SignOutButton } from "./components/SignOutButton";
import { StateMessage } from "./components/StateMessage";
import { useHandler } from "./handler";
import { ClaimPage } from "./pages/ClaimPage";
import { ConfigurationPage } from "./pages/ConfigurationPage";
import { EvaluationPage } from "./pages/EvaluationPage";
import { ImprovementPage } from "./pages/ImprovementPage";
import { QueuePage } from "./pages/QueuePage";
import { RecipePage } from "./pages/RecipePage";
import { ScoreboardPage } from "./pages/ScoreboardPage";
import { SettingsPage } from "./pages/SettingsPage";
import { SignInPage } from "./pages/SignInPage";
import { VersionPage } from "./pages/VersionPage";
import {
  CLAIM_PAGE,
  CONFIGURATION,
  EVALUATION_PAGE,
  IMPROVEMENT,
  INSTRUCTIONS,
  QUEUE,
  RECIPE_PAGE,
  SCOREBOARD,
  SETTINGS,
  SIGN_IN,
  VERSION_PAGE,
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
        <Route path={IMPROVEMENT} element={<ImprovementPage />} />
        <Route path={RECIPE_PAGE} element={<RecipePage />} />
        <Route path={CONFIGURATION} element={<ConfigurationPage />} />
        <Route path={VERSION_PAGE} element={<VersionPage />} />
        <Route path={SETTINGS} element={<SettingsPage />} />
        <Route
          path={INSTRUCTIONS}
          element={<Navigate to={CONFIGURATION} replace />}
        />
        <Route
          path="*"
          element={
            <StateMessage empty="Page not found. Choose a page from the header." />
          }
        />
      </Route>
    </Routes>
  );
}

function SignedInLayout() {
  const handler = useHandler();
  // A claim's page belongs to the queue.
  const queuePage = useMatch(QUEUE);
  const claimPage = useMatch(CLAIM_PAGE);
  const onQueue = queuePage !== null || claimPage !== null;
  return (
    <>
      <header className="header">
        <Link to={QUEUE} className="brand">
          <Brand />
        </Link>
        <nav className="nav" aria-label="Main">
          <Link
            to={QUEUE}
            className={onQueue ? "active" : undefined}
            aria-current={onQueue ? "page" : undefined}
          >
            Queue
          </Link>
          <NavLink to={SCOREBOARD}>Scoreboard</NavLink>
          <NavLink to={IMPROVEMENT}>Improvement</NavLink>
          <NavLink to={CONFIGURATION}>Configuration</NavLink>
          <NavLink to={SETTINGS}>Settings</NavLink>
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
