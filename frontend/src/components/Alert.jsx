const STYLES = {
  error: "border-danger/30 bg-danger-soft text-danger",
  warning: "border-warn/30 bg-warn-soft text-warn",
  success: "border-brand/30 bg-brand-soft text-brand-dark",
  info: "border-line bg-white text-ink",
};

export default function Alert({ kind = "info", children, onClose }) {
  if (!children) {
    return null;
  }
  return (
    <div
      className={`flex items-start justify-between gap-4 rounded-lg border px-4 py-3 text-sm ${STYLES[kind]}`}
      role={kind === "error" ? "alert" : "status"}
    >
      <div>{children}</div>
      {onClose && (
        <button type="button" onClick={onClose} className="font-semibold opacity-70 hover:opacity-100" aria-label="Dismiss">
          ✕
        </button>
      )}
    </div>
  );
}
