/** Manages personnel identities and authorization attributes. */

import { useEffect, useState } from "react";
import {
  createPersonnel,
  getPersonnel,
  getPersonnelRegistrationPreview,
  getRooms,
  updatePersonnel,
} from "../api/gateway";
import Modal from "../components/Modal";
import { SortHead, useTableSort } from "../components/TableSort";
import { humanize, roleLabel } from "../utils/formatters";

const ROLES = [
  ["visitor", "Visitor"],
  ["contractor", "Contractor"],
  ["technician", "Technician"],
  ["facility_operator", "Facility Operator"],
  ["facility_engineer", "Facility Engineer"],
  ["security_operator", "Security Operator"],
  ["ot_administrator", "OT Administrator"],
];

const CLEARANCE_PERMISSIONS = [
  {
    action: "Biometric door access request",
    roles: "All active personnel roles",
    clearance: 0,
  },
  {
    action: "Manual HVAC / PDU",
    roles: "Facility Operator, Facility Engineer, OT Administrator",
    clearance: 2,
  },
  {
    action: "Create / edit room",
    roles: "Technician, Facility Operator, Facility Engineer, OT Administrator",
    clearance: 3,
  },
  {
    action: "Register / edit / delete device",
    roles: "Technician, Facility Operator, Facility Engineer, OT Administrator",
    clearance: 3,
  },
  {
    action: "Manual door override",
    roles: "Security Operator, Facility Engineer, OT Administrator",
    clearance: 4,
  },
  {
    action: "Create / edit personnel",
    roles: "Facility Engineer, OT Administrator",
    clearance: 4,
  },
  {
    action: "Create / edit / delete IoT policy",
    roles: "Facility Engineer, OT Administrator",
    clearance: 4,
  },
  {
    action: "Create / edit / delete ABAC policy",
    roles: "OT Administrator",
    clearance: 5,
  },
];

const emptyForm = {
  person_id: "",
  name: "",
  role: "technician",
  clearance: 1,
  authorized_rooms: [],
  active: true,
};

