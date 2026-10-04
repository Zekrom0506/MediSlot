import { clinicDateString, formatDateString } from "../utils/time";

// The next 14 days as a horizontally scrolling row, matching how far ahead slots exist.
export default function DateStrip({ selectedDate, onChange, days = 14 }) {
  const dates = [];
  for (let offset = 0; offset < days; offset += 1) {
    dates.push(clinicDateString(offset));
  }

  return (
    <div className="-mx-4 flex gap-2 overflow-x-auto px-4 pb-2 sm:mx-0 sm:px-0">
      {dates.map((date, index) => {
        const [weekday, rest] = formatDateString(date).split(", ");
        const isSelected = date === selectedDate;
        return (
          <button
            key={date}
            type="button"
            onClick={() => onChange(date)}
            aria-pressed={isSelected}
            className={`flex min-w-[4.5rem] flex-col items-center rounded-lg border px-3 py-2 text-sm ${
              isSelected ? "border-brand bg-brand-soft text-brand-dark" : "border-line bg-white text-muted hover:border-ink"
            }`}
          >
            <span className="font-medium">{index === 0 ? "Today" : weekday}</span>
            <span className="tabular font-semibold text-ink">{rest}</span>
          </button>
        );
      })}
    </div>
  );
}
