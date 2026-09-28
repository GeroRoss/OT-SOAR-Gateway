/** Dashboard requests to the gateway API. */

const GATEWAY_URL = import.meta.env.VITE_GATEWAY_URL || "http://localhost:8000";

function actorHeaders(personId) {
  return personId ? { "X-Actor-ID": personId } : {};
}

async function request(path, options = {}) {
  const response = await fetch(`${GATEWAY_URL}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...options.headers,
    },
  });

  if (!response.ok) {
    let detail = response.statusText;

    try {
      const body = await response.json();

      if (typeof body.detail === "string") {
        detail = body.detail;
      } else if (body.detail?.message) {
        const reason = body.detail?.decision?.reason;

        detail = reason ? `${body.detail.message}. ${reason}` : body.detail.message;
      } else if (body.detail) {
        detail = JSON.stringify(body.detail);
      }
    } catch {
      // Keep HTTP status text when no
      // JSON error body is available.
    }

    const error = new Error(detail);
    error.status = response.status;
    throw error;
  }

  return response.status === 204 ? null : response.json();
}

export const getHealth = () => request("/health");

export const resetDemoData = () =>
  request("/system/reset-demo-data", {
    method: "POST",
  });

export const getRooms = () => request("/rooms");

export const getRoomRegistrationPreview = () => request("/rooms/registration-preview");

export const createRoom = (payload, personId) =>
  request("/rooms", {
    method: "POST",
    headers: actorHeaders(personId),
    body: JSON.stringify(payload),
  });

export const updateRoom = (roomId, payload, personId) =>
  request(`/rooms/${encodeURIComponent(roomId)}`, {
    method: "PUT",
    headers: actorHeaders(personId),
    body: JSON.stringify(payload),
  });

export const deleteRoom = (roomId, personId) =>
  request(`/rooms/${encodeURIComponent(roomId)}`, {
    method: "DELETE",
    headers: actorHeaders(personId),
  });

export const getDevices = () => request("/devices");

export const getDeviceOperationalState = (deviceId) =>
  request(`/devices/${encodeURIComponent(deviceId)}/operational-state`);

export const getDeviceRegistrationPreview = (deviceType) =>
  request(`/devices/registration-preview/${encodeURIComponent(deviceType)}`);

export const createDevice = (device, personId) =>
  request("/devices", {
    method: "POST",
    headers: actorHeaders(personId),
    body: JSON.stringify(device),
  });

export const updateDevice = (deviceId, payload, personId) =>
  request(`/devices/${encodeURIComponent(deviceId)}`, {
    method: "PUT",
    headers: actorHeaders(personId),
    body: JSON.stringify(payload),
  });

export const deleteDevice = (deviceId, personId) =>
  request(`/devices/${encodeURIComponent(deviceId)}`, {
    method: "DELETE",
    headers: actorHeaders(personId),
  });

export const getPersonnel = () => request("/personnel");

export const getPersonnelRegistrationPreview = () =>
  request("/personnel/registration-preview");

export const createPersonnel = (personnel, personId) =>
  request("/personnel", {
    method: "POST",
    headers: actorHeaders(personId),
    body: JSON.stringify(personnel),
  });

export const updatePersonnel = (personId, personnel, actorId) =>
  request(`/personnel/${encodeURIComponent(personId)}`, {
    method: "PUT",
    headers: actorHeaders(actorId),
    body: JSON.stringify(personnel),
  });

export const getPolicies = () => request("/policies");

export const getIoTDevicePolicies = () => request("/iot-policies");

export const createIoTDevicePolicy = (policy, personId) =>
  request("/iot-policies", {
    method: "POST",
    headers: actorHeaders(personId),
    body: JSON.stringify(policy),
  });

export const updateIoTDevicePolicy = (policy, personId) =>
  request(`/iot-policies/${encodeURIComponent(policy.policy_id)}`, {
    method: "PUT",
    headers: actorHeaders(personId),
    body: JSON.stringify({
      name: policy.name,
      enabled: policy.enabled,
      trigger_device_type: policy.trigger_device_type,
      trigger_attribute: policy.trigger_attribute,
      operator: policy.operator,
      threshold: Number(policy.threshold),
      required_source_state: policy.required_source_state,
      target_device_type: policy.target_device_type,
      target_scope: policy.target_scope,
      action: policy.action,
      action_value: Number(policy.action_value),
      fallback_value:
        policy.fallback_value === null || policy.fallback_value === ""
          ? null
          : Number(policy.fallback_value),
      priority: Number(policy.priority),
    }),
  });

export const deleteIoTDevicePolicy = (policyId, personId) =>
  request(`/iot-policies/${encodeURIComponent(policyId)}`, {
    method: "DELETE",
    headers: actorHeaders(personId),
  });

export const createPolicy = (policy, personId) =>
  request("/policies", {
    method: "POST",
    headers: actorHeaders(personId),
    body: JSON.stringify(policy),
  });

export const updatePolicy = (policy, personId) =>
  request(`/policies/${encodeURIComponent(policy.policy_id)}`, {
    method: "PUT",
    headers: actorHeaders(personId),
    body: JSON.stringify(policy),
  });

export const deletePolicy = (policyId, personId) =>
  request(`/policies/${encodeURIComponent(policyId)}`, {
    method: "DELETE",
    headers: actorHeaders(personId),
  });

export const getSecurityConfig = () => request("/security/config");

export const getEvents = ({ types = [], sourceId = null, limit = 100 } = {}) => {
  const params = new URLSearchParams();

  types.forEach((type) => params.append("type", type));

  if (sourceId) {
    params.set("source_id", sourceId);
  }

  params.set("limit", String(limit));

  return request(`/events?${params.toString()}`);
};

export const getResponses = (deviceId = null, limit = 100) =>
  request(
    deviceId
      ? `/responses?device_id=${encodeURIComponent(deviceId)}&limit=${limit}`
      : `/responses?limit=${limit}`,
  );

export const getDeviceSecurityStatus = (deviceId) =>
  request(`/security/devices/${encodeURIComponent(deviceId)}`);

export const resetSecurityState = (deviceId, personId) =>
  request(`/security/devices/${encodeURIComponent(deviceId)}/reset`, {
    method: "POST",
    headers: actorHeaders(personId),
  });

export const getSimulationEnvironments = () => request("/simulation/environments");

export const updateSimulationEnvironment = (roomId, values) =>
  request(`/simulation/environments/${encodeURIComponent(roomId)}`, {
    method: "PUT",
    body: JSON.stringify(values),
  });

export const launchAttack = (payload) =>
  request("/attack/launch", {
    method: "POST",
    body: JSON.stringify(payload),
  });

export const getAttackStatus = () => request("/attack/status");

export const requestDoorAccess = (deviceId, personId) =>
  request(`/access/doors/${encodeURIComponent(deviceId)}`, {
    method: "POST",
    body: JSON.stringify({
      person_id: personId,
    }),
  });

export async function getLatestTelemetry(device) {
  const routes = {
    environmental_sensor: "environmental",
    smoke_sensor: "smoke",
    pdu: "pdu",
  };

  const telemetryType = routes[device.device_type];

  if (!telemetryType) {
    return null;
  }

  try {
    return await request(
      `/telemetry/${telemetryType}/${encodeURIComponent(device.device_id)}`,
    );
  } catch (error) {
    if (error.status === 404) {
      return null;
    }

    throw error;
  }
}

export const getTelemetryHistory = (deviceId, limit = 120) =>
  request(`/telemetry/history/${encodeURIComponent(deviceId)}?limit=${limit}`);

export const controlHVAC = (deviceId, personId, coolingLevel) =>
  request(`/devices/${deviceId}/commands/hvac`, {
    method: "POST",
    body: JSON.stringify({
      person_id: personId,
      command: {
        cooling_level: Number(coolingLevel),
      },
    }),
  });

export const controlPDU = (deviceId, personId, powerOn) =>
  request(`/devices/${deviceId}/commands/pdu`, {
    method: "POST",
    body: JSON.stringify({
      person_id: personId,
      command: {
        power_on: powerOn,
      },
    }),
  });

export const controlDoor = (deviceId, personId, locked) =>
  request(`/devices/${deviceId}/commands/door`, {
    method: "POST",
    body: JSON.stringify({
      person_id: personId,
      command: {
        locked,
      },
    }),
  });
