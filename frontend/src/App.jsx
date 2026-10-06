import { Route, Routes } from "react-router-dom";
import Layout from "./components/Layout";
import ProtectedRoute from "./components/ProtectedRoute";
import AdminDashboardPage from "./pages/AdminDashboardPage";
import BookingConfirmedPage from "./pages/BookingConfirmedPage";
import DoctorDashboardPage from "./pages/DoctorDashboardPage";
import DoctorProfilePage from "./pages/DoctorProfilePage";
import LoginPage from "./pages/LoginPage";
import MyAppointmentsPage from "./pages/MyAppointmentsPage";
import NotFoundPage from "./pages/NotFoundPage";
import RegisterPage from "./pages/RegisterPage";
import SearchPage from "./pages/SearchPage";

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route path="/" element={<SearchPage />} />
        <Route path="/login" element={<LoginPage />} />
        <Route path="/register" element={<RegisterPage />} />
        <Route path="/doctors/:doctorId" element={<DoctorProfilePage />} />
        <Route
          path="/bookings/:bookingId/confirmed"
          element={<ProtectedRoute roles={["patient"]}><BookingConfirmedPage /></ProtectedRoute>}
        />
        <Route
          path="/appointments"
          element={<ProtectedRoute roles={["patient"]}><MyAppointmentsPage /></ProtectedRoute>}
        />
        <Route
          path="/doctor"
          element={<ProtectedRoute roles={["doctor"]}><DoctorDashboardPage /></ProtectedRoute>}
        />
        <Route
          path="/admin"
          element={<ProtectedRoute roles={["admin"]}><AdminDashboardPage /></ProtectedRoute>}
        />
        <Route path="*" element={<NotFoundPage />} />
      </Route>
    </Routes>
  );
}
