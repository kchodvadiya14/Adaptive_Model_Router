import { useEffect, useState } from 'react';
import { Route, Routes, useLocation } from 'react-router-dom';
import { Header } from './components/Header';
import { Sidebar } from './components/Sidebar';
import { findActiveNavItem } from './config/navigation';
import { AnalyticsPage } from './pages/AnalyticsPage';
import { BenchmarkPage } from './pages/BenchmarkPage';
import { ChatPage } from './pages/ChatPage';
import { DatasetPage } from './pages/DatasetPage';
import { ExperimentsPage } from './pages/ExperimentsPage';
import { ModelsPage } from './pages/ModelsPage';
import { OverviewPage } from './pages/OverviewPage';
import { SettingsPage } from './pages/SettingsPage';
import { TrainingPage } from './pages/TrainingPage';
import { fetchHealth } from './services/api';
import type { HealthResponse } from './types';

function App() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const location = useLocation();

  useEffect(() => {
    fetchHealth()
      .then(setHealth)
      .catch(() => setHealth(null));
  }, []);

  useEffect(() => {
    setMobileNavOpen(false);
  }, [location.pathname]);

  const active = findActiveNavItem(location.pathname);

  return (
    <div className="flex min-h-screen bg-surface-0">
      <Sidebar health={health} mobileOpen={mobileNavOpen} onMobileClose={() => setMobileNavOpen(false)} />
      <div className="flex min-h-screen w-full flex-1 flex-col">
        <Header
          title={active?.item.label ?? 'Adaptive AI Gateway'}
          group={active?.group}
          health={health}
          onMenuClick={() => setMobileNavOpen(true)}
        />
        <main className="flex-1 overflow-y-auto">
          <div className="mx-auto w-full max-w-7xl px-4 py-6 sm:px-6 lg:px-8 lg:py-8">
            <Routes>
              <Route path="/" element={<OverviewPage />} />
              <Route path="/chat" element={<ChatPage />} />
              <Route path="/analytics" element={<AnalyticsPage />} />
              <Route path="/models" element={<ModelsPage />} />
              <Route path="/benchmark" element={<BenchmarkPage />} />
              <Route path="/dataset" element={<DatasetPage />} />
              <Route path="/training" element={<TrainingPage />} />
              <Route path="/experiments" element={<ExperimentsPage />} />
              <Route path="/settings" element={<SettingsPage />} />
            </Routes>
          </div>
        </main>
      </div>
    </div>
  );
}

export default App;
