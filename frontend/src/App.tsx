import { useEffect, useState } from 'react';
import { Route, Routes } from 'react-router-dom';
import { Sidebar } from './components/Sidebar';
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

  useEffect(() => {
    fetchHealth()
      .then(setHealth)
      .catch(() => setHealth(null));
  }, []);

  return (
    <div className="flex min-h-screen bg-slate-950">
      <Sidebar health={health} />
      <main className="flex-1 overflow-y-auto p-8">
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
      </main>
    </div>
  );
}

export default App;
