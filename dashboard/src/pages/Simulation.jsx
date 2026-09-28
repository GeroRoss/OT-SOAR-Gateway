/** Provides development-only controls for benign physical and access simulation. */

import { useEffect, useState } from "react";
import {
  getDevices,
  getPersonnel,
  getSimulationEnvironments,
  requestDoorAccess,
  resetDemoData,
  updateSimulationEnvironment,
} from "../api/gateway";
import { roleLabel } from "../utils/formatters";

const presets = {
  normal: {
    temperature: 24,
    humidity: 45,
    smoke_level: 0,
    power_available: true,
  },
  overheat: {
    temperature: 42,
    humidity: 45,
    smoke_level: 0,
    power_available: true,
  },
  high_humidity: {
    temperature: 24,
    humidity: 85,
    smoke_level: 0,
    power_available: true,
  },
  smoke: {
    temperature: 30,
    humidity: 45,
    smoke_level: 65,
    power_available: true,
  },
  power_loss: {
    temperature: 30,
    humidity: 45,
    smoke_level: 0,
    power_available: false,
  },
};

function floorToOneDecimal(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return value;
  return Math.floor(number * 10) / 10;
}

export default function Simulation({ onDemoReset }) {
  const [environments, setEnvironments] = useState([]);
  const [people, setPeople] = useState([]);
  const [doors, setDoors] = useState([]);
  const [roomId, setRoomId] = useState("");
  const [form, setForm] = useState(presets.normal);
  const [accessPerson, setAccessPerson] = useState("");
  const [accessDoor, setAccessDoor] = useState("");

  const [environmentMessage, setEnvironmentMessage] = useState("");
  const [environmentError, setEnvironmentError] = useState("");
  const [presetMessage, setPresetMessage] = useState("");
  const [loadedPreset, setLoadedPreset] = useState("normal");
  const [accessMessage, setAccessMessage] = useState("");
  const [accessError, setAccessError] = useState("");
  const [resetMessage, setResetMessage] = useState("");
  const [resetError, setResetError] = useState("");

  async function load(preferredRoom = roomId) {
    try {
      const [environmentData, personnelData, deviceData] = await Promise.all([
        getSimulationEnvironments(),
        getPersonnel(),
        getDevices(),
      ]);
      const doorData = deviceData.filter(
        (device) => device.device_type === "biometric_door",
      );

      setEnvironments(environmentData);
      setPeople(personnelData);
      setDoors(doorData);

      const selected =
        environmentData.find((environment) => environment.room_id === preferredRoom) ||
        environmentData[0];
      if (selected) select(selected);

      setAccessPerson((current) => current || personnelData[0]?.person_id || "");
      setAccessDoor((current) => current || doorData[0]?.device_id || "");
      setEnvironmentError("");
    } catch (requestError) {
      setEnvironmentError(requestError.message);
    }
  }

  useEffect(() => {
    load();
  }, []);

  function select(environment) {
    setRoomId(environment.room_id);
    setForm({
      temperature: floorToOneDecimal(environment.temperature),
      humidity: floorToOneDecimal(environment.humidity),
      smoke_level: floorToOneDecimal(environment.smoke_level),
      power_available: environment.power_available,
    });
  }

  function applyPreset(name) {
    setForm({ ...presets[name] });
    setLoadedPreset(name);
    setPresetMessage(
      `Loaded ${name.replaceAll("_", " ")} preset. Press Apply to change the simulator.`,
    );
  }

  async function apply(event) {
    event.preventDefault();
    if (!roomId) return;
    setEnvironmentMessage("");
    setEnvironmentError("");
    try {
      await updateSimulationEnvironment(roomId, {
        temperature: floorToOneDecimal(form.temperature),
        humidity: floorToOneDecimal(form.humidity),
        smoke_level: floorToOneDecimal(form.smoke_level),
        power_available: form.power_available,
      });
      setEnvironmentMessage(`Physical environment updated for ${roomId}.`);

      await load(roomId);
    } catch (requestError) {
      setEnvironmentError(requestError.message);
    }
  }

  async function requestAccess() {
    setAccessMessage("");
    setAccessError("");
    try {
      const result = await requestDoorAccess(accessDoor, accessPerson);
      setAccessMessage(
        result?.status === "access_granted"
          ? `Access granted for ${result.person_name || accessPerson} at ${accessDoor}.`
          : `Door access request completed for ${accessPerson}.`,
      );
    } catch (requestError) {
      setAccessError(requestError.message);
    }
  }

  async function resetToSeededState() {
    const confirmed = window.confirm(
      "Reset all demo data? This deletes telemetry, events, responses, custom rooms/devices, personnel, ABAC policies, and IoT policies, then restores predefined seed data.",
    );
    if (!confirmed) return;

    setResetMessage("");
    setResetError("");
    try {
      const result = await resetDemoData();
      await onDemoReset?.();
      setResetMessage(result.message || "Demo data reset to seeded state.");
      setRoomId("");
      setAccessPerson("");
      setAccessDoor("");
      await load("room-001");
    } catch (requestError) {
      setResetError(requestError.message);
    }
  }

  const selectedEnvironment = environments.find(
    (environment) => environment.room_id === roomId,
  );

  return (
    <section>
      <h1>Simulation</h1>
      <p className="dev-warning">
        Development-only facility controls. Environmental conditions and physical access
        attempts are simulated here so gateway policy behaviour can be evaluated without
        physical hardware.
      </p>

      <article className="panel">
        <h2>Room Environment</h2>
        <div className="room-selector">
          {environments.map((environment) => (
            <button
              type="button"
              className={environment.room_id === roomId ? "selected-button" : ""}
              key={environment.room_id}
              onClick={() => select(environment)}
            >
              {environment.room_id}
            </button>
          ))}
        </div>
        {selectedEnvironment && (
          <div className="config-grid simulation-status">
            <span>
              <b>Temperature</b>
              <strong>{selectedEnvironment.temperature.toFixed(1)} °C</strong>
            </span>
            <span>
              <b>Humidity</b>
              <strong>{selectedEnvironment.humidity.toFixed(1)} %</strong>
            </span>
            <span>
              <b>Smoke</b>
              <strong>{selectedEnvironment.smoke_level.toFixed(1)}</strong>
            </span>
            <span>
              <b>Power</b>
              <strong>
                {selectedEnvironment.power_available ? "Available" : "Unavailable"}
              </strong>
            </span>
            <span>
              <b>Cooling</b>
              <strong>{selectedEnvironment.cooling_level ?? 0} %</strong>
            </span>
          </div>
        )}
      </article>

      {environmentError && <p className="error-banner">{environmentError}</p>}
      {environmentMessage && <p className="success-banner">{environmentMessage}</p>}
      {presetMessage && <p className="success-banner">{presetMessage}</p>}
      <article className="panel">
        <h2>Set Physical Conditions</h2>
        <p className="muted">Environmental presets</p>
        <div className="preset-grid">
          <button
            type="button"
            className={loadedPreset === "normal" ? "preset-active" : ""}
            onClick={() => applyPreset("normal")}
          >
            Normal
          </button>

          <button
            type="button"
            className={loadedPreset === "overheat" ? "preset-active" : ""}
            onClick={() => applyPreset("overheat")}
          >
            Overheat
          </button>

          <button
            type="button"
            className={loadedPreset === "high_humidity" ? "preset-active" : ""}
            onClick={() => applyPreset("high_humidity")}
          >
            High humidity
          </button>

          <button
            type="button"
            className={loadedPreset === "smoke" ? "preset-active" : ""}
            onClick={() => applyPreset("smoke")}
          >
            Smoke incident
          </button>

          <button
            type="button"
            className={loadedPreset === "power_loss" ? "preset-active" : ""}
            onClick={() => applyPreset("power_loss")}
          >
            Power loss
          </button>
        </div>
        <form className="simulation-form" onSubmit={apply}>
          <label>
            Temperature °C
            <input
              type="number"
              min="-20"
              max="100"
              step="1"
              value={form.temperature}
              onChange={(e) => {
                setLoadedPreset(null);
                setForm({ ...form, temperature: e.target.value });
              }}
            />
          </label>
          <label>
            Humidity %
            <input
              type="number"
              min="0"
              max="100"
              step="1"
              value={form.humidity}
              onChange={(e) => {
                setLoadedPreset(null);
                setForm({ ...form, humidity: e.target.value });
              }}
            />
          </label>
          <label>
            Smoke level
            <input
              type="number"
              min="0"
              max="100"
              step="1"
              value={form.smoke_level}
              onChange={(e) => {
                setLoadedPreset(null);
                setForm({ ...form, smoke_level: e.target.value });
              }}
            />
          </label>
          <label className="checkbox-label">
            <input
              type="checkbox"
              checked={form.power_available}
              onChange={(e) => {
                setLoadedPreset(null);
                setForm({ ...form, power_available: e.target.checked });
              }}
            />
            Power available
          </label>
          <button type="submit" disabled={!roomId}>
            Apply to {roomId || "room"}
          </button>
        </form>
      </article>

      {accessError && <p className="error-banner">{accessError}</p>}
      {accessMessage && <p className="success-banner">{accessMessage}</p>}
      <article className="panel">
        <h2>Door Access Simulation</h2>
        <p className="muted">
          Simulates an external biometric system successfully identifying a registered
          person. The gateway receives that personnel ID and evaluates active status,
          room authorization and ABAC policy before deciding whether the selected door
          may unlock.
        </p>
        <div className="inline-form">
          <label>
            Identified Personnel
            <select
              value={accessPerson}
              onChange={(e) => setAccessPerson(e.target.value)}
            >
              {people.map((personnel) => (
                <option key={personnel.person_id} value={personnel.person_id}>
                  {personnel.name} — {roleLabel(personnel.role)} ({personnel.person_id})
                </option>
              ))}
            </select>
          </label>
          <label>
            Door
            <select value={accessDoor} onChange={(e) => setAccessDoor(e.target.value)}>
              {doors.map((door) => (
                <option key={door.device_id} value={door.device_id}>
                  {door.name} ({door.device_id})
                </option>
              ))}
            </select>
          </label>
          <button
            type="button"
            disabled={!accessPerson || !accessDoor}
            onClick={requestAccess}
          >
            Request Access
          </button>
        </div>
      </article>

      {resetError && <p className="error-banner">{resetError}</p>}
      {resetMessage && <p className="success-banner">{resetMessage}</p>}
      <article className="panel">
        <h2>Reset Demo Data</h2>
        <p className="muted">
          Development-only reset for repeatable testing. This removes accumulated
          telemetry, security/response/activity history, custom registry records,
          personnel and policy changes, then restores the predefined seeded state.
        </p>
        <button type="button" onClick={resetToSeededState}>
          Reset to seeded state
        </button>
      </article>
    </section>
  );
}
