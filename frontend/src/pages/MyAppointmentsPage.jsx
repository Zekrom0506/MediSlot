import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import Alert from "../components/Alert";
import DateStrip from "../components/DateStrip";
import Modal from "../components/Modal";
import SlotPicker from "../components/SlotPicker";
import Spinner from "../components/Spinner";
import * as api from "../api/medislot";
import { friendlyErrorMessage } from "../utils/errors";
import { clinicDateString, formatDate, formatTime, hoursUntil } from "../utils/time";

const STATUS_LABELS = {
  confirmed: "Confirmed",
  cancelled: "Cancelled",
  completed: "Completed",
  no_show: "Missed",
  rescheduled: "Rescheduled",
};

function statusLabel(booking) {
  if (booking.status === "cancelled" && booking.cancelled_by === "clinic") {
    return "Cancelled by the clinic";
  }
  return STATUS_LABELS[booking.status];
}

export default function MyAppointmentsPage() {
  const [scope, setScope] = useState("upcoming");
  const [bookings, setBookings] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState(null);
  const [notice, setNotice] = useState("");
  const [bookingToReschedule, setBookingToReschedule] = useState(null);

  const loadBookings = useCallback(() => {
    setIsLoading(true);
    api
      .fetchMyBookings(scope)
      .then(setBookings)
      .catch(setError)
      .finally(() => setIsLoading(false));
  }, [scope]);

  useEffect(() => {
    loadBookings();
  }, [loadBookings]);

  async function handleCancel(booking) {
    const confirmed = window.confirm(`Cancel your appointment with ${booking.doctor.full_name}?`);
    if (!confirmed) {
      return;
    }
    setError(null);
    try {
      await api.cancelBooking(booking.id);
      setNotice("Appointment cancelled. The time is now free for other patients.");
      loadBookings();
    } catch (cancelError) {
      setError(cancelError);
    }
  }

  function handleRescheduled() {
    setBookingToReschedule(null);
    setNotice("Appointment moved to the new time.");
    loadBookings();
  }

  return (
    <div>
      <h1 className="text-2xl font-bold">My appointments</h1>

      <div className="mt-4 inline-flex rounded-lg border border-line bg-white p-1" role="tablist">
        {["upcoming", "past"].map((name) => (
          <button
            key={name}
            type="button"
            role="tab"
            aria-selected={scope === name}
            onClick={() => setScope(name)}
            className={`rounded-md px-4 py-1.5 text-sm font-semibold ${scope === name ? "bg-brand text-white" : "text-muted"}`}
          >
            {name === "upcoming" ? "Upcoming" : "History"}
          </button>
        ))}
      </div>

      <div className="mt-4 space-y-3">
        <Alert kind="success" onClose={() => setNotice("")}>{notice}</Alert>
        <Alert kind="error" onClose={() => setError(null)}>{friendlyErrorMessage(error)}</Alert>
      </div>

      {isLoading ? (
        <Spinner label="Loading appointments" />
      ) : bookings.length === 0 ? (
        <p className="py-10 text-muted">
          {scope === "upcoming" ? (
            <>
              No upcoming appointments. <Link to="/" className="font-semibold text-brand hover:underline">Find a doctor</Link>
            </>
          ) : (
            "Past and cancelled appointments will show up here."
          )}
        </p>
      ) : (
        <ul className="panel mt-4 divide-y divide-line">
          {bookings.map((booking) => (
            <BookingRow
              key={booking.id}
              booking={booking}
              onCancel={() => handleCancel(booking)}
              onReschedule={() => setBookingToReschedule(booking)}
            />
          ))}
        </ul>
      )}

      {bookingToReschedule && (
        <RescheduleDialog
          booking={bookingToReschedule}
          onClose={() => setBookingToReschedule(null)}
          onDone={handleRescheduled}
        />
      )}
    </div>
  );
}

function BookingRow({ booking, onCancel, onReschedule }) {
  const isActive = booking.status === "confirmed" && hoursUntil(booking.slot.start_time) > 0;
  const canChange = isActive && hoursUntil(booking.slot.start_time) >= 2;

  return (
    <li className="flex flex-col gap-4 p-4 sm:flex-row sm:items-center">
      <div className="w-28 shrink-0">
        <p className="tabular text-xl font-bold">{formatTime(booking.slot.start_time)}</p>
        <p className="text-sm text-muted">{formatDate(booking.slot.start_time)}</p>
      </div>
      <div className="flex-1">
        <p className="font-semibold">{booking.doctor.full_name}</p>
        <p className="text-sm text-muted">
          {booking.doctor.specialty}, {booking.doctor.clinic_name}, {booking.doctor.city}
        </p>
        {!isActive && <p className="mt-1 text-sm font-medium text-muted">{statusLabel(booking)}</p>}
      </div>
      {isActive && (
        <div className="flex items-center gap-2">
          {canChange ? (
            <>
              <button type="button" className="button-secondary py-2 text-sm" onClick={onReschedule}>Reschedule</button>
              <button type="button" className="button-danger text-sm" onClick={onCancel}>Cancel</button>
            </>
          ) : (
            <p className="text-sm text-warn">Too close to the start to change</p>
          )}
        </div>
      )}
    </li>
  );
}

function RescheduleDialog({ booking, onClose, onDone }) {
  const [selectedDate, setSelectedDate] = useState(clinicDateString(0));
  const [slots, setSlots] = useState([]);
  const [selectedSlot, setSelectedSlot] = useState(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    setIsLoading(true);
    setSelectedSlot(null);
    api
      .fetchAvailableSlots(booking.doctor.id, selectedDate)
      .then(setSlots)
      .catch(setError)
      .finally(() => setIsLoading(false));
  }, [booking.doctor.id, selectedDate]);

  async function confirmMove() {
    setIsSaving(true);
    setError(null);
    try {
      await api.rescheduleBooking(booking.id, selectedSlot.id);
      onDone();
    } catch (moveError) {
      setError(moveError);
      setIsSaving(false);
    }
  }

  return (
    <Modal title={`Move appointment with ${booking.doctor.full_name}`} onClose={onClose}>
      <p className="mb-4 text-sm text-muted">
        Currently {formatTime(booking.slot.start_time)} on {formatDate(booking.slot.start_time)}. Your current time is
        kept until the new one is confirmed.
      </p>
      <DateStrip selectedDate={selectedDate} onChange={setSelectedDate} />
      <div className="mt-4 space-y-4">
        <Alert kind="error">{friendlyErrorMessage(error)}</Alert>
        {isLoading ? (
          <Spinner label="Checking free times" />
        ) : (
          <SlotPicker slots={slots} selectedSlotId={selectedSlot?.id} onSelect={setSelectedSlot} />
        )}
      </div>
      <button
        type="button"
        className="button-primary mt-6 w-full"
        disabled={!selectedSlot || isSaving}
        onClick={confirmMove}
      >
        {isSaving ? "Moving…" : selectedSlot ? `Move to ${formatTime(selectedSlot.start_time)}` : "Choose a new time"}
      </button>
    </Modal>
  );
}
