import { Link } from "react-router-dom";

export default function NotFoundPage() {
  return (
    <div className="py-16">
      <h1 className="text-2xl font-bold">This page does not exist</h1>
      <p className="mt-2 text-muted">The link may be old or mistyped.</p>
      <Link to="/" className="button-primary mt-6">Go to doctor search</Link>
    </div>
  );
}
