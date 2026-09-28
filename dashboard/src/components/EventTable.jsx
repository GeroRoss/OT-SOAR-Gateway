/** Table shared by the dashboard event views. */

import { SortHead, useTableSort } from "./TableSort";

const COLUMNS = [
  ["timestamp", "Time"],
  ["type", "Type"],
  ["actor", "Actor"],
  ["action", "Action"],
  ["cause", "Cause"],
  ["violation", "Violation"],
  ["state", "State"],
];

export default function EventTable({ events }) {
  const { sortedRows, sort, requestSort } = useTableSort(events, {
    defaultKey: "timestamp",
    defaultDirection: "desc",
    dateKeys: ["timestamp"],
  });

  return (
    <table>
      <thead>
        <tr>
          {COLUMNS.map(([field, label]) => (
            <th key={field}>
              <SortHead field={field} sort={sort} onSort={requestSort}>
                {label}
              </SortHead>
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {sortedRows.map((event) => (
          <tr key={event.event_key}>
            <td>
              {new Date(event.timestamp).toLocaleString()}
              <small>{event.event_key}</small>
            </td>
            <td>{event.type}</td>
            <td>{event.actor}</td>
            <td>{event.action}</td>
            <td>{event.cause || "—"}</td>
            <td>{event.violation || "—"}</td>
            <td>{event.state || "—"}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
