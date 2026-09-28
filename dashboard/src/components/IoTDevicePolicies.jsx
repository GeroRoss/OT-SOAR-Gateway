/** Manages reusable IoT device behaviour/orchestration policies for Infrastructure. */

import { useCallback, useEffect, useState } from "react";
import { readable } from "../utils/formatters";
import {
  createIoTDevicePolicy,
  deleteIoTDevicePolicy,
  getIoTDevicePolicies,
  updateIoTDevicePolicy,
} from "../api/gateway";
import Modal from "./Modal";
import Notice from "./Notice";
import { SortHead, useTableSort } from "./TableSort";

const blankIoTPolicy = {
  name: "",
  enabled: true,
  trigger_device_type: "environmental_sensor",
  trigger_attribute: "temperature",
  operator: "greater_than_or_equal",
  threshold: 40,
  required_source_state: "normal",
  target_device_type: "hvac",
  target_scope: "same_room",
  action: "set_cooling",
  action_value: 100,
  fallback_value: 35,
  priority: 5,
};

const sourceAttributes = {
  environmental_sensor: ["temperature", "humidity"],
  smoke_sensor: ["smoke_level"],
  pdu: ["voltage", "current", "power", "power_on"],
};

const targetActions = {
  hvac: ["set_cooling"],
  pdu: ["set_power"],
  biometric_door: ["set_locked"],
};

const conditionOperators = [
  "greater_than",
  "greater_than_or_equal",
  "less_than",
  "less_than_or_equal",
  "equal",
];

const sourceSecurityStates = ["normal", "suspicious"];
const targetScopes = ["same_room", "whole_facility"];

function comparatorLabel(value) {
  return (
    {
      greater_than: ">",
      greater_than_or_equal: "≥",
      less_than: "<",
      less_than_or_equal: "≤",
      equal: "=",
    }[value] || value
  );
}

function priorityText(policy) {
  if (policy.action === "set_cooling") return "Max demand";
  return String(policy.priority);
}

function actionValueText(policy, field = "action_value") {
  const value = policy[field];
  if (value === null || value === undefined || value === "") return "No fallback";
  if (policy.action === "set_cooling") return `${value}%`;
  if (policy.action === "set_power") return Number(value) === 1 ? "On" : "Off";
  if (policy.action === "set_locked")
    return Number(value) === 1 ? "Locked" : "Unlocked";
  return String(value);
}

function ActionValueInput({ label, action, value, allowEmpty = false, onChange }) {
  if (action === "set_cooling") {
    return (
      <label>
        {label}
        <input
          type="number"
          min="0"
          max="100"
          value={value ?? ""}
          placeholder={allowEmpty ? "No fallback" : undefined}
          onChange={(e) =>
            onChange(e.target.value === "" ? "" : Number(e.target.value))
          }
          required={!allowEmpty}
        />
      </label>
    );
  }

  return (
    <label>
      {label}
      <select
        value={value ?? ""}
        onChange={(e) => onChange(e.target.value === "" ? "" : Number(e.target.value))}
      >
        {allowEmpty && <option value="">No fallback</option>}
        <option value={1}>{action === "set_power" ? "On" : "Locked"}</option>
        <option value={0}>{action === "set_power" ? "Off" : "Unlocked"}</option>
      </select>
    </label>
  );
}

