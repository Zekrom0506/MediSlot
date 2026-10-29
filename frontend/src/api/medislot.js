import { apiRequest } from "./client";

function queryString(params) {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== "") {
      search.set(key, value);
    }
  }
  const text = search.toString();
  return text ? `?${text}` : "";
}

// Auth
export const register = (details) => apiRequest("/api/auth/register", { method: "POST", body: details });
export const login = (email, password) =>
  apiRequest("/api/auth/login", { method: "POST", body: { email, password } });
export const fetchCurrentUser = () => apiRequest("/api/auth/me");

// Public doctor search
export const searchDoctors = (filters) => apiRequest(`/api/doctors${queryString(filters)}`);
export const fetchSearchFilters = () => apiRequest("/api/doctors/filters");
export const fetchDoctor = (doctorId) => apiRequest(`/api/doctors/${doctorId}`);
export const fetchAvailableSlots = (doctorId, date) =>
  apiRequest(`/api/doctors/${doctorId}/slots${queryString({ date })}`);

// Patient bookings
export const createBooking = (slotId, reasonForVisit, idempotencyKey) =>
  apiRequest("/api/bookings", {
    method: "POST",
    body: { slot_id: slotId, reason_for_visit: reasonForVisit || null },
    headers: { "Idempotency-Key": idempotencyKey },
  });
export const fetchMyBookings = (scope) => apiRequest(`/api/bookings/me?scope=${scope}`);
export const fetchBooking = (bookingId) => apiRequest(`/api/bookings/${bookingId}`);
export const cancelBooking = (bookingId) => apiRequest(`/api/bookings/${bookingId}/cancel`, { method: "POST" });
export const rescheduleBooking = (bookingId, newSlotId) =>
  apiRequest(`/api/bookings/${bookingId}/reschedule`, { method: "POST", body: { new_slot_id: newSlotId } });

// Doctor portal
export const fetchMyDoctorProfile = () => apiRequest("/api/doctor/me");
export const fetchAppointments = (scope) => apiRequest(`/api/doctor/appointments?scope=${scope}`);
export const cancelAppointment = (bookingId) =>
  apiRequest(`/api/doctor/appointments/${bookingId}/cancel`, { method: "POST" });
export const recordOutcome = (bookingId, status) =>
  apiRequest(`/api/doctor/appointments/${bookingId}`, { method: "PATCH", body: { status } });
export const fetchSchedule = () => apiRequest("/api/doctor/schedule");
export const saveSchedule = (entries) => apiRequest("/api/doctor/schedule", { method: "PUT", body: { entries } });
export const fetchMySlots = (date) => apiRequest(`/api/doctor/slots?date=${date}`);
export const blockSlot = (slotId) => apiRequest(`/api/doctor/slots/${slotId}/block`, { method: "POST" });
export const unblockSlot = (slotId) => apiRequest(`/api/doctor/slots/${slotId}/unblock`, { method: "POST" });
export const blockDay = (date) => apiRequest("/api/doctor/block-day", { method: "POST", body: { date } });

// Admin
export const fetchStats = (days) => apiRequest(`/api/admin/stats?days=${days}`);
export const fetchAdminClinics = () => apiRequest("/api/admin/clinics");
export const createClinic = (clinic) => apiRequest("/api/admin/clinics", { method: "POST", body: clinic });
export const updateClinic = (clinicId, changes) =>
  apiRequest(`/api/admin/clinics/${clinicId}`, { method: "PATCH", body: changes });
export const fetchAdminDoctors = () => apiRequest("/api/admin/doctors");
export const createDoctor = (doctor) => apiRequest("/api/admin/doctors", { method: "POST", body: doctor });
export const updateDoctor = (doctorId, changes) =>
  apiRequest(`/api/admin/doctors/${doctorId}`, { method: "PATCH", body: changes });
