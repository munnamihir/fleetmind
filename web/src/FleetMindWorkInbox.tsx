import {
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  ClipboardCheck,
  Clock3,
  Inbox,
  RefreshCw,
  ShieldCheck,
  X,
} from 'lucide-react';
import { useCallback, useEffect, useMemo, useState } from 'react';

import './FleetMindWorkInbox.css';

const API = import.meta.env.VITE_API_URL ?? 'http://localhost:8000';

type CommandSummary = {
  attentionRequired: number;
  workflow: {
    pendingApproval: number;
    approvedReady: number;
    executed: number;
  };
};

type QueueSummary = {
  activeRecommendations: number;
  unassignedActive: number;
  overdueActive: number;
};

type OutcomeSummary = {
  total: number;
  byStatus: Array<{
    status: string;
    count: number;
  }>;
};

type WorkItem = {
  id: string;
  label: string;
  count: number;
  description: string;
  pageLabel: string;
  viewLabel: string;
  urgent?: boolean;
};

async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(`${API}${path}`);
  if (!response.ok) {
    throw new Error(`${response.status} ${response.statusText}`);
  }
  return response.json() as Promise<T>;
}

function clickButtonByText(selector: string, label: string) {
  const normalized = label.trim().toLowerCase();
  const button = Array.from(
    document.querySelectorAll<HTMLButtonElement>(selector),
  ).find(candidate => candidate.textContent?.trim().toLowerCase() === normalized);
  button?.click();
  return Boolean(button);
}

function navigate(item: WorkItem) {
  const changed = clickButtonByText('.sidebar nav button', item.pageLabel);
  window.setTimeout(() => {
    clickButtonByText('[role="tab"].dashboardPageTab', item.viewLabel);
  }, changed ? 40 : 0);
}

