import { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';

import { FleetMindDemoBanner } from './FleetMindPublicDemo';

export function FleetMindDemoBannerPortal() {
  const [host, setHost] = useState<HTMLElement | null>(null);

  useEffect(() => {
    let mountedHost: HTMLElement | null = null;

    const mount = () => {
      const main = document.querySelector<HTMLElement>('main[data-dashboard-page]');
      const tabs = main?.querySelector<HTMLElement>('.dashboardPageTabs');
      if (!main || !tabs) return false;

      const existing = main.querySelector<HTMLElement>('[data-fm-demo-banner-host]');
      if (existing) {
        mountedHost = existing;
        setHost(existing);
        return true;
      }

      const nextHost = document.createElement('div');
      nextHost.dataset.fmDemoBannerHost = 'true';
      tabs.before(nextHost);
      mountedHost = nextHost;
      setHost(nextHost);
      return true;
    };

    if (mount()) {
      return () => {
        mountedHost?.remove();
      };
    }

    const observer = new MutationObserver(() => {
      if (mount()) observer.disconnect();
    });
    observer.observe(document.body, { childList: true, subtree: true });

    return () => {
      observer.disconnect();
      mountedHost?.remove();
    };
  }, []);

  return host ? createPortal(<FleetMindDemoBanner />, host) : null;
}
