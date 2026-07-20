import { Routes, Route, Navigate } from 'react-router-dom';
import Layout from './components/Layout';
import ProjectsPage from './pages/ProjectsPage';
import ProjectOverview from './pages/ProjectOverview';
import ProjectSettingsPage from './pages/ProjectSettingsPage';
import RequirementsPage from './pages/RequirementsPage';
import RequirementDetailPage from './pages/RequirementDetailPage';
import SpecificationsPage from './pages/SpecificationsPage';
import ComponentsPage from './pages/ComponentsPage';
import ComponentDetailPage from './pages/ComponentDetailPage';
import VerificationPage from './pages/VerificationPage';
import TraceMatrixPage from './pages/TraceMatrixPage';
import GraphView from './pages/GraphView';
import ChangeRequestsPage from './pages/ChangeRequestsPage';
import RisksPage from './pages/RisksPage';
import MetricsPage from './pages/MetricsPage';
import PublishPage from './pages/PublishPage';
import UsersPage from './pages/UsersPage';
import SystemPage from './pages/SystemPage';

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route path="/" element={<ProjectsPage />} />
        <Route path="/users" element={<UsersPage />} />
        <Route path="/system" element={<SystemPage />} />
        <Route path="/project/:projectId" element={<ProjectOverview />} />
        <Route path="/project/:projectId/settings" element={<ProjectSettingsPage />} />
        <Route path="/project/:projectId/requirements" element={<RequirementsPage />} />
        <Route path="/project/:projectId/requirements/:reqId" element={<RequirementDetailPage />} />
        <Route path="/project/:projectId/specifications" element={<SpecificationsPage />} />
        <Route path="/project/:projectId/components/:componentId" element={<ComponentDetailPage />} />
        <Route path="/project/:projectId/components" element={<ComponentsPage />} />
        <Route path="/project/:projectId/verification" element={<VerificationPage />} />
        <Route path="/project/:projectId/traces" element={<TraceMatrixPage />} />
        <Route path="/project/:projectId/graph" element={<GraphView />} />
        <Route path="/project/:projectId/change-requests" element={<ChangeRequestsPage />} />
        <Route path="/project/:projectId/risks" element={<RisksPage />} />
        <Route path="/project/:projectId/metrics" element={<MetricsPage />} />
        <Route path="/project/:projectId/publish" element={<PublishPage />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
