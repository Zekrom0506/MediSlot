import { useState } from "react";
import { Link, useLocation, useNavigate, useSearchParams } from "react-router-dom";
import Alert from "../components/Alert";
import { homePathForRole, useAuth } from "../context/AuthContext";
import { friendlyErrorMessage } from "../utils/errors";

export default function LoginPage() {
  const { logIn } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [searchParams] = useSearchParams();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function handleSubmit(event) {
    event.preventDefault();
    setError(null);
    setIsSubmitting(true);
    try {
      const user = await logIn(email, password);
      const returnTo = location.state?.from;
      navigate(returnTo || homePathForRole(user.role), { replace: true });
    } catch (loginError) {
      setError(loginError);
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <div className="mx-auto max-w-sm">
      <h1 className="text-2xl font-bold">Log in</h1>
      <p className="mt-1 text-muted">Patients, doctors and clinic admins all log in here.</p>

      <div className="mt-6 space-y-3">
        {searchParams.get("expired") && <Alert kind="warning">Your session has expired. Please log in again.</Alert>}
        <Alert kind="error">{friendlyErrorMessage(error)}</Alert>
      </div>

      <form onSubmit={handleSubmit} className="mt-4 space-y-4">
        <div>
          <label htmlFor="email" className="field-label">Email</label>
          <input id="email" type="email" autoComplete="email" required className="field-input"
            value={email} onChange={(event) => setEmail(event.target.value)} />
        </div>
        <div>
          <label htmlFor="password" className="field-label">Password</label>
          <input id="password" type="password" autoComplete="current-password" required className="field-input"
            value={password} onChange={(event) => setPassword(event.target.value)} />
        </div>
        <button type="submit" className="button-primary w-full" disabled={isSubmitting}>
          {isSubmitting ? "Logging in…" : "Log in"}
        </button>
      </form>

      <p className="mt-6 text-sm text-muted">
        New patient?{" "}
        <Link to="/register" className="font-semibold text-brand hover:underline">Create an account</Link>
      </p>
    </div>
  );
}
