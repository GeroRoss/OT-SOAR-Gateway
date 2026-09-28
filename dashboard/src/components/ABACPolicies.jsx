/** Provides the guided ABAC policy table, sorting, and add/edit policy modal. */

import { useEffect, useState } from "react";
import Modal from "./Modal";
import Notice from "./Notice";
import { SortHead, useTableSort } from "./TableSort";
import { humanize, roleLabel } from "../utils/formatters";
import { createPolicy, deletePolicy, getPolicies, updatePolicy } from "../api/gateway";

const SUBJECT_ROLES = [
  ["ot_administrator", "OT Administrator"],
  ["security_operator", "Security Operator"],
  ["facility_engineer", "Facility Engineer"],
  ["facility_operator", "Facility Operator"],
  ["technician", "Technician"],
  ["contractor", "Contractor"],
  ["visitor", "Visitor"],
];

const ALL_ROLE_VALUES = SUBJECT_ROLES.map(([value]) => value);

const DEVICE_TYPES = [
  ["environmental_sensor", "Environmental Sensor"],
  ["smoke_sensor", "Smoke / Fire Sensor"],
  ["pdu", "Smart PDU"],
  ["hvac", "HVAC Controller"],
  ["biometric_door", "Biometric Door Controller"],
];

const ACTIONS_BY_SUBJECT = {
  personnel: [
    ["control_hvac", "Control HVAC"],
    ["control_pdu", "Control PDU"],
    ["control_door", "Control / Override Door"],
    ["request_door_access", "Request Biometric Door Access"],
    ["create_room", "Create Room"],
    ["edit_room", "Edit Room"],
    ["delete_room", "Delete Room"],
    ["register_device", "Register Device"],
    ["edit_device", "Edit Device"],
    ["delete_device", "Delete Device"],
    ["create_personnel", "Create Personnel"],
    ["edit_personnel", "Edit Personnel"],
    ["create_iot_policy", "Create IoT Policy"],
    ["edit_iot_policy", "Edit IoT Policy"],
    ["delete_iot_policy", "Delete IoT Policy"],
    ["create_abac_policy", "Create ABAC Policy"],
    ["edit_abac_policy", "Edit ABAC Policy"],
    ["delete_abac_policy", "Delete ABAC Policy"],
    ["reset_security_state", "Reset Device Security State"],
  ],
  device: [
    ["publish_environmental_telemetry", "Publish Environmental Telemetry"],
    ["publish_smoke_telemetry", "Publish Smoke Telemetry"],
    ["publish_pdu_telemetry", "Publish PDU Telemetry"],
    ["control_hvac", "Control HVAC"],
    ["control_pdu", "Control PDU"],
    ["control_door", "Control Door"],
  ],
};

const ALL_ACTIONS = Object.values(ACTIONS_BY_SUBJECT).flat();

const ACTION_DEFAULTS = {
  publish_environmental_telemetry: {
    subject_device_type: "environmental_sensor",
    resource_type: "telemetry",
    resource_device_type: null,
  },
  publish_smoke_telemetry: {
    subject_device_type: "smoke_sensor",
    resource_type: "telemetry",
    resource_device_type: null,
  },
  publish_pdu_telemetry: {
    subject_device_type: "pdu",
    resource_type: "telemetry",
    resource_device_type: null,
  },
  control_hvac: {
    resource_type: "device",
    resource_device_type: "hvac",
  },
  control_pdu: {
    resource_type: "device",
    resource_device_type: "pdu",
  },
  control_door: {
    resource_type: "device",
    resource_device_type: "biometric_door",
  },
  request_door_access: {
    resource_type: "device",
    resource_device_type: "biometric_door",
  },
  create_room: {
    resource_type: "room",
    resource_device_type: null,
  },
  edit_room: {
    resource_type: "room",
    resource_device_type: null,
  },
  delete_room: {
    resource_type: "room",
    resource_device_type: null,
  },
  register_device: {
    resource_type: "device",
    resource_device_type: null,
  },
  edit_device: {
    resource_type: "device",
    resource_device_type: null,
  },
  delete_device: {
    resource_type: "device",
    resource_device_type: null,
  },
  create_personnel: {
    resource_type: "personnel",
    resource_device_type: null,
  },
  edit_personnel: {
    resource_type: "personnel",
    resource_device_type: null,
  },
  create_iot_policy: {
    resource_type: "iot_policy",
    resource_device_type: null,
  },
  edit_iot_policy: {
    resource_type: "iot_policy",
    resource_device_type: null,
  },
  delete_iot_policy: {
    resource_type: "iot_policy",
    resource_device_type: null,
  },
  create_abac_policy: {
    resource_type: "abac_policy",
    resource_device_type: null,
  },
  edit_abac_policy: {
    resource_type: "abac_policy",
    resource_device_type: null,
  },
  delete_abac_policy: {
    resource_type: "abac_policy",
    resource_device_type: null,
  },
  reset_security_state: {
    resource_type: "device",
    resource_device_type: null,
  },
};

