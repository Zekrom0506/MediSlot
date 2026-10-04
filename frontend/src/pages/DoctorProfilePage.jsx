import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import Alert from "../components/Alert";
import DateStrip from "../components/DateStrip";
import SlotPicker from "../components/SlotPicker";
import Spinner from "../components/Spinner";
import * as api from "../api/medislot";
import { useAuth } from "../context/AuthContext";
import { friendlyErrorMessage } from "../utils/errors";
import { clinicDateString, formatLongDate, formatRupees, formatTime } from "../utils/time";

export default function DoctorProfilePage() {
  const { doctorId } = useParams();
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const { user } = useAuth();

  const [doctor, setDoctor] = useState(null);
  const [selectedDate, setSelectedDate] = useState(searchParams.get("date") || clinicDateString(0));
  const [slots, setSlots] = useState([]);
  const [selectedSlot, setSelectedSlot] = useState(null);
  const [reason, setReason] = useState("");
  const [isLoadingSlots, setIsLoadingSlots] = useState(true);
  const [isBooking, setIsBooking] = useState(false);
  const [error, setError] = useState(null);
  // One key per booking attempt: a retry of the same attempt reuses it,
  // so the server can recognise the duplicate and not book twice.
  const [idempotencyKey, setIdempotencyKey] = useState(() => crypto.randomUUID());

  useEffect(() => {
    api.fetchDoctor(doctorId).then(setDoctor).catch(setError);
  }, [doctorId]);

  const loadSlots = useCallback(() => {
    setIsLoadingSlots(true);
    return api
      .fetchAvailableSlots(doctorId, selectedDate)
      .then(setSlots)
      .catch(setError)
      .finally(() => setIsLoadingSlots(false));
  }, [doctorId, selectedDate]);

  useEffect(() => {
    setSelectedSlot(null);
    loadSlots();
  }, [loadSlots]);

  function chooseSlot(slot) {
    setSelectedSlot(slot);
    setIdempotencyKey(crypto.randomUUID());
    setError(null);
  }

  async function confirmBooking() {
    if (!user) {
      navigate("/login", { state: { from: `/doctors/${doctorId}?date=${selectedDate}` } });
      return;
    }
    setIsBooking(true);
    setError(null);
    try {
      const booking = await api.createBooking(selectedSlot.id, reason.trim(), idempotencyKey);
      navigate(`/bookings/${booking.id}/confirmed`);
    } catch (bookingError) {
      setError(bookingError);
      if (bookingError.code === "SLOT_ALREADY_BOOKED" || bookingError.code === "SLOT_NOT_AVAILABLE") {
        setSelectedSlot(null);
        loadSlots();
      }
    } finally {
      setIsBooking(false);
    }
  }

  if (!doctor) {
    return error ? <Alert kind="error">{friendlyErrorMessage(error)}</Alert> : <Spinner label="Loading doctor" />;
  }

  const canBook = !user || user.role === "patient";

  return (
    <div className="grid gap-8 lg:grid-cols-[1fr_1.6fr]">
      <section className="min-w-0">
        <Link to="/" className="text-sm font-medium text-muted hover:text-ink">Back to search</Link>
        <h1 className="mt-3 text-3xl font-bold">{doctor.full_name}</h1>
        <p className="mt-1 text-lg text-muted">{doctor.specialty}</p>
        <dl className="mt-6 space-y-3 text-sm">
          <div>
            <dt className="text-muted">Clinic</dt>
            <dd className="font-medium">{doctor.clinic.name}</dd>
            <dd>{doctor.clinic.address}, {doctor.clinic.city}</dd>
          </div>
          <div className="grid grid-cols-3 gap-4">
            <div>
              <dt className="text-muted">Fee</dt>
              <dd className="tabular font-medium">{formatRupees(doctor.consultation_fee)}</dd>
            </div>
            <div>
              <dt className="text-muted">Experience</dt>
              <dd className="font-medium">{doctor.years_of_experience} years</dd>
            </div>
            <div>
              <dt className="text-muted">Visit length</dt>
              <dd className="font-medium">{doctor.appointment_length_minutes} min</dd>
            </div>
          </div>
        </dl>
      </section>

      <section className="panel min-w-0 p-4 sm:p-6">
        <h2 className="mb-3 text-lg font-semibold">Choose a time</h2>
        <DateStrip selectedDate={selectedDate} onChange={setSelectedDate} />
        <div className="mt-4 space-y-4">
          <Alert kind="error" onClose={() => setError(null)}>{friendlyErrorMessage(error)}</Alert>
          {isLoadingSlots ? (
            <Spinner label="Checking free times" />
          ) : (
            <SlotPicker slots={slots} selectedSlotId={selectedSlot?.id} onSelect={chooseSlot} />
          )}
        </div>

        {selectedSlot && canBook && (
          <div className="mt-6 border-t border-line pt-6">
            <p className="font-semibold">
              {formatTime(selectedSlot.start_time)}, {formatLongDate(selectedSlot.start_time)}
            </p>
            <label htmlFor="reason" className="field-label mt-4">Reason for visit (optional)</label>
            <textarea id="reason" rows={3} maxLength={500} className="field-input"
              placeholder="For example: follow-up on blood test results"
              value={reason} onChange={(event) => setReason(event.target.value)} />
            <p className="mt-1 text-right text-xs text-muted tabular">{reason.length}/500</p>
            <button type="button" className="button-primary mt-3 w-full" onClick={confirmBooking} disabled={isBooking}>
              {isBooking ? "Booking…" : user ? "Book this time" : "Log in to book"}
            </button>
          </div>
        )}
      </section>
    </div>
  );
}
