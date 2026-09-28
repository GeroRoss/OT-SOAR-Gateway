/** Provides detector status, abnormal-device controls, ABAC policy management, and security events. */

import { useEffect, useState } from "react";
import { humanize } from "../utils/formatters";
import ABACPolicies from "../components/ABACPolicies";
import EventTable from "../components/EventTable";
import {
  getDevices,
  getEvents,
  getSecurityConfig,
  resetSecurityState,
} from "../api/gateway";

const DETECTOR_FIELDS = [
  ["window_seconds", "Window", "s"],
  ["suspicious_message_threshold", "Suspicious Messages", ""],
  ["quarantine_message_threshold", "Quarantine Messages", ""],
  ["suspicious_violation_threshold", "Suspicious Violations", ""],
  ["quarantine_violation_threshold", "Quarantine Violations", ""],
  ["recovery_seconds", "Recovery", "s"],
];

export default function Security({ currentPerson }) {
  const [devices, setDevices] = useState([]);
  const [events, setEvents] = useState([]);
  const [config, setConfig] = useState({});

  async function load() {
    const [deviceData, eventData, configData] = await Promise.all([
      getDevices(),
      getEvents({ types: ["Security", "Mitigation"], limit: 200 }),
      getSecurityConfig(),
    ]);

    setDevices(deviceData);
    setEvents(eventData);
    setConfig(configData);
  }

  useEffect(() => {
    load();
  }, []);

  async function reset(id) {
    await resetSecurityState(id, currentPerson?.person_id);
    await load();
  }

  const abnormalDevices = devices.filter(
    (device) => device.security_state !== "normal",
  );

  return (
    <section>
      <h1>Security</h1>

      <div className="two-column">
        <article className="panel">
          <h2>Detector Configuration</h2>
          <div className="config-grid">
            {DETECTOR_FIELDS.map(([key, label, suffix]) => (
              <span key={key}>
                <small>{label}</small>
                <strong>
                  {config[key] ?? "—"}
                  {config[key] !== undefined && suffix ? ` ${suffix}` : ""}
                </strong>
              </span>
            ))}
          </div>
        </article>

        <article className="panel">
          <h2>Suspicious / Quarantined</h2>
          {abnormalDevices.length === 0 ? (
            <p className="muted">No devices currently require attention.</p>
          ) : (
            abnormalDevices.map((device) => (
              <div key={device.device_id} className="row-action">
                <span>
                  {device.device_id} — {humanize(device.security_state)}
                </span>
                <button type="button" onClick={() => reset(device.device_id)}>
                  Reset to Normal
                </button>
              </div>
            ))
          )}
        </article>
      </div>

      <ABACPolicies currentPerson={currentPerson} />

      <article className="panel">
        <h2>Security Events</h2>
        <EventTable events={events} />
      </article>
    </section>
  );
}
