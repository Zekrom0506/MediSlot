import { useCallback, useEffect, useState } from "react";
import Alert from "../components/Alert";
import Modal from "../components/Modal";
import Spinner from "../components/Spinner";
import * as api from "../api/medislot";
import { friendlyErrorMessage } from "../utils/errors";
import { formatDateString, formatRupees } from "../utils/time";

function percent(rate) {
  return `${(rate * 100).toFixed(1)}%`;
}

export default function AdminDashboardPage() {
  return (
    <div className="space-y-10">
      <h1 className="text-2xl font-bold">Clinic overview</h1>
      <StatsSection />
      <ClinicsSection />
      <DoctorsSection />
    </div>
  );
}

function StatsSection() {
  const [days, setDays] = useState(14);
  const [stats, setStats] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    setStats(null);
    api.fetchStats(days).then(setStats).catch(setError);
  }, [days]);

  if (error) {
    return <Alert kind="error">{friendlyErrorMessage(error)}</Alert>;
  }

  return (
    <section>
      <div className="flex items-center justify-between gap-3">
        <h2 className="text-lg font-semibold">Bookings</h2>
        <select className="field-input w-auto py-1.5 text-sm" value={days} onChange={(event) => setDays(Number(event.target.value))}
          aria-label="Period">
          <option value={7}>Last 7 days</option>
          <option value={14}>Last 14 days</option>
          <option value={30}>Last 30 days</option>
        </select>
      </div>
      {!stats ? (
        <Spinner label="Loading statistics" />
      ) : (
        <>
          <dl className="panel mt-3 grid grid-cols-2 divide-line sm:grid-cols-4 sm:divide-x">
            <Figure label="Bookings made" value={stats.total_bookings} />
            <Figure label="Cancellation rate" value={percent(stats.cancellation_rate)} />
            <Figure label="No-show rate" value={percent(stats.no_show_rate)} />
            <Figure label="Completed visits" value={stats.completed_bookings} />
          </dl>
          <div className="mt-4 grid gap-4 lg:grid-cols-[2fr_1fr]">
            <BookingsChart days={stats.bookings_per_day} />
            <div className="panel p-4">
              <h3 className="font-semibold">Busiest doctors</h3>
              {stats.busiest_doctors.length === 0 ? (
                <p className="mt-2 text-sm text-muted">No bookings in this period.</p>
              ) : (
                <ol className="mt-3 space-y-2">
                  {stats.busiest_doctors.map((doctor) => (
                    <li key={doctor.doctor_id} className="flex justify-between gap-2 text-sm">
                      <span>
                        <span className="font-medium">{doctor.full_name}</span>
                        <span className="block text-muted">{doctor.specialty}</span>
                      </span>
                      <span className="tabular font-semibold">{doctor.booking_count}</span>
                    </li>
                  ))}
                </ol>
              )}
            </div>
          </div>
        </>
      )}
    </section>
  );
}

function Figure({ label, value }) {
  return (
    <div className="p-4">
      <dt className="text-sm text-muted">{label}</dt>
      <dd className="tabular mt-1 text-2xl font-bold">{value}</dd>
    </div>
  );
}

function BookingsChart({ days }) {
  let highest = 1;
  for (const day of days) {
    highest = Math.max(highest, day.count);
  }
  return (
    <div className="panel p-4">
      <h3 className="font-semibold">Bookings per day</h3>
      <div className="mt-4 flex h-40 items-end gap-1" role="img" aria-label="Bar chart of bookings per day">
        {days.map((day) => (
          <div key={day.date} className="group flex h-full flex-1 flex-col justify-end" title={`${formatDateString(day.date)}: ${day.count}`}>
            <div className="rounded-t bg-brand/80 group-hover:bg-brand" style={{ height: `${(day.count / highest) * 100}%`, minHeight: day.count ? "4px" : "1px" }} />
          </div>
        ))}
      </div>
      <div className="mt-2 flex justify-between text-xs text-muted">
        <span>{formatDateString(days[0].date)}</span>
        <span>{formatDateString(days[days.length - 1].date)}</span>
      </div>
    </div>
  );
}

