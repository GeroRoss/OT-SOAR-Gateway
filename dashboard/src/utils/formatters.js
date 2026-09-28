/** Display labels for enums and common abbreviations. */

const ACRONYMS = {
  abac: "ABAC",
  hvac: "HVAC",
  id: "ID",
  iot: "IoT",
  mqtt: "MQTT",
  ot: "OT",
  pdu: "PDU",
};

export function humanize(value) {
  if (value === null || value === undefined || value === "") return "—";
  return String(value)
    .replaceAll("_", " ")
    .split(/\s+/)
    .map((word) => {
      const lower = word.toLowerCase();
      return (
        ACRONYMS[lower] ||
        `${word.charAt(0).toUpperCase()}${word.slice(1).toLowerCase()}`
      );
    })
    .join(" ");
}

export const readable = humanize;
export const roleLabel = humanize;
