import { Icon } from "./icons";

export function LoadingState({ label = "Memuat data operasional…" }: { label?: string }) {
  return (
    <div className="statePanel" aria-live="polite" aria-busy="true">
      <span className="spinner" />
      <strong>{label}</strong>
      <p>ALOS sedang mengambil data terbaru dari sistem.</p>
    </div>
  );
}

export function ErrorState({ message, retry }: { message: string; retry?: () => void }) {
  return (
    <div className="statePanel stateError" role="alert">
      <span className="stateIcon"><Icon name="risk" /></span>
      <strong>Data belum dapat ditampilkan</strong>
      <p>{message}</p>
      {retry ? <button className="button secondary" onClick={retry} type="button">Coba lagi</button> : null}
    </div>
  );
}

export function EmptyState({ title, description }: { title: string; description: string }) {
  return (
    <div className="statePanel">
      <span className="stateIcon"><Icon name="check" /></span>
      <strong>{title}</strong>
      <p>{description}</p>
    </div>
  );
}
