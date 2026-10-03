// The API sends UTC timestamps. Everything is shown in clinic time (India).
const CLINIC_TIME_ZONE = "Asia/Kolkata";

const timeFormatter = new Intl.DateTimeFormat("en-IN", {
  timeZone: CLINIC_TIME_ZONE,
  hour: "numeric",
  minute: "2-digit",
  hour12: true,
});

const dateFormatter = new Intl.DateTimeFormat("en-IN", {
  timeZone: CLINIC_TIME_ZONE,
  weekday: "short",
  day: "numeric",
  month: "short",
});

const longDateFormatter = new Intl.DateTimeFormat("en-IN", {
  timeZone: CLINIC_TIME_ZONE,
  weekday: "long",
  day: "numeric",
  month: "long",
  year: "numeric",
});

const hourFormatter = new Intl.DateTimeFormat("en-GB", {
  timeZone: CLINIC_TIME_ZONE,
  hour: "2-digit",
  hourCycle: "h23",
});

const isoDateFormatter = new Intl.DateTimeFormat("en-CA", {
  timeZone: CLINIC_TIME_ZONE,
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
});

export function formatTime(isoString) {
  return timeFormatter.format(new Date(isoString));
}

export function formatDate(isoString) {
  return dateFormatter.format(new Date(isoString));
}

export function formatLongDate(isoString) {
  return longDateFormatter.format(new Date(isoString));
}

export function clinicHour(isoString) {
  return Number(hourFormatter.format(new Date(isoString)));
}

// "YYYY-MM-DD" for today (plus an offset) in clinic time, the format the API expects.
export function clinicDateString(daysFromToday = 0) {
  const moment = new Date(Date.now() + daysFromToday * 24 * 60 * 60 * 1000);
  return isoDateFormatter.format(moment);
}

// Label for a "YYYY-MM-DD" date, e.g. "Mon, 6 Oct".
export function formatDateString(dateString) {
  const middayInIndia = new Date(`${dateString}T12:00:00+05:30`);
  return dateFormatter.format(middayInIndia);
}

export function hoursUntil(isoString) {
  return (new Date(isoString).getTime() - Date.now()) / (60 * 60 * 1000);
}

export function formatRupees(amount) {
  return new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 0 }).format(
    Number(amount),
  );
}
