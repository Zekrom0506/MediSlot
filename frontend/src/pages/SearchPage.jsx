import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import Alert from "../components/Alert";
import Spinner from "../components/Spinner";
import * as api from "../api/medislot";
import { friendlyErrorMessage } from "../utils/errors";
import { clinicDateString, formatDateString, formatRupees } from "../utils/time";

export default function SearchPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [filters, setFilters] = useState({ specialties: [], cities: [] });
  const [doctors, setDoctors] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState(null);

  const specialty = searchParams.get("specialty") || "";
  const city = searchParams.get("city") || "";
  const date = searchParams.get("date") || "";

  useEffect(() => {
    api.fetchSearchFilters().then(setFilters).catch(() => {});
  }, []);

  useEffect(() => {
    setIsLoading(true);
    setError(null);
    api
      .searchDoctors({ specialty, city, date })
      .then(setDoctors)
      .catch(setError)
      .finally(() => setIsLoading(false));
  }, [specialty, city, date]);

  function updateFilter(name, value) {
    const next = new URLSearchParams(searchParams);
    if (value) {
      next.set(name, value);
    } else {
      next.delete(name);
    }
    setSearchParams(next);
  }

  return (
    <div>
      <h1 className="max-w-xl text-3xl font-bold leading-tight sm:text-4xl">Find a doctor and pick a time that suits you</h1>
      <p className="mt-2 max-w-xl text-muted">Every time you see is free right now. Booking takes one tap.</p>

      <div className="panel mt-6 grid gap-4 p-4 sm:grid-cols-3">
        <div>
          <label htmlFor="specialty" className="field-label">Specialty</label>
          <select id="specialty" className="field-input" value={specialty} onChange={(event) => updateFilter("specialty", event.target.value)}>
            <option value="">Any specialty</option>
            {filters.specialties.map((name) => (
              <option key={name} value={name}>{name}</option>
            ))}
          </select>
        </div>
        <div>
          <label htmlFor="city" className="field-label">City</label>
          <select id="city" className="field-input" value={city} onChange={(event) => updateFilter("city", event.target.value)}>
            <option value="">Any city</option>
            {filters.cities.map((name) => (
              <option key={name} value={name}>{name}</option>
            ))}
          </select>
        </div>
        <div>
          <label htmlFor="date" className="field-label">Free on</label>
          <input id="date" type="date" className="field-input" min={clinicDateString(0)} max={clinicDateString(13)}
            value={date} onChange={(event) => updateFilter("date", event.target.value)} />
        </div>
      </div>

      <div className="mt-6">
        <Alert kind="error">{friendlyErrorMessage(error)}</Alert>
        {isLoading ? (
          <Spinner label="Finding doctors" />
        ) : (
          <DoctorList doctors={doctors} date={date} />
        )}
      </div>
    </div>
  );
}

function DoctorList({ doctors, date }) {
  if (doctors.length === 0) {
    return (
      <p className="py-10 text-muted">
        No doctors match these filters. Try another date or clear the specialty.
      </p>
    );
  }

  return (
    <ul className="panel divide-y divide-line">
      {doctors.map((doctor) => {
        const profileLink = date ? `/doctors/${doctor.id}?date=${date}` : `/doctors/${doctor.id}`;
        return (
          <li key={doctor.id}>
            <Link to={profileLink} className="flex flex-col gap-3 p-4 hover:bg-canvas sm:flex-row sm:items-center sm:justify-between">
              <div>
                <p className="text-lg font-semibold">{doctor.full_name}</p>
                <p className="text-muted">
                  {doctor.specialty}, {doctor.years_of_experience} years experience
                </p>
                <p className="text-sm text-muted">
                  {doctor.clinic.name}, {doctor.clinic.city}
                </p>
              </div>
              <div className="flex items-center gap-4 sm:flex-col sm:items-end sm:gap-1">
                <span className="tabular font-semibold">{formatRupees(doctor.consultation_fee)}</span>
                {doctor.available_slot_count !== null && (
                  <span className="rounded-full bg-brand-soft px-2.5 py-0.5 text-sm font-medium text-brand-dark">
                    {doctor.available_slot_count} free on {formatDateString(date)}
                  </span>
                )}
              </div>
            </Link>
          </li>
        );
      })}
    </ul>
  );
}
