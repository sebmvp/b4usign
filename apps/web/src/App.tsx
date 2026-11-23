import { Link, Route, Routes } from "react-router-dom";
import { EngineeringPage } from "./pages/Engineering";
import { LandingPage } from "./pages/Landing";
import { ReportPage } from "./pages/Report";
import { SourcesPage } from "./pages/Sources";

export function App() {
  return (
    <>
      <header className="nav no-print">
        <Link to="/" className="wordmark">
          Before You Sign
        </Link>
        <nav>
          <Link to="/sources">Sources</Link>
          <Link to="/engineering">Records log</Link>
        </nav>
      </header>
      <Routes>
        <Route path="/" element={<LandingPage />} />
        <Route path="/property/:propertyId" element={<ReportPage />} />
        <Route path="/sources" element={<SourcesPage />} />
        <Route path="/engineering" element={<EngineeringPage />} />
      </Routes>
    </>
  );
}
