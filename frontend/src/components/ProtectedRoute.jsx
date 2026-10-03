import { Navigate, useLocation } from "react-router-dom";
import { homePathForRole, useAuth } from "../context/AuthContext";
import Spinner from "./Spinner";

export default function ProtectedRoute({ roles, children }) {
  const { user, isLoading } = useAuth();
  const location = useLocation();

  if (isLoading) {
    return <Spinner label="Loading your account" />;
  }
  if (!user) {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  }
  if (roles && !roles.includes(user.role)) {
    return <Navigate to={homePathForRole(user.role)} replace />;
  }
  return children;
}