export function FleetMindWorkInbox() {
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [command, setCommand] = useState<CommandSummary | null>(null);
  const [queue, setQueue] = useState<QueueSummary | null>(null);
  const [outcomes, setOutcomes] = useState<OutcomeSummary | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const [nextCommand, nextQueue, nextOutcomes] = await Promise.all([
        getJson<CommandSummary>('/api/v1/diagnostics/fleet-command/summary'),
        getJson<QueueSummary>('/api/v1/diagnostics/decision-queue/summary'),
        getJson<OutcomeSummary>('/api/v1/diagnostics/closed-loop/outcomes/summary'),
      ]);
      setCommand(nextCommand);
      setQueue(nextQueue);
      setOutcomes(nextOutcomes);
      setError(null);
    } catch (refreshError) {
      setError(
        refreshError instanceof Error
          ? refreshError.message
          : 'Operator work summary unavailable',
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
    const timer = window.setInterval(() => void refresh(), 20000);
    return () => window.clearInterval(timer);
  }, [refresh]);

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') setOpen(false);
    }
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, []);

  const worsening =
    outcomes?.byStatus.find(row => row.status === 'WORSENED')?.count ?? 0;

  const workItems = useMemo<WorkItem[]>(
    () => [
      {
        id: 'approvals',
        label: 'Approval required',
        count: command?.workflow.pendingApproval ?? 0,
        description: 'Recommendations waiting for an explicit human approval decision.',
        pageLabel: 'Root Cause',
        viewLabel: 'Actions & Outcomes',
        urgent: true,
      },
      {
        id: 'ready',
        label: 'Ready to execute',
        count: command?.workflow.approvedReady ?? 0,
        description: 'Approved recommendations that still require an explicit execution action.',
        pageLabel: 'Root Cause',
        viewLabel: 'Actions & Outcomes',
      },
      {
        id: 'unassigned',
        label: 'Unassigned active work',
        count: queue?.unassignedActive ?? 0,
        description: 'Active queue records without an operator owner.',
        pageLabel: 'Root Cause',
        viewLabel: 'Actions & Outcomes',
      },
      {
        id: 'overdue',
        label: 'Review target overdue',
        count: queue?.overdueActive ?? 0,
        description: 'Active records beyond their configured review target.',
        pageLabel: 'Root Cause',
        viewLabel: 'Actions & Outcomes',
        urgent: true,
      },
      {
        id: 'worsening',
        label: 'Worsening observations',
        count: worsening,
        description: 'Post-execution observations currently classified as worsening.',
        pageLabel: 'Root Cause',
        viewLabel: 'Actions & Outcomes',
        urgent: true,
      },
      {
        id: 'attention',
        label: 'Fleet attention required',
        count: command?.attentionRequired ?? 0,
        description: 'Vehicles currently represented in the operational attention set.',
        pageLabel: 'Root Cause',
        viewLabel: 'Overview',
      },
    ],
    [command, queue, worsening],
  );

  const totalActionable = workItems
    .slice(0, 5)
    .reduce((sum, item) => sum + item.count, 0);

  return (
    <>
      <button
        type="button"
        className="fmWorkInboxLauncher"
        onClick={() => setOpen(true)}
        aria-haspopup="dialog"
        aria-label={`Open My Work. ${totalActionable} actionable items.`}
      >
        <Inbox size={16} aria-hidden="true" />
        <span>My Work</span>
        {totalActionable > 0 && <b>{totalActionable}</b>}
      </button>

      {open && (
        <div
          className="fmWorkInboxBackdrop"
          role="presentation"
          onMouseDown={event => {
            if (event.currentTarget === event.target) setOpen(false);
          }}
        >
          <aside
            className="fmWorkInbox"
            role="dialog"
            aria-modal="true"
            aria-labelledby="fm-work-title"
          >
            <div className="fmWorkInboxHead">
              <div>
                <span>OPERATOR INBOX</span>
                <h2 id="fm-work-title">My Work</h2>
                <p>Everything that currently needs a human review or decision.</p>
              </div>
              <button
                type="button"
                onClick={() => setOpen(false)}
                aria-label="Close My Work"
              >
                <X size={18} aria-hidden="true" />
              </button>
            </div>

            <div className="fmWorkInboxSummary">
              <div>
                <strong>{totalActionable}</strong>
                <span>actionable</span>
              </div>
              <div>
                <strong>{queue?.activeRecommendations ?? 0}</strong>
                <span>active queue</span>
              </div>
              <div>
                <strong>{command?.workflow.executed ?? 0}</strong>
                <span>executed</span>
              </div>
              <button
                type="button"
                onClick={() => void refresh()}
                disabled={loading}
              >
                <RefreshCw
                  size={15}
                  className={loading ? 'spinning' : ''}
                  aria-hidden="true"
                />
                Refresh
              </button>
            </div>

            {error && (
              <div className="fmWorkInboxError">
                <AlertTriangle size={15} aria-hidden="true" />
                <div>
                  <strong>Work summary unavailable</strong>
                  <span>{error}</span>
                </div>
              </div>
            )}

            <div className="fmWorkInboxList">
              {workItems.map(item => (
                <button
                  key={item.id}
                  type="button"
                  className={item.urgent && item.count > 0 ? 'urgent' : ''}
                  onClick={() => {
                    navigate(item);
                    setOpen(false);
                  }}
                >
                  <span className="fmWorkInboxIcon" aria-hidden="true">
                    {item.id === 'approvals' ? (
                      <ClipboardCheck size={16} />
                    ) : item.id === 'ready' ? (
                      <CheckCircle2 size={16} />
                    ) : item.id === 'overdue' ? (
                      <Clock3 size={16} />
                    ) : item.id === 'worsening' ? (
                      <AlertTriangle size={16} />
                    ) : (
                      <Inbox size={16} />
                    )}
                  </span>
                  <span className="fmWorkInboxText">
                    <span>
                      <strong>{item.label}</strong>
                      <b>{item.count}</b>
                    </span>
                    <p>{item.description}</p>
                  </span>
                  <ArrowRight size={16} aria-hidden="true" />
                </button>
              ))}
            </div>

            <div className="fmWorkInboxBoundary">
              <ShieldCheck size={15} aria-hidden="true" />
              <p>
                My Work prioritizes operator review. It does not bypass acknowledgment,
                approval or explicit execution controls.
              </p>
            </div>
          </aside>
        </div>
      )}
    </>
  );
}
