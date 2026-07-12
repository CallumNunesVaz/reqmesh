import { useParams } from 'react-router-dom';
import GraphPane from '../components/GraphPane';

export default function GraphView() {
  const { projectId } = useParams<{ projectId: string }>();

  if (!projectId) return null;

  return (
    <div className="w-full h-[calc(100vh-3.5rem)]">
      <GraphPane projectId={projectId} />
    </div>
  );
}