const RESOURCE_LABELS = {
  telemetry: "Telemetry",
  room: "Room",
  device: "Device",
  personnel: "Personnel",
  iot_policy: "IoT Policy",
  abac_policy: "ABAC Policy",
};

const SUBJECT_LABELS = {
  personnel: "Personnel",
  device: "Device",
};

const blankPolicy = {
  name: "",
  effect: "allow",
  action: "control_hvac",
  subject_type: "personnel",
  resource_type: "device",
  subject_roles: [...ALL_ROLE_VALUES],
  minimum_clearance: null,
  subject_device_type: null,
  resource_device_type: "hvac",
  require_same_room: false,
  allowed_subject_security_states: null,
  allowed_resource_security_states: ["normal", "suspicious"],
  start_hour: null,
  end_hour: null,
  priority: 5,
  enabled: true,
};

function actionLabel(action) {
  return ALL_ACTIONS.find(([value]) => value === action)?.[1] || humanize(action);
}

function deviceTypeLabel(deviceType) {
  if (!deviceType) return null;
  return (
    DEVICE_TYPES.find(([value]) => value === deviceType)?.[1] || humanize(deviceType)
  );
}

function resourceTypeLabel(resourceType) {
  return RESOURCE_LABELS[resourceType] || humanize(resourceType);
}

function subjectTypeLabel(subjectType) {
  return SUBJECT_LABELS[subjectType] || humanize(subjectType);
}

function normalisePolicy(policy) {
  const legacyRole = policy.subject_role ? [policy.subject_role] : null;
  let roles = policy.subject_roles ?? legacyRole;

  if (policy.subject_type === "personnel" && (!roles || roles.length === 0)) {
    roles = [...ALL_ROLE_VALUES];
  }

  const implied = ACTION_DEFAULTS[policy.action] || {};

  return {
    ...blankPolicy,
    ...policy,
    ...implied,
    subject_roles: roles,
  };
}

function canManageABAC(personnel) {
  return Boolean(
    personnel?.active &&
    personnel.clearance >= 5 &&
    personnel.role === "ot_administrator",
  );
}

function policySubjectSummary(policy) {
  if (policy.subject_type === "device") {
    return deviceTypeLabel(policy.subject_device_type) || "Any Device Type";
  }

  const roles = policy.subject_roles || [];
  if (roles.length === ALL_ROLE_VALUES.length) return "Any Role";
  if (roles.length === 0) return "Any Role";
  return roles.map(roleLabel).join(", ");
}

function policyResourceSummary(policy) {
  const implied = ACTION_DEFAULTS[policy.action] || {};
  const resourceType = implied.resource_type ?? policy.resource_type;
  const resourceDeviceType = Object.prototype.hasOwnProperty.call(
    implied,
    "resource_device_type",
  )
    ? implied.resource_device_type
    : policy.resource_device_type;

  if (resourceType === "device") {
    return deviceTypeLabel(resourceDeviceType) || "Any Device Type";
  }
  return resourceTypeLabel(resourceType);
}

function impliedResourceSummary(action) {
  const implied = ACTION_DEFAULTS[action] || {};
  if (!implied.resource_type) return "—";

  if (implied.resource_type === "device") {
    const deviceType = deviceTypeLabel(implied.resource_device_type);
    return deviceType ? `Device — ${deviceType}` : "Device — Any Device Type";
  }

  return resourceTypeLabel(implied.resource_type);
}

