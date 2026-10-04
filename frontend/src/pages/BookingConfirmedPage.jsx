import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import Alert from "../components/Alert";
import Spinner from "../components/Spinner";
import * as api from "../api/medislot";
import { friendlyErrorMessage } from "../utils/errors";
import { formatLongDate, formatTime } from "../utils/time";

export default function BookingConfirmedPage() {
  const { bookingId } = useParams();
  const [booking, setBooking] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    api.fetchBooking(bookingId).then(setBooking).catch(setError);
  }, [bookingId]);

  if (error) {
    return <Alert kind="error">{friendlyErrorMessage(error)}</Alert>;
  }
  if (!booking) {
    return <Spinner label="Loading your booking" />;
  }

  return (
    <div className="mx-auto max-w-lg">
      <div className="panel overflow-hidden">
        <div className="bg-brand px-6 py-8 text-white">
          <p className="font-medium text-white/80">Booking confirmed</p>
          <p className="tabular mt-2 text-4xl font-bold">{formatTime(booking.slot.start_time)}</p>
          <p className="mt-1 text-lg">{formatLongDate(booking.slot.start_time)}</p>
        </div>
        <dl className="space-y-4 px-6 py-6">
          <div>
            <dt className="text-sm text-muted">Doctor</dt>
            <dd className="font-semibold">{booking.doctor.full_name}, {booking.doctor.specialty}</dd>
          </div>
          <div>
            <dt className="text-sm text-muted">Where</dt>
            <dd>{booking.doctor.clinic_name}</dd>
            <dd className="text-muted">{booking.doctor.clinic_address}, {booking.doctor.city}</dd>
          </div>
          {booking.reason_for_visit && (
            <div>
              <dt className="text-sm text-muted">Reason for visit</dt>
              <dd>{booking.reason_for_visit}</dd>
            </div>
          )}
          <div>
            <dt className="text-sm text-muted">Booking reference</dt>
            <dd className="tabular font-semibold">#{booking.id}</dd>
          </div>
        </dl>
      </div>
      <p className="mt-4 text-sm text-muted">
        A confirmation email is on its way, and we will remind you a day before. You can cancel up to 2 hours before
        the appointment.
      </p>
      <div className="mt-6 flex gap-3">
        <Link to="/appointments" className="button-primary">View my appointments</Link>
        <Link to="/" className="button-secondary">Book another</Link>
      </div>
    </div>
  );
}
