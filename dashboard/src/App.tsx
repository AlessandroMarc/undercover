import { Link, NavLink, Route, Routes } from "react-router";
import { ClaimPage } from "./pages/ClaimPage";
import { EvaluationPage } from "./pages/EvaluationPage";
import { InstructionsPage } from "./pages/InstructionsPage";
import { QueuePage } from "./pages/QueuePage";
import { ScoreboardPage } from "./pages/ScoreboardPage";
import {
  CLAIM_PAGE,
  EVALUATION_PAGE,
  INSTRUCTIONS,
  QUEUE,
  SCOREBOARD,
} from "./paths";

export function App() {
  return (
    <>
      <header className="header">
        <Link to={QUEUE} className="brand">
          UnderCover <span className="tagline">claims pilot</span>
        </Link>
        <nav className="nav" aria-label="Main">
          <NavLink to={QUEUE} end>
            Queue
          </NavLink>
          <NavLink to={SCOREBOARD}>Scoreboard</NavLink>
          <NavLink to={INSTRUCTIONS}>Instructions</NavLink>
        </nav>
      </header>
      <main className="page">
        <Routes>
          <Route path={QUEUE} element={<QueuePage />} />
          <Route path={CLAIM_PAGE} element={<ClaimPage />} />
          <Route path={SCOREBOARD} element={<ScoreboardPage />} />
          <Route path={EVALUATION_PAGE} element={<EvaluationPage />} />
          <Route path={INSTRUCTIONS} element={<InstructionsPage />} />
          <Route path="*" element={<p className="message">Page not found</p>} />
        </Routes>
      </main>
    </>
  );
}
