/** Dashboard navigation, simulated personnel session, and security alerts. */

import { useCallback, useEffect, useRef, useState } from "react";
import { getEvents, getPersonnel } from "./api/gateway";
import Sidebar from "./components/Sidebar";
import { roleLabel } from "./utils/formatters";
import { alertReadKey, loadReadAlerts, saveReadAlerts } from "./utils/alerts";
import Attack from "./pages/Attack";
import Infrastructure from "./pages/Infrastructure";
import Overview from "./pages/Overview";
import Personnel from "./pages/Personnel";
import Security from "./pages/Security";
import Simulation from "./pages/Simulation";

const pages = {
  overview: Overview,
  infrastructure: Infrastructure,
  personnel: Personnel,
  security: Security,
  simulation: Simulation,
  attack: Attack,
};

export default function App() {
  const [currentPage, setCurrentPage] = useState("overview");
  const [people, setPeople] = useState([]);
  const [currentPersonId, setCurrentPersonId] = useState("");
  const [accountError, setAccountError] = useState("");
  const [securityAlerts, setSecurityAlerts] = useState([]);
  const [alertsOpen, setAlertsOpen] = useState(false);
  const [readAlertKeys, setReadAlertKeys] = useState(() => loadReadAlerts());
  const alertRequest = useRef(0);

  const Page = pages[currentPage] || Overview;

  const loadAccounts = useCallback(async () => {
    try {
      const personnel = await getPersonnel();

      const activePersonnel = personnel.filter((personnel) => personnel.active);

      setPeople(activePersonnel);

      setCurrentPersonId((existing) => {
        if (
          existing &&
          activePersonnel.some((personnel) => personnel.person_id === existing)
        ) {
          return existing;
        }

        return activePersonnel[0]?.person_id || "";
      });

      setAccountError("");
    } catch (error) {
      setAccountError(error.message);
    }
  }, []);

  useEffect(() => {
    loadAccounts();
  }, [loadAccounts]);

  const loadSecurityAlerts = useCallback(async () => {
    const requestId = ++alertRequest.current;
    try {
      const events = await getEvents({
        types: ["Security", "Mitigation"],
        limit: 100,
      });
      // A response started before reset must not replace the refreshed list.
      if (requestId === alertRequest.current) setSecurityAlerts(events);
    } catch {
      // Alert polling must not make the whole dashboard unusable.
    }
  }, []);

  useEffect(() => {
    loadSecurityAlerts();
    const timer = setInterval(loadSecurityAlerts, 5000);
    return () => clearInterval(timer);
  }, [loadSecurityAlerts]);

  const unreadAlerts = securityAlerts.filter(
    (event) => !readAlertKeys.has(alertReadKey(event)),
  );

  function markAlertsRead() {
    const next = new Set(readAlertKeys);
    securityAlerts.forEach((event) => next.add(alertReadKey(event)));
    setReadAlertKeys(saveReadAlerts(next));
  }

  async function handleDemoReset() {
    alertRequest.current += 1;
    setSecurityAlerts([]);
    setAlertsOpen(false);
    setReadAlertKeys(saveReadAlerts(new Set()));
    await Promise.all([loadAccounts(), loadSecurityAlerts()]);
  }

  function toggleAlerts() {
    setAlertsOpen((open) => {
      const next = !open;
      if (next) markAlertsRead();
      return next;
    });
  }

  const currentPerson =
    people.find((personnel) => personnel.person_id === currentPersonId) || null;

  return (
    <div className="app-shell">
      <Sidebar currentPage={currentPage} onNavigate={setCurrentPage} />

      <main className="main-content">
        <header className="top-bar">
          <div className="top-bar-spacer" />

          <div className="alert-center top-bar-alert-center">
            <button
              type="button"
              className="alert-button"
              onClick={toggleAlerts}
              aria-label={`${unreadAlerts.length} unread security alerts`}
              title="Security alerts"
            >
              <span aria-hidden="true">⚠</span>
              <span>Alerts</span>
              {unreadAlerts.length > 0 && (
                <span className="alert-count">{unreadAlerts.length}</span>
              )}
            </button>

            {alertsOpen && (
              <div className="alert-popover">
                <div className="alert-popover-heading">
                  <strong>Security Alerts</strong>
                  <span className="muted">Latest security and mitigation events</span>
                </div>

                {securityAlerts.length === 0 ? (
                  <p className="muted">No security alerts recorded.</p>
                ) : (
                  securityAlerts.slice(0, 8).map((event) => (
                    <div className="alert-item" key={event.event_key}>
                      <b>{event.type}</b>
                      <span>{event.actor}</span>
                      <span>{event.action}</span>
                      {event.state && <small>{event.state}</small>}
                    </div>
                  ))
                )}
              </div>
            )}
          </div>

          <div className="account-area">
            <span className="account-label">Current Account</span>

            {people.length > 0 ? (
              <select
                className="account-select"
                value={currentPersonId}
                onChange={(event) => setCurrentPersonId(event.target.value)}
              >
                {people.map((personnel) => (
                  <option key={personnel.person_id} value={personnel.person_id}>
                    {personnel.name} — {roleLabel(personnel.role)}
                  </option>
                ))}
              </select>
            ) : (
              <span className="muted">No Active Personnel</span>
            )}

            {currentPerson && (
              <div className="account-summary">
                <strong>{currentPerson.name}</strong>
                <span>
                  {roleLabel(currentPerson.role)} · Clearance {currentPerson.clearance}
                </span>
              </div>
            )}
          </div>
        </header>

        {accountError && (
          <p className="error-banner">Account loading error: {accountError}</p>
        )}

        <Page
          currentPerson={currentPerson}
          onPersonnelChanged={loadAccounts}
          onDemoReset={handleDemoReset}
        />
      </main>
    </div>
  );
}
