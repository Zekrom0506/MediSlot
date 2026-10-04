import { clinicHour, formatTime } from "../utils/time";

// Slots grouped by part of day, shown as large time buttons: the core of booking.
function groupByPartOfDay(slots) {
  const groups = [
    { name: "Morning", slots: [] },
    { name: "Afternoon", slots: [] },
    { name: "Evening", slots: [] },
  ];
  for (const slot of slots) {
    const hour = clinicHour(slot.start_time);
    if (hour < 12) {
      groups[0].slots.push(slot);
    } else if (hour < 17) {
      groups[1].slots.push(slot);
    } else {
      groups[2].slots.push(slot);
    }
  }
  return groups.filter((group) => group.slots.length > 0);
}

export default function SlotPicker({ slots, selectedSlotId, onSelect }) {
  if (slots.length === 0) {
    return (
      <p className="rounded-lg border border-dashed border-line px-4 py-6 text-center text-muted">
        No free times on this day. Try another date.
      </p>
    );
  }

  return (
    <div className="space-y-5">
      {groupByPartOfDay(slots).map((group) => (
        <div key={group.name}>
          <h3 className="mb-2 text-sm font-semibold text-muted">
            {group.name} <span className="font-normal">({group.slots.length} free)</span>
          </h3>
          <div className="grid grid-cols-3 gap-2 sm:grid-cols-4">
            {group.slots.map((slot) => {
              const isSelected = slot.id === selectedSlotId;
              return (
                <button
                  key={slot.id}
                  type="button"
                  onClick={() => onSelect(slot)}
                  aria-pressed={isSelected}
                  className={`tabular rounded-lg border px-2 py-3 text-base font-semibold transition-colors ${
                    isSelected
                      ? "border-brand bg-brand text-white"
                      : "border-line bg-white text-ink hover:border-brand hover:text-brand-dark"
                  }`}
                >
                  {formatTime(slot.start_time)}
                </button>
              );
            })}
          </div>
        </div>
      ))}
    </div>
  );
}
