import { BrowserRouter, Routes, Route, NavLink } from "react-router-dom";
import Overview from "./pages/Overview";
import IncidentList from "./pages/IncidentList";
import IncidentDetail from "./pages/IncidentDetail";
import Setup from "./pages/Setup";

const BASE = "/app";

function Nav() {
  const link = "text-sm transition-colors";
  const active = "text-white";
  const inactive = "text-[#888] hover:text-white";

  return (
    <header className="border-b border-white/[0.08] sticky top-0 z-50 bg-black/80 backdrop-blur-md">
      <div className="mx-auto max-w-5xl flex items-center justify-between px-6 h-14">
        <NavLink to={`${BASE}/`} className="flex items-center gap-2.5">
          <div className="h-6 w-6 rounded bg-white flex items-center justify-center">
            <span className="text-black text-xs font-bold leading-none">K</span>
          </div>
          <span className="text-sm font-semibold tracking-tight">Klarsicht</span>
        </NavLink>
        <nav className="flex items-center gap-6">
          <NavLink to={`${BASE}/`} end className={({ isActive }) => `${link} ${isActive ? active : inactive}`}>
            Overview
          </NavLink>
          <NavLink to={`${BASE}/incidents`} className={({ isActive }) => `${link} ${isActive ? active : inactive}`}>
            Incidents
          </NavLink>
          <NavLink to={`${BASE}/setup`} className={({ isActive }) => `${link} ${isActive ? active : inactive}`}>
            Setup
          </NavLink>
        </nav>
      </div>
    </header>
  );
}

export default function App() {
  return (
    <BrowserRouter basename={BASE}>
      <div className="min-h-screen bg-black text-white">
        <Nav />
        <Routes>
          <Route path="/" element={<Overview />} />
          <Route path="/incidents" element={<IncidentList />} />
          <Route path="/incidents/:id" element={<IncidentDetail />} />
          <Route path="/setup" element={<Setup />} />
        </Routes>
      </div>
    </BrowserRouter>
  );
}
