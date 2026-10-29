import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import Alert from "../components/Alert";
import { useAuth } from "../context/AuthContext";
import { friendlyErrorMessage } from "../utils/errors";

export default function RegisterPage() {
  const { signUp } = useAuth();
  const navigate = useNavigate();
  const [form, setForm] = useState({ full_name: "", email: "", phone_number: "", password: "" });
  const [error, setError] = useState(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  function updateField(event) {
    setForm({ ...form, [event.target.name]: event.target.value });
  }

  async function handleSubmit(event) {
    event.preventDefault();
    setError(null);
    setIsSubmitting(true);
    try {
      await signUp({ ...form, phone_number: form.phone_number || null });
      navigate("/", { replace: true });
    } catch (signUpError) {
      setError(signUpError);
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <div className="mx-auto max-w-sm">
      <h1 className="text-2xl font-bold">Create a patient account</h1>
      <p className="mt-1 text-muted">You need an account to book and manage appointments.</p>

      <div className="mt-6">
        <Alert kind="error">{friendlyErrorMessage(error)}</Alert>
      </div>

      <form onSubmit={handleSubmit} className="mt-4 space-y-4">
        <div>
          <label htmlFor="full_name" className="field-label">Full name</label>
          <input id="full_name" name="full_name" required minLength={2} className="field-input"
            value={form.full_name} onChange={updateField} autoComplete="name" />
        </div>
        <div>
          <label htmlFor="email" className="field-label">Email</label>
          <input id="email" name="email" type="email" required className="field-input"
            value={form.email} onChange={updateField} autoComplete="email" />
        </div>
        <div>
          <label htmlFor="phone_number" className="field-label">Mobile number (optional)</label>
          <input id="phone_number" name="phone_number" type="tel" placeholder="+91 98765 43210" className="field-input"
            value={form.phone_number} onChange={updateField} autoComplete="tel" />
        </div>
        <div>
          <label htmlFor="password" className="field-label">Password</label>
          <input id="password" name="password" type="password" required minLength={8} maxLength={72}
            className="field-input" value={form.password} onChange={updateField} autoComplete="new-password" />
          <p className="mt-1 text-xs text-muted">At least 8 characters.</p>
        </div>
        <button type="submit" className="button-primary w-full" disabled={isSubmitting}>
          {isSubmitting ? "Creating account…" : "Create account"}
        </button>
      </form>

      <p className="mt-6 text-sm text-muted">
        Already registered? <Link to="/login" className="font-semibold text-brand hover:underline">Log in</Link>
      </p>
    </div>
  );
}
