import { Suspense, lazy } from 'react';
import { Routes, Route, Navigate } from 'react-router-dom';
import Layout from './components/Layout';
import LoadingSplash from './components/LoadingSplash';

const ProjectsPage = lazy(() => import('./pages/ProjectsPage'));
const ProjectOverview = lazy(() => import('./pages/ProjectOverview'));
const ProjectSettingsPage = lazy(() => import('./pages/ProjectSettingsPage'));
const RequirementsPage = lazy(() => import('./pages/RequirementsPage'));
const RequirementDetailPage = lazy(() => import('./pages/RequirementDetailPage'));
const SpecificationsPage = lazy(() => import('./pages/SpecificationsPage'));
const ComponentsPage = lazy(() => import('./pages/ComponentsPage'));
const ComponentDetailPage = lazy(() => import('./pages/ComponentDetailPage'));
const VerificationPage = lazy(() => import('./pages/VerificationPage'));
const TraceMatrixPage = lazy(() => import('./pages/TraceMatrixPage'));
const GraphView = lazy(() => import('./pages/GraphView'));
const ChangeRequestsPage = lazy(() => import('./pages/ChangeRequestsPage'));
const RisksPage = lazy(() => import('./pages/RisksPage'));
const MetricsPage = lazy(() => import('./pages/MetricsPage'));
const BaselinesPage = lazy(() => import('./pages/BaselinesPage'));
const AllocationMatrixPage = lazy(() => import('./pages/AllocationMatrixPage'));
const PublishPage = lazy(() => import('./pages/PublishPage'));
const UsersPage = lazy(() => import('./pages/UsersPage'));
const SystemPage = lazy(() => import('./pages/SystemPage'));
const SettingsPage = lazy(() => import('./pages/SettingsPage'));

function PageFallback() {
  return <LoadingSplash label="Loading..." />;
}

export default function App() {
  return (
    <Suspense fallback={<PageFallback />}>
      <Routes>
        <Route element={<Layout />}>
          <Route path="/" element={<ProjectsPage />} />
          <Route path="/users" element={<UsersPage />} />
          <Route path="/system" element={<SystemPage />} />
          <Route path="/settings" element={<SettingsPage />} />
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
          <Route path="/project/:projectId/baselines" element={<BaselinesPage />} />
          <Route path="/project/:projectId/allocation" element={<AllocationMatrixPage />} />
          <Route path="/project/:projectId/publish" element={<PublishPage />} />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Suspense>
  );
}
