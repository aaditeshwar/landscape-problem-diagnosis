type Command = {
  label: string
  command: string
}

type Props = {
  title?: string
  commands: Command[]
}

export function CommandFooter({ title = 'CLI commands', commands }: Props) {
  return (
    <footer className="mt-10 rounded-lg border border-stone-200 bg-stone-50 p-4">
      <h3 className="text-sm font-semibold text-stone-800">{title}</h3>
      <ul className="mt-3 space-y-2 text-sm text-stone-700">
        {commands.map((item) => (
          <li key={item.label}>
            <span className="text-stone-600">{item.label}: </span>
            <code className="block whitespace-pre-wrap rounded bg-stone-200/80 px-2 py-1 font-mono text-xs text-stone-900 sm:inline">
              {item.command}
            </code>
          </li>
        ))}
      </ul>
    </footer>
  )
}
