export default function ErrorBanner({ children }: { children: string }) {
  return <p role="alert" className="rounded-xl bg-destructive/5 px-3 py-2 text-sm text-destructive">{children}</p>
}
