import { BrowserRouter, Routes, Route } from "react-router-dom";
import IncidentList from "./pages/IncidentList";
import IncidentDetail from "./pages/IncidentDetail";

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<IncidentList />} />
        <Route path="/incidents/:id" element={<IncidentDetail />} />
      </Routes>
    </BrowserRouter>
  );
}