export default function Personnel({ currentPerson, onPersonnelChanged }) {
  const [people, setPeople] = useState([]);
  const [rooms, setRooms] = useState([]);
  const [form, setForm] = useState(emptyForm);
  const [modal, setModal] = useState(null);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  async function load() {
    const [personData, roomData] = await Promise.all([getPersonnel(), getRooms()]);

    setPeople(personData);
    setRooms(roomData);
  }

  useEffect(() => {
    load().catch((e) => setError(e.message));
  }, []);

  async function openAdd() {
    try {
      const preview = await getPersonnelRegistrationPreview();

      setForm({
        ...emptyForm,
        person_id: preview.person_id,
      });

      setModal({ type: "add" });
      setError("");
    } catch (e) {
      setError(e.message);
    }
  }

  function openEdit(personnel) {
    setForm({
      person_id: personnel.person_id,
      name: personnel.name,
      role: personnel.role,
      clearance: personnel.clearance,
      authorized_rooms: [...personnel.authorized_rooms],
      active: personnel.active,
    });

    setModal({
      type: "edit",
      personnel,
    });
  }

  function toggleRoom(roomId) {
    setForm((current) => ({
      ...current,
      authorized_rooms: current.authorized_rooms.includes(roomId)
        ? current.authorized_rooms.filter((id) => id !== roomId)
        : [...current.authorized_rooms, roomId],
    }));
  }

  async function save(event) {
    event.preventDefault();

    setMessage("");
    setError("");

    const payload = {
      name: form.name,
      role: form.role,
      clearance: Number(form.clearance),
      authorized_rooms: form.authorized_rooms,
      active: form.active,
    };

    try {
      if (modal.type === "add") {
        const created = await createPersonnel(payload, currentPerson?.person_id);

        setMessage(`Created ${created.name} (${created.person_id}).`);
      } else {
        await updatePersonnel(form.person_id, payload, currentPerson?.person_id);

        setMessage(`Updated ${form.name}.`);
      }

      setModal(null);
      await load();
      await onPersonnelChanged?.();
    } catch (e) {
      setError(e.message);
    }
  }

  const {
    sortedRows: sortedPeople,
    sort: personnelSort,
    requestSort: requestPersonnelSort,
  } = useTableSort(people, {
    defaultKey: "person_id",
    valueGetters: {
      role: (personnel) => roleLabel(personnel.role),
      authorized_rooms: (personnel) =>
        personnel.authorized_rooms
          .map(
            (roomId) => rooms.find((room) => room.room_id === roomId)?.name || roomId,
          )
          .join(" "),
      active: (personnel) => (personnel.active ? "Active" : "Inactive"),
    },
    numericKeys: ["clearance"],
    rankings: {
      role: {
        "OT Administrator": 0,
        "Facility Engineer": 1,
        "Security Operator": 2,
        "Facility Operator": 3,
        Technician: 4,
        Contractor: 5,
        Visitor: 6,
      },
    },
  });

  return (
    <section>
      <h1>Personnel</h1>

      <div className="info-banner">
        <strong>Role and Clearance Permissions</strong>

        <p>
          Authorization requires the appropriate role and minimum clearance. Room
          authorization and other ABAC conditions still apply where relevant. Higher
          clearance alone does not grant permissions assigned to another role.
        </p>

        <table>
          <thead>
            <tr>
              <th>Action</th>
              <th>Eligible Roles</th>
              <th>Minimum Clearance</th>
            </tr>
          </thead>
          <tbody>
            {CLEARANCE_PERMISSIONS.map((permission) => (
              <tr key={permission.action}>
                <td>{permission.action}</td>
                <td>{permission.roles}</td>
                <td>{permission.clearance}</td>
              </tr>
            ))}
          </tbody>
        </table>

        <p className="muted">
          Clearance 0–1 represents low-privilege personnel. These accounts do not
          receive privileged infrastructure-management permissions from clearance alone.
          Active personnel may still request biometric access to rooms for which they
          are authorized.
        </p>
      </div>

      {error && <p className="error-banner">{error}</p>}
      {message && <p className="success-banner">{message}</p>}

      <article className="panel">
        <div className="panel-heading">
          <div>
            <h2>Personnel</h2>
          </div>

          <button type="button" onClick={openAdd}>
            Add Personnel
          </button>
        </div>

        <table>
          <thead>
            <tr>
              <th>
                <SortHead
                  field="name"
                  sort={personnelSort}
                  onSort={requestPersonnelSort}
                >
                  Personnel
                </SortHead>
              </th>
              <th>
                <SortHead
                  field="role"
                  sort={personnelSort}
                  onSort={requestPersonnelSort}
                >
                  Role
                </SortHead>
              </th>
              <th>
                <SortHead
                  field="clearance"
                  sort={personnelSort}
                  onSort={requestPersonnelSort}
                >
                  Clearance
                </SortHead>
              </th>
              <th>
                <SortHead
                  field="authorized_rooms"
                  sort={personnelSort}
                  onSort={requestPersonnelSort}
                >
                  Authorized Rooms
                </SortHead>
              </th>
              <th>
                <SortHead
                  field="active"
                  sort={personnelSort}
                  onSort={requestPersonnelSort}
                >
                  Status
                </SortHead>
              </th>
              <th>Actions</th>
            </tr>
          </thead>

          <tbody>
            {sortedPeople.map((personnel) => (
              <tr
                key={personnel.person_id}
                className={!personnel.active ? "inactive-row" : ""}
              >
                <td>
                  {personnel.name}
                  <small>{personnel.person_id}</small>
                </td>

                <td>{roleLabel(personnel.role)}</td>

                <td>{personnel.clearance}</td>

                <td>
                  {personnel.authorized_rooms.length
                    ? personnel.authorized_rooms
                        .map(
                          (roomId) =>
                            rooms.find((room) => room.room_id === roomId)?.name ||
                            roomId,
                        )
                        .join(", ")
                    : "None"}

                  {personnel.authorized_rooms.length > 0 && (
                    <small>{personnel.authorized_rooms.join(", ")}</small>
                  )}
                </td>

                <td>
                  <span
                    className={`status-badge status-${
                      personnel.active ? "active" : "inactive"
                    }`}
                  >
                    {personnel.active ? "Active" : "Inactive"}
                  </span>
                </td>

                <td>
                  <button type="button" onClick={() => openEdit(personnel)}>
                    Edit
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </article>

      {modal && (
        <Modal
          title={modal.type === "add" ? "Add Personnel" : `Edit ${form.name}`}
          onClose={() => setModal(null)}
        >
          <form className="stack-form" onSubmit={save}>
            <label>
              Personnel ID
              <input disabled value={form.person_id} />
            </label>

            <label>
              Name
              <input
                required
                value={form.name}
                onChange={(e) =>
                  setForm({
                    ...form,
                    name: e.target.value,
                  })
                }
              />
            </label>

            <label>
              Role
              <select
                value={form.role}
                onChange={(e) =>
                  setForm({
                    ...form,
                    role: e.target.value,
                  })
                }
              >
                {ROLES.map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </select>
            </label>

            <label>
              Clearance (0–5)
              <input
                type="number"
                min="0"
                max="5"
                value={form.clearance}
                onChange={(e) =>
                  setForm({
                    ...form,
                    clearance: e.target.value,
                  })
                }
              />
              <small>
                Clearance is evaluated together with role, room authorization and other
                ABAC conditions. A higher clearance does not automatically inherit
                permissions from other roles.
              </small>
            </label>

            <fieldset>
              <legend>Authorized Rooms</legend>

              <div className="checkbox-group">
                {rooms.map((room) => (
                  <label key={room.room_id}>
                    <input
                      type="checkbox"
                      checked={form.authorized_rooms.includes(room.room_id)}
                      onChange={() => toggleRoom(room.room_id)}
                    />

                    {room.name}
                    <small>{room.room_id}</small>
                  </label>
                ))}
              </div>
            </fieldset>

            <label className="checkbox-label">
              <input
                type="checkbox"
                checked={form.active}
                onChange={(e) =>
                  setForm({
                    ...form,
                    active: e.target.checked,
                  })
                }
              />
              Active Account
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
    </section>
  );
}
