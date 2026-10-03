export default function Spinner({ label = "Loading" }) {
  return (
    <div className="flex items-center gap-3 py-10 text-muted" role="status">
      <span className="h-5 w-5 animate-spin rounded-full border-2 border-line border-t-brand" />
      <span>{label}…</span>
    </div>
  );
}