function ClinicsSection() {
  const [clinics, setClinics] = useState(null);
  const [form, setForm] = useState({ name: "", address: "", city: "" });
  const [error, setError] = useState(null);

  const loadClinics = useCallback(() => {
    api.fetchAdminClinics().then(setClinics).catch(setError);
  }, []);

  useEffect(() => {
    loadClinics();
  }, [loadClinics]);

  async function handleCreate(event) {
    event.preventDefault();
    setError(null);
    try {
      await api.createClinic(form);
      setForm({ name: "", address: "", city: "" });
      loadClinics();
    } catch (createError) {
      setError(createError);
    }
  }

  async function toggleActive(clinic) {
    if (
      clinic.is_active &&
      !window.confirm(`Deactivate ${clinic.name}? Their upcoming appointments will be cancelled and patients emailed.`)
    ) {
      return;
    }
    setError(null);
    try {
      await api.updateClinic(clinic.id, { is_active: !clinic.is_active });
      loadClinics();
    } catch (updateError) {
      setError(updateError);
    }
  }

  return (
    <section>
      <h2 className="text-lg font-semibold">Clinics</h2>
      <div className="mt-3">
        <Alert kind="error" onClose={() => setError(null)}>{friendlyErrorMessage(error)}</Alert>
      </div>
      {!clinics ? (
        <Spinner label="Loading clinics" />
      ) : (
        <ul className="panel mt-3 divide-y divide-line">
          {clinics.map((clinic) => (
            <li key={clinic.id} className="flex flex-wrap items-center justify-between gap-3 p-4">
              <div>
                <p className={`font-semibold ${clinic.is_active ? "" : "text-muted line-through"}`}>{clinic.name}</p>
                <p className="text-sm text-muted">{clinic.address}, {clinic.city}</p>
              </div>
              <button type="button" className={clinic.is_active ? "button-danger text-sm" : "button-secondary py-2 text-sm"}
                onClick={() => toggleActive(clinic)}>
                {clinic.is_active ? "Deactivate" : "Reactivate"}
              </button>
            </li>
          ))}
        </ul>
      )}
      <form onSubmit={handleCreate} className="panel mt-3 grid gap-3 p-4 sm:grid-cols-[1fr_1.5fr_1fr_auto] sm:items-end">
        <div>
          <label className="field-label" htmlFor="clinic-name">Clinic name</label>
          <input id="clinic-name" required minLength={2} className="field-input" value={form.name}
            onChange={(event) => setForm({ ...form, name: event.target.value })} />
        </div>
        <div>
          <label className="field-label" htmlFor="clinic-address">Address</label>
          <input id="clinic-address" required minLength={5} className="field-input" value={form.address}
            onChange={(event) => setForm({ ...form, address: event.target.value })} />
        </div>
        <div>
          <label className="field-label" htmlFor="clinic-city">City</label>
          <input id="clinic-city" required minLength={2} className="field-input" value={form.city}
            onChange={(event) => setForm({ ...form, city: event.target.value })} />
        </div>
        <button type="submit" className="button-primary">Add clinic</button>
      </form>
    </section>
  );
}

const EMPTY_DOCTOR = {
  full_name: "",
  email: "",
  password: "",
  phone_number: "",
  clinic_id: "",
  specialty: "",
  years_of_experience: 5,
  consultation_fee: 500,
  appointment_length_minutes: 15,
};

