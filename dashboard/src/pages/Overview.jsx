/** Displays gateway health, 30-minute environmental trends, sortable device state, and audit activity. */

import { Fragment, useCallback, useEffect, useMemo, useState } from "react";
import { readable } from "../utils/formatters";
import {
  getEvents,
  getDevices,
  getDeviceOperationalState,
  getDeviceSecurityStatus,
  getHealth,
  getLatestTelemetry,
  getRooms,
  getTelemetryHistory,
} from "../api/gateway";
import { SortHead, useTableSort } from "../components/TableSort";
import EventTable from "../components/EventTable";

function LiveChart({ title, unit, data, field }) {
  const rows = data.filter((row) => Number.isFinite(Number(row[field])));
  const values = rows.map((row) => Number(row[field]));
  if (values.length < 2) {
    return (
      <div className="live-chart empty-chart">
        <strong>{title}</strong>
        <span className="muted">Waiting for telemetry…</span>
      </div>
    );
  }

  const width = 720;
  const height = 220;
  const left = 46;
  const right = 14;
  const top = 18;
  const bottom = 42;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const spread = Math.max(max - min, field === "temperature" ? 2 : 5);
  const yMin = min - spread * 0.15;
  const yMax = max + spread * 0.15;

  const points = rows
    .map((row, index) => {
      const value = Number(row[field]);
      const x = left + (index / Math.max(1, rows.length - 1)) * (width - left - right);
      const y = top + ((yMax - value) / (yMax - yMin)) * (height - top - bottom);
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");

  const tickFractions = [0, 0.25, 0.5, 0.75, 1];
  const timeTicks = tickFractions.map((fraction) => {
    const index = Math.min(rows.length - 1, Math.round(fraction * (rows.length - 1)));
    return {
      x: left + fraction * (width - left - right),
      label: new Date(rows[index].timestamp).toLocaleTimeString([], {
        hour: "2-digit",
        minute: "2-digit",
      }),
    };
  });

  return (
    <div className="live-chart">
      <div className="chart-heading">
        <strong>{title}</strong>
        <span>
          {values.at(-1).toFixed(1)} {unit}
        </span>
      </div>
      <svg
        viewBox={`0 0 ${width} ${height}`}
        role="img"
        aria-label={`${title} over the last 30 minutes`}
      >
        <line
          x1={left}
          y1={top}
          x2={left}
          y2={height - bottom}
          className="chart-axis"
        />
        <line
          x1={left}
          y1={height - bottom}
          x2={width - right}
          y2={height - bottom}
          className="chart-axis"
        />
        <polyline points={points} className="chart-line" />
        <text x="4" y={top + 5} className="chart-label">
          {yMax.toFixed(1)}
        </text>
        <text x="4" y={height - bottom} className="chart-label">
          {yMin.toFixed(1)}
        </text>
        {timeTicks.map((tick, index) => (
          <g key={`${tick.label}-${index}`}>
            <line
              x1={tick.x}
              y1={height - bottom}
              x2={tick.x}
              y2={height - bottom + 5}
              className="chart-axis"
            />
            <text
              x={tick.x}
              y={height - 13}
              textAnchor={
                index === 0
                  ? "start"
                  : index === timeTicks.length - 1
                    ? "end"
                    : "middle"
              }
              className="chart-label"
            >
              {tick.label}
            </text>
          </g>
        ))}
      </svg>
    </div>
  );
}

function DeviceStateDetails({ device, telemetry, operational }) {
  if (device.device_type === "hvac") {
    const environment = operational?.environment || {};
    return (
      <div className="detail-grid">
        <span>
          <b>HVAC output</b>
          <br />
          {environment.cooling_level ?? "—"}%
        </span>
        <span>
          <b>Room temperature</b>
          <br />
          {environment.temperature != null
            ? `${Number(environment.temperature).toFixed(1)} °C`
            : "—"}
        </span>
        <span>
          <b>Room humidity</b>
          <br />
          {environment.humidity != null
            ? `${Number(environment.humidity).toFixed(1)} %`
            : "—"}
        </span>
        <span>
          <b>Room smoke</b>
          <br />
          {environment.smoke_level != null
            ? Number(environment.smoke_level).toFixed(1)
            : "—"}
        </span>
      </div>
    );
  }

  if (device.device_type === "biometric_door") {
    return (
      <span>
        <b>Door state:</b>{" "}
        {operational ? (operational.locked ? "Locked" : "Unlocked") : "—"}
      </span>
    );
  }

  if (!telemetry)
    return <span className="muted">No accepted telemetry recorded yet.</span>;

  if (device.device_type === "environmental_sensor") {
    return (
      <div className="detail-grid">
        <span>
          <b>Temperature</b>
          <br />
          {telemetry.temperature} °C
        </span>
        <span>
          <b>Humidity</b>
          <br />
          {telemetry.humidity} %
        </span>
      </div>
    );
  }

  if (device.device_type === "smoke_sensor") {
    return (
      <span>
        <b>Smoke level:</b> {telemetry.smoke_level}
      </span>
    );
  }

  if (device.device_type === "pdu") {
    return (
      <div className="detail-grid">
        <span>
          <b>Voltage</b>
          <br />
          {telemetry.voltage} V
        </span>
        <span>
          <b>Current</b>
          <br />
          {telemetry.current} A
        </span>
        <span>
          <b>Power</b>
          <br />
          {telemetry.power} W
        </span>
        <span>
          <b>Power state</b>
          <br />
          {telemetry.power_on ? "On" : "Off"}
        </span>
      </div>
    );
  }

  return <span className="muted">No device state available.</span>;
}

export default function Overview() {
  const [data, setData] = useState({
    health: null,
    rooms: [],
    devices: [],
    activity: [],
  });
  const [latest, setLatest] = useState({});
  const [operational, setOperational] = useState({});
  const [selectedSensor, setSelectedSensor] = useState("");
  const [history, setHistory] = useState([]);
  const [expandedId, setExpandedId] = useState(null);
  const [detail, setDetail] = useState({
    telemetry: null,
    detector: null,
    operational: null,
  });
  const [error, setError] = useState("");
  const [detailError, setDetailError] = useState("");

  const load = useCallback(async () => {
    try {
      const [health, rooms, devices, activity] = await Promise.all([
        getHealth(),
        getRooms(),
        getDevices(),
        getEvents({ types: ["Management", "Control", "System"], limit: 60 }),
      ]);
      const telemetryPairs = await Promise.all(
        devices.map(async (device) => [
          device.device_id,
          await getLatestTelemetry(device),
        ]),
      );
      const actuatorPairs = await Promise.all(
        devices
          .filter((device) => ["hvac", "biometric_door"].includes(device.device_type))
          .map(async (device) => {
            try {
              return [
                device.device_id,
                await getDeviceOperationalState(device.device_id),
              ];
            } catch {
              return [device.device_id, null];
            }
          }),
      );
      setData({ health, rooms, devices, activity });
      setLatest(Object.fromEntries(telemetryPairs));
      setOperational(Object.fromEntries(actuatorPairs));
      const sensors = devices.filter(
        (device) => device.device_type === "environmental_sensor",
      );
      setSelectedSensor((current) =>
        sensors.some((device) => device.device_id === current)
          ? current
          : sensors[0]?.device_id || "",
      );
      setError("");
    } catch (err) {
      setError(err.message);
    }
  }, []);

  useEffect(() => {
    load();
    const timer = setInterval(load, 5000);
    return () => clearInterval(timer);
  }, [load]);

  useEffect(() => {
    if (!selectedSensor) {
      setHistory([]);
      return undefined;
    }
    let active = true;
    async function loadHistory() {
      try {
        const rows = await getTelemetryHistory(selectedSensor, 900);
        const cutoff = Date.now() - 30 * 60 * 1000;
        if (active) {
          setHistory(
            rows.filter(
              (row) =>
                row.telemetry_type === "environmental" &&
                new Date(row.timestamp).getTime() >= cutoff,
            ),
          );
        }
      } catch (err) {
        if (active) setError(err.message);
      }
    }
    loadHistory();
    const timer = setInterval(loadHistory, 2000);
    return () => {
      active = false;
      clearInterval(timer);
    };
  }, [selectedSensor]);

  const roomMap = useMemo(
    () => Object.fromEntries(data.rooms.map((room) => [room.room_id, room.name])),
    [data.rooms],
  );

  const suspicious = data.devices.filter(
    (device) => device.security_state === "suspicious",
  ).length;
  const quarantined = data.devices.filter(
    (device) => device.security_state === "quarantined",
  ).length;
  const environmentalSensors = data.devices.filter(
    (device) => device.device_type === "environmental_sensor",
  );

  const {
    sortedRows: sortedDevices,
    sort: deviceSort,
    requestSort: requestDeviceSort,
  } = useTableSort(data.devices, {
    defaultKey: "device_id",
    valueGetters: {
      device: (device) => `${device.name} ${device.device_id}`,
      type: (device) => device.device_type,
      room: (device) => `${roomMap[device.room_id] || ""} ${device.room_id}`,
      criticality: (device) => device.criticality,
      security: (device) => device.security_state,
      operational: (device) => operationalState(device),
    },
  });

  async function toggleDetails(device) {
    if (expandedId === device.device_id) {
      setExpandedId(null);
      return;
    }
    setExpandedId(device.device_id);
    setDetail({ telemetry: null, detector: null, operational: null });
    setDetailError("");
    try {
      const [telemetry, detector, operationalStateData] = await Promise.all([
        getLatestTelemetry(device),
        getDeviceSecurityStatus(device.device_id),
        ["hvac", "biometric_door"].includes(device.device_type)
          ? getDeviceOperationalState(device.device_id)
          : Promise.resolve(null),
      ]);
      setDetail({ telemetry, detector, operational: operationalStateData });
    } catch (err) {
      setDetailError(err.message);
    }
  }

  function operationalState(device) {
    const telemetry = latest[device.device_id];
    if (device.device_type === "pdu")
      return telemetry
        ? telemetry.power_on
          ? "Online / On"
          : "Offline / Off"
        : "Unknown";
    if (
      device.device_type === "environmental_sensor" ||
      device.device_type === "smoke_sensor"
    )
      return telemetry
        ? `Reporting / ${device.protocol.toUpperCase()}`
        : "No telemetry";
    if (device.device_type === "hvac") {
      const level = operational[device.device_id]?.environment?.cooling_level;
      return level != null ? `Cooling ${level}%` : "Actuator";
    }
    if (device.device_type === "biometric_door") {
      const state = operational[device.device_id];
      return state ? (state.locked ? "Locked" : "Unlocked") : "Actuator";
    }
    return "Unknown";
  }

  return (
    <section>
      <h1>Overview</h1>
      {error && <p className="error-banner">{error}</p>}
      <div className="stat-grid">
        <article className="panel stat">
          <b>Gateway</b>
          <span>{data.health?.status === "ok" ? "Online" : "Unavailable"}</span>
        </article>
        <article className="panel stat">
          <b>Rooms</b>
          <span>{data.rooms.length}</span>
        </article>
        <article className="panel stat">
          <b>Devices</b>
          <span>{data.devices.length}</span>
        </article>
        <article className="panel stat">
          <b>Suspicious</b>
          <span>{suspicious}</span>
        </article>
        <article className="panel stat">
          <b>Quarantined</b>
          <span>{quarantined}</span>
        </article>
      </div>

      <article className="panel">
        <div className="panel-heading">
          <div>
            <h2>Live Environmental Monitor</h2>
            <p className="muted">
              Accepted environmental telemetry from the last 30 minutes. The chart
              refreshes every 2 seconds.
            </p>
          </div>
          <select
            value={selectedSensor}
            onChange={(e) => setSelectedSensor(e.target.value)}
          >
            {environmentalSensors.map((device) => (
              <option key={device.device_id} value={device.device_id}>
                {device.name} — {roomMap[device.room_id] || device.room_id}
              </option>
            ))}
          </select>
        </div>
        <div className="chart-grid">
          <LiveChart title="Temperature" unit="°C" data={history} field="temperature" />
          <LiveChart title="Humidity" unit="%" data={history} field="humidity" />
        </div>
      </article>

      <article className="panel">
        <div className="panel-heading">
          <div>
            <h2>Device Monitoring</h2>
            <p className="muted">
              Click a column heading to sort. Security state and operational state
              remain separate dimensions.
            </p>
          </div>
        </div>
        <table>
          <thead>
            <tr>
              <th>
                <SortHead field="device" sort={deviceSort} onSort={requestDeviceSort}>
                  Device
                </SortHead>
              </th>
              <th>
                <SortHead field="type" sort={deviceSort} onSort={requestDeviceSort}>
                  Type
                </SortHead>
              </th>
              <th>
                <SortHead field="room" sort={deviceSort} onSort={requestDeviceSort}>
                  Room
                </SortHead>
              </th>
              <th>
                <SortHead
                  field="criticality"
                  sort={deviceSort}
                  onSort={requestDeviceSort}
                >
                  Criticality
                </SortHead>
              </th>
              <th>
                <SortHead field="security" sort={deviceSort} onSort={requestDeviceSort}>
                  Security
                </SortHead>
              </th>
              <th>
                <SortHead
                  field="operational"
                  sort={deviceSort}
                  onSort={requestDeviceSort}
                >
                  Operational
                </SortHead>
              </th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {sortedDevices.map((device) => (
              <Fragment key={device.device_id}>
                <tr>
                  <td>
                    {device.name}
                    <small>{device.device_id}</small>
                  </td>
                  <td>
                    {readable(device.device_type)}
                    <small>{device.protocol.toUpperCase()}</small>
                  </td>
                  <td>
                    {roomMap[device.room_id] || device.room_id}
                    <small>{device.room_id}</small>
                  </td>
                  <td>{readable(device.criticality)}</td>
                  <td>
                    <span className={`state-badge state-${device.security_state}`}>
                      {device.security_state}
                    </span>
                  </td>
                  <td>
                    <span
                      className={`operational-badge ${operationalState(device).includes("Off") ? "operational-off" : ""}`}
                    >
                      {operationalState(device)}
                    </span>
                  </td>
                  <td>
                    <button type="button" onClick={() => toggleDetails(device)}>
                      {expandedId === device.device_id ? "Hide" : "Expand"}
                    </button>
                  </td>
                </tr>
                {expandedId === device.device_id && (
                  <tr className="detail-row">
                    <td colSpan="7">
                      {detailError ? (
                        <p className="error-banner">{detailError}</p>
                      ) : (
                        <div className="device-detail">
                          <div>
                            <h3>Detector window</h3>
                            <div className="detail-grid">
                              <span>
                                <b>Messages</b>
                                <br />
                                {detail.detector?.message_count ?? "…"}
                              </span>
                              <span>
                                <b>Violations</b>
                                <br />
                                {detail.detector?.policy_violation_count ?? "…"}
                              </span>
                              <span>
                                <b>Security</b>
                                <br />
                                {detail.detector?.security_state ??
                                  device.security_state}
                              </span>
                            </div>
                          </div>
                          <div>
                            <h3>
                              {["hvac", "biometric_door"].includes(device.device_type)
                                ? "Device state"
                                : "Latest telemetry"}
                            </h3>
                            <DeviceStateDetails
                              device={device}
                              telemetry={detail.telemetry}
                              operational={detail.operational}
                            />
                          </div>
                          <div>
                            <h3>Latest activity</h3>
                            <span>
                              {data.activity.find(
                                (event) => event.source_id === device.device_id,
                              )?.message || "No activity recorded."}
                            </span>
                          </div>
                        </div>
                      )}
                    </td>
                  </tr>
                )}
              </Fragment>
            ))}
          </tbody>
        </table>
      </article>

      <article className="panel activity-panel">
        <h2>Recent Activity</h2>
        <EventTable events={data.activity} />
      </article>
    </section>
  );
}
