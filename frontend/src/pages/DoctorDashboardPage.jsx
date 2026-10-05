import { useCallback, useEffect, useState } from "react";
import Alert from "../components/Alert";
import DateStrip from "../components/DateStrip";
import Spinner from "../components/Spinner";
import * as api from "../api/medislot";
import { friendlyErrorMessage } from "../utils/errors";
import { clinicDateString, formatDate, formatDateString, formatTime, hoursUntil } from "../utils/time";

const WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];

export default function DoctorDashboardPage() {
  const [profile, setProfile] = useState(null);

  useEffect(() => {
    api.fetchMyDoctorProfile().then(setProfile).catch(() => {});
  }, []);

  return (
    <div className="space-y-10">
      <div>
        <h1 className="text-2xl font-bold">{profile ? profile.full_name : "My day"}</h1>
        {profile && (
          <p className="text-muted">
            {profile.specialty} at {profile.clinic.name}, {profile.appointment_length_minutes} minute appointments
          </p>
        )}
      </div>
      <AppointmentsSection />
      <SlotsSection />
      <ScheduleSection />
    </div>
  );
}

function AppointmentsSection() {
  const [scope, setScope] = useState("today");
  const [appointments, setAppointments] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState(null);

  const loadAppointments = useCallback(() => {
    setIsLoading(true);
    api
      .fetchAppointments(scope)
      .then(setAppointments)
      .catch(setError)
      .finally(() => setIsLoading(false));
  }, [scope]);

  useEffect(() => {
    loadAppointments();
  }, [loadAppointments]);

  async function markOutcome(appointmentId, status) {
    setError(null);
    try {
      await api.recordOutcome(appointmentId, status);
      loadAppointments();
    } catch (outcomeError) {
      setError(outcomeError);
    }
  }

  return (
    <section>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-lg font-semibold">Appointments</h2>
        <div className="inline-flex rounded-lg border border-line bg-white p-1" role="tablist">
          {["today", "upcoming"].map((name) => (
            <button key={name} type="button" role="tab" aria-selected={scope === name} onClick={() => setScope(name)}
              className={`rounded-md px-4 py-1.5 text-sm font-semibold ${scope === name ? "bg-brand text-white" : "text-muted"}`}>
              {name === "today" ? "Today" : "Upcoming"}
            </button>
          ))}
        </div>
      </div>
      <div className="mt-3">
        <Alert kind="error" onClose={() => setError(null)}>{friendlyErrorMessage(error)}</Alert>
      </div>
      {isLoading ? (
        <Spinner label="Loading appointments" />
      ) : appointments.length === 0 ? (
        <p className="py-6 text-muted">{scope === "today" ? "No appointments today." : "No upcoming appointments."}</p>
      ) : (
        <ul className="panel mt-3 divide-y divide-line">
          {appointments.map((appointment) => {
            const hasStarted = hoursUntil(appointment.slot.start_time) <= 0;
            return (
              <li key={appointment.id} className="flex flex-col gap-3 p-4 sm:flex-row sm:items-center">
                <div className="w-28 shrink-0">
                  <p className="tabular text-xl font-bold">{formatTime(appointment.slot.start_time)}</p>
                  {scope === "upcoming" && <p className="text-sm text-muted">{formatDate(appointment.slot.start_time)}</p>}
                </div>
                <div className="flex-1">
                  <p className="font-semibold">{appointment.patient.full_name}</p>
                  <p className="text-sm text-muted">{appointment.patient.phone_number || "No phone number"}</p>
                  {appointment.reason_for_visit && <p className="mt-1 text-sm">{appointment.reason_for_visit}</p>}
                </div>
                {appointment.status === "confirmed" && hasStarted && (
                  <div className="flex gap-2">
                    <button type="button" className="button-primary py-2 text-sm" onClick={() => markOutcome(appointment.id, "completed")}>
                      Mark completed
                    </button>
                    <button type="button" className="button-secondary py-2 text-sm" onClick={() => markOutcome(appointment.id, "no_show")}>
                      Mark no-show
                    </button>
                  </div>
                )}
                {appointment.status !== "confirmed" && (
                  <p className="text-sm font-medium text-muted">{appointment.status === "completed" ? "Completed" : "No-show"}</p>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}

const SLOT_STYLES = {
  available: "border-line bg-white text-ink hover:border-warn",
  blocked: "border-dashed border-warn/60 bg-warn-soft text-warn",
  booked: "border-brand bg-brand-soft text-brand-dark cursor-default",
};

function SlotsSection() {
  const [selectedDate, setSelectedDate] = useState(clinicDateString(0));
  const [slots, setSlots] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState(null);
  const [notice, setNotice] = useState("");

  const loadSlots = useCallback(() => {
    setIsLoading(true);
    api
      .fetchMySlots(selectedDate)
      .then(setSlots)
      .catch(setError)
      .finally(() => setIsLoading(false));
  }, [selectedDate]);

  useEffect(() => {
    setNotice("");
    loadSlots();
  }, [loadSlots]);

  async function toggleSlot(slot) {
    if (slot.status === "booked") {
      return;
    }
    setError(null);
    try {
      if (slot.status === "available") {
        await api.blockSlot(slot.id);
      } else {
        await api.unblockSlot(slot.id);
      }
      loadSlots();
    } catch (slotError) {
      setError(slotError);
    }
  }

  async function handleBlockDay() {
    setError(null);
    try {
      const result = await api.blockDay(selectedDate);
      let message = `Blocked ${result.blocked_count} free slots on ${formatDateString(selectedDate)}.`;
      if (result.booked_count > 0) {
        message += ` ${result.booked_count} booked appointments were left in place.`;
      }
      setNotice(message);
      loadSlots();
    } catch (blockError) {
      setError(blockError);
    }
  }

  return (
    <section>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold">Time off</h2>
          <p className="text-sm text-muted">Tap a free time to block it, or a blocked time to open it again.</p>
        </div>
        <button type="button" className="button-secondary py-2 text-sm" onClick={handleBlockDay}>
          Block whole day
        </button>
      </div>
      <div className="mt-3">
        <DateStrip selectedDate={selectedDate} onChange={setSelectedDate} />
      </div>
      <div className="mt-3 space-y-3">
        <Alert kind="success" onClose={() => setNotice("")}>{notice}</Alert>
        <Alert kind="error" onClose={() => setError(null)}>{friendlyErrorMessage(error)}</Alert>
      </div>
      {isLoading ? (
        <Spinner label="Loading slots" />
      ) : slots.length === 0 ? (
        <p className="py-6 text-muted">No slots on this day. Add working hours below.</p>
      ) : (
        <div className="mt-3 grid grid-cols-3 gap-2 sm:grid-cols-6">
          {slots.map((slot) => (
            <button key={slot.id} type="button" onClick={() => toggleSlot(slot)} disabled={slot.status === "booked"}
              className={`tabular rounded-lg border px-2 py-2.5 text-sm font-semibold ${SLOT_STYLES[slot.status]}`}
              title={slot.status === "booked" ? "Booked" : slot.status === "blocked" ? "Blocked" : "Free"}>
              {formatTime(slot.start_time)}
              <span className="block text-xs font-normal">
                {slot.status === "available" ? "Free" : slot.status === "blocked" ? "Blocked" : "Booked"}
              </span>
            </button>
          ))}
        </div>
      )}
    </section>
  );
}

function trimSeconds(timeString) {
  return timeString.slice(0, 5);
}

function ScheduleSection() {
  const [entries, setEntries] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState(null);
  const [notice, setNotice] = useState("");

  useEffect(() => {
    api
      .fetchSchedule()
      .then((saved) => {
        const editable = [];
        for (const entry of saved) {
          editable.push({ day_of_week: entry.day_of_week, start_time: trimSeconds(entry.start_time), end_time: trimSeconds(entry.end_time) });
        }
        setEntries(editable);
      })
      .catch(setError)
      .finally(() => setIsLoading(false));
  }, []);

  function updateEntry(index, field, value) {
    const updated = [...entries];
    updated[index] = { ...updated[index], [field]: field === "day_of_week" ? Number(value) : value };
    setEntries(updated);
  }

  function addEntry() {
    setEntries([...entries, { day_of_week: 0, start_time: "09:00", end_time: "13:00" }]);
  }

  function removeEntry(index) {
    setEntries(entries.filter((_, position) => position !== index));
  }

  async function handleSave() {
    setIsSaving(true);
    setError(null);
    setNotice("");
    try {
      await api.saveSchedule(entries);
      setNotice("Weekly hours saved. Slots for the next 14 days have been updated.");
    } catch (saveError) {
      setError(saveError);
    } finally {
      setIsSaving(false);
    }
  }

  if (isLoading) {
    return <Spinner label="Loading weekly hours" />;
  }

  return (
    <section>
      <h2 className="text-lg font-semibold">Weekly hours</h2>
      <p className="text-sm text-muted">Patients can book inside these hours. Existing bookings are never removed.</p>
      <div className="mt-3 space-y-3">
        <Alert kind="success" onClose={() => setNotice("")}>{notice}</Alert>
        <Alert kind="error" onClose={() => setError(null)}>{friendlyErrorMessage(error)}</Alert>
      </div>
      <div className="panel mt-3 divide-y divide-line">
        {entries.length === 0 && <p className="p-4 text-muted">No working hours yet.</p>}
        {entries.map((entry, index) => (
          <div key={index} className="grid grid-cols-2 items-end gap-3 p-4 sm:grid-cols-[2fr_1fr_1fr_auto]">
            <div className="col-span-2 sm:col-span-1">
              <label className="field-label" htmlFor={`day-${index}`}>Day</label>
              <select id={`day-${index}`} className="field-input" value={entry.day_of_week}
                onChange={(event) => updateEntry(index, "day_of_week", event.target.value)}>
                {WEEKDAYS.map((name, dayNumber) => (
                  <option key={name} value={dayNumber}>{name}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="field-label" htmlFor={`start-${index}`}>From</label>
              <input id={`start-${index}`} type="time" className="field-input" value={entry.start_time}
                onChange={(event) => updateEntry(index, "start_time", event.target.value)} />
            </div>
            <div>
              <label className="field-label" htmlFor={`end-${index}`}>To</label>
              <input id={`end-${index}`} type="time" className="field-input" value={entry.end_time}
                onChange={(event) => updateEntry(index, "end_time", event.target.value)} />
            </div>
            <button type="button" className="button-danger col-span-2 text-sm sm:col-span-1" onClick={() => removeEntry(index)}>
              Remove
            </button>
          </div>
        ))}
      </div>
      <div className="mt-3 flex gap-3">
        <button type="button" className="button-secondary" onClick={addEntry}>Add hours</button>
        <button type="button" className="button-primary" onClick={handleSave} disabled={isSaving}>
          {isSaving ? "Saving…" : "Save weekly hours"}
        </button>
      </div>
    </section>
  );
}