export default function IoTDevicePolicies({ currentPerson }) {
  const [iotPolicies, setIoTPolicies] = useState([]);
  const [iotForm, setIoTForm] = useState(blankIoTPolicy);
  const [modal, setModal] = useState(null);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    try {
      setIoTPolicies(await getIoTDevicePolicies());
      setError("");
    } catch (e) {
      setError(e.message);
    }
  }, []);

  useEffect(() => {
    load();
    const timer = setInterval(load, 5000);
    return () => clearInterval(timer);
  }, [load]);

  function openIoTAdd() {
    setIoTForm({ ...blankIoTPolicy });
    setModal({ type: "iot-add" });
    setMessage("");
  }

  function openIoTEdit(policy) {
    setIoTForm({ ...policy });
    setModal({ type: "iot-edit" });
    setMessage("");
  }

  async function saveIoT(event) {
    event.preventDefault();
    const payload = {
      ...iotForm,
      threshold: Number(iotForm.threshold),
      action_value: Number(iotForm.action_value),
      fallback_value:
        iotForm.fallback_value === "" || iotForm.fallback_value === null
          ? null
          : Number(iotForm.fallback_value),
      priority: Number(iotForm.priority),
    };

    try {
      if (modal.type === "iot-edit")
        await updateIoTDevicePolicy(payload, currentPerson?.person_id);
      else await createIoTDevicePolicy(payload, currentPerson?.person_id);
      setMessage(
        modal.type === "iot-edit"
          ? "IoT device policy updated."
          : "IoT device policy created.",
      );
      setModal(null);
      setError("");
      await load();
    } catch (e) {
      setError(e.message);
    }
  }

  async function removeIoT(policy) {
    if (!window.confirm(`Delete IoT device policy ${policy.name}?`)) return;
    try {
      await deleteIoTDevicePolicy(policy.policy_id, currentPerson?.person_id);
      setMessage(`${policy.policy_id} deleted.`);
      setError("");
      await load();
    } catch (e) {
      setError(e.message);
    }
  }

  async function toggleIoT(policy) {
    try {
      await updateIoTDevicePolicy(
        { ...policy, enabled: !policy.enabled },
        currentPerson?.person_id,
      );
      setMessage(`${policy.policy_id} ${policy.enabled ? "disabled" : "enabled"}.`);
      setError("");
      await load();
    } catch (e) {
      setError(e.message);
    }
  }

  function setIoTSourceType(deviceType) {
    setIoTForm((current) => ({
      ...current,
      trigger_device_type: deviceType,
      trigger_attribute: sourceAttributes[deviceType][0],
    }));
  }

  function setIoTTargetType(deviceType) {
    const action = targetActions[deviceType][0];
    setIoTForm((current) => ({
      ...current,
      target_device_type: deviceType,
      action,
      action_value: action === "set_cooling" ? 100 : 1,
      fallback_value: action === "set_cooling" ? 35 : null,
    }));
  }

  const {
    sortedRows: sortedIoTPolicies,
    sort: iotSort,
    requestSort: requestIoTSort,
  } = useTableSort(iotPolicies, {
    defaultKey: "policy_id",
    valueGetters: {
      policy: (policy) => `${policy.name} ${policy.policy_id}`,
      trigger: (policy) =>
        `${readable(policy.trigger_device_type)} ${readable(policy.trigger_attribute)} ${comparatorLabel(policy.operator)} ${policy.threshold} ${readable(policy.required_source_state)}`,
      target: (policy) =>
        `${readable(policy.target_device_type)} ${readable(policy.target_scope)}`,
      action: (policy) => `${readable(policy.action)} ${actionValueText(policy)}`,
      status: (policy) => (policy.enabled ? "Enabled" : "Disabled"),
    },
    numericKeys: ["priority"],
    rankings: {
      status: { enabled: 0, disabled: 1 },
    },
  });

  return (
    <>
      <article className="panel">
        <div className="panel-heading">
          <div>
            <h2>IoT Device Policies</h2>
            <p className="muted">
              Policies can match source telemetry by security state, resolve actuators
              in the same room or across the whole facility, and derive desired actuator
              state.
            </p>
          </div>
          <button type="button" onClick={openIoTAdd}>
            Add policy
          </button>
        </div>
        {error && <Notice notice={{ type: "error", text: error }} />}
        {message && <Notice notice={{ type: "success", text: message }} />}
        {iotPolicies.length === 0 ? (
          <p className="muted">
            No IoT device policies are configured. Sensors will report telemetry, but
            the gateway will not automatically control actuators.
          </p>
        ) : (
          <table>
            <thead>
              <tr>
                <th>
                  <SortHead field="policy" sort={iotSort} onSort={requestIoTSort}>
                    Policy
                  </SortHead>
                </th>
                <th>
                  <SortHead field="trigger" sort={iotSort} onSort={requestIoTSort}>
                    Trigger
                  </SortHead>
                </th>
                <th>
                  <SortHead field="target" sort={iotSort} onSort={requestIoTSort}>
                    Target
                  </SortHead>
                </th>
                <th>
                  <SortHead field="action" sort={iotSort} onSort={requestIoTSort}>
                    Action
                  </SortHead>
                </th>
                <th>
                  <SortHead field="priority" sort={iotSort} onSort={requestIoTSort}>
                    Priority
                  </SortHead>
                </th>
                <th>
                  <SortHead field="status" sort={iotSort} onSort={requestIoTSort}>
                    Status
                  </SortHead>
                </th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {sortedIoTPolicies.map((policy) => (
                <tr key={policy.policy_id}>
                  <td>
                    {policy.name}
                    <small>{policy.policy_id}</small>
                  </td>
                  <td>
                    {readable(policy.trigger_device_type)}
                    <small>
                      {readable(policy.trigger_attribute)}{" "}
                      {comparatorLabel(policy.operator)} {policy.threshold}; source must
                      be {readable(policy.required_source_state)}
                    </small>
                  </td>
                  <td>
                    {readable(policy.target_device_type)}
                    <small>{readable(policy.target_scope)}</small>
                  </td>
                  <td>
                    {readable(policy.action)} → {actionValueText(policy)}
                    <small>fallback: {actionValueText(policy, "fallback_value")}</small>
                  </td>
                  <td>{priorityText(policy)}</td>
                  <td>
                    <button
                      type="button"
                      className={`status-button ${
                        policy.enabled ? "status-enabled" : "status-disabled"
                      }`}
                      onClick={() => toggleIoT(policy)}
                    >
                      {policy.enabled ? "Enabled" : "Disabled"}
                    </button>
                  </td>
                  <td>
                    <div className="table-actions">
                      <button type="button" onClick={() => openIoTEdit(policy)}>
                        Edit
                      </button>
                      <button
                        type="button"
                        className="danger-button"
                        onClick={() => removeIoT(policy)}
                      >
                        Delete
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </article>

      {modal?.type?.startsWith("iot-") && (
        <Modal
          wide
          title={
            modal.type === "iot-edit"
              ? `Edit IoT policy — ${iotForm.policy_id}`
              : "Add IoT device policy"
          }
          onClose={() => setModal(null)}
        >
          <form className="policy-form" onSubmit={saveIoT}>
            <label>
              Name
              <input
                required
                value={iotForm.name}
                onChange={(e) => setIoTForm({ ...iotForm, name: e.target.value })}
              />
            </label>
            <label>
              Source device type
              <select
                value={iotForm.trigger_device_type}
                onChange={(e) => setIoTSourceType(e.target.value)}
              >
                <option value="environmental_sensor">Environmental sensor</option>
                <option value="smoke_sensor">Smoke sensor</option>
                <option value="pdu">PDU</option>
              </select>
            </label>
            <label>
              Telemetry attribute
              <select
                value={iotForm.trigger_attribute}
                onChange={(e) =>
                  setIoTForm({ ...iotForm, trigger_attribute: e.target.value })
                }
              >
                {sourceAttributes[iotForm.trigger_device_type].map((attribute) => (
                  <option key={attribute} value={attribute}>
                    {readable(attribute)}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Condition
              <select
                value={iotForm.operator}
                onChange={(e) => setIoTForm({ ...iotForm, operator: e.target.value })}
              >
                {conditionOperators.map((operator) => (
                  <option key={operator} value={operator}>
                    {comparatorLabel(operator)} ({readable(operator)})
                  </option>
                ))}
              </select>
            </label>
            <label>
              Threshold
              <input
                type="number"
                step="0.1"
                value={iotForm.threshold}
                onChange={(e) => setIoTForm({ ...iotForm, threshold: e.target.value })}
              />
            </label>
            <label>
              Required source state
              <select
                value={iotForm.required_source_state}
                onChange={(e) =>
                  setIoTForm({
                    ...iotForm,
                    required_source_state: e.target.value,
                  })
                }
              >
                {sourceSecurityStates.map((state) => (
                  <option key={state} value={state}>
                    {readable(state)}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Target device type
              <select
                value={iotForm.target_device_type}
                onChange={(e) => setIoTTargetType(e.target.value)}
              >
                <option value="hvac">HVAC</option>
                <option value="pdu">PDU</option>
                <option value="biometric_door">Biometric door</option>
              </select>
            </label>
            <label>
              Target relationship
              <select
                value={iotForm.target_scope}
                onChange={(e) =>
                  setIoTForm({ ...iotForm, target_scope: e.target.value })
                }
              >
                {targetScopes.map((scope) => (
                  <option key={scope} value={scope}>
                    {readable(scope)}
                  </option>
                ))}
              </select>
            </label>
            {iotForm.action === "set_cooling" ? (
              <label>
                Conflict resolution
                <input disabled value="Highest cooling demand wins" />
              </label>
            ) : (
              <label>
                Priority
                <input
                  type="number"
                  min="1"
                  max="9"
                  value={iotForm.priority}
                  onChange={(e) => setIoTForm({ ...iotForm, priority: e.target.value })}
                />
                <small>
                  Use 1–9 (9 is highest). Priority must be unique for this actuator
                  action, and whole-facility rules must outrank same-room rules.
                </small>
              </label>
            )}
            <label>
              Action
              <select value={iotForm.action} disabled>
                {targetActions[iotForm.target_device_type].map((action) => (
                  <option key={action} value={action}>
                    {readable(action)}
                  </option>
                ))}
              </select>
            </label>
            <ActionValueInput
              label="When condition matches"
              action={iotForm.action}
              value={iotForm.action_value}
              onChange={(value) => setIoTForm({ ...iotForm, action_value: value })}
            />
            <ActionValueInput
              label="When condition does not match"
              action={iotForm.action}
              value={iotForm.fallback_value}
              allowEmpty
              onChange={(value) => setIoTForm({ ...iotForm, fallback_value: value })}
            />
            <label className="checkbox-label">
              <input
                type="checkbox"
                checked={iotForm.enabled}
                onChange={(e) => setIoTForm({ ...iotForm, enabled: e.target.checked })}
              />
              Enabled
            </label>
            <p className="muted">
              Same-room scope resolves targets beside the source; whole-facility scope
              resolves every NORMAL actuator of the selected type.
            </p>
            <div className="modal-actions">
              <button type="button" onClick={() => setModal(null)}>
                Cancel
              </button>
              <button type="submit" className="primary-button">
                Save IoT policy
              </button>
            </div>
          </form>
        </Modal>
      )}
    </>
  );
}
