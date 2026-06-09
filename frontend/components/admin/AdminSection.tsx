interface Props {
  title: string
  action?: React.ReactNode
  children: React.ReactNode
}

export function AdminSection({ title, action, children }: Props) {
  return (
    <section className="mb-6">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-base font-semibold text-gray-900">{title}</h2>
        {action && <div>{action}</div>}
      </div>
      {children}
    </section>
  )
}
