/** Manages rooms/devices, manual overrides, and reusable IoT device policies. */

import { useEffect, useState } from "react";
import { readable } from "../utils/formatters";
import {
  controlDoor,
  controlHVAC,
  controlPDU,
  createDevice,
  createRoom,
  deleteDevice,
  deleteRoom,
  getDeviceOperationalState,
  getDeviceRegistrationPreview,
  getDevices,
  getRoomRegistrationPreview,
  getRooms,
  updateDevice,
  updateRoom,
} from "../api/gateway";
import Modal from "../components/Modal";
import IoTDevicePolicies from "../components/IoTDevicePolicies";
import { SortHead, useTableSort } from "../components/TableSort";

const DEVICE_TYPES = [
  ["environmental_sensor", "Environmental Sensor"],
  ["pdu", "Smart PDU"],
  ["hvac", "HVAC Controller"],
  ["biometric_door", "Biometric Door"],
  ["smoke_sensor", "Smoke Sensor"],
];

export default function Infrastructure({ currentPerson }) {
  const [rooms, setRooms] = useState([]);
  const [devices, setDevices] = useState([]);
  const [modal, setModal] = useState(null);
  const [roomForm, setRoomForm] = useState({ room_id: "", name: "" });
  const [deviceForm, setDeviceForm] = useState({
    device_id: "",
    device_type: "environmental_sensor",
    room_id: "",
    name: "",
  });
  const [devicePreview, setDevicePreview] = useState(null);
  const [coolingByDevice, setCoolingByDevice] = useState({});
  const [operationalByDevice, setOperationalByDevice] = useState({});
  const [roomMessage, setRoomMessage] = useState("");
  const [roomError, setRoomError] = useState("");
  const [deviceMessage, setDeviceMessage] = useState("");
  const [deviceError, setDeviceError] = useState("");

  async function load() {
    const [roomData, deviceData] = await Promise.all([getRooms(), getDevices()]);
    setRooms(roomData);
    setDevices(deviceData);

    const actuatorDevices = deviceData.filter((device) =>
      ["pdu", "biometric_door"].includes(device.device_type),
    );
    const stateEntries = await Promise.all(
      actuatorDevices.map(async (device) => {
        try {
          return [device.device_id, await getDeviceOperationalState(device.device_id)];
        } catch {
          return [device.device_id, null];
        }
      }),
    );
    setOperationalByDevice(Object.fromEntries(stateEntries));
  }

  useEffect(() => {
    load().catch((e) => {
      setRoomError(e.message);
      setDeviceError(e.message);
    });
  }, []);

  function roomName(roomId) {
    return rooms.find((room) => room.room_id === roomId)?.name || roomId;
  }

  async function openAddRoom() {
    try {
      const preview = await getRoomRegistrationPreview();
      setRoomForm({ room_id: preview.room_id, name: preview.name });
      setModal({ type: "room-add" });
      setRoomError("");
    } catch (e) {
      setRoomError(e.message);
    }
  }

  function openEditRoom(room) {
    setRoomForm({ room_id: room.room_id, name: room.name });
    setModal({ type: "room-edit", room });
  }

  async function removeRoom(room) {
    if (
      !window.confirm(
        `Delete ${room.name} (${room.room_id})? The room must have no active devices or personnel assignments.`,
      )
    )
      return;

    setRoomError("");
    setRoomMessage("");

    try {
      await deleteRoom(room.room_id, currentPerson?.person_id);
      setRoomMessage(`Deleted ${room.room_id}.`);
      await load();
    } catch (e) {
      setRoomError(e.message);
    }
  }

  async function saveRoom(event) {
    event.preventDefault();
    setRoomError("");
    setRoomMessage("");
    try {
      if (modal.type === "room-add") {
        const created = await createRoom(
          { name: roomForm.name },
          currentPerson?.person_id,
        );
        setRoomMessage(`Registered ${created.room_id} as ${created.name}.`);
      } else {
        await updateRoom(
          roomForm.room_id,
          { name: roomForm.name },
          currentPerson?.person_id,
        );
        setRoomMessage(`Updated ${roomForm.room_id}.`);
      }
      setModal(null);
      await load();
    } catch (e) {
      setRoomError(e.message);
    }
  }

  async function openAddDevice() {
    if (!rooms.length) {
      setDeviceError("Create a room before registering a device.");
      return;
    }
    try {
      const preview = await getDeviceRegistrationPreview("environmental_sensor");
      setDevicePreview(preview);
      setDeviceForm({
        device_id: preview.device_id,
        device_type: "environmental_sensor",
        room_id: rooms[0].room_id,
        name: preview.name,
      });
      setModal({ type: "device-add" });
      setDeviceError("");
    } catch (e) {
      setDeviceError(e.message);
    }
  }

  function openEditDevice(device) {
    setDevicePreview({
      device_id: device.device_id,
      protocol: device.protocol,
      criticality: device.criticality,
    });
    setDeviceForm({
      device_id: device.device_id,
      device_type: device.device_type,
      room_id: device.room_id,
      name: device.name,
    });
    setModal({ type: "device-edit", device });
  }

  async function changeDeviceType(deviceType) {
    try {
      const preview = await getDeviceRegistrationPreview(deviceType);
      setDevicePreview(preview);
      setDeviceForm((current) => ({
        ...current,
        device_type: deviceType,
        device_id: preview.device_id,
        name: preview.name,
      }));
    } catch (e) {
      setDeviceError(e.message);
    }
  }

  async function saveDevice(event) {
    event.preventDefault();
    setDeviceError("");
    setDeviceMessage("");
    try {
      if (modal.type === "device-add") {
        const created = await createDevice(
          {
            device_type: deviceForm.device_type,
            room_id: deviceForm.room_id,
            name: deviceForm.name,
          },
          currentPerson?.person_id,
        );
        setDeviceMessage(`Registered ${created.device_id} as ${created.name}.`);
      } else {
        await updateDevice(
          deviceForm.device_id,
          {
            name: deviceForm.name,
            room_id: deviceForm.room_id,
          },
          currentPerson?.person_id,
        );
        setDeviceMessage(`Updated ${deviceForm.device_id}.`);
      }
      setModal(null);
      await load();
    } catch (e) {
      setDeviceError(e.message);
    }
  }

  async function removeDevice(device) {
    if (
      !window.confirm(`Delete ${device.name} (${device.device_id}) from the registry?`)
    )
      return;
    try {
      await deleteDevice(device.device_id, currentPerson?.person_id);
      setDeviceMessage(`Deleted ${device.device_id}.`);
      setDeviceError("");
      await load();
    } catch (e) {
      setDeviceError(e.message);
    }
  }

  async function act(device, action) {
    setDeviceMessage("");
    setDeviceError("");
    if (!currentPerson) {
      setDeviceError("No active personnel account is selected.");
      return;
    }
    try {
      if (device.device_type === "hvac")
        await controlHVAC(
          device.device_id,
          currentPerson.person_id,
          coolingByDevice[device.device_id] ?? 50,
        );
      if (device.device_type === "pdu")
        await controlPDU(device.device_id, currentPerson.person_id, action === "on");
      if (device.device_type === "biometric_door")
        await controlDoor(device.device_id, currentPerson.person_id, action === "lock");
      setDeviceMessage(
        `Command executed for ${device.device_id} by ${currentPerson.name}.`,
      );
      await load();
    } catch (e) {
      setDeviceError(e.message);
    }
  }

  const {
    sortedRows: sortedRooms,
    sort: roomSort,
    requestSort: requestRoomSort,
  } = useTableSort(rooms, {
    defaultKey: "room_id",
  });

  const {
    sortedRows: sortedDevices,
    sort: deviceSort,
    requestSort: requestDeviceSort,
  } = useTableSort(devices, {
    defaultKey: "device_id",
    valueGetters: {
      room_id: (device) => `${roomName(device.room_id)} ${device.room_id}`,
    },
  });

  return (
    <section>
      <h1>Infrastructure</h1>
      {roomError && <p className="error-banner">{roomError}</p>}
      {roomMessage && <p className="success-banner">{roomMessage}</p>}

      <article className="panel">
        <div className="panel-heading">
          <div>
            <h2>Rooms</h2>
            <p className="muted">
              Room IDs are assigned by the gateway and remain immutable.
            </p>
          </div>
          <button type="button" onClick={openAddRoom}>
            Add room
          </button>
        </div>
        <table>
          <thead>
            <tr>
              <th>
                <SortHead field="name" sort={roomSort} onSort={requestRoomSort}>
                  Room
                </SortHead>
              </th>
              <th>
                <SortHead field="room_id" sort={roomSort} onSort={requestRoomSort}>
                  Room ID
                </SortHead>
              </th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {sortedRooms.map((room) => (
              <tr key={room.room_id}>
                <td>{room.name}</td>
                <td className="muted">{room.room_id}</td>
                <td>
                  <div className="table-actions">
                    <button type="button" onClick={() => openEditRoom(room)}>
                      Edit
                    </button>
                    <button
                      type="button"
                      className="danger-button"
                      onClick={() => removeRoom(room)}
                    >
                      Delete
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </article>

      {deviceError && <p className="error-banner">{deviceError}</p>}
      {deviceMessage && <p className="success-banner">{deviceMessage}</p>}

      <article className="panel">
        <div className="panel-heading">
          <div>
            <h2>Devices and Manual Override</h2>
            <p className="muted">
              Click a heading to sort. Security state is separate from physical
              power/actuator state.
            </p>
          </div>
          <button type="button" onClick={openAddDevice}>
            Add device
          </button>
        </div>
        {currentPerson && (
          <p className="muted">
            Commands are authorised as <strong>{currentPerson.name}</strong> (
            {readable(currentPerson.role)}, clearance {currentPerson.clearance}
            ).
          </p>
        )}
        <table>
          <thead>
            <tr>
              <th>
                <SortHead field="name" sort={deviceSort} onSort={requestDeviceSort}>
                  Device
                </SortHead>
              </th>
              <th>
                <SortHead
                  field="device_type"
                  sort={deviceSort}
                  onSort={requestDeviceSort}
                >
                  Type
                </SortHead>
              </th>
              <th>
                <SortHead field="room_id" sort={deviceSort} onSort={requestDeviceSort}>
                  Room
                </SortHead>
              </th>
              <th>
                <SortHead field="protocol" sort={deviceSort} onSort={requestDeviceSort}>
                  Protocol
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
                <SortHead
                  field="security_state"
                  sort={deviceSort}
                  onSort={requestDeviceSort}
                >
                  Security
                </SortHead>
              </th>
              <th>Manual control</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {sortedDevices.map((device) => (
              <tr key={device.device_id}>
                <td>
                  {device.name}
                  <small>{device.device_id}</small>
                </td>
                <td>{readable(device.device_type)}</td>
                <td>
                  {roomName(device.room_id)}
                  <small>{device.room_id}</small>
                </td>
                <td>{device.protocol.toUpperCase()}</td>
                <td>{readable(device.criticality)}</td>
                <td>
                  <span className={`state-badge state-${device.security_state}`}>
                    {device.security_state}
                  </span>
                </td>
                <td>
                  {device.device_type === "hvac" && (
                    <div className="control-inline">
                      <input
                        aria-label={`Cooling level for ${device.device_id}`}
                        className="compact-number"
                        type="number"
                        min="0"
                        max="100"
                        value={coolingByDevice[device.device_id] ?? 50}
                        onChange={(e) =>
                          setCoolingByDevice({
                            ...coolingByDevice,
                            [device.device_id]: e.target.value,
                          })
                        }
                      />
                      <button
                        type="button"
                        disabled={!currentPerson}
                        onClick={() => act(device, "set")}
                      >
                        Set cooling
                      </button>
                    </div>
                  )}
                  {device.device_type === "pdu" && (
                    <div className="control-inline">
                      <button
                        type="button"
                        disabled={!currentPerson}
                        className={
                          operationalByDevice[device.device_id]?.environment
                            ?.power_available
                            ? "state-on-button"
                            : ""
                        }
                        onClick={() => act(device, "on")}
                      >
                        Power on
                      </button>
                      <button
                        type="button"
                        disabled={!currentPerson}
                        className={
                          operationalByDevice[device.device_id]?.environment
                            ?.power_available === false
                            ? "state-off-button"
                            : ""
                        }
                        onClick={() => act(device, "off")}
                      >
                        Power off
                      </button>
                    </div>
                  )}
                  {device.device_type === "biometric_door" && (
                    <div className="control-inline">
                      <button
                        type="button"
                        disabled={!currentPerson}
                        className={
                          operationalByDevice[device.device_id]?.locked === true
                            ? "state-off-button"
                            : ""
                        }
                        onClick={() => act(device, "lock")}
                      >
                        Lock
                      </button>
                      <button
                        type="button"
                        disabled={!currentPerson}
                        className={
                          operationalByDevice[device.device_id]?.locked === false
                            ? "state-on-button"
                            : ""
                        }
                        onClick={() => act(device, "unlock")}
                      >
                        Unlock
                      </button>
                    </div>
                  )}
                  {!["hvac", "pdu", "biometric_door"].includes(device.device_type) && (
                    <span className="muted">Telemetry only</span>
                  )}
                </td>
                <td>
                  <div className="control-inline">
                    <button type="button" onClick={() => openEditDevice(device)}>
                      Edit
                    </button>
                    <button
                      type="button"
                      className="danger-button"
                      onClick={() => removeDevice(device)}
                    >
                      Delete
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </article>

      <IoTDevicePolicies currentPerson={currentPerson} />

      {modal?.type?.startsWith("room-") && (
        <Modal
          title={modal.type === "room-add" ? "Add room" : `Edit ${roomForm.room_id}`}
          onClose={() => setModal(null)}
        >
          <form className="stack-form" onSubmit={saveRoom}>
            <label>
              Room ID
              <input disabled value={roomForm.room_id} />
            </label>
            <label>
              Room name
              <input
                required
                value={roomForm.name}
                onChange={(e) => setRoomForm({ ...roomForm, name: e.target.value })}
              />
            </label>
            <div className="modal-actions">
              <button type="button" onClick={() => setModal(null)}>
                Cancel
              </button>
              <button type="submit" className="primary-button">
                Save
              </button>
            </div>
          </form>
        </Modal>
      )}

      {modal?.type?.startsWith("device-") && (
        <Modal
          title={
            modal.type === "device-add" ? "Add device" : `Edit ${deviceForm.device_id}`
          }
          onClose={() => setModal(null)}
        >
          <form className="stack-form" onSubmit={saveDevice}>
            <label>
              Device ID
              <input disabled value={deviceForm.device_id} />
            </label>
            <label>
              Device type
              <select
                disabled={modal.type === "device-edit"}
                value={deviceForm.device_type}
                onChange={(e) => changeDeviceType(e.target.value)}
              >
                {DEVICE_TYPES.map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Device name
              <input
                required
                value={deviceForm.name}
                onChange={(e) => setDeviceForm({ ...deviceForm, name: e.target.value })}
              />
            </label>
            <label>
              Room
              <select
                required
                value={deviceForm.room_id}
                onChange={(e) =>
                  setDeviceForm({ ...deviceForm, room_id: e.target.value })
                }
              >
                {sortedRooms.map((room) => (
                  <option key={room.room_id} value={room.room_id}>
                    {room.name} ({room.room_id})
                  </option>
                ))}
              </select>
            </label>
            {devicePreview && (
              <p className="muted">
                Criticality: {readable(devicePreview.criticality)}. These remain
                gateway-controlled.
              </p>
            )}
            <div className="modal-actions">
              <button type="button" onClick={() => setModal(null)}>
                Cancel
              </button>
              <button type="submit" className="primary-button">
                Save
              </button>
            </div>
          </form>
        </Modal>
      )}
    </section>
  );
}
