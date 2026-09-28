/** Provides evaluation-oriented development attacks against simulated IoT/OT devices. */

import { useEffect, useMemo, useState } from "react";
import { readable } from "../utils/formatters";
import {
  getAttackStatus,
  getDevices,
  getSecurityConfig,
  launchAttack,
} from "../api/gateway";

const TELEMETRY_TYPES = ["environmental_sensor", "smoke_sensor", "pdu"];

const DETECTOR_FIELDS = [
  ["window_seconds", "Window", "s"],
  ["suspicious_message_threshold", "Suspicious Messages", ""],
  ["quarantine_message_threshold", "Quarantine Messages", ""],
  ["suspicious_violation_threshold", "Suspicious Violations", ""],
  ["quarantine_violation_threshold", "Quarantine Violations", ""],
  ["recovery_seconds", "Recovery", "s"],
];

const ATTACK_HELP = {
  telemetry_flood: {
    title: "Telemetry flood",
    description:
      "Normal telemetry: one message every 2 seconds (0.5 msg/s).\nInject additional traffic to the compromised device. \nExpected path: message-rate threshold reached → suspicious → quarantined → gateway-enforced discard.",
  },
  wrong_room: {
    title: "Wrong-room telemetry",
    description:
      "A registered device repeatedly claims a room other than its assigned room. Expected path: ABAC violations → suspicious → quarantined → automated response.",
  },
  slow_poisoning: {
    title: "Slow environmental telemetry poisoning",
    description:
      "A compromised environmental sensor gradually drifts its temperature reading while keeping the normal 2-second publication cadence. Same-room peer sensors provide corroboration, so disagreement—not message volume—drives suspicious → quarantined.",
  },
  unauthorized_control: {
    title: "Unauthorized actuator control / lateral movement",
    description:
      "The selected device is treated as compromised and repeatedly attempts to control another actuator through the gateway. Default-deny ABAC attributes the violations to the source device, so HVAC and door controllers can now be quarantined and exercise their safety-aware mitigation paths.",
  },
};