function DoctorsSection() {
  const [doctors, setDoctors] = useState(null);
  const [clinics, setClinics] = useState([]);
  const [isAdding, setIsAdding] = useState(false);
  const [error, setError] = useState(null);

  const loadDoctors = useCallback(() => {
    api.fetchAdminDoctors().then(setDoctors).catch(setError);
  }, []);

  useEffect(() => {
    loadDoctors();
    api.fetchAdminClinics().then(setClinics).catch(() => {});
  }, [loadDoctors]);

  async function toggleActive(doctor) {
    if (
      doctor.is_active &&
      !window.confirm(`Deactivate ${doctor.full_name}? Their upcoming appointments will be cancelled and patients emailed.`)
    ) {
      return;
    }
    setError(null);
    try {
      await api.updateDoctor(doctor.id, { is_active: !doctor.is_active });
      loadDoctors();
    } catch (updateError) {
      setError(updateError);
    }
  }

  return (
    <section>
      <div className="flex items-center justify-between gap-3">
        <h2 className="text-lg font-semibold">Doctors</h2>
        <button type="button" className="button-primary py-2 text-sm" onClick={() => setIsAdding(true)}>Add doctor</button>
      </div>
      <div className="mt-3">
        <Alert kind="error" onClose={() => setError(null)}>{friendlyErrorMessage(error)}</Alert>
      </div>
      {!doctors ? (
        <Spinner label="Loading doctors" />
      ) : (
        <div className="panel mt-3 overflow-x-auto">
          <table className="w-full min-w-[40rem] text-left text-sm">
            <thead className="border-b border-line text-muted">
              <tr>
                <th className="px-4 py-3 font-medium">Doctor</th>
                <th className="px-4 py-3 font-medium">Clinic</th>
                <th className="px-4 py-3 font-medium">Fee</th>
                <th className="px-4 py-3 font-medium">Visit</th>
                <th className="px-4 py-3" />
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {doctors.map((doctor) => (
                <tr key={doctor.id} className={doctor.is_active ? "" : "text-muted"}>
                  <td className="px-4 py-3">
                    <span className="font-semibold">{doctor.full_name}</span>
                    <span className="block text-muted">{doctor.specialty}</span>
                  </td>
                  <td className="px-4 py-3">{doctor.clinic.name}</td>
                  <td className="tabular px-4 py-3">{formatRupees(doctor.consultation_fee)}</td>
                  <td className="tabular px-4 py-3">{doctor.appointment_length_minutes} min</td>
                  <td className="px-4 py-3 text-right">
                    <button type="button" className={doctor.is_active ? "button-danger text-sm" : "button-secondary py-2 text-sm"}
                      onClick={() => toggleActive(doctor)}>
                      {doctor.is_active ? "Deactivate" : "Reactivate"}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {isAdding && (
        <AddDoctorDialog
          clinics={clinics.filter((clinic) => clinic.is_active)}
          onClose={() => setIsAdding(false)}
          onCreated={() => {
            setIsAdding(false);
            loadDoctors();
          }}
        />
      )}
    </section>
  );
}

function AddDoctorDialog({ clinics, onClose, onCreated }) {
  const [form, setForm] = useState({ ...EMPTY_DOCTOR, clinic_id: clinics[0]?.id || "" });
  const [error, setError] = useState(null);
  const [isSaving, setIsSaving] = useState(false);

  function updateField(event) {
    setForm({ ...form, [event.target.name]: event.target.value });
  }

  async function handleSubmit(event) {
    event.preventDefault();
    setIsSaving(true);
    setError(null);
    try {
      await api.createDoctor({
        ...form,
        phone_number: form.phone_number || null,
        clinic_id: Number(form.clinic_id),
        years_of_experience: Number(form.years_of_experience),
        appointment_length_minutes: Number(form.appointment_length_minutes),
      });
      onCreated();
    } catch (createError) {
      setError(createError);
      setIsSaving(false);
    }
  }

  return (
    <Modal title="Add a doctor" onClose={onClose}>
      <form onSubmit={handleSubmit} className="grid gap-3 sm:grid-cols-2">
        <div className="sm:col-span-2">
          <Alert kind="error">{friendlyErrorMessage(error)}</Alert>
        </div>
        <TextField label="Full name" name="full_name" value={form.full_name} onChange={updateField} required />
        <TextField label="Specialty" name="specialty" value={form.specialty} onChange={updateField} required />
        <TextField label="Login email" name="email" type="email" value={form.email} onChange={updateField} required />
        <TextField label="First password" name="password" type="password" value={form.password} onChange={updateField} required minLength={8} />
        <TextField label="Phone (optional)" name="phone_number" type="tel" value={form.phone_number} onChange={updateField} />
        <div>
          <label className="field-label" htmlFor="clinic_id">Clinic</label>
          <select id="clinic_id" name="clinic_id" className="field-input" value={form.clinic_id} onChange={updateField} required>
            {clinics.map((clinic) => (
              <option key={clinic.id} value={clinic.id}>{clinic.name}</option>
            ))}
          </select>
        </div>
        <TextField label="Years of experience" name="years_of_experience" type="number" min={0} value={form.years_of_experience} onChange={updateField} />
        <TextField label="Fee (₹)" name="consultation_fee" type="number" min={0} value={form.consultation_fee} onChange={updateField} />
        <TextField label="Visit length (minutes)" name="appointment_length_minutes" type="number" min={5} max={120}
          value={form.appointment_length_minutes} onChange={updateField} />
        <div className="flex items-end sm:col-span-2">
          <button type="submit" className="button-primary w-full" disabled={isSaving}>
            {isSaving ? "Adding…" : "Add doctor"}
          </button>
        </div>
      </form>
    </Modal>
  );
}

function TextField({ label, name, ...inputProps }) {
  return (
    <div>
      <label className="field-label" htmlFor={name}>{label}</label>
      <input id={name} name={name} className="field-input" {...inputProps} />
    </div>
  );
}