export default function ABACPolicies({ currentPerson }) {
  const [policies, setPolicies] = useState([]);
  const [form, setForm] = useState(blankPolicy);
  const [modal, setModal] = useState(null);
  const [message, setMessage] = useState("");
  const [formError, setFormError] = useState("");

  async function loadPolicies() {
    const data = await getPolicies();
    setPolicies(data);
  }

  useEffect(() => {
    loadPolicies();
  }, []);

  function toggleSubjectRole(role) {
    const current = form.subject_roles || [];
    const next = current.includes(role)
      ? current.filter((item) => item !== role)
      : [...current, role];

    setForm({ ...form, subject_roles: next });
    setFormError("");
  }

  function selectAllRoles() {
    setForm({ ...form, subject_roles: [...ALL_ROLE_VALUES] });
    setFormError("");
  }

  function changeAction(action) {
    const defaults = ACTION_DEFAULTS[action] || {};
    setForm((current) => ({
      ...current,
      action,
      ...defaults,
      subject_device_type:
        current.subject_type === "device"
          ? (defaults.subject_device_type ?? current.subject_device_type)
          : null,
    }));
  }

  function changeSubjectType(subjectType) {
    const availableActions = ACTIONS_BY_SUBJECT[subjectType] || [];
    const currentActionAllowed = availableActions.some(
      ([value]) => value === form.action,
    );
    const nextAction = currentActionAllowed ? form.action : availableActions[0]?.[0];
    const defaults = ACTION_DEFAULTS[nextAction] || {};

    setForm((current) => ({
      ...current,
      subject_type: subjectType,
      action: nextAction,
      ...defaults,
      subject_roles:
        subjectType === "device"
          ? null
          : current.subject_roles?.length
            ? current.subject_roles
            : [...ALL_ROLE_VALUES],
      minimum_clearance: subjectType === "device" ? null : current.minimum_clearance,
      subject_device_type:
        subjectType === "device"
          ? (defaults.subject_device_type ?? current.subject_device_type)
          : null,
    }));
    setFormError("");
  }

  function closePolicyModal() {
    setForm(blankPolicy);
    setFormError("");
    setModal(null);
  }

  function startAdding() {
    setForm({ ...blankPolicy, subject_roles: [...ALL_ROLE_VALUES] });
    setMessage("");
    setFormError("");
    setModal({ type: "add" });
  }

  async function save(event) {
    event.preventDefault();
    setFormError("");
    setMessage("");

    if (form.subject_type === "personnel" && !form.subject_roles?.length) {
      setFormError(
        "Select at least one personnel role. Select all roles to represent Any Role.",
      );
      return;
    }

    if (form.priority < 1 || form.priority > 9) {
      setFormError("Priority must be between 1 and 9.");
      return;
    }

    const implied = ACTION_DEFAULTS[form.action] || {};
    const impliedResourceType = implied.resource_type ?? form.resource_type;
    const impliedResourceDeviceType = Object.prototype.hasOwnProperty.call(
      implied,
      "resource_device_type",
    )
      ? implied.resource_device_type
      : form.resource_device_type;

    const payload = {
      ...form,
      resource_type: impliedResourceType,
      resource_device_type:
        impliedResourceType === "device" ? impliedResourceDeviceType : null,
      subject_roles: form.subject_type === "device" ? null : form.subject_roles,
      subject_device_type:
        form.subject_type === "device" ? form.subject_device_type : null,
      minimum_clearance: form.subject_type === "device" ? null : form.minimum_clearance,
    };

    delete payload.subject_role;

    try {
      if (modal?.type === "edit") {
        const updated = await updatePolicy(payload, currentPerson?.person_id);
        setMessage(`Policy "${updated.name}" updated.`);
      } else {
        const created = await createPolicy(payload, currentPerson?.person_id);
        setMessage(`Policy "${created.name}" created as ${created.policy_id}.`);
      }

      setForm({ ...blankPolicy, subject_roles: [...ALL_ROLE_VALUES] });
      setModal(null);
      await loadPolicies();
    } catch (error) {
      setFormError(error.message);
    }
  }

  async function removeCurrentPolicy() {
    if (!form.policy_id) return;

    const confirmed = window.confirm(
      `Delete ABAC policy "${form.name}" (${form.policy_id})? This action cannot be undone.`,
    );
    if (!confirmed) return;

    setFormError("");
    try {
      await deletePolicy(form.policy_id, currentPerson?.person_id);
      setMessage(`Policy "${form.name}" deleted.`);
      closePolicyModal();
      await loadPolicies();
    } catch (error) {
      setFormError(error.message);
    }
  }

  async function toggle(policy) {
    setMessage("");
    try {
      await updatePolicy(
        {
          ...normalisePolicy(policy),
          enabled: !policy.enabled,
        },
        currentPerson?.person_id,
      );
      await loadPolicies();
    } catch (error) {
      setMessage(error.message);
    }
  }

  function startEditing(policy) {
    setForm(normalisePolicy(policy));
    setMessage("");
    setFormError("");
    setModal({ type: "edit" });
  }

  const {
    sortedRows: sortedPolicies,
    sort: policySort,
    requestSort: requestPolicySort,
  } = useTableSort(policies, {
    defaultKey: "policy_id",
    valueGetters: {
      action: (policy) => actionLabel(policy.action),
      subject: (policy) =>
        `${subjectTypeLabel(policy.subject_type)} ${policySubjectSummary(policy)}`,
      resource: (policy) => policyResourceSummary(policy),
      effect: (policy) => humanize(policy.effect),
      enabled: (policy) => (policy.enabled ? "Enabled" : "Disabled"),
    },
    numericKeys: ["priority"],
  });

  const mayManageABAC = canManageABAC(currentPerson);
  const allRolesSelected = form.subject_roles?.length === ALL_ROLE_VALUES.length;

  return (
    <>
      <article className="panel">
        <div className="panel-heading">
          <div>
            <h2>ABAC Policies</h2>
            <p className="muted">
              Click a heading to sort. Policy IDs are assigned by the gateway and remain
              immutable.
            </p>
          </div>
          {mayManageABAC && (
            <button type="button" onClick={startAdding}>
              Add Policy
            </button>
          )}
        </div>

        {message && <Notice notice={{ type: "info", text: message }} />}

        <table>
          <thead>
            <tr>
              <th>
                <SortHead field="name" sort={policySort} onSort={requestPolicySort}>
                  Policy Name
                </SortHead>
              </th>
              <th>
                <SortHead field="effect" sort={policySort} onSort={requestPolicySort}>
                  Effect
                </SortHead>
              </th>
              <th>
                <SortHead field="action" sort={policySort} onSort={requestPolicySort}>
                  Action
                </SortHead>
              </th>
              <th>
                <SortHead field="subject" sort={policySort} onSort={requestPolicySort}>
                  Subject
                </SortHead>
              </th>
              <th>
                <SortHead field="resource" sort={policySort} onSort={requestPolicySort}>
                  Resource
                </SortHead>
              </th>
              <th>
                <SortHead field="priority" sort={policySort} onSort={requestPolicySort}>
                  Priority
                </SortHead>
              </th>
              <th>
                <SortHead field="enabled" sort={policySort} onSort={requestPolicySort}>
                  Status
                </SortHead>
              </th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {sortedPolicies.map((policy) => (
              <tr key={policy.policy_id}>
                <td>
                  {policy.name}
                  <small>{policy.policy_id}</small>
                </td>
                <td>{humanize(policy.effect)}</td>
                <td>{actionLabel(policy.action)}</td>
                <td>
                  {subjectTypeLabel(policy.subject_type)} —{" "}
                  {policySubjectSummary(policy)}
                  {policy.minimum_clearance !== null &&
                    policy.minimum_clearance !== undefined && (
                      <small>Minimum Clearance: {policy.minimum_clearance}</small>
                    )}
                </td>
                <td>{policyResourceSummary(policy)}</td>
                <td>{policy.priority}</td>
                <td>
                  {mayManageABAC ? (
                    <button
                      type="button"
                      className={`status-button ${policy.enabled ? "status-enabled" : "status-disabled"}`}
                      onClick={() => toggle(policy)}
                    >
                      {policy.enabled ? "Enabled" : "Disabled"}
                    </button>
                  ) : (
                    <span
                      className={`status-badge ${policy.enabled ? "status-enabled" : "status-disabled"}`}
                    >
                      {policy.enabled ? "Enabled" : "Disabled"}
                    </span>
                  )}
                </td>
                <td>
                  {mayManageABAC ? (
                    <button type="button" onClick={() => startEditing(policy)}>
                      Edit
                    </button>
                  ) : (
                    <span className="muted">Read Only</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </article>

      {mayManageABAC && modal && (
        <Modal
          title={modal.type === "add" ? "Add ABAC Policy" : `Edit ${form.name}`}
          onClose={closePolicyModal}
          wide
        >
          <form className="stack-form" onSubmit={save}>
            {formError && <div className="error-banner">{formError}</div>}

            <label>
              Policy Name
              <input
                required
                placeholder="e.g. Facility Engineers May Control HVAC"
                value={form.name}
                onChange={(event) => setForm({ ...form, name: event.target.value })}
              />
            </label>

            <label>
              Effect
              <select
                value={form.effect}
                onChange={(event) => setForm({ ...form, effect: event.target.value })}
              >
                <option value="allow">Allow</option>
                <option value="deny">Deny</option>
              </select>
            </label>

            <label>
              Subject Type
              <select
                value={form.subject_type}
                onChange={(event) => changeSubjectType(event.target.value)}
              >
                <option value="personnel">Personnel</option>
                <option value="device">Device</option>
              </select>
              <small>
                Choose who or what is requesting permission. The Action list only shows
                valid operations for that subject type.
              </small>
            </label>

            {form.subject_type === "device" ? (
              <label>
                Subject Device Type
                <select
                  value={form.subject_device_type || ""}
                  onChange={(event) =>
                    setForm({
                      ...form,
                      subject_device_type: event.target.value || null,
                    })
                  }
                >
                  <option value="">Any Device Type</option>
                  {DEVICE_TYPES.map(([value, label]) => (
                    <option key={value} value={value}>
                      {label}
                    </option>
                  ))}
                </select>
              </label>
            ) : (
              <>
                <fieldset className="policy-role-selector">
                  <legend>Allowed Subject Roles</legend>
                  <small>
                    All roles selected means Any Role. At least one role must be
                    selected.
                  </small>
                  <div className="control-inline">
                    <button
                      type="button"
                      onClick={selectAllRoles}
                      disabled={allRolesSelected}
                    >
                      Select All Roles (Any Role)
                    </button>
                  </div>
                  <div className="checkbox-group">
                    {SUBJECT_ROLES.map(([value, label]) => (
                      <label key={value}>
                        <input
                          type="checkbox"
                          checked={(form.subject_roles || []).includes(value)}
                          onChange={() => toggleSubjectRole(value)}
                        />
                        {label}
                      </label>
                    ))}
                  </div>
                </fieldset>

                <label>
                  Minimum Clearance
                  <select
                    value={
                      form.minimum_clearance === null ||
                      form.minimum_clearance === undefined
                        ? ""
                        : String(form.minimum_clearance)
                    }
                    onChange={(event) =>
                      setForm({
                        ...form,
                        minimum_clearance:
                          event.target.value === "" ? null : Number(event.target.value),
                      })
                    }
                  >
                    <option value="5">5 — OT Administration</option>
                    <option value="4">4 — Privileged Management / Security</option>
                    <option value="3">3 — Infrastructure Management</option>
                    <option value="2">2 — Routine Personnel</option>
                    <option value="1">1 — Contractor / Low Privilege</option>
                    <option value="0">0 — Untrusted / Visitor</option>
                    <option value="">No Minimum</option>
                  </select>
                </label>
              </>
            )}
            <label>
              Action
              <select
                value={form.action}
                onChange={(event) => changeAction(event.target.value)}
              >
                {(ACTIONS_BY_SUBJECT[form.subject_type] || []).map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </select>
              <small>
                Implied Resource: {impliedResourceSummary(form.action)}. The selected
                action fixes the resource automatically.
              </small>
            </label>

            {(ACTION_DEFAULTS[form.action]?.resource_type === "room" ||
              ACTION_DEFAULTS[form.action]?.resource_type === "device") && (
              <label className="checkbox-label">
                <input
                  type="checkbox"
                  checked={form.require_same_room}
                  onChange={(event) =>
                    setForm({
                      ...form,
                      require_same_room: event.target.checked,
                    })
                  }
                />
                Require Subject and Resource to Be in the Same Room
              </label>
            )}

            <label>
              Priority (1–9)
              <input
                type="number"
                min="1"
                max="9"
                required
                value={form.priority}
                onChange={(event) =>
                  setForm({ ...form, priority: Number(event.target.value) })
                }
              />
              <small>
                Higher values are evaluated first. Matching explicit Deny policies still
                override Allow policies.
              </small>
            </label>

            <label className="checkbox-label">
              <input
                type="checkbox"
                checked={form.enabled}
                onChange={(event) =>
                  setForm({ ...form, enabled: event.target.checked })
                }
              />
              Enabled
            </label>

            <div className="modal-actions">
              {modal.type === "edit" && (
                <button
                  type="button"
                  className="danger-button"
                  onClick={removeCurrentPolicy}
                >
                  Delete Policy
                </button>
              )}
              <button type="button" onClick={closePolicyModal}>
                Cancel
              </button>
              <button type="submit" className="primary-button">
                {modal.type === "edit" ? "Save Changes" : "Create Policy"}
              </button>
            </div>
          </form>
        </Modal>
      )}
    </>
  );
}