export default function Attack() {
  const [allDevices, setAllDevices] = useState([]);
  const [status, setStatus] = useState([]);
  const [config, setConfig] = useState({});
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [form, setForm] = useState({
    device_id: "",
    attack_type: "telemetry_flood",
    rate_per_second: 1,
    duration_seconds: 5,
  });

  const eligibleDevices = useMemo(() => {
    if (form.attack_type === "unauthorized_control") return allDevices;
    if (form.attack_type === "slow_poisoning")
      return allDevices.filter(
        (device) => device.device_type === "environmental_sensor",
      );
    return allDevices.filter((device) => TELEMETRY_TYPES.includes(device.device_type));
  }, [allDevices, form.attack_type]);

  async function load() {
    try {
      const [devices, attackStatus, configData] = await Promise.all([
        getDevices(),
        getAttackStatus(),
        getSecurityConfig(),
      ]);
      setAllDevices(devices);
      setStatus(attackStatus);
      setConfig(configData);
      setError("");
    } catch (err) {
      setError(err.message);
    }
  }

  useEffect(() => {
    load();
    const timer = setInterval(load, 2000);
    return () => clearInterval(timer);
  }, []);

  useEffect(() => {
    if (!eligibleDevices.some((device) => device.device_id === form.device_id)) {
      setForm((current) => ({
        ...current,
        device_id: eligibleDevices[0]?.device_id || "",
      }));
    }
  }, [eligibleDevices, form.device_id]);

  async function start(event) {
    event.preventDefault();
    setMessage("");
    setError("");
    try {
      await launchAttack({
        ...form,
        rate_per_second: Number(form.rate_per_second),
        duration_seconds: Number(form.duration_seconds),
      });
      setMessage(
        `Launched ${ATTACK_HELP[form.attack_type].title} from ${form.device_id}.`,
      );
      await load();
    } catch (err) {
      setError(err.message);
    }
  }

  const isViolationAttack = form.attack_type === "unauthorized_control";
  const isSlowPoisoning = form.attack_type === "slow_poisoning";
  const isTelemetryFlood = form.attack_type === "telemetry_flood";

  return (
    <section>
      <h1>Attack Simulation</h1>
      <p className="dev-warning">
        Development-only attack generator. It is experimental infrastructure used to
        exercise the gateway, not part of the proposed production gateway.
      </p>
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
      <div className="two-column">
        <div>
          {message && <p className="success-message">{message}</p>}
          {error && <p className="error-message">{error}</p>}
          <article className="panel">
            <div className="panel-heading">
              <div>
                <h2>Launch Attack</h2>
                <p className="muted">
                  Select the compromised source device and an experimental behaviour.
                </p>
              </div>
            </div>

            <form className="stack-form" onSubmit={start}>
              <label>
                Compromised source device
                <select
                  value={form.device_id}
                  onChange={(event) =>
                    setForm({ ...form, device_id: event.target.value })
                  }
                >
                  {eligibleDevices.map((device) => (
                    <option key={device.device_id} value={device.device_id}>
                      {device.name} ({device.device_id}) —{" "}
                      {readable(device.device_type)}
                    </option>
                  ))}
                </select>
              </label>

              <label>
                Attack behaviour
                <select
                  value={form.attack_type}
                  onChange={(event) =>
                    setForm({
                      ...form,
                      attack_type: event.target.value,
                      rate_per_second:
                        event.target.value === "unauthorized_control"
                          ? 4
                          : event.target.value === "slow_poisoning"
                            ? 1
                            : event.target.value === "telemetry_flood"
                              ? 1
                              : 5,
                      duration_seconds:
                        event.target.value === "unauthorized_control"
                          ? 2
                          : event.target.value === "slow_poisoning"
                            ? 16
                            : event.target.value === "telemetry_flood"
                              ? 5
                              : 1,
                    })
                  }
                >
                  <option value="telemetry_flood">Telemetry flood</option>
                  <option value="wrong_room">
                    Wrong-room telemetry policy violation
                  </option>
                  <option value="slow_poisoning">
                    Slow environmental telemetry poisoning
                  </option>
                  <option value="unauthorized_control">
                    Unauthorized actuator control / lateral movement
                  </option>
                </select>
              </label>

              <div className="info-box">
                <strong>{ATTACK_HELP[form.attack_type].title}</strong>
                <p style={{ whiteSpace: "pre-line" }}>
                  {ATTACK_HELP[form.attack_type].description}
                </p>
              </div>

              {isSlowPoisoning ? (
                <div className="info-box">
                  <strong>Cadence</strong>
                  <p>
                    Fixed at one replacement reading every 2 seconds so the attack does
                    not rely on message-rate detection.
                  </p>
                </div>
              ) : (
                <label>
                  {isViolationAttack
                    ? "Attempts / second"
                    : isTelemetryFlood
                      ? "Additional flood messages / second"
                      : "Messages / second"}
                  <input
                    type="number"
                    min="1"
                    max="100"
                    value={form.rate_per_second}
                    onChange={(event) =>
                      setForm({ ...form, rate_per_second: event.target.value })
                    }
                  />
                </label>
              )}
              <label>
                Duration seconds
                <input
                  type="number"
                  min="1"
                  max="60"
                  value={form.duration_seconds}
                  onChange={(event) =>
                    setForm({ ...form, duration_seconds: event.target.value })
                  }
                />
              </label>
              <button type="submit" className="alert-button" disabled={!form.device_id}>
                Launch attack
              </button>
            </form>
          </article>
        </div>

        <article className="panel">
          <div className="panel-heading">
            <div>
              <h2>Attack Status</h2>
              <p className="muted">
                The source is the device whose security state should change.
              </p>
            </div>
          </div>
          {status.length === 0 ? (
            <p className="muted">
              No attacks have been launched in this simulator session.
            </p>
          ) : (
            status.map((attack) => (
              <div className="row-action" key={attack.attack_id}>
                <span>
                  <b>{attack.device_id}</b>
                  <small>{readable(attack.attack_type)}</small>
                  {attack.target_device_id && (
                    <small>Attempted target: {attack.target_device_id}</small>
                  )}
                  {attack.attempts != null && (
                    <small>
                      Attempts: {attack.attempts}
                      {attack.denied_attempts != null
                        ? ` · denied: ${attack.denied_attempts}`
                        : ""}
                    </small>
                  )}
                  {attack.error && <small>{attack.error}</small>}
                </span>
                <b>{attack.status}</b>
              </div>
            ))
          )}
        </article>
      </div>
    </section>
  );
}
